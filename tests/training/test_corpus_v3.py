from __future__ import annotations

from flowsec.training.contracts import EvidenceStateV2, GapDomainV2, RecoverabilityV2
from flowsec.training.corpus_v3 import _select_diverse_validation, basic_v2_envelopes


def _view() -> dict:
    return {
        "schema_version": "BASIC_EVIDENCE_V2",
        "session_summary": {"duration": 1.0},
        "first_eight_packets": [{"packet_index": 1, "length": 60}],
        "cheap_application_metadata": {"protocol": "http"},
        "packet_aligned_payload": [
            {
                "session_id": "not_projected",
                "packet_index": 1,
                "direction": "initiator_to_responder",
                "relative_time": 0.0,
                "protocol": "TCP",
                "payload_present": False,
                "payload_length": 0,
                "sanitized_payload": "",
                "sanitization_version": "SANITIZED_PAYLOAD_V2",
            }
        ],
    }


def test_basic_v2_envelopes_keep_payload_packet_alignment() -> None:
    sample_id = "fs1_" + "a" * 40
    envelopes = basic_v2_envelopes(sample_id, _view())
    payload = envelopes[1].content["packet_aligned_payload"]
    assert payload[0]["packet_index"] == 1
    assert envelopes[1].trust.value == "UNTRUSTED_PAYLOAD"
    assert sample_id not in str([item.model_dump(mode="json") for item in envelopes])


def test_validation_selection_round_robins_exact_groups() -> None:
    rows = [
        {"session_id": f"fs1_{index:040x}", "exact_signature": group}
        for index, group in enumerate(("a", "a", "a", "b", "c"))
    ]
    selected = _select_diverse_validation(rows, per_class_limit=3)
    assert {item["exact_signature"] for item in selected} == {"a", "b", "c"}


def test_evidence_state_v2_target_remains_class_free() -> None:
    state = EvidenceStateV2(
        evidence_sufficient=True,
        supporting_evidence=(),
        missing_evidence=(),
        primary_gap=None,
        gap_type=GapDomainV2.NONE,
        recoverability=RecoverabilityV2.ALREADY_SUFFICIENT,
    )
    assert "fine_label" not in state.model_dump(mode="json")
