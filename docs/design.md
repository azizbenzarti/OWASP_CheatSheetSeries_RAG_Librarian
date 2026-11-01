# Design notes

See `docs/architecture.png` (editable source: `docs/architecture.svg`;
also shown in the README) for how the pieces discussed below fit together,
offline and online.

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
- **Deployability.** The project runs as a service, not a notebook. Qdrant is
  a small, single container that runs the same way in development and in
  deployment: one `docker-compose.yml` with Streamlit, FastAPI and Qdrant,
  no code change between environments.
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

## Retrieval

`src/retrieval/retriever.py` answers a question from the already-built
index (Qdrant + BM25); it never re-chunks or re-embeds. Three base modes —
`bm25`, `vector`, `hybrid` — plus reranking, which isn't a fourth `mode`
string but a `Reranker` callable attached to the `Retriever` at
construction time (see `src/retrieval/reranker.py`); the ablation table
below calls that combination "hybrid+rerank."

**Hybrid: Reciprocal Rank Fusion (RRF), k=60.** `rrf_fuse()` scores each
chunk as `sum over retrievers of 1 / (k + rank)`, using only each
retriever's *rank* of a chunk, never its raw score. BM25 scores and cosine
similarities live on entirely different, incomparable scales (BM25 is
unbounded and corpus-dependent; cosine is bounded [-1, 1] but its useful
range for this embedding model clusters much narrower) — fusing them by
normalizing and adding would mean picking an arbitrary, unprincipled
weighting between two numbers that don't mean the same thing. Rank-based
fusion sidesteps that entirely: a chunk that both retrievers agree is
relevant (even at different ranks) consistently outscores a chunk only one
retriever found, with no scale-matching needed. k=60 is the standard
constant from the original RRF paper (Cormack et al., 2009); it damps how
much a #1-vs-#2 placement matters relative to a #40-vs-#41 one, so the fused
ranking isn't overly sensitive to noise at the very top.

**Candidate depth: 50 per retriever, 20 to the reranker, top 5 returned.**
`candidates=50` (`DEFAULT_CANDIDATES`) is how deep vector search and BM25
each look *before* RRF fusion — deep enough that a chunk only one method
ranks well still has a real chance of surviving fusion, without fetching
so much that fusion and (when attached) reranking have to wade through
near-irrelevant tail results. When a reranker is attached, the same
`candidates` parameter controls how many *fused* candidates it receives
(`candidates=20` is passed explicitly for this) — reranking is
`O(candidates)` cross-encoder forward passes, so 20 is a deliberate
quality/latency trade (see below), not the retrieval-stage 50. The
production default (CLI, and `format_context` for generation) returns the
top 5 — enough chunks for the generator to synthesize an answer with
citations without blowing up the prompt, while the reranker has already
done the work of making sure those 5 are the *best* 5 of the candidate
pool, not just whichever 5 happened to fuse highest.

