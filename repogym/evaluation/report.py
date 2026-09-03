import json
from pathlib import Path

from repogym.images import REPO_ROOT
from repogym.telemetry.metrics import trial_metrics
from repogym.telemetry.normalize import normalize_claude_trace

SOLVED = "resolved"


def collect_trials() -> list[dict]:
    rows = []
    trials_root = REPO_ROOT / "results" / "trials"
    if not trials_root.exists():
        return rows
    for grade_file in sorted(trials_root.glob("*/*/t*/grade.json")):
        tdir = grade_file.parent
        row = json.loads(grade_file.read_text())
        cfg = tdir / "config.json"
        if cfg.exists():
            row |= json.loads(cfg.read_text())
        trace = tdir / "trace.jsonl"
        if trace.exists() and row.get("agent") == "claude-code":
            row["telemetry"] = trial_metrics(normalize_claude_trace(trace))
        row["trial_dir"] = str(tdir.relative_to(REPO_ROOT))
        rows.append(row)
    return rows


def leaderboard(rows: list[dict]) -> dict[str, dict]:
    agents: dict[str, dict] = {}
    for row in rows:
        a = agents.setdefault(row.get("agent", "?"), {
            "trials": 0, "resolved": 0, "regressions": 0, "cost_usd": 0.0,
            "tokens_out": 0, "wall_s": 0.0,
        })
        a["trials"] += 1
        a["resolved"] += row.get("outcome") == SOLVED
        a["regressions"] += row.get("outcome") == "regression"
        tele = row.get("telemetry") or {}
        a["cost_usd"] += tele.get("cost_usd") or 0.0
        a["tokens_out"] += tele.get("tokens_out") or 0
        a["wall_s"] += row.get("agent_wall_s") or 0.0

    for a in agents.values():
        n = a["trials"] or 1
        a["solve_rate"] = round(a["resolved"] / n, 3)
        a["regression_rate"] = round(a["regressions"] / n, 3)
        a["cost_per_task"] = round(a["cost_usd"] / n, 3)
    return agents


def write_report() -> Path:
    rows = collect_trials()
    out = {"trials": rows, "leaderboard": leaderboard(rows)}
    path = REPO_ROOT / "results" / "report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2))
    # dashboard reads a sibling copy so it can be served statically
    (REPO_ROOT / "dashboard" / "report.json").write_text(json.dumps(out, indent=2))
    return path
