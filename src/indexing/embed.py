"""
Embeddings from a hosted, OpenAI-compatible API, with a local disk cache so
re-running the chunking experiment across configs never pays twice to embed
the same (model, text) pair.

Required env vars (see .env.example): EMBEDDING_API_KEY, EMBEDDING_MODEL.
Optional: EMBEDDING_BASE_URL, EMBEDDING_COST_PER_1M_TOKENS.

NEVER print, log, or return the API key itself from this module.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import tiktoken
from dotenv import load_dotenv
from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = ROOT / "data" / "cache" / "embeddings"

# OpenAI's current embedding models accept up to 8191 input tokens each.
# We don't know the exact limit for an arbitrary OpenAI-compatible model
# ahead of time, so this is used as the default — pass max_input_tokens
# explicitly to embed_texts() if the professor's model differs.
DEFAULT_MAX_INPUT_TOKENS = 8191
DEFAULT_BATCH_SIZE = 100
MAX_RETRIES = 5


class EmbeddingConfig:
    """Reads and validates the embedding environment once, so every caller
    fails the same clear way instead of each needing its own os.environ
    checks scattered around."""

    def __init__(self) -> None:
        load_dotenv()
        self.api_key = os.environ.get("EMBEDDING_API_KEY")
        self.model = os.environ.get("EMBEDDING_MODEL")
        self.base_url = os.environ.get("EMBEDDING_BASE_URL") or None
        cost = os.environ.get("EMBEDDING_COST_PER_1M_TOKENS")
        self.cost_per_1m_tokens = float(cost) if cost else None

        if not self.api_key:
            raise RuntimeError("EMBEDDING_API_KEY is not set. Add it to .env (see .env.example).")
        if not self.model:
            raise RuntimeError(
                "EMBEDDING_MODEL is not set. This isn't something to guess at — "
                "put the exact model name in .env (see .env.example) and try again."
            )

    def client(self) -> OpenAI:
        kwargs = {"api_key": self.api_key, "max_retries": 0}  # we do our own retry loop below
        if self.base_url:
            kwargs["base_url"] = self.base_url
        return OpenAI(**kwargs)


def _encoding_for(model: str):
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def _cache_key(model: str, text: str) -> str:
    return hashlib.sha256(f"{model}\n{text}".encode("utf-8")).hexdigest()


def _cache_path(key: str) -> Path:
    # Two-level fan-out (data/cache/embeddings/ab/ab12...json) so the
    # directory doesn't end up with tens of thousands of files side by side.
    return CACHE_DIR / key[:2] / f"{key}.json"


def _cache_get(key: str) -> list[float] | None:
    path = _cache_path(key)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))["vector"]
    return None


def _cache_put(key: str, model: str, vector: list[float]) -> None:
    path = _cache_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"model": model, "vector": vector}), encoding="utf-8")


class EmbeddingStats:
    """Accumulates what build.py / chunking_experiment.py need for
    manifest.json: how many tokens actually got sent to the API (cache hits
    are free) and the resulting estimated cost."""

    def __init__(self, cost_per_1m_tokens: float | None) -> None:
        self.total_tokens = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.cost_per_1m_tokens = cost_per_1m_tokens

    def record(self, n_tokens: int, cached: bool) -> None:
        if cached:
            self.cache_hits += 1
        else:
            self.cache_misses += 1
            self.total_tokens += n_tokens

    def as_dict(self) -> dict:
        cost = (
            round(self.total_tokens / 1_000_000 * self.cost_per_1m_tokens, 4)
            if self.cost_per_1m_tokens is not None
            else None
        )
        return {
            "embedding_tokens": self.total_tokens,
            "embedding_cache_hits": self.cache_hits,
            "embedding_cache_misses": self.cache_misses,
            "embedding_cost_usd": cost,  # null if EMBEDDING_COST_PER_1M_TOKENS wasn't set
        }


def embed_texts(
    texts: list[str],
    config: EmbeddingConfig,
    stats: EmbeddingStats | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_input_tokens: int = DEFAULT_MAX_INPUT_TOKENS,
    show_progress: bool = True,
) -> list[list[float]]:
    """Embed a list of texts, serving whatever's already cached for this
    exact (model, text) pair and only calling the API for the rest."""
    encoding = _encoding_for(config.model)
    stats = stats if stats is not None else EmbeddingStats(config.cost_per_1m_tokens)

    keys = [_cache_key(config.model, t) for t in texts]
    results: list[list[float] | None] = [None] * len(texts)
    to_fetch_idx: list[int] = []

    for i, (text, key) in enumerate(zip(texts, keys)):
        n_tokens = len(encoding.encode(text))
        assert n_tokens <= max_input_tokens, (
            f"embed_text at index {i} is {n_tokens} tokens, over the "
            f"{max_input_tokens}-token input limit for model {config.model!r}"
        )
        cached = _cache_get(key)
        if cached is not None:
            results[i] = cached
        else:
            to_fetch_idx.append(i)
        stats.record(n_tokens, cached=cached is not None)

    if to_fetch_idx:
        client = config.client()
        batches = [to_fetch_idx[i : i + batch_size] for i in range(0, len(to_fetch_idx), batch_size)]
        for batch_idx in tqdm(batches, desc=f"embedding ({config.model})", disable=not show_progress):
            batch_texts = [texts[i] for i in batch_idx]
            vectors = _embed_batch_with_retry(client, config.model, batch_texts)
            for i, vector in zip(batch_idx, vectors):
                results[i] = vector
                _cache_put(keys[i], config.model, vector)

    return results  # type: ignore[return-value]  # every slot was filled above


def _embed_batch_with_retry(client: OpenAI, model: str, texts: list[str]) -> list[list[float]]:
    delay = 1.0
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.embeddings.create(model=model, input=texts)
            return [item.embedding for item in response.data]
        except (RateLimitError, APITimeoutError, APIConnectionError):
            if attempt == MAX_RETRIES:
                raise
            time.sleep(delay)
            delay *= 2
