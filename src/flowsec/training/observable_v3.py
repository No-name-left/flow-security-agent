from __future__ import annotations

import ipaddress
import json
import math
from collections import Counter, defaultdict, deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from statistics import fmean, pstdev
from typing import Any

from .capture_wide_signal import session_mechanism_signals
from .evidence_salvage import application_semantics, payload_semantics


OBSERVABLE_DATASET_VERSION = "OBSERVABLE_DATASET_V3"
EVIDENCE_VERSION = "EVIDENCE_V2"
BASIC_VERSION = "BASIC_V2"
ELIGIBILITY_POLICY_VERSION = "FINE_CLASS_OBSERVATION_ELIGIBILITY_V2"
TEMPORAL_VERSION = "TEMPORAL_EVIDENCE_V2"
RELATION_VERSION = "RELATION_EVIDENCE_V2"
APPLICATION_VERSION = "APPLICATION_EVIDENCE_V2"
PACKET_PAYLOAD_VERSION = "PACKET_ALIGNED_SANITIZED_PAYLOAD_V2"

MAIN_CLASS_CANDIDATES = (
    "Normal",
    "DDoS_HTTP",
    "DDoS_TCP",
    "MITM",
    "Password",
    "Port_Scanning",
    "SQL_injection",
    "Vulnerability_scanner",
)

TEMPORAL_HORIZONS_SECONDS = (10, 60, 180, 300)
EVIDENCE_FAMILIES = frozenset(
    {"PACKET_PAYLOAD", "APPLICATION", "TEMPORAL", "RELATION", "KNOWLEDGE"}
)
ELIGIBILITY_CLASSES = frozenset(
    {
        "DIRECT",
        "CONTEXTUAL",
        "GENERIC_BACKGROUND",
        "NETWORK_UNOBSERVABLE",
        "WRONG_GRANULARITY",
        "LABEL_PROPAGATION_ONLY",
    }
)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _json_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def is_unicast_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not (
        address.is_multicast
        or address.is_unspecified
        or address.is_loopback
        or str(address) in {"255.255.255.255"}
    )


def interval_statistics(values: Iterable[float]) -> dict[str, float | int | None]:
    ordered = sorted(float(value) for value in values)
    # Simultaneous session starts are legitimate zero-length inter-arrivals and
    # carry useful burst information.  Dropping them would systematically make
    # dense floods look less bursty.
    intervals = [right - left for left, right in zip(ordered, ordered[1:])]
    if not intervals:
        return {
            "interval_count": 0,
            "interval_mean_seconds": None,
            "interval_std_seconds": None,
            "interval_cv": None,
        }
    mean = fmean(intervals)
    std = pstdev(intervals) if len(intervals) > 1 else 0.0
    return {
        "interval_count": len(intervals),
        "interval_mean_seconds": mean,
        "interval_std_seconds": std,
        "interval_cv": std / mean if mean > 0 else None,
    }


def _frequency_values(value: Any, *, upper: bool = False) -> Counter[str]:
    """Normalize bounded per-session URI/method summaries into a Counter."""

    if value is None:
        return Counter()
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            value = [value]
    if isinstance(value, Mapping):
        items = value.items()
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        items = Counter(str(item) for item in value).items()
    else:
        items = ((str(value), 1),)
    result: Counter[str] = Counter()
    for raw_key, raw_count in items:
        key = str(raw_key).upper() if upper else str(raw_key)
        count = max(0, _int(raw_count))
        if key and count:
            result[key] += count
    return result


def _repeat_ratio(counter: Counter[str], total: int) -> float:
    return 0.0 if total <= 0 else max(0.0, 1.0 - len(counter) / total)


