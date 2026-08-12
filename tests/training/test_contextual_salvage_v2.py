from __future__ import annotations

import json

import pytest

from flowsec.training.contextual_salvage_v2 import (
    ArpClaimV2,
    RelationGraphTargetV2,
    ScanSessionObservationV2,
    build_past_only_relation_graph_v2,
    build_past_only_scan_context_v2,
    strongest_relation_context,
    strongest_scan_context,
)


def _claim(
    timestamp: float,
    sender_ip: str,
    *,
    scope: str = "scope-a",
    mac: str = "aa:aa:aa:aa:aa:aa",
    target_ip: str = "10.0.0.9",
) -> ArpClaimV2:
    return ArpClaimV2(
        observation_scope_id=scope,
        timestamp=timestamp,
        sender_mac=mac,
        sender_ip=sender_ip,
        target_ip=target_ip,
    )


def _relation_target(
    timestamp: float = 100.0,
    *,
    record_id: str = "target",
    partition: str = "train",
    source_ip: str = "10.0.0.1",
    destination_ip: str = "10.0.0.9",
) -> RelationGraphTargetV2:
    return RelationGraphTargetV2(
        record_id=record_id,
        observation_scope_id="scope-a",
        partition_id=partition,
        timestamp=timestamp,
        source_ip=source_ip,
        destination_ip=destination_ip,
    )


def _scan_session(
    record_id: str,
    start: float,
    *,
    source: str = "source-a",
    destination: str = "destination-a",
    port: int = 80,
    partition: str = "train",
    probe: bool = True,
) -> ScanSessionObservationV2:
    return ScanSessionObservationV2(
        record_id=record_id,
        observation_scope_id="scope-a",
        partition_id=partition,
        timestamp_start=start,
        timestamp_end=start + 0.1,
        source_node_id=source,
        destination_node_id=destination,
        destination_port=port,
        packet_count=2,
        responder_packet_count=1 if probe else 2,
        tcp_syn_count=1 if probe else 0,
        tcp_synack_count=0,
        tcp_rst_count=1 if probe else 0,
        duration_seconds=0.1 if probe else 3.0,
    )


def test_relation_graph_accepts_repeated_common_target_claims_and_links_endpoint() -> None:
    target = _relation_target()
    anchor = _relation_target(timestamp=80.0, record_id="anchor")
    claims = [
        _claim(90.0, "10.0.0.1"),
        _claim(91.0, "10.0.0.2"),
        _claim(92.0, "10.0.0.1"),
        _claim(93.0, "10.0.0.2"),
    ]
    context = strongest_relation_context(
        build_past_only_relation_graph_v2([anchor, target], claims)[target.record_id]
    )
    assert context is not None
    assert context.horizon_seconds == 10
    assert context.local_network_relation_anomaly is True
    assert context.relation_level == "ENTITY_LINKED"
    assert context.linked_endpoint_roles == ("source", "destination")
    assert context.repeated_same_mac_common_target_count == 1


def test_relation_graph_is_strictly_past_and_does_not_use_future_claims() -> None:
    target = _relation_target()
    anchor = _relation_target(timestamp=90.0, record_id="anchor")
    claims = [
        _claim(99.0, "10.0.0.1"),
        _claim(99.5, "10.0.0.1"),
        _claim(100.0, "10.0.0.2"),  # exact target time is not past
        _claim(101.0, "10.0.0.2"),
        _claim(102.0, "10.0.0.2"),
    ]
    contexts = build_past_only_relation_graph_v2([anchor, target], claims)[target.record_id]
    assert all(item.arp_claim_count == 2 for item in contexts)
    assert strongest_relation_context(contexts) is None


def test_relation_graph_is_partition_local_and_label_free() -> None:
    train = _relation_target(timestamp=100.0, record_id="train", partition="train")
    train_anchor = _relation_target(
        timestamp=80.0, record_id="train-anchor", partition="train"
    )
    validation = _relation_target(
        timestamp=200.0, record_id="validation", partition="validation"
    )
    claims = [
        _claim(90.0, "10.0.0.1"),
        _claim(91.0, "10.0.0.1"),
        _claim(92.0, "10.0.0.2"),
        _claim(93.0, "10.0.0.2"),
    ]
    result = build_past_only_relation_graph_v2(
        [train_anchor, train, validation], claims
    )
    assert strongest_relation_context(result[train.record_id]) is not None
    assert strongest_relation_context(result[validation.record_id]) is None
    assert "label" not in RelationGraphTargetV2.model_fields
    assert "capture" not in RelationGraphTargetV2.model_fields


