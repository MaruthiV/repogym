import json

from repogym.telemetry.metrics import trial_metrics
from repogym.telemetry.normalize import normalize_claude_trace

SYNTHETIC = [
    {"type": "system", "subtype": "init", "cwd": "/work", "model": "claude-sonnet-5"},
    {"type": "assistant", "message": {
        "model": "claude-sonnet-5",
        "usage": {"input_tokens": 4, "output_tokens": 120,
                  "cache_read_input_tokens": 9000, "cache_creation_input_tokens": 3000},
        "content": [
            {"type": "text", "text": "let me look around"},
            {"type": "tool_use", "id": "t1", "name": "Grep",
             "input": {"pattern": "root_path"}},
        ]}},
    {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "t1", "content": "src/flask/helpers.py"}]}},
    {"type": "assistant", "message": {
        "model": "claude-sonnet-5",
        "usage": {"input_tokens": 6, "output_tokens": 200,
                  "cache_read_input_tokens": 12000, "cache_creation_input_tokens": 100},
        "content": [
            {"type": "tool_use", "id": "t2", "name": "Edit",
             "input": {"file_path": "/work/src/flask/helpers.py", "old_string": "a",
                       "new_string": "b"}},
            {"type": "tool_use", "id": "t3", "name": "Bash",
             "input": {"command": ".venv/bin/python -m pytest tests/ -q"}},
        ]}},
    {"type": "result", "subtype": "success", "duration_ms": 45000, "num_turns": 4,
     "total_cost_usd": 0.31,
     "usage": {"input_tokens": 10, "output_tokens": 320}},
]


def test_normalize_and_metrics(tmp_path):
    trace = tmp_path / "trace.jsonl"
    trace.write_text("\n".join(json.dumps(o) for o in SYNTHETIC))

    events = normalize_claude_trace(trace)
    types = [e.type for e in events]
    assert types == ["model_call", "tool_call", "model_call", "tool_call",
                     "file_edit", "tool_call", "test_run", "result"]

    m = trial_metrics(events)
    assert m["n_model_calls"] == 2
    assert m["n_tool_calls"] == 3
    assert m["tool_histogram"] == {"Grep": 1, "Edit": 1, "Bash": 1}
    assert m["files_edited"] == ["/work/src/flask/helpers.py"]
    assert m["n_test_runs"] == 1
    assert m["tokens_out"] == 320
    assert m["cache_read"] == 21000
    assert m["cost_usd"] == 0.31
    assert m["result_subtype"] == "success"


def test_normalize_skips_garbage_lines(tmp_path):
    trace = tmp_path / "trace.jsonl"
    trace.write_text("not json\n\n" + json.dumps(SYNTHETIC[-1]))
    events = normalize_claude_trace(trace)
    assert len(events) == 1 and events[0].type == "result"