**Reranker model and its latency cost.** Default `BAAI/bge-reranker-base`,
via `RERANKER_MODEL` in `.env`. A cross-encoder scores a (query, chunk)
pair jointly in one forward pass — the model attends across both texts at
once — which is why it's more accurate than the bi-encoder cosine
similarity vector search uses (which embeds query and chunk independently
and compares after the fact), and also why it doesn't scale to the whole
corpus: it's only run over the hybrid stage's top 20. Measured on this
machine (CPU, no GPU): reranking 20 candidates with `bge-reranker-base`
costs **~7-8 seconds per query** — by far the dominant cost in the
hybrid+rerank pipeline (vector search ~130ms, BM25 ~1-3ms). We also ran the
ablation with `cross-encoder/ms-marco-MiniLM-L-6-v2` (6-layer MiniLM, ~22M
params vs. `bge-reranker-base`'s ~278M) specifically because that latency
is too slow for an interactive query path; see the ablation table for the
quality it gives up in exchange, and `optimisation.md` (Week 8) for
whether that trade is worth taking in production.

**Why the reranker runs in-process, not as a hosted service.** For the first
version the cross-encoder is loaded inside the FastAPI process with
`sentence-transformers`:

- **Free:** no extra API key and no per-request cost, so the cost model only
  covers embeddings (OpenAI) and generation (Gemini).
- **No network hop:** no added latency or third-party rate limits on the
  reranking step.
- **Simple to explain:** a few lines of code, no extra service to deploy.

Trade-offs: CPU inference is the slowest step in the pipeline (see the
ablation table), and torch plus the model weights make the API image larger.
Alternatives considered: a self-hosted reranker container in the same Docker
Compose stack (e.g. Hugging Face Text Embeddings Inference), a managed
Hugging Face Inference Endpoint (paid per hour), or a rerank API (Cohere,
Jina, Voyage). We revisit this in Week 8 if reranker latency is the main
bottleneck.

**Metadata filters.** `filters={"source_file": ..., "has_code": True,
"has_table": True}`, applied identically to both retrievers (Qdrant via
payload indexes created in `vectordb.py`; BM25 in Python, since `bm25s` has
no native filtering — see `matches_filters()`). `source_file` also accepts
a list, for "search within these N cheat sheets."

### Ablation (dev set)

See `eval/results/retrieval_dev.md` / `.csv` for the full table (also
reproduced below) and `eval/results/retrieval_dev_failures.md` for the
per-question diagnostics. Generated by `eval/retrieval_eval.py` against
`data/dev.jsonl` only.

**Sample size.** 26 answerable dev questions means one question is worth
~3.8 percentage points of recall. None of the per-mode differences below
should be read as a confident winner unless they're several questions'
worth of margin — see the table for exact numbers before drawing
conclusions.

| mode | recall@1 | recall@5 | recall@10 | MRR | p50 latency | p95 latency |
|---|---|---|---|---|---|---|
| bm25 | 0.231 | 0.731 | 0.808 | 0.419 | 0.6ms | 1.0ms |
| vector | 0.423 | 0.731 | 0.769 | 0.560 | 10.1ms | 13.2ms |
| hybrid (RRF) | **0.500** | 0.769 | 0.846 | **0.632** | 8.6ms | 10.7ms |
| hybrid+rerank (bge-reranker-base) | 0.346 | **0.885** | **0.962** | 0.564 | 8.06s | 8.21s |
| hybrid+rerank (ms-marco-MiniLM-L-6-v2) | 0.346 | 0.808 | 0.923 | 0.553 | 1.52s | 1.62s |

What this shows:

- **Hybrid beats both of its inputs.** RRF fusion's recall@1 (0.500) clears
  vector (0.423) and bm25 (0.231) individually, and its MRR (0.632) is the
  best of any row — confirmation that combining the two retrieval methods
  is worth the (small) extra latency, not just a theoretical nicety.
- **Reranking trades recall@1 for recall@5/@10 — and that trade is real,
  not noise.** hybrid+rerank's recall@5 (0.885) and recall@10 (0.962) beat
  plain hybrid by 3-4 questions' worth of margin (well past the ~3.8-point
  noise floor), but its recall@1 (0.346) is *worse* than plain hybrid's by
  4 questions. The regression check #3 above is this exact effect caught
  on one query: reranking can correctly promote more *total* right answers
  into view while occasionally bumping the single best one down. Worth
  knowing before assuming "add a reranker" is a strict win — it depends
  whether the generation step only looks at chunk 1 or synthesizes across
  all 5.
- **The smaller reranker is a reasonable Week-8 candidate.**
  `ms-marco-MiniLM-L-6-v2` gets within ~2 points of `bge-reranker-base` on
  recall@5/@10 (both comfortably inside noise-floor-or-just-outside-it
  territory) at **~5.3x lower latency** (1.52s vs. 8.06s median). Given
  reranking is already the dominant cost in the pipeline by two orders of
  magnitude, this is the first place to look when optimizing latency.
