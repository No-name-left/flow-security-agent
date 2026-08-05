from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "reports" / "data_feasibility_gate_20260806"


def test_synthetic_canonical_session_fixture_matches_gate_schema() -> None:
    fixture = json.loads(
        (ROOT / "tests" / "fixtures" / "canonical_session_record.example.json").read_text(
            encoding="utf-8"
        )
    )
    schema = json.loads((GATE / "adapter_schema.json").read_text(encoding="utf-8"))

    assert schema["name"] == "CanonicalSessionRecord"
    assert set(schema["required_fields"]) <= set(fixture)
    assert len(fixture["packet_sequence"]) <= schema["packet_sequence_max"]


def test_gate_manifests_reference_existing_small_artifacts_or_ignored_outputs() -> None:
    checksum_manifest = json.loads((GATE / "checksum_manifest.json").read_text(encoding="utf-8"))
    reproducible_large_outputs = {
        "edge_smoke.jsonl",
        "iot23_smoke.jsonl",
        "qwen_input_samples.jsonl",
        "lightweight_model_predictions.csv",
    }

    missing = {
        item["path"]
        for item in checksum_manifest["files"]
        if not (GATE / item["path"]).exists() and item["path"] not in reproducible_large_outputs
    }
    assert missing == set()