def label_free_session_signals(session: Mapping[str, Any]) -> frozenset[str]:
    """Return model-safe mechanism signals without consulting a class label."""

    prepared = dict(session)
    prepared["payload_semantics"] = sorted(
        payload_semantics(_json_values(session.get("sanitized_payload_fragments")))
    )
    application = {
        "protocol": str(session.get("application_protocol") or ""),
        "observations": session.get("application_observations") or (),
    }
    prepared["application_semantics"] = sorted(application_semantics(application))
    signals = set(session_mechanism_signals(prepared))

    packet_count = max(0, _int(session.get("packet_count")))
    request_count = max(0, _int(session.get("request_count")))
    syn = max(0, _int(session.get("tcp_syn")))
    syn_ack = max(0, _int(session.get("tcp_synack")))
    ack = max(0, _int(session.get("tcp_ack")))
    if packet_count and syn / packet_count >= 0.75:
        signals.add("high_syn_ratio")
    if syn and syn_ack == 0:
        signals.add("incomplete_handshake")
    if syn_ack or ack or (
        _int(session.get("initiator_packets")) and _int(session.get("responder_packets"))
    ):
        signals.add("established_exchange")
    if request_count:
        signals.add("http_activity")
    if request_count >= 4:
        signals.add("repeated_request_in_session")
    if _int(session.get("distinct_uri_shape_count")) >= 3:
        signals.add("uri_diversity_in_session")
    if _int(session.get("distinct_method_count")) >= 2:
        signals.add("method_diversity_in_session")
    if packet_count <= 4 and _float(session.get("duration")) <= 2.0:
        signals.add("short_session")
    return frozenset(signals)


