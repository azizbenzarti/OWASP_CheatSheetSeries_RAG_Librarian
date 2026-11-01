"""
HTTP API over the existing Librarian (src/generation/answer.py), which is
reused as-is: the Retriever, reranker and Gemini client are loaded once at
startup and every request only pays for one embedding call, the rerank and
one Gemini call.

    POST /ask       {question, top_k?}            -> cited answer + timings
    POST /feedback  {request_id, helpful, comment?}
    GET  /stats     request count, p50/p95 latency, refusal rate, feedback counts
    GET  /health    200 once the Librarian is loaded and Qdrant holds one point
                    per chunk (checked live), 503 otherwise

Every /ask and /feedback is appended to data/logs/requests.jsonl and
data/logs/feedback.jsonl (gitignored; LOG_DIR overrides the location).
/stats is computed from those logs, so it survives restarts.

Status codes: 422 bad input, 503 the Librarian isn't loaded, 502 an
upstream call (Qdrant / OpenAI / Gemini) failed. The exception class is
logged; its message (which can contain URLs or request details) is never
returned to the client.

Built from two team versions: request logging, /stats and the OpenAI
generator from one; the live Qdrant health check, 502 for upstream
failures and LIBRARIAN_INDEX_DIR from Aziz's.

Run:  uvicorn src.api.main:app --port 8000
"""
from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_LOG_DIR = ROOT / "data" / "logs"
MAX_QUESTION_CHARS = 1000
MAX_TOP_K = 10
UNAVAILABLE = "The answer service is temporarily unavailable. Please try again shortly."
UPSTREAM_FAILED = "Answer generation failed upstream; please try again shortly."

log = logging.getLogger("librarian.api")


# --------------------------------------------------------------------- #
# request / response models
# --------------------------------------------------------------------- #


class AskRequest(BaseModel):
    question: str = Field(..., max_length=MAX_QUESTION_CHARS)
    top_k: int = Field(5, ge=1, le=MAX_TOP_K)

    @field_validator("question")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question must not be empty")
        return v


class Citation(BaseModel):
    number: int  # the [n] used in the answer text
    title: str
    section_path: str
    source_file: str
    source_url: str
    chunk_id: str
    text: str = ""  # the passage exactly as the model received it (the UI's source pane)


class AskResponse(BaseModel):
    request_id: str
    question: str
    answer: str
    answerable: bool
    refusal_reason: str | None
    citations: list[Citation]  # the sources the answer cites
    sources: list[Citation]  # every source given to the model
    invalid_citations: list[int]
    model: str | None
    timings_ms: dict[str, float]
    latency_ms: float  # end to end inside the API, including what timings_ms doesn't cover


class FeedbackRequest(BaseModel):
    """One thumbs up/down. Stores what was asked and answered, never who
    asked (no IP, no user id). The UI sends `rating`; `helpful` is accepted
    too. `request_id` links the vote to its line in requests.jsonl."""

    rating: Literal["up", "down"] | None = None
    helpful: bool | None = None
    comment: str | None = Field(None, max_length=2000)
    request_id: str | None = Field(None, max_length=64)
    question: str | None = Field(None, max_length=MAX_QUESTION_CHARS)
    answer: str | None = Field(None, max_length=20000)
    answerable: bool | None = None
    refusal_reason: str | None = Field(None, max_length=64)
    cited_chunk_ids: list[str] = Field(default_factory=list, max_length=MAX_TOP_K)
    model: str | None = Field(None, max_length=100)

    @model_validator(mode="after")
    def one_rating(self) -> "FeedbackRequest":
        if self.rating is None and self.helpful is None:
            raise ValueError("give rating ('up' or 'down') or helpful (true/false)")
        if self.helpful is None:
            self.helpful = self.rating == "up"
        return self


# --------------------------------------------------------------------- #
# JSONL log + stats
# --------------------------------------------------------------------- #


