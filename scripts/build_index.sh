#!/usr/bin/env bash
# Build the chosen chunking config's index, from a clean clone:
#   docker compose up -d           # starts Qdrant (see README)
#   cp .env.example .env           # then fill in EMBEDDING_API_KEY / EMBEDDING_MODEL
#   scripts/fetch_corpus.sh
#   scripts/build_index.sh
#
# This script does NOT start Qdrant itself -- it only checks that it's
# already reachable, and that the required .env variables are set, then
# builds the chosen config (see eval/results/chunking_dev.md + docs/design.md
# for how it was picked). Override any of the config values via env vars,
# e.g.:
#   STRATEGY=fixed MAX_TOKENS=256 scripts/build_index.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
cd "$ROOT"

if [ ! -d corpus/CheatSheetSeries/.git ]; then
  echo "corpus not found, fetching..."
  scripts/fetch_corpus.sh
fi

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt

QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
if ! curl -sf "${QDRANT_URL}/healthz" > /dev/null; then
  echo "ERROR: Qdrant isn't reachable at ${QDRANT_URL}. Start it first:" >&2
  echo "  docker compose up -d" >&2
  exit 1
fi

if [ ! -f .env ]; then
  echo "ERROR: .env not found. Copy .env.example to .env and fill it in first." >&2
  exit 1
fi
# Check required variable NAMES are present without ever printing values.
for var in EMBEDDING_API_KEY EMBEDDING_MODEL; do
  if ! grep -qE "^${var}=.+" .env; then
    echo "ERROR: ${var} is not set in .env. See .env.example." >&2
    exit 1
  fi
done

STRATEGY="${STRATEGY:-heading}"
MAX_TOKENS="${MAX_TOKENS:-512}"
OVERLAP="${OVERLAP:-0}"
MIN_TOKENS="${MIN_TOKENS:-20}"

python3 -m src.indexing.build \
  --strategy "$STRATEGY" \
  --max-tokens "$MAX_TOKENS" \
  --overlap "$OVERLAP" \
  --min-tokens "$MIN_TOKENS"
