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

    args = p.parse_args()
    sys.exit(args.fn(args))
