import zlib

from repogym.telemetry.events import Event
from repogym.telemetry.ucr import compute_ucr

DIFF = """diff --git a/src/x.py b/src/x.py
--- a/src/x.py
+++ b/src/x.py
@@ -1,2 +1,2 @@
-    return a - b
+    return a + b
+    log("fixed")
"""


def h(line):
    return zlib.crc32(line.strip().encode())


def test_ucr_counts_only_surviving_calls():
    events = [
        # call 1: edit survives into final diff
        Event(i=0, type="model_call", tokens_out=100),
        Event(i=1, type="file_edit", tool="Edit", arg="src/x.py",
              line_hashes=[h("return a + b"), h('log("fixed")')]),
        # call 2: edit was reverted, nothing survives
        Event(i=2, type="model_call", tokens_out=300),
        Event(i=3, type="file_edit", tool="Edit", arg="src/y.py",
              line_hashes=[h("totally gone line")]),
        # call 3: no edits at all (exploration)
        Event(i=4, type="model_call", tokens_out=100),
    ]
    assert compute_ucr(events, DIFF) == 0.2


def test_ucr_none_without_tokens():
    assert compute_ucr([], DIFF) is None


def test_ucr_partial_survival_threshold():
    events = [
        Event(i=0, type="model_call", tokens_out=50),
        # 1 of 3 lines survives -> below 0.5 threshold -> not useful
        Event(i=1, type="file_edit", tool="Edit", arg="src/x.py",
              line_hashes=[h("return a + b"), h("gone1"), h("gone2")]),
    ]
    assert compute_ucr(events, DIFF) == 0.0
