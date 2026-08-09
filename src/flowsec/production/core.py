from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

from flowsec.production.schema import Packet, canonical_json, content_hash


def sha256_file(path: Path, block_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_float(value: str | None, default: float = 0.0) -> float:
    if value in {None, "", "-", "(empty)"}:
        return default
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def safe_int(value: str | None, default: int = 0) -> int:
    if value in {None, "", "-", "(empty)"}:
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def first_value(value: str) -> str:
    return value.split(",", 1)[0].strip()


def parse_flags(value: str) -> int:
    value = first_value(value)
    if not value:
        return 0
    try:
        return int(value, 16) if value.lower().startswith("0x") else int(value)
    except ValueError:
        return 0


def canonical_endpoint_key(packet: Packet) -> tuple[Any, ...]:
    left = (packet.src, packet.sport)
    right = (packet.dst, packet.dport)
    return (
        packet.l3_protocol,
        packet.l4_protocol,
        left,
        right,
    ) if left <= right else (
        packet.l3_protocol,
        packet.l4_protocol,
        right,
        left,
    )


def canonical_endpoint_identity(
    l3_protocol: str,
    l4_protocol: str,
    src: str,
    sport: int,
    dst: str,
    dport: int,
) -> tuple[Any, ...]:
    left = (src, int(sport))
    right = (dst, int(dport))
    return (l3_protocol, l4_protocol, left, right) if left <= right else (
        l3_protocol,
        l4_protocol,
        right,
        left,
    )


def service_category(l4_protocol: str, sport: int, dport: int, supplied: str = "") -> tuple[str, str]:
    supplied = supplied.strip().lower()
    if supplied and supplied not in {"-", "(empty)"}:
        cleaned = "".join(ch for ch in supplied.upper() if ch.isalnum() or ch in {"_", "-"})
        return cleaned or "UNKNOWN", "sanitized_parser_service_v1"
    mapping = {
        20: "FTP", 21: "FTP", 22: "SSH", 23: "TELNET", 25: "SMTP", 53: "DNS",
        67: "DHCP", 68: "DHCP", 80: "HTTP", 110: "POP3", 123: "NTP", 143: "IMAP",
        161: "SNMP", 443: "HTTPS", 445: "SMB", 502: "MODBUS", 1883: "MQTT",
        1900: "SSDP", 5353: "MDNS", 8080: "HTTP_ALT", 8883: "MQTT_TLS",
    }
    for port in sorted({int(sport), int(dport)}):
        if port in mapping:
            return mapping[port], "iana_port_category_map_v1"
    nonzero = [port for port in {int(sport), int(dport)} if port]
    if not nonzero:
        return l4_protocol, "transport_protocol_fallback_v1"
    if min(nonzero) < 1024:
        return "OTHER_SYSTEM", "iana_port_range_v1"
    if min(nonzero) < 49152:
        return "OTHER_REGISTERED", "iana_port_range_v1"
    return "EPHEMERAL", "iana_port_range_v1"


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def choose_gap_seconds(
    *,
    capture_span: float,
    session_durations: list[float],
    fixed_safety_seconds: float,
    long_session_quantile: float,
    max_gap_fraction: float,
) -> dict[str, Any]:
    p_long = percentile(session_durations, long_session_quantile)
    requested = max(float(fixed_safety_seconds), math.ceil(p_long * 1000.0) / 1000.0)
    usability_cap = max(0.001, capture_span * max_gap_fraction)
    effective = min(requested, usability_cap)
    return {
        "fixed_safety_seconds": fixed_safety_seconds,
        "long_session_quantile": long_session_quantile,
        "long_session_quantile_seconds": p_long,
        "requested_gap_seconds": requested,
        "usability_cap_fraction": max_gap_fraction,
        "usability_cap_seconds": usability_cap,
        "effective_gap_seconds": effective,
        "clipped_for_split_usability": effective < requested,
    }


def chronological_split(
    start: float,
    end: float,
    minimum: float,
    maximum: float,
    gap_seconds: float,
) -> tuple[str, str | None]:
    span = max(0.001, maximum - minimum)
    first = minimum + 0.70 * span
    second = minimum + 0.85 * span
    half_gap = gap_seconds / 2.0
    if end <= first - half_gap:
        return "train", None
    if start >= first + half_gap and end <= second - half_gap:
        return "validation", None
    if start >= second + half_gap:
        return "test", None
    return "quarantine", "split_boundary_or_gap"


def logical_record_hash(row: dict[str, Any]) -> str:
    return content_hash(row)


def hash_identity(value: Any, salt: str) -> str:
    return hashlib.sha256((salt + "|" + canonical_json(value)).encode("utf-8")).hexdigest()


def combine_hashes(values: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for value in sorted(values):
        digest.update(value.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def parse_json(value: str | bytes | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)
