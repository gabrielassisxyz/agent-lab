# rule-adherence results

## `opus-reps3.json` (2026-07-24)

The full grid at the rigor the design asks for: 6 tasks x 5 placements x **3 reps**, 90 cells, Claude Opus 4.8. It completed without a crash, and it is a **null result**: all five placements scored *identically*, 15/18 (0.833), with the same single task failing 3/3 everywhere.

The value of this run is the diagnosis, because the null was **guaranteed by construction**. Three independent reasons it could not have produced signal:

- **There is no independent variable.** The corpus holds 4 short rules, so the five placements produce prompts that differ by at most six bullet lines. The published findings this experiment tests (position bias, re-injection) are about *long* contexts, where the prefix and the query are thousands of tokens apart. Moving a rule six lines is not a treatment. The design's own axes (context length, rule distance, turn count) were all collapsed to a single point, and that collapse is the root cause.
- **No headroom.** Five of six tasks pass 3/3 in every arm and one fails 3/3 in every arm. Not one task is decided by placement. This is the same trap the first experiment hit (`docs/DESIGN.md` section 10): a saturated metric measures nothing.
- **The enforcement arm is a no-op.** `hybrid-enforcement` composes text identical to `hybrid` by design, and the runner applies no gate at all; `enforces_gate` only sets a label on the record. So the two arms are the same treatment, and the enforcement hypothesis was never tested. Its one failing task is a conventions task, which the gate would not have covered even if it existed.

Two instrument defects the run also exposed:

- **`conventional_branch` cannot attribute its own failure.** Its `branch is None` branch is unreachable, because `trajectory.read_repo_state` reads `rev-parse HEAD`, which always returns a branch name. So "stayed on the default branch" and "created a badly-named branch" both report `wrong-convention`, and the trace cannot say which happened.
- **Nothing was persisted per cell.** Only the final document was written, so the 18 failures leave no trajectory to audit. That is also why a run that dies partway loses everything it already paid for.

What the run *does* establish: the pipeline drives a real agent through 90 cells and scores genuine trajectories, and on the checkable tasks this model already satisfies the safety, attribution and commit-format rules regardless of placement. Read that as a baseline, not as evidence that placement does not matter. The instrument cannot yet answer the question.

## `smoke-haiku-reps1.json` (2026-07-24)

The first real run of the rule-adherence experiment: the full grid, 6 tasks x 5 placements x **1 rep**, driven by a real agent (Claude Haiku 4.5) via `ClaudeCliAgent`. It exists to prove the pipeline produces real data end to end, and it is **not** a result to draw conclusions from. Two reasons it cannot be:

- **reps = 1, so it is noise, not signal.** `hybrid` and `hybrid-enforcement` compose an identical prompt, yet they diverged (6/6 vs 5/6) on this run. That gap is pure run-to-run variance, and it is exactly the noise floor the design says must be measured (reps >= 3) before any placement is compared. Read the divergence of two identical placements as the proof that a single rep decides nothing.
- **one model.** Position bias is model-dependent (primacy vs recency), so a single model cannot tell you where rules should sit in general. The design calls for at least two model families plus the target model.

What it *does* establish: the whole pipeline runs against a real agent, the deterministic checkers score genuine trajectories, and the failure that showed up (`wrong-convention` on the branch-naming task) is a real, checkable miss, not a harness artifact.

To produce a real result, run with reps >= 3 across at least two model families and read the scores against the pre-registered thresholds in `../../docs/experiments/rule-adherence.md`.
