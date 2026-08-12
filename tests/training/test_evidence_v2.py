from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from flowsec.training.evidence import (
    application_observation_from_frame,
    sanitize_payload_text,
)
from flowsec.training.evidence_v2 import (
    ApplicationEvidenceV2,
    ArpObservationV2,
    DnsRelationObservationV2,
    RelationSessionObservationV2,
    RelationTargetV2,
    TemporalSessionObservationV2,
    aggregate_temporal_evidence_v2,
    application_evidence_v2_from_frames,
    build_basic_evidence_v2,
    build_relation_evidence_v2,
    packet_aligned_payload_row_from_frame,
)


SAMPLE_ID = "fs1_" + "1" * 40


def _packet_frame(
    *, timestamp: float, source: str = "10.0.0.1", source_port: int = 12345, payload: str = ""
) -> dict[str, str]:
    return {
        "frame.time_epoch": str(timestamp),
        "frame.protocols": "eth:ip:tcp:http",
        "ip.src": source,
        "ip.dst": "10.0.0.2" if source == "10.0.0.1" else "10.0.0.1",
        "tcp.srcport": str(source_port),
        "tcp.dstport": "80" if source_port != 80 else "12345",
        "tcp.payload": payload,
    }


def _temporal(
    start: float,
    end: float,
    *,
    scope: str = "scope-a",
    source: str = "source-a",
    destination: str = "target-a",
    port: int = 80,
    packets: int = 10,
    bytes_: int = 1000,
    completed: bool = True,
) -> TemporalSessionObservationV2:
    return TemporalSessionObservationV2(
        observation_scope_id=scope,
        timestamp_start=start,
        timestamp_end=end,
        source_node_id=source,
        destination_node_id=destination,
        destination_port=port,
        packet_count=packets,
        byte_count=bytes_,
        initiator_bytes=600,
        responder_bytes=300,
        tcp_syn_count=1,
        tcp_synack_count=1 if completed else 0,
        tcp_ack_count=2 if completed else 0,
        handshake_completed=completed,
        authentication_request_count=1,
        application_request_count=2,
        uri_shapes=("/<SEG>",),
        methods=("GET",),
    )


def test_http_status_is_integer_in_v1_parser_and_v2_contract() -> None:
    frame = {
        "frame.protocols": "eth:ip:tcp:http",
        "http.response.code": "401",
        "http.content_type": "text/html; charset=utf-8",
    }
    observation = application_observation_from_frame(frame)
    assert observation is not None
    assert observation["status"] == 401
    assert isinstance(observation["status"], int)

    evidence = application_evidence_v2_from_frames([frame])
    assert evidence.http_status_codes == (401,)
    assert evidence.response_count == 1
    assert evidence.auth_related_structure is True
    with pytest.raises(ValidationError, match="integers in 100..599"):
        ApplicationEvidenceV2(http_status_codes=("401",))  # type: ignore[arg-type]


def test_packet_aligned_payload_records_explicit_index_direction_and_time() -> None:
    request = "GET / HTTP/1.1\r\nContent-Type: text/plain\r\n\r\nhello"
    row = packet_aligned_payload_row_from_frame(
        session_id=SAMPLE_ID,
        packet_index=2,
        frame=_packet_frame(timestamp=100.25, payload=request.encode().hex()),
        session_start_timestamp=100.0,
        initiator_ip="10.0.0.1",
        initiator_port=12345,
        responder_ip="10.0.0.2",
        responder_port=80,
    )
    assert row.packet_index == 2
    assert row.direction.value == "initiator_to_responder"
    assert row.relative_time == pytest.approx(0.25)
    assert row.payload_length == len(request.encode())
    assert row.sanitized_payload is not None
    projection = row.model_projection().model_dump(mode="json")
    assert projection["packet_index"] == 2
    assert "session_id" not in projection

    empty = packet_aligned_payload_row_from_frame(
        session_id=SAMPLE_ID,
        packet_index=1,
        frame=_packet_frame(timestamp=100.0),
        session_start_timestamp=100.0,
        initiator_ip="10.0.0.1",
        initiator_port=12345,
        responder_ip="10.0.0.2",
        responder_port=80,
    )
    assert empty.payload_present is False
    assert empty.payload_length == 0
    assert empty.sanitized_payload is None


