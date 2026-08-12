from __future__ import annotations

import bisect
import math
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from typing import Iterable, Literal, Sequence

from pydantic import Field, model_validator

from flowsec.runtime.contracts import validate_model_visible_value
from flowsec.training.contracts import FrozenModel


CONTEXTUAL_RELATION_GRAPH_V2 = "CONTEXTUAL_RELATION_GRAPH_V2"
CONTEXTUAL_SCAN_V2 = "CONTEXTUAL_SCAN_V2"
SALVAGE_HORIZONS_SECONDS = (10, 60, 180, 300)

# These are protocol-semantic reliability floors, not class- or capture-fitted
# thresholds. Two repeated claims for each of two addresses prevents a single
# retransmission or one-off address transition from becoming a relation anomaly.
MIN_REPEATED_ARP_CLAIMS = 2

# Eight distinct ports or hosts is a conservative, fixed interpretation of
# "many" for a bounded scan context. The opposite dimension must stay small so
# vertical and horizontal scanning remain distinguishable.
MIN_SCAN_PRIOR_SESSIONS = 8
MIN_SCAN_DIVERSITY = 8
MAX_SCAN_OPPOSITE_DIVERSITY = 3
MIN_SCAN_PROBE_RATIO = 0.5


class RelationGraphTargetV2(FrozenModel):
    """Backend-only target identity used by the deterministic audit builder."""

    record_id: str = Field(min_length=1, repr=False)
    observation_scope_id: str = Field(min_length=1, repr=False)
    partition_id: str = Field(min_length=1, repr=False)
    timestamp: float = Field(ge=0.0, allow_inf_nan=False, repr=False)
    source_ip: str = Field(min_length=1, repr=False)
    destination_ip: str = Field(min_length=1, repr=False)


class ArpClaimV2(FrozenModel):
    """One raw ARP claim. All identifiers stay outside the model projection."""

    observation_scope_id: str = Field(min_length=1, repr=False)
    timestamp: float = Field(ge=0.0, allow_inf_nan=False, repr=False)
    sender_mac: str = Field(min_length=1, repr=False)
    sender_ip: str = Field(min_length=1, repr=False)
    target_ip: str = Field(min_length=1, repr=False)


class RelationGraphContextV2(FrozenModel):
    schema_version: Literal["CONTEXTUAL_RELATION_GRAPH_V2"] = (
        CONTEXTUAL_RELATION_GRAPH_V2
    )
    horizon_seconds: Literal[10, 60, 180, 300]
    past_only: Literal[True] = True
    arp_claim_count: int = Field(ge=0)
    arp_claim_rate: float = Field(ge=0.0, allow_inf_nan=False)
    distinct_sender_count: int = Field(ge=0)
    distinct_claimed_ip_count: int = Field(ge=0)
    same_ip_multiple_mac_count: int = Field(ge=0)
    repeated_same_mac_multiple_ip_count: int = Field(ge=0)
    repeated_same_mac_common_target_count: int = Field(ge=0)
    mapping_change_count: int = Field(ge=0)
    repeated_anomalous_claim_count: int = Field(ge=0)
    entity_linked: bool
    linked_endpoint_roles: tuple[Literal["source", "destination"], ...] = ()
    local_network_relation_anomaly: bool
    relation_level: Literal["NONE", "ENTITY_LINKED", "LOCAL_NETWORK_STATE"]

    @model_validator(mode="after")
    def validate_semantics(self) -> "RelationGraphContextV2":
        if self.entity_linked != bool(self.linked_endpoint_roles):
            raise ValueError("entity linkage and linked roles disagree")
        expected = (
            "ENTITY_LINKED"
            if self.entity_linked and self.local_network_relation_anomaly
            else "LOCAL_NETWORK_STATE"
            if self.local_network_relation_anomaly
            else "NONE"
        )
        if self.relation_level != expected:
            raise ValueError("relation level disagrees with anomaly/linkage state")
        validate_model_visible_value(
            self.model_dump(mode="json"), location="contextual_relation_graph_v2"
        )
        return self


