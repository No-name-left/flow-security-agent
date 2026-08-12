from __future__ import annotations

import re
from collections import Counter, defaultdict
from enum import StrEnum
from statistics import fmean, pstdev
from typing import Any, Iterable, Literal, Mapping, Sequence

from pydantic import Field, field_validator, model_validator

from .contracts import SANITIZED_PAYLOAD_VERSION, FrozenModel
from .evidence import application_observation_from_frame, decode_hex_payload, sanitize_payload_text


BASIC_EVIDENCE_V2_VERSION = "BASIC_EVIDENCE_V2"
PACKET_ALIGNED_PAYLOAD_V2_VERSION = "PACKET_ALIGNED_SANITIZED_PAYLOAD_V2"
APPLICATION_EVIDENCE_V2_VERSION = "APPLICATION_EVIDENCE_V2"
TEMPORAL_EVIDENCE_V2_VERSION = "TEMPORAL_EVIDENCE_V2"
RELATION_EVIDENCE_V2_VERSION = "RELATION_EVIDENCE_V2"
TEMPORAL_HORIZONS_SECONDS = (10, 60, 180, 300)

_SAMPLE_ID = re.compile(r"^fs1_[0-9a-f]{40}$")
_HEX_PAYLOAD = re.compile(r"^[0-9a-fA-F: ]+$")


class PacketDirectionV2(StrEnum):
    INITIATOR_TO_RESPONDER = "initiator_to_responder"
    RESPONDER_TO_INITIATOR = "responder_to_initiator"


class DescriptiveStatsV2(FrozenModel):
    minimum: float = Field(ge=0.0, allow_inf_nan=False)
    maximum: float = Field(ge=0.0, allow_inf_nan=False)
    mean: float = Field(ge=0.0, allow_inf_nan=False)
    std: float = Field(ge=0.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_order(self) -> "DescriptiveStatsV2":
        if self.minimum > self.maximum or not self.minimum <= self.mean <= self.maximum:
            raise ValueError("descriptive statistics have an invalid min/mean/max order")
        return self


class PacketMetadataV2(FrozenModel):
    packet_index: int = Field(ge=1, le=16)
    direction: PacketDirectionV2
    relative_time: float = Field(ge=0.0, allow_inf_nan=False)
    relative_iat: float = Field(ge=0.0, allow_inf_nan=False)
    packet_length: int = Field(ge=0)
    l3_protocol: str = Field(min_length=1, max_length=24)
    l4_protocol: str = Field(min_length=1, max_length=24)
    tcp_flags: int | None = Field(default=None, ge=0, le=511)

    @model_validator(mode="after")
    def validate_tcp_flags(self) -> "PacketMetadataV2":
        if self.l4_protocol.upper() != "TCP" and self.tcp_flags is not None:
            raise ValueError("TCP flags cannot be attached to a non-TCP packet")
        return self


class PacketAlignedPayloadRowV2(FrozenModel):
    """Backend sidecar row with an explicit packet-to-payload join.

    ``session_id`` is lineage and is removed by ``model_projection``.  A
    present but non-text payload is represented by ``sanitized_payload=None``;
    it is never inferred from fragment-array order.
    """

    schema_version: Literal["PACKET_ALIGNED_SANITIZED_PAYLOAD_V2"] = (
        PACKET_ALIGNED_PAYLOAD_V2_VERSION
    )
    session_id: str = Field(repr=False)
    packet_index: int = Field(ge=1, le=65535)
    direction: PacketDirectionV2
    relative_time: float = Field(ge=0.0, allow_inf_nan=False)
    protocol: str = Field(min_length=1, max_length=24)
    payload_present: bool
    payload_length: int = Field(ge=0)
    sanitized_payload: str | None = Field(default=None, max_length=2048)
    sanitization_version: Literal["SANITIZED_PAYLOAD_V1"] = SANITIZED_PAYLOAD_VERSION

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: str) -> str:
        if not _SAMPLE_ID.fullmatch(value):
            raise ValueError("packet-aligned payload requires a canonical session identity")
        return value

    @model_validator(mode="after")
    def validate_payload_state(self) -> "PacketAlignedPayloadRowV2":
        if self.payload_present != (self.payload_length > 0):
            raise ValueError("payload_present and payload_length disagree")
        if not self.payload_present and self.sanitized_payload is not None:
            raise ValueError("a packet without payload cannot contain sanitized text")
        if self.sanitized_payload is not None:
            if not self.sanitized_payload.strip():
                raise ValueError("sanitized payload cannot be blank")
            canonical = sanitize_payload_text(self.sanitized_payload, max_chars=2048)
            if canonical != self.sanitized_payload:
                raise ValueError("packet-aligned payload is not in canonical sanitized form")
        return self

    def model_projection(self) -> "PacketAlignedPayloadProjectionV2":
        return PacketAlignedPayloadProjectionV2(
            packet_index=self.packet_index,
            direction=self.direction,
            relative_time=self.relative_time,
            protocol=self.protocol,
            payload_present=self.payload_present,
            payload_length=self.payload_length,
            sanitized_payload=self.sanitized_payload,
            sanitization_version=self.sanitization_version,
        )


