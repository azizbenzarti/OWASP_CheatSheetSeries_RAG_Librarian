# Review stats: draft vs. final

`data/eval_draft.json` (120 LLM-drafted questions, pre-review) vs. `data/eval.jsonl` (119 human-reviewed questions), after merging `data/review/reviewer_1..4.json`.

## Headline numbers

- Draft total: 120
- Final total (kept): 119
- Deleted by reviewers: 1
- Edited (any field besides `verified` changed from the draft): 48
- Kept unchanged (reviewer approved as-is): 71
- Answerable questions in final set: 102
- Unanswerable questions in final set: 17

## Deleted questions

1 id(s) removed, by reviewer:

- **reviewer_3**: q051

## Edited questions

48 id(s) had at least one field changed from the draft:

q004, q005, q008, q011, q015, q016, q021, q022, q024, q027, q031, q035, q036, q038, q040, q041, q043, q044, q045, q046, q047, q050, q052, q053, q057, q061, q062, q064, q066, q072, q074, q077, q083, q093, q095, q096, q098, q104, q105, q107, q108, q109, q112, q113, q114, q116, q117, q120


## Counts per `review_notes` label

`review_notes` is free text (no formal label field per `data/REVIEW_GUIDE.md`); grouped here by each note's leading word, which reviewers consistently used as an action verb (Expanded, Removed, Corrected, ...).

| label | count |
|---|---|
| Expanded | 11 |
| Removed | 10 |
| Included | 5 |
| Added | 4 |
| Corrected | 3 |
| Reduced | 2 |
| Cited | 1 |
| Preserved | 1 |
| This | 1 |
| Separated | 1 |
| Extended | 1 |
| Made | 1 |
| Broadened | 1 |
| Distinguished | 1 |
| Avoided | 1 |
| Scoped | 1 |
| Kept | 1 |
| Matched | 1 |
| Clarified | 1 |
| **total with review_notes** | **48** |

## Final counts per type (draft -> final)

| type | draft | final |
|---|---|---|
| code_table | 12 | 11 |
| comparative | 18 | 18 |
| factual | 35 | 35 |
| multi_sheet | 13 | 13 |
| procedural | 25 | 25 |
| unanswerable | 17 | 17 |
| **total** | **120** | **119** |

## Final counts per category (draft -> final)

| category | draft | final |
|---|---|---|
| ai_security | 10 | 10 |
| api_architecture | 14 | 14 |
| attacks | 30 | 30 |
| devsecops | 18 | 18 |
| frameworks | 14 | 14 |
| identity | 28 | 27 |
| other | 6 | 6 |
| **total** | **120** | **119** |

