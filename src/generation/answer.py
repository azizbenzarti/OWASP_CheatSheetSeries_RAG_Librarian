"""
Question in, cited answer out: the full RAG pipeline on top of the existing
Retriever (src/retrieval/), which is reused as-is -- nothing here rebuilds,
re-chunks or re-embeds anything.

    question -> Retriever.retrieve() (hybrid, optionally reranked) -> top-k chunks
             -> prompt.py (numbered [n] sources) -> Gemini (JSON answer)
             -> citation check -> Answer (text + cited sources with OWASP URLs)

"I don't know" can happen at four points, each recorded as refusal_reason:
  1. retrieval returned nothing (empty_query / no_results /
     below_vector_score_threshold) -- Gemini is not called at all;
  2. Gemini says the sources don't answer it (model_declined);
  3. Gemini answers but cites no valid source (no_valid_citations): an
     uncited answer can't be checked against the corpus, so it isn't shown;
  4. Gemini's output is blocked, empty or not the JSON we asked for
     (invalid_model_output);
  5. the model says answerable=true but its answer opens by saying the
     sources don't cover the question (declined_in_text) -- a refusal in
     prose. Added in Week 8: gpt-5-nano does this often, gpt-4o-mini never
     did on our eval runs (docs/optimisation.md).
Per docs/design.md, the model's judgment (2) is the primary mechanism; no
retrieval-score threshold is on by default because none separated
answerable from unanswerable cleanly on dev.

Usage:
    from src.generation import ask
    result = ask("how should I store passwords?")
    print(result.format())

CLI:  python -m src.generation "how should I store passwords?"
      python -m src.generation --smoke     # Gemini only: no Qdrant / OpenAI needed
"""
from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Sequence

from ..retrieval.retriever import DEFAULT_CANDIDATES, RetrievedChunk, Retriever
from .prompt import SYSTEM_PROMPT, build_user_prompt

Generate = Callable[[str, str], "str | None"]  # (system_prompt, user_prompt) -> raw model text

IDK_ANSWER = (
    "I don't know. The OWASP Cheat Sheet Series sources I found don't answer this question."
)
RERANK_CANDIDATES = 20  # same "rerank hybrid's top 20" as the retriever CLI and eval/retrieval_eval.py

# "[1]", "[2, 3]", "[2,3]". Not "[a]" or markdown links ("[text](url)" has no digits-only brackets).
_CITATION_RE = re.compile(r"([ \t]*)\[(\d+(?:\s*,\s*\d+)*)\]")
_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)
# First sentence = "The (provided) sources ... do not / cannot ...", with the
# negation within two words of the subject, so "The sources emphasize X and
# note that Y does not ..." (a real answer) does not match. Checked on 341
# saved eval answers: 4 true refusals caught, 0 real answers hit.
_DECLINE_RE = re.compile(
    r"^\s*(?:the\s+)?(?:provided\s+|given\s+|available\s+|retrieved\s+|owasp\s+)?"
    r"(?:sources?|corpus|cheat\s*sheets?|materials?|excerpts?|documents?)\s+(?:\w+\s+){0,2}?"
    r"(?:do(?:es)?\s+not|don't|doesn't|cannot|can't)\b",
    re.IGNORECASE,
)


# --------------------------------------------------------------------- #
# data structures
# --------------------------------------------------------------------- #


@dataclass
class Source:
    """One retrieved chunk as shown to the user. `number` is its [n] label
    in the prompt, i.e. the retriever's rank."""

    number: int
    title: str
    section_path: str
    source_file: str
    source_url: str
    chunk_id: str
    text: str = ""  # the passage itself, so a UI can show exactly what the model was given

    @classmethod
    def from_chunk(cls, number: int, chunk: RetrievedChunk) -> "Source":
        return cls(number, chunk.title, chunk.section_path, chunk.source_file, chunk.source_url, chunk.chunk_id, chunk.text)


@dataclass
class Answer:
    question: str
    answer: str
    answerable: bool
    citations: list[Source]  # only the sources the answer actually cites, by number
    sources: list[Source]  # every chunk given to the model (what it could have cited)
    refusal_reason: str | None = None
    invalid_citations: list[int] = field(default_factory=list)  # [n] the model cited that didn't exist (removed)
    model: str | None = None
    timings_ms: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def format(self) -> str:
        """Plain-text rendering for the CLI: answer, then the cited sources."""
        lines = [self.answer]
        if self.citations:
            lines.append("\nSources:")
            for s in self.citations:
                section = f" > {s.section_path}" if s.section_path else ""
                lines.append(f"  [{s.number}] {s.title}{section}\n      {s.source_url}")
        return "\n".join(lines)


