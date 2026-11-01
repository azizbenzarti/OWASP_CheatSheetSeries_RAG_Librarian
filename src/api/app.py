"""
HTTP API for The Librarian: a thin FastAPI layer over src/generation's
Librarian, which is reused as-is.

    POST /ask     {"question": "...", "top_k": 5} -> cited answer (or "I don't know")
    GET  /health  is the index loaded, and does Qdrant still hold it?

The Librarian (chunks, BM25, Qdrant client, reranker, Gemini client) is
built ONCE at startup, in the lifespan hook, and shared by every request.
Building it per request would reload the index and the cross-encoder each
time.

If startup fails (Qdrant down, index missing, a key unset) the app still
starts: /health returns 503 with the reason and /ask returns 503, so a
container healthcheck reports the real problem instead of a crash loop.

Environment (on top of the .env the Librarian already reads):
    LIBRARIAN_RERANK     "true" (default) or "false": cross-encoder rerank
    LIBRARIAN_INDEX_DIR  optional: a different built index directory

Run:  uvicorn src.api.app:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from ..generation.answer import Librarian

logger = logging.getLogger("librarian.api")

MAX_QUESTION_CHARS = 1000  # long enough for any real question; caps prompt size and cost per request
MAX_TOP_K = 10


# --------------------------------------------------------------------- #
# request / response models
# --------------------------------------------------------------------- #


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=MAX_QUESTION_CHARS)
    top_k: int = Field(5, ge=1, le=MAX_TOP_K, description="chunks given to the model")

    @field_validator("question")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question is empty")
        return v


class SourceOut(BaseModel):
    number: int
    title: str
    section_path: str
    source_file: str
    source_url: str
    chunk_id: str


class AskResponse(BaseModel):
    question: str
    answer: str
    answerable: bool
    refusal_reason: str | None
    citations: list[SourceOut]  # the sources the answer cites
    sources: list[SourceOut]  # every chunk given to the model
    invalid_citations: list[int]
    model: str | None
    timings_ms: dict[str, float]


class HealthResponse(BaseModel):
    status: str  # "ok" | "unavailable"
    index_loaded: bool
    chunks: int | None = None
    qdrant: str | None = None  # "ok" or the reason it isn't
    rerank: bool | None = None
    model: str | None = None
    error: str | None = None


# --------------------------------------------------------------------- #
# health check against the real Qdrant
# --------------------------------------------------------------------- #


@dataclass
class QdrantCheck:
    """Confirms the Qdrant collection the index was built into is reachable
    and still holds one point per chunk (same check Retriever.from_config
    does at startup, repeated on every /health)."""

    index_dir: Path

    def __call__(self, librarian: Librarian) -> str:
        from ..indexing.vectordb import get_client

        manifest = json.loads((self.index_dir / "manifest.json").read_text(encoding="utf-8"))
        collection = manifest["qdrant_collection"]
        try:
            points = get_client().get_collection(collection).points_count
        except Exception as exc:
            logger.warning("qdrant health check failed: %s", exc)
            return "unreachable"
        expected = len(librarian.retriever.chunks)
        if points != expected:
            return f"out of sync: {points} points, {expected} chunks"
        return "ok"


HealthCheck = Callable[[Librarian], str]


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


def _default_loader() -> tuple[Librarian, HealthCheck]:
    from ..retrieval.retriever import DEFAULT_INDEX_DIR

    index_dir = os.environ.get("LIBRARIAN_INDEX_DIR") or None
    librarian = Librarian.from_config(rerank=_env_flag("LIBRARIAN_RERANK", True), index_dir=index_dir)
    return librarian, QdrantCheck(Path(index_dir) if index_dir else DEFAULT_INDEX_DIR)


# --------------------------------------------------------------------- #
# app
# --------------------------------------------------------------------- #


def create_app(loader: Callable[[], tuple[Librarian, HealthCheck]] = _default_loader) -> FastAPI:
    """`loader` builds the Librarian and its health check at startup. Tests
    pass one that returns a Librarian over a fake retriever and fake Gemini."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.librarian = None
        app.state.health_check = None
        app.state.startup_error = None
        try:
            app.state.librarian, app.state.health_check = loader()
            logger.info("librarian loaded: %d chunks", len(app.state.librarian.retriever.chunks))
        except Exception as exc:
            # Startup errors from the Librarian are config messages written for
            # humans (missing index, Qdrant down, key unset); none contain a key.
            app.state.startup_error = f"{type(exc).__name__}: {exc}"
            logger.exception("librarian failed to load")
        yield

    app = FastAPI(
        title="The Librarian",
        description="RAG over the OWASP Cheat Sheet Series, with citations.",
        version="0.1.0",
        lifespan=lifespan,
    )

    def get_librarian(request: Request) -> Librarian:
        librarian = request.app.state.librarian
        if librarian is None:
            raise HTTPException(503, "The Librarian is not loaded; see GET /health for the reason.")
        return librarian

    @app.get("/health", response_model=HealthResponse)
    def health(request: Request) -> Any:
        state = request.app.state
        if state.librarian is None:
            body = HealthResponse(status="unavailable", index_loaded=False, error=state.startup_error)
            return JSONResponse(body.model_dump(), status_code=503)

        librarian: Librarian = state.librarian
        qdrant = state.health_check(librarian)
        body = HealthResponse(
            status="ok" if qdrant == "ok" else "unavailable",
            index_loaded=True,
            chunks=len(librarian.retriever.chunks),
            qdrant=qdrant,
            rerank=librarian.retriever.reranker is not None,
            model=librarian.model,
        )
        return JSONResponse(body.model_dump(), status_code=200 if qdrant == "ok" else 503)

    # Plain `def`, not `async def`: Librarian.ask() blocks (embedding call,
    # CPU reranking, Gemini call), so FastAPI runs it in its threadpool
    # instead of stalling the event loop for every other request.
    @app.post("/ask", response_model=AskResponse)
    def ask(body: AskRequest, request: Request) -> Any:
        librarian = get_librarian(request)
        try:
            result = librarian.ask(body.question, top_k=body.top_k)
        except Exception:
            # Upstream failures (OpenAI, Qdrant, Gemini after its retries) are
            # logged in full here but not echoed to the client.
            logger.exception("ask failed")
            raise HTTPException(502, "Answer generation failed upstream; try again shortly.")
        return result.to_dict()

    return app


app = create_app()
