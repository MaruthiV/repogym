from repogym.adapters.aider import Aider
from repogym.adapters.claude_code import ClaudeCode
from repogym.adapters.copilot import CopilotCLI
from repogym.adapters.openhands import OpenHands
from repogym.adapters.scripted import NoopAgent, OracleAgent, SloppyAgent

ADAPTERS = {a.name: a for a in [
    ClaudeCode(), Aider(), CopilotCLI(), OpenHands(),
    OracleAgent(), NoopAgent(), SloppyAgent(),
]}
