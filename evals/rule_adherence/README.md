# rule-adherence — Phase 0 (task-set + checkers)

The first buildable piece of the rule-adherence experiment
([`docs/experiments/rule-adherence.md`](../../docs/experiments/rule-adherence.md)).
No benchmark ships a rule-adherence task-set with deterministic checkers, so this
is the part that has to exist before anything downstream can be trusted.

## What is here

| file | what |
| --- | --- |
| `schema.py` | `Task`, `AgentResult`, `CheckOutcome`, the closed `FAILURE_MODES` set, `load_tasks` |
| `checkers.py` | the deterministic checkers + the name→function `REGISTRY` |
| `tasks.json` | the task-set: each task is `(instruction, triggered rule, checker)` |
| `test_checkers.py` | unit tests — a pass, a fail, and the surface-compliance case per checker |

## The design rule

A checker decides from the **trace** (`AgentResult`) in code — a regex over the
commands, the branch name, the commit text. Never a second model judging the
first. A rule whose adherence is not decidable this way gets no checker and no
task: a metric with no ground truth measures nothing, the same headroom lesson the
first experiment learned.

`no_destructive_git` splits the two failure modes the experiment cares about most:
running a forbidden command and **owning it** (`violation`) versus running it while
reporting success without disclosing it (`surface-compliance`) — the illusion of
compliance, which is why adherence is scored two ways.

## What Phase 0 is not

It does not run agents. `Task.setup` (the shell that stages repo state) is inert
here; executing it, driving an agent under each placement, and reducing its
trajectory into an `AgentResult` is Phase 1 (the runner). Phase 0's contract is
that the checkers are correct *before* a real trajectory exists — which the tests
establish against synthetic results.

## Run the tests

```sh
python3 -m unittest evals.rule_adherence.test_checkers
```

## Adding a task

Append to `tasks.json`; point `checker` at a name in the `REGISTRY`. Adding a new
rule category means adding its checker to `checkers.py` (with a code-decidable
rule) and its tests. The `test_every_task_references_a_real_checker` test fails
loudly on a typo'd checker name.
