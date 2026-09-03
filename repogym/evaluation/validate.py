from repogym.evaluation import testrun
from repogym.images import RepoEntry
from repogym.sandbox import Sandbox
from repogym.schema import TaskSpec
from repogym.workspace import apply_patch, setup_workspace


def validate_once(task: TaskSpec, entry: RepoEntry) -> list[str]:
    problems: list[str] = []
    t = task.timeouts.eval_s
    with Sandbox(task.runtime.image) as sb:
        setup_workspace(sb, entry, task.base_commit)

        if task.mutation_patch:
            ok, out = apply_patch(sb, task.patch_path(task.mutation_patch), "mutation")
            if not ok:
                return [f"mutation patch failed to apply: {out[-500:]}"]
            sb.exec("git add -A && git commit -qm 'task setup'")

        ok, out = apply_patch(sb, task.patch_path(task.hidden_tests.patch), "tests")
        if not ok:
            return [f"hidden tests patch failed to apply: {out[-500:]}"]

        f2p = testrun.run_tests(sb, entry, task.hidden_tests.fail_to_pass, t)
        for tid, r in f2p.items():
            if r != testrun.FAIL:
                problems.append(f"f2p test not failing pre-fix: {tid} -> {r}")

        p2p = testrun.run_tests(sb, entry, task.hidden_tests.pass_to_pass, t)
        for tid, r in p2p.items():
            if r != testrun.PASS:
                problems.append(f"p2p test not passing pre-fix: {tid} -> {r}")

        if task.oracle is None:
            problems.append("no oracle patch; cannot verify solvability")
            return problems

        ok, out = apply_patch(sb, task.patch_path(task.oracle.patch), "gold")
        if not ok:
            problems.append(f"gold patch failed to apply: {out[-500:]}")
            return problems

        f2p_post = testrun.run_tests(sb, entry, task.hidden_tests.fail_to_pass, t)
        for tid, r in f2p_post.items():
            if r != testrun.PASS:
                problems.append(f"f2p test not passing post-gold: {tid} -> {r}")

        p2p_post = testrun.run_tests(sb, entry, task.hidden_tests.pass_to_pass, t)
        for tid, r in p2p_post.items():
            if r != testrun.PASS:
                problems.append(f"p2p test not passing post-gold: {tid} -> {r}")

    return problems


def validate(task: TaskSpec, entry: RepoEntry, times: int = 2) -> list[str]:
    problems: list[str] = []
    for i in range(times):
        run_problems = validate_once(task, entry)
        problems += [f"run{i + 1}: {p}" for p in run_problems]
    return problems
