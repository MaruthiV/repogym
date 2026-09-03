from pathlib import Path

from repogym.schema import TaskSpec

TASKS = Path(__file__).parents[1] / "tasks"


def test_all_task_specs_load():
    task_dirs = [d for d in TASKS.iterdir() if (d / "task.yaml").exists()]
    assert task_dirs, "no tasks found"
    for d in task_dirs:
        spec = TaskSpec.load(d)
        assert spec.id == d.name
        assert spec.hidden_tests.fail_to_pass
        assert spec.hidden_tests.pass_to_pass
        spec.patch_path(spec.hidden_tests.patch)
        if spec.oracle:
            spec.patch_path(spec.oracle.patch)
        if spec.mutation_patch:
            spec.patch_path(spec.mutation_patch)
