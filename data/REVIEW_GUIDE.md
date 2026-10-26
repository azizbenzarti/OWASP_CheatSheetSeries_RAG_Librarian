# Review guide

You've been assigned a slice of `data/eval_draft.json` in
`data/review/reviewer_N.json` — your whole cheat sheets, not split with
anyone else. It's a pretty-printed JSON array, one question object per
entry; open it in an editor with JSON syntax highlighting. Go through every
entry and decide: **keep as-is, edit, or delete.**

Have the corpus checked out (`scripts/fetch_corpus.sh`) and the actual
`.md` file open next to each question so you can check against the real
text, not memory.

## Checklist, per row

1. **Passage exists and actually supports the answer.**
   Open `source_file`, find `source_section`, confirm `source_passage` is
   really there (word-for-word — `scripts/check_passages.py` already
   checked this mechanically, but it can't tell if the passage *means* what
   the answer claims). If the passage is there but doesn't actually support
   the answer, that's a fail even though the script passed it.
2. **Answer is correct and complete.** Re-derive the answer yourself from
   the passage alone. If you need outside knowledge to get the same answer,
   the passage is too thin — widen it or flag it.
3. **Question is natural and unambiguous.** Would a developer actually
   phrase it this way? Could it be read two different ways? Does it
   accidentally reuse the cheat sheet's own heading wording (if so, reword
   it)?
4. **For `unanswerable` rows: the absence is real.** Re-run (or spot-check)
   the grep terms in `absence_check` yourself against `cheatsheets/`. If you
   find a passage that does answer it, either delete the row or convert it
   to an answerable one with real source fields.
5. **For `comparative` / `multi_sheet` rows:** check `extra_sources` the
   same way as the primary source — passage present, supports its part of
   the answer, section path correct.
6. **For `code_table` rows:** confirm the passage is the actual code block
   / table (not prose paraphrasing it), and that the answer is something you
   can only get from that code/table, not from surrounding prose alone.

## What to do with each row

- **Fine as-is** → set `"verified": true`. Don't touch anything else.
- **Needs a small fix** (wrong section path, answer phrasing off, question
  wording awkward, passage could be tighter) → make the edit directly in
  your `reviewer_N.json` file, set `"verified": true`, and add a
  `"review_notes"` field (free text) saying what you changed and why.
- **Not salvageable** (passage doesn't support the answer, question is
  unanswerable from the corpus but was marked answerable, duplicate of
  another question, genuinely ambiguous) → delete that whole `{ ... }`
  object from the array. Don't leave `"verified": false` entries lying
  around — an entry is either fixed-and-verified or gone. Watch your commas:
  if you delete the last object in the array, remove the trailing comma on
  the one before it; your editor's JSON linter (or `check_passages.py`,
  which will fail loudly on invalid JSON) will catch it if you miss one.

## Before you're done

- Re-run `python3 scripts/check_passages.py data/review/reviewer_N.json`
  after any edits — it'll catch a passage you broke while editing, or a
  JSON syntax error from a stray/missing comma.
- Every entry in your file when you're done should have `"verified": true`.
- Send your edited `reviewer_N.json` back; someone will merge all four
  into the final `data/eval.json` (freezing and the dev/test split happen
  after that, in a later step — not your job here).

Don't rewrite questions to be "better" security advice than the cheat sheet
says — the eval set measures whether the RAG system matches *this corpus*,
not best practice in general. If you think the cheat sheet itself is wrong,
leave a `review_notes` comment instead of silently fixing it.
