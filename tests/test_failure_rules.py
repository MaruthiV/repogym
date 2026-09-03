from repogym.failure.rules import classify_rules, gold_files, loop_signal
from repogym.telemetry.events import Event

GOLD = """diff --git a/src/flask/helpers.py b/src/flask/helpers.py
index 1..2 100644
--- a/src/flask/helpers.py
+++ b/src/flask/helpers.py
"""


def ev(i, type_, **kw):
    return Event(i=i, type=type_, **kw)


def test_gold_files():
    assert gold_files(GOLD) == {"src/flask/helpers.py"}


def test_loop_detection():
    events = [ev(i, "tool_call", tool="Bash", arg="pytest -q") for i in range(3)]
    assert loop_signal(events)
    events[1] = ev(1, "tool_call", tool="Read", arg="x.py")
    assert not loop_signal(events)


def test_wrong_module_and_no_tests():
    events = [
        ev(0, "model_call"),
        ev(1, "tool_call", tool="Edit", arg="/work/src/flask/app.py"),
        ev(2, "file_edit", tool="Edit", arg="/work/src/flask/app.py"),
        ev(3, "result", subtype="success"),
    ]
    grade = {"outcome": "unresolved"}
    record = {"agent_rc": 0, "timed_out": False}
    signals = classify_rules(grade, record, events, GOLD)
    assert "repository_reasoning/edited_wrong_module" in signals
    assert "validation/failed_to_run_tests" in signals
    assert "agent_behavior/premature_completion" in signals


def test_resolved_trial_has_no_signals():
    events = [
        ev(0, "tool_call", tool="Edit", arg="/work/src/flask/helpers.py"),
        ev(1, "file_edit", tool="Edit", arg="/work/src/flask/helpers.py"),
        ev(2, "test_run", tool="Bash", arg="pytest"),
        ev(3, "result", subtype="success"),
    ]
    assert classify_rules({"outcome": "resolved"}, {"agent_rc": 0}, events, GOLD) == []


def test_regression_signal():
    assert classify_rules({"outcome": "regression"}, {}, [], GOLD) == [
        "validation/introduced_regression"
    ]
