#!/usr/bin/env python3
"""
Split data/eval.json into data/dev.jsonl and data/test.jsonl.

Sheet-disjoint: every OWASP cheat sheet file goes entirely to one split, so
tuning on dev can never leak content from a sheet that test also draws on.
Questions that cite two sheets (multi_sheet, and some comparative, via
extra_sources) force those sheets into the same split — so the split is
computed over connected components of sheets (two sheets are linked
whenever they co-occur in one question's source_file + extra_sources), not
over individual questions. A question's split then simply follows its
sheets' split; since every sheet in a question is in the same component by
construction, this is never ambiguous (verified with assertions below).

unanswerable questions have no sheet, so they're split separately: ~25% to
dev, stratified by category using largest-remainder (Hamilton) apportionment
— plain round() sends every category of size 2 to 0% or 50% dev depending
on luck, which badly skews a dataset where most unanswerable categories
only have 1-4 items; largest-remainder apportions the rounding error fairly
across categories instead.

The split is chosen by randomized search (seeded, so reproducible): many
candidate dev/test partitions of the sheet components are generated, each
scored on (a) how close total dev size is to the target, (b) how close each
question type's dev share is to 25%, and (c) whether every category (that's
big enough to possibly do so) appears in both splits; the lowest-cost
candidate found across all trials is used.

Usage: python3 scripts/split_eval.py [--seed 42] [--dev-fraction 0.25] [--trials 20000]
"""
import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

TYPES_EXCL_UNANSWERABLE = ["factual", "procedural", "comparative", "multi_sheet", "code_table"]


def load_rows():
    return json.loads((DATA / "eval.json").read_text(encoding="utf-8"))


def row_sheets(row):
    sheets = [row["source_file"]]
    for extra in row.get("extra_sources") or []:
        sheets.append(extra["source_file"])
    return sheets


def build_sheet_components(answerable_rows):
    """Union-find over sheet names: two sheets are merged whenever a single
    question cites both (primary source_file + any extra_sources)."""
    parent = {}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for row in answerable_rows:
        sheets = row_sheets(row)
        for s in sheets:
            parent.setdefault(s, s)
        for s in sheets[1:]:
            union(sheets[0], s)

    comp_rows = defaultdict(list)
    comp_sheets = defaultdict(set)
    for row in answerable_rows:
        root = find(row_sheets(row)[0])
        comp_rows[root].append(row)
        comp_sheets[root].update(row_sheets(row))

    return comp_rows, comp_sheets


def apportion_largest_remainder(counts_by_key, total_target, rng):
    """Hamilton/largest-remainder apportionment: give total_target seats to
    the groups in counts_by_key, proportional to group size, without a
    group's fractional share just getting floored to zero (which is what
    plain round() does to every group whose exact share lands below 0.5)."""
    grand_total = sum(counts_by_key.values())
    exact = {k: n * total_target / grand_total for k, n in counts_by_key.items()}
    base = {k: int(v) for k, v in exact.items()}
    remainder_seats = total_target - sum(base.values())
    order = sorted(counts_by_key.keys(), key=lambda k: (-(exact[k] - base[k]), rng.random()))
    for k in order[:remainder_seats]:
        base[k] += 1
    return base


def split_unanswerable(unanswerable_rows, dev_fraction, rng):
    by_category = defaultdict(list)
    for row in unanswerable_rows:
        by_category[row["category"]].append(row)

    target_total = round(len(unanswerable_rows) * dev_fraction)
    sizes = {c: len(rows) for c, rows in by_category.items()}
    dev_quota = apportion_largest_remainder(sizes, target_total, rng)

    dev_ids = set()
    for cat, rows in by_category.items():
        rows_sorted = sorted(rows, key=lambda r: r["id"])
        chosen = rng.sample(rows_sorted, dev_quota[cat])
        dev_ids.update(r["id"] for r in chosen)
    return dev_ids


def score_candidate(dev_rows, target_dev_answerable, type_totals, category_totals):
    size_cost = abs(len(dev_rows) - target_dev_answerable)

    type_dev = Counter(r["type"] for r in dev_rows)
    type_cost = sum(
        abs(type_dev.get(t, 0) / total - 0.25) for t, total in type_totals.items() if total
    )

    cat_dev = Counter(r["category"] for r in dev_rows)
    missing_cost = 0
    for cat, total in category_totals.items():
        if total < 2:
            continue  # can't possibly appear in both splits regardless of assignment
        dev_c = cat_dev.get(cat, 0)
        if dev_c == 0 or dev_c == total:
            missing_cost += 1

    return size_cost * 2 + type_cost * 12 + missing_cost * 3


