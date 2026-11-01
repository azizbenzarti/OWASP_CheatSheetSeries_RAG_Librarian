#!/usr/bin/env bash
# Container entrypoint (see Dockerfile / docker-compose.yml).
#
# With ENSURE_INDEX=1 (the api service), before starting the command it:
#   1. waits for Qdrant at $QDRANT_URL;
#   2. checks the chosen index (heading / 512 / overlap 0 / min 20) exists both
#      on disk (data/index/, a volume) and in Qdrant with the same chunk count;
#   3. if not, fetches the pinned corpus and builds it -- only on first start
#      or after a volume was wiped. Embeddings are disk-cached (data/cache/,
#      also a volume) and upserts are idempotent, so a rebuild is cheap.
# Without it (the ui service) it just runs the command.
set -euo pipefail
cd /app

# An empty value in .env (e.g. "RERANKER_MODEL=") would be passed as "", not
# "unset"; drop such optional vars so the code's defaults apply.
for var in RERANKER_MODEL RERANKER_MAX_LENGTH EMBEDDING_BASE_URL EMBEDDING_COST_PER_1M_TOKENS GEMINI_MODEL GEMINI_TEMPERATURE GENERATOR OPENAI_GENERATION_MODEL; do
  if [ -z "${!var:-}" ]; then unset "$var"; fi
done

if [ "${ENSURE_INDEX:-0}" = "1" ]; then
  QDRANT_URL="${QDRANT_URL:-http://qdrant:6333}"
  echo "[entrypoint] waiting for Qdrant at ${QDRANT_URL} ..."
  for i in $(seq 1 60); do
    if curl -sf "${QDRANT_URL}/healthz" > /dev/null; then break; fi
    if [ "$i" = 60 ]; then echo "[entrypoint] ERROR: Qdrant not reachable after 120s" >&2; exit 1; fi
    sleep 2
  done
  echo "[entrypoint] Qdrant is up"

  STRATEGY=heading MAX_TOKENS=512 OVERLAP=0 MIN_TOKENS=20
  INDEX_DIR="data/index/${STRATEGY}_mt${MAX_TOKENS}_min${MIN_TOKENS}"

  # Exit 0 = index on disk and in Qdrant, in sync. Never prints any secret.
  if python - "$INDEX_DIR" <<'PY'
import json, sys
from pathlib import Path
from src.indexing.vectordb import get_client
d = Path(sys.argv[1])
if not (d / "chunks.jsonl").is_file() or not (d / "manifest.json").is_file():
    sys.exit("no index on disk")
manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
n_chunks = sum(1 for _ in (d / "chunks.jsonl").open(encoding="utf-8"))
try:
    n_points = get_client().get_collection(manifest["qdrant_collection"]).points_count
except Exception:
    sys.exit("Qdrant collection missing")
if n_points != n_chunks:
    sys.exit(f"out of sync: {n_points} points vs {n_chunks} chunks")
PY
  then
    echo "[entrypoint] index ${INDEX_DIR} present and in sync with Qdrant"
  else
    echo "[entrypoint] building index ${INDEX_DIR} (first start; takes a few minutes, costs ~\$0.02 of embeddings)"
    : "${EMBEDDING_API_KEY:?EMBEDDING_API_KEY must be set in .env to build the index}"
    : "${EMBEDDING_MODEL:?EMBEDDING_MODEL must be set in .env to build the index}"
    bash scripts/fetch_corpus.sh
    python -m src.indexing.build --strategy "$STRATEGY" --max-tokens "$MAX_TOKENS" \
      --overlap "$OVERLAP" --min-tokens "$MIN_TOKENS" > /tmp/build.log
    echo "[entrypoint] index built"
  fi
fi

exec "$@"
