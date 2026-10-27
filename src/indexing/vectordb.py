"""
Qdrant collection management: one collection per chunking config (e.g.
"chunks_heading_mt512"), cosine distance, full chunk metadata as payload.

Point ids are derived deterministically from chunk_id (uuid5), so building
the same config twice upserts in place instead of duplicating points.
"""
from __future__ import annotations

import os
import uuid

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

# Any fixed UUID works here; it just needs to be the same every run so the
# same chunk_id always maps to the same point id.
_ID_NAMESPACE = uuid.UUID("c6f54b2f-3c3a-4a7b-8f2e-9e2a6b6e5a2e")

# Payload fields copied onto every point, straight from the chunk dict
# (see chunk.py's _make_chunk). "text" and "embed_text" aren't duplicated
# into the payload — chunks.jsonl is still the source of truth for those;
# the payload only needs enough to answer searches and filters, and callers
# look chunk_id up against chunks.jsonl for the actual text.
PAYLOAD_FIELDS = [
    "chunk_id",
    "source_file",
    "title",
    "section_path",
    "commit",
    "date",
    "n_tokens",
    "has_code",
    "has_table",
]

UPSERT_BATCH_SIZE = 256


def get_client() -> QdrantClient:
    url = os.environ.get("QDRANT_URL", "http://localhost:6333")
    # Default timeout is a few seconds, too short for a bulk-upsert request
    # carrying hundreds of 1536-dim vectors; we also batch (UPSERT_BATCH_SIZE)
    # to keep any single request reasonably sized in the first place.
    return QdrantClient(url=url, timeout=60)


def collection_name(strategy: str, max_tokens: int, overlap: int) -> str:
    if strategy == "heading":
        return f"chunks_heading_mt{max_tokens}"
    return f"chunks_fixed_mt{max_tokens}_ov{overlap}"


def point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(_ID_NAMESPACE, chunk_id))


def ensure_collection(client: QdrantClient, name: str, vector_size: int) -> None:
    """(Re)create the collection fresh with the right vector size, then add
    payload indexes for the fields we filter on."""
    client.recreate_collection(
        collection_name=name,
        vectors_config=qm.VectorParams(size=vector_size, distance=qm.Distance.COSINE),
    )
    client.create_payload_index(name, field_name="source_file", field_schema=qm.PayloadSchemaType.KEYWORD)
    client.create_payload_index(name, field_name="has_code", field_schema=qm.PayloadSchemaType.BOOL)
    client.create_payload_index(name, field_name="has_table", field_schema=qm.PayloadSchemaType.BOOL)


def upsert_chunks(client: QdrantClient, name: str, chunks: list[dict], vectors: list[list[float]]) -> None:
    points = [
        qm.PointStruct(
            id=point_id(chunk["chunk_id"]),
            vector=vector,
            payload={field: chunk[field] for field in PAYLOAD_FIELDS},
        )
        for chunk, vector in zip(chunks, vectors)
    ]
    # Batched: a config can be thousands of 1536-dim vectors, and sending
    # them all as one request is what caused the timeout that led to this.
    for i in range(0, len(points), UPSERT_BATCH_SIZE):
        client.upsert(collection_name=name, points=points[i : i + UPSERT_BATCH_SIZE])


def vector_search(
    client: QdrantClient,
    name: str,
    query_vector: list[float],
    k: int = 10,
    filters: qm.Filter | None = None,
) -> list[dict]:
    """Returns the top-k payloads with a '_score' field. For manual testing
    and the chunking experiment — not the real hybrid retriever (Step 4)."""
    response = client.query_points(
        collection_name=name,
        query=query_vector,
        query_filter=filters,
        limit=k,
        with_payload=True,
    )
    return [{**point.payload, "_score": point.score} for point in response.points]
