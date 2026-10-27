"""
Turn a parsed Document (see load.py) into a flat list of chunk dicts.

Two strategies:
  "heading" - one chunk per lowest-level (leaf) heading section; oversized
              sections are split further on block boundaries, tiny ones are
              merged into a neighboring sibling.
  "fixed"   - a plain sliding window over the whole document's blocks, in
              reading order, ignoring heading structure. Baseline to compare
              "heading" against.

Both strategies treat Blocks (paragraph / code / table, from load.py) as
atomic: a chunk boundary can fall between two blocks, never inside one. If
a single block is bigger than max_tokens, it still becomes its own chunk
rather than being cut apart.
"""
from __future__ import annotations

import copy
import re
from typing import Callable

import tiktoken

from .load import Block, Document, Section

CountTokens = Callable[[str], int]


def make_token_counter(model_name: str) -> CountTokens:
    """Count tokens the same way the embedding model will: with its own
    tokenizer, not a generic word/char estimate.

    Embeddings come from a hosted, OpenAI-compatible API (see
    src/indexing/embed.py), so we count with tiktoken. If the model name
    isn't one tiktoken recognizes directly (e.g. a third-party model served
    behind an OpenAI-compatible proxy), we fall back to cl100k_base, the
    encoding shared by most current OpenAI-compatible embedding models —
    an approximation, not an exact match, which is worth knowing if a
    config's measured n_tokens looks slightly off from the API's own count.
    """
    try:
        encoding = tiktoken.encoding_for_model(model_name)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")

    def count(text: str) -> int:
        return len(encoding.encode(text))

    return count


def _slug(parts: list[str]) -> str:
    joined = "/".join(parts)
    return re.sub(r"[^a-zA-Z0-9/]+", "_", joined).strip("_")


def _block_text(blocks: list[Block]) -> str:
    return "\n\n".join(b.text for b in blocks)


def _make_chunk(
    doc: Document,
    heading_path: list[str],
    blocks: list[Block],
    index: int,
    count_tokens: CountTokens,
) -> dict:
    section_path = " > ".join(heading_path)
    text = _block_text(blocks)
    embed_text = f"{section_path}\n\n{text}"
    return {
        "chunk_id": f"{doc.source_file}::{_slug(heading_path)}::{index}",
        "text": text,
        "embed_text": embed_text,
        "source_file": doc.source_file,
        "title": doc.title,
        "section_path": section_path,
        "commit": doc.commit,
        "date": doc.date,
        "n_tokens": count_tokens(text),
        "has_code": any(b.kind == "code" for b in blocks),
        "has_table": any(b.kind == "table" for b in blocks),
    }


def _pack_blocks(blocks: list[Block], count_tokens: CountTokens, max_tokens: int) -> list[list[Block]]:
    """Greedily pack consecutive blocks into groups of at most max_tokens
    tokens each, never splitting a block. A single block that alone exceeds
    max_tokens becomes its own group instead of being cut apart."""
    groups: list[list[Block]] = []
    current: list[Block] = []
    current_tokens = 0
    for block in blocks:
        bt = count_tokens(block.text)
        if current and current_tokens + bt > max_tokens:
            groups.append(current)
            current, current_tokens = [], 0
        current.append(block)
        current_tokens += bt
    if current:
        groups.append(current)
    return groups


# --------------------------------------------------------------------- #
# "heading" strategy
# --------------------------------------------------------------------- #


def _push_down_orphan_content(section: Section) -> None:
    """A heading can have its own text before its first sub-heading (e.g.
    a one-line intro under "## Password Hashing Algorithms" before its
    "### Argon2id" / "### bcrypt" children). Since only leaf sections
    become chunks, that intro text is prepended to the first child instead
    of being dropped or chunked on its own."""
    if section.children:
        if section.own_blocks:
            section.children[0].own_blocks = section.own_blocks + section.children[0].own_blocks
            section.own_blocks = []
        for child in section.children:
            _push_down_orphan_content(child)


def _collect_leaves(section: Section, out: list[Section]) -> None:
    if not section.children:
        out.append(section)
    else:
        for child in section.children:
            _collect_leaves(child, out)


