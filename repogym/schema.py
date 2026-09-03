from pathlib import Path

import yaml
from pydantic import BaseModel, PrivateAttr

CATEGORIES = {
    "bug_fix", "feature", "refactor", "test_gen", "dep_upgrade",
    "api_migration", "perf", "debugging", "navigation", "multi_file",
}
LEVELS = {"L1", "L2", "L3", "L4"}
SOURCES = {"mined", "handcrafted", "mutated"}


class HiddenTests(BaseModel):
    patch: str
    fail_to_pass: list[str]
    pass_to_pass: list[str] = []


class Oracle(BaseModel):
    patch: str


class Runtime(BaseModel):
    profile: str
    image: str
    test_cmd: str = "pytest -q"


class Timeouts(BaseModel):
    agent_s: int = 1800
    eval_s: int = 600


class TaskSpec(BaseModel):
    id: str
    repo: str
    base_commit: str
    language: str
    category: str
    level: str
    source: str
    prompt: str
    visible_tests: list[str] = []
    mutation_patch: str | None = None
    hidden_tests: HiddenTests
    oracle: Oracle | None = None
    runtime: Runtime
    timeouts: Timeouts = Timeouts()
    security_probes: list[str] = []

    _dir: Path = PrivateAttr()

    @classmethod
    def load(cls, task_dir: Path) -> "TaskSpec":
        spec = cls(**yaml.safe_load((task_dir / "task.yaml").read_text()))
        assert spec.category in CATEGORIES, f"bad category {spec.category}"
        assert spec.level in LEVELS, f"bad level {spec.level}"
        assert spec.source in SOURCES, f"bad source {spec.source}"
        spec._dir = task_dir
        return spec

    @property
    def dir(self) -> Path:
        return self._dir

    def patch_path(self, name: str) -> Path:
        p = self._dir / name
        assert p.exists(), f"missing patch file {p}"
        return p
