import shlex

from repogym.images import RepoEntry
from repogym.sandbox import Sandbox

PASS, FAIL, ERROR = "pass", "fail", "error"


def test_cmd(entry: RepoEntry, test_id: str) -> str:
    if entry.test_style == "vitest":
        # id is "path" or "path::full test name"
        path, _, name = test_id.partition("::")
        cmd = f"{entry.test_base} {shlex.quote(path)}"
        if name:
            cmd += f" -t {shlex.quote(name)}"
        return cmd
    if entry.test_style == "gotest":
        # id is "pkg::TestName" or "pkg" ("." for module root)
        pkg, _, name = test_id.partition("::")
        cmd = f"{entry.test_base} ./{pkg.strip('/')}"
        if name:
            cmd += f" -run {shlex.quote(f'^{name}$')}"
        return cmd
    return f"{entry.test_base} {shlex.quote(test_id)}"


def run_test(sb: Sandbox, entry: RepoEntry, test_id: str, timeout: int) -> str:
    rc, out = sb.exec(test_cmd(entry, test_id), timeout=timeout)
    # go test exits 0 when -run matches nothing, that is not a pass
    if entry.test_style == "gotest" and "::" in test_id \
            and ("no tests to run" in out or "[no test files]" in out):
        return ERROR
    if rc == 0:
        return PASS
    if rc == 1:
        return FAIL
    return ERROR


def run_tests(sb: Sandbox, entry: RepoEntry, test_ids: list[str], timeout: int) -> dict[str, str]:
    return {tid: run_test(sb, entry, tid, timeout) for tid in test_ids}


def all_pass(results: dict[str, str]) -> bool:
    return all(v == PASS for v in results.values())


def all_fail(results: dict[str, str]) -> bool:
    return all(v == FAIL for v in results.values())
