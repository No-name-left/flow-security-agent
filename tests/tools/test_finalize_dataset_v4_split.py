import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from tools.finalize_dataset_v4_split import (
    FINE_TO_CANONICAL,
    MODEL_VISIBLE_FIELDS,
    PARTITION_CODES,
    PilotMeta,
    ROW_SCHEMA,
    activity_group_digest,
    canonical_row_digest,
    leak_keys,
    materialize_semantic_requests,
    materialize_strict_history,
    source_row_id,
    split_for_group,
    teacher_payload,
    validate_final_acceptance,
)


def test_taxonomy_reuses_frozen_nf3_mapping() -> None:
    assert FINE_TO_CANONICAL["password"] == "Credential"
    assert FINE_TO_CANONICAL["scanning"] == "Recon_Scanning"
    assert FINE_TO_CANONICAL["injection"] == "Web_Injection"
    assert FINE_TO_CANONICAL["xss"] == "Web_Injection"
    assert "mitm" not in FINE_TO_CANONICAL
    assert "ransomware" not in FINE_TO_CANONICAL


def test_source_row_id_is_shuffle_independent_and_artifact_bound() -> None:
    row = [str(index).encode() for index in range(55)]
    digest = canonical_row_digest(row)
    first = source_row_id(17, digest)
    assert first == source_row_id(17, digest)
    assert first != source_row_id(18, digest)
    assert first != source_row_id(17, hashlib.sha256(b"other").digest())


def test_activity_group_is_unordered_temporal_and_split_stable() -> None:
    group = activity_group_digest(300_001, b"10.0.0.1", b"10.0.0.2")
    assert group == activity_group_digest(599_999, b"10.0.0.2", b"10.0.0.1")
    assert group != activity_group_digest(600_000, b"10.0.0.1", b"10.0.0.2")
    assert split_for_group(group, 20260816) == split_for_group(group, 20260816)


def _row(**overrides):
    values = {
        "source_row_index": 0,
        "source_row_id": b"i" * 32,
        "canonical_row_digest": b"d" * 32,
        "source_fine_label": "Benign",
        "canonical_label": "Benign",
        "flow_start_ms": 0,
        "flow_end_ms": 0,
        "src_code": 1,
        "dst_code": 2,
        "src_port": 1,
        "dst_port": 80,
        "protocol": 6,
        "in_bytes": 10,
        "out_bytes": 10,
        "in_pkts": 1,
        "out_pkts": 1,
        "activity_group_digest": b"g" * 16,
        "partition_code": PARTITION_CODES["TRAIN"],
        "oof_fold": 0,
        "critical_valid": True,
        "target_eligible": True,
    }
    values.update(overrides)
    return values


def test_history_is_same_split_and_strictly_past_only(tmp_path) -> None:
    rows = [
        _row(source_row_index=0, flow_start_ms=800, flow_end_ms=900),
        _row(
            source_row_index=1,
            source_row_id=b"j" * 32,
            flow_start_ms=850,
            flow_end_ms=950,
            partition_code=PARTITION_CODES["VALIDATION"],
        ),
        _row(
            source_row_index=2,
            source_row_id=b"k" * 32,
            flow_start_ms=1_000,
            flow_end_ms=1_100,
        ),
        _row(
            source_row_index=3,
            source_row_id=b"l" * 32,
            flow_start_ms=900,
            flow_end_ms=1_000,
        ),
    ]
    table = pa.Table.from_pylist(rows, schema=ROW_SCHEMA)
    path = tmp_path / "rows" / "manifest.parquet"
    path.parent.mkdir()
    pq.write_table(table, path)
    target = rows[2]
    meta = {
        2: PilotMeta(
            source_row_index=2,
            source_row_id=target["source_row_id"],
            canonical_row_digest=target["canonical_row_digest"],
            source_fine_label="Benign",
            canonical_label="Benign",
            flow_start_ms=1_000,
            flow_end_ms=1_100,
            src_code=1,
            dst_code=2,
            dst_port=80,
            group_digest=b"g" * 16,
            partition_code=PARTITION_CODES["TRAIN"],
            oof_fold=0,
            critical_valid=True,
        )
    }
    history, names = materialize_strict_history(path, meta, [2])
    assert names[0] == "source_flow_count_10s"
    assert history[0, 0] == 1.0
    assert history[0, -1] == 100.0


def test_teacher_projection_excludes_offline_sampling_truth() -> None:
    candidate = {
        "source_row_id": "opaque",
        "class_order": ["Benign", "DDoS"],
        "basic_probabilities": [0.25, 0.75],
        "basic_prediction": "DDoS",
        "class_map_version": "KNOWN_MAP_V1",
    }
    payload = teacher_payload(
        candidate=candidate,
        basic_values={
            name: None if name == "DNS_QUERY_ID" else 0.0
            for name in MODEL_VISIBLE_FIELDS
        },
    )
    assert leak_keys(payload) == []
    assert payload["current_evidence_card"]["BASIC"]["missing_fields"] == [
        "DNS_QUERY_ID"
    ]
    payload["offline"] = {"recoverable": True}
    assert leak_keys(payload) == ["offline.recoverable"]


def test_semantic_reference_materializes_exact_frozen_coverage(tmp_path) -> None:
    repo_root = tmp_path
    config_root = repo_root / "configs" / "dataset_v4"
    config_root.mkdir(parents=True)
    source = Path(__file__).parents[2] / (
        "configs/dataset_v4/semantic_admissibility_reference_v1_design.json"
    )
    config_root.joinpath(source.name).write_text(source.read_text(encoding="utf-8"))
    manifest = materialize_semantic_requests(repo_root)
    assert manifest["request_n"] == 63
    assert manifest["deepseek_calls"] == 0
    assert manifest["responses_generated"] == 0
    generated = json.loads(
        config_root.joinpath("semantic_reference_v1_request_manifest.json").read_text()
    )
    assert len(generated["requests"]) == 63


def test_tracked_final_manifests_satisfy_fail_closed_acceptance() -> None:
    repo_root = Path(__file__).parents[2]
    split = json.loads(
        repo_root.joinpath(
            "configs/dataset_v4/dataset_v4_split_manifest_v1.json"
        ).read_text()
    )
    rotations = json.loads(
        repo_root.joinpath(
            "configs/dataset_v4/unknown_rotation_manifest_v1.json"
        ).read_text()
    )
    teacher = json.loads(
        repo_root.joinpath(
            "configs/dataset_v4/teacher_cache_v1_sampling_manifest.json"
        ).read_text()
    )
    semantic = json.loads(
        repo_root.joinpath(
            "configs/dataset_v4/semantic_reference_v1_request_manifest.json"
        ).read_text()
    )
    reference = json.loads(
        repo_root.joinpath(
            "reports/dataset_v4/dataset_v4_final_split_report.json"
        ).read_text()
    )["reference_state"]
    validate_final_acceptance(
        split_manifest=split,
        rotation_manifest=rotations,
        reference_audit=reference,
        teacher_manifest=teacher,
        semantic_manifest=semantic,
    )
    teacher["final_test_contamination_n"] = 1
    with pytest.raises(RuntimeError, match="final_test_contamination_n"):
        validate_final_acceptance(
            split_manifest=split,
            rotation_manifest=rotations,
            reference_audit=reference,
            teacher_manifest=teacher,
            semantic_manifest=semantic,
        )
