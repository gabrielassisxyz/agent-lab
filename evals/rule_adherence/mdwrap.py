"""Whether Markdown is soft-wrapped: one paragraph, one line.

A port of the operator's canonical unwrapper (`llm-workflow/scripts/md-unwrap.py`),
kept faithful on purpose. The check is defined as its author defines it: text is
already soft-wrapped exactly when unwrapping it changes nothing.

**Why a port and not an approximation.** The first attempt here was a short rule, "two
joinable prose lines in a row is a wrap", and a differential run against the canonical
gate disagreed on three of ten constructs: it missed a hard-wrapped blockquote, missed
a wrapped list continuation, and convicted a setext heading. An eval that scores a
rule the operator does not actually have measures nothing, and it fails silently,
because a checker that is merely wrong still produces numbers.

Line breaks are semantic in more Markdown constructs than they are decorative. A
fenced block, a table row, a frontmatter key, a nested list item and a two-trailing-
space hard break all look like "a short line" to a naive rewrap, and joining any of
them changes what the document means. Every one of those is a guard below, and the
guards are the content of this module.

`test_mdwrap.py` holds a conformance table whose expected verdicts were produced by
running the canonical script. Re-derive it if the canonical rule ever changes.
"""

from __future__ import annotations

import re

_FENCE = re.compile(r"^\s*(```|~~~)")
# A line that opens a block whose breaks are structural: heading, table row, list
# item, blockquote, thematic break, HTML, link-reference definition.
_BLOCK_START = re.compile(
    r"^\s*("
    r"#{1,6}\s"
    r"|\|"
    r"|[-*+]\s"
    r"|\d+[.)]\s"
    r"|>"
    r"|(-{3,}|\*{3,}|_{3,})\s*$"
    r"|<"
    r"|\[[^\]]+\]:"
    r")"
)
_INDENTED_CODE = re.compile(r"^(\t| {4,})")
# Two trailing spaces or a trailing backslash is an explicit line break the author
# asked for; joining it would delete it.
_HARD_BREAK = re.compile(r"(  +|\\)$")
# A run of `=` or `-` alone under a paragraph is a setext underline: the paragraph
# above it is a heading, and it reads as prose to any rule based on line content.
_SETEXT = re.compile(r"^\s*(=+|-+)\s*$")
# A lone `>` is the blank line inside a blockquote, separating two quoted paragraphs.
_QUOTE_BLANK = re.compile(r"^\s*>\s*$")
_QUOTE_MARKER = re.compile(r"^\s*>\s?")
# GitHub renders `> [!NOTE]` as a callout only when the marker sits alone on its line.
_ALERT = re.compile(r"^\s*>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*$", re.IGNORECASE)


def is_soft_wrapped(text: str) -> bool:
    """True when the text already has one line per paragraph."""
    return unwrap(text) == text


def quote_body(line: str) -> str:
    return _QUOTE_MARKER.sub("", line).strip()


def is_prose(line: str) -> bool:
    """A line carrying no structural meaning of its own, so it may be joined."""
    return bool(line.strip()) and not _BLOCK_START.match(line) and not _INDENTED_CODE.match(line)


def unwrap(text: str) -> str:
    """Join consecutive prose lines within each block into a single line.

    Three block kinds wrap differently and each needs its own continuation rule: a
    plain paragraph continues on any following prose line; a list item continues on a
    line indented under it that does not open a new item; a blockquote continues on a
    following `>` line, whose marker is dropped when folding.
    """
    lines = text.split("\n")
    out: list[str] = []
    buf: list[str] = []
    kind = "plain"
    item_indent = 0
    in_fence = False
    fence_marker = ""
    in_frontmatter = bool(lines) and lines[0].strip() == "---"
    seen_frontmatter_start = False

    def flush(keep_tail: bool = False) -> None:
        if not buf:
            return
        joined = buf[0].rstrip()
        for extra in buf[1:]:
            body = quote_body(extra) if kind == "quote" else extra.strip()
            joined += " " + body
        if keep_tail:
            marker = _HARD_BREAK.search(buf[-1])
            if marker and not joined.endswith(marker.group(0)):
                joined += marker.group(0)
        out.append(joined)
        buf.clear()

    def indent_of(line: str) -> int:
        return len(line) - len(line.lstrip())

    def continues(line: str) -> bool:
        if not buf or not line.strip():
            return False
        if kind == "quote":
            # A `>` prefix alone does not make a line joinable prose: a quote can
            # hold a list, a heading or a table, and those keep their breaks.
            return bool(quote_body(line)) and is_prose(quote_body(line))
        if kind == "list":
            # A marker at any depth opens its own item, so the stripped line is what
            # gets tested; a nested item indented four spaces also matches the
            # indented-code pattern and would otherwise fold into its parent.
            if _BLOCK_START.match(line.lstrip()):
                return False
            if indent_of(line) - item_indent >= 4:
                return False
            # An unindented prose line is Markdown's lazy continuation and still
            # belongs to the item.
            return indent_of(line) > item_indent or is_prose(line)
        return is_prose(line)

    for line in lines:
        if in_frontmatter:
            out.append(line)
            if line.strip() == "---":
                if seen_frontmatter_start:
                    in_frontmatter = False
                else:
                    seen_frontmatter_start = True
            continue

        fence = _FENCE.match(line)
        if fence:
            marker = fence.group(1)
            if not in_fence:
                flush()
                in_fence, fence_marker = True, marker
            elif marker == fence_marker:
                in_fence = False
            out.append(line)
            continue

        if in_fence:
            out.append(line)
            continue

        # A setext underline terminates the paragraph above it and keeps its own line.
        if buf and _SETEXT.match(line):
            flush()
            out.append(line)
            continue

        if _ALERT.match(line):
            flush()
            out.append(line)
            continue

        if continues(line):
            buf.append(line)
            if _HARD_BREAK.search(line):
                flush(keep_tail=True)
            continue

        flush()

        stripped = line.lstrip()
        if not line.strip() or _FENCE.match(line) or _INDENTED_CODE.match(line):
            out.append(line)
        elif _QUOTE_BLANK.match(line):
            out.append(line)
        elif stripped.startswith(">") and is_prose(quote_body(line)):
            kind, buf[:] = "quote", [line]
        elif re.match(r"([-*+]\s|\d+[.)]\s)", stripped):
            kind, item_indent, buf[:] = "list", indent_of(line), [line]
        elif is_prose(line):
            kind, buf[:] = "plain", [line]
            if _HARD_BREAK.search(line):
                flush(keep_tail=True)
        else:
            out.append(line)

    flush()
    return "\n".join(out)