class PacketAlignedPayloadProjectionV2(FrozenModel):
    packet_index: int = Field(ge=1, le=8)
    direction: PacketDirectionV2
    relative_time: float = Field(ge=0.0, allow_inf_nan=False)
    protocol: str = Field(min_length=1, max_length=24)
    payload_present: bool
    payload_length: int = Field(ge=0)
    sanitized_payload: str | None = Field(default=None, max_length=2048)
    sanitization_version: Literal["SANITIZED_PAYLOAD_V1"] = SANITIZED_PAYLOAD_VERSION

    @model_validator(mode="after")
    def validate_payload_state(self) -> "PacketAlignedPayloadProjectionV2":
        if self.payload_present != (self.payload_length > 0):
            raise ValueError("payload_present and payload_length disagree")
        if not self.payload_present and self.sanitized_payload is not None:
            raise ValueError("a packet without payload cannot contain sanitized text")
        return self


class SessionSummaryV2(FrozenModel):
    duration: float = Field(ge=0.0, allow_inf_nan=False)
    bidirectional_packet_count: int = Field(ge=1)
    bidirectional_byte_count: int = Field(ge=0)
    initiator_packets: int = Field(ge=0)
    responder_packets: int = Field(ge=0)
    initiator_bytes: int = Field(ge=0)
    responder_bytes: int = Field(ge=0)
    packet_length_statistics: DescriptiveStatsV2
    iat_statistics: DescriptiveStatsV2
    tcp_handshake_state: str = Field(min_length=1, max_length=64)
    protocol_metadata: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_totals(self) -> "SessionSummaryV2":
        if self.bidirectional_packet_count != self.initiator_packets + self.responder_packets:
            raise ValueError("bidirectional packet total disagrees with directional totals")
        if self.bidirectional_byte_count != self.initiator_bytes + self.responder_bytes:
            raise ValueError("bidirectional byte total disagrees with directional totals")
        if len(self.protocol_metadata) > 12:
            raise ValueError("Basic-v2 protocol metadata must remain bounded")
        return self


class ApplicationEvidenceV2(FrozenModel):
    schema_version: Literal["APPLICATION_EVIDENCE_V2"] = APPLICATION_EVIDENCE_V2_VERSION
    application_protocols: tuple[str, ...] = ()
    http_methods: tuple[str, ...] = ()
    http_status_codes: tuple[int, ...] = ()
    uri_shapes: tuple[str, ...] = ()
    content_types: tuple[str, ...] = ()
    request_count: int = Field(default=0, ge=0)
    response_count: int = Field(default=0, ge=0)
    request_response_structure: Literal[
        "NONE", "REQUEST_ONLY", "RESPONSE_ONLY", "BIDIRECTIONAL"
    ] = "NONE"
    auth_related_structure: bool = False
    credential_field_presence: bool = False
    scanner_probe_structure: bool = False
    truncated: bool = False

    @field_validator("http_status_codes", mode="before")
    @classmethod
    def validate_http_statuses(cls, value: Any) -> Any:
        if not isinstance(value, (tuple, list)) or any(
            isinstance(item, bool) or not isinstance(item, int) or not 100 <= item <= 599
            for item in value
        ):
            raise ValueError("HTTP status codes must be integers in 100..599")
        return value

    @model_validator(mode="after")
    def validate_bounds_and_structure(self) -> "ApplicationEvidenceV2":
        bounded = (
            self.application_protocols,
            self.http_methods,
            self.http_status_codes,
            self.uri_shapes,
            self.content_types,
        )
        if any(len(values) > 24 for values in bounded):
            raise ValueError("Application-v2 fields are bounded to 24 distinct values")
        expected = (
            "BIDIRECTIONAL"
            if self.request_count and self.response_count
            else "REQUEST_ONLY"
            if self.request_count
            else "RESPONSE_ONLY"
            if self.response_count
            else "NONE"
        )
        if self.request_response_structure != expected:
            raise ValueError("request/response structure disagrees with counts")
        if self.http_methods and not self.request_count:
            raise ValueError("HTTP methods require at least one request")
        if self.http_status_codes and not self.response_count:
            raise ValueError("HTTP statuses require at least one response")
        return self


