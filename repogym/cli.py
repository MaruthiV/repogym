import argparse
import json
import os
import sys

from repogym.adapters import ADAPTERS
from repogym.evaluation.grade import grade
from repogym.evaluation.validate import validate
from repogym.harness.runner import run_trial, trial_dir
from repogym.images import REPO_ROOT, build_image, image_tag, load_registry
from repogym.schema import TaskSpec


def load_task(task_id: str) -> TaskSpec:
    return TaskSpec.load(REPO_ROOT / "tasks" / task_id)


def entry_for(task: TaskSpec):
    entry = load_registry()[task.runtime.repo_key]
    expected = image_tag(task.runtime.repo_key, entry)
    assert task.runtime.image == expected, \
        f"task image {task.runtime.image} != registry {expected}; re-pin the task"
    return entry


def cmd_build_image(args) -> int:
    tag = build_image(args.repo)
    print(f"built {tag}")
    return 0


def cmd_validate(args) -> int:
    task = load_task(args.task)
    problems = validate(task, entry_for(task), times=args.times)
    if problems:
        print(f"REJECTED {task.id}:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"VALID {task.id} ({args.times} runs)")
    return 0


def cmd_run(args) -> int:
    task = load_task(args.task)
    adapter = ADAPTERS[args.agent]
    tdir = run_trial(task, entry_for(task), adapter, args.trial, model=args.model)
    print(f"trial complete: {tdir}")
    print((tdir / "config.json").read_text())
    return 0


def cmd_grade(args) -> int:
    task = load_task(args.task)
    tdir = trial_dir(task.id, args.agent, args.trial)
    diff = tdir / "diff.patch"
    result = grade(task, entry_for(task), diff)
    (tdir / "grade.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0


def load_env() -> None:
    envfile = REPO_ROOT / ".env"
    if not envfile.exists():
        return
    for line in envfile.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


def cmd_classify(args) -> int:
    from repogym.failure.judge import build_prompt, call_judge, judgment_path
    from repogym.failure.rules import classify_rules, primary_from_signals
    from repogym.telemetry.normalize import normalize_claude_trace

    task = load_task(args.task)
    tdir = trial_dir(task.id, args.agent, args.trial)
    grade_data = json.loads((tdir / "grade.json").read_text())
    record = json.loads((tdir / "config.json").read_text()) if (tdir / "config.json").exists() else {}
    trace = tdir / "trace.jsonl"
    events = normalize_claude_trace(trace) if trace.exists() and args.agent == "claude-code" else []
    gold = task.patch_path(task.oracle.patch).read_text() if task.oracle else None

    signals = classify_rules(grade_data, record, events, gold)
    out: dict = {"signals": signals, "primary": primary_from_signals(signals)}

    if grade_data.get("outcome") != "resolved" and not args.no_judge:
        diff = (tdir / "diff.patch").read_text() if (tdir / "diff.patch").exists() else ""
        prompt = build_prompt(task.prompt, gold or "", diff, grade_data, signals, events)
        verdict = call_judge(prompt, model=args.model)
        out["judge"] = verdict
        if out["primary"] is None:
            out["primary"] = verdict["primary"]

    judgment_path(tdir).write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0


def cmd_label_template(args) -> int:
    # csv of failed trials for hand-labeling; fill `human_primary`, then run kappa
    import csv
    rows = []
    for jf in sorted((REPO_ROOT / "results" / "trials").glob("*/*/t*/judgment.json")):
        j = json.loads(jf.read_text())
        parts = jf.parent.parts
        rows.append({"task": parts[-3], "agent": parts[-2], "trial": parts[-1],
                     "judge_primary": j.get("judge", {}).get("primary") or j.get("primary") or "",
                     "human_primary": ""})
    out = REPO_ROOT / "results" / "labels.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["task", "agent", "trial", "judge_primary", "human_primary"])
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {out} ({len(rows)} trials) - fill human_primary, then `repogym kappa`")
    return 0


def cmd_kappa(args) -> int:
    import csv

    from repogym.evaluation.stats import cohens_kappa
    with open(REPO_ROOT / "results" / "labels.csv") as f:
        labeled = [r for r in csv.DictReader(f) if r["human_primary"].strip()]
    if not labeled:
        print("no human labels yet")
        return 1
    leaf_pairs = [(r["judge_primary"], r["human_primary"]) for r in labeled]
    branch_pairs = [(a.split("/")[0], b.split("/")[0]) for a, b in leaf_pairs]
    print(f"n={len(labeled)}  kappa_leaf={cohens_kappa(leaf_pairs):.3f}  "
          f"kappa_branch={cohens_kappa(branch_pairs):.3f}  (G3 gate: branch >= 0.6)")
    return 0


def cmd_report(args) -> int:
    from repogym.evaluation.report import collect_trials, leaderboard, write_report
    path = write_report()
    board = leaderboard(collect_trials())
    print(f"wrote {path}")
    for agent, s in board.items():
        print(f"{agent}: solve={s['solve_rate']:.0%} trials={s['trials']} "
              f"$?/task={s['cost_per_task']} regressions={s['regression_rate']:.0%}")
    return 0


def cmd_mine(args) -> int:
    from repogym.taskgen.mine import mine_repo
    entry = load_registry()[args.repo]
    stats = mine_repo(args.repo, entry, REPO_ROOT / "tasks" / "_candidates", limit=args.limit)
    print(json.dumps(stats, indent=2))
    return 0


def cmd_validate_candidates(args) -> int:
    cand_root = REPO_ROOT / "tasks" / "_candidates"
    dirs = []
    for d in sorted(cand_root.iterdir()):
        if not (d / "task.yaml").exists() or (d / "problems.txt").exists():
            continue
        if (REPO_ROOT / "tasks" / d.name).exists():  # already promoted in a past batch
            print(f"  skip {d.name}: already promoted")
            continue
        dirs.append(d)
    from concurrent.futures import ThreadPoolExecutor

    def check(d) -> bool:
        task = TaskSpec.load(d)
        try:
            problems = validate(task, entry_for(task), times=args.times)
        except Exception as e:  # noqa: BLE001 - mined junk must not kill the batch
            problems = [f"validation crashed: {e}"]
        if problems:
            (d / "problems.txt").write_text("\n".join(problems))
            print(f"  reject {task.id}: {problems[0][:110]}", flush=True)
            return False
        d.rename(REPO_ROOT / "tasks" / d.name)
        print(f"  PROMOTE {task.id}", flush=True)
        return True

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        outcomes = list(pool.map(check, dirs))
    promoted = sum(outcomes)
    print(f"promoted={promoted} rejected={len(outcomes) - promoted} "
          f"yield={promoted / max(1, len(dirs)):.0%}", flush=True)
    return 0


def main() -> None:
    load_env()
    p = argparse.ArgumentParser(prog="repogym")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build-image", help="build the pinned docker image for a repo")
    b.add_argument("repo")
    b.set_defaults(fn=cmd_build_image)

    v = sub.add_parser("validate", help="run task admission checks")
    v.add_argument("task")
    v.add_argument("--times", type=int, default=2)
    v.set_defaults(fn=cmd_validate)

    r = sub.add_parser("run", help="run one agent trial on a task")
    r.add_argument("task")
    r.add_argument("--agent", required=True, choices=sorted(ADAPTERS))
    r.add_argument("--trial", type=int, default=1)
    r.add_argument("--model", default=None)
    r.set_defaults(fn=cmd_run)

    g = sub.add_parser("grade", help="grade a completed trial post-hoc")
    g.add_argument("task")
    g.add_argument("--agent", required=True, choices=sorted(ADAPTERS))
    g.add_argument("--trial", type=int, default=1)
    g.set_defaults(fn=cmd_grade)

    rp = sub.add_parser("report", help="aggregate all graded trials into results/report.json")
    rp.set_defaults(fn=cmd_report)

    c = sub.add_parser("classify", help="classify a failed trial: rules + llm judge")
    c.add_argument("task")
    c.add_argument("--agent", required=True, choices=sorted(ADAPTERS))
    c.add_argument("--trial", type=int, default=1)
    c.add_argument("--model", default="sonnet")
    c.add_argument("--no-judge", action="store_true", help="rules only, no paid judge call")
    c.set_defaults(fn=cmd_classify)

    m = sub.add_parser("mine", help="mine issue+PR candidate tasks from github")
    m.add_argument("repo")
    m.add_argument("--limit", type=int, default=50)
    m.set_defaults(fn=cmd_mine)

    vc = sub.add_parser("validate-candidates", help="validate mined candidates, promote valid ones")
    vc.add_argument("--times", type=int, default=2)
    vc.add_argument("--jobs", type=int, default=4)
    vc.set_defaults(fn=cmd_validate_candidates)

    lt = sub.add_parser("label-template", help="csv of judged trials for human labeling")
    lt.set_defaults(fn=cmd_label_template)

    k = sub.add_parser("kappa", help="judge-vs-human agreement from results/labels.csv")
    k.set_defaults(fn=cmd_kappa)

    args = p.parse_args()
    sys.exit(args.fn(args))
