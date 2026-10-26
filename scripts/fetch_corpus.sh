#!/usr/bin/env bash
# Fetch the OWASP Cheat Sheet Series corpus at the exact commit this project
# was built against, so the eval dataset's source files/passages stay valid.
set -euo pipefail

REPO_URL="https://github.com/OWASP/CheatSheetSeries.git"
PINNED_COMMIT="a5fbb7f886c02e3418e17f5525874a868cca49e4"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TARGET_DIR="$PROJECT_ROOT/corpus/CheatSheetSeries"

if [ -d "$TARGET_DIR/.git" ]; then
  echo "corpus already present at $TARGET_DIR"
else
  mkdir -p "$PROJECT_ROOT/corpus"
  git clone --depth 1 "$REPO_URL" "$TARGET_DIR"
fi

cd "$TARGET_DIR"
if ! git cat-file -e "$PINNED_COMMIT" 2>/dev/null; then
  git fetch --depth 1 origin "$PINNED_COMMIT"
fi
git checkout --quiet "$PINNED_COMMIT"

ACTUAL_COMMIT="$(git rev-parse HEAD)"
if [ "$ACTUAL_COMMIT" != "$PINNED_COMMIT" ]; then
  echo "ERROR: checked out $ACTUAL_COMMIT, expected $PINNED_COMMIT" >&2
  exit 1
fi

echo "corpus ready at $TARGET_DIR (commit $ACTUAL_COMMIT)"
echo "the eval dataset only uses files under cheatsheets/*.md"
