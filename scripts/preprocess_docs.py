#!/usr/bin/env python3
"""Preprocess stock research documents for stable retrieval.

Subcommands:
- audit: inspect filename/date/topic quality and duplicate risks
- rename: rename files to canonical format
- dedup: detect or move exact-content duplicates
- manifest: export document metadata manifest

Safe by default: file-moving commands require --apply.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any


DATE_PATTERNS = (
    re.compile(r"(?P<year>20\d{2})[-_/\.](?P<month>\d{1,2})[-_/\.](?P<day>\d{1,2})"),
    re.compile(r"(?P<year>20\d{2})(?P<month>\d{2})(?P<day>\d{2})"),
    re.compile(r"(?<!\d)(?P<month>\d{2})(?P<day>\d{2})(?!\d)$"),
)
VERSION_SUFFIX_PATTERN = re.compile(r"[\(\（](?P<num>\d{1,3})[\)\）]$")
TOPIC_TRIM_PATTERN = re.compile(r"[\s\-_—–:：,，。\.]+$")
INVALID_FILENAME_CHARS = re.compile(r"[\\/:*?\"<>|]")
CANONICAL_PATTERN = re.compile(
    r"^(?P<topic>.+?)__(?P<date>20\d{2}-\d{2}-\d{2})__v(?P<version>\d+)$"
)


@dataclass(slots=True)
class DocRecord:
    path: Path
    stem: str
    suffix: str
    size: int
    mtime: float
    file_hash: str
    topic_raw: str
    topic_sanitized: str
    published_at: str
    version_hint: int
    has_explicit_year: bool
    is_mmdd_tail: bool
    parse_ok: bool
    parse_reason: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preprocess stock research documents.")
    parser.add_argument(
        "--docs-dir",
        default="stock_docs",
        help="Target document directory (default: stock_docs).",
    )
    parser.add_argument(
        "--default-year",
        type=int,
        default=date.today().year,
        help="Default year for MMDD-only filenames (default: current year).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser("audit", help="Inspect filename and duplicate quality.")
    audit_parser.add_argument("--json-out", help="Write audit result to JSON file.")

    rename_parser = subparsers.add_parser("rename", help="Rename files to canonical format.")
    rename_parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply file renames. Without this flag, only preview.",
    )
    rename_parser.add_argument("--json-out", help="Write rename plan to JSON file.")

    dedup_parser = subparsers.add_parser("dedup", help="Detect or move exact-content duplicates.")
    dedup_parser.add_argument(
        "--apply",
        action="store_true",
        help="Move duplicate files to archive directory. Without this flag, only preview.",
    )
    dedup_parser.add_argument(
        "--archive-dir",
        default="_duplicates_archive",
        help="Archive directory under docs-dir when --apply is set.",
    )
    dedup_parser.add_argument("--json-out", help="Write dedup report to JSON file.")

    manifest_parser = subparsers.add_parser("manifest", help="Export metadata manifest.")
    manifest_parser.add_argument(
        "--out",
        default="data/cache/docs_manifest.csv",
        help="Manifest path, supports .csv or .json.",
    )
    return parser.parse_args()


def hash_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    sha1 = hashlib.sha1()
    with path.open("rb") as handle:
        while True:
            block = handle.read(chunk_size)
            if not block:
                break
            sha1.update(block)
    return sha1.hexdigest()


def _sanitize_topic(topic: str) -> str:
    candidate = topic.strip()
    candidate = INVALID_FILENAME_CHARS.sub("_", candidate)
    candidate = re.sub(r"\s+", "", candidate)
    candidate = TOPIC_TRIM_PATTERN.sub("", candidate)
    return candidate or "untitled"


def _extract_version(stem: str) -> tuple[str, int]:
    match = VERSION_SUFFIX_PATTERN.search(stem)
    if not match:
        return stem, 1
    version = int(match.group("num"))
    trimmed = stem[: match.start()].rstrip()
    return trimmed, max(1, version)


def _to_iso_date(year: int, month: int, day: int) -> str:
    return date(year, month, day).isoformat()


def _parse_topic_and_date(stem: str, default_year: int) -> tuple[str, str, bool, bool, str]:
    stem_no_version, _ = _extract_version(stem)
    for idx, pattern in enumerate(DATE_PATTERNS):
        match = pattern.search(stem_no_version)
        if not match:
            continue
        groups = match.groupdict()
        year_raw = groups.get("year")
        month = int(groups["month"])
        day = int(groups["day"])
        has_explicit_year = bool(year_raw)
        year = int(year_raw) if year_raw else int(default_year)
        try:
            iso_date = _to_iso_date(year, month, day)
        except ValueError:
            return stem_no_version, "", has_explicit_year, False, "invalid_date"

        topic = stem_no_version[: match.start()].rstrip()
        topic = TOPIC_TRIM_PATTERN.sub("", topic)
        if not topic:
            topic = stem_no_version
        return topic, iso_date, has_explicit_year, idx == 2, ""

    return stem_no_version, "", False, False, "no_date_pattern"


def build_records(docs_dir: Path, default_year: int) -> list[DocRecord]:
    records: list[DocRecord] = []
    for path in sorted(p for p in docs_dir.iterdir() if p.is_file()):
        stem = path.stem
        suffix = path.suffix.lower()
        size = path.stat().st_size
        mtime = path.stat().st_mtime
        content_hash = hash_file(path)

        stem_no_version, version_hint = _extract_version(stem)
        topic_raw, published_at, has_explicit_year, is_mmdd_tail, parse_reason = _parse_topic_and_date(
            stem_no_version, default_year
        )
        topic_sanitized = _sanitize_topic(topic_raw)
        parse_ok = bool(published_at)

        records.append(
            DocRecord(
                path=path,
                stem=stem,
                suffix=suffix,
                size=size,
                mtime=mtime,
                file_hash=content_hash,
                topic_raw=topic_raw,
                topic_sanitized=topic_sanitized,
                published_at=published_at,
                version_hint=version_hint,
                has_explicit_year=has_explicit_year,
                is_mmdd_tail=is_mmdd_tail,
                parse_ok=parse_ok,
                parse_reason=parse_reason,
            )
        )
    return records


def canonical_name(topic: str, published_at: str, version: int, suffix: str) -> str:
    return f"{topic}__{published_at}__v{version}{suffix}"


def is_canonical_stem(stem: str) -> bool:
    return CANONICAL_PATTERN.fullmatch(stem) is not None


def build_rename_plan(records: list[DocRecord]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[DocRecord]] = {}
    for record in records:
        if not record.parse_ok:
            continue
        grouped.setdefault((record.topic_sanitized, record.published_at), []).append(record)

    actions: list[dict[str, Any]] = []
    reserved_targets: set[str] = set()
    for key, group in grouped.items():
        sorted_group = sorted(
            group,
            key=lambda item: (item.version_hint, item.mtime, item.path.name.lower()),
        )
        topic, published_at = key
        for index, record in enumerate(sorted_group, start=1):
            target_name = canonical_name(topic, published_at, index, record.suffix)
            target_path = record.path.with_name(target_name)
            needs_rename = record.path.name != target_name
            conflict = target_name in reserved_targets
            reserved_targets.add(target_name)
            actions.append(
                {
                    "source": str(record.path),
                    "target": str(target_path),
                    "source_name": record.path.name,
                    "target_name": target_name,
                    "needs_rename": needs_rename,
                    "conflict": conflict,
                    "topic": topic,
                    "published_at": published_at,
                    "version": index,
                    "parse_ok": True,
                }
            )

    for record in records:
        if record.parse_ok:
            continue
        actions.append(
            {
                "source": str(record.path),
                "target": "",
                "source_name": record.path.name,
                "target_name": "",
                "needs_rename": False,
                "conflict": False,
                "topic": record.topic_sanitized,
                "published_at": "",
                "version": 0,
                "parse_ok": False,
                "reason": record.parse_reason,
            }
        )
    return actions


def apply_rename_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    renames = [action for action in actions if action.get("needs_rename")]
    temp_moves: list[tuple[Path, Path]] = []
    final_moves: list[tuple[Path, Path]] = []

    for action in renames:
        source = Path(str(action["source"]))
        target = Path(str(action["target"]))
        if source == target:
            continue
        temp = source.with_name(f".__tmp_preprocess__{source.name}")
        idx = 1
        while temp.exists():
            temp = source.with_name(f".__tmp_preprocess__{idx}__{source.name}")
            idx += 1
        source.rename(temp)
        temp_moves.append((temp, source))
        final_moves.append((temp, target))

    applied: list[dict[str, Any]] = []
    try:
        for temp, target in final_moves:
            target.parent.mkdir(parents=True, exist_ok=True)
            temp.rename(target)
            applied.append({"source": str(temp), "target": str(target)})
    except Exception:
        # Best-effort rollback when second stage fails.
        for current, original in reversed(temp_moves):
            if current.exists() and not original.exists():
                current.rename(original)
        raise
    return applied


def build_audit_report(records: list[DocRecord], default_year: int) -> dict[str, Any]:
    total = len(records)
    parsed = [item for item in records if item.parse_ok]
    unparsed = [item for item in records if not item.parse_ok]
    with_year = sum(1 for item in parsed if item.has_explicit_year)
    mmdd_tail = sum(1 for item in parsed if item.is_mmdd_tail)

    grouped: dict[tuple[str, str], list[DocRecord]] = {}
    for item in parsed:
        grouped.setdefault((item.topic_sanitized, item.published_at), []).append(item)

    multi_groups = [
        {
            "topic": key[0],
            "published_at": key[1],
            "count": len(items),
            "filenames": [obj.path.name for obj in sorted(items, key=lambda x: x.path.name)],
        }
        for key, items in grouped.items()
        if len(items) > 1
    ]
    multi_groups.sort(key=lambda row: row["count"], reverse=True)

    hash_groups: dict[str, list[DocRecord]] = {}
    for item in records:
        hash_groups.setdefault(item.file_hash, []).append(item)
    exact_dups = [
        {
            "hash": h,
            "count": len(items),
            "filenames": [obj.path.name for obj in sorted(items, key=lambda x: x.path.name)],
        }
        for h, items in hash_groups.items()
        if len(items) > 1
    ]
    exact_dups.sort(key=lambda row: row["count"], reverse=True)

    top_dates: dict[str, int] = {}
    for item in parsed:
        top_dates[item.published_at] = top_dates.get(item.published_at, 0) + 1
    top_dates_sorted = sorted(top_dates.items(), key=lambda row: (row[1], row[0]), reverse=True)

    return {
        "summary": {
            "total_files": total,
            "parsed_date_files": len(parsed),
            "unparsed_date_files": len(unparsed),
            "explicit_year_files": with_year,
            "mmdd_tail_files": mmdd_tail,
            "default_year_for_mmdd": default_year,
            "topic_date_multi_groups": len(multi_groups),
            "exact_hash_duplicate_groups": len(exact_dups),
        },
        "unparsed_files": [
            {
                "filename": item.path.name,
                "reason": item.parse_reason,
            }
            for item in unparsed
        ],
        "topic_date_multi_groups": multi_groups,
        "exact_hash_duplicate_groups": exact_dups,
        "top_dates": [{"date": d, "count": c} for d, c in top_dates_sorted[:20]],
    }


def build_dedup_report(records: list[DocRecord]) -> dict[str, Any]:
    grouped: dict[tuple[str, str], list[DocRecord]] = {}
    for item in records:
        if item.parse_ok:
            grouped.setdefault((item.topic_sanitized, item.published_at), []).append(item)

    duplicate_actions: list[dict[str, Any]] = []
    for key, items in grouped.items():
        hash_groups: dict[str, list[DocRecord]] = {}
        for item in items:
            hash_groups.setdefault(item.file_hash, []).append(item)

        for file_hash, hashed_items in hash_groups.items():
            if len(hashed_items) <= 1:
                continue
            ordered = sorted(hashed_items, key=lambda x: (x.mtime, x.path.name), reverse=True)
            primary = ordered[0]
            for duplicate in ordered[1:]:
                duplicate_actions.append(
                    {
                        "topic": key[0],
                        "published_at": key[1],
                        "hash": file_hash,
                        "primary": str(primary.path),
                        "duplicate": str(duplicate.path),
                    }
                )
    return {
        "duplicate_file_count": len(duplicate_actions),
        "duplicates": duplicate_actions,
    }


def apply_dedup_report(report: dict[str, Any], docs_dir: Path, archive_dir_name: str) -> list[dict[str, Any]]:
    archive_dir = docs_dir / archive_dir_name
    archive_dir.mkdir(parents=True, exist_ok=True)
    moved: list[dict[str, Any]] = []
    for row in report.get("duplicates", []):
        source = Path(str(row["duplicate"]))
        if not source.exists():
            continue
        target = archive_dir / source.name
        index = 1
        while target.exists():
            target = archive_dir / f"{source.stem}__dup{index}{source.suffix}"
            index += 1
        shutil.move(str(source), str(target))
        moved.append({"source": str(source), "target": str(target), "primary": row["primary"]})
    return moved


def build_manifest_rows(records: list[DocRecord], rename_plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    plan_by_source = {str(row["source"]): row for row in rename_plan}
    rows: list[dict[str, Any]] = []
    for item in records:
        source = str(item.path)
        plan = plan_by_source.get(source, {})
        rows.append(
            {
                "filename": item.path.name,
                "path": source,
                "topic_raw": item.topic_raw,
                "topic_sanitized": item.topic_sanitized,
                "published_at": item.published_at,
                "parse_ok": item.parse_ok,
                "parse_reason": item.parse_reason,
                "version_hint": item.version_hint,
                "size_bytes": item.size,
                "mtime_iso": datetime.fromtimestamp(item.mtime).isoformat(),
                "sha1": item.file_hash,
                "canonical_target_name": plan.get("target_name", ""),
                "needs_rename": bool(plan.get("needs_rename", False)),
            }
        )
    return rows


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def write_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".json":
        write_json(path, rows)
        return

    if not rows:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow([])
        return

    columns = list(rows[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def print_audit(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print("Audit summary:")
    print(
        "  total={total_files}, parsed={parsed_date_files}, unparsed={unparsed_date_files}".format(
            **summary
        )
    )
    print(
        "  explicit_year={explicit_year_files}, mmdd_tail={mmdd_tail_files}, default_year={default_year_for_mmdd}".format(
            **summary
        )
    )
    print(
        "  topic_date_multi_groups={topic_date_multi_groups}, exact_hash_duplicate_groups={exact_hash_duplicate_groups}".format(
            **summary
        )
    )
    if report["unparsed_files"]:
        print("Unparsed files:")
        for item in report["unparsed_files"]:
            print(f"  - {item['filename']} ({item['reason']})")


def print_rename_preview(actions: list[dict[str, Any]]) -> None:
    renames = [row for row in actions if row.get("needs_rename")]
    skipped = [row for row in actions if not row.get("parse_ok")]
    print(f"Rename plan: {len(renames)} file(s) need rename, {len(skipped)} file(s) unparsed.")
    for row in renames[:30]:
        print(f"  - {row['source_name']} -> {row['target_name']}")
    if len(renames) > 30:
        print(f"  ... and {len(renames) - 30} more")


def print_dedup_preview(report: dict[str, Any]) -> None:
    duplicates = report.get("duplicates", [])
    print(f"Dedup report: {len(duplicates)} duplicate file(s) detected.")
    for row in duplicates[:30]:
        print(
            f"  - duplicate={Path(row['duplicate']).name} | primary={Path(row['primary']).name} "
            f"| topic={row['topic']} | date={row['published_at']}"
        )
    if len(duplicates) > 30:
        print(f"  ... and {len(duplicates) - 30} more")


def main() -> int:
    args = parse_args()
    docs_dir = Path(args.docs_dir).resolve()
    if not docs_dir.exists():
        raise SystemExit(f"docs directory not found: {docs_dir}")
    if not docs_dir.is_dir():
        raise SystemExit(f"docs path is not a directory: {docs_dir}")

    records = build_records(docs_dir, default_year=args.default_year)
    rename_plan = build_rename_plan(records)

    if args.command == "audit":
        report = build_audit_report(records, default_year=args.default_year)
        print_audit(report)
        if args.json_out:
            write_json(Path(args.json_out), report)
            print(f"Audit JSON written: {args.json_out}")
        return 0

    if args.command == "rename":
        print_rename_preview(rename_plan)
        if args.json_out:
            write_json(Path(args.json_out), rename_plan)
            print(f"Rename plan JSON written: {args.json_out}")
        if not args.apply:
            print("Dry run only. Add --apply to perform file renames.")
            return 0
        applied = apply_rename_actions(rename_plan)
        print(f"Applied renames: {len(applied)}")
        return 0

    if args.command == "dedup":
        report = build_dedup_report(records)
        print_dedup_preview(report)
        if args.json_out:
            write_json(Path(args.json_out), report)
            print(f"Dedup JSON written: {args.json_out}")
        if not args.apply:
            print("Dry run only. Add --apply to move duplicate files to archive.")
            return 0
        moved = apply_dedup_report(report, docs_dir, args.archive_dir)
        print(f"Moved duplicates: {len(moved)}")
        return 0

    if args.command == "manifest":
        out_path = Path(args.out)
        rows = build_manifest_rows(records, rename_plan)
        write_manifest(out_path, rows)
        print(f"Manifest written: {out_path.resolve()} (rows={len(rows)})")
        return 0

    raise SystemExit(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