class BasicEvidenceV2(FrozenModel):
    schema_version: Literal["BASIC_EVIDENCE_V2"] = BASIC_EVIDENCE_V2_VERSION
    session_summary: SessionSummaryV2
    first_eight_packets: tuple[PacketMetadataV2, ...]
    packet_aligned_payload: tuple[PacketAlignedPayloadProjectionV2, ...]
    cheap_application_metadata: ApplicationEvidenceV2

    @model_validator(mode="after")
    def validate_packet_alignment(self) -> "BasicEvidenceV2":
        if not 1 <= len(self.first_eight_packets) <= 8:
            raise ValueError("Basic-v2 requires one to eight packet metadata rows")
        expected = list(range(1, len(self.first_eight_packets) + 1))
        if [item.packet_index for item in self.first_eight_packets] != expected:
            raise ValueError("Basic-v2 packet metadata must be explicitly indexed and contiguous")
        if self.first_eight_packets[0].relative_iat != 0.0:
            raise ValueError("the first visible packet must have zero relative IAT")
        if len(self.first_eight_packets) > self.session_summary.bidirectional_packet_count:
            raise ValueError("visible packet rows exceed the whole-session packet count")
        if len(self.packet_aligned_payload) != len(expected):
            raise ValueError("Basic-v2 requires one payload-alignment row per visible packet")
        if [item.packet_index for item in self.packet_aligned_payload] != expected:
            raise ValueError("payload rows do not align one-to-one with packet metadata")
        for packet, payload in zip(
            self.first_eight_packets, self.packet_aligned_payload, strict=True
        ):
            if (
                packet.direction is not payload.direction
                or packet.l4_protocol.upper() != payload.protocol.upper()
                or abs(packet.relative_time - payload.relative_time) > 1e-6
            ):
                raise ValueError("payload row does not match its packet metadata row")
        return self


class TemporalSessionObservationV2(FrozenModel):
    """Label-free backend input to strict-past temporal aggregation."""

    observation_scope_id: str = Field(min_length=1, max_length=160, repr=False)
    timestamp_start: float = Field(ge=0.0, allow_inf_nan=False, repr=False)
    timestamp_end: float = Field(ge=0.0, allow_inf_nan=False, repr=False)
    source_node_id: str = Field(min_length=1, max_length=160, repr=False)
    destination_node_id: str = Field(min_length=1, max_length=160, repr=False)
    destination_port: int = Field(ge=0, le=65535, repr=False)
    packet_count: int = Field(ge=1)
    byte_count: int = Field(ge=0)
    initiator_bytes: int = Field(ge=0)
    responder_bytes: int = Field(ge=0)
    tcp_syn_count: int = Field(default=0, ge=0)
    tcp_synack_count: int = Field(default=0, ge=0)
    tcp_ack_count: int = Field(default=0, ge=0)
    tcp_rst_count: int = Field(default=0, ge=0)
    handshake_completed: bool = False
    authentication_request_count: int = Field(default=0, ge=0)
    application_request_count: int = Field(default=0, ge=0)
    uri_shapes: tuple[str, ...] = ()
    methods: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_times_and_bytes(self) -> "TemporalSessionObservationV2":
        if self.timestamp_end < self.timestamp_start:
            raise ValueError("session end precedes session start")
        if self.initiator_bytes + self.responder_bytes > self.byte_count:
            raise ValueError("directional bytes exceed total session bytes")
        if any(
            value > self.packet_count
            for value in (
                self.tcp_syn_count,
                self.tcp_synack_count,
                self.tcp_ack_count,
                self.tcp_rst_count,
            )
        ):
            raise ValueError("TCP flag counts exceed the packet count")
        if len(self.uri_shapes) > 24 or len(self.methods) > 24:
            raise ValueError("temporal application summaries must remain bounded")
        return self


