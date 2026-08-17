# The qualitative review, and the implementation that ranked last was the one that shipped

Four reviewers, eighteen calls, five blinded implementations of `llmux-p4-two-phase-reservation-5vg`. The question is the one no deterministic tool answers: **how much future work did this implementation create for whoever extends this package next?**

The headline is not the ordering. It is that the anonymous fifth entry — the commit that actually landed this bead on `master` — came last, and that three of the four reviewers independently named the same decision inside it as the worst single decision in the whole set.

## The ranking

Mean rank across the four reviewers (Borda), lower is better, where better means *the one you would rather inherit*.

| # | entry | implementation | mean rank | codex | gemini | glm | opus |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | B | sonnet / `llmux-claude-04` | **1.50** | 2 | 1 | 1 | 2 |
| 2 | D | deepseek pro-high / `llmux-dshigh-03` | **2.00** | 1 | 2 | 4 | 1 |
| 3 | A | kimi-k2.7 / `llmux-kimi-06` | **2.75** | 3 | 3 | 2 | 3 |
| 4 | C | gemini-3.7-flash / `llmux-agy-02` | **4.25** | 4 | 4 | 5 | 4 |
| 5 | E | **reference commit `3d6a5a2`** | **4.50** | 5 | 5 | 3 | 5 |

Three of the four orderings are near-identical: `codex` and `opus` are the same ordering exactly, and `gemini` differs from them only by swapping the top two. GLM-5.2 is the dissenter, and its dissent is the whole of the disagreement in the panel.

## Does the panel have signal at all

Pairwise Spearman correlation, **median +0.70** against a floor of +0.20 fixed before any answer existed.

| | codex | gemini | glm | opus |
| --- | --- | --- | --- | --- |
| **codex** | — | +0.90 | +0.20 | **+1.00** |
| **gemini** | +0.90 | — | +0.50 | +0.90 |
| **glm** | +0.20 | +0.50 | — | +0.20 |
| **opus** | +1.00 | +0.90 | +0.20 | — |

`codex` and `opus` produced the identical ordering without seeing each other's answers. That is the strongest evidence here that the question has a stable answer rather than four tastes.

## The two conflicts, measured rather than assumed

Opus 5 reviewed an implementation written by Claude Sonnet 5; Gemini 3.1 Pro reviewed one written by Gemini 3.7 Flash. Both were kept in the panel on the condition that the bias be measured.

| reviewer | its family's entry | where it placed it | where the conflict-free pair placed it | verdict |
| --- | --- | --- | --- | --- |
| opus | B (sonnet) | 2 | 1.50 | no effect |
| gemini | C (flash) | 4 | 4.50 | no effect |

Neither favoured its own lineage. Opus was marginally *harder* on the Sonnet entry than the conflict-free reviewers were.

**The blinding held.** Asked in a separate call, after their answers were already on disk, whether any entry read as the work of a model from their own family: `codex`, `gemini` and `opus` all answered `cannot_tell`. GLM-5.2 named B — the Sonnet entry — which is not its family and is therefore a wrong guess rather than a leak.

## Pass A: the findings

Two conflict-free reviewers read each implementation alone, with the full attention budget and no other entry in context. A finding had to cite lines, say what it costs *later*, and name a concrete follow-up; taste was allowed but had to be labelled taste.

| entry | codex | glm | non-taste | corroborated files |
| --- | --- | --- | --- | --- |
| A kimi-k2.7 | 1 | 2 | 3 | `internal/route/reserve.go` |
| B sonnet | 2 | 2 | 4 | `cooldown.go`, `reservation.go` |
| C gemini-3.7-flash | 1 | 4 | 4 | `internal/route/reservation.go` |
| D deepseek pro-high | 0 | 2 | 1 | — (codex raised nothing) |
| E reference | 0 | 4 | 3 | — (codex raised nothing) |

Note what the counts do and do not say. **A finding count is not a quality score** — it measures a reviewer's threshold at least as much as it measures the code, which is exactly why the ranking is carried by the comparative pass and not by this table. `codex` found nothing to report in two entries and gave both a clean overall; GLM-5.2 reports more findings than codex in four of five entries.

### What was actually raised, by entry

**B — sonnet, ranked 1st.** Both reviewers converged on the same two places. `expireGateIfDueLocked` mutates the gate but delegates the waiter notification to every caller by documented contract, so a third call site that forgets the notify-on-true branch silently drops a wakeup. And the composite lease introduces a second reservation-release path alongside `ReserveRateSlot` / `ReleasePendingRateSlot`, so future limiter work has to be kept consistent across both. GLM adds that `PendingLease` enforces release-once but not release-at-all: a caller that returns without `defer lease.Release()` leaks an in-flight slot and a pending reservation permanently, since neither has a timeout.

**D — deepseek pro-high, ranked 2nd.** The only entry where codex raised nothing at all, calling the boundary cohesive with "no clear extension tax". GLM raised one low finding — `> 0` guards that swallow an underflow rather than surfacing it — and one taste finding about `Finalize` routing to an exported method while `Release` routes to an unexported one.

