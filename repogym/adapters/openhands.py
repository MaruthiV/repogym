import os
import shlex
import time

from repogym.adapters.base import AgentRunResult
from repogym.sandbox import Sandbox
from repogym.schema import Timeouts

DEFAULT_MODEL = "anthropic/claude-sonnet-5"


class OpenHands:
    name = "openhands"

    def version(self, sb: Sandbox) -> str:
        _, out = sb.exec("openhands --version 2>&1 || python -m openhands.core.main --version 2>&1",
                         timeout=120)
        return out.strip().splitlines()[-1] if out.strip() else "?"

    def run(self, sb: Sandbox, timeouts: Timeouts, model: str | None) -> AgentRunResult:
        env = {
            "RUNTIME": "local",
            "SANDBOX_VOLUMES": "/work:/work:rw",
            "LLM_MODEL": model or DEFAULT_MODEL,
            "LOG_ALL_EVENTS": "true",
        }
        for k in ("ANTHROPIC_API_KEY", "LLM_API_KEY", "OPENAI_API_KEY"):
            if k in os.environ:
                env[k] = os.environ[k]
        if "LLM_API_KEY" not in env and "ANTHROPIC_API_KEY" in env:
            env["LLM_API_KEY"] = env["ANTHROPIC_API_KEY"]

        inner = (
            'openhands --headless -t "$(cat /tmp/prompt.md)" '
            ">/tmp/agent.out 2>/tmp/agent.err"
        )
        cmd = f"timeout {timeouts.agent_s}s bash -c {shlex.quote(inner)}"

        start = time.time()
        rc, _ = sb.exec(cmd, env=env, timeout=timeouts.agent_s + 120)
        # event stream location varies by version, grab both spots
        sb.exec("cp -r /root/.openhands/sessions /tmp/oh-sessions 2>/dev/null; "
                "tar czf /tmp/oh-events.tgz /tmp/oh-sessions 2>/dev/null; true", workdir="/")
        return AgentRunResult(
            rc=rc,
            wall_s=round(time.time() - start, 1),
            trace_files={
                "agent.out": "/tmp/agent.out",
                "agent.err": "/tmp/agent.err",
                "oh-events.tgz": "/tmp/oh-events.tgz",
            },
        )
