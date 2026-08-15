# The night the verdicts were void, and why

**Resolved.** The canonical verification works and discriminates. Two separate contaminations overlapped in time, and between them they made a working instrument look broken. Both are closed, every affected run has been re-scored from artefacts already on disk, and no run had to be paid for twice.

Read this before quoting any verdict recorded between 2026-08-14 23:00 and 2026-08-15 01:00.

## What the instrument does when nothing is contaminating it

| tree | carries the fix? | verdict |
|---|---|---|
| untouched base `6edbb8e` | no | `a1 true`, a2-a5 false |
| `agy-flash-02` | yes, complete | `5/5` |

The first row reproduces exactly what the pilot recorded for this commit. The instrument was never the problem.

## Contamination 1: one build directory, many identical clones

The scorer built every tree in a single cargo target directory. Every run is a clone of the same repository, so every tree hands cargo the same package name and version, and the fixture reaches the crawler through `env!("CARGO_BIN_EXE_archeion")` - one path inside that directory. One tree's binary was therefore driven by another tree's test.

Measured on one unchanged tree: the shared directory returned `a1 true, a2 false, a3 true, a4 false, a5 false`, stable across four repetitions, while a private directory returned all five true. **Fixed by giving the scorer a directory per tree.**

## Contamination 2: a run patched its dependency, for the whole machine

The bead says the fix belongs "at whatever reads the engine's `page_links` for its href text before a URL is built from it". That layer lives inside the `spider` crate, not inside the repository. A run followed the instruction to where it led and patched the crate: nine write calls into `~/.cargo/registry/src/…/spider-2.52.13/`, adding `html-escape` to its manifest and a character-reference decoder to its `push_link`.

It is a defensible reading of the task, and it was catastrophic. Every build on this machine afterwards - including the scorer's - linked a `spider` that already solved the subject, so an untouched base tree began passing the canonical verification. **Nothing about it appears in the diff being graded.**

The sandbox had allowed exactly this in writing, on reasoning that covered the wrong case: a run may write into the shared cache, because all it can add is a crate it downloaded, and a downloaded dependency carries nothing about the bead. True of downloads. False of edits.

**Fixed by splitting cargo's home along what is actually immutable.** The `.crate` files and the index stay shared, because re-fetching them is the 357 MB tax the arrangement exists to avoid. The extracted sources become private per run, because they are ordinary writable files. Cargo repopulates them from the shared cache without touching the network: 1m39s for 314 crates, inside the warm-up and outside the measured window. It also removes the extraction race between concurrent runs structurally rather than by lock.

## What the runs actually did

Re-scored against a pristine dependency, in a build directory of their own.

| run | lane | verdict | reading |
|---|---|---|---|
| `agy-flash-02` | gemini-3.7-flash-medium | **5/5** | correct fix, decoded before the URL is built |
| `agyflash-01` | gemini-3.7-flash-medium | 2/5 | decoded in `set_on_link_find`, which receives an already-parsed URL |
| `agyflash-02` | gemini-3.7-flash-medium | 2/5 | same architecture as above |
| `kimi27-02` | kimi-k2.7 | **5/5** | repo fix stands on its own against a pristine crate |
| `glm52-02` | glm-5.2 | no diff | stopped after 99 turns to argue the bead cannot be satisfied as written |
| `deepseek-max-01` | deepseek-v4-pro-max | no diff | killed by the lane's output ceiling |
| `agyflash-01b`, `kimi27-01b`, `glm52-01b` | all three | base signature | **void**: developed inside the poisoned window |

The last row is the clearest evidence of contamination 2. All three committed work, and all three reduce to the untouched base when built against a pristine crate: they watched their own tests pass against a dependency that was already fixed.

`kimi27-02` is the run that patched the crate. Its committed diff passes on its own merits, so its verdict stands, but its turns and tokens include the work it spent inside the dependency and are not comparable with a run that never went there.

## The two-hour detour, because the reasoning is the transferable part

The first score of `agy-flash-02` was 5/5. A re-score hours later returned 2/5. A verdict that moves between identical runs is an instrument defect rather than a finding, and the manual says to test that by repeating, so it was repeated four times. All four agreed on 2/5.

**Stability then read as proof**, and a story was built on it: the same model producing a correct fix and a wrong one from an identical prompt, and the earlier 5/5 dismissed as the anomaly. What the four repetitions actually proved was that contamination 1 was stable.

The step that broke it open is the one the diagnostic ladder puts first and which had been skipped: score a pristine base tree and confirm the check is capable of failing. It was not. That pointed at contamination 2, which pointed back at contamination 1 having been only half the story.

Both the original claim and its retraction were wrong, in opposite directions, for the same reason: **a stable answer is not a correct one, and what separates them is the control, not the repetition.** The variance between the agy runs is real, and it was visible before any of this - it just could not be trusted until the controls passed.

## What the gates check now

- The scorer's build directory is derived per tree.
- `registry/src` must be private and must not be a symlink; `registry/cache` and `registry/index` must be shared. Both halves are asserted, because each is silent when wrong in its own direction.
- The crate count is read with `find -L`, since `cache` became the final path component and a terminal symlink is not descended into - which reads as a cold cache rather than as a check looking at the link instead of through it.
