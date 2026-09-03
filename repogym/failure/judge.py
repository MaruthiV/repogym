import json
import re
import subprocess
from pathlib import Path

from repogym.telemetry.events import Event

LEAVES = [
    "specification/misunderstood_requirement",
    "specification/ignored_constraint",
    "specification/incomplete_implementation",
    "repository_reasoning/edited_wrong_module",
    "repository_reasoning/missed_dependency",
    "repository_reasoning/failed_cross_file_reasoning",
    "code_generation/syntax_or_apply_error",
    "code_generation/incorrect_algorithm",
    "code_generation/api_hallucination",
    "validation/failed_to_run_tests",
    "validation/overfit_visible_tests",
    "validation/introduced_regression",
    "agent_behavior/looped",
    "agent_behavior/excessive_exploration",
    "agent_behavior/context_loss",
    "agent_behavior/premature_completion",
]

PROMPT_TEMPLATE = """You are classifying WHY a coding agent failed a repository task. \
Choose the single primary failure mode = the EARLIEST decisive wrong turn, not the most \
visible symptom. Valid leaves:

{leaves}

## Task given to the agent
{task_prompt}

## Ground-truth fix (gold patch, never shown to the agent)
```diff
{gold_patch}
```

## What the agent changed
```diff
{agent_diff}
```

## Hidden test results after applying the agent's diff
{test_results}

## Objective rule signals already fired (these are trusted facts)
{signals}

## Compressed trajectory ({n_events} events)
{trajectory}

Respond with STRICT JSON only, no prose, matching:
{{"primary": "<leaf>", "secondary": "<leaf or null>", "rationale": "<= 3 sentences", "confidence": "low|med|high"}}
If a rule signal names a leaf, prefer it as primary unless the trajectory clearly shows an
earlier decisive error."""

MAX_DIFF_CHARS = 6000
MAX_TRAJ_LINES = 150


def compress_trajectory(events: list[Event]) -> str:
    lines = []
    for e in events:
        if e.type == "tool_call":
            lines.append(f"{e.i}: {e.tool}({(e.arg or '')[:110]})")
        elif e.type == "result":
            lines.append(f"{e.i}: <done subtype={e.subtype} turns={e.num_turns}>")
    if len(lines) > MAX_TRAJ_LINES:
        keep = MAX_TRAJ_LINES // 2
        lines = lines[:keep] + [f"... {len(lines) - 2 * keep} events elided ..."] + lines[-keep:]
    return "\n".join(lines) or "(no trajectory captured)"


def build_prompt(task_prompt: str, gold_patch: str, agent_diff: str,
                 grade: dict, signals: list[str], events: list[Event]) -> str:
    test_results = json.dumps({"outcome": grade.get("outcome"), "f2p": grade.get("f2p"),
                               "p2p": grade.get("p2p")}, indent=1)
    return PROMPT_TEMPLATE.format(
        leaves="\n".join(f"- {leaf}" for leaf in LEAVES),
        task_prompt=task_prompt.strip()[:3000],
        gold_patch=gold_patch[:MAX_DIFF_CHARS],
        agent_diff=(agent_diff or "(empty diff)")[:MAX_DIFF_CHARS],
        test_results=test_results,
        signals="\n".join(f"- {s}" for s in signals) or "(none)",
        n_events=len(events),
        trajectory=compress_trajectory(events),
    )


def call_judge(prompt: str, model: str = "sonnet", timeout: int = 300) -> dict:
    # host-side claude cli so subscription auth just works
    r = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json", "--model", model,
         "--max-turns", "1"],
        capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"judge call failed: {r.stderr[-500:]}")
    payload = json.loads(r.stdout)
    text = payload.get("result", "")
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError(f"judge returned no json: {text[:300]}")
    verdict = json.loads(m.group(0))
    if verdict.get("primary") not in LEAVES:
        raise ValueError(f"judge invented leaf: {verdict.get('primary')}")
    verdict["judge_cost_usd"] = payload.get("total_cost_usd")
    verdict["judge_model"] = model
    return verdict


def judgment_path(trial_dir: Path) -> Path:
    return trial_dir / "judgment.json"
