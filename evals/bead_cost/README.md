# bead-cost experiment - the environment

Measures **cost per completed bead, per lane**, on one real bead in a real repository, so that a subscription decision rests on a measured unit rather than on a per-token price. The full design - the arithmetic, the rubric, the run environment and the execution protocol - lives outside this repo with the decision it feeds; this directory is the runnable environment for it.

**This is not a SWE-bench experiment and shares none of that machinery.** No Docker, no `predictions.jsonl`, no eval image. The agents are the ones this machine actually uses, and the scoring instrument is the bead's own canonical verification applied to each run's diff. What is borrowed from this repo is its discipline, not its runner: the noise floor comes first, the metric must have headroom, the sandbox is part of the instrument, and no number is ever fabricated.

## Harness, model, lane: three words, and they were once two

A **lane is the pair**: one harness driving one model on one account. It is the unit of comparison, because the halves are not separable. The same model through two harnesses is not one measurement - `agy` reports an envelope total and `pi` a per-turn sum, and the context floor each one pays differs - and the same harness on two models is exactly the comparison this experiment exists to make. The account is part of it too, since the request ceiling is per account.

| word | what it names | where |
| --- | --- | --- |
| `harness` | the agent CLI that drives the run: `pi`, `agy`, `claude` | `run.sh`'s second argument, `record.json`, `tabulate.py`'s column |
| `model_route` | the id the proxy is asked for, account suffix included: `litellm/kimi-k2.7-k2` | `run.sh`'s third argument, `record.json` as `model`, `runs.json` |
| lane | the pair of the two. Not a field: it is the key of a `runs.json` entry and the roster name in `sweep.sh` | prose, and the results tables |

**`lane` used to be a field, and it named different things in two places** - the harness in `record.json`, the model route in `runs.json`. A reader joining the two on that key would have grouped `pi` with `litellm/kimi-k2.7-k2` as though they sat on one axis. The word now appears only where it means the pair, and the two halves each carry their own name.

One compatibility seam survives, deliberately: the marker file inside a run directory is still called `lane` and still holds the harness. Dozens of run directories on disk carry it, and re-collecting a verdict from kept artefacts is how a metric gets repaired without paying for the runs again. `tabulate.py` reads both keys for the same reason, so a run collected before the rename does not print a blank column and read as a run whose harness went unrecorded.

## The subject is a parameter, and it has moved once

The harness takes the subject repository, the bead and the base commit from the environment; nothing about a language or a repository is hardcoded in `run.sh`, which picks its warm-up and its scorer from the subject's manifest (`go.mod` or `Cargo.toml`).

| | first subject | current subject |
| --- | --- | --- |
| repository | `archeion` (Rust) | `llmux` (Go) |
| bead | `arch-42q` | `llmux-p4-two-phase-reservation-5vg` |
| base commit | `6edbb8e` | `64cfb7e`, the parent of the implementing commit |
| verdict | 5 criteria, binary | 16 test functions, graded, plus a `build_failed` flag |
| cold build | minutes, 4.5 GB of build directory | 22 s |

**`arch-42q` was retired on 2026-08-16**, after four independent lanes concluded its acceptance criteria cannot be met from inside the repository. The reasoning, the construction of the replacement and the selection filters that now govern the choice are in [`results/bead-cost/subject-change-2026-08-16.md`](../../results/bead-cost/subject-change-2026-08-16.md).

**The current bead is a cost bead, deliberately.** The cheapest lane passes it on the first attempt, which makes it useless for measuring difficulty and exactly right for measuring what a completed bead costs per lane: every lane finishes, so every lane yields a completed unit to divide by. A harder bead, in the 30 to 70 percent band, is a separate instrument for the capability question.

Confirmed rather than assumed: five runs of that lane all returned 16 of 16, with about 12 percent relative sd on turns and on output tokens. That spread resolves a difference of roughly 20 percent at five runs per arm, so five is enough for lanes that differ by a lot and not for lanes that differ by a little. See [`results/bead-cost/cost-bead-noise-floor-2026-08-16.md`](../../results/bead-cost/cost-bead-noise-floor-2026-08-16.md).

