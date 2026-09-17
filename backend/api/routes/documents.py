from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from backend.api.resources import (
    DocumentOperationError,
    is_supported_document,
    milvus_manager,
    delete_document as delete_document_data,
    replace_document,
    resolve_upload_path,
    stage_upload_file,
)
from backend.db.models import User
from backend.infra.auth import get_current_user, require_admin
from backend.jobs import DELETE_STEPS, delete_job_manager, upload_job_manager
from backend.schemas import (
    DocumentBatchUploadResponse,
    DocumentDeleteJobResponse,
    DocumentDeleteResponse,
    DocumentDeleteStartResponse,
    DocumentInfo,
    DocumentListResponse,
    DocumentUploadJobResponse,
    DocumentUploadResponse,
    DocumentUploadStartResponse,
)

router = APIRouter(tags=["documents"])


@router.get("/documents/file/{filename}")
async def view_pdf(filename: str, _: User = Depends(get_current_user)):
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="仅支持查看 PDF 文档")
    try:
        file_path = resolve_upload_path(filename)
    except ValueError:
        raise HTTPException(status_code=400, detail="文件名不合法")
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="文档不存在")

    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        headers={
            "Content-Disposition": "inline",
            "Cache-Control": "private, no-store",
        },
    )


def _update_job_progress(manager, job_id: str, progress: dict) -> None:
    manager.update_step(
        job_id, progress["step"], progress["percent"], progress["status"], progress["message"],
        total_chunks=progress.get("total_chunks"),
        processed_chunks=progress.get("processed_chunks"),
    )


def _process_upload_job(job_id: str, file_path: str, filename: str) -> None:
    try:
        replace_document(
            filename, Path(file_path),
            on_progress=lambda progress: _update_job_progress(upload_job_manager, job_id, progress),
        )
        upload_job_manager.complete_job(job_id, f"成功上传并处理 {filename}")
    except Exception as e:
        failed_step = e.step if isinstance(e, DocumentOperationError) else "parse"
        upload_job_manager.fail_job(job_id, failed_step, str(e))


def _process_delete_job(job_id: str, filename: str) -> None:
    try:
        chunks_deleted = delete_document_data(
            filename,
            on_progress=lambda progress: _update_job_progress(delete_job_manager, job_id, progress),
        )
        delete_job_manager.complete_job(job_id, f"已删除 {filename}，向量数据 {chunks_deleted} 条")
    except Exception as e:
        current_step = e.step if isinstance(e, DocumentOperationError) else "prepare"
        delete_job_manager.fail_job(job_id, current_step, str(e))


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(_: User = Depends(require_admin)):
    try:
        milvus_manager.init_collection()
        results = milvus_manager.query(
            output_fields=["filename", "file_type"],
            limit=10000,
        )

        file_stats = {}
        for item in results:
            filename = item.get("filename", "")
            file_type = item.get("file_type", "")
            if filename not in file_stats:
                file_stats[filename] = {
                    "filename": filename,
                    "file_type": file_type,
                    "chunk_count": 0,
                }
            file_stats[filename]["chunk_count"] += 1

        documents = [DocumentInfo(**stats) for stats in file_stats.values()]
        return DocumentListResponse(documents=documents)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取文档列表失败: {str(e)}")


@router.post("/documents/upload/async", response_model=DocumentUploadStartResponse)
async def upload_document_async(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    _: User = Depends(require_admin),
):
    filename = file.filename or ""
    if not filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    if not is_supported_document(filename):
        raise HTTPException(status_code=400, detail="仅支持 PDF、Word、Excel 和 HTML 文档")
    try:
        resolve_upload_path(filename)
    except ValueError:
        raise HTTPException(status_code=400, detail="文件名不能包含路径")

    job = upload_job_manager.create_job(filename)

    try:
        upload_job_manager.update_step(job["job_id"], "upload", 1, "running", "正在保存文件到服务器")
        file_path = await stage_upload_file(file, filename)
        upload_job_manager.complete_step(job["job_id"], "upload", "文件已上传，等待后台处理")
    except Exception as e:
        upload_job_manager.fail_job(job["job_id"], "upload", f"文件保存失败: {e}")
        raise HTTPException(status_code=500, detail=f"文件保存失败: {e}")

    background_tasks.add_task(_process_upload_job, job["job_id"], str(file_path), filename)
    return DocumentUploadStartResponse(
        job_id=job["job_id"],
        filename=filename,
        message="文件已上传，正在后台解析和向量化入库",
    )


