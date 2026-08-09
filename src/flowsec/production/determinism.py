from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flowsec.production.schema import content_hash
from flowsec.production.storage import write_json


CORE_MANIFEST_NAMES = (
    "canonical_schema_v1.json",
    "edge_label_schema.json",
    "iot23_label_schema.json",
    "edge_split_manifest.json",
    "iot23_split_manifest.json",
    "edge_known_unknown_presets.json",
    "iot23_known_unknown_presets.json",
    "edge_support_query_manifest.json",
    "iot23_support_query_manifest.json",
    "training_asset_manifest_edge.json",
    "training_asset_manifest_iot23.json",
    "model_feature_whitelist.json",
    "prohibited_model_fields.json",
    "anomaly_policy.json",
    "evaluation_clean_sensitivity_manifest.json",
    "class_role_support_gate.json",
)


def _manifest_hashes(root: Path) -> dict[str, str]:
    return {
        name: content_hash(json.loads((root / name).read_text(encoding="utf-8")))
        for name in CORE_MANIFEST_NAMES
    }


def compare_runs(
    *,
    clean_a: Path,
    clean_b: Path,
    resumed: Path,
    output: Path,
    clean_a_manifests: Path | None = None,
    clean_b_manifests: Path | None = None,
    resumed_manifests: Path | None = None,
) -> dict[str, Any]:
    values = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (clean_a, clean_b, resumed)
    ]
    hashes_a, hashes_b, hashes_resume = [
        value["asset_logical_hashes"] for value in values
    ]
    assets = sorted(set(hashes_a) | set(hashes_b) | set(hashes_resume))
    comparisons = {
        asset: {
            "clean_a": hashes_a.get(asset),
            "clean_b": hashes_b.get(asset),
            "resumed": hashes_resume.get(asset),
            "clean_double_equal": hashes_a.get(asset) == hashes_b.get(asset),
            "clean_resume_equal": hashes_a.get(asset) == hashes_resume.get(asset),
        }
        for asset in assets
    }
    clean_ok = all(item["clean_double_equal"] for item in comparisons.values())
    resume_ok = all(item["clean_resume_equal"] for item in comparisons.values())
    sample_ids_stable = comparisons.get("sample_id_index", {}).get(
        "clean_double_equal", False
    )
    manifest_roots = (clean_a_manifests, clean_b_manifests, resumed_manifests)
    if any(root is not None for root in manifest_roots) and not all(
        root is not None for root in manifest_roots
    ):
        raise ValueError("provide all three manifest roots or none")
    manifest_comparisons: dict[str, Any] = {}
    manifest_clean_ok = manifest_resume_ok = True
    if all(root is not None for root in manifest_roots):
        manifest_a, manifest_b, manifest_resume = [
            _manifest_hashes(root) for root in manifest_roots if root is not None
        ]
        manifest_comparisons = {
            name: {
                "clean_a": manifest_a[name],
                "clean_b": manifest_b[name],
                "resumed": manifest_resume[name],
                "clean_double_equal": manifest_a[name] == manifest_b[name],
                "clean_resume_equal": manifest_a[name] == manifest_resume[name],
            }
            for name in CORE_MANIFEST_NAMES
        }
        manifest_clean_ok = all(
            item["clean_double_equal"] for item in manifest_comparisons.values()
        )
        manifest_resume_ok = all(
            item["clean_resume_equal"] for item in manifest_comparisons.values()
        )
    complete = (
        clean_ok
        and resume_ok
        and sample_ids_stable
        and manifest_clean_ok
        and manifest_resume_ok
    )
    result = {
        "status": "PASS" if complete else "FAIL",
        "DETERMINISM_AUDIT_OK": complete,
        "scope": {
            "mode": "sample",
            "edge_capture": "Attack_OS_Fingerprinting",
            "iot23_scenario": "CTU-IoT-Malware-Capture-8-1",
            "sample_sessions_per_source": 500,
        },
        "comparison_basis": "canonical logical row and core JSON content hashes; Parquet metadata and absolute output paths ignored",
        "clean_double_run_equal": clean_ok,
        "interrupted_resume_equal_to_clean": resume_ok,
        "stable_sample_id_index_equal": sample_ids_stable,
        "core_manifest_clean_double_equal": manifest_clean_ok,
        "core_manifest_resume_equal_to_clean": manifest_resume_ok,
        "interruption_point": "after first completed capture checkpoint",
        "comparisons": comparisons,
        "core_manifest_comparisons": manifest_comparisons,
    }
    write_json(output, result)
    return result