@dataclass(slots=True)
class _WindowState:
    horizon: int
    rows: deque[Mapping[str, Any]] = field(default_factory=deque)
    packet_count: int = 0
    byte_count: int = 0
    syn_count: int = 0
    synack_count: int = 0
    rst_count: int = 0
    ack_count: int = 0
    tcp_session_count: int = 0
    completed_handshake_count: int = 0
    incomplete_count: int = 0
    request_count: int = 0
    auth_count: int = 0
    sql_count: int = 0
    probe_count: int = 0
    initiator_bytes: int = 0
    responder_bytes: int = 0
    destination_counts: Counter[str] = field(default_factory=Counter)
    destination_http_counts: Counter[str] = field(default_factory=Counter)
    source_counts: Counter[str] = field(default_factory=Counter)
    source_destination_counts: Counter[tuple[str, str]] = field(default_factory=Counter)
    destination_source_counts: Counter[tuple[str, str]] = field(default_factory=Counter)
    source_port_counts: Counter[tuple[str, int]] = field(default_factory=Counter)
    source_destination_diversity: Counter[str] = field(default_factory=Counter)
    destination_source_diversity: Counter[str] = field(default_factory=Counter)
    source_port_diversity: Counter[str] = field(default_factory=Counter)
    relation_counts: Counter[str] = field(default_factory=Counter)
    relation_auth_counts: Counter[str] = field(default_factory=Counter)
    relation_sql_counts: Counter[str] = field(default_factory=Counter)
    relation_request_counts: Counter[str] = field(default_factory=Counter)
    relation_timestamps: dict[str, deque[float]] = field(
        default_factory=lambda: defaultdict(lambda: deque(maxlen=64))
    )
    # Interval statistics are intentionally bounded. Keeping the unbounded
    # window here makes dense captures quadratic because each target copied
    # every prior timestamp before taking the last 64.
    start_timestamps: deque[float] = field(
        default_factory=lambda: deque(maxlen=64)
    )
    uri_counts: Counter[str] = field(default_factory=Counter)
    method_counts: Counter[str] = field(default_factory=Counter)
    uri_observation_count: int = 0
    method_observation_count: int = 0

    def _adjust(self, row: Mapping[str, Any], delta: int) -> None:
        source = str(row.get("raw_initiator_ip") or "")
        destination = str(row.get("raw_responder_ip") or "")
        port = _int(row.get("raw_responder_port"))
        relation = str(row.get("communication_pair_hash") or "")
        signals = set(row.get("mechanism_signals") or ())
        http_activity = bool({"http_activity", "http_request"} & signals)
        tcp_session = bool(
            str(row.get("l4_protocol") or "").upper() == "TCP"
            or _int(row.get("tcp_syn"))
            or _int(row.get("tcp_synack"))
            or _int(row.get("tcp_rst"))
            or _int(row.get("tcp_ack"))
        )
        completed_handshake = bool(tcp_session and "established_exchange" in signals)
        uri_values = _frequency_values(
            row.get("uri_shapes", row.get("uri_shapes_json"))
        )
        method_values = _frequency_values(
            row.get("methods", row.get("http_methods_json")), upper=True
        )
        self.packet_count += delta * _int(row.get("packet_count"))
        self.byte_count += delta * _int(row.get("byte_count"))
        self.syn_count += delta * _int(row.get("tcp_syn"))
        self.synack_count += delta * _int(row.get("tcp_synack"))
        self.rst_count += delta * _int(row.get("tcp_rst"))
        self.ack_count += delta * _int(row.get("tcp_ack"))
        self.tcp_session_count += delta * int(tcp_session)
        self.completed_handshake_count += delta * int(completed_handshake)
        self.incomplete_count += delta * int(tcp_session and not completed_handshake)
        self.request_count += delta * _int(row.get("request_count"))
        self.auth_count += delta * int(
            bool({"authentication_attempt", "authentication_failure"} & signals)
        )
        self.sql_count += delta * int("sql_expression" in signals)
        self.probe_count += delta * int(
            bool(
                {
                    "probe_method",
                    "path_traversal",
                    "exploit_structure",
                    "command_structure",
                }
                & signals
            )
        )
        self.initiator_bytes += delta * _int(row.get("initiator_bytes"))
        self.responder_bytes += delta * _int(row.get("responder_bytes"))
        for counter, values in (
            (self.uri_counts, uri_values),
            (self.method_counts, method_values),
        ):
            for key, amount in values.items():
                counter[key] += delta * amount
                if counter[key] <= 0:
                    counter.pop(key, None)
        self.uri_observation_count += delta * sum(uri_values.values())
        self.method_observation_count += delta * sum(method_values.values())
        for counter, key in (
            (self.destination_counts, destination),
            (self.source_counts, source),
            (self.relation_counts, relation),
        ):
            if key and key != ("", ""):
                counter[key] += delta
                if counter[key] <= 0:
                    del counter[key]
        if destination and http_activity:
            self.destination_http_counts[destination] += delta
            if self.destination_http_counts[destination] <= 0:
                self.destination_http_counts.pop(destination, None)
        for counter, diversity, owner, key in (
            (self.source_destination_counts, self.source_destination_diversity, source, (source, destination)),
            (self.destination_source_counts, self.destination_source_diversity, destination, (destination, source)),
            (self.source_port_counts, self.source_port_diversity, source, (source, port)),
        ):
            if not owner or key == ("", ""):
                continue
            previous = counter.get(key, 0)
            current = previous + delta
            if previous == 0 and current > 0:
                diversity[owner] += 1
            elif previous > 0 and current <= 0:
                diversity[owner] -= 1
                if diversity[owner] <= 0:
                    diversity.pop(owner, None)
            if current > 0:
                counter[key] = current
            else:
                counter.pop(key, None)
        if relation:
            for counter, amount in (
                (self.relation_auth_counts, int(bool({"authentication_attempt", "authentication_failure"} & signals))),
                (self.relation_sql_counts, int("sql_expression" in signals)),
                (self.relation_request_counts, _int(row.get("request_count"))),
            ):
                counter[relation] += delta * amount
                if counter[relation] <= 0:
                    counter.pop(relation, None)

    def expire(self, timestamp: float) -> None:
        lower = timestamp - self.horizon
        while self.rows and _float(self.rows[0].get("timestamp_end")) < lower:
            row = self.rows.popleft()
            expired_start = _float(row.get("timestamp_start"))
            if self.start_timestamps and self.start_timestamps[0] == expired_start:
                self.start_timestamps.popleft()
            relation = str(row.get("communication_pair_hash") or "")
            self._adjust(row, -1)
            if relation:
                values = self.relation_timestamps.get(relation)
                if values:
                    expired_time = _float(row.get("timestamp_start"))
                    if values and values[0] == expired_time:
                        values.popleft()
                    else:
                        try:
                            values.remove(expired_time)
                        except ValueError:
                            pass
                    if not values:
                        self.relation_timestamps.pop(relation, None)

    def add(self, row: Mapping[str, Any]) -> None:
        self.rows.append(row)
        self.start_timestamps.append(_float(row.get("timestamp_start")))
        self._adjust(row, 1)
        relation = str(row.get("communication_pair_hash") or "")
        if relation:
            self.relation_timestamps[relation].append(_float(row.get("timestamp_start")))

    def context(self, row: Mapping[str, Any]) -> dict[str, Any]:
        source = str(row.get("raw_initiator_ip") or "")
        destination = str(row.get("raw_responder_ip") or "")
        relation = str(row.get("communication_pair_hash") or "")
        prior = len(self.rows)
        same_destination = self.destination_counts.get(destination, 0)
        times = list(self.relation_timestamps.get(relation, ()))
        intervals = interval_statistics(times)
        recent_starts = list(self.start_timestamps)
        inter_arrivals = interval_statistics(recent_starts)
        inter_arrival_mean = inter_arrivals["interval_mean_seconds"]
        inter_arrival_std = inter_arrivals["interval_std_seconds"]
        burstiness = (
            (float(inter_arrival_std) - float(inter_arrival_mean))
            / (float(inter_arrival_std) + float(inter_arrival_mean))
            if inter_arrival_mean is not None
            and inter_arrival_std is not None
            and float(inter_arrival_std) + float(inter_arrival_mean) > 0
            else 0.0
        )
        total_directional = self.initiator_bytes + self.responder_bytes
        tcp_sessions = max(0, self.tcp_session_count)
        completed_handshakes = min(tcp_sessions, max(0, self.completed_handshake_count))
        incomplete_handshakes = min(tcp_sessions, max(0, self.incomplete_count))
        return {
            "version": TEMPORAL_VERSION,
            "schema_version": TEMPORAL_VERSION,
            "horizon_seconds": self.horizon,
            "strictly_past_only": True,
            "past_only": True,
            "prior_session_count": prior,
            "connection_rate": prior / self.horizon,
            "session_rate": prior / self.horizon,
            "latest_context_age_seconds": (
                max(
                    0.0,
                    _float(row.get("timestamp_start"))
                    - _float(self.rows[-1].get("timestamp_end")),
                )
                if self.rows
                else None
            ),
            "packet_rate": self.packet_count / self.horizon,
            "byte_rate": self.byte_count / self.horizon,
            "syn_count": self.syn_count,
            "syn_ratio": min(1.0, self.syn_count / max(1, self.packet_count)),
            "syn_rate": self.syn_count / self.horizon,
            "synack_count": self.synack_count,
            "rst_count": self.rst_count,
            "ack_count": self.ack_count,
            "handshake_completion_ratio": (
                completed_handshakes / tcp_sessions if tcp_sessions else 0.0
            ),
            "incomplete_handshake_ratio": (
                incomplete_handshakes / tcp_sessions if tcp_sessions else 0.0
            ),
            "same_destination_prior_count": same_destination,
            "same_destination_http_activity_count": self.destination_http_counts.get(
                destination, 0
            ),
            "destination_concentration": same_destination / max(1, prior),
            "source_fan_in": self.destination_source_diversity.get(destination, 0),
            "destination_fan_out": self.source_destination_diversity.get(source, 0),
            "port_diversity": self.source_port_diversity.get(source, 0),
            "same_relation_prior_count": self.relation_counts.get(relation, 0),
            "same_relation_auth_count": self.relation_auth_counts.get(relation, 0),
            "same_relation_sql_count": self.relation_sql_counts.get(relation, 0),
            "same_relation_request_count": self.relation_request_counts.get(relation, 0),
            "request_count": self.request_count,
            "application_request_count": self.request_count,
            "auth_event_count": self.auth_count,
            "authentication_request_count": self.auth_count,
            "probe_event_count": self.probe_count,
            "burstiness": burstiness,
            "inter_arrival_mean": inter_arrival_mean,
            "inter_arrival_std": inter_arrival_std,
            "inter_arrival_cv": inter_arrivals["interval_cv"],
            "uri_repetition_ratio": _repeat_ratio(
                self.uri_counts, self.uri_observation_count
            ),
            "method_repetition_ratio": _repeat_ratio(
                self.method_counts, self.method_observation_count
            ),
            "directional_byte_asymmetry": (
                abs(self.initiator_bytes - self.responder_bytes) / total_directional
                if total_directional
                else 0.0
            ),
            **intervals,
        }


