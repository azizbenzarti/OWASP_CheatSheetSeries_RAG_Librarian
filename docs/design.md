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

A cross-encoder reranker scores a (query, chunk) pair jointly in one
forward pass — the model attends across both texts at once — which is why
it's more accurate than the bi-encoder cosine similarity vector search
uses (which embeds query and chunk independently and compares after the
fact), and also why it doesn't scale to the whole corpus: it's only run
over the hybrid stage's top 20.

### Reranker choice

**Decision: pending team review.** This section is the investigation and
our recommendation; `RERANKER_MODEL` in `.env` currently defaults to
MiniLM per that recommendation, but it's not final until the team signs
off.

**Candidates:** `cross-encoder/ms-marco-MiniLM-L-6-v2` (~22M params) vs.
`BAAI/bge-reranker-base` (~278M params, ~12x the parameters).

**Decision rule:** ship `bge-reranker-base` if its latency gets to about 1
second or less; otherwise ship MiniLM, keeping the other as the Week-8
comparison point.

**Sample size.** 26 answerable dev questions means 1 question ≈ 3.8
percentage points on any recall number below. Treat smaller deltas as
noise, not a winner.

**Measured on CPU, our deployment target** — no GPU is planned for this
service. On a GPU, `bge-reranker-base` would likely be fast enough (cross-
encoder inference over 20 short sequences is typically well under 100ms on
a GPU) to be the clear choice regardless of the numbers below; this
recommendation is specific to CPU deployment, and worth re-checking if the
deployment target ever changes.

**What changed to get here:** three levers, investigated and measured
separately after finding the reranker was passing raw chunk text with the
models' own 512-token default limit. Recall numbers below are always the
26-question dev-set average. Latency in the two per-lever tables
immediately below is instead **one representative query's 20 candidates,
timed 3x (minimum reported)** — necessary to isolate one variable at a
time without re-running the full (slow) 26-question sweep for every
combination — so those two tables' absolute latency numbers run a bit
higher than the 26-question pipeline average reported everywhere else in
this document (that one query's candidates happened to be longer than the
dev-set median). The "Combined" table further down is always the real,
26-question pipeline average — use that for any "is X fast enough"
judgment, not the two per-lever tables.

**1. Threads — no lever here.** `torch.get_num_threads()` defaults to 16 on
this machine (22 logical CPUs). Forcing it higher made things *slower*, not
faster:

| `torch.set_num_threads(n)` | latency (`bge-reranker-base`, 20 candidates) |
|---|---|
| 16 (default) | 7.7s |
| 22 (all cores) | 8.7s |
| 8 | 10.0s |
| 4 | 8.8s |

16 was already left alone; more threads adds scheduling/contention
overhead for a workload this size, not more throughput.

**2. max_length — the real lever.** Both models default to a 512-token
limit, but real hybrid-top-20 candidates run 103-641 tokens (mean 325,
median 339) — `sentence-transformers` pads a whole batch to its longest
member, so a few long outliers make every pair in the batch pay full-length
attention cost even when most are much shorter. Capping `max_length`
directly cuts that cost:

| max_length | `bge` latency | `bge` recall@5 / @10 | MiniLM latency | MiniLM recall@5 / @10 |
|---|---|---|---|---|
| 512 (default) | 7.9s | 0.885 / 0.962 | 0.79s | 0.808 / 0.923 |
| **384** | 6.0s (-24%) | 0.885 / 0.923 | **0.59s (-25%)** | 0.846 / 0.923 |
| 256 | 4.0s (-49%) | 0.692 / 0.769 | 0.36s (-55%) | 0.577 / 0.731 |

384 cuts latency by about a quarter on both models with recall@5/@10 flat
or better. 256 goes too far: for both models it visibly truncates real
content (13-14 of the 20 real candidates exceed 256 tokens) and recall@5
drops by 15-20 points — a real, measured quality loss, not noise.
**max_length=384 shipped** (`DEFAULT_MAX_LENGTH` in `reranker.py`).