- **BM25 alone is a surprisingly strong recall@10 floor** (0.808, beating
  vector's 0.769) despite scoring worst on recall@1 and MRR — it finds the
  right chunk somewhere in its list more often than it ranks it first.
  Consistent with the chunking-stage ablation (`eval/results/chunking_dev.md`).

### "I don't know" threshold

**Vector cosine score is not usable for this gate.** The unanswerable
group's scores (0.522-0.622) sit *inside* the answerable group's range
(0.458-0.748) — the best achievable threshold catches 0 of 4 unanswerable
questions without also rejecting answerable ones. Cosine similarity
apparently isn't discriminating "no real answer in the corpus" from "a
real, slightly-less-perfect match" for this dev set.

**Reranker score separates much better**, though still not cleanly: at a
threshold of 0.252 it catches **4/4 unanswerable questions**, at the cost
of wrongly rejecting **1/26 answerable questions**. The reason it's not
"clean" (`max(unanswerable) < min(answerable)`) is exactly that one
answerable question, whose top reranked score (0.113) is lower than every
unanswerable question's top score.

**Decision: don't ship this as the refusal mechanism, for now.** Four
unanswerable dev questions is too small a sample to trust a threshold
tuned against it to generalize — "catches 4/4" could easily become "catches
2/4" on a slightly different unanswerable question, and we have no way to
tell from this data alone. Per the brief: leave "I don't know" to the
generation step, which has the full answer (not just a retrieval score) to
judge faithfulness from. The reranker threshold (~0.25, reranker mode only)
is kept available as a cheap backup gate — skip generation entirely when
even reranking can't find anything plausible — but it is not the primary
mechanism, and it has not been tuned against `data/test.jsonl`.

### Reranker regression checks (manual, not dev-set)

Three hand-picked queries, checked before/after reranking (`bge-reranker-base`
and `ms-marco-MiniLM-L-6-v2` agreed on ordering for all three — reported
once). These are sanity checks for a human to read, not tuned against: no
retrieval parameter was changed to make any of them pass.

**1. "how many bcrypt rounds should I use?"** — expected: the main bcrypt
section (work factor) in the top 3.

- Before (hybrid): 1. bcrypt > Input Limits of bcrypt — 2. bcrypt >
  Pre-Hashing Passwords with bcrypt — 3. Introduction
- After (hybrid+rerank): 1. bcrypt > Input Limits of bcrypt — 2. Ruby on
  Rails > Encryption — 3. Introduction

**PASS.** Note: the heading `bcrypt > Input Limits of bcrypt` is
misleading on its own — `bcrypt`'s own intro paragraph (the one that
actually says *"The work factor should be as large as verification server
performance will allow, with a minimum of 10"*) has no sub-heading of its
own, so the chunker's push-down rule (see "Index choice" above) folds it
into the first child section, `Input Limits of bcrypt`. The content is
exactly what was expected; only the label looks odd.

**2. "run docker container as non-root"** — expected: "RULE #2 - Set a
user" in the top 3.

- Before (hybrid): 1. Rule #11 - Run Docker in rootless mode — 2. Podman
  as an alternative to Docker — 3. RULE #8 - Set filesystem/volumes
  read-only
- After (hybrid+rerank): 1. Rule #11 - Run Docker in rootless mode — 2.
  Podman as an alternative to Docker — 3. Kubernetes > security context
  example

**FAIL** (both before and after; not tuned to fix). RULE #2 sits at rank 4
in the hybrid ranking — just outside top 3 — and reranking doesn't pull it
in either. Its text (`docker run -u`, `useradd`, "unprivileged user") is
genuinely on-topic but never uses the words "root" or "non-root," while
Rule #11 and Podman both do; both BM25/vector term-and-meaning overlap and
the cross-encoder lean toward the chunks that share the query's actual
vocabulary. A real gap, not a bug — logged here rather than papered over.

**3. "csrf protection for single page apps"** — expected: Web Frontend
Security › Use CSRF Protection stays at #1.

- Before (hybrid): 1. Web Frontend Security > Use CSRF Protection — 2.
  Laravel > CSRF — 3. Ruby on Rails > CSRF
- After (hybrid+rerank): 1. Laravel > CSRF — 2. CSRF Prevention > Built-In
  Or Existing CSRF Implementations — 3. CSRF Prevention > Custom Headers
  and CORS

**FAIL.** Reranking moved the expected #1 result out of the top 3 entirely.
Both cross-encoder models agreed on this reordering, so it isn't one
model's quirk. Our reading: `bge-reranker-base` and `ms-marco-MiniLM-L-6-v2`
both reward chunks whose text is densely, specifically about "CSRF" (the
Laravel and CSRF-Prevention-sheet chunks are short and CSRF-focused
end-to-end) over a chunk that mentions CSRF protection as one bullet inside
a broader "Server-Side" security checklist (Web Frontend Security's
chunk) — even though the broader chunk was the better *hybrid* match. This
is a real reranker behavior worth knowing about before trusting
hybrid+rerank blindly: it can demote a correct, broadly-relevant chunk in
favor of a narrower, keyword-dense one.

### Retrieval failure cases

Full per-question detail in `eval/results/retrieval_dev_failures.md`.
Headline: **zero questions where hybrid+rerank misses but another mode
hits** — reranking never uniquely loses to a simpler mode on this dev set.
Exactly **one question every mode misses**:

- **q021** — known issue, not a retriever bug (passage spans a sub-heading
  boundary; see "Known failure cases" above). Every mode's top-3 are all
  plausible, on-topic chunks from the right cheat sheet — the retriever is
  behaving reasonably, it just can't produce a chunk containing text that
  no single chunk contains.

**q109 is *not* a universal miss** — a genuinely interesting result.
bm25/vector/hybrid all miss it (its primary passage is a generic
AI-agent intro that never says "MCP" — see the earlier write-up), and so
does `ms-marco-MiniLM-L-6-v2`, but `bge-reranker-base`'s hybrid+rerank
*does* find a hit, somewhere in its top 10 (not top 3). Reranking looks at
the full 20-candidate pool with per-pair attention rather than independent
embeddings, which apparently let it recognize relevance to a chunk that
ranked too low in the original hybrid fusion to be obvious — a concrete
example of reranking recovering something the earlier stages buried, not
just reordering the top few.