def build_strict_past_temporal_contexts(
    rows: Sequence[Mapping[str, Any]],
    *,
    allow_prior_cross_split: bool = False,
) -> list[dict[str, Any]]:
    """Build four split-local contexts from sessions that ended before target start."""

    sample_ids: set[str] = set()
    for row in rows:
        sample_id = str(row.get("sample_id") or "")
        if not sample_id or sample_id in sample_ids:
            raise ValueError("Temporal-v2 rows require unique non-empty sample identities")
        sample_ids.add(sample_id)
        start = _float(row.get("timestamp_start"), math.nan)
        end = _float(row.get("timestamp_end"), math.nan)
        if not math.isfinite(start) or not math.isfinite(end) or end < start:
            raise ValueError("Temporal-v2 rows require finite ordered timestamps")
    locality_fields = ["capture_id_backend_only", "observation_scope_id"]
    if not allow_prior_cross_split:
        locality_fields.insert(0, "split")
    for field_name in locality_fields:
        values = {
            str(row[field_name])
            for row in rows
            if row.get(field_name) not in (None, "")
        }
        if len(values) > 1:
            raise ValueError(f"Temporal-v2 input must be local to one {field_name}")

    ordered = sorted(
        rows,
        key=lambda row: (
            _float(row.get("timestamp_start")),
            str(row.get("sample_id")),
        ),
    )
    completed = sorted(
        rows,
        key=lambda row: (
            _float(row.get("timestamp_end")),
            _float(row.get("timestamp_start")),
            str(row.get("sample_id")),
        ),
    )
    windows = {horizon: _WindowState(horizon) for horizon in TEMPORAL_HORIZONS_SECONDS}
    output: list[dict[str, Any]] = []
    cursor = 0
    completed_cursor = 0
    while cursor < len(ordered):
        timestamp = _float(ordered[cursor].get("timestamp_start"))
        end = cursor + 1
        while end < len(ordered) and _float(ordered[end].get("timestamp_start")) == timestamp:
            end += 1
        group = ordered[cursor:end]
        while (
            completed_cursor < len(completed)
            and _float(completed[completed_cursor].get("timestamp_end")) < timestamp
        ):
            prior = completed[completed_cursor]
            for window in windows.values():
                window.add(prior)
            completed_cursor += 1
        for window in windows.values():
            window.expire(timestamp)
        for row in group:
            output.append(
                {
                    "sample_id": str(row["sample_id"]),
                    "split": str(row["split"]),
                    "timestamp_start_backend_only": timestamp,
                    "contexts": {str(h): windows[h].context(row) for h in TEMPORAL_HORIZONS_SECONDS},
                }
            )
        cursor = end
    return output


