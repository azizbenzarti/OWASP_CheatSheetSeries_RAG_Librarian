# Postmortem

What went wrong while building The Librarian, what it cost us, and what we
would do differently. Ordered roughly by how much each one cost.

## 1. We chose the generator before we could measure it

**What happened.** Generation was built on Gemini (`gemini-flash-latest`)
and checked with a two-question smoke test (`python -m src.generation
--smoke`). That test checks the answer and the refusal, not the time. The
first time the whole service ran end to end (week 7, in Docker), Gemini
took **104–295 s per answer**, and 199 s even for the two-chunk smoke
prompt, against 2.5 s for `gpt-4o-mini` on the same prompt. The UI timed
out at 120 s, so 2 of the first 3 real questions failed.

**Why.** There was no generation eval yet ("Not done yet" in the README
until week 7), so nothing had ever measured generation latency, and the
smoke test only looked at the output.

**Fix.** The API's default generator is now OpenAI `gpt-4o-mini`
(`src/api/openai_generator.py`, same prompt, JSON schema and citation /
refusal rules). Gemini stays available with `GENERATOR=gemini`. All
generation numbers in the report are for `gpt-4o-mini`.

**Lesson.** Measure latency and cost of every external dependency on the
first day it is wired in, not just whether it returns the right thing.
Build the eval harness before choosing the model it is supposed to choose.

## 2. A wrong "I don't know" on an unanswerable question

**What happened.** On dev, 3 of 4 unanswerable questions are refused, but
q119 (federated fine-tuning of a shared LLM) is answered. Retrieval found
nearby AI-security chunks (multi-tenant inference, fine-tune adapters,
provenance tags) and the model stitched them into a confident, cited
answer to a question none of them addresses. One claim was even garbled
("use a shared cache key ... that varies by tenant"). Every claim is
"supported" in the narrow sense that it appears in a source, so
faithfulness and citation accuracy do not catch it. Only the refusal
metric does.

**Why.** Refusal relies on the model's judgment (per `docs/design.md`, no
retrieval-score threshold separated answerable from unanswerable cleanly
on dev). When the sources are on-topic but answer a neighbouring
question, the model answers anyway.

**Lesson / next step.** "Every claim is cited" is not "the question is
answered". Candidate fixes, not yet measured: ask the model to first state
whether the sources address *this* question, or combine the reranker
score with the model's judgment. With only 4 unanswerable dev questions,
any fix needs more unanswerable examples to be measured honestly.

## 3. A parser bug silently dropped six sections of a cheat sheet

**What happened.** One line in `Authorization_Cheat_Sheet.md` uses a
triple-backtick *inline* span. The loader read it as an unclosed code
fence and swallowed the rest of the file, so 6 real sections never
reached the index. Nothing errored.

**How it was found.** `eval/check_index.py`'s "odd number of fences"
invariant. Full story in `docs/design.md` ("Known failure cases").

**Lesson.** Silent data loss is the worst kind. Cheap structural checks on
the index (fence parity, passage coverage of the eval set) catch what no
unit test would.

## 4. The deployment broke in ways the code never did

All of these cost time during the first `docker compose up --build`:

- **Disk full.** The image (CPU-only torch + sentence-transformers) plus
  Docker's build cache filled the laptop's C: drive mid-build. Docker
  Desktop crashed with an unhelpful `rpc error: EOF`. We had to free space and
  rebuild from scratch (~10 min of downloads each time).
- **Windows line endings.** With `core.autocrlf=true`, `scripts/*.sh` were
  checked out with CRLF, which bash in a Linux container cannot run. Fixed
  twice over: `.gitattributes` (`*.sh eol=lf`) and a `sed` in the
  Dockerfile, so even an old checkout builds.
- **An empty variable is not an unset one.** `.env.example` contains
  `RERANKER_MODEL=`; `os.environ.get("RERANKER_MODEL", default)` then
  returns `""`, not the default, so a fresh `.env` copied from the example
  broke the reranker. Fixed in `reranker.py` (`get(...) or default`) and the
  container entrypoint unsets empty optional variables.
- **Account access assumptions.** The generation-eval judge was meant to be
  `gpt-4o`; our OpenAI project returns 403 for it. The judge is
  `gpt-4.1-mini` instead (listed via the models API, not guessed).

**Lesson.** "Runs from a clean clone" has to be tested on a clean machine,
early. Every one of these was invisible on the machine that wrote the code.

## 5. Two people built the same API

**What happened.** On the same day, two team members each built a FastAPI
service over the Librarian (`src/api/app.py` on `main`, `src/api/main.py`
on the deployment branch), and the UI was built against the first one.
Merging meant choosing one API (we kept the one with request logging,
`/stats` and the OpenAI generator) and adapting it to the UI's contract
(`sources` with passage text, `rating` feedback returning 204, a flat
`/health` body), and deleting the other.

**Lesson.** Agree on who owns each piece and on the API contract (request
and response shapes) before building on it, and push work in progress
early so overlap shows up in hours, not at merge time.

## 6. Secrets were shared through chat

**What happened.** API keys were pasted into chat messages while setting up
the service. They never reached the repo (`.env` is gitignored and
`.dockerignore` keeps it out of the image), but a key in a chat transcript
should be treated as exposed.

**Lesson.** Keys go straight into `.env`, never into chat, issues or
screenshots. Exposed keys should be rotated; at minimum the OpenAI project
should have a monthly budget cap.

## 7. Our eval set is small, which limits what we can claim

- dev has 26 answerable + 4 unanswerable questions: **one question is ~3.8
  points** of any answerable metric and **25 points** of the refusal rate.
  The Week 8 rule ("lose at most 2 points") is smaller than one dev
  question, so the before/after decision is made on test (89 questions,
  ~1.2 points each). Even there, 2 points is about 2 questions.
- Two dev labels needed fixing or caveats (q021: the passage spans a
  heading boundary, so no chunking config can contain it; q109: the
  primary passage is a generic intro). Some "retrieval misses" were
  label problems, not retriever bugs.
- Correctness and faithfulness are graded by an LLM judge. It occasionally
  flags a connective sentence ("The server should verify the following
  checks:") as an unsupported claim (q047), so faithfulness is slightly
  pessimistic. We did not measure judge agreement with humans.

**Lesson.** Write more unanswerable questions, and spot-check the judge
against a human on a sample before trusting small differences.

## 8. Things we have not done yet

- **Real user feedback.** The service logs every question and thumbs
  up/down (`data/logs/`, `GET /stats`), but at the time of writing it has
  only been used by the team, so there is no real-user feedback to report.
- **Public deployment.** The service runs with one command on any machine
  with Docker. A public URL still needs a host.
