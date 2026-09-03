import shlex

from repogym.sandbox import Sandbox

PASS, FAIL, ERROR = "pass", "fail", "error"


def run_test(sb: Sandbox, test_base: str, test_id: str, timeout: int) -> str:
    rc, _ = sb.exec(f"{test_base} {shlex.quote(test_id)}", timeout=timeout)
    if rc == 0:
        return PASS
    if rc == 1:
        return FAIL
    return ERROR


def run_tests(sb: Sandbox, test_base: str, test_ids: list[str], timeout: int) -> dict[str, str]:
    return {tid: run_test(sb, test_base, tid, timeout) for tid in test_ids}


def all_pass(results: dict[str, str]) -> bool:
    return all(v == PASS for v in results.values())


def all_fail(results: dict[str, str]) -> bool:
    return all(v == FAIL for v in results.values())
