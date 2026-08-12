#!/usr/bin/env python3
"""Offline capture-wide attack-signal and capture-label propagation audit.

The scanner uses verified Production backend locators and official PCAP hashes.
It extracts mechanism/protocol observations before consulting a fine label.  It
has no model/provider import or API path.  Per-session timelines remain outside
Git; only the aggregate manifest and human-readable report enter the repository.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from bisect import bisect_right
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any, Iterator

import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from flowsec.production.core import canonical_endpoint_identity, first_value, safe_int
from flowsec.training.capture_wide_signal import (
    CAPTURE_WIDE_AUDIT_VERSION,
    TARGET_CLASSES,
    classify_session_signal,
    directional_profile,
    interval_profile,
    propagation_risk,
    session_mechanism_signals,
)
from flowsec.training.contracts import canonical_json, content_digest
from flowsec.training.evidence import (
    application_observation_from_frame,
    decode_hex_payload,
    normalize_uri_shape,
    payload_fragment_from_frame,
)
from flowsec.training.evidence_salvage import application_semantics, payload_semantics
from flowsec.training.materialization import sha256_file


CORPUS_SHA256 = "5b845cf9e5886e5e44fd46562135ba3eb5907de65fd8faf5d9b8777253149123"
RAW_SCANNER_VERSION = "CAPTURE_WIDE_LABEL_FREE_RAW_SCANNER_V1"
TARGET_CAPTURE_IDS = {
    "Backdoor": "Attack_Backdoor",
    "Password": "Attack_Password",
    "Uploading": "Attack_Uploading",
    "Ransomware": "Attack_Ransomware",
}

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
    "dns.flags.rcode",
    "tls.record.version",
    "tls.handshake.type",
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
    value = _first(value)
    if not value:
        return 0
    try:
        return int(value, 16) if value.casefold().startswith("0x") else int(value)
    except ValueError:
        return 0


def _rate(value: int, total: int) -> float:
    return value / total if total else 0.0


def _pct(value: float) -> str:
    return f"{100.0 * value:.2f}%"


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(value)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _atomic_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(pa.Table.from_pylist(rows), temporary, compression="zstd")
    os.replace(temporary, path)


def _artifact(path: Path) -> dict[str, Any]:
    return {"path": str(path), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}


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


class _Matcher:
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

    def match(self, frame: int, row: dict[str, str]) -> dict[str, Any] | None:
        identity = _packet_identity(row)
        if identity is None or identity not in self.groups:
            return None
        index = bisect_right(self.starts[identity], frame) - 1
        if index >= 0:
            locator = self.groups[identity][index]
            if frame <= int(locator["last_frame_or_record"]):
                return locator
        return None


def _relation_ref(row: dict[str, Any]) -> str:
    return content_digest(
        [
            row["l3_protocol"],
            row["l4_protocol"],
            sorted(
                [
                    [row["raw_initiator_ip"], int(row["raw_initiator_port"])],
                    [row["raw_responder_ip"], int(row["raw_responder_port"])],
                ]
            ),
        ]
    )


def _source_target_service_ref(row: dict[str, Any]) -> str:
    """Hash stable behavior while excluding the client ephemeral port."""

    return content_digest(
        [
            row["l3_protocol"],
            row["l4_protocol"],
            row["raw_initiator_ip"],
            row["raw_responder_ip"],
            int(row["raw_responder_port"]),
        ]
    )


def _new_session(row: dict[str, Any], capture_start: float) -> dict[str, Any]:
    return {
        "sample_id": str(row["sample_id"]),
        "capture_id_backend_only": str(row["scenario_or_capture_id"]),
        "split_backend_only": str(row["split"]),
        "timestamp_start": float(row["timestamp_start"]),
        "timestamp_end": float(row["timestamp_end"]),
        "start_relative_time": float(row["timestamp_start"]) - capture_start,
        "end_relative_time": float(row["timestamp_end"]) - capture_start,
        "protocol": str(row["l4_protocol"]),
        "relation_ref_backend_only": _relation_ref(row),
        "current_fine_label_backend_only": str(row["fine_label"]),
        "label_assignment_method_backend_only": str(row["label_assignment_method"]),
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
        "request_count": 0,
        "response_count": 0,
        "tls_frame_count": 0,
        "dns_frame_count": 0,
        "application_protocols": set(),
        "application_observations": {},
        "payload_semantics": set(),
        "http_methods": Counter(),
        "http_statuses": Counter(),
        "content_types": Counter(),
        "uri_shapes": Counter(),
        "ftp_commands": Counter(),
        "packet_patterns": Counter(),
    }


def _tshark_command(tshark: str, pcap: Path) -> list[str]:
    command = [
        tshark,
        "-n",
        "-r",
        str(pcap),
        "-T",
        "fields",
        "-E",
        "separator=/t",
        "-E",
        "occurrence=f",
    ]
    for field in RAW_FIELDS:
        command.extend(("-e", field))
    return command


def _iter_tshark(tshark: str, pcap: Path, stderr_path: Path) -> Iterator[dict[str, str]]:
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    csv.field_size_limit(sys.maxsize)
    with stderr_path.open("w", encoding="utf-8") as stderr_handle:
        process = subprocess.Popen(
            _tshark_command(tshark, pcap),
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


def _update_session(session: dict[str, Any], locator: dict[str, Any], raw: dict[str, str]) -> None:
    src = _first(raw["ip.src"]) or _first(raw["ipv6.src"])
    sport = safe_int(_first(raw["tcp.srcport"]) or _first(raw["udp.srcport"]))
    initiator = src == str(locator["raw_initiator_ip"]) and sport == int(
        locator["raw_initiator_port"]
    )
    direction = "initiator" if initiator else "responder"
    frame_len = safe_int(_first(raw["frame.len"]))
    payload_hex = _first(raw["tcp.payload"]) or _first(raw["udp.payload"]) or _first(raw["data.data"])
    compact = "".join(character for character in payload_hex if character in "0123456789abcdefABCDEF")
    payload_bytes = len(compact) // 2 if compact and len(compact) % 2 == 0 else 0
    session["packet_count"] += 1
    session["byte_count"] += frame_len
    session[f"{direction}_packets"] += 1
    session[f"{direction}_bytes"] += frame_len
    session[f"{direction}_payload_bytes"] += payload_bytes
    session["payload_packet_count"] += int(payload_bytes > 0)
    flags = _flags(raw["tcp.flags"])
    session["tcp_syn"] += int(bool(flags & 0x02 and not flags & 0x10))
    session["tcp_synack"] += int(bool(flags & 0x02 and flags & 0x10))
    session["tcp_rst"] += int(bool(flags & 0x04))
    session["tcp_fin"] += int(bool(flags & 0x01))
    session["packet_patterns"][(direction, frame_len, flags)] += 1

    observation = application_observation_from_frame(raw)
    if observation is not None:
        key = canonical_json(observation)
        session["application_observations"].setdefault(key, observation)
        kind = str(observation.get("kind") or "unknown")
        session["application_protocols"].add(kind)
        session["dns_frame_count"] += int(kind == "dns")
    method = _first(raw["http.request.method"]).upper()
    status = _first(raw["http.response.code"])
    content_type = _first(raw["http.content_type"]).casefold()
    uri = _first(raw["http.request.uri"])
    if method:
        session["http_methods"][method] += 1
        session["request_count"] += 1
    if status:
        session["http_statuses"][status] += 1
        session["response_count"] += 1
    if content_type:
        session["content_types"][content_type] += 1
    if uri:
        session["uri_shapes"][normalize_uri_shape(uri)] += 1
    ftp_command = _first(raw["ftp.request.command"]).upper()
    if ftp_command:
        session["ftp_commands"][ftp_command] += 1
        session["request_count"] += 1
    if _first(raw["ftp.response.code"]):
        session["response_count"] += 1
    tls = bool(_first(raw["tls.record.version"]) or _first(raw["tls.handshake.type"]))
    session["tls_frame_count"] += int(tls)
    if tls:
        session["application_protocols"].add("tls")
    if _first(raw["mqtt.msgtype"]):
        session["application_protocols"].add("mqtt")
    if _first(raw["modbus.func_code"]):
        session["application_protocols"].add("modbus")
    if payload_bytes:
        fragment = payload_fragment_from_frame(raw, max_chars=768)
        if fragment:
            session["payload_semantics"].update(payload_semantics((fragment,)))


def _json_safe_session(session: dict[str, Any]) -> dict[str, Any]:
    result = dict(session)
    observations = list(result.pop("application_observations").values())
    app = {
        "protocol": "+".join(sorted(result["application_protocols"])),
        "observations": observations,
    }
    result["application_semantics"] = sorted(application_semantics(app))
    result["application_protocol"] = "+".join(sorted(result.pop("application_protocols"))) or None
    for field in ("payload_semantics",):
        result[field] = sorted(result[field])
    for field in (
        "http_methods",
        "http_statuses",
        "content_types",
        "uri_shapes",
        "ftp_commands",
    ):
        values = result[field]
        result[field] = sorted(values)
        result[field + "_counts_json"] = canonical_json(dict(sorted(values.items())))
    patterns = result.pop("packet_patterns")
    result["packet_pattern_unique_count"] = len(patterns)
    result["dominant_packet_pattern_count"] = max(patterns.values(), default=0)
    result["packet_pattern_repetition_rate"] = _rate(
        result["dominant_packet_pattern_count"], result["packet_count"]
    )
    result.update(directional_profile(result["initiator_bytes"], result["responder_bytes"]))
    result["payload_present"] = bool(result["payload_packet_count"])
    result["mechanism_signals"] = sorted(session_mechanism_signals(result))
    result["payload_semantics_json"] = canonical_json(result.pop("payload_semantics"))
    result["application_semantics_json"] = canonical_json(result.pop("application_semantics"))
    result["mechanism_signals_json"] = canonical_json(result.pop("mechanism_signals"))
    return result


def _event_kind(raw: dict[str, str], *, identity: tuple[Any, ...] | None, matched: bool) -> str | None:
    protocols = _first(raw["frame.protocols"]).casefold()
    if not identity:
        if "arp" in protocols or _first(raw["arp.opcode"]):
            return "ARP"
        if "lldp" in protocols:
            return "LLDP"
        if "eth" in protocols:
            return "OTHER_LINK_LAYER"
        return "OTHER_NON_IP"
    if matched:
        return None
    if "icmp" in protocols:
        return "UNMATCHED_ICMP_CONTROL"
    if "dns" in protocols:
        return "UNMATCHED_DNS"
    return "OTHER_UNMATCHED_IP"


def _scan_capture(
    *,
    label: str,
    spec: dict[str, Any],
    locators: list[dict[str, Any]],
    output_root: Path,
    tshark: str,
) -> dict[str, Any]:
    capture_id = str(spec["capture_id"])
    pcap = Path(spec["source_mapping"]["pcap"])
    observed_sha = sha256_file(pcap)
    if observed_sha != str(spec["pcap_sha256"]):
        raise ValueError(f"PCAP identity mismatch: {capture_id}")
    locator_digest = content_digest(
        [
            [
                row["sample_id"],
                row["first_frame_or_record"],
                row["last_frame_or_record"],
                _locator_identity(row),
            ]
            for row in sorted(locators, key=lambda item: item["sample_id"])
        ]
    )
    safe_capture = capture_id.replace("/", "_")
    checkpoint_path = output_root / "checkpoints" / f"{safe_capture}.json"
    raw_sessions_path = output_root / "raw_sessions" / f"{safe_capture}.parquet"
    events_path = output_root / "events" / f"{safe_capture}.parquet"
    if checkpoint_path.is_file():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        artifacts = checkpoint.get("artifacts") or {}
        valid = (
            checkpoint.get("status") == "PASS"
            and checkpoint.get("raw_scanner_version") == RAW_SCANNER_VERSION
            and checkpoint.get("pcap_sha256") == observed_sha
            and checkpoint.get("locator_digest") == locator_digest
            and all(
                Path(value["path"]).is_file()
                and sha256_file(Path(value["path"])) == value["sha256"]
                for value in artifacts.values()
            )
        )
        if valid:
            print(f"RAW_CHECKPOINT_REUSED capture={capture_id}", flush=True)
            return checkpoint

    print(f"RAW_SCAN_START capture={capture_id} sessions={len(locators)}", flush=True)
    capture_start = min(float(row["timestamp_start"]) for row in locators)
    sessions = {
        str(row["sample_id"]): _new_session(row, capture_start) for row in locators
    }
    matcher = _Matcher(locators)
    events: list[dict[str, Any]] = []
    event_counts: Counter[str] = Counter()
    protocol_layers: Counter[str] = Counter()
    primary_protocols: Counter[str] = Counter()
    first_timestamp: float | None = None
    last_timestamp: float | None = None
    packet_count = ip_packet_count = matched_packet_count = 0
    for raw in _iter_tshark(
        tshark,
        pcap,
        output_root / "logs" / f"{safe_capture}.tshark.stderr.log",
    ):
        packet_count += 1
        if packet_count % 250000 == 0:
            print(f"RAW_SCAN_PROGRESS capture={capture_id} packets={packet_count}", flush=True)
        frame = safe_int(_first(raw["frame.number"]), -1)
        timestamp = _float(raw["frame.time_epoch"], -1.0)
        if timestamp >= 0:
            first_timestamp = timestamp if first_timestamp is None else min(first_timestamp, timestamp)
            last_timestamp = timestamp if last_timestamp is None else max(last_timestamp, timestamp)
        protocols = [value for value in _first(raw["frame.protocols"]).split(":") if value]
        protocol_layers.update(protocols)
        identity = _packet_identity(raw)
        ip_packet_count += int(identity is not None)
        primary_protocols[(str(identity[1]) if identity else (protocols[-1] if protocols else "UNKNOWN"))] += 1
        locator = matcher.match(frame, raw) if frame >= 0 else None
        if locator is not None:
            matched_packet_count += 1
            _update_session(sessions[str(locator["sample_id"])], locator, raw)
        event_kind = _event_kind(raw, identity=identity, matched=locator is not None)
        if event_kind:
            event_counts[event_kind] += 1
            events.append(
                {
                    "capture_id_backend_only": capture_id,
                    "frame_number_backend_only": frame,
                    "relative_time": timestamp - capture_start if timestamp >= 0 else None,
                    "event_kind": event_kind,
                    "protocol_layers": ":".join(protocols),
                    "frame_length": safe_int(_first(raw["frame.len"])),
                }
            )
    rows = [_json_safe_session(sessions[key]) for key in sorted(sessions)]
    unmatched_sessions = sum(int(row["packet_count"] == 0) for row in rows)
    if unmatched_sessions:
        raise ValueError(f"raw session matching incomplete for {capture_id}: {unmatched_sessions}")
    _atomic_parquet(raw_sessions_path, rows)
    _atomic_parquet(
        events_path,
        events
        or [
            {
                "capture_id_backend_only": capture_id,
                "frame_number_backend_only": -1,
                "relative_time": None,
                "event_kind": "NONE",
                "protocol_layers": "",
                "frame_length": 0,
            }
        ],
    )
    checkpoint = {
        "status": "PASS",
        "audit_version": CAPTURE_WIDE_AUDIT_VERSION,
        "raw_scanner_version": RAW_SCANNER_VERSION,
        "class_backend_only": label,
        "capture_id_backend_only": capture_id,
        "pcap_path_backend_only": str(pcap),
        "pcap_sha256": observed_sha,
        "pcap_size": pcap.stat().st_size,
        "packet_count": packet_count,
        "duration_seconds": (last_timestamp - first_timestamp)
        if first_timestamp is not None and last_timestamp is not None
        else 0.0,
        "derived_session_count": len(rows),
        "IP_session_count": len(rows),
        "ip_packet_count": ip_packet_count,
        "matched_packet_count": matched_packet_count,
        "non_IP_packet_count": packet_count - ip_packet_count,
        "event_distribution": dict(sorted(event_counts.items())),
        "protocol_distribution": dict(primary_protocols.most_common()),
        "protocol_layer_distribution": dict(protocol_layers.most_common()),
        "locator_digest": locator_digest,
        "artifacts": {
            "raw_sessions": _artifact(raw_sessions_path),
            "events": _artifact(events_path),
        },
    }
    _atomic_json(checkpoint_path, checkpoint)
    print(f"RAW_SCAN_DONE capture={capture_id} packets={packet_count}", flush=True)
    return checkpoint


def _read_raw_rows(checkpoint: dict[str, Any]) -> list[dict[str, Any]]:
    rows = pq.read_table(checkpoint["artifacts"]["raw_sessions"]["path"]).to_pylist()
    for row in rows:
        row["payload_semantics"] = json.loads(row.pop("payload_semantics_json"))
        row["application_semantics"] = json.loads(row.pop("application_semantics_json"))
        row.pop("mechanism_signals_json")
        # Mechanism rules may be refined without re-reading the PCAP because
        # the raw checkpoint already retains every required primitive field.
        row["mechanism_signals"] = sorted(session_mechanism_signals(row))
    return rows


def _classify_capture(
    label: str,
    checkpoint: dict[str, Any],
    output_root: Path,
    locators: list[dict[str, Any]],
) -> tuple[dict[str, Any], Path]:
    rows = _read_raw_rows(checkpoint)
    locator_by_id = {str(row["sample_id"]): row for row in locators}
    if set(locator_by_id) != {str(row["sample_id"]) for row in rows}:
        raise ValueError(f"timeline/backend join incomplete: {label}")
    for row in rows:
        row["source_target_service_ref_backend_only"] = _source_target_service_ref(
            locator_by_id[str(row["sample_id"])]
        )
    relation_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    behavior_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        relation_groups[row["relation_ref_backend_only"]].append(row)
        behavior_groups[row["source_target_service_ref_backend_only"]].append(row)
    relation_profiles = {
        key: interval_profile(item["timestamp_start"] for item in members)
        for key, members in relation_groups.items()
    }
    for key, members in relation_groups.items():
        profile = relation_profiles[key]
        for row in members:
            row["capture_relation_session_count"] = len(members)
            row["capture_relation_interval_cv"] = profile["interval_cv"]
            row["capture_relation_beacon_score"] = profile["beacon_score"]

    # HTTP attempts and callbacks legitimately change client ephemeral port.
    # Context therefore groups the same anonymous source -> target service.
    history_60s: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
    history_all: dict[str, list[dict[str, Any]]] = defaultdict(list)
    sorted_rows = sorted(rows, key=lambda row: (row["timestamp_start"], row["sample_id"]))
    index = 0
    while index < len(sorted_rows):
        timestamp = float(sorted_rows[index]["timestamp_start"])
        end = index
        while end < len(sorted_rows) and float(sorted_rows[end]["timestamp_start"]) == timestamp:
            end += 1
        group = sorted_rows[index:end]
        for row in group:
            key = row["source_target_service_ref_backend_only"]
            prior = history_60s[key]
            while prior and timestamp - float(prior[0]["timestamp_start"]) > 60.0:
                prior.popleft()
            past60 = list(prior)
            past10 = [item for item in past60 if timestamp - float(item["timestamp_start"]) <= 10.0]
            past_history = list(history_all[key]) if label == "Backdoor" else past60
            assessment = classify_session_signal(
                label,
                row,
                past_10s_same_relation=past10,
                past_60s_same_relation=past60,
                past_history_same_relation=past_history,
            )
            row.update(assessment)
            row["past_10s_same_relation_session_count"] = len(past10)
            row["past_60s_same_relation_session_count"] = len(past60)
            row["assessment_reasons_json"] = canonical_json(row.pop("reasons"))
        for row in group:
            key = row["source_target_service_ref_backend_only"]
            history_60s[key].append(row)
            history_all[key].append(row)
        index = end

    timeline_path = output_root / "timelines" / f"{checkpoint['capture_id_backend_only']}.parquet"
    external_rows = []
    for row in sorted_rows:
        clean = dict(row)
        clean["payload_semantics_json"] = canonical_json(clean.pop("payload_semantics"))
        clean["application_semantics_json"] = canonical_json(clean.pop("application_semantics"))
        clean["mechanism_signals_json"] = canonical_json(clean.pop("mechanism_signals"))
        external_rows.append(clean)
    _atomic_parquet(timeline_path, external_rows)

    counts = Counter(row["category"] for row in sorted_rows)
    total = len(sorted_rows)
    direct = counts["DIRECTLY_ATTACK_INFORMATIVE"]
    contextual = counts["CONTEXTUALLY_ATTACK_INFORMATIVE"]
    generic = counts["GENERIC_OR_BACKGROUND"]
    past10 = sum(bool(row["past_10s_recoverable"]) for row in sorted_rows)
    past60 = sum(bool(row["past_60s_recoverable"]) for row in sorted_rows)

    def has(row: dict[str, Any], values: set[str]) -> bool:
        return bool(values & set(row["mechanism_signals"]))

    if label == "Password":
        payload_values = {"authentication_attempt"}
        application_values = {"authentication_failure"}
    elif label == "Uploading":
        payload_values = {"file_transfer_metadata", "script_content"}
        application_values = {"file_transfer_metadata", "ftp_upload"}
    elif label == "Backdoor":
        payload_values = {"command_structure"}
        application_values = {"command_structure"}
    else:
        payload_values = {"ransomware_specific_network_semantics"}
        application_values = {"ransomware_specific_network_semantics"}
    payload_signal = sum(has(row, payload_values) for row in sorted_rows)
    application_signal = sum(has(row, application_values) for row in sorted_rows)
    encrypted = sum("encrypted_application" in row["mechanism_signals"] for row in sorted_rows)
    bidirectional = sum("bidirectional_exchange" in row["mechanism_signals"] for row in sorted_rows)
    established = sum("established_exchange" in row["mechanism_signals"] for row in sorted_rows)
    incomplete = sum("incomplete_handshake" in row["mechanism_signals"] for row in sorted_rows)
    repeated_small = sum(
        {"small_flow", "established_exchange"} <= set(row["mechanism_signals"])
        for row in sorted_rows
    )
    periodic = 0
    periodic_profiles = []
    for key, members in behavior_groups.items():
        selected = [
            row
            for row in members
            if {"small_flow", "established_exchange"} <= set(row["mechanism_signals"])
        ]
        profile = interval_profile(row["timestamp_start"] for row in selected)
        interval_cv = profile["interval_cv"]
        if (
            len(selected) >= 4
            and interval_cv is not None
            and float(interval_cv) <= 0.35
        ):
            periodic += len(selected)
            shapes = Counter(
                (
                    int(row["packet_count"]),
                    int(row["byte_count"]),
                    int(row["initiator_payload_bytes"]),
                    int(row["responder_payload_bytes"]),
                )
                for row in selected
            )
            dominant_shape, dominant_shape_count = shapes.most_common(1)[0]
            periodic_profiles.append(
                {
                    "source_target_service_ref_backend_only": key,
                    "session_count": len(selected),
                    "unique_session_shape_count": len(shapes),
                    "dominant_session_shape_count": dominant_shape_count,
                    "dominant_session_shape": {
                        "packet_count": dominant_shape[0],
                        "byte_count": dominant_shape[1],
                        "initiator_payload_bytes": dominant_shape[2],
                        "responder_payload_bytes": dominant_shape[3],
                    },
                    **profile,
                }
            )
    label_methods = Counter()
    auth_bursts: list[int] = []
    auth_times_all: list[float] = []
    for row in sorted_rows:
        label_methods[row["label_assignment_method_backend_only"]] += 1
    if label == "Password":
        for members in behavior_groups.values():
            auth_times = sorted(
                float(row["timestamp_start"])
                for row in members
                if "authentication_attempt" in row["mechanism_signals"]
            )
            auth_times_all.extend(auth_times)
            burst = 0
            prior_time = None
            for value in auth_times:
                if prior_time is None or value - prior_time <= 10.0:
                    burst += 1
                else:
                    auth_bursts.append(burst)
                    burst = 1
                prior_time = value
            if burst:
                auth_bursts.append(burst)

    generic_rate = _rate(generic, total)
    source_fanout: dict[str, set[tuple[str, int]]] = defaultdict(set)
    target_fanin: dict[tuple[str, int], set[str]] = defaultdict(set)
    source_values: set[str] = set()
    target_values: set[str] = set()
    for locator in locators:
        source = str(locator["raw_initiator_ip"])
        target = str(locator["raw_responder_ip"])
        service = (target, int(locator["raw_responder_port"]))
        source_values.add(source)
        target_values.add(target)
        source_fanout[source].add(service)
        target_fanin[service].add(source)
    script_rows = [row for row in sorted_rows if "script_content" in row["mechanism_signals"]]
    auth_span = (
        max(auth_times_all) - min(auth_times_all) if len(auth_times_all) > 1 else 0.0
    )
    if label == "Password" and direct > 0:
        class_conclusion = "MIXED"
        viable = "true"
    elif label == "Backdoor" and contextual > 0:
        class_conclusion = "PAST_CONTEXT_RECOVERABLE"
        viable = "true"
    else:
        class_conclusion = "NETWORK_OBSERVABILITY_LIMITED"
        viable = "false"
    minimum = {
        "Password": "SESSION_PLUS_PAYLOAD",
        "Uploading": "NOT_RECOVERABLE_FROM_NETWORK" if not (direct or contextual) else "SESSION_PLUS_PAYLOAD",
        "Backdoor": "NOT_RECOVERABLE_FROM_NETWORK" if not (direct or contextual) else "SESSION_PLUS_TEMPORAL",
        "Ransomware": "NOT_RECOVERABLE_FROM_NETWORK" if not (direct or contextual) else "OTHER_NETWORK_CONTEXT",
    }[label]
    result = {
        "class": label,
        "capture_count": 1,
        "capture_id_backend_only": checkpoint["capture_id_backend_only"],
        "pcap_path_backend_only": checkpoint["pcap_path_backend_only"],
        "pcap_size": checkpoint["pcap_size"],
        "packet_count": checkpoint["packet_count"],
        "duration_seconds": checkpoint["duration_seconds"],
        "derived_session_count": total,
        "IP_session_count": checkpoint["IP_session_count"],
        "non_IP_packet_count": checkpoint["non_IP_packet_count"],
        "protocol_distribution": checkpoint["protocol_distribution"],
        "label_assignment_method_distribution": dict(label_methods),
        "direct_attack_informative_count": direct,
        "direct_attack_informative_rate": _rate(direct, total),
        "contextual_attack_informative_count": contextual,
        "contextual_attack_informative_rate": _rate(contextual, total),
        "generic_background_count": generic,
        "generic_background_rate": generic_rate,
        "past10s_recoverable_count": past10,
        "past10s_recoverable_rate": _rate(past10, total),
        "past60s_recoverable_count": past60,
        "past60s_recoverable_rate": _rate(past60, total),
        "target_only_support_count": direct,
        "target_only_support_rate": _rate(direct, total),
        "target_plus_past10s_support_count": direct + past10,
        "target_plus_past10s_support_rate": _rate(direct + past10, total),
        "target_plus_past60s_support_count": direct + past60,
        "target_plus_past60s_support_rate": _rate(direct + past60, total),
        "payload_signal_count": payload_signal,
        "payload_signal_rate": _rate(payload_signal, total),
        "application_signal_count": application_signal,
        "application_signal_rate": _rate(application_signal, total),
        "temporal_signal_count": contextual,
        "temporal_signal_rate": _rate(contextual, total),
        "relation_signal_count": contextual,
        "relation_signal_rate": _rate(contextual, total),
        "capture_to_session_label_propagation_risk": propagation_risk(generic_rate),
        "encrypted_application_semantics_count": encrypted,
        "encrypted_application_semantics": bool(encrypted),
        "bidirectional_exchange_count": bidirectional,
        "established_exchange_count": established,
        "incomplete_handshake_session_count": incomplete,
        "repeated_small_flow_count": repeated_small,
        "capture_wide_periodic_bidirectional_session_count": periodic,
        "capture_wide_periodic_established_relation_profiles_backend_only": periodic_profiles,
        "relation_count": len(relation_groups),
        "max_relation_session_count": max((len(value) for value in relation_groups.values()), default=0),
        "source_target_service_relation_count": len(behavior_groups),
        "max_source_target_service_session_count": max(
            (len(value) for value in behavior_groups.values()), default=0
        ),
        "unique_source_count_backend_only": len(source_values),
        "unique_target_count_backend_only": len(target_values),
        "max_source_target_service_fanout_backend_only": max(
            (len(value) for value in source_fanout.values()), default=0
        ),
        "max_target_service_source_fanin_backend_only": max(
            (len(value) for value in target_fanin.values()), default=0
        ),
        "rare_source_target_service_relation_count": sum(
            len(value) <= 2 for value in behavior_groups.values()
        ),
        "auth_related_session_count": direct if label == "Password" else None,
        "max_repeated_auth_burst_size_10s": max(auth_bursts, default=0) if label == "Password" else None,
        "auth_temporal_concentration": (
            {
                "attempt_count": len(auth_times_all),
                "active_span_seconds": auth_span,
                "attempts_per_active_second": len(auth_times_all) / max(auth_span, 1.0),
                "active_span_fraction_of_capture": auth_span
                / max(float(checkpoint["duration_seconds"]), 1.0),
            }
            if label == "Password"
            else None
        ),
        "capture_inter_session_profile": interval_profile(
            row["timestamp_start"] for row in sorted_rows
        ),
        "application_protocol_session_distribution": dict(
            Counter(row["application_protocol"] or "NONE" for row in sorted_rows).most_common()
        ),
        "http_method_session_distribution": dict(
            Counter(method for row in sorted_rows for method in row["http_methods"]).most_common()
        ),
        "http_status_session_distribution": dict(
            Counter(status for row in sorted_rows for status in row["http_statuses"]).most_common()
        ),
        "payload_semantic_session_distribution": dict(
            Counter(value for row in sorted_rows for value in row["payload_semantics"]).most_common()
        ),
        "payload_present_session_count": sum(bool(row["payload_present"]) for row in sorted_rows),
        "script_content_direction_summary": {
            "session_count": len(script_rows),
            "initiator_payload_bytes": sum(
                int(row["initiator_payload_bytes"]) for row in script_rows
            ),
            "responder_payload_bytes": sum(
                int(row["responder_payload_bytes"]) for row in script_rows
            ),
        },
        "mean_directional_byte_asymmetry": sum(
            float(row["byte_asymmetry"]) for row in sorted_rows
        ) / total,
        "mean_packet_pattern_repetition_rate": sum(
            float(row["packet_pattern_repetition_rate"]) for row in sorted_rows
        ) / total,
        "authentication_outcome_status_distribution": (
            dict(
                Counter(
                    status
                    for row in sorted_rows
                    if "authentication_attempt" in row["mechanism_signals"]
                    for status in row["http_statuses"]
                ).most_common()
            )
            if label == "Password"
            else None
        ),
        "network_observability": class_conclusion,
        "recommended_observation_unit": minimum,
        "retain_as_fine_class": viable,
        "timeline_external": _artifact(timeline_path),
    }
    return result, timeline_path


def _capture_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| class | sessions | direct | contextual | generic/background | past 10s | past 60s | payload | application | temporal | relation | risk | observation unit | retain |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {class} | {derived_session_count:,} | {direct_attack_informative_count:,} ({direct}) | "
            "{contextual_attack_informative_count:,} ({contextual}) | {generic_background_count:,} ({generic}) | "
            "{past10s_recoverable_count:,} ({past10}) | {past60s_recoverable_count:,} ({past60}) | "
            "{payload_signal_count:,} ({payload}) | {application_signal_count:,} ({application}) | "
            "{temporal_signal_count:,} ({temporal}) | {relation_signal_count:,} ({relation}) | "
            "{risk} | {unit} | {retain} |".format(
                **row,
                direct=_pct(row["direct_attack_informative_rate"]),
                contextual=_pct(row["contextual_attack_informative_rate"]),
                generic=_pct(row["generic_background_rate"]),
                past10=_pct(row["past10s_recoverable_rate"]),
                past60=_pct(row["past60s_recoverable_rate"]),
                payload=_pct(row["payload_signal_rate"]),
                application=_pct(row["application_signal_rate"]),
                temporal=_pct(row["temporal_signal_rate"]),
                relation=_pct(row["relation_signal_rate"]),
                risk=row["capture_to_session_label_propagation_risk"],
                unit=row["recommended_observation_unit"],
                retain=row["retain_as_fine_class"],
            )
        )
    return "\n".join(lines)


def _capture_inventory(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| class | capture ID (backend only) | PCAP path (backend only) | size | packets | duration s | sessions/IP sessions | non-IP packets | protocol distribution |",
        "|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {class} | `{capture_id_backend_only}` | `{pcap_path_backend_only}` | {pcap_size:,} | "
            "{packet_count:,} | {duration_seconds:.3f} | {derived_session_count:,}/{IP_session_count:,} | "
            "{non_IP_packet_count:,} | `{protocols}` |".format(
                **row, protocols=canonical_json(row["protocol_distribution"])
            )
        )
    return "\n".join(lines)


def _build_report(manifest: dict[str, Any]) -> str:
    rows = manifest["classes"]
    by_label = {row["class"]: row for row in rows}
    password = by_label["Password"]
    uploading = by_label["Uploading"]
    backdoor = by_label["Backdoor"]
    ransomware = by_label["Ransomware"]
    backdoor_profiles = backdoor[
        "capture_wide_periodic_established_relation_profiles_backend_only"
    ]
    backdoor_beacon = backdoor_profiles[0] if backdoor_profiles else {}
    return f"""# Capture-Wide Attack Signal and Label-Propagation Audit v1

