import subprocess
import uuid
from pathlib import Path


class SandboxError(Exception):
    pass


class Sandbox:
    def __init__(self, image: str, cpus: float = 2.0, memory: str = "6g", network: str = "bridge"):
        self.image = image
        self.cpus = cpus
        self.memory = memory
        self.network = network
        self.cid: str | None = None

    def _docker(self, *args: str, timeout: int = 120) -> subprocess.CompletedProcess:
        return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)

    def start(self) -> "Sandbox":
        name = f"repogym-{uuid.uuid4().hex[:10]}"
        r = self._docker(
            "run", "-d", "--rm", "--name", name,
            f"--cpus={self.cpus}", f"--memory={self.memory}", f"--network={self.network}",
            self.image, "sleep", "infinity",
        )
        if r.returncode != 0:
            raise SandboxError(f"container start failed: {r.stderr[-2000:]}")
        self.cid = r.stdout.strip()
        return self

    def exec(self, cmd: str, workdir: str = "/work", env: dict[str, str] | None = None,
             timeout: int = 600) -> tuple[int, str]:
        assert self.cid, "sandbox not started"
        args = ["exec", "-w", workdir]
        for k, v in (env or {}).items():
            args += ["-e", f"{k}={v}"]
        args += [self.cid, "bash", "-c", cmd]
        try:
            p = self._docker(*args, timeout=timeout)
        except subprocess.TimeoutExpired:
            return 124, f"exec timed out after {timeout}s: {cmd[:200]}"
        return p.returncode, (p.stdout or "") + (p.stderr or "")

    def copy_in(self, src: Path, dst: str) -> None:
        r = self._docker("cp", str(src), f"{self.cid}:{dst}")
        if r.returncode != 0:
            raise SandboxError(f"copy_in failed: {r.stderr[-500:]}")

    def copy_out(self, src: str, dst: Path) -> bool:
        dst.parent.mkdir(parents=True, exist_ok=True)
        return self._docker("cp", f"{self.cid}:{src}", str(dst)).returncode == 0

    def stop(self) -> None:
        if self.cid:
            self._docker("kill", self.cid)
            self.cid = None

    def __enter__(self) -> "Sandbox":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()
