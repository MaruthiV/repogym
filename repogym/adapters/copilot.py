import os
import shlex
import time
from pathlib import Path

from repogym.adapters.base import AgentRunResult
from repogym.sandbox import Sandbox
from repogym.schema import Timeouts

HOST_CONFIG = Path.home() / ".copilot" / "config.json"


class CopilotCLI:
    name = "copilot"

    def version(self, sb: Sandbox) -> str:
        _, out = sb.exec("copilot --version", timeout=60)
        return out.strip().splitlines()[0] if out.strip() else "?"

    def run(self, sb: Sandbox, timeouts: Timeouts, model: str | None) -> AgentRunResult:
        env = {}
        for k in ("GH_TOKEN", "GITHUB_TOKEN", "COPILOT_GITHUB_TOKEN"):
            if k in os.environ:
                env[k] = os.environ[k]
        # copilot auth lives in ~/.copilot; reuse the host login inside the container
        if HOST_CONFIG.exists():
            sb.exec("mkdir -p /root/.copilot", workdir="/")
            sb.copy_in(HOST_CONFIG, "/root/.copilot/config.json")

        model_flag = f"--model {model}" if model else ""
        inner = (
            f'copilot -p "$(cat /tmp/prompt.md)" --allow-all --no-ask-user --no-color '
            f"{model_flag} --usage-output-file /tmp/usage.json "
            "--log-dir /tmp/copilot-logs --log-level debug "
            ">/tmp/agent.out 2>/tmp/agent.err; "
            "cat /tmp/copilot-logs/*.log > /tmp/copilot.log 2>/dev/null; true"
        )
        cmd = f"timeout {timeouts.agent_s}s bash -c {shlex.quote(inner)}"

        start = time.time()
        rc, _ = sb.exec(cmd, env=env, timeout=timeouts.agent_s + 120)
        return AgentRunResult(
            rc=rc,
            wall_s=round(time.time() - start, 1),
            trace_files={
                "agent.out": "/tmp/agent.out",
                "agent.err": "/tmp/agent.err",
                "usage.json": "/tmp/usage.json",
                "copilot.log": "/tmp/copilot.log",
            },
        )
