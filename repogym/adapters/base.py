from typing import Protocol

from pydantic import BaseModel

from repogym.sandbox import Sandbox
from repogym.schema import Timeouts


class AgentRunResult(BaseModel):
    rc: int
    wall_s: float
    # label -> path inside container, copied out by the runner
    trace_files: dict[str, str] = {}


class AgentAdapter(Protocol):
    name: str

    def version(self, sb: Sandbox) -> str: ...

    def run(self, sb: Sandbox, timeouts: Timeouts, model: str | None) -> AgentRunResult: ...
