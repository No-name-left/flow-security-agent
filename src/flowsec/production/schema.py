from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Iterable


CANONICAL_SCHEMA_VERSION = "canonical_session_record_v1"
INITIAL_VIEW_VERSION = "primary_no_service_v1"
NO_SERVICE_VIEW_VERSION = "no_service_v1"
SERVICE_DIAGNOSTIC_VIEW_VERSION = "derived_service_diagnostic_v1"
PROHIBITED_FIELDS_VERSION = "prohibited_model_fields_v1"
NEAR_SIGNATURE_RULE = {
    "id": "initial_model_view_recursive_float_round_v1",
    "input": INITIAL_VIEW_VERSION,
    "operation": "recursively round floating-point values",
    "decimal_places": 2,
    "integer_values_unchanged": True,
}

PROHIBITED_MODEL_FIELDS = (
    "dataset_name",
    "scenario_or_capture_id",
    "source_file",
    "source_path",
    "source_sha256",
    "timestamp_start",
    "timestamp_end",
    "absolute_time",
    "raw_ip",
    "raw_initiator_ip",
    "raw_responder_ip",
    "raw_port",
    "raw_initiator_port",
    "raw_responder_port",
    "raw_endpoint_identifier",
    "stable_device_id",
    "attack_script_id",
    "fixed_payload",
    "fixed_uri",
    "fixed_topic",
    "fixed_username",
)

MODEL_FEATURE_WHITELIST = (
    "label_schema_id",
    "packet_sequence.direction",
    "packet_sequence.packet_length",
    "packet_sequence.relative_iat",
    "packet_sequence.l3_protocol",
    "packet_sequence.l4_protocol",
    "packet_sequence.tcp_flags",
    "session_summary.duration",
    "session_summary.initiator_packets",
    "session_summary.responder_packets",
    "session_summary.initiator_bytes",
    "session_summary.responder_bytes",
    "session_summary.packet_length_stats",
    "session_summary.iat_stats",
    "session_summary.handshake_state",
    "capabilities",
    "missing_fields",
)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def stable_sample_id(
    *,
    dataset_version: str,
    source_content_hash: str,
    canonical_session_identity: Iterable[Any],
    start_microseconds: int,
    deterministic_ordinal: int,
) -> str:
    """Return a path-independent, non-reversible ID tied to immutable source content."""

    identity_hash = content_hash(list(canonical_session_identity))
    material = {
        "algorithm": "flowsec_sample_id_v1",
        "dataset_version": dataset_version,
        "source_content_hash": source_content_hash,
        "canonical_session_identity_hash": identity_hash,
        "start_microseconds": int(start_microseconds),
        "deterministic_ordinal": int(deterministic_ordinal),
    }
    return "fs1_" + content_hash(material)[:40]


@dataclass(slots=True)
class OnlineStats:
    count: int = 0
    mean: float = 0.0
    m2: float = 0.0
    minimum: float = math.inf
    maximum: float = -math.inf

    def add(self, value: float) -> None:
        value = float(value)
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        self.m2 += delta * (value - self.mean)
        self.minimum = min(self.minimum, value)
        self.maximum = max(self.maximum, value)

    def as_dict(self) -> dict[str, float]:
        if not self.count:
            return {"min": 0.0, "max": 0.0, "mean": 0.0, "std": 0.0}
        return {
            "min": float(self.minimum),
            "max": float(self.maximum),
            "mean": float(self.mean),
            "std": math.sqrt(self.m2 / self.count) if self.count > 1 else 0.0,
        }


@dataclass(slots=True)
class Packet:
    frame_number: int
    timestamp: float
    packet_length: int
    src: str
    dst: str
    l3_protocol: str
    l4_protocol: str
    sport: int
    dport: int
    tcp_flags: int


