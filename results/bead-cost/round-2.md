# bead-cost round 2, 2026-08-14

The pilot beside this file is **discarded**: its cost figures were void for the five environment defects recorded there, and the two vectors that would have voided everything after it were still open when it ended. This round is the first run of the instrument with those closed.

**Two lanes, one completed.** The agy lane produced a solution that passes the admission gate. The deepseek lane produced nothing, killed by its own output ceiling in under eight minutes, and is a failed run rather than a wrong answer.

## What changed in the instrument first

Nothing here would be worth reading if the environment were still the pilot's. Five changes, each proven against the arrangement it replaces:

- **Every run is a clone of a base repository holding one branch.** Runs used to be linked worktrees of the shared subject repository, sharing one ref namespace, so `git log --all --oneline` inside a run opened with earlier runs' commit subjects, which name both the fix and the layer it belongs in. The gate now asserts that `rev-list --all` equals `rev-list HEAD`; against the old arrangement it fails and prints eight foreign commits.
- **The run executes inside `ai-jail`.** The rubric and the canonical verification were readable at an absolute path for the whole of every previous run: the check for that was made through the jail while the runs were launched outside it, so the vector the harness named was never actually closed.
- **The agy lane's credential is copied.** It is not `oauth_creds.json` but `~/.gemini/antigravity-cli/antigravity-oauth-token`. Without it the lane fails authentication in about two seconds. The pilot's agy sandbox has `You are not logged into Antigravity` in its log at the second it started.
- **The collector reads the token counts the harnesses write.** It was looking for aliases pi does not use and reported a well-formed zero for a run of twenty-eight turns; agy had no reader at all.
- **The build warms before the clock starts, serialized across runs.** Two concurrent warm-ups unpacking into one shared cargo registry is a real failure, and it took the first concurrent pair here.

## The runs

Subject: `archeion` bead `arch-42q`, base `6edbb8e`. Byte-identical prompt across lanes, built once and copied per run.

| | gemini-3.7-flash-medium via `agy` | deepseek-v4-pro-max via `pi`, key k1 |
|---|---|---|
| outcome | **completed**, admitted | **failed run**, produced nothing |
| wall clock | 11 min 24 s | 7 min 54 s |
| harness-reported duration | 679.2 s | not reported by this harness |
| turns | 1 (agy counts its own retries) | 39 |
| commit | `cc697df` | none; tree left at base |
| canonical verification | **5/5** | a1 only, which is the unmodified base signature |
| full suite | 501 passed, 0 failed | not applicable |
| new dependency | none | not applicable |
| files changed | 4 (+63 / -26) | 0 |

### Why the deepseek run failed, and what it is not

Thirty-seven turns ran normally. The thirty-eighth spent **65 536 output tokens, 61 104 of them reasoning**, hit `stopReason: length`, and pi compacted once and ended the session with exit 0, an empty stdout and nothing committed.

Three things follow, and none of them is "the model got the bead wrong":

- **It never produced an answer to be wrong about.** `score.sh` grades whatever tree it is handed, and an untouched base tree scores exactly like a wrong fix. What separates them is the record's `worktree` block: `committed: false`, `dirty: false`, head equal to the base commit.
- **The ceiling is the deployment's, not the catalog's.** `models.json` declares `maxTokens: 32000` for this lane and the observed cut was 65 536.
- **The thinking flag does not govern it.** pi recorded `thinkingLevel: "off"` for the session and the model produced 70 168 reasoning tokens across the run.

### Usage, and why the two columns must not be compared

| | agy | pi |
|---|---|---|
| input | 772 536 (envelope total) | 2 342 485 (per-turn sum) |
| output | 76 308 | 82 307 |
| reasoning | 48 764 | 70 168 |
| cache read | 16 103 935 | not reported |

**These are different measurements wearing the same labels.** Summing per-turn input counts the whole prompt again every turn, which is what the lane sends but not what an envelope reports. And Ollama publishes no cache information at all, so the blank is absence rather than a zero.

## The isolation was exercised, not just asserted

The agy run ran `git status && git branch -a` in its checkout, unprompted, roughly where the pilot's agy run was observed looking for `arch-` beads. What it got back was:

```
* main    remotes/origin/main
  remotes/origin/HEAD -> origin/main
```

No sibling branch, nothing to read. The agent went looking exactly where the leak used to be and found nothing, which is the only kind of evidence that settles this.

The trajectory sweep is otherwise clean for both lanes: no reference to the notes, the rubric, the canonical verification or any earlier run's branch. The one grep hit for `project-notes` in the agy trajectory is the text of the global instruction files, which are a deliberate constant of the environment and identical for every lane.

## What the agy solution did

Not the same architecture as the pilot's agy run, which added `async-trait` and wrapped the HTTP client. This one reuses `html_escape::decode_html_entities`, already in the repository, and decodes the href before the URL is built from it, which is the layer the bead names.

It also takes over link discovery to do it: it opens a broadcast queue on the website and returns `queue_tx.is_none()` from the should-crawl callback, so the engine's own enqueueing is suppressed and the frontier is fed explicitly. **That is a judgement call about placement rather than a correctness question, and it is what the rubric's section B exists to weigh.** The admission gate says the change works; it does not say the layer was the right one to take over.

## Still open

- **One completed run is not a cost figure.** The arithmetic divides the cost of every run by the runs that completed, and with one lane at one completion there is no denominator worth dividing by yet.
- **Whether the deepseek lane is viable on this harness at all.** One run cannot separate an unlucky turn from a lane that cannot finish a task of this shape without blowing its output budget.
- **The request-rate ceiling per account**, still unmeasured, still the precondition for any concurrency number.