def search_best_split(comp_rows, target_dev_answerable, type_totals, category_totals, seed, trials):
    components = list(comp_rows.items())
    master_rng = random.Random(seed)
    overshoot_tolerance = 3

    best_roots, best_cost = None, None
    for _ in range(trials):
        rng = random.Random(master_rng.randrange(2**63))
        order = components[:]
        rng.shuffle(order)

        dev_roots, dev_count = [], 0
        for root, rows in order:
            if dev_count >= target_dev_answerable:
                break
            if dev_count + len(rows) <= target_dev_answerable + overshoot_tolerance:
                dev_roots.append(root)
                dev_count += len(rows)

        dev_rows = [r for root in dev_roots for r in comp_rows[root]]
        cost = score_candidate(dev_rows, target_dev_answerable, type_totals, category_totals)
        if best_cost is None or cost < best_cost:
            best_cost, best_roots = cost, dev_roots

    return set(best_roots), best_cost


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dev-fraction", type=float, default=0.25)
    parser.add_argument("--trials", type=int, default=20000)
    args = parser.parse_args()

    rows = load_rows()
    answerable_rows = [r for r in rows if r["answerable"]]
    unanswerable_rows = [r for r in rows if not r["answerable"]]

    target_dev_total = round(len(rows) * args.dev_fraction)

    uns_rng = random.Random(args.seed + 1_000_000)
    dev_unanswerable_ids = split_unanswerable(unanswerable_rows, args.dev_fraction, uns_rng)

    target_dev_answerable = target_dev_total - len(dev_unanswerable_ids)

    comp_rows, comp_sheets = build_sheet_components(answerable_rows)
    type_totals = Counter(r["type"] for r in answerable_rows)
    category_totals = Counter(r["category"] for r in answerable_rows)

    dev_roots, best_cost = search_best_split(
        comp_rows, target_dev_answerable, type_totals, category_totals, args.seed, args.trials
    )

    dev_sheets, test_sheets = set(), set()
    for root, sheets in comp_sheets.items():
        (dev_sheets if root in dev_roots else test_sheets).update(sheets)

    assert dev_sheets.isdisjoint(test_sheets), "a sheet ended up assigned to both splits"

    sheet_split = {s: "dev" for s in dev_sheets}
    sheet_split.update({s: "test" for s in test_sheets})

    dev_ids = set(dev_unanswerable_ids)
    for root in dev_roots:
        dev_ids.update(r["id"] for r in comp_rows[root])

    # Verify the stated rule directly: a question's sheets must all agree on
    # one split (never mixed), and the question follows that split.
    for row in answerable_rows:
        sheets = row_sheets(row)
        splits_touched = {sheet_split[s] for s in sheets}
        assert len(splits_touched) == 1, f"{row['id']}: its sheets are split across dev/test: {sheets}"
        assert ("dev" in splits_touched) == (row["id"] in dev_ids), f"{row['id']}: split assignment inconsistent"

    final_rows = [{**row, "split": ("dev" if row["id"] in dev_ids else "test")} for row in rows]
    final_rows.sort(key=lambda r: r["id"])

    dev_out = [r for r in final_rows if r["split"] == "dev"]
    test_out = [r for r in final_rows if r["split"] == "test"]

    with (DATA / "dev.jsonl").open("w", encoding="utf-8") as f:
        for r in dev_out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with (DATA / "test.jsonl").open("w", encoding="utf-8") as f:
        for r in test_out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"dev: {len(dev_out)} rows -> data/dev.jsonl")
    print(f"test: {len(test_out)} rows -> data/test.jsonl")
    print(f"distinct dev sheets: {len(dev_sheets)}, distinct test sheets: {len(test_sheets)}")
    print(f"best candidate search cost: {best_cost}")

    write_split_report(dev_out, test_out, rows, dev_sheets, test_sheets, args)


def write_split_report(dev_out, test_out, all_rows, dev_sheets, test_sheets, args):
    def counts_table(rows_a, rows_b, key, keys_order):
        lines = [f"| {key} | dev | test |", "|---|---|---|"]
        for k in keys_order:
            a = sum(1 for r in rows_a if r[key] == k)
            b = sum(1 for r in rows_b if r[key] == k)
            lines.append(f"| {k} | {a} | {b} |")
        lines.append(f"| **total** | **{len(rows_a)}** | **{len(rows_b)}** |")
        return "\n".join(lines)

    type_order = TYPES_EXCL_UNANSWERABLE + ["unanswerable"]
    category_order = sorted({r["category"] for r in all_rows})

    md = []
    md.append("# Dev / test split\n")
    md.append(f"Generated by `scripts/split_eval.py --seed {args.seed}` from `data/eval.json` "
               f"({len(all_rows)} reviewed questions). Regenerate with:\n")
    md.append("```bash")
    md.append(f"python3 scripts/split_eval.py --seed {args.seed}")
    md.append("```\n")

    md.append("## Totals\n")
    md.append(f"- dev: {len(dev_out)} ({len(dev_out) / len(all_rows):.1%})")
    md.append(f"- test: {len(test_out)} ({len(test_out) / len(all_rows):.1%})")
    md.append(f"- distinct sheets in dev: {len(dev_sheets)}")
    md.append(f"- distinct sheets in test: {len(test_sheets)}")
    md.append("- sheet overlap between dev and test: 0 (enforced by construction + assertion)\n")

    md.append("## Counts per type\n")
    md.append(counts_table(dev_out, test_out, "type", type_order))
    md.append("")

    md.append("## Counts per category\n")
    md.append(counts_table(dev_out, test_out, "category", category_order))
    md.append("")

    md.append(
        "**dev is for tuning; test is only for final and Week 8 before/after numbers.**\n"
    )

    (DATA / "SPLIT.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("Wrote data/SPLIT.md")


if __name__ == "__main__":
    main()
