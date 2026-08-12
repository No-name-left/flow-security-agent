from __future__ import annotations

import importlib.util
from pathlib import Path


def test_teacher_v2_runner_is_explicitly_gated_by_mode() -> None:
    path = Path("tools/run_teacher_v2.py")
    spec = importlib.util.spec_from_file_location("teacher_v2_runner", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.DEFAULT_ROOT.name == "teacher_v2_observable_dataset_v3"
