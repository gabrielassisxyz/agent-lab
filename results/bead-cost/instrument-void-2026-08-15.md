# The canonical verification does not discriminate

**Every verdict this harness has produced is void.** Not wrong in one direction, not noisy: the check returns the same answer for a tree carrying a complete fix and a tree that was never touched. Read this before quoting any `section_a` from any run, including the ones in `round-2.md`.

The runs themselves are **not** void. Their diffs, trajectories and token counts are real and re-scorable the moment the check works again, which is the whole reason this experiment keeps raw artefacts instead of summaries.

## The measurement

Four trees, one scorer, per-tree build directories:

| tree | carries the fix? | verdict |
|---|---|---|
| `probe-iso-03/archeion` | no, untouched base `6edbb8e` | **5/5** |
| `deepseek-max-01/archeion` | no, untouched base | **5/5** |
| `glm52-02/archeion` | no, untouched base | **5/5** |
| `agy-flash-02/archeion-arch-42q` | yes, complete, suite green | **5/5** |

The same four under one shared build directory return `a1 true, a2 false, a3 true, a4 false, a5 false` - base trees and fixed tree alike, stable across four repetitions of the same tree.

So the build directory decides *which* uniform answer comes out. It does not decide whether the check can tell a fix from its absence, and in neither condition can it.

Neither answer matches what the pilot recorded for this base commit either, which was `a1 true` and the remaining four false. That signature no longer reproduces under any configuration tried.

## The defect that was found on the way, and is real but not this

The scorer built every tree in one shared cargo target directory. Every run is a clone of the same repository, so every tree hands cargo the same package name and version, and the fixture drives the crawler through `env!("CARGO_BIN_EXE_archeion")` - a single path inside that directory. One tree's binary was being driven by another tree's test.

That is fixed, per-tree directories are correct, and it changes nothing about the paragraph above. It is recorded here because it is exactly the kind of finding that looks like the answer and closes an investigation early: it is a genuine contamination, it produces a stable wrong verdict, and the wrong verdict it produces is the *plausible* one - the numeric spellings failing is the documented wrong answer for this bead, so it invites being believed.

## Why this was not caught earlier tonight

It was caught by the procedure that exists for it, later than it should have been.

The first scoring of `agy-flash-02` returned 5/5 and was reported as an admitted run. A re-score of the same commit, hours later, returned 2/5. The obvious reading was run-to-run instability in the crawl, and the manual says a verdict that moves between identical runs is an instrument defect rather than a finding, so it was measured: four repetitions, all 2/5, stable. Stability then looked like proof that the 2/5 was real and the earlier 5/5 was the anomaly - and a story was built on it, that the same model had produced a correct fix and a wrong one from an identical prompt.

That story was wrong. What the four stable repetitions actually proved was that the *contamination* was stable. The step that broke it open was the negative control the manual asks for first and which had not been run: score a pristine base tree and check the instrument is capable of failing. It was not.

**A stable answer is not a correct one, and the check that separates them is the control, not the repetition.**

## What has to be decided before any of this is scored again

- **Whether the fixture can discriminate at all in its current form**, on a tree built from a clone rather than the worktree it was authored against. The pilot proved it in both directions on 2026-08-14; that proof does not reproduce here, and the difference between the two situations is the run environment this repository changed in between.
- **Whether `CARGO_BIN_EXE` is the right way for the fixture to reach the crawler**, given that the thing being graded is one of many identical clones.
- **Whether the base signature the pilot recorded is still the truth about the base**, or whether the fixture drifted. The vendored copy here and the canonical copy in the design notes are byte-identical, so the drift, if any, is not in the file.

## What is still running

The sweep continues. It collects runs, and the summary marks every verdict `void-scorer`. Collecting is worth doing because the expensive half - the model's work, its trajectory and its diff - is unaffected by a broken scorer and can be graded later. Nothing about the scores is worth reading until the control passes.
