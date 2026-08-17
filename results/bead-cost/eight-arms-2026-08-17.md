# Eight arms on the cost bead, and the number that was answering two questions

Sixty runs on `llmux` bead `llmux-p4-two-phase-reservation-5vg`, base `64cfb7e`, across eight arms
and one that was parked. Every figure is read from the run artefacts, and every run was re-scored by one instrument
after the repair below, so nothing here is a mixture of two scorers.

**The headline is not the cheapest arm.** It is that "passed 0 of 5" turned out to mean two
different things, and only one of them was about the model. The scorer restores the graded package's
whole test surface from the base commit before applying the canonical file — which is what stops a
run passing by weakening the very test that states the contract, and is not in dispute. The cost is
that the canonical file calls helpers defined in those restored files, and those helpers call
methods a refactor may have removed. So a run that reorganised the package's public API and migrated
its tests to match fails to **compile** before one canonical assertion runs, and every criterion is
reported false.

Eight runs across three arms were sitting in that hole: they implement the two-phase reservation and
pass all sixteen canonical tests on their own tree. One arm's published headline moved from 0 of 5
to 5 of 7 on that difference alone.

The scorer now grades twice and reports both answers.

| regime | what it asks |
| --- | --- |
| `contract` | the canonical file over the tree as the run left it. Are the sixteen behaviours there? |
| `contract_with_legacy_api` | the same, plus every test file in the package restored from the base. Are they there **and** did the pre-existing public API survive? |

`passed` carries the first, because completing the bead is what the cost arithmetic divides by. The
second is reported per run as `pre_existing_tests_pass`, and it is a finding rather than a zero.

## What the arms cost

Means are over the arm's **usable** runs; `±` is relative standard deviation. "API kept" counts the
solved runs whose tree still satisfies the package's pre-existing tests.

| arm | solved | API kept | turns | output | reasoning | lines added |
| --- | --- | --- | --- | --- | --- | --- |
| gpt-5.6-terra / `codex` | **5 of 5** | 5 of 5 | **27** ± 13% | **8 098** ± 13% | 3 091 | **128** ± 23% |
| kimi-k2.7 / `pi` | 5 of 5 | 5 of 5 | 46 ± 12% | 13 034 ± 13% | 8 993 | 152 ± 13% |
| gemini-3.7-flash / `agy` | 5 of 5 | 5 of 5 | 62 ± 20% | 23 234 ± 15% | 14 974 | 168 ± 10% |
| gemini-3.1-pro-high / `agy` | 8 of 8 | 5 of 8 | 42 ± 45% | 26 838 ± 44% | 19 808 | 137 ± 27% |
| sonnet / `claude` | 5 of 5 | 5 of 5 | 57 ± 21% | 32 637 ± 16% | 21 206 | 169 ± 15% |
| deepseek pro-high / `pi` | 5 of 5 | 5 of 5 | 45 ± 22% | 33 412 ± 23% | 24 049 | 142 ± 9% |
| deepseek flash-high / `pi` | 7 of 8 | 4 of 7 | 61 ± 35% | 58 293 ± 42% | 38 320 | 322 ± 57% |
| deepseek pro-max / `pi` | 5 of 7 | 1 of 5 | 71 ± 24% | 70 206 ± 41% | 42 439 | 435 ± 46% |

**Output tokens per completed bead** — the arm's whole spend divided by the beads it finished, which
is the unit a subscription decision rests on:

| arm | per completed bead |
| --- | ---: |
| gpt-5.6-terra | **8 098** |
| kimi-k2.7 | 13 034 |
| gemini-3.7-flash | 23 234 |
| gemini-3.1-pro-high | 26 838 |
| sonnet | 32 637 |
| deepseek pro-high | 33 412 |
| deepseek flash-high | 66 621 |
| deepseek pro-max | 98 289 |

**Twelve times** separates the cheapest completed bead from the most expensive, against a run-to-run
spread of 13 to 45 percent inside each arm. Only one arm publishes a price: `claude`, at
**US$ 3.24 of list price per completed bead**, carried under `list_price_usd_not_paid` because the
lane authenticates with a subscription token. What was spent there is allowance, not dollars, and
none is invented for the Ollama or Antigravity lanes.

## Removing the old API is the expensive path, in three model families at once

The runs that removed pre-existing public methods are not a random subset of their arms. Split by
`pre_existing_tests_pass`, over solved runs only:

| arm | kept the API | removed it |
| --- | --- | --- |
| deepseek pro-max | 44 turns · 25 229 output · +147 lines (n=1) | 77 turns · 75 404 output · +412 lines (n=4) |
| deepseek flash-high | 45 turns · 44 821 output · +232 lines (n=4) | 75 turns · 78 266 output · +454 lines (n=3) |
| gemini-3.1-pro-high | 30 turns · 18 795 output · +112 lines (n=5) | 62 turns · 40 242 output · +179 lines (n=3) |

Every arm that did it paid between 1.7x and 2x the turns and between 1.7x and 3x the output for the
same bead, and wrote between 1.5x and 2.8x the lines. Three different model families, the same
shape. The reading is not that the refactors are wrong — they compile, they pass the contract, and
the removed methods have **no production caller anywhere in the repository**, only tests. It is that
choosing to reorganise a package's public surface while implementing a bead costs about twice as
much, and hands the next reader a migration nobody asked for.

Whether that trade is worth making is a question about design, and the deterministic scorer cannot
answer it in either direction. It is the sort of question the qualitative review exists for.

## Two arms are not in the table on purpose

**`deepseek flash-max` was parked after two runs**, both of which produced no diff. Their failure has
a signature: one turn emitted 31 999 output tokens against the alias's `max_tokens: 32000` and
stopped with `length`, and the run never recovered. The ceiling is identical on all four deepseek
aliases and the other three work inside it, so it is a constant of the environment rather than a
handicap — but two runs is not a result, and three more were stopped by hand before they could be.
The arm is recorded and not reported.

**`gpt-5.6-terra` cost nine runs to collect five.** Three declined to implement anything, and said
why: the subject's own `AGENTS.md` states that when a coordination protection is unavailable an
agent must not implement or commit until it is restored, and MCP Agent Mail is not running on this
machine. Those three are `blocked` and leave the arithmetic entirely — they are an environment gap,
not a measurement, and a real session in that repository today meets the same wall. One more was
stopped by hand and is `killed`.

That is worth stating plainly rather than burying in a count: **the only arm that read the
repository's rules and obeyed them is the only arm the rules cost anything.** The other seven
implemented straight through the same instruction.

## What this does not say

- **One bead is one bead.** This one was chosen so that every arm can pass it, which makes it a cost
  instrument and not a capability one. Nothing here generalises to a task that separates by
  capability without measuring that task.
- **Token columns do not compare across harnesses.** `pi` and `codex` report input summed over their
  model calls; `claude` and `agy` report an envelope total; the Ollama lanes publish no cache
  information at all, so a zero there is an absence rather than a reading.
- **Wall time is contaminated by design.** It includes upstream backoff and, on the lanes that share
  three account keys, time spent queueing behind another run.
- **`lines added` is a size, not a quality.** It is here because it separates the two behaviours in
  the section above, not because shorter is better.
