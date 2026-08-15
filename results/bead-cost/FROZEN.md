# Frozen benchmark artefacts - do not merge, do not sweep

Two branches in `archeion` each carry a **complete, tested solution** to bead `arch-42q`, produced by a benchmark run. They are deliberately not pull requests and deliberately not deleted.

| branch | worktree | commit |
|---|---|---|
| `bugfix/href-entity-decode` | `~/tmp/bead-cost/pilot-kimi-02/home/repositories/.worktrees/archeion/bugfix-href-entity-decode` | `6b743bc` |
| `chore/bead-cost-agy-flash-01` | `~/repositories/.worktrees/archeion/chore-bead-cost-agy-flash-01` | `08cac62` |

**Why they are not merged.** `arch-42q` is the benchmark's subject. Merging either closes the bead and leaves every remaining run measuring a problem that no longer exists, which would end the experiment rather than advance it. The bead stays open until the benchmark is finished.

**Why they are not deleted.** They are the pilot's only evidence. The report beside this file quotes them; a scorer re-run, a rubric correction, or any question about what a lane actually produced needs the trees themselves. The whole reason this experiment keeps raw artefacts is that a metric found wrong later can be repaired by re-reading rather than by paying for the runs again.

**The risk this file exists to prevent.** Both are registered in `archeion`'s worktree list, and one sits under `~/tmp`, where they look exactly like the abandoned worktrees a routine git-hygiene sweep is meant to remove. They are not abandoned. A sweep that cannot tell the difference should read this file, and anyone running one should check for it.

Two more worktrees from the same pilot carry **no** work and are free to remove: `chore/bead-cost-pilot-kimi-01` and `chore/bead-cost-pilot-kimi-02`, both still at the base commit. The launch tree of the kimi run is the second of those - the run moved its work elsewhere, which is the defect that produced `find-work.sh`.