def test_basic_v2_requires_one_payload_row_per_visible_packet() -> None:
    frames = [_packet_frame(timestamp=100.0), _packet_frame(timestamp=100.1)]
    rows = [
        packet_aligned_payload_row_from_frame(
            session_id=SAMPLE_ID,
            packet_index=index,
            frame=frame,
            session_start_timestamp=100.0,
            initiator_ip="10.0.0.1",
            initiator_port=12345,
            responder_ip="10.0.0.2",
            responder_port=80,
        )
        for index, frame in enumerate(frames, start=1)
    ]
    packets = [
        {
            "direction": "initiator_to_responder",
            "relative_iat": 0.0 if index == 1 else 0.1,
            "packet_length": 60,
            "l3_protocol": "IPv4",
            "l4_protocol": "TCP",
            "tcp_flags": 2,
        }
        for index in (1, 2)
    ]
    summary = {
        "duration": 0.1,
        "initiator_packets": 2,
        "responder_packets": 0,
        "initiator_bytes": 120,
        "responder_bytes": 0,
        "packet_length_stats": {"min": 60, "max": 60, "mean": 60, "std": 0},
        "iat_stats": {"min": 0.1, "max": 0.1, "mean": 0.1, "std": 0},
        "handshake_state": "INCOMPLETE_HANDSHAKE",
    }
    basic = build_basic_evidence_v2(
        session_id=SAMPLE_ID,
        summary=summary,
        packet_sequence=packets,
        payload_rows=rows,
        application=ApplicationEvidenceV2(),
        protocol_metadata=("TCP",),
    )
    assert [item.packet_index for item in basic.first_eight_packets] == [1, 2]
    assert [item.packet_index for item in basic.packet_aligned_payload] == [1, 2]
    assert "session_id" not in basic.model_dump_json()

    with pytest.raises(ValidationError, match="one payload-alignment row"):
        build_basic_evidence_v2(
            session_id=SAMPLE_ID,
            summary=summary,
            packet_sequence=packets,
            payload_rows=rows[:1],
            application=ApplicationEvidenceV2(),
        )


def test_temporal_v2_is_fixed_horizon_and_strictly_past() -> None:
    target = _temporal(100.0, 101.0)
    valid = _temporal(90.0, 91.0)
    ends_at_target = _temporal(99.0, 100.0)
    starts_at_target = _temporal(100.0, 100.5)
    wrong_scope = _temporal(95.0, 96.0, scope="scope-b")
    outside_window = _temporal(80.0, 89.0)
    evidence = aggregate_temporal_evidence_v2(
        target,
        [valid, ends_at_target, starts_at_target, wrong_scope, outside_window],
        horizon_seconds=10,
    )
    assert evidence.prior_session_count == 1
    assert evidence.latest_context_age_seconds == pytest.approx(9.0)
    assert evidence.session_rate == pytest.approx(0.1)
    assert evidence.syn_count == 1 and evidence.synack_count == 1
    assert evidence.handshake_completion_ratio == 1.0
    assert evidence.past_only is True

    with pytest.raises(ValueError, match="10/60/180/300"):
        aggregate_temporal_evidence_v2(target, [valid], horizon_seconds=30)


def test_temporal_v2_reports_rate_diversity_repetition_and_asymmetry() -> None:
    target = _temporal(100.0, 101.0, source="source-a", destination="target-a")
    prior = [
        _temporal(70.0, 71.0, source="source-a", destination="target-a", port=80),
        _temporal(80.0, 81.0, source="source-b", destination="target-a", port=81),
        _temporal(90.0, 91.0, source="source-a", destination="target-b", port=82),
    ]
    evidence = aggregate_temporal_evidence_v2(target, prior, horizon_seconds=60)
    assert evidence.prior_session_count == 3
    assert evidence.source_fan_in == 2
    assert evidence.destination_fan_out == 2
    assert evidence.port_diversity == 3
    assert evidence.destination_concentration == pytest.approx(2 / 3)
    assert evidence.uri_repetition_ratio == pytest.approx(2 / 3)
    assert evidence.method_repetition_ratio == pytest.approx(2 / 3)
    assert evidence.directional_byte_asymmetry == pytest.approx(1 / 3)


