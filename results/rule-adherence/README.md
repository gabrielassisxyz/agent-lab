# rule-adherence results

## `smoke-haiku-reps1.json` (2026-07-24)

The first real run of the rule-adherence experiment: the full grid, 6 tasks x 5 placements x **1 rep**, driven by a real agent (Claude Haiku 4.5) via `ClaudeCliAgent`. It exists to prove the pipeline produces real data end to end, and it is **not** a result to draw conclusions from. Two reasons it cannot be:

- **reps = 1, so it is noise, not signal.** `hybrid` and `hybrid-enforcement` compose an identical prompt, yet they diverged (6/6 vs 5/6) on this run. That gap is pure run-to-run variance, and it is exactly the noise floor the design says must be measured (reps >= 3) before any placement is compared. Read the divergence of two identical placements as the proof that a single rep decides nothing.
- **one model.** Position bias is model-dependent (primacy vs recency), so a single model cannot tell you where rules should sit in general. The design calls for at least two model families plus the target model.

What it *does* establish: the whole pipeline runs against a real agent, the deterministic checkers score genuine trajectories, and the failure that showed up (`wrong-convention` on the branch-naming task) is a real, checkable miss, not a harness artifact.

To produce a real result, run with reps >= 3 across at least two model families and read the scores against the pre-registered thresholds in `../../docs/experiments/rule-adherence.md`.
