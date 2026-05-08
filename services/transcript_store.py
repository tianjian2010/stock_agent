"""Transcript storage and lookup utilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import TRANSCRIPTS_DIR

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".mp4"}


class TranscriptStore:
    """Maps audio files to pre-generated transcript text files."""

    def __init__(self, transcript_dir: str | Path | None = None):
        self.transcript_dir = Path(transcript_dir or TRANSCRIPTS_DIR)

    def get_transcript_for_audio(self, audio_path: Path) -> dict[str, Any] | None:
        if not audio_path.exists():
            return None

        candidates = [
            self.transcript_dir / f"{audio_path.stem}.txt",
            self.transcript_dir / f"{audio_path.name}.txt",
            audio_path.with_suffix(audio_path.suffix + ".txt"),
            audio_path.with_suffix(".txt"),
            audio_path.with_suffix(".transcript.txt"),
            audio_path.with_suffix(".json"),
            audio_path.with_suffix(".transcript.json"),
        ]

        for candidate in candidates:
            result = self._load_candidate(candidate)
            if result:
                return result
        return None

    def _load_candidate(self, path: Path) -> dict[str, Any] | None:
        if not path.exists() or not path.is_file():
            return None

        if path.suffix.lower() == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return None

            text = self._extract_text_from_json(data)
            if text:
                return {"content": text, "source": str(path), "kind": "audio_transcript"}
            return None

        try:
            content = path.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception:
            return None

        if not content:
            return None

        return {"content": content, "source": str(path), "kind": "audio_transcript"}

    def _extract_text_from_json(self, data: Any) -> str:
        if isinstance(data, str):
            return data.strip()
        if isinstance(data, dict):
            for key in ("text", "transcript", "content"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            segments = data.get("segments") or data.get("chunks") or data.get("utterances")
            if isinstance(segments, list):
                texts = []
                for item in segments:
                    if isinstance(item, dict):
                        text = item.get("text") or item.get("content")
                        if isinstance(text, str) and text.strip():
                            texts.append(text.strip())
                return "\n".join(texts)
        if isinstance(data, list):
            texts = []
            for item in data:
                if isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if isinstance(text, str) and text.strip():
                        texts.append(text.strip())
            return "\n".join(texts)
        return ""
