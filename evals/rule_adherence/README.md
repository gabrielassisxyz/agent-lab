# rule-adherence experiment

The runnable core of the rule-adherence experiment
([`docs/experiments/rule-adherence.md`](../../docs/experiments/rule-adherence.md)).
No benchmark ships a rule-adherence task-set with deterministic checkers, so this
is the part that has to exist before anything downstream can be trusted.

## What is here

Phase 0 (the task-set and checkers) and Phase 1 (the runner pipeline):

| file | what |
| --- | --- |
| `schema.py` | `Task`, `AgentResult`, `Usage`, `CheckOutcome`, the closed `FAILURE_MODES` set, `load_tasks` |
| `checkers.py` | the deterministic checkers + the name-to-function `REGISTRY` |
| `destructive.py` | the destructive-git patterns, shared by the checker and the enforcement gate |
| `tasks.json` | the task-set: each task is `(instruction, triggered rule, checker)` |
| `placements.py` | compose the session under each placement, at a chosen distance (`Axes`); the classify-by-category matcher |
| `context.py` | the distance filler: inert padding within a turn and across turns |
| `corpus.sample.json` | a small vendored rule corpus (id, category, trigger, text) for the composer |
| `agent.py` | the `Agent` adapter protocol (session + env), `AgentRun`, and `FakeAgent` (a real test double) |
| `gitshim.py` | capture the agent's git commands, and block the destructive ones for the enforcement arm |
| `trajectory.py` | reduce a trajectory + the repo the agent left behind into an `AgentResult` |
| `runner.py` | `run_task`: stage setup, compose, install the shim, drive the agent, reduce, check |
| `matrix.py` | `run_matrix`: every task, placement and axis point, repeated; results document |
| `checkpoint.py` | per-cell durability: record each cell as it finishes, resume from what is on disk |
| `screening.py` | the admission test: which tasks are entitled to be in a placement comparison |
| `scoring.py` | per-placement scores, and `decay`: the pass rate as a function of distance |
| `cli_agent.py` | `parse_claude_stream` + `ClaudeCliAgent`: drive a real agent CLI across turns and reduce its transcript |
| `run.py` | the experiment entrypoint: run the grid, resume it, or describe it with `--dry-run` |
| `test_*.py` | unit + end-to-end tests (a pass, a fail, the surface-compliance case, the gate, and resume) |

## The design rule

A checker decides from the **trace** (`AgentResult`) in code: a regex over the
commands, the branch name, the commit text. Never a second model judging the
first. A rule whose adherence is not decidable this way gets no checker and no
task, because a metric with no ground truth measures nothing.

`no_destructive_git` splits the two failure modes the experiment cares about most:
running a forbidden command and **owning it** (`violation`) versus running it while
reporting success without disclosing it (`surface-compliance`), the illusion of
compliance, which is why adherence is scored two ways.

## The runner pipeline

`run_task(task, placement, agent, corpus, axes, rep)` is one cell of the matrix:

1. stage a throwaway git repo and run `task.setup` (the starting state),
2. capture the base sha **and the base branch**, so only the agent's own work is
   attributed to it and "never branched" stays distinguishable from "branched badly",
3. install the git shim (blocking, when the placement is the enforcement arm),
4. `compose` the session for the placement and the axes over the rule corpus,
5. drive the `Agent` across its turns, reduce its trajectory + the repo it left into
   an `AgentResult`,
6. run the checker.

The repo is **hermetic**: hooks point at an empty dir, so the operator's global git
hooks never fire and skew a cell. The shim and its log live **beside** the repo, never
inside it, or the instrument would be planting the untracked file that a "clean up the
stray files" task is then scored on. `FakeAgent` is a real test double, not a mock: it
executes its scripted commands inside the repo, so the pipeline is proven end to end
with no model call.

## The three things that make a result mean something

**The control arm.** `no-rules` composes the instruction with no rule text anywhere. A
task that passes it is not measuring rule adherence, it is measuring what the model
does unprompted. `screening.py` turns that into a verdict per task: `admissible`,
`measures-prior`, or `unreachable-by-text` (fails even with the rule next to the
query, which is the evidence for gating that rule instead of rewording it).

**Distance.** `Axes(turns=N, filler_tokens=K)` puts real space between the rule and the
moment it decides something, within a turn and across turns. Filler is **identical in
every arm** so that placement is never confounded with context length, and it is
**inert** by construction and by assertion: padding that mentioned a git command would
be logged by the shim and charged to the agent, silently turning every safety cell into
a false violation.

**Enforcement that enforces.** The `hybrid-enforcement` arm installs the shim in
blocking mode, so a destructive command is refused and the agent reads a correction.
Before this, the arm composed the same text as `hybrid` and applied nothing but a label,
so the hypothesis it is named after had never been tested.

## Durability

Every cell is appended to `cells.jsonl` under `--out` the moment it finishes, with its
trajectory written to `traces/`. Re-invoking the same command resumes: finished cells
are skipped, errored ones are retried. A kill costs at most the cell in flight, and a
run that never finished can still be scored from its checkpoint.

An agent call that fails is recorded as **errored**, never scored. An empty trajectory
satisfies every "did not do the forbidden thing" checker, so a rate-limited or
timed-out call would otherwise be written down as perfect adherence.

## The matrix and scoring (Phase 3/4)

`run_matrix(tasks, corpus, agent_for, placements, reps)` runs every cell and
`score(outcomes)` aggregates them into one `PlacementScore` per placement (pass
rate + a histogram of failure modes). `agent_for` is a factory called once per
cell, because a real agent needs a fresh invocation per run and the noise floor is
the variance across a cell's reps. With a deterministic agent that variance is zero
by construction, which is exactly why the real, stochastic agent is what makes the
noise floor (Phase 2) meaningful; the aggregation is proven now with a fake agent.

## Running it for real

Look at the grid before paying for it. `--dry-run` calls no model:

```sh
python3 -m evals.rule_adherence.run --dry-run --reps 3 --turns 1,5,20,50 --filler 0,8000,32000
```

The baseline sweep, which is also the task screener (all arms, one axis point):

```sh
python3 -m evals.rule_adherence.run --reps 3 --model <id> --out results/rule-adherence
```

Then one axis at a time, over the tasks the screening admitted:

```sh
python3 -m evals.rule_adherence.run --reps 3 --model <id> \
  --tasks <admissible ids> --placements hybrid,jit-near-query \
  --turns 1,5,20,50 --out results/rule-adherence-turns
```

Re-running the same command resumes it. `--out` is the identity of a run, not just a
destination.

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
new code.

**The task-set is the remaining bottleneck.** Three categories are covered
(safety-critical, non-standard conventions, attribution); the design calls for seven,
at roughly five tasks each, every one with a deterministic checker. Until then the
screening will admit only a handful of tasks, which bounds how much any sweep can say.

**The adapters.** `pi`, `codex` and `agy` are the cross-family coverage the position
question needs, and the full plan is in
[`../../docs/experiments/agent-adapters-plan.md`](../../docs/experiments/agent-adapters-plan.md).
The protocol change that plan anticipated (an `env` parameter for the shim) has landed
here together with the session shape, so the three adapters can now be written once
against a signature that will not move under them.

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
