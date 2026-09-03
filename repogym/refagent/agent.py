import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

SYSTEM = """You are a software engineer fixing a bug in a repository. You will get the \
task description and selected repository context. Respond with a unified diff (git apply \
format, paths relative to repo root) inside a ```diff fence, and nothing else. If test \
output from a previous attempt is included, use it to refine the fix."""

TURN_TEMPLATE = """## Task
{prompt}

## Repository context
{context}
{feedback}
Produce the unified diff now."""


class ContextProvider(Protocol):
    name: str

    def build(self, root: Path, prompt: str, budget_tokens: int) -> str: ...


def extract_diff(reply: str) -> str | None:
    m = re.search(r"```diff\n(.*?)```", reply, re.DOTALL)
    if m:
        return m.group(1)
    return reply if reply.lstrip().startswith(("diff --git", "--- ")) else None


def run_refagent(root: Path, prompt: str, provider: ContextProvider,
                 llm: Callable[[str, str], str], test_cmd: str | None = None,
                 budget_tokens: int = 30_000, max_rounds: int = 3) -> dict:
    context = provider.build(root, prompt, budget_tokens)
    feedback = ""
    trace: list[dict] = []

    for round_n in range(1, max_rounds + 1):
        turn = TURN_TEMPLATE.format(prompt=prompt.strip(), context=context, feedback=feedback)
        reply = llm(SYSTEM, turn)
        diff = extract_diff(reply)
        step = {"round": round_n, "context_chars": len(context),
                "reply_chars": len(reply), "applied": False}
        trace.append(step)
        if not diff:
            feedback = "\n## Previous attempt\nYour reply contained no usable diff. Try again.\n"
            continue

        r = subprocess.run(["git", "apply", "--whitespace=nowarn"], input=diff,
                           cwd=root, capture_output=True, text=True)
        if r.returncode != 0:
            feedback = f"\n## Previous attempt\nDiff failed to apply:\n{r.stderr[-800:]}\n"
            continue
        step["applied"] = True

        if not test_cmd:
            return {"rounds": round_n, "trace": trace, "done": True}
        t = subprocess.run(test_cmd, shell=True, cwd=root, capture_output=True,
                           text=True, timeout=600)
        step["tests_rc"] = t.returncode
        if t.returncode == 0:
            return {"rounds": round_n, "trace": trace, "done": True}
        # revert and retry with the failure output as feedback
        subprocess.run(["git", "checkout", "--", "."], cwd=root, capture_output=True)
        feedback = ("\n## Previous attempt\nDiff applied but tests failed:\n"
                    f"{(t.stdout + t.stderr)[-1500:]}\n")

    return {"rounds": max_rounds, "trace": trace, "done": False}