class TemporalEvidenceV2(FrozenModel):
    schema_version: Literal["TEMPORAL_EVIDENCE_V2"] = TEMPORAL_EVIDENCE_V2_VERSION
    horizon_seconds: Literal[10, 60, 180, 300]
    past_only: Literal[True] = True
    prior_session_count: int = Field(ge=0)
    latest_context_age_seconds: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    session_rate: float = Field(ge=0.0, allow_inf_nan=False)
    packet_rate: float = Field(ge=0.0, allow_inf_nan=False)
    byte_rate: float = Field(ge=0.0, allow_inf_nan=False)
    syn_count: int = Field(ge=0)
    synack_count: int = Field(ge=0)
    syn_ratio: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    syn_rate: float = Field(ge=0.0, allow_inf_nan=False)
    rst_count: int = Field(ge=0)
    ack_count: int = Field(ge=0)
    handshake_completion_ratio: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    incomplete_handshake_ratio: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    destination_concentration: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    source_fan_in: int = Field(ge=0)
    destination_fan_out: int = Field(ge=0)
    port_diversity: int = Field(ge=0)
    burstiness: float = Field(ge=-1.0, le=1.0, allow_inf_nan=False)
    inter_arrival_mean: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    inter_arrival_std: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    inter_arrival_cv: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    authentication_request_count: int = Field(ge=0)
    application_request_count: int = Field(ge=0)
    uri_repetition_ratio: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    method_repetition_ratio: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    interval_cv: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    directional_byte_asymmetry: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)


class RelationTargetV2(FrozenModel):
    observation_scope_id: str = Field(min_length=1, max_length=160, repr=False)
    timestamp: float = Field(ge=0.0, allow_inf_nan=False, repr=False)
    source_ip: str = Field(min_length=1, max_length=128, repr=False)
    destination_ip: str = Field(min_length=1, max_length=128, repr=False)
    source_mac: str | None = Field(default=None, max_length=64, repr=False)
    destination_mac: str | None = Field(default=None, max_length=64, repr=False)
    destination_port: int = Field(default=0, ge=0, le=65535, repr=False)


class ArpObservationV2(FrozenModel):
    observation_scope_id: str = Field(min_length=1, max_length=160, repr=False)
    timestamp: float = Field(ge=0.0, allow_inf_nan=False, repr=False)
    sender_ip: str = Field(min_length=1, max_length=128, repr=False)
    sender_mac: str = Field(min_length=1, max_length=64, repr=False)
    target_ip: str = Field(min_length=1, max_length=128, repr=False)
    target_mac: str | None = Field(default=None, max_length=64, repr=False)


class DnsRelationObservationV2(FrozenModel):
    observation_scope_id: str = Field(min_length=1, max_length=160, repr=False)
    timestamp: float = Field(ge=0.0, allow_inf_nan=False, repr=False)
    client_ip: str = Field(min_length=1, max_length=128, repr=False)
    responder_ip: str = Field(min_length=1, max_length=128, repr=False)
    name_shape: str = Field(min_length=1, max_length=160)
    response_code: int | None = Field(default=None, ge=0, le=15)


class RelationSessionObservationV2(FrozenModel):
    observation_scope_id: str = Field(min_length=1, max_length=160, repr=False)
    timestamp_end: float = Field(ge=0.0, allow_inf_nan=False, repr=False)
    source_ip: str = Field(min_length=1, max_length=128, repr=False)
    destination_ip: str = Field(min_length=1, max_length=128, repr=False)
    destination_port: int = Field(ge=0, le=65535, repr=False)
    responder_observed: bool = False


class RelationEvidenceV2(FrozenModel):
    schema_version: Literal["RELATION_EVIDENCE_V2"] = RELATION_EVIDENCE_V2_VERSION
    horizon_seconds: Literal[10, 60, 180, 300]
    past_only: Literal[True] = True
    linked_arp_observation_count: int = Field(ge=0)
    arp_mapping_count: int = Field(ge=0)
    arp_ip_conflict_count: int = Field(ge=0)
    arp_mapping_change_count: int = Field(ge=0)
    same_mac_multiple_ip_count: int = Field(ge=0)
    dns_relationship_count: int = Field(ge=0)
    dns_name_diversity: int = Field(ge=0)
    source_fan_in: int = Field(ge=0)
    destination_fan_out: int = Field(ge=0)
    multi_source_same_target: bool
    port_relationship_diversity: int = Field(ge=0)
    unexpected_responder_count: int = Field(ge=0)
    linked_endpoint_roles: tuple[Literal["source", "destination"], ...] = ()