**A — kimi-k2.7, ranked 3rd.** Both flag documentation-versus-behaviour drift rather than structure. The `PendingLease` doc implies `Finalize` releases the in-flight slot when it does not, and `releaseReservation` notifies waiters while `finalizeReservation` does not, with the rule left implicit — so the next person adding a third way a reservation ends will copy the wrong shape.

**C — gemini-3.7-flash, ranked 4th.** The heaviest structural criticism. `PendingLease` carries a back-pointer to `*Coordinator` and mutates shared state through it, so the lease's correctness is coupled to the Coordinator's lifetime and lock rather than to the reservation it represents. codex frames the same thing as a lifecycle that stops halfway: the lease owns the in-flight slot but has no successful-dispatch transition that releases it, so the lifecycle is split across two APIs. GLM adds that the admission gate is encoded as two independent checks that must be edited in lockstep.

**E — the reference, ranked last.** codex reported no finding and a clean overall. GLM raised three non-taste findings, all structural: `PendingLease` embeds its own `sync.Mutex` and takes it *before* the Coordinator mutex, fixing a two-lock ordering that any future method touching both must respect or deadlock; the pending/in-flight bookkeeping is spread across `Reserve`, `Finalize` and `Release` with the rules duplicated in prose rather than centralised; and the gate has two live definitions, since `Reserve` still checks `now < state.rateGateDeadline` after `expireGateIfDueLocked` already clears an expired deadline.

### The one thing three reviewers found independently

Asked for the single worst decision in the set, `codex`, `gemini` and `opus` each named the same one, in entry E:

> `Release` is overloaded with a second meaning. Called after `Finalize`, it frees only the in-flight slot; called before, it frees both. One method name, two behaviours selected by hidden state, on the path that settles every admission.

GLM was the exception and named a gate check in D instead. Three independent reviewers converging on one method in one entry is the strongest single signal in this result — and it is against the code that shipped.

## What this does not say

- **The reference is not a control, and its position is not a verdict on the review.** `3d6a5a2` was produced the same way the candidates were, by an agent working in a repository that took 52 commits that day, and the git author field cannot distinguish it because every commit there carries the same author by convention. Nothing marks it as good except having been merged. Its position was demoted to a reported point of attention before this run, precisely so that a result like this one could be read rather than discarded.
- **One task, one run per arm.** Each entry is the median run by output tokens within its arm; a different median-choosing rule would put different code in front of the reviewers. Nothing here is a claim about the models in general.
- **deepseek pro-max is absent and that is deliberate.** None of its five runs compiles against the package's own tests, and "how much future work does this create" presupposes something you can build on. What is known about that arm was settled by the compiler and the exported-API diff, which are stronger instruments than any reviewer.
- **Correctness was not re-litigated.** Every entry passes the sixteen canonical tests, the repository's 52 test files, `go vet`, the race detector and five static analysers against a baseline. The reviewers were told so and asked not to re-derive it.

## Two defects in the instrument, found by this run

Both were silent, both produced well-formed reports, and both are fixed with tests that fail when the fix is removed.

**All seven codex answers were unreadable.** `codex exec` echoes the entire prompt before answering, the prompt carries the packet, and the packet is Go source. Reading from the first brace to the end of the file therefore starts inside the echoed example and runs through thousands of lines that are not JSON. Uncaught, the panel would have lost a conflict-free reviewer and the run would have been declared invalid — for the wrong reason, since every one of those answers was intact.

**A reviewer refusing to guess was recorded as having guessed.** The blinding check offers `none` and `cannot_tell` beside the letters. The code took the first character of the reply, so `cannot_tell` became `C` — and C was the entry written by Gemini's own family. Three of four reviewers refused; the check read that as Gemini identifying its own lineage and voided the ranking. Opus refused in the same word and escaped only because its family happened to be the B entry.

Neither was a wrong answer from a model. Both were correct answers read wrongly, which is the failure mode this harness keeps producing and the reason every gate here is broken on purpose before it is trusted.

## Reproducing it

```sh
cd evals/bead_cost
./build_review_packet.py --seed 20260816 --out ~/tmp/bead-cost-review/review-packet   # sha256 ee097e83…
./review-isolate.sh ~/tmp/bead-cost-review/review-packet                              # 8 checks, from inside
./run-review.sh --probe ~/tmp/bead-cost-review/review-packet                          # 4 calls, spends almost nothing
./run-review.sh ~/tmp/bead-cost-review/review-packet                                  # the 18
./aggregate_review.py ~/tmp/bead-cost-review/answers --key ~/tmp/bead-cost-review-keys/review-packet.json
```

The eighteen calls ran in 3 minutes 43 seconds across two waves. The protocol, the two reviewer conflicts and the conditions that invalidate the result are in the plan; the aggregation rule was implemented before the first reviewer was called, and the reference-entry rule was demoted before it too.
