"""Document processor skill."""

from typing import Any

from langchain_core.tools import BaseTool

from services.document_retriever import get_document_retriever


class DocProcessorSkill:
    """Document retrieval skill for stock research materials."""

    name = "doc_processor"
    description = "Index and search stock research documents"

    def __init__(self):
        self.retriever = get_document_retriever()

    def index_documents(self) -> dict[str, Any]:
        return self.retriever.index_documents()

    def search_documents(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        results = self.retriever.search(query, k)
        return [{"content": item.content, "metadata": item.metadata} for item in results]

    def get_document_by_file(self, filename: str) -> str | None:
        document = self.retriever.get_document(filename)
        return None if document is None else document["content"]


def create_doc_processor_tools() -> list[BaseTool]:
    from langchain_core.tools import tool

    skill = DocProcessorSkill()

    @tool
    def index_research_documents() -> dict[str, Any]:
        """Index all stock research documents for searching."""
        return skill.index_documents()

    @tool
    def search_research_documents(query: str, k: int = 5) -> list[dict[str, Any]]:
        """Search indexed research documents."""
        return skill.search_documents(query, k)

    @tool
    def get_document_content(filename: str) -> str | None:
        """Get full document content by filename."""
        return skill.get_document_by_file(filename)

    return [index_research_documents, search_research_documents, get_document_content]


_doc_skill: DocProcessorSkill | None = None


def get_doc_processor_skill() -> DocProcessorSkill:
    """Get the document processor skill instance."""
    global _doc_skill
    if _doc_skill is None:
        _doc_skill = DocProcessorSkill()
    return _doc_skill
