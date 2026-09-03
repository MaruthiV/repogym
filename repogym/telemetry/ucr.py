import zlib

from repogym.telemetry.events import FILE_EDIT, MODEL_CALL, Event

SURVIVAL_THRESHOLD = 0.5


def diff_added_hashes(diff_text: str) -> set[int]:
    out = set()
    for line in diff_text.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            stripped = line[1:].strip()
            if stripped:
                out.add(zlib.crc32(stripped.encode()))
    return out


def compute_ucr(events: list[Event], final_diff_text: str) -> float | None:
    final = diff_added_hashes(final_diff_text)
    useful_tokens = 0
    total_tokens = 0
    current_call: Event | None = None
    call_is_useful: dict[int, bool] = {}
    call_tokens: dict[int, int] = {}

    for e in events:
        if e.type == MODEL_CALL:
            current_call = e
            call_tokens[e.i] = e.tokens_out or 0
            call_is_useful.setdefault(e.i, False)
        elif e.type == FILE_EDIT and current_call is not None and e.line_hashes:
            surviving = sum(1 for h in e.line_hashes if h in final)
            if surviving / len(e.line_hashes) >= SURVIVAL_THRESHOLD:
                call_is_useful[current_call.i] = True

    total_tokens = sum(call_tokens.values())
    if not total_tokens:
        return None
    useful_tokens = sum(t for i, t in call_tokens.items() if call_is_useful.get(i))
    return round(useful_tokens / total_tokens, 4)
