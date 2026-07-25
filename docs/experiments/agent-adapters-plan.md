---
status: plan
---

# Implementation plan: additional agent adapters (pi, codex, agy)

> A self-contained plan for a fresh session. Goal: add three more agent adapters to the rule-adherence experiment so it can drive families other than Claude. Read `rule-adherence.md` (the experiment design) and `../../evals/rule_adherence/README.md` (the code map) first; everything you need to implement this is restated below so you do not have to reconstruct it from a conversation.

## Why this exists

Only one adapter exists today, `ClaudeCliAgent` (`evals/rule_adherence/cli_agent.py`). It drives the `claude` CLI, so every model it can reach is a Claude model, and Claude is a single position-bias family (recency-leaning, per the MOSAIC finding cited in the design). The experiment's whole cross-model question ("where should rules sit in context, in general") needs at least one **primacy-leaning** family to compare against. Those models (for example `deepseek-v4-pro-max`) are reachable through the local LiteLLM proxy, which the `claude` CLI does not use. Hence new adapters.

Three targets, in priority order:

1. **PiCliAgent** drives `pi`, which reaches LiteLLM models (deepseek, glm, kimi) via the provider extension this repo already ships. This is the one that unlocks the cross-family run, so it is first.
2. **CodexAgent** drives `codex exec`; a second path to LiteLLM and to the OpenAI family.
3. **AgyAgent** drives `agy`; lowest priority and highest risk (see its gate).

A secondary payoff: the experiment design also wants to compare *harnesses*, not only models. Three more real adapters is exactly that surface.

## The contract you are implementing against (unchanged)

The `Agent` protocol (`evals/rule_adherence/agent.py`):

```python
class Agent(Protocol):
    def run(self, prompt: str, repo_dir: Path) -> list[Event]: ...
```

An `Event` is a dict of one of three shapes:

```python
{"type": "command", "command": "<shell command the agent ran>"}
{"type": "read",    "path": "<file the agent read>"}
{"type": "message", "text": "<the agent's final message>"}
```

`ClaudeCliAgent` is the template. Its shape is the pattern every adapter copies:

- a **pure parser** `parse_<agent>_stream(lines) -> list[Event]`, unit-tested against a captured fixture transcript, no model call;
- a thin **adapter dataclass** whose `run()` shells out to the CLI, captures stdout, and calls the parser.

Everything downstream is reused unchanged and must not be touched: `trajectory.build_result` (reduces events + repo state into an `AgentResult`), the checkers, `runner.run_task`, `matrix.run_matrix`, `scoring.score`, and `run.py`. A new adapter is additive.

## The load-bearing architectural decision: decouple command capture

**Problem.** Each CLI exposes what the agent did differently, and one target (`agy`) has no structured-output flag at all. Parsing every CLI's transcript for the exact commands it ran is the riskiest, least portable part of each adapter.

**Insight.** Only one checker needs the command list. The dependency is:

| checker | needs `commands` | needs repo state (commits/branch/patch) |
| --- | --- | --- |
| `no_destructive_git` | YES | no |
| `conventional_commit` | no | YES |
| `conventional_branch` | no | YES |
| `no_assistant_attribution` | no | YES |

Repo state is read from git by `trajectory.read_repo_state`, independent of the agent. So three of four checkers work for **any** adapter that merely runs the agent, with no transcript parsing at all. Only `no_destructive_git` needs commands, and the commands it cares about are **git** commands.

**Decision (shared component S1): an agent-agnostic git-command shim.** A tiny wrapper `git` placed on a shim directory, prepended to `PATH` in the environment the agent subprocess sees. It appends its `argv` to a log file, then execs the real git. The runner reads that log for `commands`. This captures exactly the top-level git commands the agent issued, regardless of which CLI ran, and makes `no_destructive_git` robust even for an agent whose transcript reveals nothing.

