"""
Load OWASP cheat sheets and parse each one into a tree of headings.

A cheat sheet's content is split into "blocks": prose paragraphs, fenced
code blocks, and Markdown tables. Code blocks and tables are atomic — the
parser never splits them, so the chunker (chunk.py) never has to either.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CHEATSHEETS_DIR = ROOT / "corpus" / "CheatSheetSeries" / "cheatsheets"

# "# Title", "## Heading", ... up to h6. Trailing "#"s (closed ATX headings,
# e.g. "## Heading ##") are stripped along with trailing whitespace.
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE_RE = re.compile(r"^(```|~~~)")
# A table separator cell is dashes, optionally with alignment colons: "---", ":---", "---:", ":---:"
TABLE_SEP_CELL_RE = re.compile(r"^:?-+:?$")


@dataclass
class Block:
    """One atomic piece of section content."""

    kind: str  # "para" | "code" | "table"
    text: str  # raw text as it appears in the file (fences/pipes included)


@dataclass
class Section:
    """One heading and the content directly under it (not counting
    sub-headings, which are separate Section nodes in `children`)."""

    heading_path: list[str]  # e.g. ["Password Storage Cheat Sheet", "Password Hashing Algorithms", "Argon2id"]
    level: int
    parent: "Section | None" = None
    own_blocks: list[Block] = field(default_factory=list)
    children: list["Section"] = field(default_factory=list)


@dataclass
class Document:
    source_file: str
    title: str
    commit: str | None
    date: str | None
    root: Section


def list_cheatsheet_files() -> list[Path]:
    """Every file in scope: cheatsheets/*.md, excluding Index*.md.
    (cheatsheets_draft/ and repo tooling files live outside this directory
    entirely, so a plain glob here already excludes them.)"""
    return sorted(p for p in CHEATSHEETS_DIR.glob("*.md") if not p.name.startswith("Index"))


def get_commit_hash() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=CHEATSHEETS_DIR,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except Exception:
        return None


def get_last_modified_date(path: Path) -> str | None:
    """Date (YYYY-MM-DD) of the last commit that touched this file, per the
    corpus repo's own git history. None if git isn't available or the file
    isn't tracked (e.g. a clean clone without full history)."""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%ad", "--date=short", "--", path.name],
            cwd=path.parent,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def is_table_separator(line: str) -> bool:
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    cells = [c for c in cells if c]
    return bool(cells) and all(TABLE_SEP_CELL_RE.match(c) for c in cells)


def parse_markdown(text: str, fallback_title: str) -> Section:
    """Parse raw Markdown into a tree of Sections, one per heading.

    Headings nest by level using a stack: when a new heading arrives, we
    pop any open heading at the same level or deeper, then attach the new
    one under whatever is left on top of the stack. This works even if a
    file skips a level (h1 -> h3 with no h2).
    """
    lines = text.splitlines()
    virtual_root = Section(heading_path=[], level=0)
    stack: list[Section] = [virtual_root]
    current = virtual_root

    para_buffer: list[str] = []

    def flush_para() -> None:
        if para_buffer:
            joined = "\n".join(para_buffer).strip()
            if joined:
                current.own_blocks.append(Block("para", joined))
            para_buffer.clear()

    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        fence_match = FENCE_RE.match(stripped)
        if fence_match:
            fence = fence_match.group(1)
            if fence in stripped[len(fence):]:
                # Self-closing on one line (e.g. "```https://example.com```"
                # used as inline code) -- a real fence opener is just the
                # marker plus an optional language tag, never a second copy
                # of the marker on the same line. Treat as plain text so we
                # don't scan to EOF looking for a closing line that was
                # never going to come.
                para_buffer.append(line)
                i += 1
                continue
            flush_para()
            start = i
            i += 1
            while i < n and not lines[i].strip().startswith(fence):
                i += 1
            i = min(i + 1, n)  # include the closing fence line, if any
            current.own_blocks.append(Block("code", "\n".join(lines[start:i])))
            continue

        heading_match = HEADING_RE.match(line)
        if heading_match:
            flush_para()
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            while stack[-1].level >= level:
                stack.pop()
            node = Section(heading_path=stack[-1].heading_path + [title], level=level, parent=stack[-1])
            stack[-1].children.append(node)
            stack.append(node)
            current = node
            i += 1
            continue

        if stripped == "":
            flush_para()
            i += 1
            continue

        # A table starts where a "|"-bearing line is immediately followed
        # by a valid separator row ("|---|:--:|---|"); it ends at the next
        # blank line or the first following line without a "|".
        if "|" in line and i + 1 < n and is_table_separator(lines[i + 1]):
            flush_para()
            start = i
            i += 2
            while i < n and lines[i].strip() != "" and "|" in lines[i]:
                i += 1
            current.own_blocks.append(Block("table", "\n".join(lines[start:i])))
            continue

        para_buffer.append(line)
        i += 1

    flush_para()

    if virtual_root.children:
        return virtual_root.children[0]
    # No heading at all (shouldn't happen in this corpus) — synthesize a
    # root so the rest of the pipeline still has something to chunk.
    virtual_root.heading_path = [fallback_title]
    virtual_root.level = 1
    return virtual_root


def load_document(path: Path, commit: str | None) -> Document:
    text = path.read_text(encoding="utf-8")
    fallback_title = path.stem.replace("_", " ")
    root = parse_markdown(text, fallback_title)
    return Document(
        source_file=path.name,
        title=root.heading_path[0] if root.heading_path else fallback_title,
        commit=commit,
        date=get_last_modified_date(path),
        root=root,
    )


def load_all_documents() -> list[Document]:
    commit = get_commit_hash()
    return [load_document(p, commit) for p in list_cheatsheet_files()]
