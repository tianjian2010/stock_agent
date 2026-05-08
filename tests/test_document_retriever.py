import unittest
from pathlib import Path

from services.document_retriever import DocumentRetriever, parse_document_metadata, parse_query_date


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
        self.assertRegex(parse_query_date("5/8日的资料有哪一些？") or "", r"^\d{4}-05-08$")

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


if __name__ == "__main__":
    unittest.main()
