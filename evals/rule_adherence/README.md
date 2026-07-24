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

## Not done yet

The real sandboxed CLI adapter (drive `claude -p` / `pi` and parse its
`events.jsonl`) is the next increment, deliberately not stubbed. So is the noise
floor for the adherence metric (Phase 2) and the full matrix (Phase 3). The
classify step is a v1 match-by-category; a sharper matcher is future work.

## Run the tests

```sh
python3 -m unittest discover -s evals -p 'test_*.py'
```

## Adding a task

Append to `tasks.json`; point `checker` at a name in the `REGISTRY`. A new rule
category means adding its checker to `checkers.py` (with a code-decidable rule) and
its tests. `test_every_task_references_a_real_checker` fails loudly on a typo'd
checker name.