def _unique_bounded(values: Iterable[Any], *, limit: int = 24) -> tuple[Any, ...]:
    return tuple(sorted(set(values), key=lambda item: str(item)))[:limit]


def _payload_hex(frame: Mapping[str, str]) -> str:
    for field in ("tcp.payload", "udp.payload", "data.data"):
        value = str(frame.get(field, "") or "").strip()
        if value:
            return value
    return ""


def _payload_octets(value: str) -> int | None:
    if not value:
        return 0
    if not _HEX_PAYLOAD.fullmatch(value):
        return None
    compact = re.sub(r"[^0-9a-fA-F]", "", value)
    return len(compact) // 2 if len(compact) % 2 == 0 else None


def _frame_protocol(frame: Mapping[str, str]) -> str:
    if frame.get("tcp.srcport") or frame.get("tcp.dstport"):
        return "TCP"
    if frame.get("udp.srcport") or frame.get("udp.dstport"):
        return "UDP"
    protocols = str(frame.get("frame.protocols", "")).casefold().split(":")
    return next((item.upper() for item in reversed(protocols) if item), "OTHER")[:24]


def packet_aligned_payload_row_from_frame(
    *,
    session_id: str,
    packet_index: int,
    frame: Mapping[str, str],
    session_start_timestamp: float,
    initiator_ip: str,
    initiator_port: int,
    responder_ip: str,
    responder_port: int,
) -> PacketAlignedPayloadRowV2:
    """Create one explicit sidecar row; the caller supplies the real packet index."""

    timestamp = float(frame.get("frame.time_epoch", ""))
    if timestamp < session_start_timestamp:
        raise ValueError("frame timestamp precedes the canonical session start")
    source_ip = str(frame.get("ip.src") or frame.get("ipv6.src") or "")
    source_port_text = str(frame.get("tcp.srcport") or frame.get("udp.srcport") or "0")
    try:
        source_port = int(source_port_text)
    except ValueError as exc:
        raise ValueError("frame has an invalid source port") from exc
    if source_ip == initiator_ip and source_port == initiator_port:
        direction = PacketDirectionV2.INITIATOR_TO_RESPONDER
    elif source_ip == responder_ip and source_port == responder_port:
        direction = PacketDirectionV2.RESPONDER_TO_INITIATOR
    else:
        raise ValueError("frame source does not belong to the canonical session endpoints")
    raw_hex = _payload_hex(frame)
    length = _payload_octets(raw_hex)
    if length is None:
        raise ValueError("frame payload is not a complete hexadecimal octet sequence")
    decoded = decode_hex_payload(raw_hex) if length else None
    sanitized = sanitize_payload_text(decoded, max_chars=768) if decoded else None
    return PacketAlignedPayloadRowV2(
        session_id=session_id,
        packet_index=packet_index,
        direction=direction,
        relative_time=timestamp - session_start_timestamp,
        protocol=_frame_protocol(frame),
        payload_present=length > 0,
        payload_length=length,
        sanitized_payload=sanitized,
    )


