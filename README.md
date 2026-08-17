# agent-lab

A lab for measuring what actually moves an AI coding agent's performance — the **harness** around a model, not the model alone.

The premise worth testing: the same model can behave very differently depending on the scaffolding it runs inside — the skills it is given, the `AGENTS.md` it reads, whether an orchestrator coordinates several agents, where the rules sit in its context. *How much* of a difference is an open question (one widely-repeated figure puts it as high as 6×, but that number is unverified and treated here as a hypothesis, not a result). This repo is an attempt to measure a small, honest corner of it.

## The questions

Each has no published answer for this specific setup, and each isolates **one variable**:

- **Does a personal agent-scaffolding layer do anything?** Skills on/off, `AGENTS.md` on/off.
- **Does multi-agent orchestration beat a single agent?**
- **Which agent harness is actually better** — mini-swe-agent, Claude Code, Codex, `pi`, OpenCode — for a real, opinionated workflow?
- **Greenfield vs brownfield** — because the answer is probably not the same.

## How it works

- **Benchmark: [SWE-rebench](https://github.com/SWE-rebench/SWE-bench-fork).** Chosen for one reason above all — **decontamination**. It publishes post-training-cutoff task splits, so a measured "scaffolding effect" is not just the model reciting a solution it memorized. It also ships a fixed-scaffolding baseline run 5× per model with error bars, which is the "no scaffolding" control group this lab needs, already measured.
- **Agent-agnostic scoring.** The scorer takes a `predictions.jsonl` of `{instance_id, model, patch}` and evaluates the diff in Docker. Anything that emits a patch can be compared: Claude Code, Codex, OpenCode, `pi`, mini-swe-agent, a custom orchestrator.
- **A sandbox that is part of the instrument.** The agent runs in a container with no route to the internet except a LiteLLM proxy — its brain is reachable, its hands are not. Without that, a task can be "resolved" by fetching the answer, and cheating shows up as a scaffolding win.

## Status — honest

This is a **curiosity project**, early. What exists today:

- The sandbox, the SWE-rebench integration, and a scorer.
- A measured **noise floor** — the run-to-run variance of the same task/agent/config, because if that noise is larger than the effects being hunted, every downstream result is noise with a number attached.
- The hard-won finding that most obvious metrics (resolve rate, retrieval) sit **at ceiling** on the first task and measure nothing; **turns** is the only metric with headroom, and it needs many runs per arm to be significant.

What does not exist yet: the full experiment matrix. The reasoning, the rejected alternatives, and every trap found the hard way are in **[`docs/DESIGN.md`](docs/DESIGN.md)** — the honest part of the project, and the place to start.

## Layout

| path | what |
| --- | --- |
| `docs/DESIGN.md` | the decision record — read this first |
| `docs/qualitative-review.md` | the runbook for judging implementations by how much future work they create, once a deterministic scorer has said they all work |
| `evals/` | runners (`noise_floor.py`, `score_runs.py`, `nodes.py`) and the sandbox |
| `evals/sandbox/` | the network-isolated Docker sandbox + LiteLLM proxy |
| `results/` | committed experiment outputs |

## Running it

Needs Docker and a free read-scoped `HF_TOKEN` (the post-cutoff splits sit behind HuggingFace Xet storage and 401 for anonymous requests — a misleading failure). See `docs/DESIGN.md` §8 for setup. Run `bin/install-hooks` once after clone; `bin/ci` is the gate.

## License

MIT — see [LICENSE](LICENSE).
