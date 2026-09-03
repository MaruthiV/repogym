import os
import shlex
import time

from repogym.adapters.base import AgentRunResult
from repogym.sandbox import Sandbox
from repogym.schema import Timeouts

PASSTHROUGH_ENV = ["ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"]


class ClaudeCode:
    name = "claude-code"

    def version(self, sb: Sandbox) -> str:
        _, out = sb.exec("claude --version", timeout=60)
        return out.strip()

    def run(self, sb: Sandbox, timeouts: Timeouts, model: str | None) -> AgentRunResult:
        env = {k: os.environ[k] for k in PASSTHROUGH_ENV if k in os.environ}
        # claude refuses --dangerously-skip-permissions as root without this
        env["IS_SANDBOX"] = "1"

        flags = "--output-format stream-json --verbose --dangerously-skip-permissions"
        if model:
            flags += f" --model {model}"
        inner = f'claude -p "$(cat /tmp/prompt.md)" {flags} >/tmp/trace.jsonl 2>/tmp/agent.err'
        cmd = f"timeout {timeouts.agent_s}s bash -c {shlex.quote(inner)}"

        start = time.time()
        rc, _ = sb.exec(cmd, env=env, timeout=timeouts.agent_s + 120)
        return AgentRunResult(
            rc=rc,
            wall_s=round(time.time() - start, 1),
            trace_files={"trace.jsonl": "/tmp/trace.jsonl", "agent.err": "/tmp/agent.err"},
        )
