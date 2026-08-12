from __future__ import annotations

import pytest

from flowsec.training.evidence_salvage import (
    application_semantics,
    choose_failure_mode,
    class_relevant_signal,
    packet_bucket,
    payload_semantics,
    temporal_semantics,
    validate_assessment,
)


def test_packet_buckets_are_one_based_and_frozen() -> None:
    assert packet_bucket(1) == "first_8"
    assert packet_bucket(8) == "first_8"
    assert packet_bucket(9) == "packet_9_16"
    assert packet_bucket(16) == "packet_9_16"
    assert packet_bucket(17) == "after_16"
    with pytest.raises(ValueError):
        packet_bucket(0)


def test_payload_semantics_are_label_free_and_sanitized() -> None:
    features = payload_semantics(
        ["POST /<SEG> HTTP/1.1\nContent-Type: multipart/form-data\n\n<CREDENTIAL_PARAM>=<TEXT>"]
    )
    assert "http_request" in features
    assert "file_transfer_metadata" in features
    assert "credential_structure" in features
    assert all("password" not in value for value in features)


def test_application_semantics_extracts_protocol_shapes() -> None:
    features = application_semantics(
        {
            "protocol": "http",
            "observations": [
                {"kind": "http", "method": "PUT", "content_type": "multipart/form-data"},
                {"kind": "http", "method": "OPTIONS", "status": 403},
            ],
        }
    )
    assert {"protocol:http", "http", "upload_method", "file_transfer_metadata"} <= features
    assert {"probe_method", "authentication_response"} <= features


def test_generic_exploit_shapes_are_detected_without_class_tokens() -> None:
    payload = payload_semantics(("<!DOCTYPE x [<!ENTITY y SYSTEM '/etc/passwd'>]>",))
    application = application_semantics(
        {"protocol": "http", "observations": [{"kind": "http", "method": "PROPFIND"}]}
    )
    assert "exploit_structure" in payload
    assert "probe_method" in application
    assert class_relevant_signal(
        "Vulnerability_scanner", payload=payload, application=application
    )


def test_temporal_signal_requires_joint_behavior_for_ddos_tcp() -> None:
    features = temporal_semantics(
        {
            "prior_session_count": 5000,
            "same_destination_distinct_source_count": 4990,
            "incomplete_handshake_ratio": 0.99,
            "repeated_pair_count": 0,
            "inter_session_gap": 0.01,
        },
        handshake_state="INCOMPLETE_HANDSHAKE",
    )
    assert class_relevant_signal(
        "DDoS_TCP",
        temporal=features,
        session={"high_syn_ratio"},
    )
    assert not class_relevant_signal(
        "DDoS_TCP",
        temporal={"session_burst"},
        session={"high_syn_ratio"},
    )


def test_mitm_requires_observed_mapping_anomaly() -> None:
    assert class_relevant_signal("MITM", relation={"arp_mapping_conflict"})
    assert not class_relevant_signal("MITM", application={"protocol:dns"})


def test_failure_attribution_prefers_observed_layer_loss() -> None:
    assert choose_failure_mode(
        current_support=False,
        full_support=True,
        raw_signal_present=True,
        session_retains_signal=False,
        payload_capability_available=False,
        payload_visible_current=False,
        application_available=False,
        application_visible_current=False,
        temporal_gap=True,
        relation_gap=False,
    ) == "SESSIONIZATION_LOSS"
    assert choose_failure_mode(
        current_support=False,
        full_support=True,
        raw_signal_present=True,
        session_retains_signal=True,
        payload_capability_available=True,
        payload_visible_current=False,
        application_available=False,
        application_visible_current=False,
        temporal_gap=False,
        relation_gap=False,
    ) == "EVIDENCE_SELECTION_LOSS"


def test_assessment_enum_guard_rejects_unregistered_values() -> None:
    validate_assessment(
        {
            "failure_mode": "TEMPORAL_FEATURE_GAP",
            "salvageability": "SALVAGEABLE_WITH_RICHER_EVIDENCE",
        }
    )
    with pytest.raises(ValueError):
        validate_assessment({"failure_mode": "GUESS", "salvageability": "INCONCLUSIVE"})
