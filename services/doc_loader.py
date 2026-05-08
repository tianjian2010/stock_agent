"""Document loader service for research materials."""

from __future__ import annotations

import logging
import csv
from pathlib import Path
from typing import Any

from app.config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    MAX_SPREADSHEET_COLS,
    MAX_SPREADSHEET_ROWS,
    STOCK_DOCS_PATHS,
)
from services.transcript_store import AUDIO_EXTENSIONS, TranscriptStore

logger = logging.getLogger(__name__)


class DocumentLoader:
    """Document loader for txt, docx, pdf, xlsx and transcript-backed audio."""

    def __init__(
        self,
        chunk_size: int = CHUNK_SIZE,
        chunk_overlap: int = CHUNK_OVERLAP,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.transcript_store = TranscriptStore()
        self._document_extensions = {".txt", ".docx", ".pdf", ".xlsx", ".xls", ".csv"}
        self._supported_extensions = self._document_extensions | AUDIO_EXTENSIONS

    @property
    def supported_extensions(self) -> set[str]:
        return set(self._supported_extensions)

    def is_supported_file(self, filename: str) -> bool:
        return Path(filename).suffix.lower() in self._supported_extensions

    def _load_txt(self, file_path: Path) -> str:
        return file_path.read_text(encoding="utf-8", errors="ignore")

    def _load_docx(self, file_path: Path) -> str:
        from docx import Document

        doc = Document(file_path)
        paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
        return "\n\n".join(paragraphs)

    def _load_pdf(self, file_path: Path) -> str:
        from pypdf import PdfReader

        reader = PdfReader(str(file_path))
        pages = []
        for index, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(f"[Page {index}]\n{text}")
        return "\n\n".join(pages)

    def _load_spreadsheet(self, file_path: Path) -> str:
        suffix = file_path.suffix.lower()
        if suffix == ".csv":
            return self._load_csv(file_path)
        return self._load_excel(file_path)

    def _load_csv(self, file_path: Path) -> str:
        rows: list[list[str]] = []
        with open(file_path, "r", encoding="utf-8", errors="ignore", newline="") as handle:
            reader = csv.reader(handle)
            for index, row in enumerate(reader):
                if index >= MAX_SPREADSHEET_ROWS:
                    break
                rows.append(row[:MAX_SPREADSHEET_COLS])
        return self._rows_to_text("Sheet1", rows)

    def _load_excel(self, file_path: Path) -> str:
        try:
            import pandas as pd
        except Exception as exc:
            logger.warning("Excel support unavailable for %s: %s", file_path, exc)
            return ""

        excel = pd.ExcelFile(file_path)
        sections: list[str] = []
        for sheet_name in excel.sheet_names[:5]:
            frame = excel.parse(sheet_name, nrows=MAX_SPREADSHEET_ROWS)
            if frame.empty:
                continue
            truncated = frame.iloc[:, :MAX_SPREADSHEET_COLS].fillna("")
            rows = [list(map(str, truncated.columns.tolist()))]
            rows.extend(truncated.astype(str).values.tolist())
            sections.append(self._rows_to_text(sheet_name, rows))
        return "\n\n".join(section for section in sections if section)

    def _rows_to_text(self, sheet_name: str, rows: list[list[str]]) -> str:
        if not rows:
            return ""
        lines = [",".join(cell.strip() for cell in row) for row in rows if row]
        return f"[Sheet: {sheet_name}]\n" + "\n".join(lines)

    def _load_audio_transcript(self, file_path: Path) -> str | None:
        transcript = self.transcript_store.get_transcript_for_audio(file_path)
        if transcript is None:
            return None
        return transcript["content"]

    def load(self, file_path: Path) -> str | None:
        if not file_path.exists():
            logger.warning("File not found: %s", file_path)
            return None

        suffix = file_path.suffix.lower()
        if suffix not in self._supported_extensions:
            logger.warning("Unsupported file type: %s", suffix)
            return None

        try:
            if suffix == ".txt":
                return self._load_txt(file_path)
            if suffix == ".docx":
                return self._load_docx(file_path)
            if suffix == ".pdf":
                return self._load_pdf(file_path)
            if suffix in {".xlsx", ".xls", ".csv"}:
                return self._load_spreadsheet(file_path)
            if suffix in AUDIO_EXTENSIONS:
                return self._load_audio_transcript(file_path)
        except Exception as exc:
            logger.error("Error loading %s: %s", file_path, exc)
            return None

        return None

    def load_and_chunk(self, file_path: Path) -> list[dict[str, Any]]:
        content = self.load(file_path)
        if not content:
            return []

        chunks = []
        start = 0
        chunk_id = 0
        step = max(1, self.chunk_size - self.chunk_overlap)

        while start < len(content):
            end = start + self.chunk_size
            chunk_text = content[start:end]
            chunks.append(
                {
                    "content": chunk_text,
                    "metadata": {
                        "source": str(file_path),
                        "filename": file_path.name,
                        "chunk_id": chunk_id,
                        "total_chunks": -1,
                        "file_type": file_path.suffix.lower(),
                    },
                }
            )
            start += step
            chunk_id += 1

        for chunk in chunks:
            chunk["metadata"]["total_chunks"] = len(chunks)

        return chunks

    def scan_directories(
        self,
        directories: list[Path] | None = None,
    ) -> list[dict[str, Any]]:
        directories = directories or STOCK_DOCS_PATHS
        documents: list[dict[str, Any]] = []

        for directory in directories:
            if not directory.exists():
                logger.warning("Directory not found: %s", directory)
                continue

            for ext in self._supported_extensions:
                for file_path in directory.rglob(f"*{ext}"):
                    try:
                        content = self.load(file_path)
                        if content:
                            documents.append(
                                {
                                    "content": content,
                                    "metadata": {
                                        "source": str(file_path),
                                        "filename": file_path.name,
                                        "size": file_path.stat().st_size,
                                        "file_type": file_path.suffix.lower(),
                                    },
                                }
                            )
                    except Exception as exc:
                        logger.error("Error loading %s: %s", file_path, exc)

        return documents
