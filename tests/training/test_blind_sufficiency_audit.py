from __future__ import annotations

import json

import pytest

from flowsec.training.blind_audit import (
    BLIND_CLASSIFIER_PROMPT_VERSION,
    BlindAuditSampleV1,
    audit_prompt_leakage,
    build_blind_classifier_request,
    select_primary_diagnostic_sample,
    validate_blind_output,
    pair_transition_stratum,
    select_pair_diagnostic_sample,
    wilson_interval,
)
from flowsec.training.contracts import (
    EvidenceDomain,
    EvidenceEnvelope,
    EvidenceGapType,
    EvidenceSnapshot,
    EvidenceStateV1,
    EvidenceTrustV1,
    MissingEvidenceV1,
    SFTRecordV1,
    StageType,
)


def _evidence(suffix: str = "1") -> EvidenceEnvelope:
    return EvidenceEnvelope(
        evidence_id="ev_initial_" + suffix * 8,
        evidence_type="initial",
        domain=EvidenceDomain.OBSERVATION,
        trust=EvidenceTrustV1.TRUSTED_OBSERVATION,
        content={
            "packet_sequence": [
                {
                    "direction": "initiator_to_responder",
                    "packet_length": 60,
                    "relative_iat": 0.0,
                    "l4_protocol": "TCP",
                }
            ]
        },
        provenance="model_safe_fixture",
    )


def _record(index: int, label: str, *, sufficient: bool) -> tuple[SFTRecordV1, EvidenceSnapshot]:
    sample_id = "fs1_" + f"{index:040x}"
    state_id = "state_" + f"{index:024x}"
    evidence = (_evidence(f"{index % 10}"),)
    target = EvidenceStateV1(
        behavior_summary="One bounded TCP packet is visible.",
        supporting_evidence=(),
        missing_evidence=(
            ()
            if sufficient
            else (
                MissingEvidenceV1(
                    type=EvidenceGapType.PACKET,
                    description="More packet interaction is material.",
                ),
            )
        ),
        evidence_sufficient=sufficient,
        gap_type=EvidenceGapType.NONE if sufficient else EvidenceGapType.PACKET,
    )
    record = SFTRecordV1(
        sample_id=sample_id,
        evidence_state_id=state_id,
        fine_label=label,
        class_index=0,
        classification_ce_eligible=True,
        state_role="primary",
        serialized_model_input="model-safe fixture",
        evidence_state_target=target,
        stage_type=StageType.INITIAL,
        available_capability_mask=(),
        prompt_version="fixture",
        serialization_version="fixture",
        teacher_annotation_digest="a" * 64,
        teacher_model="fixture",
        teacher_prompt_digest="b" * 64,
        teacher_request_id="fixture-request",
        dataset_digest="c" * 64,
        session_weight=1.0,
    )
    snapshot = EvidenceSnapshot(
        sample_id=sample_id,
        evidence_state_id=state_id,
        fine_label=label,
        coarse_label="fixture",
        split="train",
        ku_role="K_known",
        stage_type=StageType.INITIAL,
        classification_supervision_valid=True,
        available_capabilities=(),
        evidence=evidence,
        source_digest="d" * 64,
    )
    return record, snapshot


def test_blind_request_has_independent_prompt_and_no_backend_or_teacher_fields() -> None:
    evidence = (_evidence(),)
    request = build_blind_classifier_request(
        evidence,
        ("Backdoor", "Normal"),
        provider="deepseek",
        base_url="https://api.deepseek.com",
        model_id="deepseek-v4-flash",
        timeout_seconds=90.0,
    )
    rendered = json.dumps(request.model_dump(mode="json"), sort_keys=True)
    assert request.prompt.prompt_version == BLIND_CLASSIFIER_PROMPT_VERSION
    assert request.request_metadata["backend_role"] == "blind_classifier"
    assert "teacher_prompt" not in rendered.casefold()
    assert "evidence_sufficient" not in rendered
    assert "gap_type" not in rendered
    assert "missing_evidence" not in rendered
    assert "sample_id" not in rendered
    assert "fine_label" not in rendered

    leakage = audit_prompt_leakage(
        request,

        sample_id="fs1_" + "f" * 40,
        dataset_identity="Edge-IIoTset",
        capture_ref_hash="1" * 64,
        source_sha256="2" * 64,
    )
    assert leakage == {key: 0 for key in leakage}

