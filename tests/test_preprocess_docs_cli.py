import tempfile
import unittest
from pathlib import Path

from scripts import preprocess_docs


class PreprocessDocsCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.docs_dir = Path(self.temp_dir.name) / "stock_docs"
        self.docs_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_text(self, name: str, content: str) -> Path:
        path = self.docs_dir / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_build_records_parses_mmdd_with_default_year(self) -> None:
        self._write_text("Alpha0508.txt", "alpha")

        records = preprocess_docs.build_records(self.docs_dir, default_year=2026)

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertTrue(record.parse_ok)
        self.assertEqual(record.published_at, "2026-05-08")
        self.assertEqual(record.topic_sanitized, "Alpha")

    def test_build_records_marks_unparsed_file(self) -> None:
        self._write_text("NoDateNote.txt", "note")

        records = preprocess_docs.build_records(self.docs_dir, default_year=2026)

        self.assertFalse(records[0].parse_ok)
        self.assertEqual(records[0].parse_reason, "no_date_pattern")

    def test_build_rename_plan_assigns_versions_for_same_topic_date(self) -> None:
        self._write_text("Alpha0508.txt", "v1")
        self._write_text("Alpha0508(1).txt", "v2")

        records = preprocess_docs.build_records(self.docs_dir, default_year=2026)
        plan = preprocess_docs.build_rename_plan(records)
        targets = sorted(
            row["target_name"] for row in plan if row.get("needs_rename")
        )

        self.assertEqual(
            targets,
            ["Alpha__2026-05-08__v1.txt", "Alpha__2026-05-08__v2.txt"],
        )

    def test_apply_rename_actions_renames_files(self) -> None:
        self._write_text("Alpha0508.txt", "v1")
        self._write_text("Alpha0508(1).txt", "v2")

        records = preprocess_docs.build_records(self.docs_dir, default_year=2026)
        plan = preprocess_docs.build_rename_plan(records)
        preprocess_docs.apply_rename_actions(plan)

        files = sorted(path.name for path in self.docs_dir.iterdir() if path.is_file())
        self.assertEqual(
            files,
            ["Alpha__2026-05-08__v1.txt", "Alpha__2026-05-08__v2.txt"],
        )

    def test_build_dedup_report_detects_exact_duplicates(self) -> None:
        self._write_text("Alpha0508.txt", "same-content")
        self._write_text("Alpha0508(1).txt", "same-content")
        self._write_text("Alpha0508(2).txt", "different-content")

        records = preprocess_docs.build_records(self.docs_dir, default_year=2026)
        report = preprocess_docs.build_dedup_report(records)

        self.assertEqual(report["duplicate_file_count"], 1)
        self.assertEqual(len(report["duplicates"]), 1)
        duplicate = report["duplicates"][0]
        self.assertEqual(duplicate["topic"], "Alpha")
        self.assertEqual(duplicate["published_at"], "2026-05-08")


if __name__ == "__main__":
    unittest.main()