**3. Text: raw chunk text vs. the embed_text breadcrumb — a quality lever,
not a speed one.** Reranking `f"{section_path}\n\n{text}"` (the same
breadcrumb the embedding model sees) instead of bare `chunk.text` changed
latency by under 5% either way (noise), but changed recall@1 consistently:

| config | recall@1, raw | recall@1, breadcrumb |
|---|---|---|
| bge, 512 | 0.346 | **0.500** |
| bge, 384 | 0.308 | **0.423** |
| bge, 256 | 0.385 | **0.462** |
| MiniLM, 512 | 0.346 | **0.423** |
| MiniLM, 384 | 0.385 | 0.385 (tied) |
| MiniLM, 256 | 0.308 | **0.423** |

Breadcrumb text won or tied recall@1 in all six (model, max_length)
combinations tested, by 2-4 questions where it won — giving the
cross-encoder the same "which sheet, which section" context the embedding
model already uses helps it pick the single best match, consistent with
how that context is used everywhere else in the pipeline. **Breadcrumb
text shipped.**

**Combined, re-verified through the real pipeline** (26 dev questions,
cached embeddings, *including* the q109 label fix below — see the full
ablation table further down for the complete picture including
bm25/vector/hybrid):

| config | recall@1 | recall@5 | recall@10 | MRR | p50 | p95 |
|---|---|---|---|---|---|---|
| MiniLM, tuned (**shipped**) | 0.385 | 0.846 | 0.962 | 0.588 | **785ms** | 897ms |
| bge, tuned (Week-8 comparison) | 0.423 | 0.923 | 0.962 | 0.629 | **4,580ms** | 4,823ms |
| bge, untuned (original default) | 0.346 | 0.885 | 0.962 | 0.564 | 8,062ms | 8,207ms |
| MiniLM, untuned | 0.346 | 0.808 | 0.923 | 0.553 | 1,522ms | 1,615ms |

