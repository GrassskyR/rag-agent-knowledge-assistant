import json
import logging
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from threading import Lock
from typing import Literal, NotRequired, TypedDict

from fastapi import UploadFile

from backend.indexing import (
    DocumentLoader,
    MilvusWriter,
    ParentChunkStore,
    embedding_service,
)
from backend.indexing.milvus_client import get_milvus_store

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR.parent / "data"
UPLOAD_DIR = DATA_DIR / "documents"
logger = logging.getLogger(__name__)
_document_write_lock = Lock()


class DocumentProgress(TypedDict):
    step: str
    status: Literal["running", "completed"]
    percent: int
    message: str
    processed_chunks: NotRequired[int]
    total_chunks: NotRequired[int]


class ReplacementResult(TypedDict):
    filename: str
    parent_count: int
    leaf_count: int


class DocumentIndexSnapshot(TypedDict):
    parents: list[dict]
    leaf_rows: list[dict]


class DocumentOperationError(RuntimeError):
    def __init__(self, step: str, error: Exception, recovery: str, recovery_error: str | None = None):
        self.step = step
        self.recovery = recovery
        self.recovery_error = recovery_error
        status = {
            "unchanged": "原文档与索引未修改",
            "restored": "已恢复替换前的索引",
            "incomplete": f"恢复未完成：{recovery_error}",
            "retry_delete": "删除未完成，可重试删除",
        }[recovery]
        super().__init__(f"{error}；{status}")


def resolve_upload_path(filename: str) -> Path:
    """将文件名解析到上传目录内，拒绝路径穿越。"""
    if not filename or "/" in filename or "\\" in filename or Path(filename).name != filename:
        raise ValueError("文件名不合法")
    upload_root = UPLOAD_DIR.resolve()
    file_path = (upload_root / filename).resolve()
    if file_path.parent != upload_root:
        raise ValueError("文件名不合法")
    return file_path

loader = DocumentLoader()
parent_chunk_store = ParentChunkStore()
milvus_manager = get_milvus_store()
milvus_writer = MilvusWriter(embedding_service=embedding_service, milvus_manager=milvus_manager)


def _report_progress(on_progress, step, percent, message, **counts) -> None:
    if on_progress is None:
        return
    try:
        on_progress({
            "step": step, "percent": percent, "message": message,
            "status": "completed" if percent == 100 else "running", **counts,
        })
    except Exception:
        # 进度展示失败不能撤销已经发布的文档。
        logger.exception("文档进度更新失败")


def _filename_filter(filename: str) -> str:
    return f"filename == {json.dumps(filename, ensure_ascii=False)}"


def _snapshot_document_indexes(filename: str) -> DocumentIndexSnapshot:
    parents = parent_chunk_store.get_documents_by_filename(filename)
    fields = [
        "dense_embedding", "text", "filename", "file_type", "file_path",
        "page_number", "chunk_idx", "chunk_id", "parent_chunk_id", "root_chunk_id", "chunk_level",
    ]
    leaf_rows = milvus_manager.query_all(
        filter_expr=_filename_filter(filename),
        output_fields=fields,
    )
    # 查询迭代器会附带游标主键，恢复时只保留可写入的业务字段。
    return {"parents": parents, "leaf_rows": [{field: row[field] for field in fields} for row in leaf_rows]}


def _delete_document_indexes(filename: str) -> int:
    result = milvus_manager.delete(_filename_filter(filename))
    parent_chunk_store.delete_by_filename(filename)
    return result.get("delete_count", 0) if isinstance(result, dict) else 0


def _restore_document_indexes(filename: str, snapshot: DocumentIndexSnapshot) -> None:
    _delete_document_indexes(filename)
    parent_chunk_store.upsert_documents(snapshot["parents"])
    # 复用原密集向量，自动 ID 和 BM25 稀疏向量由 Milvus 重新生成。
    for offset in range(0, len(snapshot["leaf_rows"]), 50):
        milvus_manager.insert(snapshot["leaf_rows"][offset:offset + 50])


def _remove_staged_file(staged_path: Path) -> None:
    try:
        staged_path.unlink(missing_ok=True)
    except OSError:
        logger.exception("清理上传临时文件失败：%s", staged_path)


async def stage_upload_file(file: UploadFile, filename: str) -> Path:
    resolve_upload_path(filename)
    ensure_upload_dir()
    staging_dir = UPLOAD_DIR / ".staging"
    staging_dir.mkdir(exist_ok=True)
    fd, path = tempfile.mkstemp(prefix="upload-", suffix=Path(filename).suffix, dir=staging_dir)
    os.close(fd)
    staged_path = Path(path)
    try:
        await save_upload_file(file, staged_path)
    except BaseException:
        _remove_staged_file(staged_path)
        raise
    return staged_path


