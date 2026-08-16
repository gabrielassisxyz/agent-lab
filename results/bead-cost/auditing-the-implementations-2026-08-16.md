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

| arm | findings not present in the base |
| --- | --- |
| kimi-k2.7 | **0** |
| gemini-3.7-flash | **0** |
| sonnet | **0** |
| deepseek pro-high | **0** |
| deepseek pro-max | 3 to 16 |

And the deepseek-max findings decompose entirely into things pass 1 already reported:

- **three per run** are `staticcheck` restating the compile failure (`ReserveRateSlot undefined`);
- **the thirteen extra on one run** are all in `internal/route/crash_test.go`, a test file that run authored. That is a leak in the isolation rather than a finding about an implementation, and it is recorded under the coverage gaps below.

**Pass 2 produced no independent finding.** Everything it reported, pass 1 had already said, for a tenth of the cost.

### The negative control, without which the zeros mean nothing

Twenty clean reports read exactly like a scanner that returns zero for everything. So one implementation that scanned clean was given a single injected defect of the shape these tools exist to report - an HTTP response whose error is discarded and whose body is never closed - and scanned again:

```
without the defect   new=0
with the defect      new=3   gosec G107, go.http-default-client, go.http-response-body-not-closed
```

The instrument fires. The zeros are measured rather than absent.

## What was NOT measured

Stated because a result that hides its gaps is the same error in a different costume.

- **`errcheck` never ran, on any tree.** It fails on the base itself with `failed to check packages`, because the base's `reservation_test.go` does not compile - which is the bead's contract. `errcheck` loads the package including its tests and gives up. It contributed zero findings and the aggregator read that as "nothing to report" rather than "did not run", which is exactly the ambiguous zero this repository keeps being bitten by.
- **`govulncheck` and `golangci-lint` were not wired in**, although both are installed. `govulncheck` is the only one of these that would notice a run editing `go.mod`, and `golangci-lint` aggregates the most linters, so it is the most likely of the three to have produced something new.
- **Test files a run CREATED leak into the delta.** The isolation restores every test file that exists at the base, but does not remove test files a run added. One run's own `crash_test.go` therefore contributed thirteen findings about test code to a comparison meant to be about implementations.

None of these changes the conclusion - pass 1 carried the entire signal and pass 2 added nothing independent - but "does not change the conclusion" is a different claim from "was measured", and only the second one was asked for.

## What this says

**The silent bug did not appear.** Twenty implementations, each around 150 lines, pass sixteen canonical criteria, the repository's own 52 test files, the race detector and static analysis, and change no exported contract.

**The one real defect was loud, not silent.** Deleting six public methods is something a compiler shouts about. It stayed invisible for exactly one reason: the scorer restored a single test file instead of all of them, so a run could rewrite the tests that would have objected. Repairing the scorer surfaced it immediately.

**The ordering held, and by a wider margin than expected.** Pass 1 found everything for eleven seconds and no tokens. Pass 2 cost roughly ten minutes of scanning and found nothing pass 1 had not. For a Go subject, the exported-API diff was the highest-yield check in the plan and is also the cheapest thing in it.

## What is left for a reviewer

Three questions were on the table. Two are now answered without a model: *did it introduce a bug* and *did it break something*.

The third is not, and no deterministic tool answers it: **does this implementation make future work harder?** Layering, naming, where state lives, whether the abstraction earns itself. That is the qualitative half of the rubric, still never exercised.

If it is worth spending on, the scope suggested by these results is much smaller than twenty-five reviews: one implementation per arm, blind to which lane produced it, asked only that question. The other two have their answers already.
