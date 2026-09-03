from pathlib import Path

from repogym.images import RepoEntry
from repogym.sandbox import Sandbox, SandboxError

DIFF_EXCLUDES = "':(exclude).venv' ':(exclude)*.egg-info' ':(exclude)uv.lock'"


def setup_workspace(sb: Sandbox, entry: RepoEntry) -> None:
    rc, out = sb.exec("rm -rf /work && cp -a /repo /work && rm -rf /work/.venv", workdir="/")
    if rc != 0:
        raise SandboxError(f"workspace copy failed: {out[-1000:]}")
    # keep venv and build junk out of git add -A no matter the repo's gitignore
    sb.exec("printf '.venv/\\n*.egg-info/\\nuv.lock\\n' >> /work/.git/info/exclude")
    rc, out = sb.exec(entry.install, timeout=900)
    if rc != 0:
        raise SandboxError(f"install failed: {out[-2000:]}")


def apply_patch(sb: Sandbox, host_patch: Path, label: str) -> tuple[bool, str]:
    dst = f"/tmp/{label}.patch"
    sb.copy_in(host_patch, dst)
    rc, out = sb.exec(f"git apply --whitespace=nowarn {dst}")
    return rc == 0, out


def extract_diff(sb: Sandbox, base_sha: str) -> str:
    # stage everything so new files show up in the diff
    sb.exec(f"git add -A -- . {DIFF_EXCLUDES}")
    rc, out = sb.exec(f"git diff {base_sha} -- . {DIFF_EXCLUDES}", timeout=120)
    if rc != 0:
        raise SandboxError(f"diff extraction failed: {out[-1000:]}")
    return out