# --------------------------------------------------------------------- #
# pure helpers (no I/O, unit-tested in tests/test_generation.py)
# --------------------------------------------------------------------- #


def parse_model_output(raw: str | None) -> tuple[bool, str] | None:
    """(answerable, answer) from the model's JSON, or None if it isn't the
    shape we asked for. Tolerates a ```json fence around it, which some
    models add even in JSON mode."""
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    fenced = _CODE_FENCE_RE.match(text)
    if fenced:
        text = fenced.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    answerable, answer = data.get("answerable"), data.get("answer")
    if not isinstance(answerable, bool) or not isinstance(answer, str):
        return None
    return answerable, answer.strip()


def declines_in_text(answer: str) -> bool:
    """True if the answer's first sentence says the sources don't cover the
    question, i.e. a refusal written as prose under answerable=true."""
    first = re.split(r"(?<=[.!?])\s", answer.strip(), maxsplit=1)[0]
    return bool(_DECLINE_RE.search(first))


def check_citations(answer: str, n_sources: int) -> tuple[str, list[int], list[int]]:
    """Keep [n] citations that point at a real source (1..n_sources); drop
    the rest from the text. Returns (cleaned answer, valid numbers sorted,
    invalid numbers sorted)."""
    valid: set[int] = set()
    invalid: set[int] = set()

    def fix(match: re.Match) -> str:
        nums = [int(n) for n in re.split(r"\s*,\s*", match.group(2))]
        keep = [n for n in nums if 1 <= n <= n_sources]
        valid.update(keep)
        invalid.update(n for n in nums if n not in keep)
        # Dropping a marker also drops the space before it: "claim [9]." -> "claim."
        return f"{match.group(1)}[{', '.join(map(str, keep))}]" if keep else ""

    cleaned = _CITATION_RE.sub(fix, answer)
    return cleaned.strip(), sorted(valid), sorted(invalid)


def build_answer(
    question: str,
    raw: str | None,
    chunks: Sequence[RetrievedChunk],
    model: str | None = None,
) -> Answer:
    """Turn the model's raw output into an Answer, applying refusal rules 2-5
    from the module docstring."""
    sources = [Source.from_chunk(i, c) for i, c in enumerate(chunks, start=1)]

    def refuse(reason: str, invalid: list[int] | None = None) -> Answer:
        return Answer(question, IDK_ANSWER, False, [], sources, reason, invalid or [], model)

    parsed = parse_model_output(raw)
    if parsed is None:
        return refuse("invalid_model_output")
    answerable, text = parsed
    if not answerable or not text:
        return refuse("model_declined")
    if declines_in_text(text):
        return refuse("declined_in_text")

    cleaned, valid, invalid = check_citations(text, len(sources))
    if not valid:
        return refuse("no_valid_citations", invalid)

    cited = [sources[n - 1] for n in valid]
    return Answer(question, cleaned, True, cited, sources, None, invalid, model)


