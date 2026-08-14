from __future__ import annotations

import json

import pytest

from flowsec.training.contracts import (
    EvidenceDomain,
    EvidenceEnvelope,
    EvidenceTrustV1,
)
from flowsec.training.model_a_evaluation import (
    classification_metrics,
    evidence_metrics_flat,
    evidence_reference_from_eligibility,
    parse_evidence_output,
    supported_classification_metrics,
)


def _evidence(*, knowledge: bool = False) -> tuple[EvidenceEnvelope, ...]:
    return (
        EvidenceEnvelope(
            evidence_id="ev_basic_metadata_12345678",
            evidence_type="basic_metadata",
            domain=(EvidenceDomain.KNOWLEDGE if knowledge else EvidenceDomain.OBSERVATION),
            trust=(
                EvidenceTrustV1.UNTRUSTED_KNOWLEDGE
                if knowledge
                else EvidenceTrustV1.TRUSTED_OBSERVATION
            ),
            content={"packet_count": 8},
            provenance="unit_test",
        ),
    )


def test_classification_metrics_penalize_invalid_predictions() -> None:
    metrics = classification_metrics([0, 1, 1], [0, 1, -1], ("A", "B"))

    assert metrics["accuracy"] == pytest.approx(2 / 3)
    assert metrics["invalid_prediction_count"] == 1
    assert metrics["per_class"]["B"]["recall"] == pytest.approx(0.5)


def test_supported_subset_metrics_do_not_average_absent_classes() -> None:
    metrics = supported_classification_metrics([2, 2], [2, 2], ("A", "B", "C"))

    assert metrics["macro_f1"] == 1.0
    assert metrics["class_order"] == ["C"]
    assert metrics["macro_scope"] == "classes_with_subset_support"


def test_evidence_output_requires_strict_v2_schema_and_tracks_grounding() -> None:
    state, grounding = parse_evidence_output(
        json.dumps(
            {
                "behavior_summary": "Eight visible packets form one bounded session.",
                "supporting_evidence": [
                    {
                        "evidence_id": "ev_basic_metadata_12345678",
                        "claim": "Eight packets are visible.",
                    }
                ],
                "missing_evidence": [],
                "evidence_sufficient": True,
                "primary_gap": None,
                "gap_type": "NONE",
                "recoverability": "ALREADY_SUFFICIENT",
            }
        ),
        _evidence(),
    )

    assert state.evidence_sufficient is True
    assert grounding["severe_hallucination_count"] == 0


def test_knowledge_citation_is_counted_as_severe_hallucination() -> None:
    _state, grounding = parse_evidence_output(
        json.dumps(
            {
                "behavior_summary": "One generic fact is visible.",
                "supporting_evidence": [
                    {
                        "evidence_id": "ev_basic_metadata_12345678",
                        "claim": "The fact proves observed behavior.",
                    }
                ],
                "missing_evidence": ["TEMPORAL"],
                "evidence_sufficient": False,
                "primary_gap": "TEMPORAL",
                "gap_type": "OBSERVATIONAL",
                "recoverability": "RECOVERABLE_WITH_AVAILABLE_TOOLS",
            }
        ),
        _evidence(knowledge=True),
    )

    assert grounding["knowledge_cited_as_observation_count"] == 1
    assert grounding["severe_hallucination_count"] == 1


def test_invalid_evidence_output_cannot_receive_default_credit() -> None:
    metrics = evidence_metrics_flat(
        [
            {
                "schema_valid": False,
                "target_basic_sufficient": True,
                "target_missing_evidence": [],
                "severe_hallucination_count": 0,
            },
            {
                "schema_valid": False,
                "target_basic_sufficient": False,
                "target_missing_evidence": ["TEMPORAL"],
                "severe_hallucination_count": 0,
            },
        ]
    )

    assert metrics["schema_valid_rate"] == 0.0
    assert metrics["sufficiency"]["accuracy"] == 0.0
    assert metrics["missing_evidence"]["exact_match"] == 0.0


def test_eligibility_reference_is_closed_and_pre_model() -> None:
    reference = evidence_reference_from_eligibility(
        {
            "basic_sufficient": False,
            "supporting_evidence_families_json": '["TEMPORAL", "APPLICATION"]',
        }
    )

    assert reference["basic_sufficient"] is False
    assert reference["missing_evidence"] == ["APPLICATION", "TEMPORAL"]
    assert "pre-model" in reference["reference_source"]

    with pytest.raises(ValueError, match="unsupported family"):
        evidence_reference_from_eligibility(
            {
                "basic_sufficient": False,
                "supporting_evidence_families_json": '["FUTURE"]',
            }
        )
