#!/usr/bin/env python3
"""Build versioned Evidence-v2 and observation-eligibility assets.

The builder is derivative-only: it reads verified PCAPs and current paper-v2
backend locators, never rewrites Production sessions or split assignments.  It
extracts label-free evidence first and applies the class-conditional eligibility
contract only after the evidence is materialized.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
from bisect import bisect_right
from collections import Counter, defaultdict
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any, Iterator

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from flowsec.production.core import canonical_endpoint_identity, first_value, safe_int
from flowsec.training.contracts import SANITIZED_PAYLOAD_VERSION, canonical_json, content_digest
from flowsec.training.evidence import (
    application_observation_from_frame,
    payload_fragment_from_frame,
)
from flowsec.training.materialization import sha256_file
from flowsec.training.evidence_v2 import (
    ApplicationEvidenceV2,
    BasicEvidenceV2,
    DescriptiveStatsV2,
    PacketAlignedPayloadRowV2,
    PacketDirectionV2,
    PacketMetadataV2,
    RelationEvidenceV2,
    SessionSummaryV2,
)
from flowsec.training.observable_v3 import (
    APPLICATION_VERSION,
    BASIC_VERSION,
    EVIDENCE_VERSION,
    ELIGIBILITY_POLICY_VERSION,
    MAIN_CLASS_CANDIDATES,
    OBSERVABLE_DATASET_VERSION,
    PACKET_PAYLOAD_VERSION,
    RELATION_VERSION,
    TEMPORAL_HORIZONS_SECONDS,
    assess_fine_observation_eligibility,
    build_strict_past_temporal_contexts,
    label_free_session_signals,
    validate_temporal_context,
)


SCANNER_VERSION = "OBSERVABLE_DATASET_V3_EVIDENCE_SCANNER_V2"
SANITIZATION_VERSION = SANITIZED_PAYLOAD_VERSION
DEFAULT_PRODUCTION_ROOT = Path("/root/autodl-tmp/processed/edge_split_revision_v2")
DEFAULT_OUTPUT_ROOT = Path("/root/autodl-tmp/processed/observable_dataset_v3")

ARTIFACT_NAMES = frozenset(
    {
        "raw_sessions",
        "packet_payload",
        "application",
        "temporal",
        "relation",
        "eligibility",
        "basic_views",
        "link_events",
    }
)

RAW_FIELDS = (
    "frame.number",
    "frame.time_epoch",
    "frame.len",
    "frame.protocols",
    "eth.src",
    "eth.dst",
    "arp.opcode",
    "arp.src.proto_ipv4",
    "arp.dst.proto_ipv4",
    "ip.src",
    "ipv6.src",
    "ip.dst",
    "ipv6.dst",
    "ip.proto",
    "ipv6.nxt",
    "tcp.srcport",
    "tcp.dstport",
    "udp.srcport",
    "udp.dstport",
    "tcp.flags",
    "tcp.len",
    "udp.length",
    "http.request.method",
    "http.request.uri",
    "http.response.code",
    "http.content_type",
    "http.content_length",
    "dns.qry.name",
    "dns.qry.type",
    "dns.a",
    "dns.flags.response",
    "dns.flags.rcode",
    "tls.record.version",
    "tls.handshake.type",
    "tls.handshake.version",
    "tls.handshake.extensions_server_name",
    "ftp.request.command",
    "ftp.request.arg",
    "ftp.response.code",
    "mqtt.msgtype",
    "mqtt.topic",
    "modbus.func_code",
    "tcp.payload",
    "udp.payload",
    "data.data",
)


def _first(value: str) -> str:
    return first_value(value or "")


def _float(value: str, default: float = 0.0) -> float:
    try:
        return float(_first(value))
    except ValueError:
        return default


def _flags(value: str) -> int:
    compact = _first(value)
    if not compact:
        return 0
    try:
        return int(compact, 16) if compact.casefold().startswith("0x") else int(compact)
    except ValueError:
        return 0


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _atomic_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"refusing schema-less empty parquet: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
        pq.write_table(pa.Table.from_pylist(rows), temporary, compression="zstd")
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _artifact(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def _packet_identity(row: dict[str, str]) -> tuple[Any, ...] | None:
    src4, src6 = _first(row["ip.src"]), _first(row["ipv6.src"])
    dst4, dst6 = _first(row["ip.dst"]), _first(row["ipv6.dst"])
    src, dst = src4 or src6, dst4 or dst6
    if not src or not dst:
        return None
    l3 = "IPv4" if src4 else "IPv6"
    protocol = safe_int(_first(row["ip.proto"]) or _first(row["ipv6.nxt"]))
    tcp_s, tcp_d = safe_int(_first(row["tcp.srcport"])), safe_int(_first(row["tcp.dstport"]))
    udp_s, udp_d = safe_int(_first(row["udp.srcport"])), safe_int(_first(row["udp.dstport"]))
    if tcp_s or tcp_d or protocol == 6:
        l4, sport, dport = "TCP", tcp_s, tcp_d
    elif udp_s or udp_d or protocol == 17:
        l4, sport, dport = "UDP", udp_s, udp_d
    elif protocol in {1, 58}:
        l4, sport, dport = "ICMP", 0, 0
    else:
        l4, sport, dport = (f"IP_{protocol}" if protocol else "IP_OTHER"), 0, 0
    return canonical_endpoint_identity(l3, l4, src, sport, dst, dport)


def _locator_identity(row: dict[str, Any]) -> tuple[Any, ...]:
    return canonical_endpoint_identity(
        str(row["l3_protocol"]),
        str(row["l4_protocol"]),
        str(row["raw_initiator_ip"]),
        int(row["raw_initiator_port"]),
        str(row["raw_responder_ip"]),
        int(row["raw_responder_port"]),
    )


class Matcher:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[_locator_identity(row)].append(row)
        self.groups = {
            key: sorted(value, key=lambda item: (item["first_frame_or_record"], item["sample_id"]))
            for key, value in grouped.items()
        }
        self.starts = {
            key: [int(item["first_frame_or_record"]) for item in value]
            for key, value in self.groups.items()
        }

    def match(self, frame: int, raw: dict[str, str]) -> dict[str, Any] | None:
        identity = _packet_identity(raw)
        if identity is None or identity not in self.groups:
            return None
        index = bisect_right(self.starts[identity], frame) - 1
        if index >= 0:
            locator = self.groups[identity][index]
            if frame <= int(locator["last_frame_or_record"]):
                return locator
        return None


def _tshark_command(tshark: str, pcap: Path, packet_limit: int | None) -> list[str]:
    command = [tshark, "-n", "-r", str(pcap)]
    if packet_limit is not None:
        command.extend(("-c", str(packet_limit)))
    command.extend(("-T", "fields", "-E", "separator=/t", "-E", "occurrence=f"))
    for field in RAW_FIELDS:
        command.extend(("-e", field))
    return command


def _iter_tshark(
    tshark: str,
    pcap: Path,
    stderr_path: Path,
    packet_limit: int | None,
) -> Iterator[dict[str, str]]:
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    csv.field_size_limit(sys.maxsize)
    with stderr_path.open("w", encoding="utf-8") as stderr_handle:
        process = subprocess.Popen(
            _tshark_command(tshark, pcap, packet_limit),
            stdout=subprocess.PIPE,
            stderr=stderr_handle,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1024 * 1024,
        )
        assert process.stdout is not None
        reader = csv.reader(process.stdout, delimiter="\t", quotechar='"')
        for parts in reader:
            if len(parts) < len(RAW_FIELDS):
                parts.extend([""] * (len(RAW_FIELDS) - len(parts)))
            if len(parts) == len(RAW_FIELDS):
                yield dict(zip(RAW_FIELDS, parts, strict=True))
        process.stdout.close()
        return_code = process.wait()
    if return_code:
        raise RuntimeError(f"tshark failed for {pcap}; see {stderr_path}")


def _verified_corrupt_tail_limitation(
    *,
    error: RuntimeError,
    stderr_path: Path,
    packet_limit: int | None,
    max_frame_seen: int,
    max_locator_frame: int,
) -> dict[str, Any] | None:
    """Accept only a damaged trailing PCAP record after all located sessions.

    Edge-IIoTset's verified Vulnerability-scanner PCAP contains one malformed
    trailing record after frame 265827.  Wireshark returns a non-zero status
    even though every frame referenced by the frozen Production locators was
    emitted.  This helper keeps that source limitation explicit and fail-closed:
    partial scans, early corruption, packet-limited scans, and unrelated tshark
    failures remain fatal.
    """

    if packet_limit is not None or max_frame_seen < max_locator_frame:
        return None
    try:
        stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    required = (
        "appears to be damaged or corrupt",
        "pcap: File has ",
        "-byte packet, bigger than maximum of ",
    )
    if not all(fragment in stderr for fragment in required):
        return None
    return {
        "type": "VERIFIED_CORRUPT_TAIL_AFTER_ALL_PRODUCTION_LOCATORS",
        "tshark_error": str(error),
        "max_frame_seen": max_frame_seen,
        "max_locator_frame": max_locator_frame,
        "all_production_locators_covered": True,
    }


def _moment() -> dict[str, float | int | None]:
    return {"count": 0, "sum": 0.0, "sum_sq": 0.0, "min": None, "max": None}


def _moment_add(moment: dict[str, Any], value: float) -> None:
    moment["count"] += 1
    moment["sum"] += value
    moment["sum_sq"] += value * value
    moment["min"] = value if moment["min"] is None else min(moment["min"], value)
    moment["max"] = value if moment["max"] is None else max(moment["max"], value)


def _moment_summary(moment: dict[str, Any]) -> dict[str, float | int | None]:
    count = int(moment["count"])
    if not count:
        return {"count": 0, "mean": None, "std": None, "min": None, "max": None}
    mean = float(moment["sum"]) / count
    variance = max(0.0, float(moment["sum_sq"]) / count - mean * mean)
    return {
        "count": count,
        "mean": mean,
        "std": math.sqrt(variance),
        "min": moment["min"],
        "max": moment["max"],
    }


def _new_session(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_id": str(row["sample_id"]),
        "capture_id_backend_only": str(row["scenario_or_capture_id"]),
        "split": str(row["split"]),
        "fine_label_backend_only": str(row["fine_label"]),
        "coarse_label_backend_only": str(row["coarse_label"]),
        "timestamp_start": float(row["timestamp_start"]),
        "timestamp_end": float(row["timestamp_end"]),
        "raw_initiator_ip": str(row["raw_initiator_ip"]),
        "raw_responder_ip": str(row["raw_responder_ip"]),
        "raw_initiator_port": int(row["raw_initiator_port"]),
        "raw_responder_port": int(row["raw_responder_port"]),
        "l3_protocol": str(row["l3_protocol"]),
        "l4_protocol": str(row["l4_protocol"]),
        "source_identity_hash": str(row["source_identity_hash"]),
        "destination_identity_hash": str(row["destination_identity_hash"]),
        "communication_pair_hash": str(row["communication_pair_hash"]),
        "capture_provenance_status": str(row["capture_provenance_status"]),
        "label_assignment_method": str(row["label_assignment_method"]),
        "packet_count": 0,
        "byte_count": 0,
        "initiator_packets": 0,
        "responder_packets": 0,
        "initiator_bytes": 0,
        "responder_bytes": 0,
        "initiator_payload_bytes": 0,
        "responder_payload_bytes": 0,
        "payload_packet_count": 0,
        "tcp_syn": 0,
        "tcp_synack": 0,
        "tcp_rst": 0,
        "tcp_fin": 0,
        "tcp_ack": 0,
        "request_count": 0,
        "response_count": 0,
        "basic_request_count": 0,
        "basic_response_count": 0,
        "tls_frame_count": 0,
        "dns_frame_count": 0,
        "packet_lengths": _moment(),
        "packet_iats": _moment(),
        "last_packet_time": None,
        "first_8_packets": [],
        "payload_fragments_1_8": [],
        "payload_fragments_1_16": [],
        "application_observations": {},
        "basic_application_observations": {},
        "application_protocols": set(),
        "http_methods": Counter(),
        "http_statuses": Counter(),
        "content_types": Counter(),
        "uri_shapes": Counter(),
        "ftp_commands": Counter(),
    }


def _frame_direction(session: dict[str, Any], raw: dict[str, str]) -> str:
    src = _first(raw["ip.src"]) or _first(raw["ipv6.src"])
    sport = safe_int(_first(raw["tcp.srcport"]) or _first(raw["udp.srcport"]))
    if src == session["raw_initiator_ip"] and (
        sport == session["raw_initiator_port"] or session["raw_initiator_port"] == 0
    ):
        return PacketDirectionV2.INITIATOR_TO_RESPONDER.value
    return PacketDirectionV2.RESPONDER_TO_INITIATOR.value


def _payload_hex_length(raw: dict[str, str]) -> int:
    value = _first(raw["tcp.payload"]) or _first(raw["udp.payload"]) or _first(raw["data.data"])
    compact = "".join(character for character in value if character in "0123456789abcdefABCDEF")
    return len(compact) // 2 if compact and len(compact) % 2 == 0 else 0


def _update_session(
    session: dict[str, Any],
    raw: dict[str, str],
    *,
    frame_number: int,
    packet_payload_rows: list[dict[str, Any]],
) -> None:
    packet_index = int(session["packet_count"]) + 1
    timestamp = _float(raw["frame.time_epoch"], session["timestamp_start"])
    relative_time = max(0.0, timestamp - session["timestamp_start"])
    previous = session["last_packet_time"]
    iat = max(0.0, timestamp - previous) if previous is not None else 0.0
    session["last_packet_time"] = timestamp
    direction = _frame_direction(session, raw)
    frame_len = safe_int(_first(raw["frame.len"]))
    payload_length = _payload_hex_length(raw)
    flags = _flags(raw["tcp.flags"])
    session["packet_count"] = packet_index
    session["byte_count"] += frame_len
    prefix = (
        "initiator"
        if direction == PacketDirectionV2.INITIATOR_TO_RESPONDER.value
        else "responder"
    )
    session[f"{prefix}_packets"] += 1
    session[f"{prefix}_bytes"] += frame_len
    session[f"{prefix}_payload_bytes"] += payload_length
    session["payload_packet_count"] += int(payload_length > 0)
    session["tcp_syn"] += int(bool(flags & 0x02 and not flags & 0x10))
    session["tcp_synack"] += int(bool(flags & 0x02 and flags & 0x10))
    session["tcp_rst"] += int(bool(flags & 0x04))
    session["tcp_fin"] += int(bool(flags & 0x01))
    session["tcp_ack"] += int(bool(flags & 0x10))
    _moment_add(session["packet_lengths"], float(frame_len))
    if packet_index > 1:
        _moment_add(session["packet_iats"], iat)

    packet_metadata = {
        "packet_index": packet_index,
        "direction": direction,
        "relative_time": relative_time,
        "relative_iat": iat,
        "packet_length": frame_len,
        "l3_protocol": session["l3_protocol"],
        "l4_protocol": session["l4_protocol"],
        "tcp_flags": flags if session["l4_protocol"] == "TCP" else None,
    }
    if packet_index <= 8:
        session["first_8_packets"].append(packet_metadata)

    sanitized = payload_fragment_from_frame(raw, max_chars=768) if payload_length else None
    if packet_index <= 16:
        payload_row = {
                "schema_version": PACKET_PAYLOAD_VERSION,
                "session_id": session["sample_id"],
                "packet_index": packet_index,
                "direction": direction,
                "relative_time": relative_time,
                "protocol": session["l4_protocol"],
                "payload_present": bool(payload_length),
                "payload_length": payload_length,
                "sanitized_payload": sanitized,
                "sanitization_version": SANITIZATION_VERSION,
                "frame_number_backend_only": frame_number,
            }
        PacketAlignedPayloadRowV2.model_validate(
            {key: value for key, value in payload_row.items() if not key.endswith("backend_only")}
        )
        packet_payload_rows.append(payload_row)
        if sanitized:
            session["payload_fragments_1_16"].append(sanitized)
            if packet_index <= 8:
                session["payload_fragments_1_8"].append(sanitized)

    observation = application_observation_from_frame(raw)
    if observation is not None:
        observation = {"packet_index": packet_index, **observation}
        key = canonical_json(observation)
        if len(session["application_observations"]) < 24:
            session["application_observations"].setdefault(key, observation)
        if packet_index <= 8 and len(session["basic_application_observations"]) < 12:
            session["basic_application_observations"].setdefault(key, observation)
        session["application_protocols"].add(str(observation.get("kind") or "unknown"))
        session["dns_frame_count"] += int(observation.get("kind") == "dns")
    method = _first(raw["http.request.method"]).upper()
    status = _first(raw["http.response.code"])
    content_type = _first(raw["http.content_type"]).casefold()
    uri = _first(raw["http.request.uri"])
    if method:
        session["http_methods"][method] += 1
        session["request_count"] += 1
        session["basic_request_count"] += int(packet_index <= 8)
    if status:
        session["http_statuses"][status] += 1
        session["response_count"] += 1
        session["basic_response_count"] += int(packet_index <= 8)
    if content_type:
        session["content_types"][content_type] += 1
    if uri:
        from flowsec.training.evidence import normalize_uri_shape

        session["uri_shapes"][normalize_uri_shape(uri)] += 1
    ftp_command = _first(raw["ftp.request.command"]).upper()
    if ftp_command:
        session["ftp_commands"][ftp_command] += 1
        session["request_count"] += 1
        session["basic_request_count"] += int(packet_index <= 8)
    if _first(raw["ftp.response.code"]):
        session["response_count"] += 1
        session["basic_response_count"] += int(packet_index <= 8)
    tls = bool(_first(raw["tls.record.version"]) or _first(raw["tls.handshake.type"]))
    session["tls_frame_count"] += int(tls)
    if tls:
        session["application_protocols"].add("tls")
    if _first(raw["mqtt.msgtype"]):
        session["application_protocols"].add("mqtt")
    if _first(raw["modbus.func_code"]):
        session["application_protocols"].add("modbus")


def _finalize_session(session: dict[str, Any]) -> dict[str, Any]:
    application = list(session.pop("application_observations").values())
    basic_application = list(session.pop("basic_application_observations").values())
    protocols = sorted(session.pop("application_protocols"))
    lengths = _moment_summary(session.pop("packet_lengths"))
    iats = _moment_summary(session.pop("packet_iats"))
    session.pop("last_packet_time")
    duration = max(0.0, session["timestamp_end"] - session["timestamp_start"])
    if session["tcp_synack"] or (
        session["initiator_packets"] and session["responder_packets"]
    ):
        handshake = "ESTABLISHED_OR_BIDIRECTIONAL"
    elif session["tcp_syn"]:
        handshake = "INCOMPLETE_HANDSHAKE"
    else:
        handshake = "NOT_APPLICABLE_OR_UNOBSERVED"
    session_summary = {
        "duration": duration,
        "bidirectional_packet_count": session["packet_count"],
        "bidirectional_byte_count": session["byte_count"],
        "initiator_packet_count": session["initiator_packets"],
        "responder_packet_count": session["responder_packets"],
        "initiator_byte_count": session["initiator_bytes"],
        "responder_byte_count": session["responder_bytes"],
        "packet_length_statistics": lengths,
        "iat_statistics": iats,
        "tcp_handshake_state": handshake,
        "safe_protocol": session["l4_protocol"],
        "application_protocols": protocols,
    }
    session["duration"] = duration
    session["application_protocol"] = "+".join(protocols)
    session["application_observations"] = application
    session["basic_application_observations"] = basic_application
    session["sanitized_payload_fragments"] = list(session.pop("payload_fragments_1_16"))
    basic_fragments = list(session.pop("payload_fragments_1_8"))
    session["distinct_uri_shape_count"] = len(session["uri_shapes"])
    session["distinct_method_count"] = len(session["http_methods"])
    session["mechanism_signals"] = sorted(label_free_session_signals(session))
    basic_projection = dict(session)
    basic_projection["sanitized_payload_fragments"] = basic_fragments
    basic_projection["application_observations"] = basic_application
    basic_projection["request_count"] = session["basic_request_count"]
    basic_projection["response_count"] = session["basic_response_count"]
    session["basic_mechanism_signals"] = sorted(label_free_session_signals(basic_projection))
    session["session_summary_json"] = canonical_json(session_summary)
    session["first_8_packets_json"] = canonical_json(session.pop("first_8_packets"))
    session["basic_payload_json"] = canonical_json(basic_fragments)
    session["application_observations_json"] = canonical_json(application)
    session["basic_application_observations_json"] = canonical_json(basic_application)
    session["mechanism_signals_json"] = canonical_json(session.pop("mechanism_signals"))
    session["basic_mechanism_signals_json"] = canonical_json(
        session.pop("basic_mechanism_signals")
    )
    session["sanitized_payload_fragments_json"] = canonical_json(
        session.pop("sanitized_payload_fragments")
    )
    for field in ("http_methods", "http_statuses", "content_types", "uri_shapes", "ftp_commands"):
        values = session.pop(field)
        session[field + "_json"] = canonical_json(dict(sorted(values.items())))
    return session


def _session_for_rules(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    for field in (
        "application_observations",
        "basic_application_observations",
        "mechanism_signals",
        "basic_mechanism_signals",
        "sanitized_payload_fragments",
    ):
        result[field] = json.loads(result.pop(field + "_json"))
    return result


def _stats_contract(value: dict[str, Any]) -> DescriptiveStatsV2:
    if not int(value.get("count") or 0):
        return DescriptiveStatsV2(minimum=0.0, maximum=0.0, mean=0.0, std=0.0)
    return DescriptiveStatsV2(
        minimum=float(value["min"]),
        maximum=float(value["max"]),
        mean=float(value["mean"]),
        std=float(value["std"]),
    )


def _application_contract(
    observations: list[dict[str, Any]],
    *,
    payload_fragments: list[str],
    truncated: bool,
) -> ApplicationEvidenceV2:
    methods = sorted(
        {str(item["method"]).upper() for item in observations if item.get("method")}
    )[:24]
    statuses = sorted(
        {int(item["status"]) for item in observations if item.get("status") is not None}
    )[:24]
    uri_shapes = sorted(
        {str(item["uri_shape"]) for item in observations if item.get("uri_shape")}
    )[:24]
    content_types = sorted(
        {str(item["content_type"]) for item in observations if item.get("content_type")}
    )[:24]
    protocols = sorted({str(item.get("kind") or "unknown") for item in observations})[:24]
    request_count = sum(int(bool(item.get("method"))) for item in observations)
    response_count = sum(int(item.get("status") is not None) for item in observations)
    structure = (
        "BIDIRECTIONAL"
        if request_count and response_count
        else "REQUEST_ONLY"
        if request_count
        else "RESPONSE_ONLY"
        if response_count
        else "NONE"
    )
    payload_text = "\n".join(payload_fragments).casefold()
    return ApplicationEvidenceV2(
        application_protocols=tuple(protocols),
        http_methods=tuple(methods),
        http_status_codes=tuple(statuses),
        uri_shapes=tuple(uri_shapes),
        content_types=tuple(content_types),
        request_count=request_count,
        response_count=response_count,
        request_response_structure=structure,
        auth_related_structure=bool(set(statuses) & {401, 403})
        or "<credential_param>" in payload_text,
        credential_field_presence="<credential_param>" in payload_text,
        scanner_probe_structure=bool(
            set(methods) & {"HEAD", "OPTIONS", "TRACE", "CONNECT", "PROPFIND", "SEARCH"}
        )
        or any(
            marker in payload_text
            for marker in ("<automation_tool>", "<path_traversal>", "<command_param>")
        ),
        truncated=truncated,
    )


def _basic_contract(
    row: dict[str, Any], payload_rows: list[dict[str, Any]]
) -> BasicEvidenceV2:
    summary = json.loads(row["session_summary_json"])
    packet_rows = json.loads(row["first_8_packets_json"])
    payload_models = [
        PacketAlignedPayloadRowV2.model_validate(
            {key: value for key, value in value.items() if not key.endswith("backend_only")}
        )
        for value in sorted(payload_rows, key=lambda item: int(item["packet_index"]))
        if int(value["packet_index"]) <= len(packet_rows)
    ]
    packets = tuple(
        PacketMetadataV2.model_validate(value) for value in packet_rows
    )
    basic_app_observations = json.loads(row["basic_application_observations_json"])
    basic_payload = json.loads(row["basic_payload_json"])
    application = _application_contract(
        basic_app_observations,
        payload_fragments=basic_payload,
        truncated=False,
    )
    session_summary = SessionSummaryV2(
        duration=float(summary["duration"]),
        bidirectional_packet_count=int(summary["bidirectional_packet_count"]),
        bidirectional_byte_count=int(summary["bidirectional_byte_count"]),
        initiator_packets=int(summary["initiator_packet_count"]),
        responder_packets=int(summary["responder_packet_count"]),
        initiator_bytes=int(summary["initiator_byte_count"]),
        responder_bytes=int(summary["responder_byte_count"]),
        packet_length_statistics=_stats_contract(summary["packet_length_statistics"]),
        iat_statistics=_stats_contract(summary["iat_statistics"]),
        tcp_handshake_state=str(summary["tcp_handshake_state"]),
        protocol_metadata=tuple(summary["application_protocols"]),
    )
    return BasicEvidenceV2(
        session_summary=session_summary,
        first_eight_packets=packets,
        packet_aligned_payload=tuple(item.model_projection() for item in payload_models),
        cheap_application_metadata=application,
    )


def _label_free_near_signature(basic: BasicEvidenceV2) -> str:
    """Coarsen only model-safe behavior; never include label/capture/split identity."""

    summary = basic.session_summary
    application = basic.cheap_application_metadata
    packet_shapes = [
        {
            "direction": item.direction.value,
            "l3": item.l3_protocol,
            "l4": item.l4_protocol,
            "flags": item.tcp_flags,
            "length_bucket": min(16, int(math.log2(max(1, item.packet_length)))),
        }
        for item in basic.first_eight_packets
    ]
    return content_digest(
        {
            "duration_bucket": min(16, int(math.log2(max(1.0, summary.duration + 1.0)))),
            "packet_count_bucket": min(
                24, int(math.log2(max(1, summary.bidirectional_packet_count)))
            ),
            "byte_count_bucket": min(
                32, int(math.log2(max(1, summary.bidirectional_byte_count)))
            ),
            "handshake": summary.tcp_handshake_state,
            "protocols": summary.protocol_metadata,
            "packet_shapes": packet_shapes,
            "application_protocols": application.application_protocols,
            "http_methods": application.http_methods,
            "http_status_codes": application.http_status_codes,
            "uri_shapes": application.uri_shapes,
            "content_types": application.content_types,
            "request_response_structure": application.request_response_structure,
            "auth_related_structure": application.auth_related_structure,
            "credential_field_presence": application.credential_field_presence,
            "scanner_probe_structure": application.scanner_probe_structure,
        }
    )


def _relation_evidence(
    rows: list[dict[str, Any]], arp_events: list[dict[str, Any]], dns_events: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    if not rows:
        return {}
    if len({str(row["split"]) for row in rows}) != 1:
        raise ValueError("Relation-v2 input must be local to one split")
    if len({str(row["capture_id_backend_only"]) for row in rows}) != 1:
        raise ValueError("Relation-v2 input must be local to one capture")
    split_start = min(float(row["timestamp_start"]) for row in rows)
    ip_macs: dict[str, set[str]] = defaultdict(set)
    mac_ips: dict[str, set[str]] = defaultdict(set)
    anomaly_events: list[tuple[float, str, str]] = []
    for event in sorted(arp_events, key=lambda item: (item["timestamp"], item["frame_number_backend_only"])):
        if float(event["timestamp"]) < split_start:
            continue
        ip, mac = str(event["source_ip"]), str(event["source_mac"])
        if not ip or ip == "0.0.0.0" or not mac:
            continue
        previous_macs = set(ip_macs[ip])
        previous_ips = set(mac_ips[mac])
        ip_macs[ip].add(mac)
        mac_ips[mac].add(ip)
        if len(ip_macs[ip]) > 1:
            anomaly_events.append((float(event["timestamp"]), ip, "arp_ip_multiple_macs"))
            if previous_macs and mac not in previous_macs:
                anomaly_events.append((float(event["timestamp"]), ip, "arp_mapping_change"))
        if len(mac_ips[mac]) > 1:
            for value in mac_ips[mac]:
                anomaly_events.append((float(event["timestamp"]), value, "arp_mac_multiple_ips"))
            if previous_ips and ip not in previous_ips:
                for value in mac_ips[mac]:
                    anomaly_events.append((float(event["timestamp"]), value, "arp_mapping_change"))

    dns_name_answers: dict[str, set[str]] = defaultdict(set)
    for event in sorted(dns_events, key=lambda item: item["timestamp"]):
        if float(event["timestamp"]) < split_start:
            continue
        name, answer = str(event["name_shape"]), str(event["answer"])
        if not name or not answer:
            continue
        dns_name_answers[name].add(answer)
        if len(dns_name_answers[name]) > 1:
            for value in dns_name_answers[name]:
                anomaly_events.append((float(event["timestamp"]), value, "dns_mapping_change"))

    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        endpoints = {str(row["raw_initiator_ip"]), str(row["raw_responder_ip"])}
        timestamp = float(row["timestamp_start"])
        contexts: dict[str, dict[str, Any]] = {}
        for horizon in TEMPORAL_HORIZONS_SECONDS:
            visible = [
                (event_time, endpoint, kind)
                for event_time, endpoint, kind in anomaly_events
                if endpoint in endpoints
                and event_time < timestamp
                and timestamp - event_time <= horizon
            ]
            linked = sorted({endpoint for _, endpoint, _ in visible})
            kinds = sorted({kind for _, _, kind in visible})
            contexts[str(horizon)] = {
                "schema_version": RELATION_VERSION,
                "horizon_seconds": horizon,
                "past_only": True,
                "linked_arp_observation_count": sum(
                    kind.startswith("arp_") for _, _, kind in visible
                ),
                "arp_mapping_count": len(linked),
                "arp_ip_conflict_count": sum(
                    kind == "arp_ip_multiple_macs" for _, _, kind in visible
                ),
                "arp_mapping_change_count": sum(
                    kind == "arp_mapping_change" for _, _, kind in visible
                ),
                "same_mac_multiple_ip_count": sum(
                    kind == "arp_mac_multiple_ips" for _, _, kind in visible
                ),
                "dns_relationship_count": sum(
                    kind == "dns_mapping_change" for _, _, kind in visible
                ),
                "dns_name_diversity": int("dns_mapping_change" in kinds),
                "source_fan_in": 0,
                "destination_fan_out": 0,
                "multi_source_same_target": False,
                "port_relationship_diversity": 0,
                "unexpected_responder_count": 0,
                "linked_endpoint_roles": tuple(
                    role
                    for role, endpoint in (
                        ("source", str(row["raw_initiator_ip"])),
                        ("destination", str(row["raw_responder_ip"])),
                    )
                    if endpoint in linked
                ),
                "anomaly_types": kinds,
            }
            RelationEvidenceV2.model_validate(
                {
                    key: value
                    for key, value in contexts[str(horizon)].items()
                    if key != "anomaly_types"
                }
            )
        strongest = contexts["300"]
        kinds = strongest["anomaly_types"]
        output[str(row["sample_id"])] = {
            "version": RELATION_VERSION,
            "strictly_past_only": True,
            "target_endpoint_linked": bool(strongest["linked_endpoint_roles"]),
            "arp_ip_multiple_macs": "arp_ip_multiple_macs" in kinds,
            "arp_mac_multiple_ips": "arp_mac_multiple_ips" in kinds,
            "arp_mapping_change": "arp_mapping_change" in kinds,
            "dns_mapping_change": "dns_mapping_change" in kinds,
            "anomaly_types": kinds,
            "linked_endpoint_count_backend_only": len(strongest["linked_endpoint_roles"]),
            "contexts": contexts,
        }
    return output


def _load_specs(production_root: Path) -> dict[str, dict[str, Any]]:
    manifest = json.loads(
        (production_root / "manifests/edge_label_provenance_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    output = {}
    for item in manifest["captures"]:
        if item.get("status") != "PASS" or item.get("expected_label") not in MAIN_CLASS_CANDIDATES:
            continue
        output[str(item["capture_id"])] = item
    if len(output) != 17:
        raise ValueError(f"expected 17 v3 candidate captures, found {len(output)}")
    return output


def _load_locators(production_root: Path, capture_id: str) -> list[dict[str, Any]]:
    backend = ds.dataset(
        production_root / "backend_records", format="parquet", partitioning="hive"
    )
    columns = [
        "sample_id",
        "scenario_or_capture_id",
        "timestamp_start",
        "timestamp_end",
        "raw_initiator_ip",
        "raw_responder_ip",
        "raw_initiator_port",
        "raw_responder_port",
        "l3_protocol",
        "l4_protocol",
        "first_frame_or_record",
        "last_frame_or_record",
        "fine_label",
        "coarse_label",
        "split",
        "source_identity_hash",
        "destination_identity_hash",
        "communication_pair_hash",
        "capture_provenance_status",
        "label_assignment_method",
    ]
    table = backend.to_table(
        columns=columns, filter=pc.field("scenario_or_capture_id") == capture_id
    )
    rows = table.to_pylist()
    if not rows:
        raise ValueError(f"no v2 locators for {capture_id}")
    return rows


def _checkpoint_valid(
    path: Path, *, pcap_sha256: str, locator_digest: str, packet_limit: int | None
) -> bool:
    if not path.is_file():
        return False
    value = json.loads(path.read_text(encoding="utf-8"))
    if not (
        value.get("status") == "PASS"
        and value.get("scanner_version") == SCANNER_VERSION
        and value.get("pcap_sha256") == pcap_sha256
        and value.get("locator_digest") == locator_digest
        and value.get("packet_limit") == packet_limit
    ):
        return False
    for artifact in (value.get("artifacts") or {}).values():
        artifact_path = Path(artifact["path"])
        if not artifact_path.is_file() or sha256_file(artifact_path) != artifact["sha256"]:
            return False
    return True


def build_capture(
    *,
    capture_id: str,
    spec: dict[str, Any],
    production_root: Path,
    output_root: Path,
    tshark: str,
    packet_limit: int | None,
) -> dict[str, Any]:
    locators = _load_locators(production_root, capture_id)
    pcap = Path(spec["source_mapping"]["pcap"])
    observed_sha = sha256_file(pcap)
    if observed_sha != str(spec["pcap_sha256"]):
        raise ValueError(f"PCAP identity mismatch: {capture_id}")
    locator_digest = content_digest(
        [
            [
                row["sample_id"],
                row["split"],
                row["first_frame_or_record"],
                row["last_frame_or_record"],
                _locator_identity(row),
            ]
            for row in sorted(locators, key=lambda item: str(item["sample_id"]))
        ]
    )
    safe_capture = capture_id.replace("/", "_")
    checkpoint_path = output_root / "checkpoints" / f"{safe_capture}.json"
    if _checkpoint_valid(
        checkpoint_path,
        pcap_sha256=observed_sha,
        locator_digest=locator_digest,
        packet_limit=packet_limit,
    ):
        print(f"V3_CHECKPOINT_REUSED capture={capture_id}", flush=True)
        return json.loads(checkpoint_path.read_text(encoding="utf-8"))

    print(f"V3_SCAN_START capture={capture_id} sessions={len(locators)}", flush=True)
    sessions = {str(row["sample_id"]): _new_session(row) for row in locators}
    matcher = Matcher(locators)
    packet_payload_rows: list[dict[str, Any]] = []
    arp_events: list[dict[str, Any]] = []
    dns_events: list[dict[str, Any]] = []
    packet_count = matched_packet_count = 0
    max_frame_seen = -1
    max_locator_frame = max(int(row["last_frame_or_record"]) for row in locators)
    stderr_path = output_root / "logs" / f"{safe_capture}.tshark.stderr.log"
    source_limitation: dict[str, Any] | None = None
    try:
        for raw in _iter_tshark(tshark, pcap, stderr_path, packet_limit):
            packet_count += 1
            if packet_count % 250000 == 0:
                print(
                    f"V3_SCAN_PROGRESS capture={capture_id} packets={packet_count}",
                    flush=True,
                )
            frame = safe_int(_first(raw["frame.number"]), -1)
            max_frame_seen = max(max_frame_seen, frame)
            timestamp = _float(raw["frame.time_epoch"], -1.0)
            locator = matcher.match(frame, raw) if frame >= 0 else None
            if locator is not None:
                matched_packet_count += 1
                _update_session(
                    sessions[str(locator["sample_id"])],
                    raw,
                    frame_number=frame,
                    packet_payload_rows=packet_payload_rows,
                )
            if _first(raw["arp.opcode"]) or "arp" in _first(
                raw["frame.protocols"]
            ).casefold():
                arp_events.append(
                    {
                        "frame_number_backend_only": frame,
                        "timestamp": timestamp,
                        "source_mac": _first(raw["eth.src"]),
                        "source_ip": _first(raw["arp.src.proto_ipv4"]),
                        "target_ip": _first(raw["arp.dst.proto_ipv4"]),
                    }
                )
            if _first(raw["dns.qry.name"]) and _first(raw["dns.a"]):
                from flowsec.training.evidence import normalize_dns_name

                dns_events.append(
                    {
                        "frame_number_backend_only": frame,
                        "timestamp": timestamp,
                        "name_shape": normalize_dns_name(_first(raw["dns.qry.name"])),
                        "answer": _first(raw["dns.a"]),
                    }
                )
    except RuntimeError as error:
        source_limitation = _verified_corrupt_tail_limitation(
            error=error,
            stderr_path=stderr_path,
            packet_limit=packet_limit,
            max_frame_seen=max_frame_seen,
            max_locator_frame=max_locator_frame,
        )
        if source_limitation is None:
            raise
        print(
            f"V3_SOURCE_LIMITATION_ACCEPTED capture={capture_id} "
            f"max_frame={max_frame_seen} locators_through={max_locator_frame}",
            flush=True,
        )

    raw_rows = [_finalize_session(sessions[key]) for key in sorted(sessions)]
    if packet_limit is None:
        unmatched = sum(int(row["packet_count"] == 0) for row in raw_rows)
        if unmatched:
            raise ValueError(f"session matching incomplete for {capture_id}: {unmatched}")
    payload_by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for payload_row in packet_payload_rows:
        payload_by_session[str(payload_row["session_id"])].append(payload_row)
    application_rows: list[dict[str, Any]] = []
    for row in raw_rows:
        sample_id = str(row["sample_id"])
        application = _application_contract(
            json.loads(row["application_observations_json"]),
            payload_fragments=json.loads(row["sanitized_payload_fragments_json"]),
            truncated=len(json.loads(row["application_observations_json"])) >= 24,
        )
        application_rows.append(
            {
                "version": APPLICATION_VERSION,
                "session_id": sample_id,
                "application_json": canonical_json(application.model_dump(mode="json")),
                **application.model_dump(mode="json"),
            }
        )

    temporal_rows: list[dict[str, Any]] = []
    eligibility_rows: list[dict[str, Any]] = []
    basic_rows: list[dict[str, Any]] = []
    rule_rows = [_session_for_rules(row) for row in raw_rows]
    rule_by_id = {str(row["sample_id"]): row for row in rule_rows}
    raw_by_id = {str(row["sample_id"]): row for row in raw_rows}
    relation_by_id: dict[str, dict[str, Any]] = {}
    for split in ("train", "validation", "test", "quarantine"):
        split_rows = [row for row in rule_rows if row["split"] == split]
        if not split_rows:
            continue
        split_start = min(float(row["timestamp_start"]) for row in split_rows)
        split_relations = _relation_evidence(
            split_rows,
            [event for event in arp_events if float(event["timestamp"]) >= split_start],
            [event for event in dns_events if float(event["timestamp"]) >= split_start],
        )
        relation_by_id.update(split_relations)
        contexts = build_strict_past_temporal_contexts(split_rows)
        for value in contexts:
            sample_id = str(value["sample_id"])
            row = rule_by_id[sample_id]
            temporal = value["contexts"]
            for context in temporal.values():
                validate_temporal_context(context)
            relation = split_relations[sample_id]
            assessment = assess_fine_observation_eligibility(
                str(row["fine_label_backend_only"]),
                row,
                temporal_contexts=temporal,
                relation_evidence=relation,
            )
            temporal_rows.append(
                {
                    "version": EVIDENCE_VERSION,
                    "session_id": sample_id,
                    "split": split,
                    "strictly_past_only": True,
                    "contexts_json": canonical_json(temporal),
                }
            )
            eligibility_rows.append(
                {
                    "dataset_version": OBSERVABLE_DATASET_VERSION,
                    "session_id": sample_id,
                    "capture_id_backend_only": capture_id,
                    "fine_label": row["fine_label_backend_only"],
                    "coarse_label": row["coarse_label_backend_only"],
                    "split": split,
                    "timestamp_start_backend_only": row["timestamp_start"],
                    "full_observational_sufficient": assessment[
                        "full_observational_sufficient"
                    ],
                    "basic_sufficient": assessment["basic_sufficient"],
                    "eligibility_class": assessment["eligibility_class"],
                    "exclusion_reason": assessment["exclusion_reason"],
                    "classification_ce_eligible": assessment[
                        "classification_ce_eligible"
                    ],
                    "label_propagation_only": assessment["label_propagation_only"],
                    "supporting_evidence_families_json": canonical_json(
                        assessment["supporting_evidence_families"]
                    ),
                    "supporting_reasons_json": canonical_json(
                        assessment["supporting_reasons"]
                    ),
                    "capture_provenance_status": row["capture_provenance_status"],
                    "label_assignment_method_backend_only": row["label_assignment_method"],
                    "communication_pair_hash_backend_only": row[
                        "communication_pair_hash"
                    ],
                }
            )
            basic = _basic_contract(raw_by_id[sample_id], payload_by_session[sample_id])
            basic_view = {
                **basic.model_dump(mode="json"),
                "capabilities": {
                    "PACKET_PAYLOAD": True,
                    "APPLICATION": True,
                    "TEMPORAL": True,
                    "RELATION": True,
                    "KNOWLEDGE": False,
                },
            }
            view_json = canonical_json(basic_view)
            basic_rows.append(
                {
                    "version": BASIC_VERSION,
                    "session_id_backend_only": sample_id,
                    "split_backend_only": split,
                    "view_json": view_json,
                    "view_sha256": content_digest(view_json),
                    "exact_signature": content_digest(view_json),
                    "near_signature": _label_free_near_signature(basic),
                }
            )

    if set(relation_by_id) != set(rule_by_id):
        raise ValueError(f"Relation-v2 coverage mismatch for {capture_id}")
    if len(basic_rows) != len(raw_rows) or len(application_rows) != len(raw_rows):
        raise ValueError(f"Evidence-v2 session coverage mismatch for {capture_id}")
    relation_rows = [
        {
            "session_id": sample_id,
            **{key: value for key, value in evidence.items() if key != "contexts"},
            "contexts_json": canonical_json(evidence["contexts"]),
        }
        for sample_id, evidence in sorted(relation_by_id.items())
    ]

    paths = {
        "raw_sessions": output_root / "raw_sessions" / f"{safe_capture}.parquet",
        "packet_payload": output_root / "packet_payload" / f"{safe_capture}.parquet",
        "application": output_root / "application" / f"{safe_capture}.parquet",
        "temporal": output_root / "temporal" / f"{safe_capture}.parquet",
        "relation": output_root / "relation" / f"{safe_capture}.parquet",
        "eligibility": output_root / "eligibility" / f"{safe_capture}.parquet",
        "basic_views": output_root / "basic_views" / f"{safe_capture}.parquet",
        "link_events": output_root / "link_events" / f"{safe_capture}.parquet",
    }
    _atomic_parquet(paths["raw_sessions"], raw_rows)
    _atomic_parquet(paths["packet_payload"], packet_payload_rows)
    _atomic_parquet(paths["application"], application_rows)
    _atomic_parquet(paths["temporal"], temporal_rows)
    _atomic_parquet(paths["relation"], relation_rows)
    _atomic_parquet(paths["eligibility"], eligibility_rows)
    _atomic_parquet(paths["basic_views"], basic_rows)
    link_rows = [
        {"version": RELATION_VERSION, "event_type": "ARP", **row} for row in arp_events
    ] + [{"version": RELATION_VERSION, "event_type": "DNS", **row} for row in dns_events]
    if not link_rows:
        link_rows = [
            {
                "version": RELATION_VERSION,
                "event_type": "NONE",
                "frame_number_backend_only": -1,
                "timestamp": None,
            }
        ]
    _atomic_parquet(paths["link_events"], link_rows)

    eligibility_counts = Counter(row["eligibility_class"] for row in eligibility_rows)
    split_eligible = Counter(
        row["split"] for row in eligibility_rows if row["full_observational_sufficient"]
    )
    checkpoint = {
        "status": "PASS",
        "scanner_version": SCANNER_VERSION,
        "dataset_version": OBSERVABLE_DATASET_VERSION,
        "evidence_version": EVIDENCE_VERSION,
        "capture_id_backend_only": capture_id,
        "fine_label": spec["expected_label"],
        "pcap_path_backend_only": str(pcap),
        "pcap_sha256": observed_sha,
        "locator_digest": locator_digest,
        "packet_limit": packet_limit,
        "packet_count": packet_count,
        "matched_packet_count": matched_packet_count,
        "session_count": len(raw_rows),
        "packet_payload_row_count": len(packet_payload_rows),
        "arp_event_count": len(arp_events),
        "dns_event_count": len(dns_events),
        "source_limitation": source_limitation,
        "eligibility_distribution": dict(sorted(eligibility_counts.items())),
        "eligible_split_distribution": dict(sorted(split_eligible.items())),
        "artifacts": {name: _artifact(path) for name, path in paths.items()},
    }
    _atomic_json(checkpoint_path, checkpoint)
    print(
        f"V3_SCAN_DONE capture={capture_id} packets={packet_count} "
        f"eligible={sum(split_eligible.values())}",
        flush=True,
    )
    return checkpoint


def reassess_capture(
    *,
    capture_id: str,
    output_root: Path,
    rebuild_temporal_cross_split_past: bool = False,
) -> dict[str, Any]:
    """Reapply the deterministic eligibility contract without rerunning tshark."""

    safe_capture = capture_id.replace("/", "_")
    checkpoint_path = output_root / "checkpoints" / f"{safe_capture}.json"
    if not checkpoint_path.is_file():
        raise ValueError(f"missing capture checkpoint for reassessment: {capture_id}")
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    if checkpoint.get("status") != "PASS" or checkpoint.get("packet_limit") is not None:
        raise ValueError(f"capture checkpoint is not a full PASS: {capture_id}")
    artifacts = checkpoint.get("artifacts") or {}
    for required in ("raw_sessions", "temporal", "relation", "eligibility"):
        artifact = artifacts.get(required) or {}
        path = Path(str(artifact.get("path") or ""))
        if not path.is_file() or sha256_file(path) != artifact.get("sha256"):
            raise ValueError(f"invalid reassessment source artifact {required}: {capture_id}")

    raw_rows = pq.read_table(Path(artifacts["raw_sessions"]["path"])).to_pylist()
    relation_rows = pq.read_table(Path(artifacts["relation"]["path"])).to_pylist()
    relation_by_id = {
        str(row["session_id"]): {
            **row,
            "contexts": json.loads(row["contexts_json"]),
        }
        for row in relation_rows
    }
    rule_rows = [_session_for_rules(row) for row in raw_rows]
    temporal_path = Path(artifacts["temporal"]["path"])
    if rebuild_temporal_cross_split_past:
        rebuilt = build_strict_past_temporal_contexts(
            rule_rows, allow_prior_cross_split=True
        )
        temporal_rows = [
            {
                "version": EVIDENCE_VERSION,
                "session_id": str(value["sample_id"]),
                "split": str(value["split"]),
                "strictly_past_only": True,
                "context_scope": "CAPTURE_CHRONOLOGICAL_STRICT_PAST",
                "contexts_json": canonical_json(value["contexts"]),
            }
            for value in rebuilt
        ]
        _atomic_parquet(temporal_path, temporal_rows)
        checkpoint["artifacts"]["temporal"] = _artifact(temporal_path)
        checkpoint["temporal_context_scope"] = (
            "CAPTURE_CHRONOLOGICAL_STRICT_PAST_INCLUDES_EARLIER_SPLITS_AND_QUARANTINE"
        )
    else:
        temporal_rows = pq.read_table(temporal_path).to_pylist()
    temporal_by_id = {
        str(row["session_id"]): json.loads(row["contexts_json"])
        for row in temporal_rows
    }
    if set(temporal_by_id) != {str(row["sample_id"]) for row in rule_rows}:
        raise ValueError(f"Temporal-v2 reassessment coverage mismatch: {capture_id}")
    if set(relation_by_id) != {str(row["sample_id"]) for row in rule_rows}:
        raise ValueError(f"Relation-v2 reassessment coverage mismatch: {capture_id}")

    eligibility_rows: list[dict[str, Any]] = []
    for row in rule_rows:
        sample_id = str(row["sample_id"])
        assessment = assess_fine_observation_eligibility(
            str(row["fine_label_backend_only"]),
            row,
            temporal_contexts=temporal_by_id[sample_id],
            relation_evidence=relation_by_id[sample_id],
        )
        eligibility_rows.append(
            {
                "dataset_version": OBSERVABLE_DATASET_VERSION,
                "eligibility_policy_version": assessment["eligibility_policy_version"],
                "session_id": sample_id,
                "capture_id_backend_only": capture_id,
                "fine_label": row["fine_label_backend_only"],
                "coarse_label": row["coarse_label_backend_only"],
                "split": row["split"],
                "timestamp_start_backend_only": row["timestamp_start"],
                "full_observational_sufficient": assessment[
                    "full_observational_sufficient"
                ],
                "basic_sufficient": assessment["basic_sufficient"],
                "eligibility_class": assessment["eligibility_class"],
                "exclusion_reason": assessment["exclusion_reason"],
                "classification_ce_eligible": assessment[
                    "classification_ce_eligible"
                ],
                "label_propagation_only": assessment["label_propagation_only"],
                "supporting_evidence_families_json": canonical_json(
                    assessment["supporting_evidence_families"]
                ),
                "supporting_reasons_json": canonical_json(
                    assessment["supporting_reasons"]
                ),
                "capture_provenance_status": row["capture_provenance_status"],
                "label_assignment_method_backend_only": row[
                    "label_assignment_method"
                ],
                "communication_pair_hash_backend_only": row[
                    "communication_pair_hash"
                ],
            }
        )
    eligibility_path = Path(artifacts["eligibility"]["path"])
    _atomic_parquet(eligibility_path, eligibility_rows)
    checkpoint["eligibility_policy_version"] = ELIGIBILITY_POLICY_VERSION
    checkpoint["eligibility_reassessed_without_packet_rescan"] = True
    checkpoint["eligibility_distribution"] = dict(
        sorted(Counter(row["eligibility_class"] for row in eligibility_rows).items())
    )
    checkpoint["eligible_split_distribution"] = dict(
        sorted(
            Counter(
                row["split"]
                for row in eligibility_rows
                if row["full_observational_sufficient"]
            ).items()
        )
    )
    checkpoint["artifacts"]["eligibility"] = _artifact(eligibility_path)
    _atomic_json(checkpoint_path, checkpoint)
    print(
        f"V3_REASSESS_DONE capture={capture_id} "
        f"eligible={sum(checkpoint['eligible_split_distribution'].values())}",
        flush=True,
    )
    return checkpoint


def finalize(output_root: Path, expected_capture_count: int = 17) -> dict[str, Any]:
    checkpoints = []
    for path in sorted((output_root / "checkpoints").glob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("packet_limit") is None and value.get("status") == "PASS":
            checkpoints.append(value)
    if len(checkpoints) != expected_capture_count:
        raise ValueError(
            f"full v3 capture gate requires {expected_capture_count} checkpoints; found {len(checkpoints)}"
        )
    table = ds.dataset(output_root / "eligibility", format="parquet").to_table()
    rows = table.to_pylist()
    identity_counts = Counter(str(row["session_id"]) for row in rows)
    duplicate_ids = sum(int(value > 1) for value in identity_counts.values())
    class_split: dict[str, Counter[str]] = defaultdict(Counter)
    class_original: Counter[str] = Counter()
    class_eligible: Counter[str] = Counter()
    class_removed: dict[str, Counter[str]] = defaultdict(Counter)
    basic_sufficient: Counter[str] = Counter()
    family_needs: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        label, split = str(row["fine_label"]), str(row["split"])
        class_original[label] += 1
        if row["full_observational_sufficient"]:
            class_eligible[label] += 1
            class_split[label][split] += 1
            basic_sufficient[label] += int(row["basic_sufficient"])
            for family in json.loads(row["supporting_evidence_families_json"]):
                family_needs[label][str(family)] += int(not row["basic_sufficient"])
        else:
            class_removed[label][str(row["eligibility_class"])] += 1
    split_identity_sets = {
        split: {
            str(row["session_id"])
            for row in rows
            if row["split"] == split and row["full_observational_sufficient"]
        }
        for split in ("train", "validation", "test")
    }
    overlap = {
        "train_validation": len(split_identity_sets["train"] & split_identity_sets["validation"]),
        "train_test": len(split_identity_sets["train"] & split_identity_sets["test"]),
        "validation_test": len(split_identity_sets["validation"] & split_identity_sets["test"]),
    }
    per_class = {}
    for label in MAIN_CLASS_CANDIDATES:
        eligible = class_eligible[label]
        per_class[label] = {
            "class": label,
            "original_n": class_original[label],
            "eligible_n": eligible,
            "removed_generic_n": class_removed[label]["GENERIC_BACKGROUND"],
            "removed_unobservable_n": class_removed[label]["NETWORK_UNOBSERVABLE"],
            "removed_wrong_granularity_n": class_removed[label]["WRONG_GRANULARITY"],
            "removed_label_propagation_only_n": class_removed[label]["LABEL_PROPAGATION_ONLY"],
            "train_n": class_split[label]["train"],
            "validation_n": class_split[label]["validation"],
            "test_n": class_split[label]["test"],
            "quarantine_n": class_split[label]["quarantine"],
            "basic_sufficient_rate": basic_sufficient[label] / eligible if eligible else 0.0,
            "needs_packet_payload_rate": family_needs[label]["PACKET_PAYLOAD"] / eligible if eligible else 0.0,
            "needs_application_rate": family_needs[label]["APPLICATION"] / eligible if eligible else 0.0,
            "needs_temporal_rate": family_needs[label]["TEMPORAL"] / eligible if eligible else 0.0,
            "needs_relation_rate": family_needs[label]["RELATION"] / eligible if eligible else 0.0,
            "needs_knowledge_rate": family_needs[label]["KNOWLEDGE"] / eligible if eligible else 0.0,
        }
    gate = {
        "OBSERVABLE_DATASET_V3_PREFLIGHT": "PASS"
        if not duplicate_ids and not any(overlap.values())
        else "FAIL",
        "dataset_version": OBSERVABLE_DATASET_VERSION,
        "evidence_version": EVIDENCE_VERSION,
        "capture_count": len(checkpoints),
        "session_count": len(rows),
        "duplicate_identity_count": duplicate_ids,
        "eligible_cross_split_identity_overlap": overlap,
        "split_protocol": "CONSTRAINED_CHRONOLOGICAL_BOUNDARY_V2_FILTERED",
        "per_class": per_class,
        "capture_checkpoints": [
            {
                "capture_id": value["capture_id_backend_only"],
                "fine_label": value["fine_label"],
                "pcap_sha256": value["pcap_sha256"],
                "locator_digest": value["locator_digest"],
                "packet_count": value["packet_count"],
                "session_count": value["session_count"],
                "eligibility_distribution": value["eligibility_distribution"],
            }
            for value in sorted(checkpoints, key=lambda item: item["capture_id_backend_only"])
        ],
    }
    path = output_root / "manifests/observable_dataset_v3_preflight.json"
    _atomic_json(path, gate)
    print(f"V3_PREFLIGHT={gate['OBSERVABLE_DATASET_V3_PREFLIGHT']} path={path}", flush=True)
    return gate


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production-root", type=Path, default=DEFAULT_PRODUCTION_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--capture", action="append", default=[])
    parser.add_argument("--tshark", default="tshark")
    parser.add_argument("--packet-limit", type=int)
    parser.add_argument("--finalize-only", action="store_true")
    parser.add_argument("--reassess-only", action="store_true")
    parser.add_argument("--rebuild-temporal-cross-split-past", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    production_root = args.production_root.resolve()
    output_root = args.output_root.resolve()
    if args.packet_limit is not None and args.packet_limit < 1:
        raise ValueError("--packet-limit must be positive")
    if args.finalize_only:
        finalize(output_root)
        return 0
    specs = _load_specs(production_root)
    selected = args.capture or sorted(specs)
    unknown = sorted(set(selected) - set(specs))
    if unknown:
        raise ValueError(f"unknown/non-candidate captures: {unknown}")
    if args.reassess_only:
        if args.packet_limit is not None:
            raise ValueError("--reassess-only cannot be combined with --packet-limit")
        for capture_id in selected:
            reassess_capture(
                capture_id=capture_id,
                output_root=output_root,
                rebuild_temporal_cross_split_past=args.rebuild_temporal_cross_split_past,
            )
        if not args.capture:
            finalize(output_root)
        return 0
    for capture_id in selected:
        build_capture(
            capture_id=capture_id,
            spec=specs[capture_id],
            production_root=production_root,
            output_root=output_root,
            tshark=args.tshark,
            packet_limit=args.packet_limit,
        )
    if not args.capture and args.packet_limit is None:
        finalize(output_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
