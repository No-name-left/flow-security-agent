from __future__ import annotations

import importlib.util
from pathlib import Path

from flowsec.training.contracts import EvidenceStageV2, EvidenceTrustV1


def _load_builder():
    path = Path("tools/build_teacher_v2_snapshots.py")
    spec = importlib.util.spec_from_file_location("teacher_v2_snapshot_builder", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BUILDER = _load_builder()
SAMPLE_ID = "fs1_" + "a" * 40


def test_basic_snapshot_separates_untrusted_payload_from_metadata() -> None:
    view = {
        "schema_version": "BASIC_EVIDENCE_V2",
        "session_summary": {"duration": 1.0},
        "first_eight_packets": [{"packet_index": 1}],
        "cheap_application_metadata": {"request_count": 0},
        "packet_aligned_payload": [
            {"packet_index": 1, "payload_present": False, "sanitized_payload": None}
        ],
        "capabilities": {"TEMPORAL": True},
    }
    evidence = BUILDER._basic_envelopes(SAMPLE_ID, view)
    assert len(evidence) == 2
    assert evidence[0].trust is EvidenceTrustV1.TRUSTED_OBSERVATION
    assert evidence[1].trust is EvidenceTrustV1.UNTRUSTED_PAYLOAD
    assert "capabilities" not in evidence[0].content


def test_snapshot_contract_has_one_basic_primary_and_hidden_capabilities() -> None:
    evidence = (
        BUILDER._envelope(SAMPLE_ID, "basic_metadata", {"duration": 1.0}),
    )
    snapshot = BUILDER._snapshot(
        sample_id=SAMPLE_ID,
        fine_label="Normal",
        coarse_label="Normal",
        stage=EvidenceStageV2.BASIC,
        primary=True,
        evidence=evidence,
        acquired=set(),
        dataset_digest="b" * 64,
    )
    assert snapshot.classification_supervision_valid is True
    assert snapshot.stage_type is EvidenceStageV2.BASIC
    assert set(snapshot.available_capabilities) == set(BUILDER.ALL_CAPABILITIES)
