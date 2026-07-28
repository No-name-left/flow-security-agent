from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any, Iterable, Mapping

from .ground_truth import GroundTruthEvent


class MatchStatus(StrEnum):
    UNIQUE = "uniquely_matched"
    AMBIGUOUS = "ambiguous_multiple_matches"
    UNMATCHED = "unmatched"


@dataclass(frozen=True)
class FlowIdentity:
    flow_id: str
    start_ms: int
    end_ms: int
    source_ip: str
    destination_ip: str
    protocol: int
    source_port: int
    destination_port: int
    label: str | None = None


@dataclass(frozen=True)
class MatchResult:
    flow_id: str
    status: MatchStatus
    event_ids: tuple[str, ...]
    rule_types: tuple[str, ...]
    label_agreement: bool | None


def duplicate_signature(
    record: Mapping[str, Any],
    *,
    excluded_fields: frozenset[str] = frozenset(
        {"source_row", "row_index", "sample_id", "group_id", "split", "fold"}
    ),
) -> str:
    """Stable exact-record signature for the future must-link split constraint."""

    semantic = {key: value for key, value in record.items() if key not in excluded_fields}
    payload = json.dumps(semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _utc_day(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).date().isoformat()


class EventIndex:
    """Label-free endpoint/protocol/day index followed by exact interval and port checks."""

    def __init__(self, events: Iterable[GroundTruthEvent], *, allow_reverse: bool = True) -> None:
        self.allow_reverse = allow_reverse
        self._buckets: dict[tuple[str, int | None, str, str], list[GroundTruthEvent]] = defaultdict(list)
        for event in sorted(events, key=lambda item: item.event_id):
            current_day = datetime.fromtimestamp(event.start_ms / 1000, tz=timezone.utc).date()
            last_day = datetime.fromtimestamp(event.end_ms / 1000, tz=timezone.utc).date()
            while current_day <= last_day:
                day = current_day.isoformat()
                self._buckets[(day, event.protocol, event.source_ip, event.destination_ip)].append(
                    event
                )
                if allow_reverse and event.source_ip != event.destination_ip:
                    self._buckets[(day, event.protocol, event.destination_ip, event.source_ip)].append(
                        event
                    )
                current_day += timedelta(days=1)

    def _candidate_events(self, flow: FlowIdentity) -> list[GroundTruthEvent]:
        day = _utc_day(flow.start_ms)
        candidates: dict[str, GroundTruthEvent] = {}
        for protocol in (flow.protocol, None):
            for event in self._buckets.get(
                (day, protocol, flow.source_ip, flow.destination_ip), ()
            ):
                candidates[event.event_id] = event
        return [candidates[key] for key in sorted(candidates)]

    def match(self, flow: FlowIdentity) -> MatchResult:
        matches: list[tuple[GroundTruthEvent, str]] = []
        for event in self._candidate_events(flow):
            if flow.end_ms < event.start_ms or flow.start_ms > event.end_ms:
                continue
            direct = (
                flow.source_ip == event.source_ip
                and flow.destination_ip == event.destination_ip
            )
            reverse = (
                self.allow_reverse
                and flow.source_ip == event.destination_ip
                and flow.destination_ip == event.source_ip
            )
            if not (direct or reverse):
                continue
            expected_source_port = event.source_port if direct else event.destination_port
            expected_destination_port = event.destination_port if direct else event.source_port
            if expected_source_port is not None and flow.source_port != expected_source_port:
                continue
            if (
                expected_destination_port is not None
                and flow.destination_port != expected_destination_port
            ):
                continue
            wildcard = event.protocol is None or event.source_port is None or event.destination_port is None
            if reverse:
                rule = "reverse_direction_time"
            elif wildcard:
                rule = "wildcard_port_time"
            else:
                rule = "exact_5tuple_time"
            matches.append((event, rule))

        if not matches:
            return MatchResult(flow.flow_id, MatchStatus.UNMATCHED, (), (), None)
        status = MatchStatus.UNIQUE if len(matches) == 1 else MatchStatus.AMBIGUOUS
        event_ids = tuple(event.event_id for event, _ in matches)
        rule_types = tuple(rule for _, rule in matches)
        agreement: bool | None = None
        if flow.label is not None:
            agreement = all(event.label == flow.label for event, _ in matches)
        return MatchResult(flow.flow_id, status, event_ids, rule_types, agreement)

    def match_many(self, flows: Iterable[FlowIdentity]) -> list[MatchResult]:
        return [self.match(flow) for flow in flows]

    @property
    def fingerprint(self) -> str:
        events = []
        seen: set[str] = set()
        for bucket in self._buckets.values():
            for event in bucket:
                if event.event_id not in seen:
                    seen.add(event.event_id)
                    events.append(asdict(event))
        payload = json.dumps(
            {"allow_reverse": self.allow_reverse, "events": sorted(events, key=lambda x: x["event_id"])},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
