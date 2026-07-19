---
status: active
last_reviewed: 2026-07-14
---

# Backlog — workflow-benchmark

> The design and every rejected alternative live in [`docs/design.md`](docs/design.md). **Read that first** — this file is only the to-do list.
>
> This is a curiosity project. No deadline, no goal steering its scope.

## Now — the noise floor (§7 of the design)

The whole matrix is blocked on one number: **how much does the same task, same agent, same config vary between runs?** If run-to-run noise is larger than the effects being hunted (skills on/off, scaffold on/off), every result downstream is noise wearing a number's clothes.

- [x] Clone [`SWE-rebench/SWE-bench-fork`](https://github.com/SWE-rebench/SWE-bench-fork), install,
      verify Docker. → `~/repositories/_cloned/SWE-bench-fork`, `swebench 4.0.3`.
- [x] **Prove the scorer**: gold patch on `pgmpy__pgmpy-3137` (`2026_03`) → **resolved**, ~5 min.
      Needs `HF_TOKEN` — see design §8, the failure is misleading.
- [ ] **Close the sandbox leaks** (design §6): **no network** in the agent container, **prune
      future git refs and remotes** from the checkout. Must happen *before* the first agent run.
- [x] Run one instance **10×** with a neutral scaffold. Done with **pi + Kimi K2.7** on
      `pgmpy__pgmpy-3137` (`2026_03`).
- [x] **Read the dispersion.** → design §10. **Verdict variance is zero (8/8); process variance
      is 3.5x (30–106 turns).**

### What the number changed

- **Resolve rate and file recall are both at ceiling on this task, so neither can measure a scaffold.** Task selection is now a *precondition*, not a cost optimisation.
- **Turns looked like the only metric with headroom**, at ~44% relative sd → **~14 runs per arm** to see a 47% effect, **~31** for a 32% effect. One run per cell measures nothing. **⚠️ Now in doubt** — node retrieval was never really measured. See below.
- **`wall_time_s` is contaminated** by upstream rate-limit backoff (2 of 10 runs died in it) and must not be reported as a signal.

## Next — the control

### 1. ~~Fix the node-retrieval metric~~ — DONE (design §10b)

- [x] Replaced the hunk-header regex with **AST extraction** (`evals/nodes.py`, tree-sitter). The
      old definition read the label git prints in the hunk header — a *rendering artifact of the
      diff*: gold and the agent's patch touched **the same lines of the same file** but were
      rendered by different diff drivers (`def` vs `class`), so the label sets were disjoint by
      construction and the metric could only ever return `0.0`.
- [x] **Re-scored the ten runs. `node_recall` is `1.0`, sd 0** — the agent hits both gold nodes
      (`_ConstraintMixin._build_skeleton`, `_ConstraintMixin._get_potential_sepsets`) on every
      completed run. Cost: zero inference.
- [x] ~~Redo the sample-size maths~~ — **not needed. The hypothesis was wrong.** The fixed metric
      is at *ceiling*, not hiding headroom, so **§10 stands unchanged**: turns remains the only
      metric with room, and ~14–125 runs per arm still holds. §10 was right for a reason it had
      not established; now it has.

**Kept from it — a trap worth not re-learning:** retrieval **precision** is 0.5 on every run because the agent also fixes `pgmpy/estimators/BaseConstraintEstimator.py`, a **genuine parallel implementation** of the same logic (not a deprecated shim) that the gold patch ignores. The repo carries two copies of the bug; the agent fixes both and still passes 8/8. **Precision against a single gold patch measures conformity to one human's fix, not correctness — in any repo with duplicated logic it is noise. Recall is the signal.**

### 2. The K2.6 control — the main question, and now unblocked

**Run Kimi K2.6 (published cutoff 2025-04) on the same instance, same everything.** K2.7-Code shipped 2026-06-12 with no published cutoff and went 8/8 with perfect file recall on a task created 2026-03-22. If K2.6 also cruises, the task is easy. **If it struggles, K2.7 saw the answer** — and that is a result about the benchmark's decontamination premise, not about Kimi.

- [x] LiteLLM config: `kimi-k2.6` added; `glm-5.1`/`glm-5.2` were missing
      `OLLAMA_CLOUD_API_KEY_03` and were silently running on 2/3 of the intended throughput.
- [x] **LiteLLM restarted** (2026-07-14 17:03) and the four models **verified answering** —
      `kimi-k2.6`, `kimi-k2.7`, `glm-5.1`, `glm-5.2`. The container had been up since 07-07,
      *older than its own config*, so `kimi-k2.6` was unroutable while `docker ps` said
      `healthy`. Logged in `llm-workflow/ops/omarchy-log.md`.
- [ ] **Run the K2.6 control 10×.** Nothing blocks it: the proxy is up, the four models answer,
      and the instrument is fixed and proven. **This is the next thing to do.**

## Then — one variable at a time

The full curiosity list is combinatorial (5 agents × skills × scaffold × orchestration × greenfield/brownfield ≈ 80 cells before repeats) and will not close. One variable at a time, paired across ~20–30 instances rather than repeated on one.

**First variable: skills + scaffold on/off.** Chosen because agent-vs-agent is partially covered by [the neuralnoise WIP](https://www.neuralnoise.com/2026/harness-bench-wip/) and *nobody* has published on whether a personal scaffolding layer moves the number.

Then, in no fixed order:
- **Agent harness**: mini-swe-agent · Claude Code · Codex · `pi` · OpenCode.
- **Multi-agent orchestration** (kernl's orchestrator shape) vs a single agent.
- **Greenfield**, which needs a different dataset — Commit0 scores a from-scratch library against a spec + hidden tests, which is Akita's brief with automated scoring.

## Later

- **Build the agent** — ~300 lines in a loop (ghuntley's framing: read · list · bash · edit · search). Objective (3). The benchmark above becomes its test bench.
- **Our own tasks** — objective (2), and only after running someone else's has taught us what a task actually is.

## Open questions

- **Is per-task difficulty derivable from the leaderboard dataset?** Needed for the mid-range (30–70% pass rate) filter. Not confirmed — see design §8.
- **The "6x performance from the harness alone" claim is unverified.** It is the premise of the whole repo and it rests on an unchecked LLM citation. Read the source before it goes anywhere public.
