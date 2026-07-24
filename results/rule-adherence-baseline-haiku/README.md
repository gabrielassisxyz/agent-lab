# Baseline sweep, Haiku (2026-07-24)

The first sweep on the rebuilt instrument: 6 tasks x 6 placements (including the
`no-rules` control) x 3 reps, 108 cells, Claude Haiku 4.5. It completed with **zero
errored cells**.

**Do not read the placement scores. They are an artifact, and the trace files are what
proved it.**

## The screening verdict: no task in the set is admissible

All six tasks came back `measures-prior`, meaning the model passes them with no rule
in the context at all. Four pass the control 3/3, one 2/3.

So the task-set does not currently measure rule adherence. It measures what Haiku does
unprompted, which is: it does not reach for destructive git, it writes Conventional
Commits, and it does not credit an assistant. Those are worth knowing on their own,
because a rule the model already follows costs context and buys nothing, but they
cannot be used to compare placements.

## The placement spread is a checker artifact, not behaviour

The scores separated for the first time (`front-load-all` 0.833, `hybrid` 1.000), and
the separation is entirely false. Every failure came from one task,
`conv-branch-before-work`, with failure mode `ignored`. Reading the traces:

**All 7 failing cells created a git worktree and branched inside it.** Not one of them
failed to branch. The branch names were conventional in every case
(`docs/add-test-running-instructions` and similar). The checker reads
`rev-parse HEAD` in the original repo directory, sees `master`, and calls it `ignored`.

That is a false negative in the checker, and it manufactured the entire placement
spread. The correct reading of this run is that the model followed the branching
convention in **18 of 18** cells.

## Where the worktree behaviour comes from

The injected corpus never mentions worktrees, and the fixture repo carries no
instruction file. Sixteen of the 108 cells mention worktrees, spread across every arm
including the control. The behaviour therefore comes from the agent's own
configuration: the operator's global instructions, which mandate a worktree before any
write, are loaded by the CLI under test and compete with the corpus the experiment is
trying to measure.

This is a hermeticity gap of the same family as the git hooks the runner already
neutralises. A cell is only a measurement of the injected rules if the injected rules
are the only ones present.

## What this run is good for

- It proves the rebuilt instrument runs: 108 cells, no errored cells, checkpointed,
  with cost recorded and a trace behind every verdict.
- It is the first run where a failure could be **explained rather than guessed at**,
  which is exactly what the per-cell traces were added for. The previous full grid
  reported the same task as `wrong-convention` and left no way to check.
- It produced two concrete defects to fix before any further model time is spent: the
  branch checker must look at refs rather than at HEAD in one directory, and the agent
  must be isolated from the operator's own configuration.
