import subprocess
from pathlib import Path

import yaml
from pydantic import BaseModel

REPO_ROOT = Path(__file__).parents[1]


class RepoEntry(BaseModel):
    url: str
    sha: str
    language: str
    install: str
    test_base: str
    test_style: str = "pytest"
    default_p2p: list[str] = []


def load_registry() -> dict[str, RepoEntry]:
    raw = yaml.safe_load((REPO_ROOT / "images" / "registry.yaml").read_text())
    return {k: RepoEntry(**v) for k, v in raw.items()}


def image_tag(key: str, entry: RepoEntry) -> str:
    return f"repogym/{key}:{entry.sha[:12]}"


def build_image(key: str, quiet: bool = False) -> str:
    entry = load_registry()[key]
    tag = image_tag(key, entry)
    dockerfile = REPO_ROOT / "images" / f"{entry.language}.Dockerfile"
    cmd = [
        "docker", "build", "-f", str(dockerfile), "-t", tag,
        "--build-arg", f"REPO_URL={entry.url}",
        "--build-arg", f"REPO_SHA={entry.sha}",
        "--build-arg", f"INSTALL_CMD={entry.install}",
        str(REPO_ROOT / "images"),
    ]
    r = subprocess.run(cmd, capture_output=not quiet, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"image build failed for {key}: {(r.stderr or '')[-3000:]}")
    return tag
