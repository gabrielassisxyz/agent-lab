---
status: active
last_reviewed: 2026-07-14
---

# Backlog — workflow-benchmark

> The design and every rejected alternative live in [`docs/design.md`](docs/design.md).
> **Read that first** — this file is only the to-do list.
>
> This is a curiosity project. No deadline, no goal steering its scope.

## Now — the noise floor (§7 of the design)

The whole matrix is blocked on one number: **how much does the same task, same agent, same
config vary between runs?** If run-to-run noise is larger than the effects being hunted (skills
on/off, scaffold on/off), every result downstream is noise wearing a number's clothes.

- [x] Clone [`SWE-rebench/SWE-bench-fork`](https://github.com/SWE-rebench/SWE-bench-fork), install,
      verify Docker. → `~/repositories/_cloned/SWE-bench-fork`, `swebench 4.0.3`.
- [x] **Prove the scorer**: gold patch on `pgmpy__pgmpy-3137` (`2026_03`) → **resolved**, ~5 min.
      Needs `HF_TOKEN` — see design §8, the failure is misleading.
- [ ] **Close the sandbox leaks** (design §6): **no network** in the agent container, **prune
      future git refs and remotes** from the checkout. Must happen *before* the first agent run.
- [ ] Pick one instance from `2026_02` / `2026_03` (post-cutoff). Run `claude -p` with a neutral
      scaffold **10×**.
- [ ] Record per run: resolved · turns · tokens · wall time · files touched · tests run ·
      file/node-retrieval recall.
- [ ] Read the dispersion. **That number sizes everything else.**

## Next — one variable at a time

The full curiosity list is combinatorial (5 agents × skills × scaffold × orchestration ×
greenfield/brownfield ≈ 80 cells before repeats) and will not close. One variable at a time,
paired across ~20–30 instances rather than repeated on one.

**First variable: skills + scaffold on/off.** Chosen because agent-vs-agent is partially covered
by [the neuralnoise WIP](https://www.neuralnoise.com/2026/harness-bench-wip/) and *nobody* has
published on whether a personal scaffolding layer moves the number.

Then, in no fixed order:
- **Agent harness**: mini-swe-agent · Claude Code · Codex · `pi` · OpenCode.
- **Multi-agent orchestration** (kernl's orchestrator shape) vs a single agent.
- **Greenfield**, which needs a different dataset — Commit0 scores a from-scratch library against
  a spec + hidden tests, which is Akita's brief with automated scoring.

## Later

- **Build the agent** — ~300 lines in a loop (ghuntley's framing: read · list · bash · edit ·
  search). Objective (3). The benchmark above becomes its test bench.
- **Our own tasks** — objective (2), and only after running someone else's has taught us what a
  task actually is.

## Open questions

- **Is per-task difficulty derivable from the leaderboard dataset?** Needed for the mid-range
  (30–70% pass rate) filter. Not confirmed — see design §8.
- **The "6x performance from the harness alone" claim is unverified.** It is the premise of the
  whole repo and it rests on an unchecked LLM citation. Read the source before it goes anywhere
  public.
