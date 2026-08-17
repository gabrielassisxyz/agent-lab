# Eight arms reviewed, and the packet that got bigger stopped resolving

Forty-five review calls over nine blinded implementations of `llmux-p4-two-phase-reservation-5vg` - eight arms plus the commit that actually landed the bead. The question is the one no deterministic tool answers: **how much future work did this implementation create for whoever extends this package next?**

Three reviewers, not four. `codex` (GPT-5.6 Sol), GLM-5.2 through `pi`, and Claude Opus. The Google reviewer was dropped because it runs `gemini-3.1-pro-high`, which is now an arm in the packet, and the same model reading its own code is not a second opinion. The other Google id in reach is also an arm, so the family had nothing to fall back to.

**Read the ranking against the floor before believing any of it.** On this packet the floor is worse than it has ever been measured, and that is the first result.

## The measurement floor doubled when the packet did

Three passes of the comparative call over the SAME packet - same entries, same lettering, same prompts, same accounts. Everything that differs between them is the panel disagreeing with itself.

| entry | positions | swing | mean-rank drift |
| --- | --- | --- | --- |
| deepseek-pro-max | 1, 1, 1 | **0** | 0.00 |
| deepseek-pro-high | 2, 2, 2 | **0** | 0.00 |
| kimi-k2.7 | 3, 4, 3 | 1 | 0.33 |
| sonnet | 4, 3, 4 | 1 | 0.67 |
| deepseek-flash-high | 5, 5, 6 | 1 | 1.00 |
| gemini-3.7-flash | 6, 6, 5 | 1 | 0.33 |
| reference commit `3d6a5a2` | 7, 8, 7 | 1 | 0.67 |
| gpt-5.6-terra | 9, 7, 8 | **2** | 1.00 |
| gemini-3.1-pro-high | 8, 9, 9 | 1 | 0.67 |

On the five-entry packet this same measurement moved **no position at all**, with mean rank wandering by 0.5. On nine entries it moves one position almost everywhere and two in one place, and the drift reaches 1.0.

The packet went from about 32 KB to 59.6 KB and the call count did not change, so each entry got a smaller share of the same attention. That was written down as an open question and is now measured: **a gap under one full rank position is not something this packet resolves.**

## The ranking, replicated

Five packets, each holding a **different run of every arm**, drawn without replacement from seed `20260818`.

| arm | rep 1 | rep 2 | rep 3 | rep 4 | rep 5 | mean | swing |
| --- | --- | --- | --- | --- | --- | --- | --- |
| sonnet | 3 | 2 | 2 | 1 | 5 | **2.60** | 4 |
| deepseek-pro-high | 2 | 1 | 4 | 4 | 3 | **2.80** | 3 |
| deepseek-pro-max | 7 | 5 | 1 | 2 | 1 | **3.20** | 6 |
| deepseek-flash-high | 1 | 3 | 8 | 3 | 2 | **3.40** | 7 |
| gemini-3.7-flash | 4 | 7 | 6 | 5 | 4 | 5.20 | 3 |
| gpt-5.6-terra | 8 | 4 | 7 | 6 | 6 | 6.20 | 4 |
| kimi-k2.7 | 5 | 6 | 5 | 9 | 7 | 6.40 | 4 |
| reference commit `3d6a5a2` | 6 | 9 | 3 | 8 | 8 | 6.80 | 6 |
| gemini-3.1-pro-high | 9 | 8 | 9 | 7 | 9 | **8.40** | 2 |

**Kendall W = 0.56**, Friedman chi2 22.35, df 8, **p = 0.0043**, blocks independent.

Read against a floor of one rank position, three things are sayable and nothing else is:

- **The top is a four-way tie.** Sonnet, deepseek pro-high, pro-max and flash-high sit inside 0.8 of a rank of each other. That is narrower than the floor.
- **The bottom is `gemini-3.1-pro-high`**, at 8.40 with the smallest swing in the table. It is the only position replication confirms.
- **The middle is a cluster** - gemini-3.7-flash, gpt-5.6-terra, kimi-k2.7 and the reference between 5.2 and 6.8, inside each other's noise.

## What one packet said, and why it was wrong

The single packet built from each arm's median run reported this, unanimously at the top:

