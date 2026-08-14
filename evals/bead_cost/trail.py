#!/usr/bin/env python3
"""Render a pi session log as something a person can follow, live or after the fact.

    tail -f <session>.jsonl | ./trail.py          # follow a run
    ./trail.py <session>.jsonl                    # read one that finished
    tail -f <session>.jsonl | ./trail.py --full   # no truncation

Written for the pilot protocol's third step - read the trajectory looking for contamination, a
memory, a previous run's branch, a web result - which is not something anyone does against raw
JSONL. It is a viewer and nothing else: it never sums, scores or judges, because a number worth
having comes from `collect.py` reading the same file, and two tools computing the same figure
differently is how a run ends up with two truths.

The event shapes are the ones pi 0.84 actually writes, read off a live session rather than assumed:
`session`, `model_change`, `thinking_level_change`, `compaction`, and `message` with role `user`,
`assistant` or `toolResult`. Anything else prints as its type instead of being swallowed, because a
viewer that hides what it does not recognise is a viewer that hides the interesting part.
"""
from __future__ import annotations

import argparse
import json
import sys

RESET = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"
COLOR = {
    "user": "\033[36m",
    "assistant": "\033[35m",
    "tool": "\033[33m",
    "error": "\033[31m",
    "meta": "\033[34m",
    "think": "\033[90m",
}


def paint(text: str, key: str, enabled: bool) -> str:
    return f"{COLOR.get(key, '')}{text}{RESET}" if enabled else text


def clock(event: dict) -> str:
    stamp = event.get("timestamp") or ""
    # "2026-08-14T22:20:42.914Z" -> "22:20:42"
    return stamp[11:19] if len(stamp) >= 19 else "--:--:--"


def squash(text: str, limit: int | None) -> str:
    text = " ".join(str(text).split())
    if limit and len(text) > limit:
        return text[:limit] + "…"
    return text


def render(event: dict, limit: int | None, color: bool) -> list[str]:
    kind = event.get("type")
    when = paint(clock(event), "meta", color)
    out: list[str] = []

    if kind == "session":
        return [f"{when} {paint('session', 'meta', color)} pi {event.get('version')} in {event.get('cwd')}"]

    if kind == "model_change":
        return [f"{when} {paint('model', 'meta', color)} {event.get('provider')}/{event.get('modelId')}"]

    if kind == "thinking_level_change":
        return [f"{when} {paint('thinking', 'meta', color)} level={event.get('thinkingLevel')}"]

    if kind == "compaction":
        # Worth its own line and never folded into the noise: a compaction changes what every later
        # turn is priced against, so a token curve that bends here bends for that reason.
        return [
            f"{when} {paint('COMPACTION', 'error', color)} "
            f"tokens_before={event.get('tokensBefore')} summary={squash(event.get('summary') or '', limit)}"
        ]

    if kind != "message":
        return [f"{when} {paint(str(kind), 'meta', color)} {squash(json.dumps(event), limit)}"]

    message = event.get("message") or {}
    role = message.get("role")
    content = message.get("content")
    parts = content if isinstance(content, list) else []

    if role == "user":
        text = " ".join(p.get("text", "") for p in parts if p.get("type") == "text")
        return [f"{when} {paint('user', 'user', color)} {squash(text, limit)}"]

    if role == "toolResult":
        name = message.get("toolName", "?")
        tag = "tool!" if message.get("isError") else "tool"
        text = " ".join(p.get("text", "") for p in parts if p.get("type") == "text")
        key = "error" if message.get("isError") else "tool"
        return [f"{when} {paint(f'{tag} {name}', key, color)} {squash(text, limit)}"]

    if role == "assistant":
        for part in parts:
            ptype = part.get("type")
            if ptype == "thinking":
                out.append(f"{when} {paint('think', 'think', color)} {squash(part.get('thinking', ''), limit)}")
            elif ptype == "text":
                out.append(f"{when} {paint('say', 'assistant', color)} {squash(part.get('text', ''), limit)}")
            elif ptype == "toolCall":
                args = part.get("arguments")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        pass
                out.append(
                    f"{when} {paint('call ' + str(part.get('name')), 'tool', color)} "
                    f"{squash(json.dumps(args, ensure_ascii=False) if isinstance(args, (dict, list)) else args, limit)}"
                )
        usage = message.get("usage") or {}
        if usage:
            # Per-turn, never cumulative. A running total here would be a second opinion on
            # collect.py's numbers, and the wrong place to form one.
            out.append(
                f"{when} {DIM if color else ''}     in={usage.get('input')} out={usage.get('output')} "
                f"reason={usage.get('reasoning')} cacheR={usage.get('cacheRead')} "
                f"stop={message.get('stopReason')}{RESET if color else ''}"
            )
        return out or [f"{when} {paint('assistant', 'assistant', color)} (no content)"]

    return [f"{when} {paint(str(role), 'meta', color)} {squash(json.dumps(message), limit)}"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", nargs="?", help="session .jsonl; omit to read stdin")
    parser.add_argument("--full", action="store_true", help="do not truncate")
    parser.add_argument("--width", type=int, default=160, help="truncate at N chars (default 160)")
    parser.add_argument("--no-color", action="store_true")
    args = parser.parse_args()

    limit = None if args.full else args.width
    color = not args.no_color and sys.stdout.isatty()
    stream = open(args.path, errors="replace") if args.path else sys.stdin

    for line in stream:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            # A partial line is normal under `tail -f`: the writer is mid-append. Say so rather
            # than dying, and never silently drop it.
            print(f"{DIM}(partial line){RESET}" if color else "(partial line)", flush=True)
            continue
        for rendered in render(event, limit, color):
            print(rendered, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
