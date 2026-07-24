# rule-adherence experiment

The runnable core of the rule-adherence experiment
([`docs/experiments/rule-adherence.md`](../../docs/experiments/rule-adherence.md)).
No benchmark ships a rule-adherence task-set with deterministic checkers, so this
is the part that has to exist before anything downstream can be trusted.

## What is here

Phase 0 (the task-set and checkers) and Phase 1 (the runner pipeline):

| file | what |
| --- | --- |
| `schema.py` | `Task`, `AgentResult`, `CheckOutcome`, the closed `FAILURE_MODES` set, `load_tasks` |
| `checkers.py` | the deterministic checkers + the name-to-function `REGISTRY` |
| `tasks.json` | the task-set: each task is `(instruction, triggered rule, checker)` |
| `placements.py` | compose the prompt under each of the five placements; the classify-by-category matcher |
| `corpus.sample.json` | a small vendored rule corpus (id, category, trigger, text) for the composer |
| `agent.py` | the `Agent` adapter protocol + `FakeAgent` (a real test double) |
| `trajectory.py` | reduce a trajectory + the repo the agent left behind into an `AgentResult` |
| `runner.py` | `run_task`: stage setup, compose, drive the agent, reduce, check |
| `matrix.py` | `run_matrix`: every task under every placement, repeated; results document |
| `scoring.py` | aggregate outcomes into a per-placement score (pass rate + failure-mode histogram) |
| `cli_agent.py` | `parse_claude_stream` + `ClaudeCliAgent`: drive a real agent CLI and reduce its transcript |
| `run.py` | the experiment entrypoint: run the matrix with a real agent and write `results.json` |
| `test_*.py` | unit + end-to-end tests (a pass, a fail, and the surface-compliance case) |

## The design rule

A checker decides from the **trace** (`AgentResult`) in code: a regex over the
commands, the branch name, the commit text. Never a second model judging the
first. A rule whose adherence is not decidable this way gets no checker and no
task, because a metric with no ground truth measures nothing.

`no_destructive_git` splits the two failure modes the experiment cares about most:
running a forbidden command and **owning it** (`violation`) versus running it while
reporting success without disclosing it (`surface-compliance`), the illusion of
compliance, which is why adherence is scored two ways.

## The runner pipeline (Phase 1)

`run_task(task, placement, agent, corpus)` is one cell of the matrix:

1. stage a throwaway git repo and run `task.setup` (the starting state),
2. capture the base sha, so only the agent's own commits are attributed to it,
3. `compose` the prompt for the placement over the rule corpus,
4. drive the `Agent`, reduce its trajectory + the repo it left into an `AgentResult`,
5. run the checker.

The repo is **hermetic**: hooks point at an empty dir, so the operator's global git
hooks never fire and skew a cell. `FakeAgent` is a real test double, not a mock: it
executes its scripted commands inside the repo, so the pipeline is proven end to end
with no model call.

## The matrix and scoring (Phase 3/4)

`run_matrix(tasks, corpus, agent_for, placements, reps)` runs every cell and
`score(outcomes)` aggregates them into one `PlacementScore` per placement (pass
rate + a histogram of failure modes). `agent_for` is a factory called once per
cell, because a real agent needs a fresh invocation per run and the noise floor is
the variance across a cell's reps. With a deterministic agent that variance is zero
by construction, which is exactly why the real, stochastic agent is what makes the
noise floor (Phase 2) meaningful; the aggregation is proven now with a fake agent.

## Running it for real

`run.py` drives the matrix with `ClaudeCliAgent` and writes `results.json`:

```sh
python3 -m evals.rule_adherence.run --reps 3 --model <id> --out results/rule-adherence
```

This makes real model calls and should run inside the sandbox, so it is not part of
`bin/ci`. What CI covers is the reduction logic (`parse_claude_stream` against a
fixture transcript) and the full pipeline through a fake agent, so everything except
the live call is verified.

A first real run exists at `results/rule-adherence/smoke-haiku-reps1.json` (full
grid, Haiku, reps=1). It proves the pipeline produces real data, and it doubles as a
warning: two identically-composed placements diverged on it, which is the reps=1
noise the design says to measure away before comparing anything. See that folder's
README.

## Not done yet

The live runs themselves: Phase 2 (the adherence noise floor, which is just
`--reps N` against the stochastic agent and reading the variance) and the
pre-registered threshold decision (Phase 4) are operations on top of `run.py`, not
new code. A second real adapter (`pi`, codex) is the same shape as `ClaudeCliAgent`; the
full plan for the `pi`, `codex`, and `agy` adapters (with the shared git-shim
design) is in [`../../docs/experiments/agent-adapters-plan.md`](../../docs/experiments/agent-adapters-plan.md).
The classify step is a v1 match-by-category; a sharper matcher is future work.

## Run the tests

```sh
python3 -m unittest discover -s evals -p 'test_*.py'
```

## Adding a task

Append to `tasks.json`; point `checker` at a name in the `REGISTRY`. A new rule
category means adding its checker to `checkers.py` (with a code-decidable rule) and
its tests. `test_every_task_references_a_real_checker` fails loudly on a typo'd
checker name.
