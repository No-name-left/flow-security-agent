from __future__ import annotations

import copy
import json

import pytest

from flowsec.training.observable_v3 import (
    TEMPORAL_HORIZONS_SECONDS,
    assess_fine_observation_eligibility,
    build_strict_past_temporal_contexts,
    interval_statistics,
    validate_temporal_context,
)


def _row(
    sample_id: str,
    start: float,
    end: float,
    *,
    split: str = "train",
    capture: str = "capture-a",
    signals: tuple[str, ...] = (),
    packet_count: int = 10,
    byte_count: int = 1_000,
    syn: int = 0,
    synack: int = 0,
    ack: int = 0,
    rst: int = 0,
    requests: int = 0,
    uri_shapes: dict[str, int] | None = None,
    methods: dict[str, int] | None = None,
    relation: str = "relation-a",
) -> dict[str, object]:
    return {
        "sample_id": sample_id,
        "split": split,
        "capture_id_backend_only": capture,
        "timestamp_start": start,
        "timestamp_end": end,
        "raw_initiator_ip": "10.0.0.1",
        "raw_responder_ip": "10.0.0.2",
        "raw_responder_port": 80,
        "communication_pair_hash": relation,
        "l4_protocol": "TCP",
        "packet_count": packet_count,
        "byte_count": byte_count,
        "tcp_syn": syn,
        "tcp_synack": synack,
        "tcp_ack": ack,
        "tcp_rst": rst,
        "request_count": requests,
        "initiator_bytes": 750,
        "responder_bytes": 250,
        "mechanism_signals": signals,
        "uri_shapes_json": json.dumps(uri_shapes or {}),
        "http_methods_json": json.dumps(methods or {}),
    }


def _context_for(
    values: list[dict[str, object]], sample_id: str, horizon: int = 60
) -> dict[str, object]:
    result = next(item for item in values if item["sample_id"] == sample_id)
    return result["contexts"][str(horizon)]  # type: ignore[index,return-value]


def _session(*signals: str, **overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "packet_count": 10,
        "byte_count": 1_000,
        "duration": 1.0,
        "tcp_syn": 0,
        "tcp_synack": 0,
        "tcp_ack": 0,
        "tcp_rst": 0,
        "request_count": 0,
        "initiator_packets": 5,
        "responder_packets": 5,
        "raw_initiator_ip": "10.0.0.1",
        "raw_responder_ip": "10.0.0.2",
        "mechanism_signals": signals,
        "basic_mechanism_signals": signals,
    }
    result.update(overrides)
    return result


def test_interval_statistics_preserves_simultaneous_start_bursts() -> None:
    stats = interval_statistics([1.0, 1.0, 2.0])
    assert stats["interval_count"] == 2
    assert stats["interval_mean_seconds"] == pytest.approx(0.5)
    assert stats["interval_cv"] == pytest.approx(1.0)


def test_temporal_context_is_strict_past_and_boundary_inclusive() -> None:
    rows = [
        _row("outside", 80.0, 89.9),
        _row("boundary", 89.0, 90.0),
        _row("overlap", 80.0, 101.0),
        _row("ends-at-target", 95.0, 100.0),
        _row("target", 100.0, 101.0),
        _row("same-start-peer", 100.0, 100.5),
    ]
    contexts = build_strict_past_temporal_contexts(rows)
    target_10 = _context_for(contexts, "target", 10)
    assert target_10["prior_session_count"] == 1
    assert target_10["latest_context_age_seconds"] == pytest.approx(10.0)
    assert target_10["strictly_past_only"] is True
    assert target_10["past_only"] is True

    target_60 = _context_for(contexts, "target", 60)
    assert target_60["prior_session_count"] == 2
    assert set(target_60) >= {
        "session_rate",
        "burstiness",
        "inter_arrival_cv",
        "uri_repetition_ratio",
        "method_repetition_ratio",
    }
    assert set(target_60) and tuple(sorted(int(item) for item in TEMPORAL_HORIZONS_SECONDS)) == (
        10,
        60,
        180,
        300,
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"split": "validation"}, "one split"),
        ({"capture_id_backend_only": "capture-b"}, "one capture_id_backend_only"),
    ],
)
def test_temporal_builder_rejects_cross_boundary_input(
    mutation: dict[str, object], message: str
) -> None:
    first = _row("one", 1.0, 2.0)
    second = _row("two", 3.0, 4.0)
    second.update(mutation)
    with pytest.raises(ValueError, match=message):
        build_strict_past_temporal_contexts([first, second])