def application_evidence_v2_from_frames(
    frames: Iterable[Mapping[str, str]],
    *,
    sanitized_payloads: Iterable[str] = (),
    limit: int = 24,
) -> ApplicationEvidenceV2:
    if not 1 <= limit <= 24:
        raise ValueError("Application-v2 observation limit must be within 1..24")
    observations = [
        observation
        for frame in frames
        if (observation := application_observation_from_frame(dict(frame))) is not None
    ]
    truncated = len(observations) > limit
    visible = observations[:limit]
    methods = [str(item["method"]).upper() for item in visible if item.get("method")]
    statuses = [int(item["status"]) for item in visible if item.get("status") is not None]
    uri_shapes = [str(item["uri_shape"]) for item in visible if item.get("uri_shape")]
    content_types = [str(item["content_type"]) for item in visible if item.get("content_type")]
    protocols = [str(item.get("kind", "unknown")) for item in visible]
    request_count = sum(bool(item.get("method")) for item in visible)
    response_count = sum(item.get("status") is not None for item in visible)
    payload_text = "\n".join(sanitized_payloads).casefold()
    structure = (
        "BIDIRECTIONAL"
        if request_count and response_count
        else "REQUEST_ONLY"
        if request_count
        else "RESPONSE_ONLY"
        if response_count
        else "NONE"
    )
    return ApplicationEvidenceV2(
        application_protocols=_unique_bounded(protocols),
        http_methods=_unique_bounded(methods),
        http_status_codes=_unique_bounded(statuses),
        uri_shapes=_unique_bounded(uri_shapes),
        content_types=_unique_bounded(content_types),
        request_count=request_count,
        response_count=response_count,
        request_response_structure=structure,
        auth_related_structure=bool(set(statuses) & {401, 403})
        or "<credential_param>" in payload_text,
        credential_field_presence="<credential_param>" in payload_text,
        scanner_probe_structure=bool(set(methods) & {"HEAD", "OPTIONS", "TRACE", "CONNECT"})
        or "<automation_tool>" in payload_text,
        truncated=truncated,
    )


def _stats_from_v1(value: Mapping[str, Any]) -> DescriptiveStatsV2:
    return DescriptiveStatsV2(
        minimum=float(value.get("min", 0.0)),
        maximum=float(value.get("max", 0.0)),
        mean=float(value.get("mean", 0.0)),
        std=float(value.get("std", 0.0)),
    )


def build_basic_evidence_v2(
    *,
    session_id: str,
    summary: Mapping[str, Any],
    packet_sequence: Sequence[Mapping[str, Any]],
    payload_rows: Sequence[PacketAlignedPayloadRowV2],
    application: ApplicationEvidenceV2,
    protocol_metadata: Iterable[str] = (),
) -> BasicEvidenceV2:
    if not _SAMPLE_ID.fullmatch(session_id):
        raise ValueError("Basic-v2 requires a canonical session identity")
    if any(item.session_id != session_id for item in payload_rows):
        raise ValueError("Basic-v2 payload rows cross session identity")
    visible_packets = list(packet_sequence[:8])
    relative_time = 0.0
    packets: list[PacketMetadataV2] = []
    for index, packet in enumerate(visible_packets, start=1):
        iat = float(packet.get("relative_iat", 0.0))
        relative_time += iat
        packets.append(
            PacketMetadataV2(
                packet_index=index,
                direction=str(packet["direction"]),
                relative_time=relative_time,
                relative_iat=iat,
                packet_length=int(packet["packet_length"]),
                l3_protocol=str(packet["l3_protocol"]),
                l4_protocol=str(packet["l4_protocol"]),
                tcp_flags=packet.get("tcp_flags"),
            )
        )
    ordered_payload = sorted(payload_rows, key=lambda item: item.packet_index)
    summary_v2 = SessionSummaryV2(
        duration=float(summary["duration"]),
        bidirectional_packet_count=int(summary["initiator_packets"])
        + int(summary["responder_packets"]),
        bidirectional_byte_count=int(summary["initiator_bytes"])
        + int(summary["responder_bytes"]),
        initiator_packets=int(summary["initiator_packets"]),
        responder_packets=int(summary["responder_packets"]),
        initiator_bytes=int(summary["initiator_bytes"]),
        responder_bytes=int(summary["responder_bytes"]),
        packet_length_statistics=_stats_from_v1(summary["packet_length_stats"]),
        iat_statistics=_stats_from_v1(summary["iat_stats"]),
        tcp_handshake_state=str(summary["handshake_state"]),
        protocol_metadata=_unique_bounded(str(item) for item in protocol_metadata),
    )
    return BasicEvidenceV2(
        session_summary=summary_v2,
        first_eight_packets=tuple(packets),
        packet_aligned_payload=tuple(item.model_projection() for item in ordered_payload),
        cheap_application_metadata=application,
    )


def _repeat_ratio(values: Sequence[str]) -> float:
    return 0.0 if not values else 1.0 - len(set(values)) / len(values)