```
1. deepseek-pro-max (1.00)   2. deepseek-pro-high (2.33)   3. kimi-k2.7 (4.00)
4. sonnet (4.00)             5. deepseek-flash-high (5.33) 6. gemini-3.7-flash (6.00)
7. reference (7.33)          8. gemini-3.1-pro-high (7.33) 9. gpt-5.6-terra (7.67)
```

Across five replicates `deepseek-pro-max` lands 7, 5, 1, 2, 1 - a swing of six positions. `deepseek-flash-high` swings seven. The first place was a property of the run that was drawn, not of the arm behind it, and it took twenty more calls to find that out.

An obvious explanation was tested and does not hold. Three arms are internally split: some of their runs remove pre-existing public API and some do not, so a replicate could be drawing one of two different behaviours. Crossing every replicate position with that flag, `deepseek-pro-max` runs that removed the API occupy both first place and seventh. The within-arm variance is real and this is not what causes it.

## The question the scorer cannot answer, and the panel split on it

Two entries in the packet removed exported declarations that existed before the task - `ReserveRateSlot`, `ReleasePendingRateSlot`, `FinalizeDispatch`, `IncrementInFlight` - none of which has a caller in production code, only in the package's older tests. The absolute pass asked whether that is a simplification or a breaking change.

Both reviewers identified exactly the two entries that did it, and named the same methods. Then they disagreed, the same way, twice:

> **codex, on both:** "removed without replacement-compatible entry points" - **breaking change**
>
> **GLM, on both:** "removed and replaced by a single `Reserve` that folds rate, gate, health and in-flight into one critical section, eliminating the compositional burden the old entry points forced on every caller" - **simplification**

Seven entries, both reviewers, `untouched` - which is correct for all seven.

That the two of them agree on the facts and split on the judgement is the answer worth having: it is not a question with a hidden right answer that the scorer was failing to compute. It is a design trade-off, and the cost table already prices one side of it - the runs that removed the old API spent between 1.7x and 2x the turns and up to 3x the output of the ones that did not.

## Self-preference, now asked per entry

Both conflicted reviewers favoured their own family's entry:

| reviewer | its family's entry | placed it | the clean reviewers placed it | |
| --- | --- | --- | --- | --- |
| opus | sonnet | 3rd | 4.50 | FAVOURED |
| codex | gpt-5.6-terra | 6th | 8.50 | FAVOURED |

Both gaps are around 1.5 positions, in the expected direction, on the first packet where the question could be asked of two reviewers at once. It is why the baseline is computed per entry from the readers that share no lineage with it, rather than from a fixed pair.

The blinding held: all three answered the check without naming an entry from their own family.

## Findings are not reproducible, and that is now measured too

Five entries in this packet are **byte-identical** to entries reviewed on 2026-08-16, by the same two reviewers on the same models. Comparing the two absolute passes:

| entry | codex, then and now | GLM, then and now | same files? |
| --- | --- | --- | --- |
| deepseek-pro-high | 0 / 0 | 2 / 1 | yes |
| gemini-3.7-flash | 1 / 0 | 4 / 3 | yes |
| kimi-k2.7 | 1 / 0 | 2 / 3 | yes |
| reference `3d6a5a2` | 0 / 1 | 4 / 3 | yes |
| sonnet | 2 / 0 | 2 / 1 | no |

`codex` changed its answer on four of five, twice going from a finding to none and once from none to a finding. GLM changed its count on every one of them but pointed at the same files in four of five.

**The prompt was not identical between the two runs** - the newer one dropped a claim that had stopped being true and added the question above - so this confounds prompt change with reviewer variance and is an upper bound on stability rather than a clean measurement. Even as an upper bound it says the same thing the runbook already said for a different reason: a finding count is not a quality score. What survives repetition is roughly *where* a reviewer looks, not *how much* it reports.

## What this does not say

- **Positions from different packets do not compare.** The nine-entry ordering and the five-entry ordering from 2026-08-16 are separate measurements of separate sets.
- **The reference is not a control.** It came out of the same kind of agent run as the candidates, so its position - 6.80, mid-table, swinging six - is a claim about that implementation and falsifies nothing.
- **This is one bead**, chosen so that every arm can pass it. Nothing here separates arms by capability, and the ranking is about the shape of a solution rather than about whether one exists.
- **Three reviewers is thinner than four.** Losing the Google reader cost one ordering and the ability to ask whether it favours its own family, and no arm's position should be read as if the panel were unchanged.