## Why it lives here

Because `docs/DESIGN.md` §6–§10 is the record of this exact class of experiment going wrong and being caught, and every trap it names applies unchanged:

- **Variance** - the same prompt on the same model varied 3× on the quota meter, and turns carried 44% relative sd on the ancestor experiment.
- **Statistical power** - one task repeated is coin flips. This experiment accepts that knowingly: it answers the *cost* question, where the lanes differ by up to sixty times, and gives only a directional read on quality.
- **The sandbox is part of the instrument** - with two leaks specific to running on the host rather than in a container, both closed by `sandbox.sh` and both checked by `verify.sh`.

## What is here

**Driving a run**

| file | what |
| --- | --- |
| `run.sh` | drive one run end to end, in the one order that is safe: base repo, checkout, sandbox, prompt, verify, warm the build, then measure |
| `sweep.sh` | run rounds across several lanes, unattended, until a deadline. Decides nothing; every run still goes through `run.sh` |

**Building the environment**

| file | what |
| --- | --- |
| `base-repo.sh` | build the isolated base repository every run is cut from, holding ONE branch at ONE commit, named per subject |
| `checkout.sh` | cut one run's checkout from that base, so it has a ref namespace of its own |
| `sandbox.sh` | build a per-run `HOME`: copy the constant config, zero the state, close the leaks |
| `harden-worktree.sh` | narrow the jail's mapping to the run's own worktree, so the rubric is out of reach |
| `verify.sh` | prove the isolation **before run 1**, rather than assume it |
| `bead_prompt.py` | render the bead as the task statement, from whitelisted fields. Exists because the tracker's own comment log announced the fix and named its identifiers |

**Scoring**

| file | what |
| --- | --- |
| `find-work.sh` | find the tree a run actually left its work in, rather than the one it was launched in |
| `score.sh` | apply the Rust canonical verification to one run's worktree and emit its verdict |
| `score-go.sh` | the same for a Go subject, graded per test function rather than binary |
| `go_verdict.py` · `test_go_verdict.py` | reduce `go test -json` to a verdict; the tests pin the build-failure semantics |
| `classify.py` · `test_classify.py` | say what a run's outcome was in the vocabulary the arithmetic needs: `admitted`, `wrong`, `no-diff`, and the unreachable cases |
| `rescore.sh` | re-grade runs that already happened, from the trees they left, and write the verdict back |
| `fixtures/benchmark_arch_42q_verify.rs` | the first subject's canonical verification, vendored |
| `fixtures/llmux_5vg_reservation_test.go` | the current subject's, 16 test functions. Already present in the base tree, so the contract reaches the agent through the failing test |

**Reading the results**

| file | what |
| --- | --- |
| `collect.py` | reduce one run to its record, from raw artefacts only, reporting absent as `null` |
| `tabulate.py` | reduce every run under the root to one table, regenerated rather than maintained |
| `trail.py` | follow a pi session live, or read a finished one |
| `agy_trail.py` | the same for agy, which does not stream and keeps its trajectory in SQLite |

### Three defaults that are this bead's, not generic

- **`score-go.sh` carries `5vg`'s fixture, path and package** in `BEAD_COST_GO_FIXTURE`, `BEAD_COST_GO_FIXTURE_PATH` and `BEAD_COST_GO_PACKAGE`. A different bead needs all three set, or it silently grades the wrong package.
- **The prompt is built once per bead and cached** at `_prompt-<bead>.txt` under the run root, deliberately, so lanes are never compared on prompts that differ by a byte. **If the prompt builder changes, the stale file wins and nothing warns you** - delete it to regenerate.
- **The Go warm-up requires `go build ./...` to succeed but only tries to compile the tests.** That is not laxity: on this bead one test package failing to compile IS the task, and requiring it rejected the first pilot outright.

## Constant is fine, varying is not

