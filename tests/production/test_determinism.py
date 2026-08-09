from __future__ import annotations

import json
from pathlib import Path

from flowsec.production.determinism import CORE_MANIFEST_NAMES, compare_runs


def _write_result(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "asset_logical_hashes": {
                    "sample_id_index": "stable",
                    "canonical_sessions": "canonical",
                }
            }
        ),
        encoding="utf-8",
    )


def _write_manifests(root: Path) -> None:
    root.mkdir()
    for name in CORE_MANIFEST_NAMES:
        (root / name).write_text(json.dumps({"name": name}), encoding="utf-8")


def test_determinism_includes_core_manifests(tmp_path: Path) -> None:
    results = [tmp_path / name for name in ("a.json", "b.json", "resume.json")]
    roots = [tmp_path / name for name in ("a", "b", "resume")]
    for path in results:
        _write_result(path)
    for root in roots:
        _write_manifests(root)
    passed = compare_runs(
        clean_a=results[0],
        clean_b=results[1],
        resumed=results[2],
        output=tmp_path / "passed.json",
        clean_a_manifests=roots[0],
        clean_b_manifests=roots[1],
        resumed_manifests=roots[2],
    )
    assert passed["DETERMINISM_AUDIT_OK"] is True
    assert passed["core_manifest_clean_double_equal"] is True

    changed = roots[1] / "edge_support_query_manifest.json"
    changed.write_text(json.dumps({"changed": True}), encoding="utf-8")
    failed = compare_runs(
        clean_a=results[0],
        clean_b=results[1],
        resumed=results[2],
        output=tmp_path / "failed.json",
        clean_a_manifests=roots[0],
        clean_b_manifests=roots[1],
        resumed_manifests=roots[2],
    )
    assert failed["DETERMINISM_AUDIT_OK"] is False
    assert failed["core_manifest_clean_double_equal"] is False
