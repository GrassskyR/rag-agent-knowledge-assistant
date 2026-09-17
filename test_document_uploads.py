import importlib.util
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.infra.auth import get_current_user, get_db
from backend.jobs.upload_jobs import UploadJobManager


ROOT = Path(__file__).resolve().parent


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DocumentUploadTests(unittest.TestCase):
    def setUp(self):
        # 使用真实路由、文件保存和任务管理，仅替换模型与外部存储。
        indexing = ModuleType("backend.indexing")
        for name in ("DocumentLoader", "MilvusWriter", "ParentChunkStore", "embedding_service"):
            setattr(indexing, name, Mock())
        milvus = ModuleType("backend.indexing.milvus_client")
        milvus.get_milvus_store = Mock()
        with patch.dict(sys.modules, {"backend.indexing": indexing, "backend.indexing.milvus_client": milvus}):
            self.resources = load_module("upload_test_resources", "backend/api/resources.py")
        with patch.dict(sys.modules, {"backend.api.resources": self.resources}):
            self.routes = load_module("upload_test_routes", "backend/api/routes/documents.py")

        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.resources.UPLOAD_DIR = Path(self.directory.name)
        self.routes.UPLOAD_DIR = self.resources.UPLOAD_DIR
        self.routes.upload_job_manager = UploadJobManager()
        self.resources.loader.load_document.side_effect = lambda path, filename: [
            {"filename": filename, "chunk_level": 1},
            {"filename": filename, "chunk_level": 3},
        ]
        self.routes.milvus_manager.query.return_value = []
        self.resources.milvus_manager.query_all.return_value = []
        self.resources.parent_chunk_store.get_documents_by_filename.return_value = []
        self.app = FastAPI()
        self.app.include_router(self.routes.router)
        self.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role="admin")
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def upload(self, filenames):
        return self.client.post(
            "/documents/upload/batch/async",
            files=[("files", (filename, b"document content", "application/octet-stream")) for filename in filenames],
        )

    def get_jobs(self, response):
        self.assertEqual(response.status_code, 200, response.text)
        return [
            self.client.get(f'/documents/upload/jobs/{job["job_id"]}').json()
            for job in response.json()["jobs"]
        ]

    def test_batch_upload_saves_each_file_and_completes_independent_jobs(self):
        filenames = ["guide.pdf", "notes.docx", "sheet.xlsx", "page.html"]
        jobs = self.get_jobs(self.upload(filenames))
        self.assertEqual([job["filename"] for job in jobs], filenames)
        self.assertEqual(len({job["job_id"] for job in jobs}), len(filenames))
        self.assertTrue(all(job["status"] == "completed" for job in jobs))
        for filename in filenames:
            self.assertEqual((self.routes.UPLOAD_DIR / filename).read_bytes(), b"document content")
        self.assertEqual(self.resources.parent_chunk_store.upsert_documents.call_count, len(filenames))
        self.assertEqual(self.resources.milvus_writer.write_documents.call_count, len(filenames))
        self.assertEqual(
            [call.args[1] for call in self.resources.loader.load_document.call_args_list], filenames
        )

    def test_parse_failure_does_not_stop_remaining_files(self):
        self.resources.loader.load_document.side_effect = [
            ValueError("invalid PDF"),
            [{"filename": "good.html", "chunk_level": 3}],
        ]
        jobs = self.get_jobs(self.upload(["bad.pdf", "good.html"]))
        self.assertEqual([job["status"] for job in jobs], ["failed", "completed"])
        self.assertEqual(jobs[0]["current_step"], "parse")
        self.assertIn("invalid PDF", jobs[0]["error"])
        self.resources.milvus_writer.write_documents.assert_called_once()

    def test_save_failure_is_returned_and_remaining_files_are_processed(self):
        save_upload_file = self.resources.save_upload_file

        async def save(file, path):
            if file.filename == "bad.pdf":
                raise OSError("save failed")
            await save_upload_file(file, path)

        with patch.object(self.resources, "save_upload_file", side_effect=save):
            response = self.upload(["bad.pdf", "good.html"])
        self.assertEqual(response.json()["jobs"][0]["status"], "failed")
        jobs = self.get_jobs(response)
        self.assertEqual([job["status"] for job in jobs], ["failed", "completed"])
        self.assertEqual(jobs[0]["current_step"], "upload")
        self.assertEqual(self.resources.loader.load_document.call_args.args[1], "good.html")

    def test_invalid_batches_are_rejected_before_any_write(self):
        for filenames in (["good.pdf", "bad.txt"], ["same.pdf", "same.pdf"], ["../outside.pdf"]):
            with self.subTest(filenames=filenames):
                response = self.upload(filenames)
                self.assertEqual(response.status_code, 400, response.text)
                self.assertEqual(self.routes.upload_job_manager.list_jobs(), [])
                self.assertEqual(list(self.routes.UPLOAD_DIR.iterdir()), [])
        self.resources.loader.load_document.assert_not_called()

    def test_missing_files_and_wrong_multipart_field_are_rejected(self):
        for files in (None, [("file", ("one.pdf", b"content"))]):
            with self.subTest(files=files):
                response = self.client.post("/documents/upload/batch/async", files=files)
                self.assertEqual(response.status_code, 422)
        self.assertEqual(self.routes.upload_job_manager.list_jobs(), [])

    def test_batch_upload_requires_admin(self):
        self.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role="user")
        self.assertEqual(self.upload(["one.pdf"]).status_code, 403)
        del self.app.dependency_overrides[get_current_user]
        self.app.dependency_overrides[get_db] = lambda: None
        self.assertEqual(self.upload(["one.pdf"]).status_code, 401)
        self.assertEqual(self.routes.upload_job_manager.list_jobs(), [])

    def test_existing_single_upload_endpoints_keep_their_contract(self):
        for endpoint in ("/documents/upload", "/documents/upload/async"):
            with self.subTest(endpoint=endpoint):
                response = self.client.post(endpoint, files={"file": ("single.html", b"content")})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["filename"], "single.html")
                if endpoint.endswith("/async"):
                    job_id = response.json()["job_id"]
                    job = self.client.get(f"/documents/upload/jobs/{job_id}").json()
                    self.assertEqual(job["status"], "completed")
                else:
                    self.assertEqual(response.json()["chunks_processed"], 1)


if __name__ == "__main__":
    unittest.main()