def test_relation_v2_requires_scope_time_and_endpoint_linkage() -> None:
    target = RelationTargetV2(
        observation_scope_id="scope-a",
        timestamp=100.0,
        source_ip="10.0.0.1",
        destination_ip="10.0.0.2",
        source_mac="aa:aa:aa:aa:aa:aa",
        destination_mac="bb:bb:bb:bb:bb:bb",
        destination_port=80,
    )
    arp = [
        ArpObservationV2(
            observation_scope_id="scope-a",
            timestamp=90.0,
            sender_ip="10.0.0.1",
            sender_mac="aa:aa:aa:aa:aa:aa",
            target_ip="10.0.0.2",
        ),
        ArpObservationV2(
            observation_scope_id="scope-a",
            timestamp=95.0,
            sender_ip="10.0.0.1",
            sender_mac="cc:cc:cc:cc:cc:cc",
            target_ip="10.0.0.2",
        ),
        ArpObservationV2(
            observation_scope_id="scope-a",
            timestamp=96.0,
            sender_ip="10.0.0.2",
            sender_mac="aa:aa:aa:aa:aa:aa",
            target_ip="10.0.0.1",
        ),
        # Capture-local but endpoint-unrelated: this must never propagate.
        ArpObservationV2(
            observation_scope_id="scope-a",
            timestamp=97.0,
            sender_ip="10.0.0.8",
            sender_mac="dd:dd:dd:dd:dd:dd",
            target_ip="10.0.0.9",
        ),
        # Endpoint-linked but simultaneous, hence not strictly past.
        ArpObservationV2(
            observation_scope_id="scope-a",
            timestamp=100.0,
            sender_ip="10.0.0.1",
            sender_mac="ee:ee:ee:ee:ee:ee",
            target_ip="10.0.0.2",
        ),
        # Endpoint-linked but from another source scope.
        ArpObservationV2(
            observation_scope_id="scope-b",
            timestamp=94.0,
            sender_ip="10.0.0.1",
            sender_mac="ff:ff:ff:ff:ff:ff",
            target_ip="10.0.0.2",
        ),
    ]
    sessions = [
        RelationSessionObservationV2(
            observation_scope_id="scope-a",
            timestamp_end=92.0,
            source_ip="10.0.0.3",
            destination_ip="10.0.0.2",
            destination_port=80,
        ),
        RelationSessionObservationV2(
            observation_scope_id="scope-a",
            timestamp_end=93.0,
            source_ip="10.0.0.4",
            destination_ip="10.0.0.2",
            destination_port=80,
        ),
        RelationSessionObservationV2(
            observation_scope_id="scope-a",
            timestamp_end=94.0,
            source_ip="10.0.0.1",
            destination_ip="10.0.0.2",
            destination_port=443,
        ),
        RelationSessionObservationV2(
            observation_scope_id="scope-a",
            timestamp_end=95.0,
            source_ip="10.0.0.9",
            destination_ip="10.0.0.1",
            destination_port=12345,
            responder_observed=True,
        ),
    ]
    dns = [
        DnsRelationObservationV2(
            observation_scope_id="scope-a",
            timestamp=89.0,
            client_ip="10.0.0.1",
            responder_ip="10.0.0.53",
            name_shape="<HOST>.local",
            response_code=0,
        )
    ]
    evidence = build_relation_evidence_v2(
        target,
        arp_observations=arp,
        dns_observations=dns,
        session_observations=sessions,
        horizon_seconds=60,
    )
    assert evidence.linked_arp_observation_count == 3
    assert evidence.arp_ip_conflict_count == 1
    assert evidence.arp_mapping_change_count == 1
    assert evidence.same_mac_multiple_ip_count == 1
    assert evidence.dns_relationship_count == 1
    assert evidence.source_fan_in == 3
    assert evidence.multi_source_same_target is True
    assert evidence.port_relationship_diversity == 1
    assert evidence.unexpected_responder_count == 1
    assert evidence.linked_endpoint_roles == ("destination", "source")
    serialized = json.dumps(evidence.model_dump(mode="json"), sort_keys=True)
    assert "10.0.0." not in serialized and "scope-a" not in serialized


def test_v2_label_free_inputs_reject_fine_label_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        TemporalSessionObservationV2.model_validate(
            {
                **_temporal(1.0, 2.0).model_dump(),
                "fine_label": "MITM",
            }
        )


def test_sanitized_http_uri_shapes_are_idempotent() -> None:
    raw = (
        "GET /app/route/item?id=7&name=alice HTTP/1.1\r\n"
        "Host: 10.0.0.1\r\nCookie: secret\r\n\r\n"
    )
    first = sanitize_payload_text(raw, max_chars=768)
    assert first is not None
    assert sanitize_payload_text(first, max_chars=768) == first
    assert sanitize_payload_text(first, max_chars=2048) == first

    shaped = (
        "GET /<SEG>/<FILE>.php/<NUM> HTTP/1.1\n"
        "Host: <HOST>\nUser-Agent: <CLIENT>"
    )
    assert sanitize_payload_text(shaped, max_chars=768) == shaped

    encoded_control = "GET /app/file.jsp%00 HTTP/1.1\r\nHost: 10.0.0.1\r\n\r\n"
    controlled = sanitize_payload_text(encoded_control, max_chars=768)
    assert controlled is not None and "\x00" not in controlled
    assert sanitize_payload_text(controlled, max_chars=2048) == controlled