def answer_question(
    question: str,
    retriever: Retriever,
    generate: Generate,
    top_k: int = 5,
    min_vector_score: float | None = None,
    model: str | None = None,
    rerank_candidates: int = RERANK_CANDIDATES,
) -> Answer:
    """The whole pipeline for one question. `retriever` and `generate` are
    passed in (not built here) so tests can use fakes, and so a long-lived
    caller (the future API) loads the index once and reuses it."""
    t0 = time.perf_counter()
    candidates = rerank_candidates if retriever.reranker else DEFAULT_CANDIDATES
    retrieved = retriever.retrieve(
        question, top_k=top_k, mode="hybrid", candidates=candidates, min_vector_score=min_vector_score
    )
    timings = {f"retrieval_{k}": v for k, v in retrieved.timings_ms.items()}

    if retrieved.is_empty:  # refusal rule 1: nothing to ground an answer in, so don't pay for a Gemini call
        timings["total_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return Answer(question, IDK_ANSWER, False, [], [], retrieved.no_answer_reason, model=model, timings_ms=timings)

    t = time.perf_counter()
    raw = generate(SYSTEM_PROMPT, build_user_prompt(question, retrieved.chunks))
    timings["generation_ms"] = round((time.perf_counter() - t) * 1000, 2)

    result = build_answer(question, raw, retrieved.chunks, model)
    timings["total_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    result.timings_ms = timings
    return result


# --------------------------------------------------------------------- #
# real wiring
# --------------------------------------------------------------------- #


class Librarian:
    """Holds a loaded Retriever + Gemini generator, so each question only
    pays for retrieval and one Gemini call. Build once with from_config()."""

    def __init__(self, retriever: Retriever, generate: Generate, model: str | None = None) -> None:
        self.retriever = retriever
        self.generate = generate
        self.model = model

    @classmethod
    def from_config(cls, rerank: bool = True, index_dir: str | None = None) -> "Librarian":
        """Real wiring: Retriever.from_config() (needs Qdrant, the built
        data/index/, and the OpenAI embedding key) + GeminiGenerator (needs
        GEMINI_API_KEY). rerank=True is the dev-set winner at top-5 (recall@5
        0.85 vs 0.77 for plain hybrid, see eval/results/retrieval_dev.md)."""
        from .gemini import GeminiGenerator

        reranker = None
        if rerank:
            try:
                from ..retrieval.reranker import make_reranker
            except ImportError as exc:
                raise RuntimeError(
                    "Reranking needs torch + sentence-transformers: run `pip install -r requirements.txt`, "
                    "or pass rerank=False (CLI: --no-rerank)."
                ) from exc
            reranker = make_reranker()
        retriever = Retriever.from_config(index_dir, reranker=reranker)
        generator = GeminiGenerator()
        return cls(retriever, generator, generator.model)

    def ask(
        self, question: str, top_k: int = 5, min_vector_score: float | None = None,
        rerank_candidates: int = RERANK_CANDIDATES,
    ) -> Answer:
        return answer_question(
            question, self.retriever, self.generate, top_k, min_vector_score, self.model, rerank_candidates
        )


_default_librarian: Librarian | None = None


def ask(question: str, top_k: int = 5, rerank: bool = True) -> Answer:
    """One call, question -> Answer. Loads the index and models on first use
    and reuses them afterwards (a second call with a different `rerank` is
    ignored -- build a Librarian yourself if you need both)."""
    global _default_librarian
    if _default_librarian is None:
        _default_librarian = Librarian.from_config(rerank=rerank)
    return _default_librarian.ask(question, top_k=top_k)


# --------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------- #

# Two hand-written chunks for --smoke: tests Gemini + the prompt + citation
# handling with no Qdrant, no index and no OpenAI call.
_SMOKE_CHUNKS = [
    RetrievedChunk(
        chunk_id="smoke-1", source_file="Password_Storage_Cheat_Sheet.md",
        title="Password Storage Cheat Sheet", section_path="Password Hashing Algorithms > Argon2id",
        text="Argon2id should use one of the following configuration settings as a base minimum "
        "which includes the minimum memory size (m), the minimum number of iterations (t) and the "
        "degree of parallelism (p): m=47104 (46 MiB), t=1, p=1 (Do not use with Argon2i).",
        score=1.0, rank=1,
        source_url="https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html",
    ),
    RetrievedChunk(
        chunk_id="smoke-2", source_file="Password_Storage_Cheat_Sheet.md",
        title="Password Storage Cheat Sheet", section_path="Password Hashing Algorithms > bcrypt",
        text="The work factor for bcrypt should be as large as verification server performance will "
        "allow, with a minimum of 10.",
        score=0.9, rank=2,
        source_url="https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html",
    ),
]
_SMOKE_QUESTIONS = [
    "What Argon2id parameters should I use for password hashing?",  # answerable from the chunks
    "How do I configure TLS certificate pinning on Android?",  # not in the chunks -> should say I don't know
]


def _print(result: Answer, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return
    print(result.format())
    if result.refusal_reason:
        print(f"\n(refusal_reason: {result.refusal_reason})")
    if result.invalid_citations:
        print(f"(removed invalid citations: {result.invalid_citations})")
    if result.timings_ms:
        print(f"\n{json.dumps(result.timings_ms)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Answer a question from the OWASP index with Gemini.")
    parser.add_argument("question", nargs="?")
    parser.add_argument("-k", "--top-k", type=int, default=5)
    parser.add_argument("--no-rerank", action="store_true", help="plain hybrid retrieval (no torch needed)")
    parser.add_argument("--index-dir", default=None)
    parser.add_argument("--json", action="store_true", help="print the full Answer as JSON")
    parser.add_argument(
        "--smoke", action="store_true",
        help="test Gemini alone on two built-in chunks (2 Gemini calls, no Qdrant/OpenAI)",
    )
    args = parser.parse_args()

    if args.smoke:
        from .gemini import GeminiGenerator

        generator = GeminiGenerator()
        print(f"model: {generator.model}\n")
        for q in _SMOKE_QUESTIONS:
            print(f"=== {q}")
            raw = generator(SYSTEM_PROMPT, build_user_prompt(q, _SMOKE_CHUNKS))
            _print(build_answer(q, raw, _SMOKE_CHUNKS, generator.model), args.json)
            print()
        return

    if not args.question:
        parser.error("give a question, or --smoke")
    librarian = Librarian.from_config(rerank=not args.no_rerank, index_dir=args.index_dir)
    _print(librarian.ask(args.question, top_k=args.top_k), args.json)
