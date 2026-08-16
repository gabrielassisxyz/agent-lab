# Five runs on the cost bead: the first noise floor on the new subject

One lane, one bead, five runs. **All five passed 16 of 16.** That settles what `5vg` is for, and it produces the first run-to-run spread this experiment has ever had on a task every run completes.

Lane: `kimi-k2.7` through `pi`. Subject: `llmux`, bead `llmux-p4-two-phase-reservation-5vg`, base `64cfb7e`.

## The runs

| run | account | verdict | wall | turns | output | reasoning | input | diff | commit |
|---|---|---|---|---|---|---|---|---|---|
| `llmux-kimi-02` | k2 | 16/16 | 263 s | 41 | 11 559 | 7 307 | 2 382 111 | 1 file, +119 | `62bf722` |
| `llmux-kimi-03` | k1 | 16/16 | 298 s | 44 | 11 585 | 7 508 | 2 073 161 | 1 file, +157 | `3132e25` |
| `llmux-kimi-04` | k2 | 16/16 | 431 s | 55 | 15 471 | 12 014 | 3 081 962 | 1 file, +151 | `a675354` |
| `llmux-kimi-05` | k3 | 16/16 | 366 s | 46 | 13 722 | 9 727 | 3 452 027 | 2 files, +162 | `1cab277` |
| `llmux-kimi-06` | k2 | 16/16 | 423 s | 44 | 12 832 | 8 407 | 2 639 661 | 2 files, +170 | `2acbda5` |

`build_failed: false` on all five. Input is a per-turn sum, which counts the whole prompt again every turn; it is the lane's real traffic and it is not comparable with a harness that reports an envelope total.

## The spread

| metric | mean | sd | rsd | sem | min to max |
|---|---|---|---|---|---|
| turns | 46.0 | 5.3 | **11.6 %** | 2.4 (5.2 %) | 41 to 55 |
| output tokens | 13 034 | 1 638 | **12.6 %** | 732 (5.6 %) | 11 559 to 15 471 |
| reasoning tokens | 8 993 | 1 940 | 21.6 % | 868 (9.6 %) | 7 307 to 12 014 |
| input tokens | 2 725 784 | 549 030 | 20.1 % | 245 534 (9.0 %) | 2 073 161 to 3 452 027 |
| wall clock | 356 s | 75 | 20.9 % | 33 (9.4 %) | 263 s to 431 s |

**The wall-clock row must not be quoted as a noise floor.** Four of the five ran concurrently, in one window from 18:06:40 to 18:14:25; the fifth ran alone an hour earlier and is the fastest of the set. That is contention, not variance, and it is the same contamination `wall_time` has carried by design since the pilot. The token and turn columns are unaffected by it, and the check that says so is that the four concurrent runs alone hold the spread on their own: turns 11.1 %, output 12.2 %, against 11.6 % and 12.6 % for all five. Dropping the solo run changes nothing, so the solo run is not what produced the spread.

### What this buys, and what it does not

**About 12 % relative sd on turns is a far tighter instrument than this repo has measured before.** The ancestor experiment carried 44 % on the same metric. The comparison is directional only: different task, different repository, different lane, and a bead every run finishes rather than one most runs fail.

The number that decides how many runs an arm needs is the minimum difference this spread can resolve. At five runs per arm, with sd at 11.6 % of the mean, the standard error of a difference between two lanes is about 7 % of the mean, and a difference has to reach roughly **20 % on turns** before five runs can tell it from noise.

**So five runs per arm is enough for a lane that differs by a lot, and not enough for a lane that differs by a little.** The lanes this experiment exists to compare differ by up to sixty times on price, which is far outside that band. Turn counts and token counts between two competent lanes may well sit inside it, and no number of careful tables will fix that; only more runs will.

## `5vg` is a cost bead, and now it is confirmed rather than assumed

The first pass on this bead raised the question with n=1. Five for five answers it: **resolve rate on this bead is at ceiling, and it is at ceiling on purpose.**

That makes it useless for measuring difficulty and correct for measuring what a completed bead costs. Every lane finishes, so every lane yields a completed unit, and cost per completed bead has a denominator instead of an argument. A bead only two lanes solve gives two data points and four excuses.

The capability question needs a separate, harder bead, selected with the four filters and sitting in the 30 to 70 percent band. Nothing here answers it and nothing here was meant to.

## The verification measures behaviour, not placement

Five runs produced **five different implementations** and all five passed: 119 to 170 added lines, across one or two files. The original commit put the work in `coordinator.go`; the runs put it in `rate.go` and elsewhere. A verification that graded placement would have rejected most of these, and a verification that graded naming alone would have accepted work that does not run.

This is the property that makes the bead usable at all, and it survives repetition rather than having held once.

## A gate defect found by a typo, and worth recording

The first attempt at these four runs was launched with a mistyped model route: `litellm/kimi-k2.7-`, the account suffix lost to a shell that does not word-split an unquoted variable. **The sandbox gate passed it.** The check matched the catalogue as a substring, and `kimi-k2.7-` is a prefix of `kimi-k2.7-k1`.

So four sandboxes were built, four builds warmed, and the runs entered the measured window before dying against a model nobody serves. A gate that accepts an id the provider does not have is worse than no gate: it spends the environment before failing, and it fails where the failure looks like the model's.

Fixed by comparing whole tokens rather than substrings, and proven by negative control on the real gate: the prefix is now rejected and the full id still passes. The same hole sat on the claude branch, where the needle is an account name and a truncated one would have passed just as quietly.

**This is the third defect in this harness of the same family**, after the shared scoring build directory and the `pipefail` pipeline that reported a model missing when it was found. All three produced a *confident, stable* wrong answer, which is what let them survive: a gate that says `ok` and a table that agrees with itself read exactly like a working instrument. What catches them is the negative control, never the reading.

## Open

- **The other lanes on this bead.** One arm of five is a spread, not a comparison. `agy`, `glm`, `deepseek` and `claude` have not run it.
- **The harder bead** for the capability question, still to be selected.
- **The per-account request ceiling**, still unmeasured. These runs put three concurrent sessions on three accounts and two on one, for eight minutes, with no throttling seen; that is a lower bound on nothing much.