The instinct is to choose between a *realistic* environment and a *clean* one. That is the wrong axis. A constant - the global `CLAUDE.md`, the skill library - shifts every lane by the same amount and cancels in a comparison of lanes; on `agy` it is not overhead at all but the measured 34.5k token floor. Stripping it measures a machine nobody owns, while the decision being fed is explicitly *what does it cost if I route my real work here*.

What ruins the measurement is state that **differs between runs**, and worst of all state that accumulates as the runs go, so the last lane is measured on an easier problem than the first.

**Kept:** the five generated global config files · the skill library, frozen for the window · the `ai-jail` wrappers · the repo at one base commit.

**Isolated:** `ai-memory` - it writes and reads back, so run 1 records what it learned and run 7 starts ahead, which systematically favours whichever lane runs last · session and handoff state · web-reaching tools · the build cache, whose first run pays the compile that the rest do not.

## The two leaks that are specific to running on the host

Neither leaves a trace in the diff, which is what makes them worth a script rather than a habit.

1. **`ai-jail` is not a state boundary.** It is a filesystem blast-radius control and it *requires* `~/.claude` and `~/.config` read-write - it refuses to hide them. Inside the jail every run shares one memory store and one session history.
2. **The benchmark's own notes are readable from a run.** `~/repositories` is mounted read-write and `archeion` carries no `.ai-jail` of its own, so a run can reach the rubric - which names the hook that produces the plausible-wrong-fix and explains why it is the wrong layer. A model that wandered in would be handed the judgement section's answer.

## The pilot comes first, and it is not a formality

**One agent, one run, checked to exhaustion before anything runs in parallel.** The reason is on the record twice: this repo collected ten runs whose `node_recall` was `0.0` on every one of them and which was *structurally incapable* of returning anything else; and building the canonical verification for this experiment turned up five defects of the same family, the worst being a `--concurrency 1` that made three of the five criteria unable to pass however correct the fix.

Before a second run is launched:

1. **Re-derive every recorded number by hand** from the raw artefacts and check it against what the harness reported. A metric that is constant across a dimension it should vary on is the signature to hunt.
2. **Read the trajectory for contamination** - a memory, a previous run's branch, a web result, the rubric.
3. **Score the diff twice** with the rubric, which is also the rubric's own required sanity check.
4. **Confirm cost landed** in `kernl orchestrator stats` and that turns is populated for that lane.

**Keep every raw trajectory.** The whole `node_recall` correction was a re-read of data already on disk: no inference, no API, no cost. A benchmark that keeps only its summaries cannot be repaired, only rerun.

## Parallelism, once the pilot is clean

- **Ollama: the limit is a request RATE per account, and that changes the arithmetic.** The plan was three account keys with three concurrent runs each. The pinning half works and is not in question: the deployment that rate-limited was the pinned one, by name. The concurrency half is the problem. **A single run, alone on one key, hit `429` twice** - the second time four consecutive throttling errors exhausted the proxy's three retries and ended it. Its cause was measured rather than assumed: the two other keys answered immediately when probed, which an exhausted account quota would not, and the failing run was issuing a tool call roughly every two seconds for an hour.

  So the keys do not divide a budget between them; each one has a ceiling on requests per unit of time, and one agent of this shape already saturates it. **Three runs per key does not mean a third of the load each - it means three runs competing for one ceiling, all three degrading together**, with the cooldown landing in a wall clock that would then be reported as the model's.

  The number to measure is therefore **requests per second one account tolerates**, not how many keys exist. That is cheaper and more conclusive than inferring it from whole runs, and it is what should decide the concurrency.
- **`agy`: one at a time.** The quota does not support concurrency and the failure mode is several runs dying mid-way against a limit, which spends the quota *and* produces no data point.
- **Claude and Codex last.** Codex waits for its window reset regardless.

`wall_time` is contaminated by design and is never reported as a clean signal - on the ancestor experiment two of ten runs sat ~26 minutes in client-side backoff and died at timeout. With nine concurrent runs on three keys, rate-limit waiting is guaranteed. A run killed by a limit records `timeout: true` and is never confused with a model that failed.