@router.post("/documents/upload/batch/async", response_model=DocumentBatchUploadResponse)
async def upload_documents_batch_async(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    _: User = Depends(require_admin),
):
    if not files:
        raise HTTPException(status_code=400, detail="请至少选择一个文件")

    filenames = set()
    for file in files:
        filename = file.filename or ""
        if not filename:
            raise HTTPException(status_code=400, detail="文件名不能为空")
        if "/" in filename or "\\" in filename:
            raise HTTPException(status_code=400, detail="文件名不能包含路径")
        if not is_supported_document(filename):
            raise HTTPException(status_code=400, detail=f"{filename}：仅支持 PDF、Word、Excel 和 HTML 文档")
        if filename in filenames:
            raise HTTPException(status_code=400, detail=f"同一批次不能上传同名文件：{filename}")
        filenames.add(filename)

    jobs = []
    for file in files:
        filename = file.filename
        job_id = upload_job_manager.create_job(filename)["job_id"]
        try:
            upload_job_manager.update_step(job_id, "upload", 1, "running", "正在保存文件到服务器")
            file_path = await stage_upload_file(file, filename)
            upload_job_manager.complete_step(job_id, "upload", "文件已上传，等待后台处理")
        except Exception as e:
            upload_job_manager.fail_job(job_id, "upload", f"文件保存失败: {e}")
        else:
            # 同一批次顺序处理，复用现有模型和逐文件失败状态。
            background_tasks.add_task(_process_upload_job, job_id, str(file_path), filename)
        jobs.append(DocumentUploadJobResponse(**upload_job_manager.get_job(job_id)))

    return DocumentBatchUploadResponse(jobs=jobs)


@router.get("/documents/upload/jobs/{job_id}", response_model=DocumentUploadJobResponse)
async def get_upload_job(job_id: str, _: User = Depends(require_admin)):
    job = upload_job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="上传任务不存在或已过期")
    return DocumentUploadJobResponse(**job)


@router.get("/documents/upload/jobs", response_model=list[DocumentUploadJobResponse])
async def list_upload_jobs(_: User = Depends(require_admin)):
    jobs = upload_job_manager.list_jobs()
    jobs.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return [DocumentUploadJobResponse(**job) for job in jobs]


@router.delete("/documents/delete/async/{filename}", response_model=DocumentDeleteStartResponse)
async def delete_document_async(
    filename: str,
    background_tasks: BackgroundTasks,
    _: User = Depends(require_admin),
):
    try:
        resolve_upload_path(filename)
    except ValueError:
        raise HTTPException(status_code=400, detail="文件名不能包含路径")
    job = delete_job_manager.create_job(
        filename,
        steps=DELETE_STEPS,
        current_step="prepare",
        message="等待删除",
        completion_step="parent_store",
    )
    delete_job_manager.update_step(job["job_id"], "prepare", 1, "running", "删除任务已提交")
    background_tasks.add_task(_process_delete_job, job["job_id"], filename)
    return DocumentDeleteStartResponse(
        job_id=job["job_id"],
        filename=filename,
        message=f"正在删除 {filename}",
    )


@router.get("/documents/delete/jobs/{job_id}", response_model=DocumentDeleteJobResponse)
async def get_delete_job(job_id: str, _: User = Depends(require_admin)):
    job = delete_job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="删除任务不存在或已过期")
    return DocumentDeleteJobResponse(**job)


@router.post("/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(file: UploadFile = File(...), _: User = Depends(require_admin)):
    try:
        filename = file.filename or ""
        if not filename:
            raise HTTPException(status_code=400, detail="文件名不能为空")
        if not is_supported_document(filename):
            raise HTTPException(status_code=400, detail="仅支持 PDF、Word、Excel 和 HTML 文档")
        try:
            resolve_upload_path(filename)
        except ValueError:
            raise HTTPException(status_code=400, detail="文件名不能包含路径")

        staged_path = await stage_upload_file(file, filename)
        result = await run_in_threadpool(replace_document, filename, staged_path)

        return DocumentUploadResponse(
            filename=filename,
            chunks_processed=result["leaf_count"],
            message=(
                f"成功上传并处理 {filename}，叶子分块 {result['leaf_count']} 个，"
                f"父级分块 {result['parent_count']} 个（存入 PostgreSQL）"
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文档上传失败: {str(e)}")


@router.delete("/documents/{filename}", response_model=DocumentDeleteResponse)
async def delete_document(filename: str, _: User = Depends(require_admin)):
    try:
        chunks_deleted = await run_in_threadpool(delete_document_data, filename)

        return DocumentDeleteResponse(
            filename=filename,
            chunks_deleted=chunks_deleted,
            message=f"成功删除文档 {filename} 的索引与本地文件",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除文档失败: {str(e)}")
