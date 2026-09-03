from pydantic import BaseModel

MODEL_CALL = "model_call"
TOOL_CALL = "tool_call"
FILE_EDIT = "file_edit"
TEST_RUN = "test_run"
RESULT = "result"

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
TEST_MARKERS = ("pytest", "go test", "npm test", "vitest", "jest", "unittest")


class Event(BaseModel):
    i: int
    type: str
    # model_call
    model: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cache_read: int | None = None
    cache_create: int | None = None
    # tool_call / file_edit / test_run
    tool: str | None = None
    arg: str | None = None
    # file_edit only: hashes of lines this edit added, for ucr survival matching
    line_hashes: list[int] | None = None
    # result
    cost_usd: float | None = None
    duration_ms: int | None = None
    num_turns: int | None = None
    subtype: str | None = None


def write_events(events: list[Event], path) -> None:
    with open(path, "w") as f:
        f.writelines(e.model_dump_json(exclude_none=True) + "\n" for e in events)


def read_events(path) -> list[Event]:
    return [Event.model_validate_json(line) for line in open(path) if line.strip()]