@dataclass(slots=True)
class SessionAccumulator:
    canonical_key: tuple[Any, ...]
    initiator_ip: str
    responder_ip: str
    initiator_port: int
    responder_port: int
    l3_protocol: str
    l4_protocol: str
    start: float
    end: float
    first_frame_number: int
    last_frame_number: int
    first_packets: list[dict[str, Any]] = field(default_factory=list)
    initiator_packets: int = 0
    responder_packets: int = 0
    initiator_bytes: int = 0
    responder_bytes: int = 0
    packet_length_stats: OnlineStats = field(default_factory=OnlineStats)
    iat_stats: OnlineStats = field(default_factory=OnlineStats)
    flags_or: int = 0
    syn_seen: bool = False
    synack_seen: bool = False
    last_timestamp: float | None = None

    def add(self, packet: Packet, packet_limit: int = 16) -> None:
        direction = "initiator_to_responder" if (
            packet.src == self.initiator_ip and packet.sport == self.initiator_port
        ) else "responder_to_initiator"
        if direction == "initiator_to_responder":
            self.initiator_packets += 1
            self.initiator_bytes += packet.packet_length
        else:
            self.responder_packets += 1
            self.responder_bytes += packet.packet_length
        relative_iat = 0.0 if self.last_timestamp is None else max(
            0.0, packet.timestamp - self.last_timestamp
        )
        if self.last_timestamp is not None:
            self.iat_stats.add(relative_iat)
        self.packet_length_stats.add(packet.packet_length)
        if len(self.first_packets) < packet_limit:
            self.first_packets.append(
                {
                    "direction": direction,
                    "packet_length": packet.packet_length,
                    "relative_iat": round(relative_iat, 6),
                    "l3_protocol": packet.l3_protocol,
                    "l4_protocol": packet.l4_protocol,
                    "tcp_flags": packet.tcp_flags if packet.l4_protocol == "TCP" else None,
                }
            )
        self.end = max(self.end, packet.timestamp)
        self.last_timestamp = packet.timestamp
        self.last_frame_number = packet.frame_number
        self.flags_or |= packet.tcp_flags
        self.syn_seen = self.syn_seen or bool(packet.tcp_flags & 0x02 and not packet.tcp_flags & 0x10)
        self.synack_seen = self.synack_seen or bool(packet.tcp_flags & 0x02 and packet.tcp_flags & 0x10)

    @property
    def packet_count(self) -> int:
        return self.initiator_packets + self.responder_packets

    @property
    def byte_count(self) -> int:
        return self.initiator_bytes + self.responder_bytes

    @property
    def handshake_state(self) -> str:
        if self.syn_seen and self.synack_seen and self.flags_or & (0x01 | 0x04):
            return "ESTABLISHED_CLOSED"
        if self.syn_seen and self.synack_seen:
            return "ESTABLISHED_OPEN"
        if self.syn_seen:
            return "INCOMPLETE_HANDSHAKE"
        if self.flags_or & 0x04:
            return "RESET"
        return "NOT_APPLICABLE_OR_UNOBSERVED"

    def summary(self, service_category: str, service_source: str) -> dict[str, Any]:
        return {
            "duration": max(0.0, self.end - self.start),
            "initiator_packets": self.initiator_packets,
            "responder_packets": self.responder_packets,
            "initiator_bytes": self.initiator_bytes,
            "responder_bytes": self.responder_bytes,
            "packet_length_stats": self.packet_length_stats.as_dict(),
            "iat_stats": self.iat_stats.as_dict(),
            "handshake_state": self.handshake_state,
            "service_category": service_category,
            "service_category_source": service_source,
        }


def initial_model_view(
    *,
    label_schema_id: str,
    packets: list[dict[str, Any]],
    summary: dict[str, Any],
    capabilities: list[str],
    missing_fields: list[str],
    include_service: bool = False,
) -> dict[str, Any]:
    safe_summary = {key: value for key, value in summary.items() if not key.startswith("service_")}
    if include_service:
        safe_summary["service_category"] = summary["service_category"]
        safe_summary["service_category_source"] = summary["service_category_source"]
    return {
        "label_schema_id": label_schema_id,
        "packet_sequence": packets[:8],
        "session_summary": safe_summary,
        "capabilities": sorted(capabilities),
        "missing_fields": sorted(missing_fields),
    }


def model_view_violations(view: dict[str, Any], raw_identity_values: Iterable[str] = ()) -> list[str]:
    serialized = canonical_json(view).lower()
    violations = [field for field in PROHIBITED_MODEL_FIELDS if field.lower() in serialized]
    for value in raw_identity_values:
        token = str(value).strip().lower()
        if token and token in serialized:
            violations.append("raw_identity_value")
    return sorted(set(violations))
