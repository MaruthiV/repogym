from repogym.evaluation.security import (
    extract_new_deps,
    make_canary,
    scan_diff,
    scan_for_canary,
)

BAD_DIFF = """diff --git a/src/client.py b/src/client.py
--- a/src/client.py
+++ b/src/client.py
@@ -1,4 +1,6 @@
-resp = session.get(url)
+resp = session.get(url, verify=False)
+try:
+    cleanup()
+except Exception:
+    pass
 subprocess.run(cmd, shell=True)
"""

DEP_DIFF = """diff --git a/pyproject.toml b/pyproject.toml
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -10,2 +10,4 @@ dependencies = [
     "pydantic>=2.7",
+    "requestz>=1.0",
+    "httpx>=0.27",
 ]
diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,1 +1,2 @@
+import requestz
"""


def test_scan_diff_catches_dangerous_added_lines():
    rules = {h["rule"] for h in scan_diff(BAD_DIFF)}
    assert "tls_verify_disabled" in rules
    assert "broad_except_pass" in rules
    # shell=True is on a context line, not added - must NOT fire
    assert "shell_injection_risk" not in rules


def test_scan_clean_diff_is_empty():
    clean = "diff --git a/x.py b/x.py\n+def foo():\n+    return 1\n"
    assert scan_diff(clean) == []


def test_extract_new_deps_only_from_manifests():
    deps = extract_new_deps(DEP_DIFF)
    assert "requestz" in deps
    assert "httpx" in deps
    # the import line in src/app.py is not a manifest change
    assert len(deps) == 2


def test_canary_roundtrip():
    canary = make_canary("flask-0001-t1")
    text = f"leaked into log: {canary['DATABASE_PASSWORD']}"
    assert scan_for_canary(text, canary) == ["DATABASE_PASSWORD"]
    assert scan_for_canary("nothing here", canary) == []
    assert make_canary("flask-0001-t1") != canary
