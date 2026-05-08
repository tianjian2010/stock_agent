import shutil
import unittest
from pathlib import Path

from services.doc_loader import DocumentLoader


class DocumentLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.test_dir = Path("data/test_doc_loader")
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)
        self.test_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_load_csv_as_text_table(self) -> None:
        path = self.test_dir / "sample.csv"
        path.write_text("code,name\n300750,宁德时代\n600519,贵州茅台\n", encoding="utf-8")

        loader = DocumentLoader()
        content = loader.load(path)

        self.assertIsNotNone(content)
        self.assertIn("300750", content)
        self.assertIn("宁德时代", content)

    def test_load_audio_transcript_sidecar(self) -> None:
        audio_path = self.test_dir / "roadshow.mp3"
        transcript_path = self.test_dir / "roadshow.transcript.txt"
        audio_path.write_bytes(b"fake-audio")
        transcript_path.write_text("管理层表示订单恢复明显。", encoding="utf-8")

        loader = DocumentLoader()
        content = loader.load(audio_path)

        self.assertEqual(content, "管理层表示订单恢复明显。")


if __name__ == "__main__":
    unittest.main()