def _strongest_context(contexts: Mapping[str, Mapping[str, Any]]) -> Mapping[str, Any]:
    return contexts.get("60") or contexts.get("300") or contexts.get("180") or contexts.get("10") or {}


def _any_context(
    contexts: Mapping[str, Mapping[str, Any]], predicate: Any
) -> bool:
    return any(predicate(value) for value in contexts.values())


def assess_fine_observation_eligibility(
    fine_label: str,
    session: Mapping[str, Any],
    *,
    temporal_contexts: Mapping[str, Mapping[str, Any]],
    relation_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply the frozen label after extracting label-free evidence.

    This function never accepts capture name, path, dataset identity or future
    context.  It returns auditable evidence reasons rather than silently using
    capture membership.
    """

    if fine_label not in MAIN_CLASS_CANDIDATES:
        raise ValueError(f"unsupported v3 main-class candidate: {fine_label}")
    packet_count = _int(session.get("packet_count"))
    if packet_count <= 0:
        return _assessment(
            "NETWORK_UNOBSERVABLE",
            reasons=("no_matched_packet_observation",),
            families=(),
            basic=False,
        )
    signals = set(session.get("mechanism_signals") or label_free_session_signals(session))
    basic_signals = set(session.get("basic_mechanism_signals") or ())
    relation = dict(relation_evidence or {})
    reasons: list[str] = []
    families: set[str] = set()
    direct = contextual = basic = False

    if fine_label == "Normal":
        direct = True
        basic = True
        reasons.append("valid_observed_normal_session")

    elif fine_label == "SQL_injection":
        direct = "sql_expression" in signals
        basic = "sql_expression" in basic_signals
        contextual = bool(
            not direct
            and "http_activity" in signals
            and _any_context(
                temporal_contexts,
                lambda value: _int(value.get("same_relation_sql_count")) > 0,
            )
        )
        if direct:
            families.update({"PACKET_PAYLOAD", "APPLICATION"})
            reasons.append("sql_syntax_or_database_error_observed_in_session")
        elif contextual:
            families.add("TEMPORAL")
            reasons.append("http_exchange_strictly_follows_same_relation_sql_observation")

    elif fine_label == "Password":
        direct = bool({"authentication_attempt", "authentication_failure"} & signals)
        basic = bool({"authentication_attempt", "authentication_failure"} & basic_signals)
        current_auth_context = bool(
            {"http_activity", "application_success_response", "authentication_failure"} & signals
        )
        contextual = bool(
            not direct
            and current_auth_context
            and _any_context(
                temporal_contexts,
                lambda value: _int(value.get("same_relation_auth_count")) > 0,
            )
        )
        if direct:
            families.update({"PACKET_PAYLOAD", "APPLICATION"})
            reasons.append("credential_or_authentication_response_observed")
        elif contextual:
            families.add("TEMPORAL")
            reasons.append("same_relation_authentication_sequence_in_strict_past")

    elif fine_label == "DDoS_TCP":
        target_tcp_syn = "high_syn_ratio" in signals or "incomplete_handshake" in signals
        contextual = target_tcp_syn and _any_context(
            temporal_contexts,
            lambda value: (
                _float(value.get("connection_rate")) >= 20.0
                and _float(value.get("destination_concentration")) >= 0.70
                and (
                    _float(value.get("syn_ratio")) >= 0.50
                    or _float(value.get("incomplete_handshake_ratio")) >= 0.70
                )
            ),
        )
        basic = bool(
            target_tcp_syn
            and _int(session.get("packet_count")) >= 20
            and _int(session.get("tcp_syn")) / max(1, _int(session.get("packet_count"))) >= 0.75
        )
        direct = basic
        if direct:
            reasons.append("single_session_contains_repeated_syn_flood_mechanism")
        elif contextual:
            families.add("TEMPORAL")
            reasons.append("syn_handshake_flood_rate_and_target_concentration_in_strict_past")

    elif fine_label == "DDoS_HTTP":
        http = "http_activity" in signals
        http_service_compatible = http or _int(session.get("raw_responder_port")) in {
            80,
            8000,
            8080,
            8888,
        }
        contextual = http_service_compatible and _any_context(
            temporal_contexts,
            lambda value: (
                _float(value.get("connection_rate")) >= 5.0
                and _float(value.get("destination_concentration")) >= 0.50
                and _int(value.get("same_destination_http_activity_count")) >= 3
            ),
        )
        basic = http and (
            _int(session.get("request_count")) >= 4
            or "repeated_request_in_session" in basic_signals
        )
        direct = basic
        if direct:
            families.add("APPLICATION")
            reasons.append("repeated_http_requests_observed_inside_target_session")
        elif contextual:
            families.update({"TEMPORAL", "APPLICATION"})
            reasons.append("observed_http_exchange_in_strict_past_connection_flood_and_target_concentration")

    elif fine_label == "Port_Scanning":
        target_probe = bool({"short_session", "incomplete_handshake", "reset_observed"} & signals)
        contextual = target_probe and _any_context(
            temporal_contexts,
            lambda value: (
                _float(value.get("connection_rate")) >= 1.0
                and (
                    _int(value.get("port_diversity")) >= 10
                    or _int(value.get("destination_fan_out")) >= 10
                )
            ),
        )
        direct = "probe_method" in signals
        basic = "probe_method" in basic_signals
        if direct:
            families.add("APPLICATION")
            reasons.append("explicit_application_probe_method_observed")
        elif contextual:
            families.update({"TEMPORAL", "RELATION"})
            reasons.append("short_or_failed_connection_in_strict_past_port_or_target_sweep")

    elif fine_label == "Vulnerability_scanner":
        probe_signals = {
            "path_traversal",
            "script_content",
            "probe_method",
            "command_structure",
            "exploit_structure",
        }
        direct = bool(probe_signals & signals)
        basic = bool(probe_signals & basic_signals)
        target_probe = bool({"http_activity", "short_session", "incomplete_handshake"} & signals)
        contextual = bool(
            not direct
            and target_probe
            and _any_context(
                temporal_contexts,
                lambda value: (
                    _int(value.get("probe_event_count")) >= 3
                    or _int(value.get("port_diversity")) >= 8
                    or _int(value.get("destination_fan_out")) >= 8
                ),
            )
        )
        if direct:
            families.update({"PACKET_PAYLOAD", "APPLICATION"})
            reasons.append("scanner_or_exploit_probe_structure_observed")
        elif contextual:
            families.update({"TEMPORAL", "RELATION"})
            reasons.append("probe_like_session_in_strict_past_scanner_sequence")

    else:  # MITM
        linked = bool(relation.get("target_endpoint_linked"))
        conflict = bool(
            relation.get("arp_ip_multiple_macs")
            or relation.get("arp_mac_multiple_ips")
            or relation.get("arp_mapping_change")
            or relation.get("dns_mapping_change")
        )
        endpoints_unicast = bool(
            is_unicast_address(str(session.get("raw_initiator_ip") or ""))
            and is_unicast_address(str(session.get("raw_responder_ip") or ""))
        )
        meaningful_exchange = bool(
            "established_exchange" in signals
            or (_int(session.get("initiator_packets")) and _int(session.get("responder_packets")))
        )
        contextual = linked and conflict and endpoints_unicast and meaningful_exchange
        if contextual:
            families.add("RELATION")
            reasons.append("time_linked_arp_or_dns_mapping_anomaly_on_target_endpoints")

    if direct or contextual:
        return _assessment(
            "DIRECT" if direct else "CONTEXTUAL",
            reasons=reasons,
            families=families,
            basic=basic,
        )
    if fine_label == "MITM":
        return _assessment(
            "WRONG_GRANULARITY",
            reasons=("no_time_linked_relation_anomaly_on_meaningful_target_session",),
            families=(),
            basic=False,
        )
    return _assessment(
        "GENERIC_BACKGROUND",
        reasons=("capture_label_without_class_relevant_target_or_strict_past_evidence",),
        families=(),
        basic=False,
    )


def _assessment(
    eligibility_class: str,
    *,
    reasons: Iterable[str],
    families: Iterable[str],
    basic: bool,
) -> dict[str, Any]:
    if eligibility_class not in ELIGIBILITY_CLASSES:
        raise ValueError(f"invalid eligibility class: {eligibility_class}")
    family_values = tuple(sorted(set(families)))
    unknown = set(family_values) - EVIDENCE_FAMILIES
    if unknown:
        raise ValueError(f"invalid evidence families: {sorted(unknown)}")
    eligible = eligibility_class in {"DIRECT", "CONTEXTUAL"}
    return {
        "eligibility_policy_version": ELIGIBILITY_POLICY_VERSION,
        "eligibility_class": eligibility_class,
        "full_observational_sufficient": eligible,
        "basic_sufficient": bool(basic and eligible),
        "supporting_evidence_families": family_values,
        "supporting_reasons": tuple(reasons),
        "exclusion_reason": None if eligible else eligibility_class,
        "classification_ce_eligible": eligible,
        "label_propagation_only": eligibility_class
        in {"GENERIC_BACKGROUND", "LABEL_PROPAGATION_ONLY"},
    }


def validate_temporal_context(value: Mapping[str, Any]) -> None:
    if value.get("version") != TEMPORAL_VERSION:
        raise ValueError("unexpected Temporal-v2 version")
    if value.get("schema_version") != TEMPORAL_VERSION:
        raise ValueError("unexpected Temporal-v2 schema version")
    if value.get("strictly_past_only") is not True:
        raise ValueError("Temporal-v2 must be strictly past-only")
    if value.get("past_only") is not True:
        raise ValueError("Temporal-v2 contract must be past-only")
    if _int(value.get("horizon_seconds")) not in TEMPORAL_HORIZONS_SECONDS:
        raise ValueError("invalid Temporal-v2 horizon")
    for field_name in (
        "connection_rate",
        "session_rate",
        "packet_rate",
        "byte_rate",
        "syn_rate",
    ):
        value_number = _float(value.get(field_name), math.nan)
        if not math.isfinite(value_number) or value_number < 0:
            raise ValueError(f"invalid Temporal-v2 field: {field_name}")
    if not math.isclose(
        _float(value.get("connection_rate"), math.nan),
        _float(value.get("session_rate"), math.nan),
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        raise ValueError("Temporal-v2 connection/session rates disagree")
    for field_name in (
        "syn_ratio",
        "handshake_completion_ratio",
        "incomplete_handshake_ratio",
        "destination_concentration",
        "directional_byte_asymmetry",
        "uri_repetition_ratio",
        "method_repetition_ratio",
    ):
        value_number = _float(value.get(field_name), math.nan)
        if not math.isfinite(value_number) or not 0.0 <= value_number <= 1.0:
            raise ValueError(f"invalid Temporal-v2 ratio: {field_name}")
    burstiness = _float(value.get("burstiness"), math.nan)
    if not math.isfinite(burstiness) or not -1.0 <= burstiness <= 1.0:
        raise ValueError("invalid Temporal-v2 burstiness")
    for field_name in (
        "latest_context_age_seconds",
        "inter_arrival_mean",
        "inter_arrival_std",
        "inter_arrival_cv",
        "interval_mean_seconds",
        "interval_std_seconds",
        "interval_cv",
    ):
        if value.get(field_name) is None:
            continue
        value_number = _float(value.get(field_name), math.nan)
        if not math.isfinite(value_number) or value_number < 0:
            raise ValueError(f"invalid Temporal-v2 optional field: {field_name}")
    if _float(value.get("handshake_completion_ratio")) + _float(
        value.get("incomplete_handshake_ratio")
    ) > 1.0 + 1e-12:
        raise ValueError("Temporal-v2 handshake ratios exceed one")
