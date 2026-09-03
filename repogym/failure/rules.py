import re

from repogym.telemetry.events import Event

# taxonomy leaves the rules can assert without a judge
SYNTAX_OR_APPLY = "code_generation/syntax_or_apply_error"
INTRODUCED_REGRESSION = "validation/introduced_regression"
FAILED_TO_RUN_TESTS = "validation/failed_to_run_tests"
LOOPED = "agent_behavior/looped"
CONTEXT_LOSS = "agent_behavior/context_loss"
PREMATURE_COMPLETION = "agent_behavior/premature_completion"
WRONG_MODULE = "repository_reasoning/edited_wrong_module"
EXCESSIVE_EXPLORATION = "agent_behavior/excessive_exploration"

LOOP_N = 3
EXPLORATION_TOOLCALLS = 80
EXPLORATION_EDIT_RATIO = 0.05

RULE_PRECEDENCE = [
    INTRODUCED_REGRESSION, SYNTAX_OR_APPLY, LOOPED, CONTEXT_LOSS,
    FAILED_TO_RUN_TESTS, WRONG_MODULE, EXCESSIVE_EXPLORATION, PREMATURE_COMPLETION,
]


def primary_from_signals(signals: list[str]) -> str | None:
    return next((leaf for leaf in RULE_PRECEDENCE if leaf in signals), None)


def gold_files(gold_patch_text: str) -> set[str]:
    return set(re.findall(r"^diff --git a/\S+ b/(\S+)", gold_patch_text, re.MULTILINE))


def loop_signal(events: list[Event]) -> bool:
    calls = [(e.tool, e.arg) for e in events if e.type == "tool_call"]
    run = 1
    for prev, cur in zip(calls, calls[1:]):
        run = run + 1 if cur == prev else 1
        if run >= LOOP_N:
            return True
    return False


def classify_rules(grade: dict, record: dict, events: list[Event],
                   gold_patch_text: str | None) -> list[str]:
    signals: list[str] = []
    outcome = grade.get("outcome")
    solved = outcome == "resolved"

    if outcome == "patch_error":
        signals.append(SYNTAX_OR_APPLY)
    if outcome == "regression":
        signals.append(INTRODUCED_REGRESSION)

    if events:
        test_runs = [e for e in events if e.type == "test_run"]
        tool_calls = [e for e in events if e.type == "tool_call"]
        edits = [e for e in events if e.type == "file_edit"]
        result = next((e for e in events if e.type == "result"), None)

        if not solved and not test_runs:
            signals.append(FAILED_TO_RUN_TESTS)
        if loop_signal(events):
            signals.append(LOOPED)
        if result and result.subtype and "max_turns" in result.subtype:
            signals.append(CONTEXT_LOSS)
        if not solved and len(tool_calls) > EXPLORATION_TOOLCALLS \
                and len(edits) / len(tool_calls) < EXPLORATION_EDIT_RATIO:
            signals.append(EXCESSIVE_EXPLORATION)
        if not solved and result and not record.get("timed_out") \
                and record.get("agent_rc") == 0 and not test_runs and edits:
            signals.append(PREMATURE_COMPLETION)

        if not solved and gold_patch_text and edits:
            edited = {e.arg.removeprefix("/work/") for e in edits if e.arg}
            if edited and not (edited & gold_files(gold_patch_text)):
                signals.append(WRONG_MODULE)

    return signals