- With the shim, a new adapter's parser only has to produce the **final message** (and, optionally, reads). Commands come from the shim. That collapses the per-adapter risk.
- The shim is **optional where a CLI already emits tool events** (`claude`, and likely `pi --mode json`): those adapters can parse commands directly, and the shim is a belt-and-suspenders cross-check. It is **required** wherever a CLI does not (`agy`).
- Trade-off: the shim captures git only, not arbitrary bash. That is sufficient for the current checkers (the only command-based one is git-specific). If a future checker needs non-git commands, extend the shim to also wrap `bash`/`sh` the same way.
- Protocol change this implies: the `Agent.run` signature gains an optional `env` parameter (`run(self, prompt, repo_dir, env=None)`), so the runner can pass the shimmed `PATH`. `FakeAgent` ignores it; `ClaudeCliAgent` forwards it to `subprocess`. This is a small, backward-compatible extension. Update `FakeAgent`, `ClaudeCliAgent`, and `runner._run_in` accordingly, and keep all existing tests green.

## Shared prerequisites (do these first; they block all three adapters)

### S1 - the git shim + protocol env parameter

- Add `evals/rule_adherence/gitshim.py`: a helper that creates a shim dir with an executable `git` wrapper (logs `"$@"` to `$AGENT_LAB_GIT_LOG`, then `exec` the real git found by skipping the shim dir on `PATH`), and returns `(shim_dir, log_path)`.
- Extend the `Agent` protocol and both existing agents with an optional `env` arg.
- In `runner._run_in`: build the shim before the agent runs, pass `env` with the shimmed `PATH` and `AGENT_LAB_GIT_LOG`, and after the run read the log into `commands`, merging with any commands the adapter's parser already produced (dedupe by order, prefer the parser's when both exist).
- Tests: `test_gitshim.py` proves the wrapper logs a git invocation and execs real git; a runner test proves a `FakeAgent` that runs `git clean -fd` is caught via the shim path even if it emits no command event.

### S2 - an agent registry and a `--agent` flag

- `run.py` hardcodes `ClaudeCliAgent`. Add an agent registry (name -> factory) and a `--agent {claude,pi,codex,agy}` flag; keep `claude` the default so nothing changes for existing runs. Each factory reads `--model` and any agent-specific env.
- Test: `run_and_report` already takes an `agent_for`; add a small test that the registry resolves each name to a callable and raises on an unknown one.

S1 and S2 are independent of each other and can be done in parallel.

## Per-adapter work (each independent after S1 + S2)

Every adapter follows the same three steps: **discover** the CLI's real behavior, **build** parser + adapter, **test** the parser against a captured fixture. Each ends at a **go/no-go gate** so a dead end is reported, not forced.

### P - PiCliAgent (first; unlocks the cross-family run)

Grounded facts (from `pi --help`): `-p` / `--print` is non-interactive; `--mode json` emits structured output; `--provider`/`--model provider/id` select the model; `-e` loads an extension; `--no-session` keeps it ephemeral. This repo ships `evals/agents/pi-litellm-provider.ts`, which registers a `litellm` provider reading `LITELLM_BASE_URL` and `LITELLM_API_KEY`.

- **Discover:** run `pi -p --mode json --no-session -e evals/agents/pi-litellm-provider.ts --provider litellm --model litellm/deepseek-v4-pro-max "list files"` in a scratch git repo with the LiteLLM env set. Capture the JSON. Identify: the block that carries a `bash` tool call (its command), a `read` tool call (its path), and the final assistant text. Save a trimmed sample as `tests` fixture.
- **Build:** `parse_pi_stream(lines) -> list[Event]` mapping pi's json events to the three event types; `PiCliAgent(model, extra_args, timeout_s)` whose `run` shells out as above and passes the shim `env`. If pi's json exposes commands, use them; the shim is the cross-check.
- **Test:** `test_pi_agent.py` runs the parser over the fixture; assert commands, reads, final text. Do not call pi live in CI.
- **Gate:** if `--mode json` does not actually expose tool calls, fall back to the shim for commands and parse only the final message from the text mode; if pi cannot reach LiteLLM at all, stop and report (the litellm provider is the reason to build this one).

### C - CodexAgent

