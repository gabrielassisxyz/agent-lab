# Reviewing implementations qualitatively: how it runs, and what each number is worth

The scoring half of `evals/bead_cost` answers *did this run solve the bead*. A compiler, a test suite, a race detector and five static analysers answer it, and on a well-chosen bead they answer it the same way every time.

This half answers the question none of those touch:

> **How much future work did this implementation create for whoever extends this package next?**

Layering, where state lives, whether an abstraction earns its indirection, whether the next person fights the code. Not correctness. Correctness is settled before this starts.

It is a different instrument with different failure modes, and most of this page is those failure modes. The design record is [`../local/plan-qualitative-review-2026-08-16.md`](../local) when it is present; the results it has produced are under [`../results/bead-cost/`](../results/bead-cost).

## The shape of it

```
build_review_packet.py   one packet: N implementations, lettered, blinded, plus a hidden reference
review-isolate.sh        narrow the sandbox to that packet, and prove it from inside
run-review.sh --probe    one trivial call per reviewer: does it answer, and what can it reach
run-review.sh            the real passes, in two waves
aggregate_review.py      decode, aggregate, and state validity as a verdict

run-review.sh --pass-b   the comparative pass alone - repeat it to measure the panel against itself
build_replicates.py      one packet per replicate, a different run of every arm in each
aggregate_replicates.py  position per ARM across replicates, with Kendall's W and Friedman
```

Two passes, because they answer different things and check each other.

**Pass A is absolute**, one implementation per call, full attention budget, and it produces the *findings*: line-cited, actionable, labelled taste where it is taste. **Pass B is comparative**, every implementation in one packet, and it produces the *ordering*.

The ordering is carried by pass B and not by pass A on purpose. An absolute review always finds problems, including in code written by the strongest model available, so "four findings, severity medium" measures a reviewer's threshold at least as much as it measures the code. A ranking needs no calibration, only internal consistency. The reverse is also true and is why pass A exists: a ranking position is not actionable, and it is valid only for the set that was ranked.

## Step 1: build the packet

```sh
cd evals/bead_cost
./build_review_packet.py --seed 20260816 --out ~/tmp/bead-cost-review/review-packet
```

It prints a **sha256 of the packet body**. That hash is the point: reviewers given different text are not a second opinion, they are a second experiment. Record it and check it on every rebuild.

The blinding is mechanical rather than well-intentioned:

- entries are lettered from the seed, never ordered by arm, so "first" carries nothing;
- **commit messages are stripped entirely** - the runs write their own, and the tracker has been observed leaking an agent's identity into text a run could read;
- run ids, model names, account suffixes and any path under the run root are absent by construction, because nothing but diff text is copied;
- test files are excluded, which also keeps entries structurally comparable.

**The reference entry goes in unlabelled.** The commit that actually landed the bead sits among the candidates under the same kind of letter, and no reviewer is told it exists.

It is **not a control**, and treating it as one was a real mistake made here. That reading needs the reference to be known-good, and on this subject it was produced the same way the candidates were - an agent in a repository that took 52 commits that day - with the git author field unable to distinguish it because every commit there carries the same author by convention. So its position falsifies nothing: last is a claim about that implementation, first is not evidence of signal.

**Where the packet may live is a constraint, not a preference.** See step 2.

## Step 2: prove the isolation

```sh
./review-isolate.sh ~/tmp/bead-cost-review/review-packet
```

Eight checks, all asked **from inside the sandbox** rather than about it, including a negative control on the checking mechanism itself.

The risk being closed is not the open web. The subject repository is private; no search finds it. The risk is the local filesystem, where the real solution sits in git history a reviewer could simply read - and nothing in its written answer would reveal that it had.

Two things this script learned the hard way, both of which certified an isolation that did not hold:

- **`ai-jail` reads `.ai-jail` from the current working directory**, not from any path it is handed. Written as `ai-jail … -- env -C "$packet" …`, which looks equivalent, it picks up whatever config the caller's directory has. Measured: without the `cd`, `ls ~/repositories/llmux` prints the tree; with it, "No such file or directory".
- **`rw_maps` does not govern every mount.** `ai-jail` binds some volumes regardless of the config - on this machine `/mnt/build`, where agent scratchpads live - and those scratchpads hold full clones of the subject whose object store carries the reference commit. Only `mask` takes them away, and a content grep is no substitute: the clone's HEAD sits on the base commit, the reference exists only as a compressed object, so grepping the tree finds nothing while `git show` still yields the answer.