def aggregate_temporal_evidence_v2(
    target: TemporalSessionObservationV2,
    candidates: Iterable[TemporalSessionObservationV2],
    *,
    horizon_seconds: int,
) -> TemporalEvidenceV2:
    if horizon_seconds not in TEMPORAL_HORIZONS_SECONDS:
        raise ValueError("Temporal-v2 horizon must be one of 10/60/180/300 seconds")
    prior = sorted(
        (
            item
            for item in candidates
            if item.observation_scope_id == target.observation_scope_id
            and item.timestamp_end < target.timestamp_start
            and target.timestamp_start - item.timestamp_end <= horizon_seconds
        ),
        key=lambda item: (item.timestamp_start, item.timestamp_end),
    )
    count = len(prior)
    packets = sum(item.packet_count for item in prior)
    byte_count = sum(item.byte_count for item in prior)
    syn = sum(item.tcp_syn_count for item in prior)
    synack = sum(item.tcp_synack_count for item in prior)
    ack = sum(item.tcp_ack_count for item in prior)
    rst = sum(item.tcp_rst_count for item in prior)
    completed = sum(item.handshake_completed for item in prior)
    destination_counts = Counter(item.destination_node_id for item in prior)
    starts = [item.timestamp_start for item in prior]
    intervals = [right - left for left, right in zip(starts, starts[1:]) if right > left]
    interval_mean = fmean(intervals) if intervals else None
    interval_std = pstdev(intervals) if len(intervals) > 1 else (0.0 if intervals else None)
    interval_cv = (
        interval_std / interval_mean
        if interval_mean is not None and interval_std is not None and interval_mean > 0
        else (0.0 if intervals else None)
    )
    burstiness = (
        (interval_std - interval_mean) / (interval_std + interval_mean)
        if interval_mean is not None
        and interval_std is not None
        and interval_std + interval_mean > 0
        else 0.0
    )
    uri_shapes = [shape for item in prior for shape in item.uri_shapes]
    methods = [method.upper() for item in prior for method in item.methods]
    directional_total = sum(item.initiator_bytes + item.responder_bytes for item in prior)
    directional_delta = sum(abs(item.initiator_bytes - item.responder_bytes) for item in prior)
    tcp_sessions = sum(
        bool(
            item.handshake_completed
            or item.tcp_syn_count
            or item.tcp_synack_count
            or item.tcp_ack_count
            or item.tcp_rst_count
        )
        for item in prior
    )
    return TemporalEvidenceV2(
        horizon_seconds=horizon_seconds,
        prior_session_count=count,
        latest_context_age_seconds=(
            target.timestamp_start - max(item.timestamp_end for item in prior) if prior else None
        ),
        session_rate=count / horizon_seconds,
        packet_rate=packets / horizon_seconds,
        byte_rate=byte_count / horizon_seconds,
        syn_count=syn,
        synack_count=synack,
        syn_ratio=syn / packets if packets else 0.0,
        syn_rate=syn / horizon_seconds,
        rst_count=rst,
        ack_count=ack,
        handshake_completion_ratio=completed / tcp_sessions if tcp_sessions else 0.0,
        incomplete_handshake_ratio=(tcp_sessions - completed) / tcp_sessions if tcp_sessions else 0.0,
        destination_concentration=max(destination_counts.values()) / count if count else 0.0,
        source_fan_in=len(
            {item.source_node_id for item in prior if item.destination_node_id == target.destination_node_id}
        ),
        destination_fan_out=len(
            {item.destination_node_id for item in prior if item.source_node_id == target.source_node_id}
        ),
        port_diversity=len({item.destination_port for item in prior}),
        burstiness=burstiness,
        inter_arrival_mean=interval_mean,
        inter_arrival_std=interval_std,
        inter_arrival_cv=interval_cv,
        authentication_request_count=sum(item.authentication_request_count for item in prior),
        application_request_count=sum(item.application_request_count for item in prior),
        uri_repetition_ratio=_repeat_ratio(uri_shapes),
        method_repetition_ratio=_repeat_ratio(methods),
        interval_cv=interval_cv,
        directional_byte_asymmetry=(directional_delta / directional_total if directional_total else 0.0),
    )


def _strict_past_in_scope(
    *, event_scope: str, event_timestamp: float, target: RelationTargetV2, horizon_seconds: int
) -> bool:
    return (
        event_scope == target.observation_scope_id
        and event_timestamp < target.timestamp
        and target.timestamp - event_timestamp <= horizon_seconds
    )


