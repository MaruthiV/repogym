from repogym.adapters.aider import Aider
from repogym.adapters.claude_code import ClaudeCode
from repogym.adapters.copilot import CopilotCLI
from repogym.adapters.openhands import OpenHands

ADAPTERS = {a.name: a for a in [ClaudeCode(), Aider(), CopilotCLI(), OpenHands()]}
