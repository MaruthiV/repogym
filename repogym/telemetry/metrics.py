from collections import Counter

from repogym.telemetry.events import FILE_EDIT, MODEL_CALL, RESULT, TEST_RUN, TOOL_CALL, Event


def trial_metrics(events: list[Event]) -> dict:
    model_calls = [e for e in events if e.type == MODEL_CALL]
    tool_calls = [e for e in events if e.type == TOOL_CALL]
    result = next((e for e in events if e.type == RESULT), None)

    m = {
        "n_model_calls": len(model_calls),
        "n_tool_calls": len(tool_calls),
        "tool_histogram": dict(Counter(e.tool for e in tool_calls)),
        "files_edited": sorted({e.arg for e in events if e.type == FILE_EDIT and e.arg}),
        "n_test_runs": sum(1 for e in events if e.type == TEST_RUN),
        "tokens_out": sum(e.tokens_out or 0 for e in model_calls),
        "tokens_in_uncached": sum(e.tokens_in or 0 for e in model_calls),
        "cache_read": sum(e.cache_read or 0 for e in model_calls),
        "cache_create": sum(e.cache_create or 0 for e in model_calls),
    }
    if result:
        m["cost_usd"] = result.cost_usd
        m["duration_ms"] = result.duration_ms
        m["num_turns"] = result.num_turns
        m["result_subtype"] = result.subtype
    return m
