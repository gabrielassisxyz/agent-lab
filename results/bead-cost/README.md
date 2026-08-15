# bead-cost pilot, 2026-08-14

One agent, one run, checked to exhaustion before anything runs in parallel. Two lanes ended up being run rather than one, which was not the plan and turned out to be the most useful part.

**Read this first, before any number below is quoted anywhere: the pilot did not measure the models. It measured the environment, found five defects in it, and every cost figure it produced is void.** That is a successful pilot, not a failed one, and it is exactly what the protocol exists to buy before 45 runs are spent.

## What was run

Subject: `archeion` bead `arch-42q`, *a link written with `&amp;` still costs a request per spelling*. Both lanes received a byte-identical prompt: the bead's full text, plus *"Make the change and commit it. The repository's gate is `bin/ci`."*

| | kimi-k2.7 via `pi` | gemini-3.7-flash-medium via `agy` |
|---|---|---|
| outcome | finished, across three invocations | finished in one |
| wall clock | 60 min (killed by ceiling) + 6.5 (killed by 429) + 4 | 22.5 min |
| commit | `6b743bc` | `08cac62` |
| section A of the rubric | **pass, 5/5, stable over 4 runs** | **pass, 5/5, stable over 4 runs** |
| full test suite | 502 passed, 0 failed | 0 failed |
| B1 (left `canonical_url.rs` alone) | pass | pass |
| B2 (one decode point, three spellings) | pass | pass |
| B3 (reused the existing decoder) | pass | pass |
| new dependency | none | `async-trait` |

**Both lanes solved the bead**, including the numeric character references the bead warns fail worse than the named one. A throwaway fix written by hand while building the instrument did **not** solve them: it decoded in the callback that receives an already-parsed URL, which is too late, because `#` is a fragment delimiter and the parameter behind it is gone before the callback sees it. That failure is worth recording because it is the plausible-wrong answer the rubric's judgement section was built to catch, and its author fell into it without trying.

Three distinct architectures for one bug:

- **hand-written probe** - decode in `on_link_find_callback`. Wrong layer, fails the numeric forms.
- **kimi** - decode the raw href where `page_links` still holds the page's own text, carry the rewrite in a side map, substitute in the callback. New state on the engine struct and a mutex on a hot path; every call site changed.
- **agy** - a custom fetch engine wrapping the HTTP client. No shared state, but it adds a dependency to a bug fix.

## Why no cost figure survives

Five environment defects, all in the harness, each found by measuring rather than reasoning:

1. **The lane's model catalog was not in the sandbox.** The first run died with `Model not found` before spending a token. Provider catalog, auth and extensions are constants that make a lane a lane; only the instruction file had been copied.
2. **One agent's own MCP configuration was untouched** while another's had been cleared, leaving the memory server reachable for precisely the lane whose sessions this experiment reads.
3. **357 MB of crates and 172 MB of npm packages were re-downloaded inside the measured hour**, because overriding `HOME` hid the machine's real caches. That time was indistinguishable from the model's own, and it surfaced to the agent as `can't find crate`, which it reasonably wrote off as transient and worked around instead of working on the bead.
4. **The scorer would have graded the wrong tree.** The sandbox carries the machine's real global instruction files, which open with a gate telling an agent to create its own worktree before its first write. One agent followed it. Scoring where the run was launched would have graded a tree abandoned after a few minutes.
5. **Text authored in the repo that owns the design failed this repo's prose gate** when vendored here. Green where text is written says nothing about where it lands.

Add to those a 60-minute ceiling chosen by the harness author and two rate-limit kills, and neither lane's wall clock or token total describes the lane.

## Two readings that were wrong, and how they were caught

Both are recorded because the correction, not the conclusion, is the transferable part.

**"It did not finish."** Inferred from exit 124 and an absent commit. The instrument then returned 5/5, and the full suite returned zero failures: the last edit before the kill had repaired the regression the run introduced. It was functionally complete and had not committed. **An exit code is not a verdict about work.**

**"It exhausted its window."** Inferred from a 429. Probing the two other keys answered immediately, which an exhausted account quota would not, and the failing run was issuing a tool call about every two seconds for an hour. The limit is a **request rate per account**, not a window. This inverts the concurrency plan: keys do not divide a budget, so three runs on one key compete for one ceiling rather than taking a third each.

## What the pilot changed

- Toolchain caches are shared rather than recreated empty, with a gate that asserts the crate count rather than the symlink, because a link to an empty directory passes every structural check.
- The scorer discovers the tree a run left its work in (`find-work.sh`), scoped to that run's HOME.
- Sandbox verification gained checks for the lane's reachability and for both MCP configurations, each proven against the sandbox that actually failed.
- Two trajectory viewers, because one harness streams a session log and the other writes a single envelope at the end and keeps its live trajectory in SQLite.

## The subject is spent, deliberately

`arch-42q` now has two committed solutions on disk. **Neither becomes a pull request, and that is the decision rather than an oversight**: merging either would close the bead the benchmark is built on and leave the remaining runs measuring a problem that no longer exists. Both trees stay frozen where they are until the benchmark is done.

That is also the sharpest limitation this pilot exposes about the design. **A bead can be a benchmark subject once.** Comparing many lanes on one bead means every lane after the first is measured on work already solved nearby, and the subject cannot be reused later for its own sake.

## What still has to be decided

- **The request-rate ceiling per account**, measured directly, before any concurrency number.
- **The turn ceiling.** One hour was not enough with a broken environment; what it should be with a working one is unmeasured.
- **Whether one bead can carry this comparison at all**, given that the binary verdict sat at ceiling for both lanes exactly as this repo's earlier experiment predicted, leaving the graded rubric and the process metrics as the only things with headroom.
