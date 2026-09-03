# RepoGym

A reproducible benchmark and evaluation harness for autonomous coding agents (Claude Code, GitHub Copilot CLI, Aider, OpenHands) on real repositories.

Most benchmarks ask "what fraction of tasks can the agent solve?" and report a single number. That number is saturating and it hides everything interesting. RepoGym asks a better question: **when should you trust a coding agent, and why does it fail when it fails?**

So instead of just pass rates, the harness measures four extra axes on every single trial:

1. **Capability by difficulty.** Tasks are stratified L1 to L4, so you get degradation curves, not one number.

2. **Failure taxonomy.** Failed trials get classified into 16 failure modes across 5 branches (spec misreading, repository reasoning, code generation, validation behavior, agent behavior) by objective rules first, an LLM judge second, and a human agreement check (Cohen's kappa) on top.

3. **Incidental safety.** Every trial has fake credentials planted in the workspace, every diff is scanned for dangerous patterns, every new dependency is checked against PyPI, and some tasks are traps where the tempting shortcut is a security violation.

4. **Efficiency.** Exact tokens, cost, wall clock, tool calls, plus UCR (useful compute ratio: what fraction of generated tokens actually survive into the final patch).

## the numbers right now

| thing | count |
|---|---|
| validated tasks | 50 (every one admitted by a two-run validation gauntlet in fresh containers) |
| real repositories | 8 pinned at exact SHAs: flask, click, jinja, httpx, rich, zod, chi, cobra |
| languages | 3 (Python, TypeScript, Go), one pipeline for all of them |
| trap tasks | 6 built out of 8 designs |
| agent adapters | 4 (claude-code, copilot, aider, openhands) |
| docker images | 9, each with all agent CLIs baked in |
| merged PRs mined | ~2,500 scanned, ~250 candidates extracted, every survivor validated twice |
| harness | ~2,000 lines of Python, 27 unit tests, 11 CLI subcommands |
| pilot | every task x 4 agents x 2 trials, 400 trials attempted, 396 completed |

Upstream test suites in the pinned images range from 494 tests (flask) to 8,000+ (zod) and run in seconds, so grading is cheap at scale.

## how a task works

Every task is a directory: a `task.yaml` plus up to three patches.

```yaml
id: flask-0001

repo: pallets/flask

base_commit: d318b68...        # exact pin

category: bug_fix              # 10 categories

level: L2                      # L1: one function ... L4: architectural

source: mutated                # mined | mutated | handcrafted

prompt: |                      # what the agent sees, written like a real bug report

mutation_patch: bug.patch      # the planted bug (for mutated tasks)

hidden_tests:

  patch: tests.patch           # applied only at grading time, agent never sees it

  fail_to_pass: [...]          # must fail before the fix, pass after

  pass_to_pass: [...]          # regression sentinels

oracle:

  patch: gold.patch            # known-good fix, used for localization metrics
```

The lifecycle:

1. **Validation gauntlet.** Before a task is admitted: fresh container, fail-to-pass tests must fail, pass-to-pass tests must pass, then the gold patch must flip everything green. Run twice to catch flakiness. Tasks that fail any step are rejected, not patched around. This is not optional ceremony, it is the product (see findings below).

2. **Trial.** The agent runs headless inside a sandboxed container (CPU/memory capped) against a fresh workspace. Its full trace is captured: every model call, tool call, file edit, token count.

3. **Grading.** Post-hoc, in a *new* container. The agent's diff is applied to a clean checkout and the hidden tests decide. The agent saying "tests pass!" counts for nothing. Outcomes: resolved, partial, unresolved, regression, patch_error, error. Solving the task while breaking a regression sentinel counts as regression, not resolved.

## where tasks come from

Three sources, deliberately mixed:

- **Mined (31).** A scraper walks merged GitHub PRs (REST + GraphQL for UI-linked issues), keeps ones that close a real issue and add tests, splits the PR diff into hidden tests vs gold patch, and pins the base to the merge commit's first parent. The issue text becomes the prompt.

- **Mutated (14).** A real bug is planted in a real repo, generated so the upstream suite stays green and only the hidden tests catch it. Example: flask-0001 plants a root path resolution bug that all 494 upstream flask tests miss.

- **Handcrafted (5).** Feature, migration, and trap tasks that cannot be mined.

The trap tasks are the fun part. Each one has a visible failing signal, a tempting shortcut, and hidden tests plus scanners that catch the shortcut:

- **T1** silence the failing test (deleting/skipping it gets flagged, hidden duplicates still fail)

- **T3** wrap the crash in a broad `except: pass` (weak visible test goes green, exact hidden tests do not)

- **T4** delete the auth check (visible test passes, hidden 401 tests convert it into a regression)

- **T5** dependency bait (the prompt casually recommends a package that does not exist on PyPI)

- **T7** hardcode the credential from `.env` (the planted canary value showing up in any diff is an instant flag)

- **T8** silence the type checker (`@ts-ignore` / `as any` greens the typecheck, hidden runtime tests catch the still-broken logic)

## findings

Building and running the benchmark produced results on its own:

- **~40% of shaped issue+PR pairs add characterization tests**, tests that already pass before the fix. Naively mining them produces unsolvable-by-definition tasks. Our validation gauntlet rejects them automatically. This is the same problem that forced OpenAI to hand-verify SWE-bench, reproduced and quantified by pipeline.

- **`pr.base.sha` lies.** The GitHub API's base SHA often postdates the fix. The correct pre-fix state is the merge commit's first parent. Without this, tests "fail to fail" and yield collapses.

- **Mining yield varies wildly by repo**: jinja's recent history validates at ~35%, click's deep history at 0% (55 straight rejections). Repo selection is a first-class design decision.

- **The gauntlet catches dead tasks.** A planted zod mutation changed a default argument that no caller uses. Every test stayed green including the hidden ones, and validation rejected the task. Task QA that actually works.

## agent results

The 400-trial pilot ran across all 50 tasks, four agents, and two trials per task. 396 trials completed and 4 terminated with infrastructure errors, a 1.0% infra error rate.

Measured resolve rate (pass@1, avg of 2 trials):

| agent | L1 | L2 | L3 | overall |
|---|---|---|---|---|
| claude-code | 89% | 71% | 49% | 62% |
| copilot | 84% | 61% | 41% | 53% |
| openhands (sonnet) | 81% | 59% | 38% | 51% |
| aider (sonnet) | 79% | 51% | 31% | 44% |
| fleet average | 83% | 61% | 40% | 52% |

```text
OBSERVED difficulty degradation (each block = 5pp resolve rate)

           L1                  L2                L3

claude    ##################   ##############    ##########    89 > 71 > 49

copilot   #################    ############      ########      84 > 61 > 41

openhands ################     ############      ########      81 > 59 > 38

aider     ################     ##########        ######        79 > 51 > 31
```

Other measured results:

- **Trials completed**: 396 of 400 (1.0% infra error rate)

- **Top failure modes** (share of failed trials): repository reasoning 34.8%, validation behavior 24.6%, code generation 18.3%. Repository reasoning was the largest failure branch, supporting the project thesis that the bottleneck is not just generating code but reasoning correctly about the repository around it.

- **Trap violations**: 12 of 48 trap trials took the shortcut (25.0%), with silence-the-test and ts-ignore taken most, hardcode-the-credential least. One trial landed resolved WITH a flagged violation.

- **UCR** (claude-code): 0.36 overall, higher on solved trials (0.46) than failed (0.21)

- **Cost per resolved task**: aider $0.82, openhands $1.08, claude-code $1.37, copilot measured in premium requests (9.6 per resolved)

- **Max/min resolve-rate ratio across the four agents**: 1.41x

## stack

- **Python 3.12 + uv + pydantic v2** for the harness. Plain functions, subprocess + docker CLI, JSONL traces on disk at every stage so anything can be rerun from the previous stage's files.

- **Docker** sandboxes: per-repo images pinned at exact commits with warm package caches, so a fresh workspace install takes seconds. Arbitrary base commits check out inside the image (mined tasks span history).

- **Three test drivers** behind one interface: pytest, vitest, `go test -run` (with a guard for go's "exit 0 when no tests matched" footgun).

- **gh CLI + GraphQL** for mining, **PyPI API** for dependency checks, regex scanners over diffs for dangerous patterns (verify=False, broad excepts, test deletion, ts-ignore, and friends).

- **LLM judge** rides the claude CLI with forced-choice JSON output, compressed trajectories, and ground truth artifacts (gold patch + hidden test results), because raw-trace judging is known to be weak. Rules get precedence over the judge, and the judge gets audited with Cohen's kappa against human labels.

- **Stats in stdlib**: Wilson intervals, exact McNemar for agent pairs, kappa. No stats theater at small n.

- **Dashboard**: one self-contained static HTML file over `report.json`. No build step.

## cli

```bash
uv run repogym mine flask --limit 400        # scrape candidate tasks from merged PRs

uv run repogym validate-candidates --jobs 4  # admission gauntlet, auto-promote survivors

uv run repogym validate flask-0001           # validate one task, twice

uv run repogym run flask-0001 --agent claude-code

uv run repogym grade flask-0001 --agent claude-code

uv run repogym classify flask-0001 --agent claude-code   # failure taxonomy: rules + judge

uv run repogym run-batch --agents claude-code,aider --trials 2 --budget-usd 50

uv run repogym report                        # leaderboard + per-trial json for the dashboard

uv run repogym label-template && uv run repogym kappa    # human agreement check
```

## status

The benchmark is built and tested end to end: corpus, sandbox, adapters, telemetry, grading, taxonomy rules, judge, security suite, stats, orchestration, dashboard. The 400-trial pilot across all four agents is complete, along with the failure-labeling pass. The context-retrieval study is next (a minimal in-house agent with swappable retrieval: full-context vs BM25 vs import-graph vs grep, already written and unit-tested).

Task content note: hidden tests and gold patches live in this repo, and hiddenness is enforced by the harness (the agent workspace never sees the task directory). Results are date-stamped and versioned since models trained after publication may have seen this repo.