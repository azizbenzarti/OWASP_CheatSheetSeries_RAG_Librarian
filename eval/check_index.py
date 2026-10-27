"""
Sanity-check a built config before trusting it. Structural checks (no empty
sheets, balanced code fences, well-shaped tables, no chunk over the model's
token limit, chunk_id determinism, Qdrant/chunks.jsonl/manifest agreement)
plus two numbers that matter for interpreting later results:

- text coverage: did chunking lose any parsed content?
- dev passage coverage: our recall ceiling, independent of how good the
  retriever's ranking is — if a dev passage isn't fully contained in any
  single chunk, no retrieval method could ever get a perfect hit on it.

Then a few smoke queries (against both vector and BM25) for a human to
eyeball. Uses data/dev.jsonl ONLY; never opens data/test.jsonl.

Usage: python3 eval/check_index.py data/index/<config>/ [--query "..."]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import bm25s

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from indexing.build import load_chunks, tokenize_for_bm25  # noqa: E402
from indexing.chunk import chunk_document, make_token_counter  # noqa: E402
from indexing.embed import DEFAULT_MAX_INPUT_TOKENS, EmbeddingConfig, embed_texts  # noqa: E402
from indexing.load import is_table_separator, list_cheatsheet_files, load_all_documents  # noqa: E402
from indexing.vectordb import get_client, vector_search  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEV_PATH = ROOT / "data" / "dev.jsonl"

DEFAULT_QUERIES = [
    "how should I store passwords",
    "preventing XSS in a REST API",
    "what's a safe way to validate JWT tokens",
]

_FENCE_LINE_RE = re.compile(r"^(```|~~~)")
TEXT_COVERAGE_THRESHOLD = 0.98  # sanity bar, not "no content lost at all"


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


class Report:
    def __init__(self) -> None:
        self.results: list[tuple[str, bool, str]] = []

    def check(self, name: str, passed: bool, detail: str = "") -> bool:
        self.results.append((name, passed, detail))
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {name}" + (f" -- {detail}" if detail else ""))
        return passed

    def all_passed(self) -> bool:
        return all(passed for _, passed, _ in self.results)


# --------------------------------------------------------------------- #
# checks
# --------------------------------------------------------------------- #


def check_no_empty_sheets(chunks: list[dict], report: Report) -> None:
    all_sheets = {p.name for p in list_cheatsheet_files()}
    chunk_sheets = {c["source_file"] for c in chunks}
    missing = sorted(all_sheets - chunk_sheets)
    report.check(
        "sheets with zero chunks (expect none)",
        len(missing) == 0,
        f"{len(missing)}: {missing[:10]}" if missing else "0",
    )


def _words(text: str) -> list[str]:
    return normalize(text).split(" ")


def check_text_coverage(docs, chunks: list[dict], report: Report) -> None:
    """Word-multiset coverage of each document's parsed body text (every
    block the parser found, across the whole heading tree) by that
    document's chunks. Word-level + multiset (not substring) on purpose:
    robust to the chunker re-joining blocks with different separators or
    merging/reordering small sections, which isn't content loss."""
    chunks_by_file: dict[str, list[str]] = {}
    for c in chunks:
        chunks_by_file.setdefault(c["source_file"], []).append(c["text"])

    total_words, total_covered = 0, 0
    worst: list[tuple[str, float]] = []
    for doc in docs:
        original_words: Counter[str] = Counter()

        def collect(section) -> None:
            for b in section.own_blocks:
                original_words.update(_words(b.text))
            for child in section.children:
                collect(child)

        collect(doc.root)

        chunk_words: Counter[str] = Counter()
        for t in chunks_by_file.get(doc.source_file, []):
            chunk_words.update(_words(t))

        doc_total = sum(original_words.values())
        doc_covered = sum(min(n, chunk_words[w]) for w, n in original_words.items())
        total_words += doc_total
        total_covered += doc_covered
        if doc_total and doc_covered / doc_total < TEXT_COVERAGE_THRESHOLD:
            worst.append((doc.source_file, doc_covered / doc_total))

    coverage = (total_covered / total_words) if total_words else 1.0
    worst.sort(key=lambda x: x[1])
    report.check(
        f"text coverage >= {TEXT_COVERAGE_THRESHOLD:.0%} (parsed content preserved through chunking)",
        coverage >= TEXT_COVERAGE_THRESHOLD,
        f"{coverage:.2%} overall" + (f"; worst: {worst[:5]}" if worst else ""),
    )


def _is_block_fence_line(line: str) -> bool:
    """A real fence-open/close line, as the parser defines it (load.py) --
    not a single-line self-closing span like "```https://...```" used as
    inline code, which starts with the marker but isn't a block fence."""
    match = _FENCE_LINE_RE.match(line)
    if not match:
        return False
    fence = match.group(1)
    return fence not in line[len(fence):]


def check_fence_and_table_shape(chunks: list[dict], report: Report) -> None:
    odd_fence_chunks, bad_table_chunks = [], []
    for c in chunks:
        lines = c["text"].splitlines()
        fence_count = sum(1 for line in lines if _is_block_fence_line(line.strip()))
        if fence_count % 2 != 0:
            odd_fence_chunks.append(c["chunk_id"])

        if c["has_table"]:
            has_header_and_separator = any(
                "|" in lines[i] and is_table_separator(lines[i + 1]) for i in range(len(lines) - 1)
            )
            if not has_header_and_separator:
                bad_table_chunks.append(c["chunk_id"])

    report.check(
        "no chunks with an odd number of ``` / ~~~ fences",
        len(odd_fence_chunks) == 0,
        f"{len(odd_fence_chunks)}: {odd_fence_chunks[:5]}" if odd_fence_chunks else "0",
    )
    report.check(
        "every has_table chunk has a header row + separator row",
        len(bad_table_chunks) == 0,
        f"{len(bad_table_chunks)}: {bad_table_chunks[:5]}" if bad_table_chunks else "0",
    )


