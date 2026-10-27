# Design notes

## Index choice

Embeddings come from a hosted, OpenAI-compatible API (`src/indexing/embed.py`)
and live in Qdrant (`docker-compose.yml`, `src/indexing/vectordb.py`). BM25
stays local, in Python, over the same chunks. `chunks.jsonl` + `manifest.json`
are still the source of truth for chunk text and build stats; there's no
local `embeddings.npy` anymore.

**Why Qdrant.** Once embeddings come from an external API rather than a
model we run ourselves, "just load a NumPy array" stops covering what we
actually need:

- **Metadata filtering at query time.** We create payload indexes on
  `source_file`, `has_code`, and `has_table` so a search can be restricted
  (e.g. "only this cheat sheet" or "only chunks with a code example")
  without filtering a Python list by hand after the fact.
- **Deployability.** The project ultimately needs to run as a service, not
  a notebook. Qdrant is a small, single-binary container we can run the
  same way in development and on the course's K3s cluster — same image,
  same `docker-compose.yml`-equivalent manifest, no code change between
  environments.
- **Persistence independent of any one process.** The index survives
  restarts of the Python process (and can be queried by more than one
  process) because it's a separate service with its own storage volume,
  not an in-memory array that only exists inside whichever script loaded
  it.
- **Idempotent rebuilds.** Point ids are derived deterministically from
  each chunk's `chunk_id` (`uuid5`), so rebuilding a config re-upserts in
  place instead of duplicating points — safe to run the build repeatedly.

**Why BM25 stays separate, in Python.** BM25 doesn't need a service: `bm25s`
builds and queries a keyword index over ~1,000-4,000 chunks in well under a
second, entirely in-process, with no network round trip. Moving it into
Qdrant (or any other service) would add a dependency and a hop for no
benefit at this scale — the two retrieval methods are combined later (Step
4's hybrid retriever), but there's no reason for both to live in the same
service just because they'll eventually be combined.

**Embedding model and its limits.** The model is read from `EMBEDDING_MODEL`
in `.env` — there's no hardcoded default, specifically so this never
silently uses the wrong model. Confirmed via a 5-chunk smoke test before the
full build: **`text-embedding-3-small`**, **1536**-dimensional vectors,
**8191**-token input limit (OpenAI's published limit for the
`text-embedding-3-*` family; `DEFAULT_MAX_INPUT_TOKENS` in
`src/indexing/embed.py`). `src/indexing/embed.py` asserts no `embed_text`
exceeds that limit before sending it, and counts tokens with `tiktoken`
(falling back to the `cl100k_base` encoding for any model name `tiktoken`
doesn't recognize directly — an approximation worth knowing about if a
config's `n_tokens` looks slightly off from the API's own count).

**Embedding cost.** Every build records `embedding_tokens`,
`embedding_cache_hits`/`embedding_cache_misses`, and (if
`EMBEDDING_COST_PER_1M_TOKENS` is set in `.env`) `embedding_cost_usd` in
`manifest.json`. The disk cache (`data/cache/embeddings/`, keyed by
`sha256(model + embed_text)`) means only the first build of a given
(model, text) pair is ever charged for — re-running an experiment sweep or
rebuilding the same config again is free.

Full-corpus token totals for the 7 configs swept in
`eval/results/chunking_dev.csv` (each is independent — embedding the whole
corpus fresh under that config's chunk boundaries):

| config | tokens |
|---|---|
| heading_mt256_min20 | 591,132 |
| heading_mt512_min20 (chosen config — see `eval/results/chunking_dev.md`) | 577,562 |
| heading_mt1024_min20 | 573,836 |
| fixed_mt256_ov0 | 569,972 |
| fixed_mt256_ov38 | 806,979 |
| fixed_mt512_ov0 | 548,247 |
| fixed_mt512_ov77 | 743,715 |

`EMBEDDING_COST_PER_1M_TOKENS` isn't set for this account, so
`embedding_cost_usd` is empty in the results rather than guessed. For scale,
OpenAI's published public rate for `text-embedding-3-small` is $0.02 per 1M
tokens — at that rate the chosen config (577,562 tokens) would cost about
**$0.012** to embed the whole corpus from scratch, and all 7 configs
combined (~4.4M tokens, since each is a from-scratch embed of the full
corpus under different chunk boundaries) about **$0.088**. This is a public
reference figure, not a confirmed rate for this specific key — set
`EMBEDDING_COST_PER_1M_TOKENS` in `.env` once the actual billing rate is
known to get a real number in `manifest.json`.

## Known failure cases

**Inline fence parsed as a block-fence opener, silently dropping the rest
of a file.** `Authorization_Cheat_Sheet.md` line 91 is
`` ```https://mybank.com/accountTransactions?acct_id=901``` `` — a
single-line, self-closing inline code span (three backticks used instead of
one, likely so the URL could contain a literal backtick-free structure
without stuffing). The original parser (`load.py`) matched any line
starting with `` ``` `` as a multi-line fence *opener*, then scanned forward
for a line starting with `` ``` `` to close it. Since this was the only
line in the entire file starting with `` ``` ``, no closing line ever
existed, so the scan ran to the end of the file and swallowed everything
from line 91 onward into one bogus "code" block — silently dropping **6
real sections** (`Enforce Authorization Checks on Static Resources`,
`Verify that Authorization Checks are Performed in the Right Location`,
`Exit Safely when Authorization Checks Fail`, `Implement Appropriate
Logging`, `Create Unit and Integration Test Cases for Authorization Logic`,
`References`) from parsing — they were never even wrong, they just stopped
existing as far as the chunker was concerned.

*How it was found:* the `eval/check_index.py` "no chunks with an odd number
of fences" check, added for this step, flagged one chunk with an odd fence
count. Direct inspection of the parsed tree for that file showed the
section ended abruptly instead of continuing through the document's
remaining sections, and `grep -n '^```' Authorization_Cheat_Sheet.md` showed
exactly one match in the whole file — confirming the fence was never
closed because there was nothing to close it with.

*The fix:* `load.py`'s fence detection now checks whether the fence marker
also appears later on the *same* line before treating it as a block-fence
opener; if so, it's left as plain text instead. A genuine fence-opener line
is just the marker plus an optional language tag — it never contains a
second copy of the marker. Verified corpus-wide afterward: zero remaining
odd-fence chunks across all 137 sheets, and the recovered 6 sections now
parse and chunk normally. Confirmed isolated to this one line (`grep -lE
'^```.+```$' cheatsheets/*.md` matches only this file).

**q021: passage spans a sub-heading boundary.** The dev question's
`source_passage` (in `Unvalidated_Redirects_and_Forwards_Cheat_Sheet.md`,
section "Preventing Unvalidated Redirects and Forwards") runs from a bullet
list directly into the following `### Validating URLs` sub-heading's own
paragraph. Since the heading strategy chunks per leaf section, that
sub-heading starts a new chunk — no `max_tokens` setting can produce a
single chunk containing the whole passage, because the split happens at a
real heading in the source document, not at a token-count boundary a config
could widen. `eval/check_index.py`'s "dev passage coverage" check (our
recall ceiling) correctly flags this as unfixable by chunking-parameter
changes; it's a property of where the review process drew this particular
passage's boundary, not a chunker defect. Confirmed via the chunking
experiment: q021 misses in every one of the 7 configs and both retrieval
methods — the only question that does.
