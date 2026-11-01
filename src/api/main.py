"""
HTTP API over the existing Librarian (src/generation/answer.py), which is
reused as-is: the Retriever, reranker and Gemini client are loaded once at
startup and every request only pays for one embedding call, the rerank and
one Gemini call.

    POST /ask       {question, top_k?}            -> cited answer + timings
    POST /feedback  {request_id, helpful, comment?}
    GET  /stats     request count, p50/p95 latency, refusal rate, feedback counts
    GET  /health    200 once the Librarian is loaded, 503 before / if it failed

Every /ask and /feedback is appended to data/logs/requests.jsonl and
data/logs/feedback.jsonl (gitignored; LOG_DIR overrides the location).
/stats is computed from those logs, so it survives restarts.

Errors from Qdrant / OpenAI / Gemini become a plain 503: the exception
class is logged, its message (which can contain URLs or request details)
is never returned to the client.

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
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_LOG_DIR = ROOT / "data" / "logs"
MAX_QUESTION_CHARS = 1000
MAX_TOP_K = 10
UNAVAILABLE = "The answer service is temporarily unavailable. Please try again shortly."

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


class AskResponse(BaseModel):
    request_id: str
    question: str
    answer: str
    answerable: bool
    refusal_reason: str | None
    citations: list[Citation]
    model: str | None
    timings_ms: dict[str, float]
    latency_ms: float  # end to end inside the API, including what timings_ms doesn't cover


class FeedbackRequest(BaseModel):
    request_id: str = Field(..., min_length=1, max_length=64)
    helpful: bool
    comment: str | None = Field(None, max_length=2000)


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


def _load_real_librarian() -> Any:
    """OpenAI (OpenAIGenerator) by default: with our Gemini key, Gemini took
    100-300s per answer vs ~3s for gpt-4o-mini. GENERATOR=gemini uses the
    original Librarian.from_config() instead. Retrieval and the reranker are
    wired exactly as Librarian.from_config does it."""
    from ..generation import Librarian

    rerank = os.environ.get("LIBRARIAN_RERANK", "1") != "0"
    if os.environ.get("GENERATOR", "openai").lower() == "gemini":
        return Librarian.from_config(rerank=rerank)

    from ..retrieval.retriever import Retriever
    from .openai_generator import OpenAIGenerator

    reranker = None
    if rerank:
        from ..retrieval.reranker import make_reranker

        reranker = make_reranker()
    generator = OpenAIGenerator()
    return Librarian(Retriever.from_config(reranker=reranker), generator, generator.model)


def create_app(
    librarian_factory: Callable[[], Any] = _load_real_librarian,
    log_dir: Path | str | None = None,
) -> FastAPI:
    """`librarian_factory` is injectable so tests can pass a fake Librarian
    (anything with .ask(question, top_k=...) -> Answer) and run offline."""
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

    @app.get("/health")
    def health():
        if state["librarian"] is None:
            detail = {"status": "unavailable", "reason": state["load_error"] or "loading"}
            raise HTTPException(status_code=503, detail=detail)
        return {"status": "ok", "model": getattr(state["librarian"], "model", None)}

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
            log.error("ask %s failed: %s", request_id, type(exc).__name__)
            events.log_request({**record, "status": "error", "error": type(exc).__name__,
                                "latency_ms": round((time.perf_counter() - t0) * 1000, 2)})
            raise HTTPException(status_code=503, detail=UNAVAILABLE)

        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        citations = [Citation(**vars(c)) for c in result.citations]
        events.log_request({
            **record, "status": "ok", "answerable": result.answerable, "refusal_reason": result.refusal_reason,
            "answer": result.answer, "cited_chunks": [c.chunk_id for c in citations],
            "retrieved_chunks": [s.chunk_id for s in result.sources], "model": result.model,
            "timings_ms": result.timings_ms, "latency_ms": latency_ms,
        })
        return AskResponse(
            request_id=request_id, question=req.question, answer=result.answer, answerable=result.answerable,
            refusal_reason=result.refusal_reason, citations=citations, model=result.model,
            timings_ms=result.timings_ms, latency_ms=latency_ms,
        )

    @app.post("/feedback")
    def feedback(req: FeedbackRequest):
        if req.request_id not in events.request_ids:
            raise HTTPException(status_code=404, detail="unknown request_id")
        events.log_feedback({"ts": _now(), "request_id": req.request_id, "helpful": req.helpful,
                             "comment": (req.comment or "").strip() or None})
        return {"status": "recorded"}

    @app.get("/stats")
    def stats():
        return events.stats()

    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()
