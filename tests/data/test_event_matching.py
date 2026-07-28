from __future__ import annotations

from dataclasses import asdict

import pytest

from flowsec.data.event_matching import (
    EventIndex,
    FlowIdentity,
    MatchStatus,
    duplicate_signature,
)
from flowsec.data.ground_truth import (
    GroundTruthEvent,
    GroundTruthSchema,
    GroundTruthSchemaError,
    normalize_ground_truth_rows,
)


def _event(event_id: str = "event-1", **changes: object) -> GroundTruthEvent:
    values: dict[str, object] = {
        "event_id": event_id,
        "start_ms": 1_000,
        "end_ms": 5_000,
        "source_ip": "10.0.0.1",
        "destination_ip": "10.0.0.2",
        "protocol": 6,
        "source_port": 40_000,
        "destination_port": 80,
        "label": "Scanning",
    }
    values.update(changes)
    return GroundTruthEvent(**values)  # type: ignore[arg-type]


def _flow(flow_id: str = "flow-1", **changes: object) -> FlowIdentity:
    values: dict[str, object] = {
        "flow_id": flow_id,
        "start_ms": 2_000,
        "end_ms": 2_100,
        "source_ip": "10.0.0.1",
        "destination_ip": "10.0.0.2",
        "protocol": 6,
        "source_port": 40_000,
        "destination_port": 80,
        "label": "Scanning",
    }
    values.update(changes)
    return FlowIdentity(**values)  # type: ignore[arg-type]


def test_exact_time_and_five_tuple_matches_uniquely() -> None:
    result = EventIndex([_event()]).match(_flow())
    assert result.status is MatchStatus.UNIQUE
    assert result.event_ids == ("event-1",)
    assert result.rule_types == ("exact_5tuple_time",)
    assert result.label_agreement is True


def test_non_overlapping_time_does_not_match() -> None:
    result = EventIndex([_event()]).match(_flow(start_ms=6_000, end_ms=6_100))
    assert result.status is MatchStatus.UNMATCHED


def test_reverse_direction_obeys_configuration() -> None:
    reverse = _flow(
        source_ip="10.0.0.2",
        destination_ip="10.0.0.1",
        source_port=80,
        destination_port=40_000,
    )
    assert EventIndex([_event()], allow_reverse=True).match(reverse).rule_types == (
        "reverse_direction_time",
    )
    assert EventIndex([_event()], allow_reverse=False).match(reverse).status is MatchStatus.UNMATCHED


def test_wildcard_ports_match() -> None:
    result = EventIndex([_event(source_port=None, destination_port=None)]).match(
        _flow(source_port=12_345, destination_port=443)
    )
    assert result.status is MatchStatus.UNIQUE
    assert result.rule_types == ("wildcard_port_time",)


def test_overlapping_events_are_ambiguous() -> None:
    result = EventIndex([_event("event-2"), _event("event-1")]).match(_flow())
    assert result.status is MatchStatus.AMBIGUOUS
    assert result.event_ids == ("event-1", "event-2")


def test_label_disagreement_is_explicit() -> None:
    result = EventIndex([_event(label="DDoS")]).match(_flow(label="Scanning"))
    assert result.status is MatchStatus.UNIQUE
    assert result.label_agreement is False


def test_duplicate_signature_is_stable_and_ignores_only_lineage_fields() -> None:
    record = asdict(_flow()) | {"source_row": 10}
    changed_lineage = record | {"source_row": 999, "split": "test"}
    assert duplicate_signature(record) == duplicate_signature(changed_lineage)
    assert duplicate_signature(record) != duplicate_signature(record | {"destination_port": 443})


def test_same_input_produces_same_results_and_fingerprint() -> None:
    first = EventIndex([_event("b"), _event("a")])
    second = EventIndex([_event("a"), _event("b")])
    assert first.match(_flow()) == second.match(_flow())
    assert first.fingerprint == second.fingerprint


def test_missing_ground_truth_field_fails_clearly() -> None:
    schema = GroundTruthSchema(
        start="start",
        end="end",
        source_ip="src",
        destination_ip="dst",
        label="attack",
        timestamp_unit="milliseconds",
    )
    with pytest.raises(GroundTruthSchemaError, match="missing configured columns"):
        normalize_ground_truth_rows(
            [{"start": "1000", "end": "2000", "src": "10.0.0.1", "attack": "DoS"}],
            schema,
        )


def test_matching_uses_stable_flow_id_not_input_row_position() -> None:
    index = EventIndex([_event()])
    flows = [_flow("flow-b"), _flow("flow-a", destination_port=443)]
    forward = {result.flow_id: result.status for result in index.match_many(flows)}
    reverse = {result.flow_id: result.status for result in index.match_many(reversed(flows))}
    assert forward == reverse
    assert forward == {"flow-a": MatchStatus.UNMATCHED, "flow-b": MatchStatus.UNIQUE}
