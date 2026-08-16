# Auditing the implementations: did any of them introduce a problem?

Twenty-five implementations of `llmux-p4-two-phase-reservation-5vg` survive from the five-arm campaign. A verdict of sixteen out of sixteen says a run satisfied the bead's verification. It says nothing about what else the run did, and the campaign had already shown that gap mattering: one arm was recorded as passing four times while deleting exported methods the package depended on.

So the question here is the other one. **Did any implementation introduce a defect, break something that already worked, or leave the repository harder to build on?**

Two passes were run for it, cheapest first, on the principle that a reviewer should never be asked to read code a compiler has already rejected.

## Pass 1: what the toolchain decides by itself

`evals/bead_cost/audit_go.py`. Per implementation: `go build ./...`, `go vet ./...`, the full test suite across all twelve packages, the race detector on the concurrency package, and a set difference over every exported declaration against the base.

Every test file in the repository is restored from the base first. A run is free to edit tests, and grading against the tests a run shipped lets it move the goalposts and call that a pass. It grades a copy; the run's tree is never written to.

| arm | clean | failing |
| --- | --- | --- |
| kimi-k2.7 | 5/5 | |
| gemini-3.7-flash | 5/5 | |
| sonnet | 5/5 | |
| deepseek pro-high | 5/5 | |
| deepseek pro-**max** | **0/5** | vet, full suite and race all fail |

**Twenty of twenty-five are clean on every check.** The five that are not are one arm, and they fail the same way.

### The exported API each arm removed

The cheapest check in the whole plan is a set difference over strings, and it isolates the responsible arm by itself:

| declaration removed from `Coordinator` | removed by |
| --- | --- |
| `ReserveRateSlot` | all 5 deepseek-max |
| `FinalizeDispatch` | all 5 deepseek-max |
| `ReleasePendingRateSlot` | all 5 deepseek-max |
| `IncrementInFlight` | 4 of 5 deepseek-max |
| `DecrementInFlight` | 3 of 5 deepseek-max |
| `ExpireGateIfDue` | 3 of 5 deepseek-max |

Six exported methods. All of them exist at the base commit **and in the commit that implemented this bead for real**, so nothing about the task asked for their removal. **No run in the other twenty removed anything.**

Cost of the pass: about eleven seconds per implementation and no tokens.

## Pass 2: UBS and the Go analysers, against a baseline

A scan without a baseline is not a measurement of the run. **The base commit alone carries 346 findings** across these tools - UBS's own summary counts 12 critical, 107 warning and 831 info - and attributing those to whichever model is scanned next is precisely the mistake this experiment exists to avoid.

Findings are keyed on tool, rule, file and code snippet, never on line number: a run that adds a function shifts every line below it, and keying on position reports the whole file as new work. The tree scanned is the same one pass 1 grades, so test files are identical across runs and cancel.

The first sweep used three tools and one column; the corrected sweep, with five tools and production and test findings separated, is in the section after next. Under either, **pass 2 produced no independent finding**: everything it reported, pass 1 had already said, for a tenth of the cost.

### The negative control, without which the zeros mean nothing

Twenty clean reports read exactly like a scanner that returns zero for everything. So one implementation that scanned clean was given a single injected defect of the shape these tools exist to report - an HTTP response whose error is discarded and whose body is never closed - and scanned again:

```
without the defect   new=0
with the defect      new=3   gosec G107, go.http-default-client, go.http-response-body-not-closed
```

The instrument fires. The zeros are measured rather than absent.

## The three gaps this page first reported, and how they closed

They were written down before they were fixed, because a result that hides its gaps is the same error in a different costume. All three are now closed and the scan was re-run from scratch against a rebuilt baseline.

- **`errcheck` never ran, on any tree.** It type-checks each package including its tests, and the base has a package whose test does not compile by construction - that failing test IS the bead's contract - so it aborted the whole run and contributed a zero that read as "nothing to report". With `-ignoretests` it runs, and reports **zero on the base and on the reference solution**: the repository genuinely has no unchecked errors in production code, which is a measurement rather than an absence.
- **`govulncheck` and `golangci-lint` were not wired in.** Both are now. `golangci-lint` adds seven findings to the baseline; `govulncheck` reports none, and is the only tool here that would notice a run editing `go.mod`.
- **Test files a run CREATED leaked into the delta.** They are not discarded, because they are work the run did - they are counted in **their own column**. A single total reads "wrote extra tests" as "introduced more problems", which inverts the incentive: one run authored a 100-line crash test and drew findings for it while runs that wrote no extra tests drew none.

### The scan re-run with all five tools and the split columns

The baseline is 353 findings on the base commit. Against it:

| arm | new in production | new in run-authored tests |
| --- | --- | --- |
| kimi-k2.7 | **0** | 0 |
| gemini-3.7-flash | **0** | 0 |
| sonnet | **0** | 0 |
| deepseek pro-high | **0** | 0 |
| deepseek pro-max | **0** | 6 to 19 |

**Every arm introduces zero static-analysis findings into production code**, including the one whose implementations do not compile. What the earlier pass reported as "three to sixteen findings" for that arm was a compiler error restated by `staticcheck` plus findings in test files the runs wrote themselves. Splitting the columns did not soften the result; it moved it to where it belongs, and pass 1's verdict on that arm is unchanged and unforgiving.

The negative control was re-run against the five-tool scanner and still fires: zero without the injected defect, three with it.

**One regression was introduced and caught while wiring the extra tools.** Making the runner merge stderr broke UBS, whose progress lines corrupted its SARIF, so it contributed 0 instead of 335 - and it was found only by comparing against the earlier baseline. A parser that returns zero on malformed input is indistinguishable from a clean tree, which is the shape this repository keeps paying for.

## What this says

**The silent bug did not appear.** Twenty implementations, each around 150 lines, pass sixteen canonical criteria, the repository's own 52 test files, the race detector and static analysis, and change no exported contract.

**The one real defect was loud, not silent.** Deleting six public methods is something a compiler shouts about. It stayed invisible for exactly one reason: the scorer restored a single test file instead of all of them, so a run could rewrite the tests that would have objected. Repairing the scorer surfaced it immediately.

**The ordering held, and by a wider margin than expected.** Pass 1 found everything for eleven seconds and no tokens. Pass 2 cost roughly ten minutes of scanning and found nothing pass 1 had not. For a Go subject, the exported-API diff was the highest-yield check in the plan and is also the cheapest thing in it.

## What is left for a reviewer

Three questions were on the table. Two are now answered without a model: *did it introduce a bug* and *did it break something*.

The third is not, and no deterministic tool answers it: **does this implementation make future work harder?** Layering, naming, where state lives, whether the abstraction earns itself. That is the qualitative half of the rubric, still never exercised.

If it is worth spending on, the scope suggested by these results is much smaller than twenty-five reviews: one implementation per arm, blind to which lane produced it, asked only that question. The other two have their answers already.