Grounded facts (from `codex --help`): `codex exec` runs non-interactively; it has a JSON output mode (confirm the exact flag during discovery, e.g. `codex exec --json`); `--model` selects the model; a LiteLLM/OpenAI-compatible endpoint is configured via `~/.codex` config or `OPENAI_BASE_URL`/`OPENAI_API_KEY` env.

- **Discover:** run `codex exec --json --model <id> "list files"` in a scratch repo, pointed at LiteLLM via env/config. Capture the JSONL event stream; identify command, read, and final-message events. Save a fixture.
- **Build / Test / Gate:** same shape as P. Gate: if `codex exec` cannot be pointed at a non-OpenAI endpoint, it still gives the OpenAI family as a data point, which is useful; keep it, do not block on LiteLLM.

### A - AgyAgent (last; highest risk)

Grounded facts (from `agy --help`): `-p` / `--print` runs one prompt non-interactively; `--dangerously-skip-permissions` auto-approves tools; `--model`, `--agent`, `--sandbox`, `--log-file` exist. There is **no json/structured-output flag** in help, so the command list is the problem case this plan's shim exists for.

- **Discover:** run `agy -p --dangerously-skip-permissions --model <id> "list files"` in a scratch repo. Check whether `--log-file` yields a parseable action log; run `agy models` to see which providers/models it can reach (is LiteLLM among them?).
- **Build:** `AgyAgent(model, extra_args)` whose `run` takes the final response text from stdout as the message event, and relies on the **git shim** for commands (the whole reason S1 is a prerequisite). Reads are best-effort (skip if unavailable).
- **Test:** if there is any structured log, test its parser against a fixture; otherwise the adapter has no parser to unit-test and its correctness rests on S1's shim tests plus a documented manual smoke run.
- **Gate:** if `agy -p` cannot run a coding task headlessly without hanging, or cannot reach a useful model, report it as not-viable and stop. Do not spend effort forcing it.

## Sequencing and dependencies

```
S1 (git shim + env)  ┐
                     ├─> P (pi) ──> the cross-family run becomes possible
S2 (registry + flag) ┘        └──> C (codex) ─┐
                                  A (agy) ─────┴─> full harness comparison
```

- S1 and S2 first, in parallel. They are the only shared work.
- Then P, C, A are independent of one another. A swarm can take all three at once; a single session should do P first (it is the one with a clear payoff), then C, then A.
- Nothing here touches the checkers, the runner's scoring, or the matrix, so no adapter can regress another.

## Test and CI bar (non-negotiable, matches the repo)

- Each parser is unit-tested against a **captured fixture transcript**, never a live call. The live call is integration and stays out of `bin/ci`.
- The shim and the registry get their own tests.
- Keep `bin/ci` green: gitleaks, shellcheck, `py_compile`, the unittest suite, and slop-guard `--diff`. Write comments and docstrings in ASCII with no long dash, or slop-guard fails on the added lines.
- Update `evals/rule_adherence/README.md`'s file table and the `local/BACKLOG.md` phase entries as each adapter lands.

## Definition of done

- `python3 -m evals.rule_adherence.run --agent pi --model deepseek-v4-pro-max --reps 3` writes a `results.json`, and its scores can be placed next to the Claude run for the first real cross-family comparison.
- `codex` and `agy` adapters either work the same way or are documented as not-viable with the reason, so no future session re-litigates them from scratch.

## Risks and open questions

- **Command capture per CLI.** Mitigated by S1 for the git-based checker; a checker that needs non-git commands would need the shim widened.
- **LiteLLM auth/env for pi and codex.** The provider extension and codex config both read env; confirm the exact variable names during discovery and never commit a key (gitleaks + slop-guard both run).
- **agy headless feasibility.** It may not run a coding task non-interactively in a way that produces a usable trajectory. That is why it is last and hard-gated.
- **Hermetic temp repo interaction.** Each CLI has its own permission model; confirm each runs to completion without prompting (the flags above are the starting point) and does not hang, or a cell blocks until the adapter's timeout.