def percentile(values: list[float], p: float) -> float | None:
    """Nearest-rank percentile (p in 0..100); None for no data."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p / 100 * len(ordered)) - 1)]


class EventLog:
    """Append-only JSONL files plus the in-memory copy /stats is computed
    from. Existing files are read back at startup, so stats cover every
    request the service has logged, not just this process's."""

    def __init__(self, log_dir: Path) -> None:
        self.dir = log_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.requests_path = self.dir / "requests.jsonl"
        self.feedback_path = self.dir / "feedback.jsonl"
        self._lock = threading.Lock()
        self.requests = self._read(self.requests_path)
        self.feedback = self._read(self.feedback_path)
        self.request_ids = {r["request_id"] for r in self.requests if "request_id" in r}

    @staticmethod
    def _read(path: Path) -> list[dict]:
        if not path.is_file():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:  # a half-written line from a crash shouldn't stop startup
                continue
        return rows

    def _append(self, path: Path, rows: list[dict], record: dict) -> None:
        with self._lock:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            rows.append(record)

    def log_request(self, record: dict) -> None:
        self._append(self.requests_path, self.requests, record)
        self.request_ids.add(record["request_id"])

    def log_feedback(self, record: dict) -> None:
        self._append(self.feedback_path, self.feedback, record)

    def stats(self) -> dict:
        with self._lock:
            requests, feedback = list(self.requests), list(self.feedback)
        ok = [r for r in requests if r.get("status") == "ok"]
        latencies = [r["latency_ms"] for r in ok]
        refused = [r for r in ok if not r.get("answerable")]
        reasons: dict[str, int] = {}
        for r in refused:
            reason = r.get("refusal_reason") or "unknown"
            reasons[reason] = reasons.get(reason, 0) + 1
        helpful = sum(1 for f in feedback if f.get("helpful"))
        return {
            "requests": len(requests),
            "answered": len(ok),
            "errors": len(requests) - len(ok),
            "latency_ms": {"p50": percentile(latencies, 50), "p95": percentile(latencies, 95)},
            "refusal_rate": round(len(refused) / len(ok), 4) if ok else None,
            "refusal_reasons": reasons,
            "feedback": {"total": len(feedback), "helpful": helpful, "not_helpful": len(feedback) - helpful},
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


# --------------------------------------------------------------------- #
# app
# --------------------------------------------------------------------- #


def _index_dir() -> Path:
    from ..retrieval.retriever import DEFAULT_INDEX_DIR

    return Path(os.environ.get("LIBRARIAN_INDEX_DIR") or DEFAULT_INDEX_DIR)


class QdrantCheck:
    """Live check for /health (from Aziz's first version of the API): the
    Qdrant collection the index was built into is reachable and still holds
    one point per chunk -- the same check Retriever.from_config does at
    startup, repeated on every call so a Qdrant restart or wiped volume shows
    up in /health instead of as failed answers."""

    def __init__(self, index_dir: Path) -> None:
        self.index_dir = index_dir

    def __call__(self, librarian: Any) -> str:
        from ..indexing.vectordb import get_client

        manifest = json.loads((self.index_dir / "manifest.json").read_text(encoding="utf-8"))
        try:
            points = get_client().get_collection(manifest["qdrant_collection"]).points_count
        except Exception as exc:
            log.warning("Qdrant health check failed: %s", type(exc).__name__)
            return "unreachable"
        expected = len(librarian.retriever.chunks)
        return "ok" if points == expected else f"out of sync: {points} points, {expected} chunks"


def _load_real_librarian() -> Any:
    """OpenAI (OpenAIGenerator) by default: with our Gemini key, Gemini took
    100-300s per answer vs ~3s for gpt-4o-mini. GENERATOR=gemini uses the
    original Librarian.from_config() instead. Retrieval and the reranker are
    wired exactly as Librarian.from_config does it."""
    from ..generation import Librarian

    rerank = os.environ.get("LIBRARIAN_RERANK", "true").strip().lower() not in ("0", "false", "no", "off")
    index_dir = _index_dir()
    if os.environ.get("GENERATOR", "openai").lower() == "gemini":
        return Librarian.from_config(rerank=rerank, index_dir=str(index_dir))

    from ..retrieval.retriever import Retriever
    from .openai_generator import OpenAIGenerator

    reranker = None
    if rerank:
        from ..retrieval.reranker import make_reranker

        reranker = make_reranker()
    generator = OpenAIGenerator()
    return Librarian(Retriever.from_config(index_dir, reranker=reranker), generator, generator.model)


def create_app(
    librarian_factory: Callable[[], Any] = _load_real_librarian,
    log_dir: Path | str | None = None,
    health_check: Callable[[Any], str] | None = None,
) -> FastAPI:
    """`librarian_factory` is injectable so tests can pass a fake Librarian
    (anything with .ask(question, top_k=...) -> Answer) and run offline.
    `health_check(librarian)` returns "ok" or why Qdrant isn't; None skips it."""
    state: dict[str, Any] = {"librarian": None, "load_error": None}
    events = EventLog(Path(log_dir or os.environ.get("LOG_DIR") or DEFAULT_LOG_DIR))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        t = time.perf_counter()
        try:
            state["librarian"] = librarian_factory()
            log.info("Librarian loaded in %.1fs", time.perf_counter() - t)
        except Exception as exc:  # keep serving /health and /stats so the failure is visible
            state["load_error"] = type(exc).__name__
            log.error("Librarian failed to load: %s: %s", type(exc).__name__, exc)
        yield

    app = FastAPI(title="The Librarian", description="Cited answers from the OWASP Cheat Sheet Series.", lifespan=lifespan)

    # Flat body in both cases (the UI reads it even on 503).
    @app.get("/health")
    def health():
        librarian = state["librarian"]
        if librarian is None:
            reason = state["load_error"] or "loading"
            return JSONResponse({"status": "unavailable", "index_loaded": False, "error": reason}, status_code=503)
        qdrant = health_check(librarian) if health_check else "ok"
        retriever = getattr(librarian, "retriever", None)
        body = {
            "status": "ok" if qdrant == "ok" else "unavailable", "index_loaded": True,
            "model": getattr(librarian, "model", None), "qdrant": qdrant,
            "chunks": len(getattr(retriever, "chunks", []) or []) or None,
            "rerank": getattr(retriever, "reranker", None) is not None,
        }
        return JSONResponse(body, status_code=200 if qdrant == "ok" else 503)

    # Plain `def` (not async): Librarian.ask blocks on network + CPU, so
    # FastAPI runs it in its threadpool instead of stalling the event loop.
    @app.post("/ask", response_model=AskResponse)
    def ask(req: AskRequest):
        request_id = uuid.uuid4().hex
        t0 = time.perf_counter()
        record: dict[str, Any] = {"request_id": request_id, "ts": _now(), "question": req.question, "top_k": req.top_k}
        librarian = state["librarian"]
        if librarian is None:
            events.log_request({**record, "status": "error", "error": state["load_error"] or "not_loaded",
                                "latency_ms": round((time.perf_counter() - t0) * 1000, 2)})
            raise HTTPException(status_code=503, detail=UNAVAILABLE)
        try:
            result = librarian.ask(req.question, top_k=req.top_k)
        except Exception as exc:  # Qdrant down, OpenAI/Gemini errors after retries, ...
            # 502, not 503: the service is up, an upstream call failed. The UI
            # tells these apart ("ask again" vs "index not loaded").
            log.error("ask %s failed: %s", request_id, type(exc).__name__)
            events.log_request({**record, "status": "error", "error": type(exc).__name__,
                                "latency_ms": round((time.perf_counter() - t0) * 1000, 2)})
            raise HTTPException(status_code=502, detail=UPSTREAM_FAILED)

        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        citations = [Citation(**vars(c)) for c in result.citations]
        sources = [Citation(**vars(s)) for s in result.sources]
        events.log_request({
            **record, "status": "ok", "answerable": result.answerable, "refusal_reason": result.refusal_reason,
            "answer": result.answer, "cited_chunks": [c.chunk_id for c in citations],
            "retrieved_chunks": [s.chunk_id for s in result.sources], "model": result.model,
            "timings_ms": result.timings_ms, "latency_ms": latency_ms,
        })
        return AskResponse(
            request_id=request_id, question=req.question, answer=result.answer, answerable=result.answerable,
            refusal_reason=result.refusal_reason, citations=citations, sources=sources,
            invalid_citations=result.invalid_citations, model=result.model,
            timings_ms=result.timings_ms, latency_ms=latency_ms,
        )

    # Works even when the Librarian failed to load: feedback doesn't need the index.
    @app.post("/feedback", status_code=204)
    def feedback(req: FeedbackRequest):
        if req.request_id is not None and req.request_id not in events.request_ids:
            raise HTTPException(status_code=404, detail="unknown request_id")
        record = req.model_dump(exclude={"rating"})
        record["comment"] = (req.comment or "").strip() or None
        events.log_feedback({"ts": _now(), **record})
        return Response(status_code=204)

    @app.get("/stats")
    def stats():
        return events.stats()

    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app(health_check=QdrantCheck(_index_dir()))
