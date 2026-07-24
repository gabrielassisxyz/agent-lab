---
status: active
last_reviewed: 2026-07-14
---

# Design — what this repo measures, and why it is built this way

> Decision record for the benchmark. Written before any code, from the session that turned the spark conversation (two months old) into a concrete instrument.
>
> **Read this before touching `evals/`.** Most of what is below is *why a thing was rejected*, and rejections are the part nobody can reconstruct from the code.

---

## 1. What this is, and what it is not

**This is a curiosity project.** It is not tied to a deadline or a deliverable, and no outside goal is allowed to steer its scope. It exists because the questions below are genuinely interesting and the answers do not exist anywhere yet. If it later produces something publishable, good — but that is a side effect, and designing for it would corrupt the design.

**The objective, in order:**

1. **Run existing benchmarks end to end, to understand how they actually work.** The artifact of this step is *comprehension*, not a score: open a trajectory, watch the agent work, watch the scorer decide pass/fail.
2. **Build our own tasks**, once (1) has taught us what a task really is.
3. **Later: build an agent** (~300 lines in a loop, in ghuntley's framing), and use (1) and (2) as its test bench.

**The questions that motivate it** — the whole point is that these have *no published answers* for this specific setup:

- **Does a personal agent-scaffolding layer (skills, `AGENTS.md`) do anything?** Skills on/off, `AGENTS.md` on/off.
- **Does multi-agent orchestration beat a single agent?** (a custom multi-agent orchestrator is the concrete shape in mind.)
- **Which agent harness is actually better** — mini-swe-agent, Claude Code, Codex, `pi`, OpenCode — *for one real, opinionated workflow*.
- **Greenfield vs brownfield**, because the answer is probably not the same.

---

## 2. The spark, and the concept it has a name for

The origin is a conversation from ~May 2026 (kept in the maintainer's private notes). It starts as "why is the SWE-bench leaderboard stale" and turns, at the point where it asks whether open-weight models' downsides can be mitigated *by optimizing the harness's own prompt and the environment it works in*.

That idea has a name in the literature: **agent scaffolding** / **harness engineering**. The claim that made it interesting — *the same model can vary up to 6x in performance purely by changing the harness around it* — **is not verified.** It came from an LLM answer, and the citation behind it has not been checked. **Do not put that number in anything public until someone reads the source.** It is a hypothesis, and this repo is one attempt to test a small corner of it.

The four arXiv links from that conversation **were confirmed to exist**: `2407.16741` (OpenHands), `2604.03515` (Inside the Scaffold), `2602.05892` (ContextBench), `2601.21064` (Textual Equilibrium Propagation).

---

## 3. The benchmark choice: SWE-rebench

**Chosen: [SWE-rebench](https://swe-rebench.com/)** (`nebius/SWE-rebench-leaderboard`), scored by [the SWE-bench fork](https://github.com/SWE-rebench/SWE-bench-fork).

### Why — and the argument is entirely about contamination

Contamination is not an academic footnote here. **It destroys the exact effect this repo is trying to measure**, and it does so in the most dangerous way possible: by producing a *null result that looks credible*.

The mechanism: if a task is in the model's training data, the model **recalls the gold patch**. It then succeeds *with* the scaffold and *without* it — memorisation does the work the scaffolding would have done. The measured delta collapses toward zero, and the conclusion "my `AGENTS.md` makes no difference" is reached for a reason that has nothing to do with `AGENTS.md`.

The inverse is the same coin: **scaffolding matters most on tasks the model has never seen**, because that is when the agent has to navigate, search, and recover from its own errors. So the effect under study is *largest* precisely where SWE-rebench operates.

### What SWE-rebench gives that the others do not

- **Continuously mined, decontaminated tasks.** An automated pipeline pulls *fresh* GitHub issues; 21,000+ issue–PR pairs from 3,400+ Python repos. The others are static snapshots that rot with every model release.
- **A free control group.** Their leaderboard is produced under a **fixed scaffolding** — a minimal ReAct agent, identical prompts, default hyperparameters, 128K context — run **five times per model**, reporting **SEM and pass@5**. The "no scaffolding" baseline this repo needs has therefore *already been measured by someone else, with error bars*.
- **Agent-agnostic scoring — verified.** The harness takes a `predictions.jsonl` of `{instance_id, model_name_or_path, model_patch}` and evaluates the diff in Docker. Anything that emits a patch can be scored: Claude Code, Codex, OpenCode, `pi`, mini-swe-agent, a custom multi-agent orchestrator. **This is the property the entire experiment matrix depends on**, and it is why the check for it was done before committing to the benchmark.
- **7,500 pre-built Docker images** on Docker Hub — no environment construction.

### Rejected, and why

- **LiveCodeBench, Aider Polyglot** — *no agent*. LeetCode-shaped, one-shot, no repo, no tools, no terminal. There is nowhere to attach a skill, a scaffold or an orchestrator: **no surface for the independent variable**. They measure the bare model, which is the one axis this repo does not care about. (LiveCodeBench was initially recommended for being cheap to run. Cheap is worthless when it measures the wrong thing.)
- **Akita's `llm-coding-benchmark`** — a good reference and a good read, but **greenfield-only** (one fixed Rails brief, 18 models) and **one-shot prompting**, which is not the workflow this repo targets. Its real lesson is kept, though, and it is a big one: *"benchmark metrics lie about runtime correctness."* The scoring here is **hybrid** — automated artifact checks plus a hand-written 0–100 rubric across 8 dimensions, with a human reading the generated code. It caught models hallucinating the `RubyLLM` API, which no automated check would have flagged.
- **SWE-PolyBench** (Amazon) — Java/JS/TS/Python, 2110 instances, 21 repos. **Static, therefore contaminating.** But **its metrics are stolen wholesale** — see §4.
- **Multi-SWE-bench** — the widest language coverage (Java, TS, JS, **Go**, Rust, C, C++; 1632 instances). **This is the plan B**, and the one to switch to if the Python-only constraint ever becomes the binding one. It loses on the two axes that decide *this* experiment: contamination and metric resolution.
- **Terminal-Bench 2.0 / Harbor** — a strong fit structurally (Harbor's whole design is a pluggable agent abstraction over containerised tasks) and worth revisiting for the *terminal/infra* flavour of the question. Not chosen now because it does not give the decontamination or the published fixed-scaffold baseline.

### The price, stated plainly

**SWE-rebench is Python-only.** The first instinct was **Go**, to learn it. That was set aside on one principle: **the benchmark is the instrument, not the curriculum.** Go can be learned anywhere; a contaminated benchmark cannot be decontaminated. Python also happens to be the language most easily read here, which helps when the job is to open a failed trajectory and understand *why* it failed — but that was a consequence of the choice, not a reason for it.

---

## 4. The instrument — assembled from the best part of each

| Piece | Taken from | What it is |
|---|---|---|
| **Dataset** | SWE-rebench | `nebius/SWE-rebench-leaderboard`. Fresh, decontaminated, Python. |
| **Scorer** | SWE-rebench's SWE-bench fork | `run_evaluation --predictions_path predictions.jsonl`. Docker, pre-built images, patch in / verdict out. |
| **Protocol** | SWE-rebench | Fixed scaffold, identical prompts, **5 runs per configuration**, report **SEM + pass@5**. Their published ReAct line is the control group. |
| **Metrics** | SWE-PolyBench | **File-retrieval** and **node-retrieval** recall/precision, computed by us from *predicted patch vs gold patch*. Plus their complexity classes. |
| **Task selection** | "Efficient Benchmarking of AI Agents" | The **mid-range filter**: keep only tasks with a historical pass rate of ~30–70%. Cuts 44–70% of runs at near-identical ranking fidelity. |
| **Sandbox discipline** | The neuralnoise WIP's failure | See §6. The sandbox is part of the instrument. |

**Why the PolyBench metrics matter more than they look.** The hypothesis — "the scaffolding helps" — predicts an improvement in **navigation before it predicts one in resolution**. If `AGENTS.md` works, the first thing it changes is that the agent *finds the right file sooner*. File-retrieval recall is a **graded** signal; pass/fail is **one bit**. Measuring only resolve rate means looking where the signal is weakest. And these metrics are **portable** — they are computed from two diffs, so they need no cooperation from the benchmark that invented them.

---

## 5. Prior art: the neuralnoise WIP, and the two holes that are our contribution

[*Benchmarking Local LLMs Against Coding Agent Harnesses*](https://www.neuralnoise.com/2026/harness-bench-wip/) is the closest existing work, and it compares almost exactly the harnesses on this repo's list: **Aider, Claude Code, OpenCode, Pi, Qwen CLI** — 17 model quantizations × 5 harnesses × 16 tasks = 1,360 runs, on a single M3 Max via `llama.cpp`. Findings: Pi leads at 76.9%; Q4 is not meaningfully degraded vs Q8.

It has two holes, and they are the reason this repo has something to say:

1. **Every cell ran exactly once.** No repeats, therefore **no noise floor** — the author says as much, that the findings *"probably deserve a careful re-run before I'd trust the rankings to two decimal places."* A ranking published without knowing its own variance.
2. **One harness cheated.** OpenCode **read or executed the hidden test files in 14 instances**, inflating its score. That study measured cheating and reported it as capability.

And it tests **none** of this repo's variables — no skills, no scaffold, no orchestration — and it is local-models-only on hardware not available here.

---

## 6. The three traps, all of which will bite if ignored

### Trap 1 — variance. Agentic runs are noisy.

Same model, same task, same prompt, different outcome: the agent loops or it doesn't; it finds the file on the 2nd try or the 10th. **SWE-rebench runs every model 5× and publishes SEM for this exact reason.**

This is fatal for the questions here, because they are all about **small deltas**. "With skills vs without" might be 5 percentage points. **If the run-to-run noise is 15 points, the experiment measures noise and calls it a result** — and it will be believed, because it arrives as a number.

**Hence the first experiment is the noise floor, before anything else** (§7).

### Trap 2 — statistical power. Repetition is not how you get it.

Pass/fail on one task across 5 runs is **five coin flips**. The confidence interval swallows any effect worth finding. Repetition tells you the *noise*; it does not buy *signal*.

**The signal comes from pairing:** run **20–30 instances once each, per configuration**, and compare configurations **on the same instances** (a paired / McNemar-style comparison). That is where the cheap statistical power is. Repeats exist only to establish how many of them each cell needs — not to be the design.

### Trap 3 — the sandbox is part of the instrument.

SWE-bench's structure already protects against the neuralnoise failure: the `test_patch` is applied by the *scorer*, not present in the agent's workspace. **But two leaks remain open by default, and neither leaves an obvious trace in the diff:**

- **The git history.** The container holds a real public repo. `git log --all`, a future ref, a `git show` — and the agent can simply *read the commit that fixes the issue*.
- **The network.** With `bash` and an outbound route, the agent can search for the issue and find the original PR.

An agent that "resolves" a task this way is not well-scaffolded, it is **cheating** — and it would show up as a scaffolding win. **Close both before run 1:** no network in the agent container; prune remotes and future refs from the checkout.

---

## 7. The first experiment — the noise floor

Deliberately not about skills, not about agents. Its only job is to produce **one number** that decides whether the rest of the matrix is viable at all.

1. Clone the SWE-bench fork, install, verify Docker.
2. **Prove the scorer before any agent exists**: run `--predictions_path gold` on one instance. The gold patch must resolve. If it does not, nothing downstream means anything.
3. Pick **one mid-range instance**.
4. Run **one agent** (`claude -p`), **neutral scaffold**, **10 times** (not 5 — 5 is too few even to *estimate* noise), with the sandbox of §6 closed.
5. Record per run: **resolved (bool) · turns · tokens · wall time · files touched · did it run the tests · file/node-retrieval recall**.
6. Read the **dispersion**. That number sizes every experiment that follows.

**Also the payoff for objective (1):** step 4 produces ten trajectories of the *same* task, to be read side by side — the agent solving it five different ways, and the scorer deciding.

---

## 8. Setup — what actually happened, verified 2026-07-14

**The scorer is proven.** Gold patch on `pgmpy__pgmpy-3137` (split `2026_03`) → `Instances resolved: 1`, ~5 minutes, using a pre-built image. The harness is installed at `~/repositories/_cloned/SWE-bench-fork` (`swebench 4.0.3`, venv via `uv`).

```bash
HF_TOKEN=... .venv/bin/python -m swebench.harness.run_evaluation \
  --dataset_name nebius/SWE-rebench-leaderboard --split 2026_03 \
  --predictions_path gold --instance_ids pgmpy__pgmpy-3137 \
  --cache_level instance --run_id validate-gold --namespace swerebench
```

Four things the setup taught, none of which are in anyone's README:

- **An `HF_TOKEN` is mandatory** — and the failure is deeply misleading. `nebius/SWE-rebench-leaderboard`'s large files sit in HuggingFace's **Xet** storage, which **401s for anonymous requests on this repo specifically** (`princeton-nlp/SWE-bench_Verified` and `nebius/SWE-rebench` both download fine without one). It is not a network, machine, or library problem, and it presents as one. Any free read-scoped token fixes it.
- **The fresh tasks exist ONLY in the leaderboard dataset, and this nearly ruined the experiment.** The public `nebius/SWE-rebench` (21,336 instances) **stops at 2025 — zero 2026 tasks.** The post-cutoff splits (`2026_01`: 48 · `2026_02`: 57 · `2026_03`: 110) live exclusively in `nebius/SWE-rebench-leaderboard` — the one that was 401ing. **Decontamination, the sole reason this benchmark was chosen, sits entirely behind that token.** Without checking the date distribution we would have run on 2024 tasks while believing the benchmark was fresh, and the scaffolding effect would have been silently compressed by memorisation. **Always assert the `created_at` range of the split you are about to run.** Opus 4.8's cutoff is 2026-01, so `2026_02` and `2026_03` are the safe splits today; this shifts with every model release.
- **Difficulty metadata exists, but not where it is needed, and it is not what the paper asks for.** `nebius/SWE-rebench` carries `meta.llm_score.difficulty_score` (plus `issue_text_score`, `test_score`, `is_lite`, `num_modified_files`). The **leaderboard splits do not carry it**. And it is an **LLM's opinion of difficulty**, not an **empirical pass rate across models** — which is what the mid-range (30–70%) filter actually requires. The two are not interchangeable. The empirical rates must come from the published swe-rebench.com per-model results, or be estimated ourselves with a cheap model.
- **Useful fields we get for free:** `docker_image` (which pre-built image to pull), `created_at` (date-based decontamination), and `interface` / `harbor_cpus` / `harbor_memory` / `harbor_verifier_timeout_sec` — **they already support Harbor**, which is the natural way to plug the different agent harnesses in later.

**Disk:** each instance caches its own image (~1–2 GB). Fine for now (253 GB free), but a 30-instance paired run needs planning, and `--cache_level` is the knob.

---

## 9. Decontamination in practice — use the release date, not the cutoff

Choosing a post-cutoff split requires knowing each model's cutoff. **Half of them do not publish one** — and it is precisely the open-weight vendors this repo cares about that stay silent. Worse, asking the model is useless: the standard reference on this opens by saying *"never trust a model's self-reported cutoff"*, because models hallucinate their own boundary.

**So do not depend on the cutoff. Depend on the bound.**

> **A model's release date is a hard ceiling on its training cutoff.** Nothing can be trained on data that did not exist when it shipped.

Release dates are public, dated, and not self-reported. The rule, in order:

1. **An official cutoff exists** → use it.
2. **It does not** → use the release date as the ceiling. Conservative, and always true.

### The table (researched 2026-07-14)

| Model | Cutoff | Confidence |
|---|---|---|
| GPT-5.5 | **2025-12-01** | Official |
| Claude Opus 4.8 | **2026-01** | Official |
| Gemini 3.5 Flash | **2025-01** | Official (despite a 2026-05 release) |
| MiniMax M3 | **2026-01** | Official (HF chat template) |
| Kimi K2.6 | **2025-04** | Vendor, via reviews |
| Gemini 3.1 Pro | 2025-01 *(inherited from Gemini 3 Pro)* | **Card does not state it**; a third party claims 2026-02. **Unresolved — do not use until settled.** |
| DeepSeek V4 Pro / Flash | **2026-04** *(third party only)* | Official docs are silent. Released **2026-04-24**. |
| Kimi K2.7-Code · GLM-5.1 · GLM-5.2 · MiniMax M2.7 · Gemma 4 | — | **Unpublished.** Use the release-date ceiling. |
| MiniMax M2.5 | 2025-01 *(?)* | Secondary and **incoherent** — the same source dates M2 at 2025-09, which is *later*. Discard. |

### Applied to the splits

**Run on `2026_03`** — newest, and the largest (110 instances, vs 48 and 57).

- **Clean:** GPT-5.5 · Opus 4.8 · Gemini 3.5 Flash · MiniMax M3 · Kimi K2.6, plus anything whose *release* predates 2026-03.
- **Structurally suspect:** **DeepSeek V4** (released 2026-04-24; the one cutoff claim that exists says 2026-04, which would contaminate **all three** 2026 splits) and **Gemma 4** (released 2026-04-02). Both shipped *after* the March 2026 PRs and could have seen them.
- **Worth doing on purpose:** run the suspect models anyway, as a **contamination control group**. If they score suspiciously well on `2026_03` relative to their standing elsewhere, that is a finding in itself — and it validates the whole decontamination premise empirically rather than by appeal to a vendor's word.

---

## 10. Result — the noise floor, measured (2026-07-14)

**pi + Kimi K2.7-Code, `pgmpy__pgmpy-3137` (split `2026_03`), 10 runs, neutral scaffold** (`--no-skills --no-context-files`), sandboxed with no route to the internet.

| metric | result |
|---|---|
| **resolve rate** | **8/8** of the completed runs |
| **turns** | 30 → 106 · median 59 · **sd 28 · 3.5x** |
| **patch lines** | 120 → 153 · 1.3x |
| **file-retrieval recall** | **1.0 on every run. sd = 0.** |
| **node-retrieval recall** | **1.0 on every run. sd = 0.** *(first reported as `0.0` — the metric was broken; see §10b)* |
| retrieval precision (file / node) | **0.5 / 0.5 on every run** — the agent fixes a second, duplicated implementation the gold patch ignores. **Not a quality signal — see §10b.** |
| timed out on upstream backoff | 2 of 10 |

### The finding, and it inverts the plan

**The noise floor of the *verdict* is zero. The noise floor of the *process* is 3.5x.**

The agent solved the task every single time, found the right file every single time, and wrote a patch of near-identical size every time — while spending anywhere from 30 to 106 turns getting there. It always arrives; the route is chaotic.

Three consequences, and they are load-bearing for everything downstream:

- **Resolve rate is useless on this task — it is at ceiling.** You cannot measure a scaffold's effect on a metric that is already saturated. This is the mid-range filter (30–70% historical pass rate) from *Efficient Benchmarking of AI Agents*, rediscovered the hard way. **Task selection is therefore not a cost optimisation — it is a precondition for the experiment meaning anything.** A task the model always wins (or always loses) carries zero information about the scaffold.
- **The retrieval metrics were wrong too, and they were my strongest argument.** §4 claimed they would be "the sharpest instrument", because a scaffold should improve navigation before it improves resolution. Both came back **1.0 with zero variance** — also at ceiling. A graded metric is worth nothing if the agent is already perfect on it. (Node retrieval initially *appeared* to be at the floor instead; that was a bug in the metric, corrected in §10b. The corrected value is 1.0, so this conclusion holds — but it was reached before the evidence for it existed.)
- **Turns is the only metric with headroom, and it is expensive.** With sd=28 on a mean of 63 (**44% relative sd**), the sample sizes are brutal: **~14 runs per arm** to detect a 30-turn (~47%) difference, **~31 per arm** for 20 turns, **~125 per arm** for 10 turns. A scaffold effect plausibly lives in the 10–20 turn range. **One run per cell would have measured nothing** — which is precisely the question this experiment existed to answer, and now it has a number instead of an intuition.

**So the design holds and is now quantified:** do not fight the variance with repetition. **Pair across instances** — ~25 mid-range tasks, once each per configuration, compared on the same instances. That removes per-instance variance as a nuisance factor instead of trying to average it away.

### Two operational facts

- **`wall_time_s` is not a clean signal and must not be reported as one.** It includes time spent waiting on upstream rate limits. Two of ten runs sat in client-side backoff for ~26 minutes and died at the 40-minute timeout without finishing. The queue is being measured alongside the agent. Turns, tool calls, patch size and the verdict are the signals that survive.
- **A ~20% upstream-timeout rate is a property of this bench, not of the model**, and it is recorded separately (`"timeout": true`) so it can never be confused with "the model failed".

### The elephant

**8/8, with perfect file recall, on a task created 2026-03-22 — by a model released 2026-06-12 that publishes no cutoff.** That is what memorisation looks like. It is not proof. But it turns the **Kimi K2.6 control** (cutoff 2025-04, published) from a methodological nicety into the central question: if K2.6 also cruises to 8/8, the task is simply easy. If it struggles, K2.7 has seen the answer.

---

## 10b. The node-retrieval metric was broken. Fixed, it says 1.0 — and §10 survives (2026-07-14)

**`node_recall` came back `0.0` on all ten runs — including the eight that resolved the task.** That was not a metric at its floor: it was a metric that **could not return anything else**. It has been rewritten to read the AST, and the true value is **`1.0` on every completed run, sd 0**.

The correction changes the *evidence* under §10 without changing its *conclusion*. That is worth saying plainly, because the hypothesis that motivated the fix — "the broken metric is hiding headroom" — **was wrong**.

### Why it was structurally zero

The old scorer defined a "node" as **the label git prints in the hunk header**:

```python
NODE_RE = re.compile(r"^@@ .* @@\s*(?:def|class)\s+(\w+)", re.M)   # removed
```

That label is a **rendering artifact of the diff**, not a property of the code. Git picks it with the `xfuncname` heuristic **of whatever diff driver is configured** — and the two sides of the comparison were produced by different ones:

| | hunks at | git labelled them |
|---|---|---|
| **gold** (from the dataset's pipeline, Python driver: matches indented `def`) | lines 353, 421 | `def _build_skeleton`, `def _get_potential_sepsets` |
| **predicted** (the agent's `git diff`, default driver: only matches column 0) | lines **353, 421** | `class _ConstraintMixin` |

**Same file. Same lines. Different labels.** The sets are disjoint by construction, so the intersection is empty and `node_recall` is `0.0` *regardless of what the agent actually did*. The regex was never the bug — the **definition** was.

### The fix, and what it measures

`evals/nodes.py` does what SWE-PolyBench does: parse the file **at `base_commit`** and map every line a patch touches to the innermost enclosing `def`/`class`, qualified (`Class.method`). The base files are lifted out of **the prebuilt eval image** — the exact tree the agent worked on, local, and incapable of drifting from what was run.

Proven to discriminate before being trusted: gold vs. itself → `1.0/1.0`; a patch touching only the *other* file → `0.0`; an empty patch and a module-level edit → no nodes. It is not a `1.0`-machine.

### The result: the ceiling was real

| metric | old (hunk label) | **now (AST)** |
|---|---|---|
| `node_recall` | `0.0` — artifact | **`1.0` · sd 0.000** |
| `node_prec` | not reported | **`0.5` · sd 0.000** |

The gold patch touches exactly two nodes — `_ConstraintMixin._build_skeleton` and `_ConstraintMixin._get_potential_sepsets`. **The agent hits both, on all eight completed runs, without exception.**

So node retrieval is **at ceiling, exactly like file retrieval and resolve rate**. §4 had called it the *sharpest instrument*; on this task it is as blunt as the rest. **§10's conclusion — turns is the only metric with headroom — stands, and the sample-size maths (~14 to ~125 runs per arm) is unchanged.** It was right for a reason it had not actually established; now it has.

### The precision of 0.5 is not sloppiness — and it is a trap

`file_prec` and `node_prec` sit at 0.5 because the agent always repairs a **second** location the gold patch ignores: `pgmpy/estimators/BaseConstraintEstimator.py`. That file is **not a deprecated shim** — it is a genuine parallel implementation of the same logic (its own `build_skeleton`, with joblib parallelism). The repo carries **two copies of the bug**; the agent fixes both; the human fixed one.

**So retrieval precision penalises the agent for being more thorough than the reference — while it still passes the tests 8/8.** The lesson generalises past this instance and must not be forgotten when the matrix starts producing cells:

> **Precision against a single gold patch measures conformity to one human's fix, not correctness.** In any repo with duplicated logic it is noise. **Recall is the signal.**

### It cost nothing, and that is the point

No inference, no API, no proxy: the ten patches were on disk, the gold came from the dataset, the base files came from a local image, and the verdicts were already scored. **The whole correction was a re-read of data already collected** — which is the argument for keeping raw trajectories around at all.

---

## 11. Still open, and honest

- **The "6x from the harness" claim is unverified** (§2). It is the premise of the whole repo.
- **Empirical per-task pass rates** are still missing — see §8. Needed for the mid-range filter.
- **Cost is expected to be ~zero, still to be confirmed.** The plan drives the CLI agents already paid for by subscription (`claude -p`, `opencode run`, `codex exec`) rather than calling an API in a loop; Docker and the scorer are local. The `litellm` proxy on the desktop (`:4000`) is up but needs a key — relevant only if raw-model runs are ever wanted.
- **The sandbox leaks of §6 are NOT yet closed.** The gold run did not involve an agent, so nothing has been at risk yet. They must be closed before the first agent run, not after.