def test_relation_model_projection_contains_no_backend_identity() -> None:
    target = _relation_target(source_ip="10.10.10.10", destination_ip="10.10.10.11")
    anchor = _relation_target(timestamp=80.0, record_id="anchor")
    claims = [
        _claim(90.0, "10.10.10.10", target_ip="10.10.10.11"),
        _claim(91.0, "10.10.10.12", target_ip="10.10.10.11"),
        _claim(92.0, "10.10.10.10", target_ip="10.10.10.11"),
        _claim(93.0, "10.10.10.12", target_ip="10.10.10.11"),
    ]
    context = strongest_relation_context(
        build_past_only_relation_graph_v2([anchor, target], claims)[target.record_id]
    )
    assert context is not None
    serialized = json.dumps(context.model_dump(mode="json"), sort_keys=True)
    for forbidden in (
        "10.10.10.10",
        "10.10.10.11",
        "aa:aa:aa:aa:aa:aa",
        "scope-a",
        "train",
        "capture",
        "dataset",
        "fine_label",
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize("kind", ["vertical", "horizontal"])
def test_scan_context_detects_protocol_semantic_sweeps(kind: str) -> None:
    prior = []
    for index in range(8):
        prior.append(
            _scan_session(
                f"prior-{index}",
                10.0 + index,
                destination=("destination-a" if kind == "vertical" else f"host-{index}"),
                port=(1000 + index if kind == "vertical" else 80),
            )
        )
    target = _scan_session("target", 30.0)
    context = strongest_scan_context(
        build_past_only_scan_context_v2([*prior, target])[target.record_id]
    )
    assert context is not None
    assert context.vertical_scan_supported is (kind == "vertical")
    assert context.horizontal_scan_supported is (kind == "horizontal")


def test_scan_context_rejects_single_host_single_service_repetition() -> None:
    prior = [_scan_session(f"prior-{index}", 10.0 + index) for index in range(20)]
    target = _scan_session("target", 40.0)
    contexts = build_past_only_scan_context_v2([*prior, target])[target.record_id]
    assert strongest_scan_context(contexts) is None
    assert max(item.prior_same_source_session_count for item in contexts) == 20
    assert max(item.distinct_destination_count for item in contexts) == 1
    assert max(item.distinct_destination_port_count for item in contexts) == 1


def test_scan_context_excludes_future_same_time_and_other_partition() -> None:
    target = _scan_session("target", 30.0)
    exact_boundary = _scan_session("exact-boundary", 29.9)
    future = [
        _scan_session(
            f"future-{index}",
            30.0 + index,
            destination=f"host-{index}",
        )
        for index in range(8)
    ]
    other_partition = [
        _scan_session(
            f"validation-{index}",
            10.0 + index,
            destination=f"host-{index}",
            partition="validation",
        )
        for index in range(8)
    ]
    contexts = build_past_only_scan_context_v2(
        [target, exact_boundary, *future, *other_partition]
    )[target.record_id]
    assert all(item.prior_same_source_session_count == 0 for item in contexts)
    assert strongest_scan_context(contexts) is None


def test_scan_projection_is_label_free_and_model_safe() -> None:
    prior = [
        _scan_session(f"prior-{index}", 10.0 + index, port=1000 + index)
        for index in range(8)
    ]
    target = _scan_session("target", 30.0)
    context = strongest_scan_context(
        build_past_only_scan_context_v2([*prior, target])[target.record_id]
    )
    assert context is not None
    assert "label" not in ScanSessionObservationV2.model_fields
    assert "capture" not in ScanSessionObservationV2.model_fields
    serialized = json.dumps(context.model_dump(mode="json"), sort_keys=True)
    for forbidden in (
        "source-a",
        "destination-a",
        "scope-a",
        "train",
        "capture",
        "dataset",
        "fine_label",
    ):
        assert forbidden not in serialized
