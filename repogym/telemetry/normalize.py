import json
from pathlib import Path

from repogym.telemetry.events import (
    EDIT_TOOLS,
    FILE_EDIT,
    MODEL_CALL,
    RESULT,
    TEST_MARKERS,
    TEST_RUN,
    TOOL_CALL,
    Event,
)


def _tool_arg(name: str, tool_input: dict) -> str | None:
    if name in EDIT_TOOLS or name in ("Read",):
        return tool_input.get("file_path") or tool_input.get("notebook_path")
    if name == "Bash":
        return (tool_input.get("command") or "")[:300]
    if name in ("Glob", "Grep"):
        return tool_input.get("pattern")
    return None


def normalize_claude_trace(trace_path: Path) -> list[Event]:
    events: list[Event] = []
    i = 0
    for line in trace_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        kind = obj.get("type")
        if kind == "assistant":
            msg = obj.get("message") or {}
            usage = msg.get("usage") or {}
            events.append(Event(
                i=i, type=MODEL_CALL,
                model=msg.get("model"),
                tokens_in=usage.get("input_tokens"),
                tokens_out=usage.get("output_tokens"),
                cache_read=usage.get("cache_read_input_tokens"),
                cache_create=usage.get("cache_creation_input_tokens"),
            ))
            i += 1
            for block in msg.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    name = block.get("name") or "?"
                    tool_input = block.get("input") or {}
                    arg = _tool_arg(name, tool_input)
                    events.append(Event(i=i, type=TOOL_CALL, tool=name, arg=arg))
                    i += 1
                    if name in EDIT_TOOLS and arg:
                        events.append(Event(i=i, type=FILE_EDIT, tool=name, arg=arg))
                        i += 1
                    cmd = tool_input.get("command") or ""
                    if name == "Bash" and any(m in cmd for m in TEST_MARKERS):
                        events.append(Event(i=i, type=TEST_RUN, tool=name, arg=arg))
                        i += 1
        elif kind == "result":
            usage = obj.get("usage") or {}
            events.append(Event(
                i=i, type=RESULT,
                subtype=obj.get("subtype"),
                cost_usd=obj.get("total_cost_usd"),
                duration_ms=obj.get("duration_ms"),
                num_turns=obj.get("num_turns"),
                tokens_in=usage.get("input_tokens"),
                tokens_out=usage.get("output_tokens"),
                cache_read=usage.get("cache_read_input_tokens"),
                cache_create=usage.get("cache_creation_input_tokens"),
            ))
            i += 1
    return events