def test_pair_sample_is_same_session_and_tracks_false_to_true() -> None:
    before, _ = _record(100, "Normal", sufficient=False)
    after, _ = _record(100, "Normal", sufficient=True)
    before = before.model_copy(
        update={
            "evidence_state_id": "state_" + f"{101:024x}",
            "state_role": "auxiliary",
            "classification_ce_eligible": False,
        }
    )
    assert pair_transition_stratum(before, after) == "false_to_true"
    selected = select_pair_diagnostic_sample(
        [before, after], quotas={"false_to_true": 1}
    )
    assert len(selected) == 1
    assert selected[0].sample_id == before.sample_id == after.sample_id
    assert selected[0].transition_stratum_backend_only == "false_to_true"

    unrelated, _ = _record(102, "Normal", sufficient=True)
    with pytest.raises(ValueError, match="share one session"):
        pair_transition_stratum(before, unrelated)



def test_blind_output_is_closed_set_distinct_and_evidence_grounded() -> None:
    evidence = (_evidence(),)
    valid = {
        "top1": "Normal",
        "top2": "Backdoor",
        "confidence": "medium",
        "supporting_evidence_ids": [evidence[0].evidence_id],
        "short_basis": "One bounded TCP observation is visible.",
    }
    assert validate_blind_output(
        valid, candidate_labels=("Backdoor", "Normal"), evidence=evidence
    ).top1 == "Normal"
    with pytest.raises(ValueError, match="must differ"):
        validate_blind_output(
            {**valid, "top2": "Normal"},
            candidate_labels=("Backdoor", "Normal"),
            evidence=evidence,
        )
    with pytest.raises(ValueError, match="candidate list"):
        validate_blind_output(
            {**valid, "top1": "Unknown"},
            candidate_labels=("Backdoor", "Normal"),
            evidence=evidence,
        )
    with pytest.raises(ValueError, match="unavailable Evidence"):
        validate_blind_output(
            {**valid, "supporting_evidence_ids": ["ev_missing_12345678"]},
            candidate_labels=("Backdoor", "Normal"),
            evidence=evidence,
        )


def test_diagnostic_sample_is_class_balanced_and_oversamples_no_next() -> None:
    corpus: list[SFTRecordV1] = []
    snapshots: dict[str, EvidenceSnapshot] = {}
    index = 1
    for label in ("Backdoor", "Normal"):
        for sufficient in (False, False, False, True):
            record, snapshot = _record(index, label, sufficient=sufficient)
            corpus.append(record)
            snapshots[snapshot.evidence_state_id] = snapshot
            index += 1
    sample = select_primary_diagnostic_sample(
        corpus,
        snapshots,
        candidate_labels=("Backdoor", "Normal"),
        application_ids=set(),
        payload_ids=set(),
        knowledge_available=False,
        per_class=3,
        sufficient_controls_per_class=1,
        no_next_per_class=1,
    )
    assert all(isinstance(item, BlindAuditSampleV1) for item in sample)
    assert len(sample) == 6
    assert {label: sum(item.fine_label_backend_only == label for item in sample) for label in ("Backdoor", "Normal")} == {
        "Backdoor": 3,
        "Normal": 3,
    }
    assert sum(item.teacher_sufficient_backend_only for item in sample) == 2
    assert sum(item.no_gap_matched_next_action_backend_only for item in sample) == 4


def test_wilson_interval_is_bounded_and_rejects_invalid_counts() -> None:
    low, high = wilson_interval(7, 10)
    assert 0.0 < low < 0.7 < high < 1.0
    with pytest.raises(ValueError, match="invalid"):
        wilson_interval(1, 0)