def build_relation_evidence_v2(
    target: RelationTargetV2,
    *,
    arp_observations: Iterable[ArpObservationV2] = (),
    dns_observations: Iterable[DnsRelationObservationV2] = (),
    session_observations: Iterable[RelationSessionObservationV2] = (),
    horizon_seconds: int,
) -> RelationEvidenceV2:
    if horizon_seconds not in TEMPORAL_HORIZONS_SECONDS:
        raise ValueError("Relation-v2 horizon must be one of 10/60/180/300 seconds")
    endpoint_ips = {target.source_ip, target.destination_ip}
    endpoint_macs = {value for value in (target.source_mac, target.destination_mac) if value}
    linked_arp: list[ArpObservationV2] = []
    linked_roles: set[Literal["source", "destination"]] = set()
    for item in arp_observations:
        if not _strict_past_in_scope(
            event_scope=item.observation_scope_id,
            event_timestamp=item.timestamp,
            target=target,
            horizon_seconds=horizon_seconds,
        ):
            continue
        event_ips = {item.sender_ip, item.target_ip}
        event_macs = {value for value in (item.sender_mac, item.target_mac) if value}
        if not (event_ips & endpoint_ips or event_macs & endpoint_macs):
            continue
        linked_arp.append(item)
        if target.source_ip in event_ips or (target.source_mac and target.source_mac in event_macs):
            linked_roles.add("source")
        if target.destination_ip in event_ips or (
            target.destination_mac and target.destination_mac in event_macs
        ):
            linked_roles.add("destination")

    ip_macs: dict[str, set[str]] = defaultdict(set)
    mac_ips: dict[str, set[str]] = defaultdict(set)
    arp_by_ip: dict[str, list[ArpObservationV2]] = defaultdict(list)
    for item in linked_arp:
        ip_macs[item.sender_ip].add(item.sender_mac)
        mac_ips[item.sender_mac].add(item.sender_ip)
        arp_by_ip[item.sender_ip].append(item)
    changes = 0
    for values in arp_by_ip.values():
        ordered = sorted(values, key=lambda item: item.timestamp)
        changes += sum(
            right.timestamp > left.timestamp and left.sender_mac != right.sender_mac
            for left, right in zip(ordered, ordered[1:])
        )

    linked_dns = [
        item
        for item in dns_observations
        if _strict_past_in_scope(
            event_scope=item.observation_scope_id,
            event_timestamp=item.timestamp,
            target=target,
            horizon_seconds=horizon_seconds,
        )
        and {item.client_ip, item.responder_ip} & endpoint_ips
    ]
    linked_sessions = [
        item
        for item in session_observations
        if _strict_past_in_scope(
            event_scope=item.observation_scope_id,
            event_timestamp=item.timestamp_end,
            target=target,
            horizon_seconds=horizon_seconds,
        )
        and {item.source_ip, item.destination_ip} & endpoint_ips
    ]
    fan_in_sources = {
        item.source_ip for item in linked_sessions if item.destination_ip == target.destination_ip
    }
    fan_out_destinations = {
        item.destination_ip for item in linked_sessions if item.source_ip == target.source_ip
    }
    related_pair_ports = {
        item.destination_port
        for item in linked_sessions
        if item.source_ip == target.source_ip and item.destination_ip == target.destination_ip
    }
    unexpected_responders = {
        item.source_ip
        for item in linked_sessions
        if item.destination_ip == target.source_ip
        and item.responder_observed
        and item.source_ip != target.destination_ip
    }
    return RelationEvidenceV2(
        horizon_seconds=horizon_seconds,
        linked_arp_observation_count=len(linked_arp),
        arp_mapping_count=len({(item.sender_ip, item.sender_mac) for item in linked_arp}),
        arp_ip_conflict_count=sum(len(macs) > 1 for macs in ip_macs.values()),
        arp_mapping_change_count=changes,
        same_mac_multiple_ip_count=sum(len(ips) > 1 for ips in mac_ips.values()),
        dns_relationship_count=len(linked_dns),
        dns_name_diversity=len({item.name_shape for item in linked_dns}),
        source_fan_in=len(fan_in_sources),
        destination_fan_out=len(fan_out_destinations),
        multi_source_same_target=len(fan_in_sources) > 1,
        port_relationship_diversity=len(related_pair_ports),
        unexpected_responder_count=len(unexpected_responders),
        linked_endpoint_roles=tuple(sorted(linked_roles)),
    )
