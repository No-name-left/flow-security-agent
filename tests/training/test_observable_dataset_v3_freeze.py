from __future__ import annotations

import importlib.util
from collections import Counter
from pathlib import Path


def _load_freezer():
    path = Path("tools/freeze_observable_dataset_v3.py")
    spec = importlib.util.spec_from_file_location("observable_dataset_v3_freezer", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FREEZER = _load_freezer()


def test_diversity_selection_is_deterministic_near_first_and_exact_bounded() -> None:
    rows = []
    for index in range(60):
        rows.append(
            {
                "sample_id": f"sample-{index:03d}",
                "exact_signature": f"exact-{index // 10}",
                "near_signature": f"near-{index % 15}",
            }
        )
    first = FREEZER.select_diversity_aware(
        rows, budget=24, maximum_per_exact=4, seed=7
    )
    second = FREEZER.select_diversity_aware(
        list(reversed(rows)), budget=24, maximum_per_exact=4, seed=7
    )
    assert first == second
    assert len(first) == 24
    assert max(Counter(row["exact_signature"] for row in first).values()) <= 4
    # The exact-multiplicity safety cap takes precedence if one near group's
    # stable representative belongs to an already saturated exact group.
    assert len({row["near_signature"] for row in first}) >= 14


def test_frozen_roles_and_class_count_are_explicit() -> None:
    assert len(FREEZER.FINAL_MAIN_CLASSES) == 6
    assert "MITM" not in FREEZER.FINAL_MAIN_CLASSES
    assert "Port_Scanning" not in FREEZER.FINAL_MAIN_CLASSES
    assert set(FREEZER.EXCLUDED_CANDIDATE_ROLES) == {"MITM", "Port_Scanning"}