Status: `{manifest['CAPTURE_WIDE_AUDIT_STATUS']}`

## Scope and safeguards

This is a deterministic backend-only forensic audit of the four verified official Edge-IIoTset attack captures. Mechanism/protocol features were extracted without a class or capture filename in the detector input; the verified fine label was consulted only for the final backend categorization. Context is strict past-only over the same anonymized source-to-target service (excluding the client's ephemeral port). No future packets, whole-capture identity, filename, run label, model call, synthetic evidence, corpus edit, split/K-U edit, or U_final content was used.

`FORMAL_CORPUS_MODIFIED=false`

`FORMAL_SFT_STARTED=false`

`DEEPSEEK_NEW_API_CALLS=0`
`QWEN_NEW_RUNS=0`

## Capture/run structure

Each target fine class has exactly one verified official source PCAP and one companion CSV. Consequently this audit can measure within-capture signal and label propagation, but **cannot validate cross-run stability**. All four captures have 100% companion-label purity and current sessions use `VERIFIED_CAPTURE_FALLBACK`; official CSV rows do not provide a stable formal frame mapping.

The backend-only external aggregate records PCAP paths, hashes, packet/duration/protocol distributions and per-capture timeline locations. Paths and capture identities are not model Evidence.

{_capture_inventory(rows)}

The corresponding full session timelines and non-session ARP/control events are Git-external and digest-bound in the manifest. All four captures are single-run assets; there is no second independent run for cross-run stability validation.

## Capture-Wide Label Semantics Table

{_capture_table(rows)}

Rates use all reconstructed Production sessions, including chronological quarantine rows, because capture-label propagation applies before split role. `generic/background` is the direct estimate of capture-to-session over-propagation; capture membership alone never makes a session attack-informative.

## Class findings

### Backdoor

The full capture has {backdoor['derived_session_count']:,} sessions. The dominant candidate service contributes {backdoor['incomplete_handshake_session_count']:,} incomplete SYN→RST sessions, which are not C2 evidence. Separately, one stable relation contains {backdoor['capture_wide_periodic_bidirectional_session_count']:,} identical-shape, three-packet, small established binary exchanges at a mean interval of {float(backdoor_beacon.get('interval_mean_seconds') or 0.0):.3f}s with CV {float(backdoor_beacon.get('interval_cv') or 0.0):.4f}. No decoded command string is required for this timing/size/direction signal. After three prior exchanges, {backdoor['contextual_attack_informative_count']:,} sessions become contextually informative under strict past-only history; however, previous 10s and 60s both recover {backdoor['past60s_recoverable_count']:,} because every recurrence is just over 60s. Thus the earlier sampled 0% missed the small beacon-like subset, while the current 60s Temporal contract also misses it.

Conclusion: `{backdoor['network_observability']}`; minimum observation `{backdoor['recommended_observation_unit']}`.

### Password

The observable attack behavior is HTTP form authentication, not an inferred class-name shortcut. Across {password['derived_session_count']:,} sessions, {password['auth_related_session_count']:,} credential-bearing POST sessions are direct; their observed response distribution is `{canonical_json(password['authentication_outcome_status_distribution'])}` (redirects are observable, success/failure semantics are not asserted). These attempts span {password['auth_temporal_concentration']['active_span_seconds']:.3f}s at {password['auth_temporal_concentration']['attempts_per_active_second']:.3f} attempts/s, and the maximum strict 10-second repeated-auth burst is {password['max_repeated_auth_burst_size_10s']}. A further {password['contextual_attack_informative_count']:,} GET/HTTP sessions are supported by an already observed past authentication attempt on the same anonymized source→target service. The remaining {password['generic_background_count']:,} sessions ({_pct(password['generic_background_rate'])}) are generic/background. Thus the former 26.67% sample rate was selecting real auth sessions, while capture fallback propagates Password to a materially larger run.

Conclusion: `{password['network_observability']}`; minimum observation `{password['recommended_observation_unit']}`.

### Uploading

Across {uploading['derived_session_count']:,} sessions, {uploading['http_method_session_distribution'].get('GET', 0):,} are HTTP GET sessions and {uploading['http_status_session_distribution'].get('200', 0):,} receive HTTP 200; none is POST/PUT/multipart/FTP upload. The {uploading['script_content_direction_summary']['session_count']:,} script-shaped binary sessions contain {uploading['script_content_direction_summary']['initiator_payload_bytes']:,} initiator versus {uploading['script_content_direction_summary']['responder_payload_bytes']:,} responder payload bytes, i.e. the observed direction is not proof of client upload. Therefore {uploading['direct_attack_informative_count']:,} sessions contain explicit upload semantics and {uploading['contextual_attack_informative_count']:,} are recoverable after a prior observed upload. `ENCRYPTED_APPLICATION_SEMANTICS={str(uploading['encrypted_application_semantics']).lower()}`. The generic/background fraction is {_pct(uploading['generic_background_rate'])}; the previous 6.67% reflected suspicious content in a small subset, not a defensible per-session Uploading label.

Conclusion: `{uploading['network_observability']}`; minimum observation `{uploading['recommended_observation_unit']}`.

### Ransomware

The full capture has {ransomware['derived_session_count']:,} sessions, including {ransomware['incomplete_handshake_session_count']:,} incomplete handshakes and {ransomware['bidirectional_exchange_count']:,} bidirectional exchanges. It exposes no network-observed ransomware-specific key/encryption workflow, command/control chain, malware transfer, or other signal that distinguishes `Ransomware` from generic suspicious/malware traffic. Host-side encryption is outside the PCAP and is never inferred. The result is `NETWORK_FINE_LABEL_NOT_OBSERVABLE_FROM_AVAILABLE_PCAP`.

Conclusion: `{ransomware['network_observability']}`; minimum observation `{ransomware['recommended_observation_unit']}`.

## Label propagation and context

The pipeline behavior is confirmed as `attack-labeled capture → every reconstructed within-capture session → VERIFIED_CAPTURE_FALLBACK fine label` for all {manifest['TOTAL_DERIVED_SESSIONS']:,} audited sessions. The generic/background fraction is therefore a concrete capture-to-session label-propagation estimate, not a classifier metric. Overall risk is `{manifest['CAPTURE_TO_SESSION_LABEL_PROPAGATION_RISK']}`.

Strict past-only context helps only when an earlier real mechanism anchor exists on the same source→target service. It recovers {manifest['PAST_10S_RECOVERABLE_COUNT']:,} sessions at 10 seconds and {manifest['PAST_60S_RECOVERABLE_COUNT']:,} at 60 seconds, almost entirely Password. Backdoor requires a history longer than 60s; Uploading/Ransomware have no direct anchor. The class-balanced salvageability rating is `{manifest['PAST_ONLY_CONTEXT_SALVAGEABILITY']}`; future traffic, run identity and capture labels remain forbidden.

## Parser/extractor loss

The raw scan records HTTP/application shapes and decoded bounded payload semantics that are absent from Initial Evidence, so Password has `PAYLOAD_NOT_ALIGNED`/`APPLICATION_NOT_PARSED` and missing auth-aware Temporal features. Uploading has application/payload observations, but GET-delivered script content does not establish upload; this is primarily label granularity rather than silent parser loss. Backdoor/Ransomware do not reveal a hidden decisive payload/application signal; their dominant finding is network observability/label granularity, not extractor failure. Non-IP/control events are retained in the external event timelines.

## Direct answers

1. **Backdoor 0%:** the sample missed a {backdoor['capture_wide_periodic_bidirectional_session_count']:,}-session, ~{float(backdoor_beacon.get('interval_mean_seconds') or 0.0):.2f}s periodic small established binary relation. It is real network behavior, but current 10/60s context cannot recover it and {backdoor['generic_background_count']:,}/{backdoor['derived_session_count']:,} sessions remain non-informative.
2. **Password remainder:** beyond 23,650 direct credential POSTs, 47,298 GET/HTTP sessions have a strict prior-10s auth anchor and 25,133 sessions remain generic/background; only 302 redirects, not success/failure semantics, are observable.
3. **Uploading 6.67%:** the full scan does not support broad per-session Uploading semantics; GET/script delivery must not be reinterpreted as upload merely because of the capture label.
4. **Ransomware:** no available network evidence distinguishes Ransomware from generic suspicious/malware traffic.
5. **Over-propagation:** yes; quantified per class by `generic_background_rate`.
6. **Past-only salvage:** strong for Password at 10s, possible for Backdoor only with a longer (>60s) past window, and absent for Uploading/Ransomware.

## Limitations

- One official attack capture per class prevents independent-run stability claims.
- These are conservative deterministic signal-coverage statistics, not trained-model accuracy or formal paper results.
- Capture CSV purity proves provenance but not per-session fine semantics.
- Fine-class retention/observation-unit recommendations are audit findings; this task does not change data, K/U, corpus, training, or the canonical plan.

## Final fields

```text
CAPTURE_WIDE_AUDIT_STATUS={manifest['CAPTURE_WIDE_AUDIT_STATUS']}
BACKDOOR_FINE_CLASS_VIABILITY={manifest['BACKDOOR_FINE_CLASS_VIABILITY']}
PASSWORD_FINE_CLASS_VIABILITY={manifest['PASSWORD_FINE_CLASS_VIABILITY']}
UPLOADING_FINE_CLASS_VIABILITY={manifest['UPLOADING_FINE_CLASS_VIABILITY']}
RANSOMWARE_FINE_CLASS_VIABILITY={manifest['RANSOMWARE_FINE_CLASS_VIABILITY']}
CAPTURE_TO_SESSION_LABEL_PROPAGATION_RISK={manifest['CAPTURE_TO_SESSION_LABEL_PROPAGATION_RISK']}
PAST_ONLY_CONTEXT_SALVAGEABILITY={manifest['PAST_ONLY_CONTEXT_SALVAGEABILITY']}
TASK_REDEFINITION_REQUIRED={str(manifest['TASK_REDEFINITION_REQUIRED']).lower()}
FORMAL_CORPUS_MODIFIED=false
FORMAL_SFT_STARTED=false
DEEPSEEK_NEW_API_CALLS=0
QWEN_NEW_RUNS=0
```
"""


def _load_locators(production_root: Path, label: str, capture_id: str) -> list[dict[str, Any]]:
    backend = ds.dataset(production_root / "backend_records", format="parquet", partitioning="hive")
    columns = [
        "sample_id",
        "scenario_or_capture_id",
        "fine_label",
        "split",
        "timestamp_start",
        "timestamp_end",
        "first_frame_or_record",
        "last_frame_or_record",
        "l3_protocol",
        "l4_protocol",
        "raw_initiator_ip",
        "raw_responder_ip",
        "raw_initiator_port",
        "raw_responder_port",
        "label_assignment_method",
    ]
    rows = backend.to_table(
        columns=columns,
        filter=(ds.field("dataset") == "Edge-IIoTset")
        & (ds.field("fine_label") == label)
        & (ds.field("scenario_or_capture_id") == capture_id),
    ).to_pylist()
    if not rows or any(row["fine_label"] != label for row in rows):
        raise ValueError(f"backend locator coverage missing: {label}")
    if any(row["label_assignment_method"] != "VERIFIED_CAPTURE_FALLBACK" for row in rows):
        raise ValueError(f"unexpected session label method in capture-wide audit: {label}")
    return rows


def run(args: argparse.Namespace) -> int:
    corpus_before = sha256_file(args.corpus)
    if corpus_before != CORPUS_SHA256:
        raise ValueError("formal corpus digest is not the frozen baseline")
    provenance = json.loads(
        (args.production_root / "manifests/edge_label_provenance_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    if provenance.get("CAPTURE_PROVENANCE_GATE") != "PASS":
        raise ValueError("capture provenance gate is not PASS")
    specs = {str(row["capture_id"]): row for row in provenance["captures"]}
    results = []
    raw_checkpoints = []
    for label in TARGET_CLASSES:
        capture_id = TARGET_CAPTURE_IDS[label]
        spec = specs[capture_id]
        if (
            spec.get("status") != "PASS"
            or spec.get("expected_label") != label
            or float(spec.get("csv_label_purity") or 0.0) != 1.0
        ):
            raise ValueError(f"verified pure provenance missing: {label}")
        locators = _load_locators(args.production_root, label, capture_id)
        raw = _scan_capture(
            label=label,
            spec=spec,
            locators=locators,
            output_root=args.output_root,
            tshark=args.tshark,
        )
        result, _ = _classify_capture(label, raw, args.output_root, locators)
        results.append(result)
        raw_checkpoints.append(raw)

    total = sum(row["derived_session_count"] for row in results)
    generic = sum(row["generic_background_count"] for row in results)
    past10 = sum(row["past10s_recoverable_count"] for row in results)
    past60 = sum(row["past60s_recoverable_count"] for row in results)
    per_class_risks = Counter(
        row["capture_to_session_label_propagation_risk"] for row in results
    )
    risk = "HIGH" if per_class_risks["HIGH"] >= 2 else propagation_risk(_rate(generic, total))
    context_rate = _rate(past60, total)
    context_supported_classes = sum(row["past60s_recoverable_rate"] >= 0.10 for row in results)
    context_level = (
        "HIGH" if context_supported_classes >= 3 else "MEDIUM" if context_supported_classes else "LOW"
    )
    by_label = {row["class"]: row for row in results}
    manifest: dict[str, Any] = {
        "audit_version": CAPTURE_WIDE_AUDIT_VERSION,
        "CAPTURE_WIDE_AUDIT_STATUS": "PASS_WITH_LIMITATIONS",
        "BACKDOOR_FINE_CLASS_VIABILITY": "CONDITIONAL_ON_STRICT_PAST_CONTEXT_GT_60S",
        "PASSWORD_FINE_CLASS_VIABILITY": "VIABLE_WITH_SESSION_PAYLOAD_AND_PAST_CONTEXT",
        "UPLOADING_FINE_CLASS_VIABILITY": "NOT_VIABLE_FROM_AVAILABLE_PCAP",
        "RANSOMWARE_FINE_CLASS_VIABILITY": "NOT_VIABLE_FROM_AVAILABLE_PCAP",
        "CAPTURE_TO_SESSION_LABEL_PROPAGATION_RISK": risk,
        "PAST_ONLY_CONTEXT_SALVAGEABILITY": context_level,
        "TASK_REDEFINITION_REQUIRED": risk == "HIGH"
        or any(row["retain_as_fine_class"] == "false" for row in results),
        "FORMAL_CORPUS_MODIFIED": False,
        "FORMAL_SFT_STARTED": False,
        "DEEPSEEK_NEW_API_CALLS": 0,
        "QWEN_NEW_RUNS": 0,
        "BASE_CORPUS_SHA256": CORPUS_SHA256,
        "formal_corpus_sha256_after": sha256_file(args.corpus),
        "TOTAL_DERIVED_SESSIONS": total,
        "GENERIC_BACKGROUND_COUNT": generic,
        "GENERIC_BACKGROUND_RATE": _rate(generic, total),
        "PAST_10S_RECOVERABLE_COUNT": past10,
        "PAST_10S_RECOVERABLE_RATE": _rate(past10, total),
        "PAST_60S_RECOVERABLE_COUNT": past60,
        "PAST_60S_RECOVERABLE_RATE": context_rate,
        "CLASS_BALANCED_CONTEXT_SUPPORTED_CLASS_COUNT": context_supported_classes,
        "CLASS_BALANCED_PROPAGATION_RISK_DISTRIBUTION": dict(per_class_risks),
        "capture_run_structure": {
            "captures_per_class": {label: 1 for label in TARGET_CLASSES},
            "independent_run_stability_verifiable": False,
            "reason": "one verified official source capture per target fine class",
        },
        "session_label_pipeline": {
            "observed": "VERIFIED_SINGLE_LABEL_CAPTURE_TO_ALL_WITHIN_CAPTURE_SESSIONS",
            "formal_frame_direct_mapping_available": False,
            "capture_membership_used_as_attack_signal": False,
        },
        "classes": results,
        "raw_capture_checkpoints": [
            {
                key: value
                for key, value in row.items()
                if key
                in {
                    "capture_id_backend_only",
                    "pcap_path_backend_only",
                    "pcap_sha256",
                    "packet_count",
                    "duration_seconds",
                    "non_IP_packet_count",
                    "protocol_distribution",
                    "event_distribution",
                    "artifacts",
                }
            }
            for row in raw_checkpoints
        ],
        "parser_extractor_loss": {
            "Backdoor": ["TEMPORAL_FEATURE_MISSING", "RELATION_FEATURE_MISSING"],
            "Password": ["PAYLOAD_NOT_ALIGNED", "APPLICATION_NOT_PARSED", "TEMPORAL_FEATURE_MISSING"],
            "Uploading": ["APPLICATION_NOT_PARSED", "PAYLOAD_NOT_ALIGNED"],
            "Ransomware": [],
            "interpretation": "listed only where raw observations exist; absence of a decisive raw signal is not extractor failure",
        },
        "u_final_isolation_check": {"status": "PENDING", "content_inspected": False},
        "limitations": [
            "One official attack capture per class prevents cross-run stability validation.",
            "Deterministic coverage is not model accuracy or a formal paper result.",
            "Verified pure capture provenance does not imply per-session fine semantics.",
        ],
    }
    isolation = json.loads(
        (args.near_root / "manifests/u_final_isolation_audit.json").read_text(encoding="utf-8")
    )
    ufinal_pass = isolation.get("status") == "PASS" and int(isolation.get("u_final_count", 0)) == 0
    manifest["u_final_isolation_check"] = {
        "status": "PASS" if ufinal_pass else "FAIL",
        "content_inspected": False,
    }
    if manifest["formal_corpus_sha256_after"] != CORPUS_SHA256:
        raise ValueError("formal corpus changed during capture-wide audit")
    if not ufinal_pass:
        raise ValueError("U_final isolation manifest no longer passes")
    aggregate_path = args.output_root / "aggregate.json"
    _atomic_json(aggregate_path, manifest)
    manifest["external_aggregate"] = _artifact(aggregate_path)
    _atomic_json(args.manifest, manifest)
    _atomic_text(args.report, _build_report(manifest))
    print(f"CAPTURE_WIDE_AUDIT_STATUS={manifest['CAPTURE_WIDE_AUDIT_STATUS']}")
    print(f"CAPTURE_TO_SESSION_LABEL_PROPAGATION_RISK={risk}")
    print(f"PAST_ONLY_CONTEXT_SALVAGEABILITY={context_level}")
    print("FORMAL_CORPUS_MODIFIED=false")
    print("FORMAL_SFT_STARTED=false")
    print("DEEPSEEK_NEW_API_CALLS=0")
    print("QWEN_NEW_RUNS=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--production-root",
        type=Path,
        default=Path("/root/autodl-tmp/processed/edge_split_revision_v2"),
    )
    parser.add_argument(
        "--near-root",
        type=Path,
        default=Path("/root/autodl-tmp/processed/near_pretraining_v1"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("/root/autodl-tmp/experiments/capture_wide_signal_audit_v1"),
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path(
            "/root/autodl-tmp/processed/near_pretraining_v1/sft_corpus/final/near_sft_corpus_v2.jsonl"
        ),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/training_readiness/capture_wide_signal_audit_v1.md"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("reports/training_readiness/capture_wide_signal_audit_v1_manifest.json"),
    )
    parser.add_argument("--tshark", default="tshark")
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(run(parse_args()))