(The "untuned" rows predate the q109 fix too, so part of the gap to the
tuned rows is the data fix, not only max_length/breadcrumb — see "What
this shows" above for the breakdown.) Tuning cut both models' latency
substantially while holding or improving recall — not a quality/speed
trade, a clean win on both axes. bge stays well over the ~1s bar even
tuned; MiniLM was already under it even untuned, and tuning took it
further under. Cached latency varies somewhat run-to-run on this shared
machine (the MiniLM row above reads 785ms here vs. 628ms in an earlier
run with identical code and config) — treat it as "same order of
magnitude," not a precise figure; "Real latency, cached vs. uncached"
below has the more meaningful cached-vs-uncached comparison.

**Is adding the (tuned) reranker worth it at all, relative to plain
hybrid?** This is the comparison that matters for whether to run it on
every query. Using each mode's realistic, uncached ("first time this exact
question is asked") latency, since that's what a real user experiences on
a question nobody's asked before:

| | recall@1 | recall@5 | recall@10 | MRR | p50 (uncached) |
|---|---|---|---|---|---|
| hybrid (no rerank) | 0.500 | 0.769 | 0.846 | 0.632 | ~410ms |
| hybrid + MiniLM (tuned) | 0.385 | 0.846 | 0.962 | 0.588 | ~1,025ms |

Stated plainly: on dev, adding the tuned MiniLM reranker gains about **2
questions at recall@5 and 3 questions at recall@10**, loses about **3
questions at recall@1** (and MRR drops with it), and **adds ~600ms**. A
better case for the reranker than before the q109 fix (recall@5/@10 gains
are now clearly past the noise floor), but recall@1 still regresses by a
real margin — it depends whether the generation step needs the single
best chunk at #1 (where plain hybrid is still better) or benefits from a
cleaner top-5/top-10 to synthesize across. **Leading Week-8 candidate:
skip the reranker — always, or conditionally when hybrid's own
agreement/score already looks confident** — given the latency this buys
back and that recall@1 (not just recall@5/@10) matters for whatever the
generation step actually uses.

**Recommendation:** MiniLM, per the stated decision rule — `bge-reranker-base`
never gets close to the ~1s bar even tuned (~4-6s depending on run), while
MiniLM comfortably clears it even untuned (1.52s) and more so tuned
(~0.6-0.8s). `bge-reranker-base` is kept as the Week-8 comparison point
since it does score meaningfully higher on recall@5/MRR when a reranker is
used at all. **Decision: pending team review** (see above) — this is our
recommendation, not yet a committed final choice.

### Real latency, cached vs. uncached

`embed.py`'s disk cache (`data/cache/embeddings/`) means a question embedded
once is free on every later run — including every earlier number in this
document that didn't explicitly disable it. That's correct behavior for a
dev-iteration or re-run workflow, but it means the pipeline's *first-ever*
latency for a genuinely new question is quite different:

| mode | cached p50 | cached p95 | uncached p50 (real OpenAI call) | uncached p95 |
|---|---|---|---|---|
| vector | 4.5ms | 7.2ms | **522ms** | 1,537ms |
| hybrid | 4.3ms | 6.2ms | **412ms** | 788ms |
| hybrid+rerank (MiniLM) | 652ms | 721ms | **1,025ms** | 1,496ms |

(`eval/retrieval_eval.py --no-cache`, which forces `use_cache=False` through
to `embed_texts()` and bypasses the in-process `embed_query` cache via
`Retriever.from_config(cache_queries=False)` — both layers, not just one.)
The embedding API call itself costs ~400-900ms uncached and is identical
regardless of which reranker is chosen, so it doesn't change the
bge-vs-MiniLM comparison above — but it does mean a cold cache pushes
hybrid+rerank's realistic first-query latency to ~1 second even with
MiniLM. BM25 isn't shown: it never calls the embedding API, cached or not.

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

**Current** (after tuning — MiniLM default, max_length=384, breadcrumb text
— *and* after the q109 label fix below; this is the authoritative table,
regenerated by the most recent `eval/retrieval_eval.py` run):

| mode | recall@1 | recall@5 | recall@10 | MRR | p50 latency | p95 latency |
|---|---|---|---|---|---|---|
| bm25 | 0.231 | 0.731 | 0.808 | 0.419 | 0.4ms | 0.8ms |
| vector | 0.423 | 0.769 | 0.808 | 0.580 | 7.7ms | 9.4ms |
| hybrid (RRF) | **0.500** | 0.769 | 0.846 | **0.632** | 8.1ms | 9.4ms |
| hybrid+rerank (MiniLM, shipped) | 0.385 | 0.846 | 0.962 | 0.588 | **785ms** | 897ms |
| hybrid+rerank (bge-reranker-base) | 0.423 | **0.923** | 0.962 | 0.629 | 4,580ms | 4,823ms |

(Cached p50/p95 above vary somewhat run-to-run on this shared machine —
e.g. hybrid+rerank (MiniLM) read 628ms in one run and 785ms in another
with no code change between them; see "Real latency, cached vs. uncached"
for the cached-vs-uncached comparison that matters more than small
run-to-run noise in the cached numbers specifically.)

**Before any of the above** (raw chunk text, max_length=512 default,
`bge-reranker-base` as the then-default, and the pre-fix q109 label — kept
for comparison, not reproduced by current code or data):

| mode | recall@1 | recall@5 | recall@10 | MRR | p50 latency | p95 latency |
|---|---|---|---|---|---|---|
| hybrid+rerank (bge-reranker-base) | 0.346 | 0.885 | 0.962 | 0.564 | 8,062ms | 8,207ms |
| hybrid+rerank (ms-marco-MiniLM-L-6-v2) | 0.346 | 0.808 | 0.923 | 0.553 | 1,522ms | 1,615ms |

bm25/vector/hybrid rows changed between the two tables only because the
q109 label fix (below) changed what counts as a hit for that one question
— not a retriever or tuning change.

What this shows:

- **Hybrid beats both of its inputs.** RRF fusion's recall@1 (0.500) clears
  vector (0.423) and bm25 (0.231) individually, and its MRR (0.632) is the
  best of any row — confirmation that combining the two retrieval methods
  is worth the (small) extra latency, not just a theoretical nicety.
- **Tuning bought recall *and* a large latency cut, simultaneously** — not
  a trade. hybrid+rerank (MiniLM)'s recall@5 (0.846) and MRR (0.588) both
  *improved* over the untuned baseline (0.808 / 0.553), recall@1 improved
  by one question (0.346 -> 0.385), while p50 dropped from 1,522ms to
  785ms (uncached: 1,025ms vs. the untuned config's own uncached cost,
  which wasn't separately measured — the two are not directly comparable
  on the cached figure alone). The three-lever breakdown above explains
  why: max_length=384 cut compute with no recall cost, breadcrumb text
  specifically helped recall@1, and the q109 label fix below accounts for
  part of the recall@5/@10 gain too (both tuning and the data fix moved
  the same direction, so don't attribute all of it to tuning).
- **Is the (tuned) reranker worth it at all, relative to plain hybrid?**
  Using each mode's realistic, uncached latency (what a question nobody's
  asked before actually costs): hybrid alone is recall@1 0.500, recall@5
  0.769, recall@10 0.846, MRR 0.632, ~410ms; hybrid+MiniLM (tuned) is
  recall@1 0.385, recall@5 0.846, recall@10 0.962, MRR 0.588, ~1,025ms.
  Stated plainly: the reranker gains **~2 questions at recall@5 and 3
  questions at recall@10, loses ~3 questions at recall@1** (MRR drops with
  it), and **adds ~600ms**. Closer to a clear win on recall@5/@10 than
  before the q109 fix, but recall@1 still regresses meaningfully — depends
  whether generation needs the single best chunk at #1 (hybrid alone is
  better there) or a cleaner top-5/top-10 to synthesize across. Leading
  Week-8 candidate: skip the reranker, always or when hybrid already looks
  confident — see "Reranker choice" below for the full investigation and
  decision rule. `bge-reranker-base`'s recall@5 (0.923) is an even clearer
  win over hybrid (about 4 questions), which is why it's kept as the
  Week-8 quality comparison despite its latency.