def test_temporal_builder_can_use_only_earlier_observations_across_splits() -> None:
    train = _row(
        "train",
        1.0,
        2.0,
        signals=("http_activity",),
        split="train",
    )
    validation = _row("validation", 3.0, 4.0, split="validation")
    contexts = build_strict_past_temporal_contexts(
        [validation, train], allow_prior_cross_split=True
    )
    context = _context_for(contexts, "validation", 10)
    assert context["prior_session_count"] == 1
    assert context["same_destination_http_activity_count"] == 1
    assert _context_for(contexts, "train", 10)["prior_session_count"] == 0


def test_temporal_builder_rejects_duplicate_or_invalid_rows() -> None:
    with pytest.raises(ValueError, match="unique"):
        build_strict_past_temporal_contexts(
            [_row("same", 1.0, 2.0), _row("same", 3.0, 4.0)]
        )
    with pytest.raises(ValueError, match="finite ordered"):
        build_strict_past_temporal_contexts([_row("bad", 2.0, 1.0)])


def test_temporal_statistics_are_bounded_repetition_aware_and_expire_cleanly() -> None:
    rows = [
        _row(
            "completed",
            70.0,
            71.0,
            signals=("established_exchange",),
            syn=1,
            synack=4,
            ack=5,
            requests=3,
            uri_shapes={"/<SEG>": 2, "/login": 1},
            methods={"GET": 3},
        ),
        _row(
            "incomplete",
            80.0,
            81.0,
            signals=("incomplete_handshake",),
            syn=1,
            requests=1,
            uri_shapes={"/<SEG>": 1},
            methods={"POST": 1},
        ),
        _row("target", 90.0, 91.0),
        _row("late", 400.0, 401.0),
    ]
    contexts = build_strict_past_temporal_contexts(rows)
    target = _context_for(contexts, "target")
    assert target["latest_context_age_seconds"] == pytest.approx(9.0)
    assert target["handshake_completion_ratio"] == pytest.approx(0.5)
    assert target["incomplete_handshake_ratio"] == pytest.approx(0.5)
    assert target["syn_ratio"] == pytest.approx(2 / 20)
    assert target["burstiness"] == pytest.approx(-1.0)
    assert target["inter_arrival_mean"] == pytest.approx(10.0)
    assert target["inter_arrival_std"] == pytest.approx(0.0)
    assert target["uri_repetition_ratio"] == pytest.approx(0.5)
    assert target["method_repetition_ratio"] == pytest.approx(0.5)
    assert target["application_request_count"] == 4
    validate_temporal_context(target)

    expired = _context_for(contexts, "late")
    assert expired["prior_session_count"] == 0
    assert expired["uri_repetition_ratio"] == 0.0
    assert expired["method_repetition_ratio"] == 0.0
    assert expired["handshake_completion_ratio"] == 0.0

    invalid = copy.deepcopy(target)
    invalid["handshake_completion_ratio"] = 1.1
    with pytest.raises(ValueError, match="ratio"):
        validate_temporal_context(invalid)


def test_dense_temporal_interval_buffers_remain_bounded() -> None:
    rows = [
        _row(f"prior-{index}", float(index), float(index) + 0.1)
        for index in range(1_000)
    ] + [_row("target", 1_001.0, 1_001.1)]
    contexts = build_strict_past_temporal_contexts(rows)
    target = _context_for(contexts, "target", 300)
    assert target["prior_session_count"] == 299
    # The descriptive interval sample is bounded even though aggregate rates
    # continue to use every legal prior session in the full horizon.
    assert target["inter_arrival_mean"] == pytest.approx(1.0)
    assert target["inter_arrival_std"] == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("label", "session", "relation"),
    [
        ("Normal", _session(), None),
        (
            "SQL_injection",
            _session("sql_expression"),
            None,
        ),
        (
            "Password",
            _session("authentication_attempt"),
            None,
        ),
        (
            "DDoS_TCP",
            _session("high_syn_ratio", packet_count=20, tcp_syn=15),
            None,
        ),
        (
            "DDoS_HTTP",
            _session("http_activity", "repeated_request_in_session", request_count=4),
            None,
        ),
        ("Port_Scanning", _session("probe_method"), None),
        ("Vulnerability_scanner", _session("path_traversal"), None),
        (
            "MITM",
            _session("established_exchange"),
            {"target_endpoint_linked": True, "arp_mac_multiple_ips": True},
        ),
    ],
)
def test_all_eight_candidate_classes_have_real_direct_or_contextual_paths(
    label: str,
    session: dict[str, object],
    relation: dict[str, object] | None,
) -> None:
    result = assess_fine_observation_eligibility(
        label,
        session,
        temporal_contexts={},
        relation_evidence=relation,
    )
    assert result["full_observational_sufficient"] is True
    assert result["classification_ce_eligible"] is True
    assert result["eligibility_class"] in {"DIRECT", "CONTEXTUAL"}
    assert result["supporting_reasons"]