def _merge_tiny_leaves(leaves: list[Section], count_tokens: CountTokens, min_tokens: int) -> list[Section]:
    """Fold sections smaller than min_tokens into a neighboring sibling
    under the same parent heading, so we don't end up with e.g. a 4-token
    chunk for a heading that's just "See below." Leaves that share a parent
    are always consecutive in `leaves` (pre-order traversal visits a whole
    subtree before moving to the next sibling), so a single left-to-right
    pass is enough."""
    merged: list[Section] = []
    i = 0
    while i < len(leaves):
        leaf = leaves[i]
        tokens = count_tokens(_block_text(leaf.own_blocks))
        has_next_sibling = i + 1 < len(leaves) and leaves[i + 1].parent is leaf.parent
        has_prev_sibling = merged and merged[-1].parent is leaf.parent

        if tokens < min_tokens and has_next_sibling:
            leaves[i + 1].own_blocks = leaf.own_blocks + leaves[i + 1].own_blocks
        elif tokens < min_tokens and has_prev_sibling:
            merged[-1].own_blocks = merged[-1].own_blocks + leaf.own_blocks
        else:
            merged.append(leaf)
        i += 1
    return merged


def chunk_heading(doc: Document, max_tokens: int, min_tokens: int, count_tokens: CountTokens) -> list[dict]:
    # Work on a deep copy: push-down and merge both mutate the tree, and
    # the same parsed Document gets reused across many configs when the
    # chunking experiment (eval/chunking_experiment.py) sweeps parameters.
    root = copy.deepcopy(doc.root)
    _push_down_orphan_content(root)
    leaves: list[Section] = []
    _collect_leaves(root, leaves)
    leaves = _merge_tiny_leaves(leaves, count_tokens, min_tokens)

    chunks: list[dict] = []
    for leaf in leaves:
        groups = _pack_blocks(leaf.own_blocks, count_tokens, max_tokens)
        for idx, group in enumerate(groups):
            if group:  # a merged-away leaf can end up with no blocks of its own
                chunks.append(_make_chunk(doc, leaf.heading_path, group, idx, count_tokens))
    return chunks


# --------------------------------------------------------------------- #
# "fixed" strategy
# --------------------------------------------------------------------- #


def _flatten_blocks(section: Section, out: list[tuple[Block, Section]]) -> None:
    for block in section.own_blocks:
        out.append((block, section))
    for child in section.children:
        _flatten_blocks(child, out)


def chunk_fixed(doc: Document, max_tokens: int, overlap: int, count_tokens: CountTokens) -> list[dict]:
    flat: list[tuple[Block, Section]] = []
    _flatten_blocks(doc.root, flat)

    chunks: list[dict] = []
    i, n = 0, len(flat)
    index = 0
    while i < n:
        window: list[tuple[Block, Section]] = []
        window_tokens = 0
        j = i
        while j < n:
            bt = count_tokens(flat[j][0].text)
            if window and window_tokens + bt > max_tokens:
                break
            window.append(flat[j])
            window_tokens += bt
            j += 1

        blocks = [b for b, _ in window]
        heading_path = window[0][1].heading_path  # where this window starts
        chunks.append(_make_chunk(doc, heading_path, blocks, index, count_tokens))
        index += 1

        if j >= n:
            break

        # Step back from j by whole blocks until we've covered ~overlap
        # tokens, so the next window re-includes some trailing content.
        back_tokens = 0
        k = j
        while k > i and back_tokens < overlap:
            k -= 1
            back_tokens += count_tokens(flat[k][0].text)
        i = k if k > i else j  # guarantee forward progress even with overlap=0

    return chunks


def chunk_document(
    doc: Document,
    strategy: str,
    max_tokens: int,
    overlap: int,
    min_tokens: int,
    count_tokens: CountTokens,
) -> list[dict]:
    if strategy == "heading":
        return chunk_heading(doc, max_tokens, min_tokens, count_tokens)
    if strategy == "fixed":
        return chunk_fixed(doc, max_tokens, overlap, count_tokens)
    raise ValueError(f"unknown chunking strategy: {strategy!r}")
