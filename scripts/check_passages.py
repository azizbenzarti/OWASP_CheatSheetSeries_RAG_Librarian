#!/usr/bin/env python3
"""
Validate data/eval_draft.json against data/SCHEMA.md's invariants:

1. Every non-null source_passage (and extra_sources[].source_passage) appears
   verbatim, after whitespace normalization, in its claimed source_file.
2. source_file must exist under corpus/CheatSheetSeries/cheatsheets/.
3. unanswerable rows: source_file/source_section/source_passage all null,
   answerable is false, absence_check is non-empty.
4. non-unanswerable rows: answerable is true, source_file/source_section/
   source_passage all non-null.

Also prints counts per type, category, and sheet (source_file).

Accepts either format: a pretty-printed JSON array (the canonical format,
*.json) or legacy one-JSON-object-per-line JSONL (*.jsonl).

Usage: python3 scripts/check_passages.py [path/to/eval.json]
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHEATSHEETS_DIR = ROOT / "corpus" / "CheatSheetSeries" / "cheatsheets"
DEFAULT_DATA = ROOT / "data" / "eval_draft.json"

VALID_TYPES = {
    "factual",
    "procedural",
    "comparative",
    "multi_sheet",
    "code_table",
    "unanswerable",
}
VALID_CATEGORIES = {
    "attacks",
    "identity",
    "devsecops",
    "frameworks",
    "api_architecture",
    "ai_security",
    "other",
}


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


_file_cache: dict[str, str] = {}


def normalized_file_text(filename: str) -> str | None:
    if filename not in _file_cache:
        path = CHEATSHEETS_DIR / filename
        if not path.is_file():
            _file_cache[filename] = None
        else:
            _file_cache[filename] = normalize(path.read_text(encoding="utf-8"))
    return _file_cache[filename]


def check_source(row_id, label, source_file, passage, errors):
    if not source_file:
        errors.append(f"{row_id}: {label} source_file is empty/null")
        return
    text = normalized_file_text(source_file)
    if text is None:
        errors.append(f"{row_id}: {label} source_file '{source_file}' not found under cheatsheets/")
        return
    norm_passage = normalize(passage or "")
    if not norm_passage:
        errors.append(f"{row_id}: {label} source_passage is empty")
        return
    if norm_passage not in text:
        errors.append(
            f"{row_id}: {label} source_passage not found verbatim in '{source_file}'"
        )


def main():
    data_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DATA
    if not data_path.is_file():
        print(f"ERROR: {data_path} not found", file=sys.stderr)
        sys.exit(1)

    raw_text = data_path.read_text(encoding="utf-8")
    rows: list[tuple[int, dict]] = []
    stripped = raw_text.lstrip()
    if stripped.startswith("["):
        # Canonical format: a pretty-printed JSON array.
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as e:
            print(f"ERROR: {data_path} is not valid JSON: {e}", file=sys.stderr)
            sys.exit(1)
        rows = [(i + 1, row) for i, row in enumerate(parsed)]
    else:
        # Legacy format: one JSON object per line.
        for lineno, line in enumerate(raw_text.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append((lineno, json.loads(line)))
            except json.JSONDecodeError as e:
                print(f"ERROR: line {lineno} is not valid JSON: {e}", file=sys.stderr)
                sys.exit(1)

    errors = []
    seen_ids = set()
    type_counts = Counter()
    category_counts = Counter()
    sheet_counts = Counter()

    for lineno, row in rows:
        row_id = row.get("id", f"<line {lineno}>")

        if row_id in seen_ids:
            errors.append(f"{row_id}: duplicate id")
        seen_ids.add(row_id)

        rtype = row.get("type")
        if rtype not in VALID_TYPES:
            errors.append(f"{row_id}: invalid type '{rtype}'")
        type_counts[rtype] += 1

        category = row.get("category")
        if category not in VALID_CATEGORIES:
            errors.append(f"{row_id}: invalid category '{category}'")
        category_counts[category] += 1

        answerable = row.get("answerable")
        is_unanswerable = rtype == "unanswerable"

        if is_unanswerable:
            if answerable is not False:
                errors.append(f"{row_id}: unanswerable row must have answerable=false")
            for field in ("source_file", "source_section", "source_passage"):
                if row.get(field) is not None:
                    errors.append(f"{row_id}: unanswerable row must have {field}=null")
            if not row.get("absence_check"):
                errors.append(f"{row_id}: unanswerable row missing non-empty absence_check")
        else:
            if answerable is not True:
                errors.append(f"{row_id}: non-unanswerable row must have answerable=true")
            for field in ("source_file", "source_section", "source_passage"):
                if not row.get(field):
                    errors.append(f"{row_id}: {field} must be non-null/non-empty")
            if row.get("source_file"):
                check_source(row_id, "primary", row["source_file"], row.get("source_passage"), errors)
                sheet_counts[row["source_file"]] += 1

        for i, extra in enumerate(row.get("extra_sources") or []):
            sf = extra.get("source_file")
            check_source(row_id, f"extra_sources[{i}]", sf, extra.get("source_passage"), errors)
            if sf:
                sheet_counts[sf] += 1

    print(f"Checked {len(rows)} rows from {data_path}\n")

    print("=== Counts per type ===")
    for t in sorted(VALID_TYPES):
        print(f"  {t:15s} {type_counts.get(t, 0)}")
    print(f"  {'TOTAL':15s} {sum(type_counts.values())}\n")

    print("=== Counts per category ===")
    for c in sorted(VALID_CATEGORIES):
        print(f"  {c:18s} {category_counts.get(c, 0)}")
    print(f"  {'TOTAL':18s} {sum(category_counts.values())}\n")

    print(f"=== Counts per sheet (source_file, primary + extra_sources) ===")
    print(f"  distinct sheets referenced: {len(sheet_counts)}")
    for sheet, count in sorted(sheet_counts.items()):
        print(f"  {sheet:60s} {count}")
    print()

    if errors:
        print(f"=== {len(errors)} FAILURE(S) ===")
        for e in errors:
            print(f"  FAIL: {e}")
        sys.exit(1)
    else:
        print("=== All checks passed ===")
        sys.exit(0)


if __name__ == "__main__":
    main()