- **BM25 and vector are now tied on recall@10** (0.808 each) after the
  q109 fix moved vector up (it was 0.769 before) — bm25 still trails badly
  on recall@1 and MRR, finding the right chunk somewhere in its list more
  often than it ranks it first. Consistent with the chunking-stage
  ablation (`eval/results/chunking_dev.md`).

### "I don't know" threshold

**Vector cosine score is not usable for this gate.** The unanswerable
group's scores (0.522-0.622) sit *inside* the answerable group's range
(0.458-0.748) — the best achievable threshold catches 0 of 4 unanswerable
questions without also rejecting answerable ones. Cosine similarity
apparently isn't discriminating "no real answer in the corpus" from "a
real, slightly-less-perfect match" for this dev set. (Unaffected by the
reranker tuning above — this score comes from the vector retriever, not
the reranker.)

**Reranker score separates better, but which reranker matters a lot.**
With `bge-reranker-base`, a threshold of 0.252 caught 4/4 unanswerable
questions at the cost of wrongly rejecting 1/26 answerable ones — a strong
signal. With the shipped **MiniLM**, the same approach is much weaker: the
best threshold (-3.609) catches only **1/4 unanswerable questions**,
wrongly rejecting 0/26 answerable.

This is a real difference in how well the two models' judgments separate
the two groups, not an artifact of the numbers' scale: `bge-reranker-base`
reports a sigmoid-squashed score (0-1) and MiniLM a raw, unbounded logit,
but sigmoid is monotonic — it cannot change whether two score
*distributions* separate, only how the numbers that already do (or don't)
are labeled. The actual cause is some combination of (a) MiniLM genuinely
judging unanswerable questions' best candidate as more plausible than bge
does, relative to answerable questions, and/or (b) the breadcrumb-text
change, which was applied at the same time we switched models and wasn't
separately re-tested for its effect on calibration specifically (unlike
recall, which was). We haven't isolated which of the two matters more here
— worth doing before promoting this threshold past "backup gate."

**Decision: don't ship either as the refusal mechanism, for now** — more
true than ever with MiniLM as the default. Four unanswerable dev questions
is too small a sample to trust a threshold tuned against it to generalize,
and the shipped model's own separation is weak on top of that. Per the
brief: leave "I don't know" to the generation step, which has the full
answer (not just a retrieval score) to judge faithfulness from. If a cheap
backup gate is wanted later, it should use `bge-reranker-base`'s score
specifically (the stronger signal), not MiniLM's — but it is not the
primary mechanism either way, and nothing here has been tuned against
`data/test.jsonl`.

### Reranker regression checks (manual, not dev-set)

Three hand-picked queries, re-run after the tuning above (breadcrumb text,
max_length=384), both models. These are sanity checks for a human to read,
not tuned against: no retrieval parameter was changed to make any of them
pass — the docker-non-root result below improving is a side effect of the
max_length/breadcrumb tuning, discovered afterward, not the goal it was
tuned toward.

**1. "how many bcrypt rounds should I use?"** — expected: the main bcrypt
section (work factor) in the top 3.

- hybrid (no rerank): 1. bcrypt > Input Limits of bcrypt — 2. bcrypt >
  Pre-Hashing Passwords with bcrypt — 3. Introduction
- hybrid+rerank (MiniLM, shipped): **1.** bcrypt > Input Limits of bcrypt
  — 2. Ruby on Rails > Encryption — 3. Introduction
- hybrid+rerank (bge-reranker-base): 1. Ruby on Rails > Encryption — **2.**
  bcrypt > Input Limits of bcrypt — 3. Introduction

**PASS for both models** (MiniLM even ranks it #1). Note: the heading
`bcrypt > Input Limits of bcrypt` is misleading on its own — `bcrypt`'s own
intro paragraph (the one that actually says *"The work factor should be as
large as verification server performance will allow, with a minimum of
10"*) has no sub-heading of its own, so the chunker's push-down rule (see
"Index choice" above) folds it into the first child section, `Input Limits
of bcrypt`. The content is exactly what was expected; only the label looks
odd.

**2. "run docker container as non-root"** — expected: "RULE #2 - Set a
user" in the top 3.

- hybrid (no rerank): 1. Rule #11 - Run Docker in rootless mode — 2. Podman
  as an alternative to Docker — 3. RULE #8 - Set filesystem/volumes
  read-only
- hybrid+rerank (MiniLM, shipped): 1. Rule #11 - rootless mode — 2. Node.js
  Docker > Don't run containers as root — **3.** RULE #2 - Set a user
- hybrid+rerank (bge-reranker-base): 1. Rule #11 - rootless mode — 2.
  Podman as an alternative — 3. Kubernetes > security context example

**Now PASSES with the shipped (MiniLM) config** — it did not before tuning
(RULE #2 sat at hybrid rank 4, just outside top 3, and the untuned reranker
didn't pull it in either; see git history for that result). `bge-reranker-base`
still misses it even after tuning. Breadcrumb text is the likely reason:
RULE #2's chunk text alone never says "root" or "non-root" (it's
`docker run -u`, `useradd`, "unprivileged user"), but its breadcrumb
(`Docker Security Cheat Sheet > Rules > RULE #2 - Set a user`) gives MiniLM
the sheet/rule context to recognize it as the right kind of answer even
without exact vocabulary overlap. Not something we tuned toward on
purpose — a genuine side effect worth noting.

**3. "csrf protection for single page apps"** — expected: Web Frontend
Security › Use CSRF Protection stays at #1.

- hybrid (no rerank): 1. Web Frontend Security > Use CSRF Protection — 2.
  Laravel > CSRF — 3. Ruby on Rails > CSRF
- hybrid+rerank (MiniLM, shipped): 1. Laravel > CSRF — 2. CSRF Prevention >
  Custom Headers and CORS — 3. NodeJS Security > Use Anti-CSRF tokens
- hybrid+rerank (bge-reranker-base): 1. Laravel > CSRF — 2. Ruby on Rails >
  CSRF — 3. CSRF Prevention > Custom Headers and CORS

**FAIL for both models, before and after tuning.** Reranking moves the
expected #1 result out of the top 3 entirely either way. Our reading:
both cross-encoders reward chunks whose text is densely, specifically
about "CSRF" (the Laravel and CSRF-Prevention-sheet chunks are short and
CSRF-focused end-to-end) over a chunk that mentions CSRF protection as one
bullet inside a broader "Server-Side" security checklist (Web Frontend
Security's chunk) — even though the broader chunk was the better *hybrid*
match. A real reranker behavior worth knowing about before trusting
hybrid+rerank blindly: it can demote a correct, broadly-relevant chunk in
favor of a narrower, keyword-dense one. Tuning improved check #2 as a side
effect but didn't touch this one — consistent with these being genuine
reranker behaviors, not tuning artifacts in either direction.

### Retrieval failure cases

Full per-question detail in `eval/results/retrieval_dev_failures.md`.
Headline (current): **zero questions where hybrid+rerank misses but
another mode hits** — reranking never uniquely loses to a simpler mode on
this dev set. Exactly **one question every mode misses**:

- **q021** — known issue, not a retriever bug (passage spans a sub-heading
  boundary; see "Known failure cases" above). Every mode's top-3 are all
  plausible, on-topic chunks from the right cheat sheet — the retriever is
  behaving reasonably, it just can't produce a chunk containing text that
  no single chunk contains.

**q109 was also a universal miss, and turned out to be a label bug in the
eval set, not a retriever problem** — found via this diagnostics file,
fixed post-freeze. Its primary `source_passage` was
`AI_Agent_Security_Cheat_Sheet.md`'s generic intro, which never mentions
MCP at all, even though the question is specifically about MCP; the
passage that actually supports the question (`MCP_Security_Cheat_Sheet.md`'s
intro) was sitting uncredited in `extra_sources`. No retrieval method could
score a hit against a passage that doesn't address the question — every
mode missing it was the *correct* behavior given the mislabeled data, not
a retrieval defect. Fixed in `data/eval.json` / `data/dev.jsonl`
(primary/extra_sources swapped, answer trimmed to match; logged in
`data/REVIEW_STATS.md` under "Post-freeze label fixes") and confirmed: all
numbers in this document now reflect the corrected row, and q109 is no
longer a universal miss (hybrid and both reranker configs now hit it).

One transient observation from before the fix, kept for the record since
it illustrates something real about reranking even though the underlying
data turned out to be wrong: with the *pre-fix* mislabeled passage,
`bge-reranker-base`'s hybrid+rerank uniquely found a hit for q109
somewhere in its top 10 (not top 3) under the untuned config, which
stopped happening once max_length/breadcrumb tuning was applied. That
specific effect is moot now that the underlying label is fixed, but it was
a real example of reranking sometimes recovering (or failing to recover)
something earlier stages buried — worth remembering that reranker tuning
can have small, hard-to-predict side effects in either direction (see
check #2 above for one that helped, on real data).
