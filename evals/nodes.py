"""Node-retrieval metric — which functions/classes a patch actually modifies.

Replaces the previous definition, which read the label git prints in the hunk header
(`@@ -353,11 +353,13 @@ def _build_skeleton(`). That label is a *rendering artifact* of the
diff, not a property of the code: git picks it with the `xfuncname` heuristic of whatever diff
driver happened to be configured. The gold patches ship from a pipeline with Python's driver
(which matches indented `def`s); an agent's `git diff` inside the container uses the default one
(which only matches column 0, so it reports the enclosing `class`). Same file, same lines, two
different labels — and a metric built on them is structurally zero. See design.md §10b.

The nodes are read from the AST instead, which is what SWE-PolyBench does:
parse the file **at `base_commit`**, then map each line the patch touches to the innermost
`def`/`class` that contains it.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import tree_sitter_python
from tree_sitter import Language, Node, Parser

PY = Language(tree_sitter_python.language())
HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@")
FILE_RE = re.compile(r"^diff --git a/(\S+) b/\S+")


def base_files(image: str, paths: set[str], cache: Path) -> dict[str, bytes]:
    """The repo's files as the agent found them, lifted out of the prebuilt eval image.

    The image is the ground truth for `base_commit`: it is the exact tree the agent worked on,
    and it is local, so this needs no network and cannot drift from what was run.
    """
    cache.mkdir(parents=True, exist_ok=True)
    out: dict[str, bytes] = {}
    missing = {p for p in paths if not (cache / p.replace("/", "__")).exists()}
    if missing:
        cid = subprocess.run(["docker", "create", image], capture_output=True, text=True,
                             check=True).stdout.strip()
        try:
            for p in missing:
                dst = cache / p.replace("/", "__")
                subprocess.run(["docker", "cp", f"{cid}:/testbed/{p}", str(dst)],
                               capture_output=True, check=False)
        finally:
            subprocess.run(["docker", "rm", cid], capture_output=True, check=False)
    for p in paths:
        f = cache / p.replace("/", "__")
        if f.exists():
            out[p] = f.read_bytes()
    return out


def _qualname(node: Node) -> str:
    """`Class.method` — the chain of enclosing definitions, so two same-named methods differ."""
    parts = []
    cur: Node | None = node
    while cur is not None:
        if cur.type in ("function_definition", "class_definition"):
            name = cur.child_by_field_name("name")
            if name is not None:
                parts.append(name.text.decode())
        cur = cur.parent
    return ".".join(reversed(parts))


def _defs(source: bytes) -> list[tuple[int, int, str]]:
    """Every def/class in the file as (first_line, last_line, qualified_name), 1-indexed."""
    tree = Parser(PY).parse(source)
    found: list[tuple[int, int, str]] = []

    def walk(node: Node) -> None:
        if node.type in ("function_definition", "class_definition"):
            found.append((node.start_point[0] + 1, node.end_point[0] + 1, _qualname(node)))
        for child in node.children:
            walk(child)

    walk(tree.root_node)
    return found


def _innermost(defs: list[tuple[int, int, str]], lo: int, hi: int) -> str | None:
    """The tightest def/class that fully contains [lo, hi]. None = module level, i.e. no node."""
    enclosing = [d for d in defs if d[0] <= lo and d[1] >= hi]
    if not enclosing:
        return None
    return min(enclosing, key=lambda d: d[1] - d[0])[2]


def _touched_lines(hunk_body: list[str], start: int) -> list[tuple[int, int]]:
    """The pre-image spans a hunk touches, as (lo, hi) line ranges to attribute to a node.

    A removed line is itself touched, so it maps to the node containing it. An *inserted* line
    consumes no pre-image line: it lands in the gap between the previous and the next pre-image
    line, so it is attributed to the node that strictly contains that gap. That is what makes a
    method added between two methods count as a change to the enclosing *class* and not as a
    change to whichever neighbour happens to sit above it.
    """
    spans: list[tuple[int, int]] = []
    pre = start
    for line in hunk_body:
        if line.startswith("-"):
            spans.append((pre, pre))
            pre += 1
        elif line.startswith("+"):
            spans.append((max(pre - 1, 1), pre))
        else:
            pre += 1
    return spans


def nodes_in(patch: str, files: dict[str, bytes]) -> set[str]:
    """The set of `path::Qualified.name` nodes a patch modifies."""
    nodes: set[str] = set()
    path: str | None = None
    defs: list[tuple[int, int, str]] = []
    start = 0
    body: list[str] = []

    def flush() -> None:
        if path is None or not body:
            return
        for lo, hi in _touched_lines(body, start):
            name = _innermost(defs, lo, hi)
            if name:
                nodes.add(f"{path}::{name}")

    for line in patch.splitlines():
        if (m := FILE_RE.match(line)):
            flush()
            body = []
            path = m.group(1)
            # A file the agent created has no base version: it contributes no *retrieved* node.
            defs = _defs(files[path]) if path in files else []
        elif (m := HUNK_RE.match(line)):
            flush()
            body = []
            start = int(m.group(1))
        elif path is not None and line[:1] in (" ", "+", "-"):
            body.append(line)
    flush()
    return nodes


def files_in(patch: str) -> set[str]:
    return set(re.findall(r"^diff --git a/(\S+) b/\S+", patch, re.M))
