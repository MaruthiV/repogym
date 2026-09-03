import time
from pathlib import Path

from repogym.evaluation import testrun
from repogym.images import RepoEntry
from repogym.sandbox import Sandbox
from repogym.schema import TaskSpec
from repogym.workspace import apply_patch, setup_workspace

RESOLVED = "resolved"
PARTIAL = "partial"
UNRESOLVED = "unresolved"
REGRESSION = "regression"
PATCH_ERROR = "patch_error"
ERROR = "error"


def grade(task: TaskSpec, entry: RepoEntry, diff_path: Path) -> dict:
    start = time.time()
    t = task.timeouts.eval_s
    result: dict = {"task": task.id, "outcome": None, "f2p": {}, "p2p": {}, "detail": ""}

    with Sandbox(task.runtime.image) as sb:
        setup_workspace(sb, entry)

        if task.mutation_patch:
            ok, out = apply_patch(sb, task.patch_path(task.mutation_patch), "mutation")
            if not ok:
                result.update(outcome=ERROR, detail=f"mutation apply failed: {out[-300:]}")
                return result
            sb.exec("git add -A && git commit -qm 'task setup'")

        diff_text = diff_path.read_text() if diff_path.exists() else ""
        if diff_text.strip():
            ok, out = apply_patch(sb, diff_path, "agent")
            if not ok:
                result.update(outcome=PATCH_ERROR, detail=f"agent diff apply failed: {out[-500:]}")
                return result
        else:
            result["detail"] = "empty agent diff"

        ok, out = apply_patch(sb, task.patch_path(task.hidden_tests.patch), "tests")
        if not ok:
            # usually means the agent rewrote test files the hidden patch touches
            result.update(outcome=ERROR, detail=f"hidden tests apply failed: {out[-500:]}")
            return result

        result["f2p"] = testrun.run_tests(sb, entry.test_base, task.hidden_tests.fail_to_pass, t)
        result["p2p"] = testrun.run_tests(sb, entry.test_base, task.hidden_tests.pass_to_pass, t)

    if not testrun.all_pass(result["p2p"]):
        result["outcome"] = REGRESSION
    elif testrun.all_pass(result["f2p"]):
        result["outcome"] = RESOLVED
    elif any(v == testrun.PASS for v in result["f2p"].values()):
        result["outcome"] = PARTIAL
    else:
        result["outcome"] = UNRESOLVED

    result["grade_wall_s"] = round(time.time() - start, 1)
    return result
