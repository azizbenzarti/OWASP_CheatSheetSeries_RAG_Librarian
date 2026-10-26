# The Librarian — RAG over the OWASP Cheat Sheet Series

CS496 AI Engineering, Project 2. A retrieval-augmented service that answers
application-security questions from the OWASP Cheat Sheet Series, with
citations, and says "I don't know" when the corpus doesn't cover something.

## Corpus

[OWASP Cheat Sheet Series](https://github.com/OWASP/CheatSheetSeries),
licensed [CC BY-SA 4.0](https://github.com/OWASP/CheatSheetSeries/blob/master/LICENSE.md).
Pinned at commit `a5fbb7f886c02e3418e17f5525874a868cca49e4`. The corpus for
this project is only the files under `cheatsheets/*.md` (137 files) —
`cheatsheets_draft/`, the `Index*.md` files, and repo tooling files are
excluded.

### Fetching the corpus

```bash
scripts/fetch_corpus.sh
```

Clones (or reuses) `corpus/CheatSheetSeries` and checks out the pinned
commit above, so the eval dataset's recorded source files/passages stay
valid. `corpus/` is gitignored — it is not committed to this repo.

## Status

The evaluation dataset has been human-reviewed. **`data/eval.json`** is the
final set — 119 questions, every row `verified: true` — and is what the
retrieval/generation eval harness should use going forward.

`data/eval_draft.json` (the original 120 LLM-drafted questions, pre-review)
is kept as-is for audit purposes; it is not used by anything downstream.
`data/REVIEW_STATS.md` has the draft-vs-final diff (what was kept, edited,
or deleted, and why). `data/SCHEMA.md` documents the shared format.

Quality-check freezing and the dev/test split have not happened yet — that's
the next step, not done here.
