# AGENTS.md — agent-lab

**What this repo is:** a lab for measuring what actually moves an AI coding agent's performance — the *harness* around a model (skills, `AGENTS.md`, orchestration, prompt/context placement), not the model alone. It runs controlled experiments against a decontaminated benchmark (SWE-rebench) in a sandbox. The design record — every choice and every rejected alternative — is [`docs/DESIGN.md`](docs/DESIGN.md); **read it before touching `evals/`**, because most of it is *why* a thing was rejected, which the code cannot tell you.

## Current scope

Run existing benchmarks end to end to understand how they score an agent, then build our own tasks and experiments on top. Each experiment isolates ONE variable (skills on/off, scaffold on/off, rule placement, harness A vs B). Don't expand beyond "measure agent setups honestly, one variable at a time" without a present need — no hosted service, no multi-user dashboard, no leaderboard-as-a-product. If a change drifts past that, STOP and flag it.

## How to work here

- **The instrument's credibility is the whole point.** Before trusting any delta, the noise floor must be known (run-to-run variance) and the metric must have headroom (not at ceiling/floor). A result that ignores either is noise wearing a number's clothes — `docs/DESIGN.md` §6–§10 is the record of exactly this going wrong and being caught.
- **The sandbox is part of the instrument.** The agent container has no route to the internet except the LiteLLM proxy (its brain is reachable, its hands are not). Never weaken that: no network in the agent container, prune remotes/future refs from the checkout, or a task can be "resolved" by cheating and it shows up as a scaffold win.
- **Decontamination is non-negotiable.** Always assert the `created_at` range of the split you run against the target model's training cutoff — running a contaminated split silently compresses the effect being measured. §9 has the mechanics.
- **Never fabricate a number.** Zeroed costs, `"timeout": true`, SEM/pass@k — the results tables must never contain a value that looks measured but was invented. A fabricated price or a hidden timeout corrupts every downstream conclusion.
- **`bin/ci` green before any PR.** It runs gitleaks (secret scan), shellcheck (shell lint), a Python syntax check, and slop-guard (`--diff` — em-dash/tool-name tells on added lines) — the deterministic gates. Run `bin/install-hooks` once after clone.
- **Conventional Commits**, branch before non-trivial work, what+why in the message, no external attribution. English in files.

## Stack

- **Python** — the runners and scorers (`evals/*.py`); depends on `swebench 4.0.3`. No package manifest yet; it is a set of scripts.
- **Docker** — the sandbox and every benchmark task run inside containers (`evals/sandbox/`).
- **TypeScript** — a single ~36-line `pi` provider shim (`evals/agents/pi-litellm-provider.ts`) that registers the LiteLLM proxy as a provider for one agent-under-test. Not a TS codebase; no toolchain.

## Gotchas

- **An `HF_TOKEN` (any free read-scoped one) is mandatory** and its absence is misleading: the post-cutoff SWE-rebench splits live in `nebius/SWE-rebench-leaderboard`, whose large files sit in HuggingFace Xet storage and **401 for anonymous requests** — it presents as a network/machine problem and is not.
- **The fresh (post-2025) tasks exist ONLY in the leaderboard dataset**, not in the public `nebius/SWE-rebench` (which stops at 2025). Decontamination sits entirely behind that token.
- **Resolve rate and retrieval metrics were at ceiling on the first task** — a saturated metric measures nothing. Turns was the only metric with headroom, and it needs many runs per arm (see §10). Task selection (30–70% historical pass rate) is a precondition, not an optimization.