Hence: **the packet must not live in the agent scratchpad**, because that is inside the volume that has to be masked. The script refuses such a packet rather than building a jail that would hide the packet along with everything else. `~/tmp/bead-cost-review/` is the location the rest of the tooling assumes.

The answer key is moved out of the packet on the first run, to `~/tmp/bead-cost-review-keys/<packet-basename>.json`. Never show it to a reviewer.

**What this does not promise:** it is a filesystem control, not a network one. `allow_tcp_ports` applies only in lockdown mode, and reviewers must reach their own model endpoints. Network restraint comes from each CLI's own flags, and the honest claim is filesystem-only.

## Step 3: probe before spending

```sh
./run-review.sh --probe ~/tmp/bead-cost-review/review-packet ~/tmp/bead-cost-review/probe
```

Four calls, one per reviewer, through **the same functions the real passes use**. A probe written as its own command line proves a command line nobody will run, and what fails on a first launch is never the prompt: it is a flag the CLI rejects, an account with no quota left, a credential the sandbox does not mount.

The probe asks each reviewer for its model identifier and for what it sees at the subject repository, so one cheap call answers both *does this work* and *can it reach the solution*. Read every answer before going further.

**Two answers look alarming and are not.** The GLM lane reports its model as `claude-sonnet-4-5`; open models self-report unreliably and the route is `litellm/glm-5.2-k<slot>`, which the proxy maps to `glm-5.2:cloud`. And `codex` prints `bwrap: Failed to make / slave: Operation not permitted` - that is its own sandbox declining to nest inside the jail it is already in, not a failure to run. The answer that actually matters is the negative one: `claude` reporting `Directory does not exist: ~/repositories/llmux` is the isolation working, from inside.

## Step 4: the real passes

```sh
BEAD_COST_CLAUDE_ACCOUNT=<account> ./run-review.sh ~/tmp/bead-cost-review/review-packet
```

