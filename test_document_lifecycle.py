import json
import unittest
from copy import deepcopy
from unittest.mock import patch

import test_document_uploads as uploads


class DocumentFailureTests(unittest.TestCase):
    def setUp(self):
        uploads.DocumentUploadTests.setUp(self)
        self.parents = []
        self.leaves = []
        self.resources.parent_chunk_store.get_documents_by_filename.side_effect = (
            lambda filename: deepcopy([row for row in self.parents if row["filename"] == filename])
        )
        self.resources.parent_chunk_store.delete_by_filename.side_effect = self.delete_parents
        self.resources.parent_chunk_store.upsert_documents.side_effect = self.write_parents
        self.resources.milvus_manager.query_all.side_effect = (
            lambda filter_expr, output_fields: deepcopy([
                {**{key: row[key] for key in output_fields}, "id": 123} for row in self.leaves
                if row["filename"] == json.loads(filter_expr.split(" == ", 1)[1])
            ])
        )
        self.resources.milvus_manager.delete.side_effect = self.delete_leaves
        self.resources.milvus_manager.insert.side_effect = self.restore_leaves
        self.resources.loader.load_document.side_effect = self.parse_document

    def chunks(self, filename, text):
        common = {
            "filename": filename, "text": text, "file_type": "PDF",
            "file_path": str(self.resources.UPLOAD_DIR / filename),
            "page_number": 0, "chunk_idx": 0, "root_chunk_id": filename + "::root",
        }
        parent = {**common, "chunk_id": filename + "::root", "parent_chunk_id": "", "chunk_level": 1}
        leaf = {
            **common, "chunk_id": filename + "::leaf", "parent_chunk_id": parent["chunk_id"],
            "chunk_level": 3, "dense_embedding": [0.2, 0.8],
        }
        return parent, leaf

    def seed_old_document(self, filename="guide.pdf"):
        (self.resources.UPLOAD_DIR / filename).write_bytes(b"old document")
        parent, leaf = self.chunks(filename, "old content")
        self.parents.append(parent)
        self.leaves.append(leaf)
        return deepcopy(self.parents), deepcopy(self.leaves)

    def parse_document(self, path, filename):
        parent, leaf = self.chunks(filename, "new content")
        parent["file_path"] = leaf["file_path"] = path
        return [parent, leaf]

    def delete_parents(self, filename):
        count = sum(row["filename"] == filename for row in self.parents)
        self.parents[:] = [row for row in self.parents if row["filename"] != filename]
        return count

    def write_parents(self, rows):
        self.parents.extend(deepcopy(rows))
        return len(rows)

    def delete_leaves(self, expression):
        filename = json.loads(expression.split(" == ", 1)[1])
        count = sum(row["filename"] == filename for row in self.leaves)
        self.leaves[:] = [row for row in self.leaves if row["filename"] != filename]
        return {"delete_count": count}

    def restore_leaves(self, rows):
        for row in rows:
            self.assertNotIn("id", row)
            self.assertNotIn("sparse_embedding", row)
        self.leaves.extend(deepcopy(rows))

    def upload(self, filename="guide.pdf"):
        response = self.client.post(
            "/documents/upload/async", files={"file": (filename, b"new document")}
        )
        self.assertEqual(response.status_code, 200, response.text)
        return self.client.get(f'/documents/upload/jobs/{response.json()["job_id"]}').json()

    def assert_old_document(self, snapshot):
        self.assertEqual((self.resources.UPLOAD_DIR / "guide.pdf").read_bytes(), b"old document")
        self.assertEqual((self.parents, self.leaves), snapshot)

    def test_parse_failure_preserves_old_file_and_indexes_for_all_upload_entries(self):
        snapshot = self.seed_old_document()
        self.resources.loader.load_document.side_effect = ValueError("invalid PDF")
        for endpoint in ("/documents/upload", "/documents/upload/async", "/documents/upload/batch/async"):
            with self.subTest(endpoint=endpoint):
                field = "files" if "batch" in endpoint else "file"
                response = self.client.post(endpoint, files={field: ("guide.pdf", b"broken PDF")})
                if endpoint == "/documents/upload":
                    self.assertEqual(response.status_code, 500)
                else:
                    self.assertEqual(response.status_code, 200, response.text)
                self.assert_old_document(snapshot)

    def test_save_failure_preserves_old_document_and_cleans_staged_file(self):
        snapshot = self.seed_old_document()

        async def fail_save(file, path):
            path.write_bytes(b"partial upload")
            raise OSError("disk full")

        with patch.object(self.resources, "save_upload_file", side_effect=fail_save):
            response = self.client.post(
                "/documents/upload/async", files={"file": ("guide.pdf", b"new document")}
            )
        self.assertEqual(response.status_code, 500)
        self.assert_old_document(snapshot)
        self.assertEqual(
            [path for path in self.resources.UPLOAD_DIR.rglob("*") if path.is_file()],
            [self.resources.UPLOAD_DIR / "guide.pdf"],
        )

    def test_snapshot_failure_does_not_modify_old_document(self):
        snapshot = self.seed_old_document()
        self.resources.milvus_manager.query_all.side_effect = RuntimeError("snapshot unavailable")
        job = self.upload()
        self.assertEqual(job["status"], "failed")
        self.assert_old_document(snapshot)

    def test_partial_vector_write_failure_restores_old_indexes_or_removes_first_upload(self):
        for replacing in (True, False):
            with self.subTest(replacing=replacing):
                self.parents.clear()
                self.leaves.clear()
                (self.resources.UPLOAD_DIR / "guide.pdf").unlink(missing_ok=True)
                snapshot = self.seed_old_document() if replacing else ([], [])

                def fail_second_batch(rows, progress_callback=None):
                    self.leaves.extend(deepcopy(rows[:1]))
                    raise RuntimeError("second vector batch failed")

                self.resources.milvus_writer.write_documents.side_effect = fail_second_batch
                job = self.upload()
                self.assertEqual(job["status"], "failed")
                self.assertEqual(job["current_step"], "vector_store")
                self.assertEqual((self.parents, self.leaves), snapshot)
                if replacing:
                    self.assert_old_document(snapshot)
                else:
                    self.assertFalse((self.resources.UPLOAD_DIR / "guide.pdf").exists())

    def test_publish_failure_restores_indexes_and_old_file(self):
        snapshot = self.seed_old_document()
        self.resources.milvus_writer.write_documents.side_effect = (
            lambda rows, progress_callback=None: self.leaves.extend(deepcopy(rows))
        )
        with patch("os.replace", side_effect=OSError("publish failed")):
            job = self.upload()
        self.assertEqual(job["status"], "failed")
        self.assertIn("publish failed", job["error"])
        self.assert_old_document(snapshot)

    def test_failed_compensation_reports_both_errors(self):
        self.seed_old_document()
        self.resources.milvus_writer.write_documents.side_effect = RuntimeError("write failed")
        self.resources.milvus_manager.insert.side_effect = RuntimeError("restore failed")
        job = self.upload()
        self.assertEqual(job["status"], "failed")
        self.assertIn("write failed", job["error"])
        self.assertIn("restore failed", job["error"])
        self.assertIn("恢复未完成", job["error"])
        self.assertEqual((self.resources.UPLOAD_DIR / "guide.pdf").read_bytes(), b"old document")

    def test_delete_retry_finishes_after_parent_store_failure(self):
        self.seed_old_document()
        with patch.object(self.resources.parent_chunk_store, "delete_by_filename", side_effect=RuntimeError("PG unavailable")):
            response = self.client.delete("/documents/guide.pdf")
        self.assertEqual(response.status_code, 500)
        self.assertTrue((self.resources.UPLOAD_DIR / "guide.pdf").exists())
        response = self.client.delete("/documents/guide.pdf")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse((self.resources.UPLOAD_DIR / "guide.pdf").exists())
        self.assertEqual((self.parents, self.leaves), ([], []))


if __name__ == "__main__":
    unittest.main()
