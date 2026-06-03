import unittest
from pathlib import Path

from services.document_retriever import (
    DocumentRetriever,
    parse_document_metadata,
    parse_query_date,
)


class FakeLoader:
    def __init__(self, documents, chunks_by_source):
        self.documents = documents
        self.chunks_by_source = chunks_by_source

    def scan_directories(self):
        return self.documents

    def load_and_chunk(self, file_path):
        return self.chunks_by_source[str(file_path)]


class DocumentRetrieverTests(unittest.TestCase):
    def test_parse_document_metadata_supports_mmdd(self) -> None:
        metadata = parse_document_metadata("创新药0415.docx")
        self.assertEqual(metadata["topic"], "创新药")
        self.assertRegex(metadata["published_at"], r"^\d{4}-04-15$")

    def test_parse_query_date_supports_month_day(self) -> None:
        self.assertRegex(parse_query_date("5/8日的资料有哪些？") or "", r"^\d{4}-05-08$")

    def test_search_returns_relevant_chunk(self) -> None:
        documents = [
            {
                "content": "量子通信进入产业加速期。",
                "metadata": {"source": "docs/量子0416.txt", "filename": "量子0416.txt"},
            },
            {
                "content": "创新药板块估值修复仍在继续。",
                "metadata": {"source": "docs/创新药0415.txt", "filename": "创新药0415.txt"},
            },
        ]
        chunks_by_source = {
            str(Path("docs/量子0416.txt")): [
                {
                    "content": "量子通信进入产业加速期。",
                    "metadata": {
                        "source": "docs/量子0416.txt",
                        "filename": "量子0416.txt",
                        "chunk_id": 0,
                        "total_chunks": 1,
                    },
                }
            ],
            str(Path("docs/创新药0415.txt")): [
                {
                    "content": "创新药板块估值修复仍在继续。",
                    "metadata": {
                        "source": "docs/创新药0415.txt",
                        "filename": "创新药0415.txt",
                        "chunk_id": 0,
                        "total_chunks": 1,
                    },
                }
            ],
        }

        retriever = DocumentRetriever(loader=FakeLoader(documents, chunks_by_source))
        retriever.index_documents(force=True)
        results = retriever.search("量子", k=1)

        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0].metadata["filename"], "量子0416.txt")
        self.assertIn("量子通信", results[0].content)

    def test_list_documents_by_date_filters_published_at(self) -> None:
        documents = [
            {
                "content": "a",
                "metadata": {"source": "docs/福瑞医科0508.txt", "filename": "福瑞医科0508.txt"},
            },
            {
                "content": "b",
                "metadata": {"source": "docs/国芯科技0507.txt", "filename": "国芯科技0507.txt"},
            },
        ]
        chunks_by_source = {
            str(Path("docs/福瑞医科0508.txt")): [
                {
                    "content": "a",
                    "metadata": {
                        "source": "docs/福瑞医科0508.txt",
                        "filename": "福瑞医科0508.txt",
                        "chunk_id": 0,
                        "total_chunks": 1,
                    },
                }
            ],
            str(Path("docs/国芯科技0507.txt")): [
                {
                    "content": "b",
                    "metadata": {
                        "source": "docs/国芯科技0507.txt",
                        "filename": "国芯科技0507.txt",
                        "chunk_id": 0,
                        "total_chunks": 1,
                    },
                }
            ],
        }

        retriever = DocumentRetriever(loader=FakeLoader(documents, chunks_by_source))
        retriever.index_documents(force=True)
        results = retriever.list_documents_by_date("2026-05-08")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["filename"], "福瑞医科0508.txt")

    def test_get_stats_and_latest_documents_window(self) -> None:
        documents = [
            {
                "content": "a",
                "metadata": {"source": "docs/a0510.txt", "filename": "a0510.txt"},
            },
            {
                "content": "b",
                "metadata": {"source": "docs/b0509.txt", "filename": "b0509.txt"},
            },
        ]
        chunks_by_source = {
            str(Path("docs/a0510.txt")): [
                {
                    "content": "a",
                    "metadata": {
                        "source": "docs/a0510.txt",
                        "filename": "a0510.txt",
                        "chunk_id": 0,
                        "total_chunks": 1,
                    },
                }
            ],
            str(Path("docs/b0509.txt")): [
                {
                    "content": "b",
                    "metadata": {
                        "source": "docs/b0509.txt",
                        "filename": "b0509.txt",
                        "chunk_id": 0,
                        "total_chunks": 1,
                    },
                }
            ],
        }
        retriever = DocumentRetriever(loader=FakeLoader(documents, chunks_by_source))
        retriever.index_documents(force=True)

        stats = retriever.get_stats()
        self.assertEqual(stats["document_count"], 2)
        self.assertEqual(stats["chunk_count"], 2)
        self.assertIn("vector_ready", stats)

        latest_only = retriever.find_latest_documents()
        latest_window = retriever.find_latest_documents(days=2)
        self.assertGreaterEqual(len(latest_only), 1)
        self.assertGreaterEqual(len(latest_window), len(latest_only))

    def test_normalize_mmdd_rollback_on_future_date(self) -> None:
        from datetime import date as date_type
        from services.document_retriever import _normalize_filename_date

        today = date_type.today()
        future_mmdd = f"{(today.month):02d}{(today.day + 5):02d}"
        if len(future_mmdd) != 4:
            future_mmdd = f"{(today.month + 1):02d}01"

        year, month, day = _normalize_filename_date(future_mmdd)
        inferred = date_type(year, month, day)

        self.assertLessEqual(inferred, today)

    def test_normalize_mmdd_past_date_stays_current_year(self) -> None:
        from datetime import date as date_type
        from services.document_retriever import _normalize_filename_date

        today = date_type.today()
        year, _month, _day = _normalize_filename_date("0101")
        self.assertEqual(year, today.year)

    def test_parse_query_date_mmdd_rollback(self) -> None:
        from datetime import date as date_type

        today = date_type.today()
        future_day = today.day + 7
        future_month = today.month
        if future_day > 28:
            future_month += 1
            future_day = 1
        future_query = f"{future_month}月{future_day}日的资料"

        result = parse_query_date(future_query)
        if result:
            parsed = date_type.fromisoformat(result)
            self.assertLessEqual(parsed, today)

    def test_parse_query_date_past_mmdd_stays_current_year(self) -> None:
        from datetime import date as date_type

        result = parse_query_date("1月1日的资料")
        today = date_type.today()
        self.assertIn(str(today.year), result)

    def test_parse_document_metadata_invalid_mmdd_does_not_raise(self) -> None:
        metadata = parse_document_metadata("bad1301.txt")
        self.assertEqual(metadata["filename"], "bad1301.txt")
        self.assertEqual(metadata["published_at"], "")

    def test_parse_document_metadata_supports_yyyy_mm_dd_with_separators(self) -> None:
        metadata = parse_document_metadata("福瑞医科__2026-05-12__v1.docx")
        self.assertEqual(metadata["topic"], "福瑞医科")
        self.assertEqual(metadata["published_at"], "2026-05-12")


if __name__ == "__main__":
    unittest.main()