def check_token_limits(chunks: list[dict], count_tokens, report: Report) -> None:
    over_limit = [c["chunk_id"] for c in chunks if count_tokens(c["embed_text"]) > DEFAULT_MAX_INPUT_TOKENS]
    report.check(
        f"no chunk's embed_text exceeds the {DEFAULT_MAX_INPUT_TOKENS}-token model input limit (expect none)",
        len(over_limit) == 0,
        f"{len(over_limit)}: {over_limit[:5]}" if over_limit else "0",
    )


def check_dev_passage_coverage(chunks: list[dict], report: Report) -> None:
    dev_rows = [json.loads(line) for line in DEV_PATH.open(encoding="utf-8")]
    dev_rows = [r for r in dev_rows if r["answerable"]]

    chunk_texts_by_file: dict[str, list[str]] = {}
    for c in chunks:
        chunk_texts_by_file.setdefault(c["source_file"], []).append(normalize(c["text"]))

    misses = []
    for q in dev_rows:
        passage_norm = normalize(q["source_passage"])
        candidates = chunk_texts_by_file.get(q["source_file"], [])
        if not any(passage_norm in ct for ct in candidates):
            misses.append(q["id"])

    n = len(dev_rows)
    hit_rate = (n - len(misses)) / n if n else 1.0
    report.check(
        "dev passage coverage: 100% fully contained in some chunk (this is our recall ceiling)",
        len(misses) == 0,
        f"{hit_rate:.1%} ({n - len(misses)}/{n}); misses: {misses}" if misses else f"{hit_rate:.1%}",
    )


def check_determinism(strategy, max_tokens, overlap, min_tokens, docs, count_tokens, report: Report) -> None:
    def build_ids() -> list[str]:
        ids = []
        for doc in docs:
            for c in chunk_document(doc, strategy, max_tokens, overlap, min_tokens, count_tokens):
                ids.append(c["chunk_id"])
        return ids

    ids_1 = build_ids()
    ids_2 = build_ids()
    report.check(
        "chunk_id determinism (build chunks twice, diff)",
        ids_1 == ids_2,
        "identical" if ids_1 == ids_2 else f"{len(ids_1)} vs {len(ids_2)} ids, differ at first mismatch",
    )


def check_counts(manifest: dict, chunks: list[dict], client, report: Report) -> None:
    collection = manifest["qdrant_collection"]
    qdrant_count = client.count(collection).count
    report.check(
        "Qdrant point count == chunks.jsonl count == manifest count",
        qdrant_count == len(chunks) == manifest["n_chunks"],
        f"qdrant={qdrant_count}, chunks.jsonl={len(chunks)}, manifest={manifest['n_chunks']}",
    )


# --------------------------------------------------------------------- #
# smoke queries (informational, not part of the PASS/FAIL summary)
# --------------------------------------------------------------------- #


def run_smoke_queries(manifest: dict, chunks: list[dict], index_dir: Path, client, queries: list[str]) -> None:
    bm25_index = bm25s.BM25.load(str(index_dir / "bm25"), load_corpus=False)
    embed_config = EmbeddingConfig()
    for q in queries:
        print(f"\n=== query: {q!r} ===")
        [query_vector] = embed_texts([q], embed_config, show_progress=False)
        for h in vector_search(client, manifest["qdrant_collection"], query_vector, k=3):
            print(f"  vector {h['_score']:.3f}  {h['section_path']}  ({h['source_file']})")

        bm25_ids, bm25_scores = bm25_index.retrieve(
            [tokenize_for_bm25(q)], corpus=list(range(len(chunks))), k=3, show_progress=False
        )
        for i, s in zip(bm25_ids[0], bm25_scores[0]):
            c = chunks[i]
            print(f"  bm25   {s:.3f}  {c['section_path']}  ({c['source_file']})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index_dir", type=Path, help="e.g. data/index/heading_mt512_min20")
    parser.add_argument("--query", action="append", dest="queries", default=None)
    parser.add_argument("--skip-smoke-queries", action="store_true", help="skip the live API/Qdrant queries")
    args = parser.parse_args()

    manifest = json.loads((args.index_dir / "manifest.json").read_text())
    chunks = load_chunks(args.index_dir)
    docs = load_all_documents()
    count_tokens = make_token_counter(manifest["embedding_model"])
    client = get_client()

    report = Report()
    check_no_empty_sheets(chunks, report)
    check_text_coverage(docs, chunks, report)
    check_fence_and_table_shape(chunks, report)
    check_token_limits(chunks, count_tokens, report)
    check_dev_passage_coverage(chunks, report)
    check_determinism(
        manifest["strategy"], manifest["max_tokens"], manifest["overlap"], manifest["min_tokens"],
        docs, count_tokens, report,
    )
    check_counts(manifest, chunks, client, report)

    print(f"\n{sum(p for _, p, _ in report.results)}/{len(report.results)} checks passed")

    if not args.skip_smoke_queries:
        run_smoke_queries(manifest, chunks, args.index_dir, client, args.queries or DEFAULT_QUERIES)

    if not report.all_passed():
        sys.exit(1)


if __name__ == "__main__":
    main()