Twenty-four calls for a nine-entry packet: eighteen pass A (nine entries × two reviewers with no lineage in the entry), three pass B, three blinding. The arithmetic follows the panel, and the panel follows the packet - see [the panel is not fixed](#the-panel-is-not-fixed-it-is-whatever-the-packet-leaves-clean).

**Two waves.** The blinding check is asked after the answers it must not influence are already on disk. Asking it in the same call would tell the reviewer that authorship matters, and then the ranking measures the question.

**Lanes rather than a scheduler.** Each lane is a sequential worker over its own list, so the number of lanes a reviewer gets *is* its concurrency cap and there is nothing to queue or tune. Every cap traces to a limit:

| reviewer | lanes | why |
| --- | --- | --- |
| `codex` | 2 | what its quota takes; it holds most of the calls and sets the wall clock |
| GLM via `pi` | one per call | the limit is a request rate **per account**, and three accounts absorb six calls at two apiece |
| `agy` | 1 | its calls share one home directory under the packet and would collide in it |
| `claude` | 1 | file auth holds one account at a time, and it also takes whatever pass A work is routed away from a conflicted reviewer |

Two switches for when this shape is the suspect: `BEAD_COST_REVIEW_SERIAL=1` collapses every lane into one, and `BEAD_COST_REVIEW_DRYRUN=1` prints what each lane would ask - with its account slot and schema - and spends nothing. Use the dry run before any launch; two dozen paid calls are worth reading before they are worth running. It also prints the routing - `ROUTE E is codex family - its pass A goes to opus instead` - which is the cheapest way to see that the panel came out the way you meant it to.

The runner is resumable. A label with a usable answer is skipped; an answer that turns out to be empty is moved aside as `<label>.txt.empty` so a rerun asks again and the evidence survives.

**The answers live outside the packet directory, and that is independence rather than tidiness.** `agy` keeps its tools, and its calls run after the ones that answer earlier, so answers stored beside the packet sit in a directory it can list. Four orderings that agree because one reviewer read the others are indistinguishable from four that agree because the signal is real - and agreement is the whole basis for publishing a ranking. A sibling directory is not visible from inside the sandbox, and the answer files are opened by the unjailed caller regardless of where they sit, so nothing is lost by keeping them out.

### Each reviewer's trap, and it is never the prompt

| CLI | the trap |
| --- | --- |
| `codex` | `codex exec` **waits on stdin forever** without `< /dev/null`, and the symptom is a silent stall indistinguishable from a reviewer thinking hard. It also bills a floor of roughly 23 000 input tokens per call - multiply the floor, not the prompt. |
| `pi` | retries an unreachable MCP server for about 40 seconds before answering normally. Noise on stderr, not a hang. `--no-tools` is the point: the packet is in the prompt, so a reviewer that can run nothing can still answer. |
| `agy` | **`--print` must be the last flag**, or everything after it is swallowed as prompt text and the model politely answers about the flag. Effort is baked into the model id and `--effort` is rejected for such ids. It also needs `--dangerously-skip-permissions --mode plan` together: in print mode it cannot prompt for a permission, so the first tool the model reaches for is auto-denied and the turn ends having written nothing. Auto-approving is only a small claim because plan mode cannot write and the sandbox leaves nothing to read but the packet. |
| `claude` | always `claude-as <account>`, never bare `claude`: file auth holds one account at a time, so a bare launch bills whichever token that file happens to carry. |

## Step 5: aggregate, and read the verdict

```sh
./aggregate_review.py ~/tmp/bead-cost-review/answers \
  --key ~/tmp/bead-cost-review-keys/review-packet.json
```

Aggregation is **mean rank (Borda)**, not majority vote: the task is an ordering, and majority voting over orderings throws away what makes an ordering useful. A finding raised by one reviewer is reported as raised by one, never promoted to consensus.

Every rule was fixed before the first reviewer was called, and that ordering is the point - an aggregation chosen after reading the answers is a choice made while already knowing the result.

**Invalidating conditions**, which exit 2 and say the ranking must not be published:

- reviewer orderings do not correlate with each other (median Spearman below +0.20);
- a reviewer identifies its own family's entry in the blinding check;
- **an entry is down to fewer than two reviewers sharing no lineage with it.** Those readers are the baseline its conflicted readers are measured against, and one ordering cannot tell a biased reviewer from a merely different one. The rule is per ENTRY rather than per panel, which is what makes it survive the set of arms growing: a reviewer conflicted on one entry out of nine is still a baseline for the other eight.

**Attention lines**, which are true and do not discard anything:

- the reference entry ranking last - read it as a finding about that implementation;
- a conflicted reviewer missing, which costs one measurement and leaves the rest standing;
- a blinding answer that is neither a letter nor a refusal.

### Reading answers is where this breaks, three times over

Every one of these produced a well-formed report while dropping or inventing an answer. None was a wrong answer from a model.

- **`codex exec` echoes the entire prompt before answering**, the prompt carries the packet, and the packet is source code. Reading from the first brace to the end of the file starts inside the echoed example and runs through thousands of lines that are not JSON. A brace counter is not the fix either: the echoed code carries its own quotes and braces, and a counter walking forwards loses synchronisation inside it. The answer is found by `raw_decode` at each opening brace **from the end backwards**, stopping at the first object carrying the key the caller asked for.
- **`agy` returns an envelope, not an answer**, and that envelope carries a copy of the schema it was handed - whose `properties` object has the answer's keys for its own keys. Searching that file backwards reaches the schema before the answer. So a recognised envelope is unwrapped first and is then the only thing in the file worth reading.
- **A refusal is not the letter it starts with.** The blinding check offers `none` and `cannot_tell` beside the letters, and taking the first character turns `cannot_tell` into `C`. Three of four reviewers refused in the first real run, and the check reported the blinding broken and voided the result.

## The panel is not fixed: it is whatever the packet leaves clean

The reviewers are chosen per packet, and two rules decide who is in it.

**A reviewer whose model is an ARM is out of the packet, not merely conflicted.** The Google reader ran `gemini-3.1-pro-high`; when that id became an arm, the same model would have been reading its own code, and no aggregation rule repairs that afterwards. The family's other id was also an arm, so there was nothing to swap to and the panel went from four readers to three. Check this before building the packet: it is the one conflict that costs a whole reviewer.

**Every other conflict is a property of the PAIR, and it is asked per entry.** A reviewer sharing a family with one entry out of nine is still a baseline for the other eight. So:

- **pass B cannot route around it.** One call ranks the whole packet, so a conflicted reviewer still ranks its own family's entry. What changes is how that placement is USED - it is measured against the readers clean for that entry, never averaged in as if it were one.
- **pass A can, and does.** It is one call per (entry, reviewer), so on an entry written by a reviewer's own family that reviewer is replaced rather than dropped, and the entry keeps two readers. The runner reads the answer key to decide that. This is the one place the key is allowed: it picks which account to bill, never what to show, and it never enters a prompt, a packet or a jail.

Measured on the eight-arm packet, with both conflicted readers present: `opus` placed the sonnet entry at 3 where the clean readers put it at 4.50, and `codex` placed the OpenAI entry at 6 where they put it at 8.50. Both favoured their own family by around a rank and a half. That is why the baseline is per entry rather than a fixed pair.

## Step 6: the measurement floor, before believing any movement

```sh
./run-review.sh --pass-b <packet> <fresh-out-dir>      # repeat, twice
```

Same packet, same lettering, same prompts, same flags, same accounts. Everything that differs between two runs of this is **the panel disagreeing with itself**.

Measured on this subject: the aggregate ordering did not move at all across three runs - swing 0 on every position - while mean rank wandered by up to **0.5 rank units**. Two of the four reviewers reproduced their ordering exactly; one differed once; one never repeated itself.

Both readings are load-bearing, and neither is available without spending the four calls:

- movement in a replication is the **runs**, not the reviewers;
- **a gap thinner than half a rank unit is not one this instrument resolves**, however many replicates it is averaged over.

This is a floor for *this* material. Entries that are close together would leave more room to disagree, and the number would be different.

## Step 7: replicate, because one packet ranks runs

A single packet holds one run of each arm, so a position in it is a claim about that run and only inferentially about the arm behind it. Run-to-run spread inside an arm was 13 to 23 percent in output tokens on this subject, and a spread that size moves a position - two of five did.

```sh
./build_replicates.py --out-root ~/tmp/bead-cost-review/replicates --draw-seed 20260817
for i in 1 2 3 4 5; do
  ./run-review.sh --pass-b ~/tmp/bead-cost-review/replicates/replicate-$i \
                           ~/tmp/bead-cost-review/replicate-answers/replicate-$i
done
./aggregate_replicates.py ~/tmp/bead-cost-review/replicates/manifest.json \
  --answers-root ~/tmp/bead-cost-review/replicate-answers
```

Which run of each arm lands in which packet is **drawn from a seed and written to a manifest**, without replacement, so no run is reviewed twice and one lucky sample cannot carry weight in two replicates. Eligibility is derived from the verdicts rather than listed, because a hardcoded list of the good runs stops being true the next time the campaign is extended.

Each replicate also gets its own lettering seed, so the same arm lands on a different letter every time and an opinion formed about "entry C" carries nothing between packets.

**Read the output in this order.**

1. **The position table.** Five rows of the same ordering is a result nobody needs a test to see. Let the rest support it.
2. **Kendall's W**, from 0 to 1: how strongly the blocks agree on one ordering. This answers *how strong*, which significance never answers.
3. **Friedman**, which answers only whether this much agreement could come from treatments that are interchangeable. Not which beats which, and not whether the difference matters. Two pairwise comparisons at this size would not survive multiple-comparison correction, so none is claimed.

Both statistics are reported twice: over replicates, which are independent blocks, and over every reviewer-replicate pair, which are not - the same reviewers appear in every replicate, so that p is optimistic and is labelled where it is printed rather than in a footnote.

## Adding a model to the comparison

The comparative pass **does not get more expensive as arms are added**. Every entry rides in one packet, so pass B is one call per reviewer per packet whatever the packet holds.

```
pass B, replicated  = reviewers × replicates      independent of the number of arms
pass A              = 2 × entries                 one call per (entry, reviewer)
blinding            = reviewers × packet versions
measurement floor   = reviewers × (repeats − 1)   not optional on a packet that grew
```

For the eight-arm packet that was **45 review calls** with a panel of three - and the 20 already spent on the four-arm packet are *replaced*, not extended, because a ranking is valid only for the set that was ranked.

Pass A findings carry over only where the entry is byte-identical AND the prompt has not changed. The first half is checkable rather than assumed: the same run of the same arm produces the same diff, so hashing the body of each `impl-<letter>.md` and comparing it against the previous packet's says exactly which entries are new. Five of the nine were identical here. Both were true for five entries in the eight-arm packet and the second was not, so they were re-asked; what that bought is in [the results](../results/bead-cost/qualitative-review-eight-arms-2026-08-17.md), and it is not reassuring about finding counts.

The real cost is elsewhere, in three places:

- **The implementation runs.** Five per arm, and one run of a strong model costs more than the whole review pass it will later be judged in.
- **Attention per entry, and this one is now measured rather than feared.** A five-entry packet is 29.7 KB and repeating its comparative pass moved **no position at all**. A nine-entry packet is 59.6 KB, and repeating it moves one position nearly everywhere and two in one place, with mean rank drifting by a full point. The call count is flat; the resolution is not. **Take the floor on the packet you are actually publishing** - a gap that would have been real on five entries is inside the noise on nine.
- **The panel.** Adding an arm from a reviewer's family does not cost you that reviewer, but it does cost you its opinion **on that entry**. Check the families before choosing the models, not after - and if an arm turns out to be the same model id as a reviewer, that reviewer is out of the packet entirely rather than merely conflicted. See below.

Each new arm also needs five runs that pass, or it cannot enter the draw.

## Appendix: what Friedman and Kendall's W actually are

Both are reported by `aggregate_replicates.py`, and quoting a statistic nobody in the room can explain is how a number outlives the caveat attached to it.

**The setup.** Several judges each rank the same treatments. The question: are the treatments different, or are the judges producing noise over things that are interchangeable? With four judges and five treatments, somebody has to come first by accident, and the eye cannot tell that apart from a real ordering.

**Why not an ANOVA or a t-test.** Two reasons, both of which apply here. These are *ranks*, not quantities - the distance from first to second is not comparable with the distance from fourth to fifth, so a mean of positions is a convenience rather than a measured quantity. And the observations are *paired inside each judge*: every reviewer saw the same entries, so a reviewer that is uniformly harsher shifts everything together, and that must not count as a difference between treatments. Friedman is built for exactly that layout - each judge is a block, and only the ordering within a block counts. It is the non-parametric relative of a repeated-measures ANOVA.

**The arithmetic, on the four reviewers of the first real packet.** Sum each entry's ranks:

```
B: 2+1+1+2 =  6      D: 1+2+4+1 =  8      A: 3+3+2+3 = 11
C: 4+4+5+4 = 17      E: 5+5+3+5 = 18
```

If the five were interchangeable each would tend towards `n(k+1)/2` = 12. The deviations are −6, −4, −1, +5, +6, and

```
chi2_F = 12 / (n·k·(k+1)) · Σ R²  −  3·n·(k+1)   =  11.4,  df 4,  p ≈ 0.022
```

**What p ≈ 0.022 means:** if the entries really were interchangeable and the judges ranked at random, agreement at least this strong would turn up in about two panels in a hundred.

**What it does not mean**, and this is where it is usually misread:

- **Not which beats which.** It says a difference exists somewhere. "Is B better than E?" needs a post-hoc test, and at these sizes no pair survives correction for multiple comparisons.
- **Not that the difference matters.** Significance is not effect size. **Kendall's W** is the same arithmetic rescaled to 0-to-1, where 0 is total disagreement and 1 is perfect agreement. On that panel it is 0.71, which matches the median pairwise Spearman of +0.70 measured independently.
- **Not a repair for a small n.** With four judges the chi-square approximation is coarse and the p should be read with suspicion.

**What it would reject.** Take four judges whose orderings cancel out - every rank sum lands near 12, `chi2_F ≈ 0.6`, `p ≈ 0.96`. The means still exist and still sort into a presentable table, and the table means nothing. That is the whole purchase: telling an *ordering* apart from *numbers arranged in order*.

**How the layout changes with replicates.** In a single packet the blocks are reviewers and the treatments are entries. Across replicates the blocks become the replicates - each one a different sample of code from every arm - and the question becomes whether an arm holds its position across samples, which is the question the campaign asks. The same statistic is also reported over every reviewer-replicate pair, which gives many more blocks but not independent ones, since the same four reviewers appear in every replicate.

## What this instrument cannot do

- **It ranks; it does not score.** There is no absolute scale, and positions from different packets do not compare.
- **A finding count is not a quality score.** It measures a reviewer's threshold as much as the code.
- **It sees no tests.** The packet excludes them so entries stay structurally comparable, and the price is that reviewers overstate regression risk - one finding here claimed an invariant was "protected only by a comment" when a canonical test in the subject's own suite pinned it, and had pinned it since before the base commit.
- **One bead is one bead.** A cost bead is chosen so every arm passes it; it separates arms by what they spend and what they leave behind, not by capability. Nothing measured on it generalises to a task that separates by capability without measuring that task.
