import subprocess

from repogym.refagent.agent import extract_diff, run_refagent
from repogym.refagent.providers import BM25Context, FullContext, GraphContext, prompt_keywords


def make_repo(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mathy.py").write_text("def add(a, b):\n    return a - b\n")
    (tmp_path / "pkg" / "other.py").write_text("from pkg import mathy\nX = 1\n")
    (tmp_path / "readme.md").write_text("small demo repo\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "init"], cwd=tmp_path)
    return tmp_path


def test_prompt_keywords_extracts_identifiers():
    kws = prompt_keywords("add() returns wrong result in pkg/mathy.py subtraction bug")
    assert "add" in kws and "mathy" in kws


def test_providers_rank_relevant_file_first(tmp_path):
    root = make_repo(tmp_path)
    prompt = "the add function in mathy returns the wrong result"
    for provider in (FullContext(), BM25Context(), GraphContext()):
        ctx = provider.build(root, prompt, budget_tokens=5000)
        assert "mathy.py" in ctx, provider.name
    bm25 = BM25Context().build(root, prompt, budget_tokens=5000)
    assert bm25.index("mathy.py") < bm25.index("readme.md") if "readme.md" in bm25 else True


def test_extract_diff_variants():
    fenced = "here\n```diff\ndiff --git a/x b/x\n```\n"
    assert extract_diff(fenced).startswith("diff --git")
    bare = "diff --git a/x b/x\n--- a/x\n"
    assert extract_diff(bare) == bare
    assert extract_diff("no patch here") is None


GOOD_DIFF = """```diff
diff --git a/pkg/mathy.py b/pkg/mathy.py
--- a/pkg/mathy.py
+++ b/pkg/mathy.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a - b
+    return a + b
```"""


def test_refagent_loop_applies_and_passes(tmp_path):
    root = make_repo(tmp_path)

    def fake_llm(system, turn):
        return GOOD_DIFF

    result = run_refagent(root, "add() subtracts instead of adding", FullContext(),
                          fake_llm, test_cmd="python3 -c \"import sys; sys.path.insert(0,'.'); "
                          "from pkg.mathy import add; assert add(2,3)==5\"")
    assert result["done"] and result["rounds"] == 1
    assert (root / "pkg" / "mathy.py").read_text().count("a + b") == 1


def test_refagent_retries_on_garbage(tmp_path):
    root = make_repo(tmp_path)
    replies = iter(["no diff at all", GOOD_DIFF])

    def flaky_llm(system, turn):
        return next(replies)

    result = run_refagent(root, "fix add", FullContext(), flaky_llm)
    assert result["done"] and result["rounds"] == 2
