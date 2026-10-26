#!/usr/bin/env python3
"""
Merge the four human-reviewed data/review/reviewer_N.json files into
data/eval.jsonl (JSON Lines, one compact object per line, sorted by id).

data/eval_draft.json (the raw LLM draft) is never read for anything other
than the before/after comparison in data/REVIEW_STATS.md — it is not
modified.

Fails loudly (prints every problem, writes nothing, exits non-zero) if:
  - the same id appears more than once across the four reviewer files
  - any entry is missing a required field
  - any entry still has verified: false (i.e. wasn't actually reviewed)
Also flagged as a loud failure, since manual JSON editing invites it: an id
that isn't in the draft, or a 'reviewer' field that doesn't match the file
it was found in.

Usage: python3 scripts/merge_reviews.py
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REVIEW_DIR = DATA / "review"
DRAFT_PATH = DATA / "eval_draft.json"
OUTPUT_PATH = DATA / "eval.jsonl"
STATS_PATH = DATA / "REVIEW_STATS.md"

REVIEWERS = ["reviewer_1", "reviewer_2", "reviewer_3", "reviewer_4"]

REQUIRED_FIELDS = [
    "id",
    "type",
    "category",
    "answerable",
    "question",
    "answer",
    "source_file",
    "source_section",
    "source_passage",
    "extra_sources",
    "origin",
    "verified",
    "reviewer",
]

# Fields whose expected change (false -> true on every reviewed row) doesn't
# by itself count as a content edit.
DIFF_IGNORE_FIELDS = {"verified"}


def load_json_array(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    draft_rows = load_json_array(DRAFT_PATH)
    draft_by_id = {r["id"]: r for r in draft_rows}

    errors = []
    seen_ids = {}
    final_rows = []

    for reviewer in REVIEWERS:
        path = REVIEW_DIR / f"{reviewer}.json"
        if not path.is_file():
            errors.append(f"{reviewer}: file not found at {path}")
            continue
        rows = load_json_array(path)
        for row in rows:
            row_id = row.get("id")
            if not row_id:
                errors.append(f"{reviewer}: an entry has no 'id' field at all")
                continue

            if row_id in seen_ids:
                errors.append(
                    f"{row_id}: duplicated (appears in both {seen_ids[row_id]} and {reviewer})"
                )
            else:
                seen_ids[row_id] = reviewer

            missing = [f for f in REQUIRED_FIELDS if f not in row]
            if missing:
                errors.append(f"{row_id}: missing required field(s): {', '.join(missing)}")

            if row.get("type") == "unanswerable" and not row.get("absence_check"):
                errors.append(f"{row_id}: type is unanswerable but absence_check is missing/empty")

            if row.get("verified") is not True:
                errors.append(
                    f"{row_id}: verified is {row.get('verified')!r}, not true — not actually reviewed"
                )

            if row_id not in draft_by_id:
                errors.append(f"{row_id}: not found in data/eval_draft.json (unexpected id)")

            if row.get("reviewer") != reviewer:
                errors.append(
                    f"{row_id}: reviewer field is {row.get('reviewer')!r} but the row was found in {reviewer}.json"
                )

            final_rows.append(row)

    if errors:
        print(f"=== MERGE FAILED: {len(errors)} problem(s) ===")
        for e in sorted(errors):
            print(f"  FAIL: {e}")
        print(f"\n{OUTPUT_PATH} was NOT written. Fix the issues above and re-run.")
        raise SystemExit(1)

    final_rows.sort(key=lambda r: r["id"])

    with OUTPUT_PATH.open("w", encoding="utf-8") as out:
        for row in final_rows:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Wrote {len(final_rows)} rows to {OUTPUT_PATH}, sorted by id.")

    # ---------------------------------------------------------------- stats
    final_ids = {r["id"] for r in final_rows}
    draft_ids = set(draft_by_id.keys())
    deleted_ids = sorted(draft_ids - final_ids)

    deleted_by_reviewer = defaultdict(list)
    for did in deleted_ids:
        deleted_by_reviewer[draft_by_id[did].get("reviewer", "unknown")].append(did)

    edited_ids, unchanged_ids = [], []
    notes_without_diff, diff_without_notes = [], []
    for row in final_rows:
        draft_row = draft_by_id[row["id"]]
        draft_cmp = {k: v for k, v in draft_row.items() if k not in DIFF_IGNORE_FIELDS}
        final_cmp = {k: v for k, v in row.items() if k not in DIFF_IGNORE_FIELDS}
        changed = draft_cmp != final_cmp
        has_notes = bool(row.get("review_notes"))
        if changed:
            edited_ids.append(row["id"])
        else:
            unchanged_ids.append(row["id"])
        if has_notes and not changed:
            notes_without_diff.append(row["id"])
        if changed and not has_notes:
            diff_without_notes.append(row["id"])

    # review_notes has no formal taxonomy (free text per REVIEW_GUIDE.md) —
    # use each note's leading word (consistently a past-tense action verb:
    # "Expanded", "Removed", "Corrected", ...) as an ad hoc label.
    note_label_counts = Counter()
    for row in final_rows:
        note = row.get("review_notes")
        if note:
            label = note.strip().split()[0].rstrip(".,:;")
            note_label_counts[label] += 1

    type_counts = Counter(r["type"] for r in final_rows)
    category_counts = Counter(r["category"] for r in final_rows)
    answerable_count = sum(1 for r in final_rows if r.get("answerable") is True)

    draft_type_counts = Counter(r["type"] for r in draft_rows)
    draft_category_counts = Counter(r["category"] for r in draft_rows)

    lines = []
    lines.append("# Review stats: draft vs. final\n")
    lines.append(
        f"`data/eval_draft.json` (120 LLM-drafted questions, pre-review) "
        f"vs. `data/eval.jsonl` ({len(final_rows)} human-reviewed questions), "
        f"after merging `data/review/reviewer_1..4.json`.\n"
    )

    lines.append("## Headline numbers\n")
    lines.append(f"- Draft total: {len(draft_rows)}")
    lines.append(f"- Final total (kept): {len(final_rows)}")
    lines.append(f"- Deleted by reviewers: {len(deleted_ids)}")
    lines.append(f"- Edited (any field besides `verified` changed from the draft): {len(edited_ids)}")
    lines.append(f"- Kept unchanged (reviewer approved as-is): {len(unchanged_ids)}")
    lines.append(f"- Answerable questions in final set: {answerable_count}")
    lines.append(f"- Unanswerable questions in final set: {len(final_rows) - answerable_count}\n")

    lines.append("## Deleted questions\n")
    if deleted_ids:
        lines.append(f"{len(deleted_ids)} id(s) removed, by reviewer:\n")
        for reviewer in REVIEWERS:
            ids = deleted_by_reviewer.get(reviewer, [])
            if ids:
                lines.append(f"- **{reviewer}**: {', '.join(ids)}")
    else:
        lines.append("None.")
    lines.append("")

    lines.append("## Edited questions\n")
    lines.append(f"{len(edited_ids)} id(s) had at least one field changed from the draft:\n")
    lines.append(", ".join(edited_ids) if edited_ids else "None.")
    lines.append("")
    if notes_without_diff:
        lines.append(
            f"Note: {len(notes_without_diff)} row(s) carry a `review_notes` but diffed identical to the draft "
            f"otherwise (notes likely describe something not captured by a field-level diff, e.g. confirming "
            f"an absence_check by re-running it): {', '.join(notes_without_diff)}"
        )
    if diff_without_notes:
        lines.append(
            f"Note: {len(diff_without_notes)} row(s) changed from the draft but have no `review_notes` "
            f"explaining why: {', '.join(diff_without_notes)}"
        )
    lines.append("")

    lines.append("## Counts per `review_notes` label\n")
    lines.append(
        "`review_notes` is free text (no formal label field per `data/REVIEW_GUIDE.md`); "
        "grouped here by each note's leading word, which reviewers consistently used as an "
        "action verb (Expanded, Removed, Corrected, ...).\n"
    )
    lines.append("| label | count |")
    lines.append("|---|---|")
    for label, count in note_label_counts.most_common():
        lines.append(f"| {label} | {count} |")
    lines.append(f"| **total with review_notes** | **{sum(note_label_counts.values())}** |\n")

    lines.append("## Final counts per type (draft -> final)\n")
    lines.append("| type | draft | final |")
    lines.append("|---|---|---|")
    for t in sorted(set(draft_type_counts) | set(type_counts)):
        lines.append(f"| {t} | {draft_type_counts.get(t, 0)} | {type_counts.get(t, 0)} |")
    lines.append(f"| **total** | **{sum(draft_type_counts.values())}** | **{sum(type_counts.values())}** |\n")

    lines.append("## Final counts per category (draft -> final)\n")
    lines.append("| category | draft | final |")
    lines.append("|---|---|---|")
    for c in sorted(set(draft_category_counts) | set(category_counts)):
        lines.append(f"| {c} | {draft_category_counts.get(c, 0)} | {category_counts.get(c, 0)} |")
    lines.append(
        f"| **total** | **{sum(draft_category_counts.values())}** | **{sum(category_counts.values())}** |\n"
    )

    STATS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {STATS_PATH}")


if __name__ == "__main__":
    main()
