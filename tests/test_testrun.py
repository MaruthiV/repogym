from repogym.evaluation.testrun import test_cmd as compose
from repogym.images import RepoEntry

PY = RepoEntry(url="u", sha="s", language="python",
               install="x", test_base=".venv/bin/python -m pytest -q")
TS = RepoEntry(url="u", sha="s", language="typescript", test_style="vitest",
               install="x", test_base="npx vitest run")


def test_pycompose():
    assert compose(PY, "tests/test_x.py::test_y") == \
        ".venv/bin/python -m pytest -q tests/test_x.py::test_y"


def test_vitest_cmd_with_name():
    got = compose(TS, "packages/zod/tests/string.test.ts::trim works")
    assert got == "npx vitest run packages/zod/tests/string.test.ts -t 'trim works'"


def test_vitest_cmd_whole_file():
    assert compose(TS, "packages/zod/tests/string.test.ts") == \
        "npx vitest run packages/zod/tests/string.test.ts"
