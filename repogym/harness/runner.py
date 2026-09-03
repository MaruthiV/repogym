import json
import time
from datetime import UTC, datetime
from pathlib import Path

from repogym.adapters.base import AgentAdapter
from repogym.images import REPO_ROOT, RepoEntry
from repogym.sandbox import Sandbox
from repogym.schema import TaskSpec
from repogym.workspace import apply_patch, extract_diff, setup_workspace

PROMPT_WRAPPER = """{prompt}

You are working in the repository checked out in the current directory. \
Make the change described above and ensure it is saved to disk. \
Do not commit; leave changes in the working tree."""


def trial_dir(task_id: str, agent_name: str, trial_n: int) -> Path:
    return REPO_ROOT / "results" / "trials" / task_id / agent_name / f"t{trial_n}"


def run_trial(task: TaskSpec, entry: RepoEntry, adapter: AgentAdapter, trial_n: int,
              model: str | None = None) -> Path:
    tdir = trial_dir(task.id, adapter.name, trial_n)
    tdir.mkdir(parents=True, exist_ok=True)
    start = time.time()

    prompt = PROMPT_WRAPPER.format(prompt=task.prompt.strip())
    (tdir / "prompt.md").write_text(prompt)

    record = {
        "task": task.id,
        "agent": adapter.name,
        "trial": trial_n,
        "model": model,
        "image": task.runtime.image,
        "started_at": datetime.now(UTC).isoformat(),
    }

    with Sandbox(task.runtime.image) as sb:
        record["agent_version"] = adapter.version(sb)
        setup_workspace(sb, entry)

        if task.mutation_patch:
            ok, out = apply_patch(sb, task.patch_path(task.mutation_patch), "mutation")
            if not ok:
                raise RuntimeError(f"mutation apply failed for {task.id}: {out[-500:]}")
            sb.exec("git add -A && git commit -qm 'task setup'")
        _, diff_base = sb.exec("git rev-parse HEAD")
        diff_base = diff_base.strip()

        sb.copy_in(tdir / "prompt.md", "/tmp/prompt.md")
        result = adapter.run(sb, task.timeouts, model)
        record["agent_rc"] = result.rc
        record["agent_wall_s"] = result.wall_s
        record["timed_out"] = result.rc == 124

        for label, cpath in result.trace_files.items():
            sb.copy_out(cpath, tdir / label)

        (tdir / "diff.patch").write_text(extract_diff(sb, diff_base))
        record["diff_base"] = diff_base

    record["total_wall_s"] = round(time.time() - start, 1)
    (tdir / "config.json").write_text(json.dumps(record, indent=2))
    return tdir
