# Replicating the qualitative review: two of the five positions belonged to the run, not the arm

The first review ranked one run of each arm and reported an ordering. This ran the comparative pass five more times, each against a packet holding a **different** run of every arm, plus three repeats against one unchanged packet to find out how much the panel disagrees with itself.

Twenty-eight calls. Two of the five positions moved, two held, and the head of the table turned out to be a tie that a single packet had no way to show.

## The measurement floor comes first, because nothing else is readable without it

The comparative pass was run three times against the **identical** packet - same entries, same lettering, same prompts, same flags, same accounts. Anything that moves there is the panel, not the code.

| reviewer | run 1 | run 2 | run 3 | |
| --- | --- | --- | --- | --- |
| GPT-5.6 Sol / `codex` | `DBACE` | `DBACE` | `DBACE` | identical |
| Gemini 3.1 Pro / `agy` | `BDACE` | `BDACE` | `BDACE` | identical |
| Opus 5 / `claude` | `DBACE` | `BDACE` | `BDACE` | differs once, min rho +0.90 |
| GLM-5.2 / `pi` | `BAEDC` | `BADCE` | `BDEAC` | never repeated, min rho +0.50 |

**No entry moved position in the aggregate: swing 0, three times, and the ordering `B D A C E` all three.** Mean rank wandered by up to 0.5 rank units.

Two readings follow, and both are load-bearing:

- Movement in the replication below is the **runs**, not the reviewers.
- **A gap thinner than half a rank unit is not one this instrument resolves**, however many replicates it is averaged over.

Half the panel is deterministic on this input. GLM-5.2 never reproduced its own ordering and agrees with itself (min rho +0.50) barely more than it agreed with `codex` in the first run (+0.20) - so the dissent that made the first result look contested was substantially the reviewer, not the code.

## The replicated ranking

Five packets, each drawing a different run of every arm, seeded and recorded in a manifest. Every one of the twenty usable runs was used exactly once, and each packet re-lettered from its own seed so an opinion about "entry C" carries nothing between them.

| arm | rep 1 | rep 2 | rep 3 | rep 4 | rep 5 | mean | swing |
| --- | --- | --- | --- | --- | --- | --- | --- |
| deepseek pro-high | 2 | 1 | 2 | 1 | 1 | **1.40** | 1 |
| sonnet | 1 | 2 | 1 | 2 | 2 | **1.60** | 1 |
| gemini-3.7-flash | 3 | 3 | 4 | 4 | 3 | **3.40** | 1 |
| kimi-k2.7 | 5 | 4 | 3 | 3 | 5 | **4.00** | 2 |
| reference commit `3d6a5a2` | 4 | 5 | 5 | 5 | 4 | **4.60** | 1 |

**Kendall's W = 0.82** over replicates as blocks - chi-square 16.48, df 4, p = 0.0024. Those blocks are independent: every replicate is different code from every arm. Over reviewer-replicate pairs the agreement is W = 0.78, and that p is not quoted here because the same four reviewers appear in every replicate and the blocks are therefore not independent.

## What the twenty individual orderings say

Each of the five packets produced four complete orderings. Read as twenty independent judgements:

| | count |
| --- | --- |
| `{sonnet, deepseek pro-high}` are the top two | **19 of 20** |
| sonnet ahead of deepseek pro-high | **10 of 20** |
| deepseek pro-high ahead of sonnet | **10 of 20** |
| the reference is last | 13 of 20 |
| the reference is in the bottom two | 18 of 20 |
| the reference is in the top two | **0 of 20** |

The single exception to the top pair is Opus in replicate 3, which placed kimi second.

**Ten to ten is the result at the head of the table.** deepseek pro-high finishes with the better mean, 1.40 against 1.60, and that difference is a fifth of a rank unit against a floor of half a rank unit - it is not a difference this instrument can resolve. What replicated is that these two arms hold the top two places and nothing else gets in: no other arm reached second place in any of the five replicates.

## What the single packet got wrong, and how

The first review reported: sonnet, deepseek, **kimi**, gemini-3.7-flash, reference. Two of those positions were properties of the run that happened to be drawn.

- **kimi-k2.7 was third and is fourth, with the only swing of 2 in the table.** `llmux-kimi-06` was an unusually good run of that arm; across the replicates kimi lands last in two, fourth in one and third in two. It is also the only arm other than the reference ever to finish last, and it did so seven times out of twenty.
- **gemini-3.7-flash was fourth and is third**, consistently. `llmux-agy-02` was penalising it.

The median-by-output-tokens rule that chose those runs is not at fault; it did exactly what it promised, which is to pick one representative reproducibly. The lesson is narrower and worth stating plainly: **one run per arm ranks runs, and calling that an arm's position is an inference the data does not carry.** Run-to-run spread inside these arms was 13 to 23 percent in output tokens during the campaign, and a spread that size moves a position.

## What held

**The reference commit stays at the bottom.** It was last in three of the five replicates and second-to-last in the other two, and across all twenty individual orderings it never once appeared in the top two. That is the same result the single packet produced, now against five sets of agent runs that share no code with the original.

It remains a finding about that implementation rather than about the review, because the reference is not a control: `3d6a5a2` was produced the same way the candidates were, in a repository that took 52 commits that day, and nothing marks it as good except having been merged.

## What this still does not say

- **One task.** Every number here is about `llmux-p4-two-phase-reservation-5vg`, a bead chosen to separate arms by cost and explicitly not by capability. All four arms pass it 5 out of 5.
- **The findings were not replicated, only the ranking.** Pass A ran once, on the original packet. Its findings describe those five specific implementations and carry no more weight than they did.
- **deepseek pro-max is still absent**, since none of its five runs compiles.
- **Five replicates is modest.** The position table is what carries the confidence; W and the p-value support it and do not replace it. No pairwise test would survive multiple-comparison correction at this size, which is why none is claimed.

## One correction the first review's own material invited

The GLM finding against the deepseek entry said the gate check is "correct only because `expireGateIfDueLocked` ran first ... and the only thing preventing it is a comment." It is not a comment. `TestReserveLazilyExpiresGateBeforeChecking` sits in the subject repository's own suite, pins the expired-gate case, and predates the base commit the runs started from. Reorder that call and the test goes red.

The reviewer could not have known: the packet excludes test files by design, so that entries stay structurally comparable. The price of that choice is that reviewers overstate regression risk, and it belongs in the record as a property of the instrument rather than as a fault of the reviewer.

## Reproducing it

```sh
cd evals/bead_cost
./build_replicates.py --out-root ~/tmp/bead-cost-review/replicates --draw-seed 20260817
for i in 1 2 3 4 5; do
  ./run-review.sh --pass-b ~/tmp/bead-cost-review/replicates/replicate-$i \
                           ~/tmp/bead-cost-review/replicate-answers/replicate-$i
done
./aggregate_replicates.py ~/tmp/bead-cost-review/replicates/manifest.json \
  --answers-root ~/tmp/bead-cost-review/replicate-answers
```

The draw seed fixes which run of each arm lands in which packet, and the manifest records the assignment and each packet's hash. The five packets rebuild byte-identically from the same seed; that was checked before any of the twenty calls was spent.