@pytest.mark.parametrize(
    ("label", "signals", "context"),
    [
        ("SQL_injection", ("http_activity",), {"same_relation_sql_count": 1}),
        ("Password", ("http_activity",), {"same_relation_auth_count": 1}),
        (
            "DDoS_TCP",
            ("incomplete_handshake",),
            {
                "connection_rate": 20.0,
                "destination_concentration": 0.7,
                "incomplete_handshake_ratio": 0.7,
            },
        ),
        (
            "DDoS_HTTP",
            ("http_activity",),
            {
                "connection_rate": 5.0,
                "destination_concentration": 0.5,
                "same_destination_http_activity_count": 3,
            },
        ),
        (
            "Port_Scanning",
            ("short_session",),
            {"connection_rate": 1.0, "port_diversity": 10},
        ),
        (
            "Vulnerability_scanner",
            ("http_activity",),
            {"probe_event_count": 3},
        ),
    ],
)
def test_attack_contextual_paths_require_target_signal_and_strict_past_summary(
    label: str, signals: tuple[str, ...], context: dict[str, object]
) -> None:
    result = assess_fine_observation_eligibility(
        label,
        _session(*signals, basic_mechanism_signals=()),
        temporal_contexts={"60": context},
    )
    assert result["eligibility_class"] == "CONTEXTUAL"
    assert result["basic_sufficient"] is False


@pytest.mark.parametrize(
    ("label", "session", "context", "expected_reason"),
    [
        (
            "DDoS_TCP",
            _session("high_syn_ratio", packet_count=20, tcp_syn=15),
            {
                "connection_rate": 20.0,
                "destination_concentration": 0.9,
                "syn_ratio": 0.9,
            },
            "single_session_contains_repeated_syn_flood_mechanism",
        ),
        (
            "DDoS_HTTP",
            _session("http_activity", "repeated_request_in_session", request_count=4),
            {
                "connection_rate": 5.0,
                "destination_concentration": 0.9,
                "same_relation_request_count": 10,
            },
            "repeated_http_requests_observed_inside_target_session",
        ),
        (
            "Port_Scanning",
            _session("probe_method", "short_session"),
            {"connection_rate": 2.0, "port_diversity": 20},
            "explicit_application_probe_method_observed",
        ),
    ],
)
def test_direct_reason_takes_precedence_when_context_is_also_positive(
    label: str,
    session: dict[str, object],
    context: dict[str, object],
    expected_reason: str,
) -> None:
    result = assess_fine_observation_eligibility(
        label, session, temporal_contexts={"60": context}
    )
    assert result["eligibility_class"] == "DIRECT"
    assert result["supporting_reasons"] == (expected_reason,)


def test_ddos_http_context_does_not_require_tshark_method_reassembly() -> None:
    result = assess_fine_observation_eligibility(
        "DDoS_HTTP",
        _session("http_activity", request_count=0, basic_mechanism_signals=()),
        temporal_contexts={
            "10": {
                "connection_rate": 50.0,
                "destination_concentration": 1.0,
                "request_count": 0,
                "same_relation_request_count": 0,
                "same_destination_http_activity_count": 3,
            }
        },
    )
    assert result["eligibility_class"] == "CONTEXTUAL"
    assert result["supporting_evidence_families"] == ("APPLICATION", "TEMPORAL")


def test_exclusion_categories_do_not_all_claim_label_propagation() -> None:
    unobservable = assess_fine_observation_eligibility(
        "SQL_injection", _session(packet_count=0), temporal_contexts={}
    )
    assert unobservable["eligibility_class"] == "NETWORK_UNOBSERVABLE"
    assert unobservable["label_propagation_only"] is False

    generic = assess_fine_observation_eligibility(
        "SQL_injection", _session(), temporal_contexts={}
    )
    assert generic["eligibility_class"] == "GENERIC_BACKGROUND"
    assert generic["label_propagation_only"] is True

    wrong_granularity = assess_fine_observation_eligibility(
        "MITM", _session(), temporal_contexts={}, relation_evidence={}
    )
    assert wrong_granularity["eligibility_class"] == "WRONG_GRANULARITY"
    assert wrong_granularity["label_propagation_only"] is False