def replace_document(
    filename: str,
    staged_path: Path,
    *,
    on_progress: Callable[[DocumentProgress], None] | None = None,
) -> ReplacementResult:
    """先解析新文件；替换索引失败时补偿，全部写入后才发布正式文件。"""
    upload_path = resolve_upload_path(filename)
    staged_path = staged_path.resolve()
    if staged_path.parent != (upload_path.parent / ".staging").resolve():
        raise ValueError("上传临时路径不合法")
    step = "parse"
    try:
        _report_progress(on_progress, step, 5, "正在解析文档并执行三级分块")
        new_docs = loader.load_document(str(staged_path), filename)
        if not new_docs:
            raise ValueError("文档处理失败，未能提取内容")
        for doc in new_docs:
            doc["file_path"] = str(upload_path)
        parent_docs = [doc for doc in new_docs if int(doc.get("chunk_level", 0) or 0) in (1, 2)]
        leaf_docs = [doc for doc in new_docs if int(doc.get("chunk_level", 0) or 0) == 3]
        if not leaf_docs:
            raise ValueError("文档处理失败，未生成可检索叶子分块")
        _report_progress(on_progress, step, 100, f"解析完成：父级分块 {len(parent_docs)} 个，叶子分块 {len(leaf_docs)} 个")

        with _document_write_lock:
            step = "cleanup"
            _report_progress(on_progress, step, 10, "正在备份并清理同名旧文档索引")
            milvus_manager.init_collection()
            snapshot = _snapshot_document_indexes(filename)
            try:
                _delete_document_indexes(filename)
                _report_progress(on_progress, step, 100, "旧索引已备份并清理")

                step = "parent_store"
                _report_progress(on_progress, step, 20, "正在写入父级分块")
                parent_chunk_store.upsert_documents(parent_docs)
                _report_progress(on_progress, step, 100, f"父级分块已入库：{len(parent_docs)} 个")

                step = "vector_store"
                _report_progress(on_progress, step, 0, "正在向量化入库", total_chunks=len(leaf_docs), processed_chunks=0)

                def on_vector_progress(processed: int, total: int) -> None:
                    percent = min(round(processed * 100 / total), 99) if total else 99
                    _report_progress(on_progress, "vector_store", percent, f"正在向量化入库：{processed} / {total}", total_chunks=total, processed_chunks=processed)

                milvus_writer.write_documents(leaf_docs, progress_callback=on_vector_progress)
                # 同文件系统的替换是提交点；此后进度回调不能触发补偿。
                os.replace(staged_path, upload_path)
            except Exception as error:
                try:
                    _restore_document_indexes(filename, snapshot)
                except Exception as recovery_error:
                    raise DocumentOperationError(step, error, "incomplete", str(recovery_error)) from error
                raise DocumentOperationError(step, error, "restored") from error

        _report_progress(on_progress, "vector_store", 100, "向量化入库及文档发布完成", total_chunks=len(leaf_docs), processed_chunks=len(leaf_docs))
        return {"filename": filename, "parent_count": len(parent_docs), "leaf_count": len(leaf_docs)}
    except DocumentOperationError:
        raise
    except Exception as error:
        raise DocumentOperationError(step, error, "unchanged") from error
    finally:
        _remove_staged_file(staged_path)


def delete_document(
    filename: str,
    *,
    on_progress: Callable[[DocumentProgress], None] | None = None,
) -> int:
    """按顺序删除索引与文件；已删除的数据可安全重试。"""
    upload_path = resolve_upload_path(filename)
    step = "prepare"
    with _document_write_lock:
        try:
            _report_progress(on_progress, step, 50, "正在初始化 Milvus 集合")
            milvus_manager.init_collection()
            _report_progress(on_progress, step, 100, "准备完成")
            step = "milvus"
            _report_progress(on_progress, step, 20, "正在删除向量分块")
            result = milvus_manager.delete(_filename_filter(filename))
            count = result.get("delete_count", 0) if isinstance(result, dict) else 0
            _report_progress(on_progress, step, 100, f"共删除 {count} 条向量记录")
            _report_progress(on_progress, "bm25", 100, "BM25 统计由 Milvus 自动维护")
            step = "parent_store"
            _report_progress(on_progress, step, 20, "正在清理父级分块、缓存和本地文件")
            parent_chunk_store.delete_by_filename(filename)
            upload_path.unlink(missing_ok=True)
            _report_progress(on_progress, step, 100, "父级分块、缓存和本地文件已清理")
            return count
        except Exception as error:
            raise DocumentOperationError(step, error, "retry_delete") from error


def is_supported_document(filename: str) -> bool:
    file_lower = filename.lower()
    return (
        file_lower.endswith(".pdf")
        or file_lower.endswith((".docx", ".doc"))
        or file_lower.endswith((".xlsx", ".xls"))
        or file_lower.endswith((".html", ".htm"))
    )


async def save_upload_file(file, file_path: Path) -> None:
    with open(file_path, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)


def ensure_upload_dir() -> None:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
