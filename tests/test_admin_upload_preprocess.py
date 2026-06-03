import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.datastructures import UploadFile

from app.api import admin


class _FakeRetriever:
    def __init__(self) -> None:
        self.calls = 0

    def index_documents_incremental(self) -> dict[str, object]:
        self.calls += 1
        return {
            "status": "incremental",
            "document_count": 1,
            "chunk_count": 1,
            "vector_ready": False,
            "updated_files": 1,
            "removed_files": 0,
        }


class AdminUploadPreprocessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.docs_dir = Path(self.temp_dir.name) / "stock_docs"
        self.docs_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @staticmethod
    def _make_upload(filename: str, content: bytes) -> UploadFile:
        return UploadFile(filename=filename, file=io.BytesIO(content))

    def test_upload_preprocesses_filename_before_save(self) -> None:
        retriever = _FakeRetriever()
        upload = self._make_upload("Alpha0508.txt", b"hello")

        with patch.object(admin, "STOCK_DOCS_DIR", self.docs_dir), patch.object(
            admin, "DOCUMENT_DEFAULT_YEAR", 2026
        ), patch.object(admin, "get_document_retriever", return_value=retriever):
            result = admin.upload_documents(files=[upload], overwrite=False)

        self.assertEqual(len(result["saved"]), 1)
        self.assertEqual(result["saved"][0]["filename"], "Alpha__2026-05-08__v1.txt")
        self.assertTrue((self.docs_dir / "Alpha__2026-05-08__v1.txt").exists())
        self.assertEqual(retriever.calls, 1)

    def test_upload_skips_unparseable_filename(self) -> None:
        retriever = _FakeRetriever()
        upload = self._make_upload("NoDate.txt", b"hello")

        with patch.object(admin, "STOCK_DOCS_DIR", self.docs_dir), patch.object(
            admin, "DOCUMENT_DEFAULT_YEAR", 2026
        ), patch.object(admin, "get_document_retriever", return_value=retriever):
            result = admin.upload_documents(files=[upload], overwrite=False)

        self.assertEqual(len(result["saved"]), 0)
        self.assertEqual(len(result["skipped"]), 1)
        self.assertEqual(result["skipped"][0]["status"], "invalid_name")
        self.assertEqual(retriever.calls, 0)

    def test_upload_skips_exact_duplicate_content_same_topic_date(self) -> None:
        retriever = _FakeRetriever()
        upload_1 = self._make_upload("Alpha0508.txt", b"same-content")
        upload_2 = self._make_upload("Alpha0508(1).txt", b"same-content")

        with patch.object(admin, "STOCK_DOCS_DIR", self.docs_dir), patch.object(
            admin, "DOCUMENT_DEFAULT_YEAR", 2026
        ), patch.object(admin, "get_document_retriever", return_value=retriever):
            result = admin.upload_documents(files=[upload_1, upload_2], overwrite=False)

        self.assertEqual(len(result["saved"]), 1)
        self.assertEqual(len(result["skipped"]), 1)
        self.assertEqual(result["skipped"][0]["status"], "duplicate")
        self.assertEqual(retriever.calls, 1)


if __name__ == "__main__":
    unittest.main()