class ScanSessionObservationV2(FrozenModel):
    """Label-free session observation for same-source scan aggregation."""

    record_id: str = Field(min_length=1, repr=False)
    observation_scope_id: str = Field(min_length=1, repr=False)
    partition_id: str = Field(min_length=1, repr=False)
    timestamp_start: float = Field(ge=0.0, allow_inf_nan=False, repr=False)
    timestamp_end: float = Field(ge=0.0, allow_inf_nan=False, repr=False)
    source_node_id: str = Field(min_length=1, repr=False)
    destination_node_id: str = Field(min_length=1, repr=False)
    destination_port: int = Field(ge=0, le=65535, repr=False)
    packet_count: int = Field(ge=1)
    responder_packet_count: int = Field(ge=0)
    tcp_syn_count: int = Field(ge=0)
    tcp_synack_count: int = Field(ge=0)
    tcp_rst_count: int = Field(ge=0)
    duration_seconds: float = Field(ge=0.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_times_and_counts(self) -> "ScanSessionObservationV2":
        if self.timestamp_end < self.timestamp_start:
            raise ValueError("session end precedes session start")
        if self.responder_packet_count > self.packet_count:
            raise ValueError("responder packets exceed total packets")
        for count in (self.tcp_syn_count, self.tcp_synack_count, self.tcp_rst_count):
            if count > self.packet_count:
                raise ValueError("TCP flag count exceeds packet count")
        return self

    @property
    def probe_like(self) -> bool:
        return self.duration_seconds <= 2.0 and (
            self.tcp_rst_count > 0
            or (self.tcp_syn_count > 0 and self.tcp_synack_count == 0)
        )


class ScanContextV2(FrozenModel):
    schema_version: Literal["CONTEXTUAL_SCAN_V2"] = CONTEXTUAL_SCAN_V2
    horizon_seconds: Literal[10, 60, 180, 300]
    past_only: Literal[True] = True
    current_probe_like: bool
    prior_same_source_session_count: int = Field(ge=0)
    connection_rate: float = Field(ge=0.0, allow_inf_nan=False)
    packet_rate: float = Field(ge=0.0, allow_inf_nan=False)
    distinct_destination_count: int = Field(ge=0)
    distinct_destination_port_count: int = Field(ge=0)
    syn_count: int = Field(ge=0)
    syn_ratio: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    rst_count: int = Field(ge=0)
    response_ratio: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    short_or_incomplete_ratio: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    target_concentration: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    inter_arrival_mean: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    inter_arrival_cv: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    burstiness: float = Field(ge=-1.0, le=1.0, allow_inf_nan=False)
    vertical_scan_supported: bool
    horizontal_scan_supported: bool
    same_service_multi_host_probe: bool

    @property
    def scan_supported(self) -> bool:
        return self.vertical_scan_supported or self.horizontal_scan_supported

    @model_validator(mode="after")
    def validate_model_safe_projection(self) -> "ScanContextV2":
        if self.same_service_multi_host_probe != self.horizontal_scan_supported:
            raise ValueError("same-service multi-host flag must match horizontal support")
        validate_model_visible_value(
            self.model_dump(mode="json"), location="contextual_scan_v2"
        )
        return self


def _valid_claim(item: ArpClaimV2) -> bool:
    return item.sender_ip not in {"0.0.0.0", "::"} and bool(
        item.sender_mac and item.target_ip
    )


def _relation_context(
    target: RelationGraphTargetV2,
    claims: Iterable[ArpClaimV2],
    *,
    horizon_seconds: int,
) -> RelationGraphContextV2:
    values = tuple(claims)
    pair_counts = Counter(
        (item.sender_mac, item.sender_ip, item.target_ip) for item in values
    )
    ip_mac_counts: dict[str, Counter[str]] = defaultdict(Counter)
    mac_ip_counts: dict[str, Counter[str]] = defaultdict(Counter)
    common_target_counts: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for (mac, ip, target_ip), count in pair_counts.items():
        ip_mac_counts[ip][mac] += count
        mac_ip_counts[mac][ip] += count
        common_target_counts[(mac, target_ip)][ip] += count

    repeated_ip_conflicts = {
        ip: {mac for mac, count in macs.items() if count >= MIN_REPEATED_ARP_CLAIMS}
        for ip, macs in ip_mac_counts.items()
    }
    repeated_ip_conflicts = {
        ip: macs for ip, macs in repeated_ip_conflicts.items() if len(macs) >= 2
    }
    repeated_multi_ip_macs = {
        mac: {ip for ip, count in ips.items() if count >= MIN_REPEATED_ARP_CLAIMS}
        for mac, ips in mac_ip_counts.items()
    }
    repeated_multi_ip_macs = {
        mac: ips for mac, ips in repeated_multi_ip_macs.items() if len(ips) >= 2
    }
    common_target_anomalies = {
        key: {ip for ip, count in ips.items() if count >= MIN_REPEATED_ARP_CLAIMS}
        for key, ips in common_target_counts.items()
    }
    common_target_anomalies = {
        key: ips for key, ips in common_target_anomalies.items() if len(ips) >= 2
    }

    anomalous_ips = set(repeated_ip_conflicts)
    anomalous_targets: set[str] = set()
    anomalous_pairs: set[tuple[str, str, str]] = set()
    for (mac, target_ip), ips in common_target_anomalies.items():
        anomalous_targets.add(target_ip)
        anomalous_ips.update(ips)
        anomalous_pairs.update((mac, ip, target_ip) for ip in ips)
    for ip, macs in repeated_ip_conflicts.items():
        anomalous_pairs.update(
            pair for pair in pair_counts if pair[1] == ip and pair[0] in macs
        )

    roles: list[Literal["source", "destination"]] = []
    if target.source_ip in anomalous_ips or target.source_ip in anomalous_targets:
        roles.append("source")
    if target.destination_ip in anomalous_ips or target.destination_ip in anomalous_targets:
        roles.append("destination")
    anomaly = bool(repeated_ip_conflicts or common_target_anomalies)
    entity_linked = bool(roles) and anomaly

    mapping_changes = sum(max(0, len(macs) - 1) for macs in ip_mac_counts.values())
    repeated_anomalous_claims = sum(pair_counts[pair] for pair in anomalous_pairs)
    return RelationGraphContextV2(
        horizon_seconds=horizon_seconds,
        arp_claim_count=len(values),
        arp_claim_rate=len(values) / horizon_seconds,
        distinct_sender_count=len({item.sender_mac for item in values}),
        distinct_claimed_ip_count=len({item.sender_ip for item in values}),
        same_ip_multiple_mac_count=len(repeated_ip_conflicts),
        repeated_same_mac_multiple_ip_count=len(repeated_multi_ip_macs),
        repeated_same_mac_common_target_count=len(common_target_anomalies),
        mapping_change_count=mapping_changes,
        repeated_anomalous_claim_count=repeated_anomalous_claims,
        entity_linked=entity_linked,
        linked_endpoint_roles=tuple(roles),
        local_network_relation_anomaly=anomaly,
        relation_level=(
            "ENTITY_LINKED"
            if entity_linked
            else "LOCAL_NETWORK_STATE"
            if anomaly
            else "NONE"
        ),
    )


def build_past_only_relation_graph_v2(
    targets: Sequence[RelationGraphTargetV2],
    arp_claims: Sequence[ArpClaimV2],
    *,
    horizons_seconds: Sequence[int] = SALVAGE_HORIZONS_SECONDS,
) -> dict[str, tuple[RelationGraphContextV2, ...]]:
    """Build split-local relation contexts from claims in ``[t-horizon, t)``.

    The function has no label, capture-name or model-result input. Scope and
    partition identifiers are backend-only locality guards and are absent from
    every returned model-safe context.
    """

    horizons = tuple(horizons_seconds)
    if not horizons or any(value not in SALVAGE_HORIZONS_SECONDS for value in horizons):
        raise ValueError("relation horizons must be selected from 10/60/180/300")
    record_ids = [item.record_id for item in targets]
    if len(record_ids) != len(set(record_ids)):
        raise ValueError("relation targets require unique record IDs")

    claims_by_scope: dict[str, list[ArpClaimV2]] = defaultdict(list)
    for item in arp_claims:
        if _valid_claim(item):
            claims_by_scope[item.observation_scope_id].append(item)
    for values in claims_by_scope.values():
        values.sort(key=lambda item: item.timestamp)

    grouped: dict[tuple[str, str], list[RelationGraphTargetV2]] = defaultdict(list)
    for item in targets:
        grouped[(item.observation_scope_id, item.partition_id)].append(item)

    output: dict[str, list[RelationGraphContextV2]] = defaultdict(list)
    for (scope, _partition), group in grouped.items():
        ordered_targets = sorted(group, key=lambda item: (item.timestamp, item.record_id))
        partition_start = ordered_targets[0].timestamp
        eligible_claims = [
            item for item in claims_by_scope.get(scope, ()) if item.timestamp >= partition_start
        ]
        for horizon in horizons:
            visible: deque[ArpClaimV2] = deque()
            cursor = 0
            for target in ordered_targets:
                while (
                    cursor < len(eligible_claims)
                    and eligible_claims[cursor].timestamp < target.timestamp
                ):
                    visible.append(eligible_claims[cursor])
                    cursor += 1
                lower = target.timestamp - horizon
                while visible and visible[0].timestamp < lower:
                    visible.popleft()
                output[target.record_id].append(
                    _relation_context(target, visible, horizon_seconds=horizon)
                )

    return {record_id: tuple(values) for record_id, values in output.items()}


@dataclass
class _SourceWindow:
    count: int = 0
    probe_count: int = 0
    packet_count: int = 0
    syn_count: int = 0
    rst_count: int = 0
    response_count: int = 0
    destinations: Counter[str] = field(default_factory=Counter)
    ports: Counter[int] = field(default_factory=Counter)
    start_times: list[float] = field(default_factory=list)
    interval_sum: float = 0.0
    interval_square_sum: float = 0.0

    def _adjust_interval(self, value: float, delta: int) -> None:
        self.interval_sum += delta * value
        self.interval_square_sum += delta * value * value

    def _insert_start(self, value: float) -> None:
        index = bisect.bisect_right(self.start_times, value)
        previous = self.start_times[index - 1] if index else None
        following = self.start_times[index] if index < len(self.start_times) else None
        if previous is not None and following is not None:
            self._adjust_interval(following - previous, -1)
        if previous is not None:
            self._adjust_interval(value - previous, 1)
        if following is not None:
            self._adjust_interval(following - value, 1)
        self.start_times.insert(index, value)

    def _remove_start(self, value: float) -> None:
        index = bisect.bisect_left(self.start_times, value)
        if index >= len(self.start_times) or self.start_times[index] != value:
            raise ValueError("scan context start-time index is inconsistent")
        previous = self.start_times[index - 1] if index else None
        following = (
            self.start_times[index + 1] if index + 1 < len(self.start_times) else None
        )
        if previous is not None:
            self._adjust_interval(value - previous, -1)
        if following is not None:
            self._adjust_interval(following - value, -1)
        if previous is not None and following is not None:
            self._adjust_interval(following - previous, 1)
        self.start_times.pop(index)

    def interval_metrics(self) -> tuple[float | None, float | None, float]:
        interval_count = len(self.start_times) - 1
        if interval_count <= 0:
            return None, None, 0.0
        mean = self.interval_sum / interval_count
        variance = max(0.0, self.interval_square_sum / interval_count - mean * mean)
        std = math.sqrt(variance)
        cv = std / mean if mean > 0 else None
        burstiness = (std - mean) / (std + mean) if std + mean > 0 else 0.0
        return mean, cv, max(-1.0, min(1.0, burstiness))

    def adjust(self, item: ScanSessionObservationV2, delta: int) -> None:
        self.count += delta
        self.probe_count += delta * int(item.probe_like)
        self.packet_count += delta * item.packet_count
        self.syn_count += delta * item.tcp_syn_count
        self.rst_count += delta * item.tcp_rst_count
        self.response_count += delta * int(item.responder_packet_count > 0)
        self.destinations[item.destination_node_id] += delta
        self.ports[item.destination_port] += delta
        if self.destinations[item.destination_node_id] <= 0:
            self.destinations.pop(item.destination_node_id, None)
        if self.ports[item.destination_port] <= 0:
            self.ports.pop(item.destination_port, None)
        if delta > 0:
            self._insert_start(item.timestamp_start)
        else:
            self._remove_start(item.timestamp_start)


def _scan_context(
    target: ScanSessionObservationV2,
    state: _SourceWindow,
    *,
    horizon_seconds: int,
) -> ScanContextV2:
    count = max(0, state.count)
    destination_count = len(state.destinations)
    port_count = len(state.ports)
    probe_ratio = state.probe_count / count if count else 0.0
    vertical = bool(
        target.probe_like
        and count >= MIN_SCAN_PRIOR_SESSIONS
        and port_count >= MIN_SCAN_DIVERSITY
        and destination_count <= MAX_SCAN_OPPOSITE_DIVERSITY
        and probe_ratio >= MIN_SCAN_PROBE_RATIO
    )
    horizontal = bool(
        target.probe_like
        and count >= MIN_SCAN_PRIOR_SESSIONS
        and destination_count >= MIN_SCAN_DIVERSITY
        and port_count <= MAX_SCAN_OPPOSITE_DIVERSITY
        and probe_ratio >= MIN_SCAN_PROBE_RATIO
    )
    mean, cv, burstiness = state.interval_metrics()
    concentration = max(state.destinations.values(), default=0) / count if count else 0.0
    return ScanContextV2(
        horizon_seconds=horizon_seconds,
        current_probe_like=target.probe_like,
        prior_same_source_session_count=count,
        connection_rate=count / horizon_seconds,
        packet_rate=state.packet_count / horizon_seconds,
        distinct_destination_count=destination_count,
        distinct_destination_port_count=port_count,
        syn_count=max(0, state.syn_count),
        syn_ratio=min(1.0, max(0, state.syn_count) / max(1, state.packet_count)),
        rst_count=max(0, state.rst_count),
        response_ratio=min(1.0, max(0, state.response_count) / max(1, count)),
        short_or_incomplete_ratio=min(1.0, max(0, state.probe_count) / max(1, count)),
        target_concentration=concentration,
        inter_arrival_mean=mean,
        inter_arrival_cv=cv,
        burstiness=burstiness,
        vertical_scan_supported=vertical,
        horizontal_scan_supported=horizontal,
        same_service_multi_host_probe=horizontal,
    )


def build_past_only_scan_context_v2(
    sessions: Sequence[ScanSessionObservationV2],
    *,
    horizons_seconds: Sequence[int] = SALVAGE_HORIZONS_SECONDS,
) -> dict[str, tuple[ScanContextV2, ...]]:
    """Build strict same-source scan contexts from sessions ending before target.

    No class label, capture name, split role or model result participates in the
    decision. ``partition_id`` is only a locality boundary and is not emitted.
    """

    horizons = tuple(horizons_seconds)
    if not horizons or any(value not in SALVAGE_HORIZONS_SECONDS for value in horizons):
        raise ValueError("scan horizons must be selected from 10/60/180/300")
    record_ids = [item.record_id for item in sessions]
    if len(record_ids) != len(set(record_ids)):
        raise ValueError("scan sessions require unique record IDs")

    grouped: dict[tuple[str, str], list[ScanSessionObservationV2]] = defaultdict(list)
    for item in sessions:
        grouped[(item.observation_scope_id, item.partition_id)].append(item)

    output: dict[str, list[ScanContextV2]] = defaultdict(list)
    for group in grouped.values():
        targets = sorted(group, key=lambda item: (item.timestamp_start, item.record_id))
        ended = sorted(group, key=lambda item: (item.timestamp_end, item.record_id))
        for horizon in horizons:
            states: dict[str, _SourceWindow] = defaultdict(_SourceWindow)
            lower_cursor = upper_cursor = 0
            for target in targets:
                while (
                    upper_cursor < len(ended)
                    and ended[upper_cursor].timestamp_end < target.timestamp_start
                ):
                    item = ended[upper_cursor]
                    states[item.source_node_id].adjust(item, 1)
                    upper_cursor += 1
                lower = target.timestamp_start - horizon
                while (
                    lower_cursor < upper_cursor
                    and ended[lower_cursor].timestamp_end < lower
                ):
                    item = ended[lower_cursor]
                    states[item.source_node_id].adjust(item, -1)
                    lower_cursor += 1
                output[target.record_id].append(
                    _scan_context(
                        target,
                        states[target.source_node_id],
                        horizon_seconds=horizon,
                    )
                )

    return {record_id: tuple(values) for record_id, values in output.items()}


def strongest_relation_context(
    contexts: Sequence[RelationGraphContextV2],
) -> RelationGraphContextV2 | None:
    supported = [item for item in contexts if item.local_network_relation_anomaly]
    return min(supported, key=lambda item: item.horizon_seconds) if supported else None


def strongest_scan_context(contexts: Sequence[ScanContextV2]) -> ScanContextV2 | None:
    supported = [item for item in contexts if item.scan_supported]
    return min(supported, key=lambda item: item.horizon_seconds) if supported else None
