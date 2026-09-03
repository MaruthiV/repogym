import os
import shlex
import time

from repogym.adapters.base import AgentRunResult
from repogym.sandbox import Sandbox
from repogym.schema import TaskSpec, Timeouts

PASSTHROUGH_ENV = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"]


class Aider:
    name = "aider"

    def version(self, sb: Sandbox) -> str:
        _, out = sb.exec("aider --version", timeout=120)
        return out.strip()

    def run(self, sb: Sandbox, task: TaskSpec, timeouts: Timeouts,
            model: str | None) -> AgentRunResult:
        env = {k: os.environ[k] for k in PASSTHROUGH_ENV if k in os.environ}
        model_flag = f"--model {model}" if model else ""
        inner = (
            f"aider --yes-always --no-stream --no-show-model-warnings {model_flag} "
            "--message-file /tmp/prompt.md --llm-history-file /tmp/llm_history.txt "
            ">/tmp/agent.out 2>/tmp/agent.err"
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
                "llm_history.txt": "/tmp/llm_history.txt",
                "chat_history.md": "/work/.aider.chat.history.md",
            },
        )
