# Eval dataset schema

`data/eval_draft.json` — a single pretty-printed JSON array (`indent=2`), one
object per question, in the field order below. This format (not one-object-
per-line JSONL) is deliberate: a human reviewer needs to actually read and
hand-edit every row, and a 2000-character single line is not reviewable.
`scripts/check_passages.py` accepts this array format (and, for backward
compatibility, legacy JSONL).

Field order within each object (also the order a reviewer should expect
when scanning a row top to bottom: what it is, then the Q&A, then where it
came from, then bookkeeping):

| field | type | notes |
|---|---|---|
| `id` | string | `q001`, `q002`, ... zero-padded, unique, stable once assigned. |
| `type` | string | One of `factual \| procedural \| comparative \| multi_sheet \| code_table \| unanswerable`. See below. |
| `category` | string | One of `attacks \| identity \| devsecops \| frameworks \| api_architecture \| ai_security \| other`. The topic area the question belongs to (see `data/PLAN.md` for the sheet→category mapping used in this dataset). |
| `answerable` | bool | `true` unless `type` is `unanswerable`. |
| `question` | string | Phrased the way a developer would actually ask it. Never copies the cheat sheet's own heading wording. |
| `answer` | string | Short, precise, complete. For `unanswerable` questions: `"I don't know"` (or the literal expected refusal text). |
| `source_file` | string \| null | Filename only, e.g. `"Password_Storage_Cheat_Sheet.md"`, relative to `corpus/CheatSheetSeries/cheatsheets/`. `null` if `answerable` is `false`. |
| `source_section` | string \| null | Full heading path from H1 (or H2) down to the heading that contains the passage, joined with `" > "`, e.g. `"Password Hashing Algorithms > Argon2id"`. `null` if unanswerable. |
| `source_passage` | string \| null | Copied **verbatim** from the file (only whitespace may be normalized — collapse runs of spaces, trim line edges). The smallest span that fully supports the answer, usually 1–6 sentences, or a full code block / table row set when the type is `code_table`. `null` if unanswerable. |
| `extra_sources` | array | Only non-empty for `type: "multi_sheet"` (and occasionally `"comparative"`) questions that need a second cheat sheet. Each entry: `{"source_file": ..., "source_section": ..., "source_passage": ...}`, same rules as above. `[]` otherwise. |
| `absence_check` | string | **Only present on `type: "unanswerable"` rows** (the key is omitted entirely on other rows, not set to `null`). The grep terms run against the whole `cheatsheets/` folder that were used to confirm the answer is genuinely absent, e.g. `"grep -ril 'argon2 memory cost default' cheatsheets/ -> no hits"`. |
| `origin` | string | `"llm_draft"` for everything produced in this pass. |
| `verified` | bool | `false` until a human reviewer confirms it in Part C/D (human review). Always `false` at draft time. |
| `reviewer` | string | One of `reviewer_1`..`reviewer_4`. Assigned after generation so each reviewer owns whole sheets (see `data/REVIEW_GUIDE.md`). |

## Type definitions

- **factual** — a single fact/definition/recommendation, answerable from one short passage in one file.
- **procedural** — "how do I / what are the steps to..." answerable from an ordered list or sequence of steps in one file.
- **comparative** — asks to compare two options/approaches (e.g. bcrypt vs Argon2id, Authentication vs Session Management). Usually draws on two cheat sheets; use `extra_sources` for the second one when that's the case.
- **multi_sheet** — the answer genuinely requires combining information from two different cheat sheets (not just comparing them — synthesizing). `extra_sources` must be non-empty.
- **code_table** — the answer sits inside a fenced code block or a Markdown table in the source file.
- **unanswerable** — a realistic security question the corpus does not cover. `source_file`/`source_section`/`source_passage` are `null`, `answerable` is `false`, `answer` is the "I don't know" refusal, and `absence_check` records what was grepped to confirm absence.

## Invariants enforced by `scripts/check_passages.py`

1. Every non-null `source_passage` (and every `extra_sources[].source_passage`) must appear verbatim (after whitespace normalization) in its `source_file` under `corpus/CheatSheetSeries/cheatsheets/`.
2. `source_file` must exist in `corpus/CheatSheetSeries/cheatsheets/`.
3. `unanswerable` rows must have `source_file`, `source_section`, `source_passage` all `null`, `answerable: false`, and a non-empty `absence_check`.
4. Non-`unanswerable` rows must have `answerable: true` and non-null `source_file`/`source_section`/`source_passage`.

We deliberately store the section heading path and verbatim passage text — not chunk IDs — because chunking strategy will change later in the project and must not invalidate the eval set.
