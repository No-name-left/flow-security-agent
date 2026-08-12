#!/usr/bin/env python3
"""Offline class-conditional RAW -> session -> Evidence salvageability audit.

The command reads the frozen 330-sample blind-classification cache and existing
Production/Near assets. It never imports a model transport and has no API path.
Detailed per-sample artifacts are written outside Git; only aggregate report and
manifest outputs are allowed inside the repository.
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
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

import pyarrow.dataset as ds

from flowsec.production.core import canonical_endpoint_identity, first_value, safe_int
from flowsec.training.contracts import content_digest
from flowsec.training.evidence import decode_hex_payload, normalize_uri_shape, sanitize_payload_text
from flowsec.training.evidence_salvage import (
    EVIDENCE_SALVAGE_AUDIT_VERSION,
    EVIDENCE_SALVAGE_SEED,
    application_semantics,
    choose_failure_mode,
    class_relevant_signal,
    packet_bucket,
    payload_semantics,
    relation_semantics,
    temporal_semantics,
    validate_assessment,
)


CORPUS_SHA256 = "5b845cf9e5886e5e44fd46562135ba3eb5907de65fd8faf5d9b8777253149123"
PRIMARY_MANIFEST_DIGEST = "93b30ccd9075fef4925da45e3a8a287c200cfec4d54c05e2611be91d9173ca88"
PAIR_MANIFEST_DIGEST = "f8c08f55bf744b4f03b9dca5ad7017b54f22f429454ed7a88877d504a9d7df96"
NEAR_CLASSES = (
    "Backdoor",
    "DDoS_HTTP",
    "DDoS_TCP",
    "MITM",
    "Normal",
    "Password",
    "Port_Scanning",
    "Ransomware",
    "SQL_injection",
    "Uploading",
    "Vulnerability_scanner",
)
PROHIBITED_CLASSES = frozenset({"DDoS_UDP", "XSS"})
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
    "http.request.method",
    "http.request.uri",
    "http.response.code",
    "http.content_type",
    "http.content_length",
    "dns.qry.name",
    "dns.a",
    "dns.flags.rcode",
    "tls.handshake.type",
    "tls.handshake.extensions_server_name",
    "modbus.func_code",
    "tcp.payload",
    "udp.payload",
    "data.data",
)


RECOMMENDATIONS = {
    "Backdoor": (
        "summary plus bounded payload when present",
        "service-normalized temporal pattern / application decoder",
        "HIGH",
        "HIGH",
    ),
    "DDoS_HTTP": (
        "first-8 metadata plus cheap HTTP metadata",
        "HTTP-aware 60s temporal",
        "LOW",
        "LOW",
    ),
    "DDoS_TCP": (
        "first-8 metadata plus summary",
        "SYN/handshake/rate temporal",
        "LOW",
        "LOW",
    ),
    "MITM": (
        "first-8 metadata plus summary",
        "ARP/DNS relation-path evidence",
        "MEDIUM",
        "HIGH",
    ),
    "Normal": (
        "first-8 metadata plus bounded payload/application metadata",
        "terminal or temporal consistency",
        "LOW",
        "LOW",
    ),
    "Password": (
        "first-8 bounded payload plus cheap HTTP metadata",
        "payload expansion then repeated-auth temporal",
        "LOW",
        "LOW",
    ),
    "Port_Scanning": (
        "first-8 metadata plus summary",
        "port-diversity/probe-rate temporal",
        "MEDIUM",
        "LOW",
    ),
    "Ransomware": (
        "first-8 metadata plus bounded payload when present",
        "application/payload then terminal if absent",
        "HIGH",
        "HIGH",
    ),
    "SQL_injection": (
        "first-8 bounded payload plus cheap HTTP metadata",
        "payload expansion/application",
        "LOW",
        "LOW",
    ),
    "Uploading": (
        "first-8 bounded payload plus cheap HTTP metadata",
        "payload expansion/application",
        "MEDIUM",
        "MEDIUM",
    ),
    "Vulnerability_scanner": (
        "first-8 bounded payload plus cheap HTTP metadata",
        "application then probe-rate temporal",
        "LOW",
        "LOW",
    ),
}


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(value)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _rate(count: int, total: int) -> float:
    return count / total if total else 0.0


def _pct(value: float) -> str:
    return f"{100.0 * value:.2f}%"


def _manifest_digest(value: dict[str, Any], expected: str, name: str) -> None:
    recorded = value.get("manifest_digest")
    unsigned = dict(value)
    unsigned.pop("manifest_digest", None)
    if recorded != expected or content_digest(unsigned) != recorded:
        raise ValueError(f"fixed {name} manifest changed")


def _parquet_rows(root: Path, sample_ids: list[str]) -> list[dict[str, Any]]:
    dataset = ds.dataset(root, format="parquet", partitioning="hive")
    return dataset.to_table(filter=ds.field("sample_id").isin(sample_ids)).to_pylist()


def _snapshot_index(path: Path, state_ids: set[str]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            state_id = str(row["evidence_state_id"])
            if state_id in state_ids:
                result[state_id] = row
    if set(result) != state_ids:
        raise ValueError(f"snapshot join incomplete: {len(result)}/{len(state_ids)}")
    return result


def _visible_types(snapshot: dict[str, Any]) -> set[str]:
    types: set[str] = set()
    for evidence in snapshot.get("evidence") or ():
        kind = str(evidence.get("evidence_type", "")).casefold()
        content = evidence.get("content") or {}
        content_kind = str(content.get("evidence_type", "")).casefold()
        combined = kind + " " + content_kind
        if "payload" in combined:
            types.add("payload")
        if "application" in combined:
            types.add("application")
        if "temporal" in combined:
            types.add("temporal")
        if "relation" in combined or "graph" in combined:
            types.add("relation")
        if "packet" in combined:
            types.add("packet")
        if "knowledge" in combined:
            types.add("knowledge")
        if "initial" in combined:
            types.add("initial")
    return types


def _snapshot_observations(snapshot: dict[str, Any]) -> dict[str, Any]:
    payload_fragments: list[str] = []
    application: dict[str, Any] | None = None
    temporal: dict[str, Any] | None = None
    relation: dict[str, Any] | None = None
    initial: dict[str, Any] | None = None
    for evidence in snapshot.get("evidence") or ():
        kind = str(evidence.get("evidence_type", "")).casefold()
        content = evidence.get("content") or {}
        content_kind = str(content.get("evidence_type", "")).casefold()
        combined = kind + " " + content_kind
        if "payload" in combined:
            payload_fragments.extend(content.get("fragments") or ())
        elif "application" in combined:
            application = content
        elif "temporal" in combined:
            temporal = content
        elif "relation" in combined or "graph" in combined:
            relation = content
        elif "initial" in combined:
            initial = content
    return {
        "payload_fragments": payload_fragments,
        "application": application,
        "temporal": temporal,
        "relation": relation,
        "initial": initial,
    }


def _first(values: str) -> str:
    return first_value(values or "")


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


def _locator_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return canonical_endpoint_identity(
        str(row["l3_protocol"]),
        str(row["l4_protocol"]),
        str(row["raw_initiator_ip"]),
        int(row["raw_initiator_port"]),
        str(row["raw_responder_ip"]),
        int(row["raw_responder_port"]),
    )


def _new_raw_sample(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_id": row["sample_id"],
        "fine_label_backend_only": row["fine_label"],
        "capture_id_backend_only": row["scenario_or_capture_id"],
        "first_frame": int(row["first_frame_or_record"]),
        "last_frame": int(row["last_frame_or_record"]),
        "matched_packet_count": 0,
        "payload_frame_count": 0,
        "payload_bytes": 0,
        "payload_frames_by_bucket": Counter(),
        "decoded_fragments_by_bucket": defaultdict(list),
        "payload_semantics_by_bucket": defaultdict(set),
        "http_methods": Counter(),
        "http_statuses": Counter(),
        "content_types": Counter(),
        "protocols": Counter(),
        "tcp_syn": 0,
        "tcp_synack": 0,
        "tcp_rst": 0,
        "tcp_fin": 0,
        "initiator_bytes": 0,
        "responder_bytes": 0,
        "past_60s": {},
        "past_arp_conflict": False,
        "past_dns_conflict": False,
    }


def _json_safe_raw_sample(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    for key in (
        "payload_frames_by_bucket",
        "http_methods",
        "http_statuses",
        "content_types",
        "protocols",
    ):
        result[key] = dict(sorted(result[key].items()))
    result["decoded_fragments_by_bucket"] = {
        key: value[:5] for key, value in sorted(result["decoded_fragments_by_bucket"].items())
    }
    result["payload_semantics_by_bucket"] = {
        key: sorted(value) for key, value in sorted(result["payload_semantics_by_bucket"].items())
    }
    return result


def _tshark_command(tshark: str, pcap: Path, last_frame: int) -> list[str]:
    command = [
        tshark,
        "-n",
        "-r",
        str(pcap),
        "-c",
        str(last_frame),
        "-T",
        "fields",
        "-E",
        "separator=/t",
        "-E",
        "occurrence=f",
    ]
    for field in RAW_FIELDS:
        command.extend(["-e", field])
    return command


def _capture_raw_audit(
    *,
    capture_id: str,
    pcap: Path,
    expected_sha256: str,
    locators: list[dict[str, Any]],
    tshark: str,
) -> dict[str, Any]:
    observed_sha256 = _sha256(pcap)
    if observed_sha256 != expected_sha256:
        raise ValueError(f"raw PCAP identity mismatch: {capture_id}")
    by_key: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    samples: dict[str, dict[str, Any]] = {}
    for locator in locators:
        by_key[_locator_key(locator)].append(locator)
        samples[str(locator["sample_id"])] = _new_raw_sample(locator)
    for values in by_key.values():
        values.sort(key=lambda row: int(row["first_frame_or_record"]))

    window: deque[tuple[float, str, str, int, int, int, str, str]] = deque()
    destination_packets: Counter[str] = Counter()
    destination_sources: Counter[tuple[str, str]] = Counter()
    destination_distinct_sources: Counter[str] = Counter()
    destination_ports: Counter[tuple[str, int]] = Counter()
    destination_distinct_ports: Counter[str] = Counter()
    destination_syn: Counter[str] = Counter()
    destination_http: Counter[str] = Counter()
    destination_http_methods: Counter[tuple[str, str]] = Counter()
    destination_distinct_http_methods: Counter[str] = Counter()
    destination_uri_shapes: Counter[tuple[str, str]] = Counter()
    destination_distinct_uri_shapes: Counter[str] = Counter()
    arp_mapping: dict[str, set[str]] = defaultdict(set)
    arp_mac_claims: dict[str, set[str]] = defaultdict(set)
    dns_mapping: dict[str, set[str]] = defaultdict(set)
    arp_conflict = dns_conflict = False
    total_rows = ip_rows = arp_rows = 0

    def evict(now: float) -> None:
        while window and now - window[0][0] > 60.0:
            _, old_src, old_dst, old_port, old_syn, old_http, old_method, old_uri = window.popleft()
            destination_packets[old_dst] -= 1
            source_key = (old_dst, old_src)
            destination_sources[source_key] -= 1
            if destination_sources[source_key] == 0:
                del destination_sources[source_key]
                destination_distinct_sources[old_dst] -= 1
            port_key = (old_dst, old_port)
            destination_ports[port_key] -= 1
            if destination_ports[port_key] == 0:
                del destination_ports[port_key]
                destination_distinct_ports[old_dst] -= 1
            destination_syn[old_dst] -= old_syn
            destination_http[old_dst] -= old_http
            if old_method:
                method_key = (old_dst, old_method)
                destination_http_methods[method_key] -= 1
                if destination_http_methods[method_key] == 0:
                    del destination_http_methods[method_key]
                    destination_distinct_http_methods[old_dst] -= 1
            if old_uri:
                uri_key = (old_dst, old_uri)
                destination_uri_shapes[uri_key] -= 1
                if destination_uri_shapes[uri_key] == 0:
                    del destination_uri_shapes[uri_key]
                    destination_distinct_uri_shapes[old_dst] -= 1

    command = _tshark_command(tshark, pcap, max(int(row["last_frame_or_record"]) for row in locators))
    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stderr_handle:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=stderr_handle,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1024 * 1024,
        )
        assert process.stdout is not None
        csv.field_size_limit(sys.maxsize)
        reader = csv.reader(process.stdout, delimiter="\t", quotechar='"')
        for parts in reader:
            total_rows += 1
            if len(parts) < len(RAW_FIELDS):
                parts.extend([""] * (len(RAW_FIELDS) - len(parts)))
            raw = dict(zip(RAW_FIELDS, parts, strict=True))
            frame = safe_int(_first(raw["frame.number"]), -1)
            timestamp = _float(raw["frame.time_epoch"], -1.0)
            arp_ip = _first(raw["arp.src.proto_ipv4"])
            arp_mac = _first(raw["eth.src"])
            if arp_ip and arp_mac:
                arp_rows += 1
                arp_mapping[arp_ip].add(arp_mac)
                arp_conflict = arp_conflict or len(arp_mapping[arp_ip]) > 1
                if _first(raw["arp.opcode"]) == "2" and arp_ip != "0.0.0.0":
                    arp_mac_claims[arp_mac].add(arp_ip)
                    arp_conflict = arp_conflict or len(arp_mac_claims[arp_mac]) > 1
            dns_name, dns_answer = _first(raw["dns.qry.name"]), _first(raw["dns.a"])
            if dns_name and dns_answer:
                dns_mapping[dns_name.casefold()].add(dns_answer)
                dns_conflict = dns_conflict or len(dns_mapping[dns_name.casefold()]) > 1
            identity = _packet_identity(raw)
            if identity is None or frame < 0 or timestamp < 0:
                continue
            ip_rows += 1
            src = _first(raw["ip.src"]) or _first(raw["ipv6.src"])
            dst = _first(raw["ip.dst"]) or _first(raw["ipv6.dst"])
            dport = safe_int(_first(raw["tcp.dstport"]) or _first(raw["udp.dstport"]))
            flags = _flags(raw["tcp.flags"])
            is_syn = int(bool(flags & 0x02 and not flags & 0x10))
            http_method = _first(raw["http.request.method"]).upper()
            raw_uri = _first(raw["http.request.uri"])
            uri_shape = normalize_uri_shape(raw_uri) if raw_uri else ""
            is_http = int(bool(http_method))
            evict(timestamp)

            for locator in by_key.get(identity, ()):  # one packet can match only one interval
                if not int(locator["first_frame_or_record"]) <= frame <= int(locator["last_frame_or_record"]):
                    continue
                sample = samples[str(locator["sample_id"])]
                if sample["matched_packet_count"] == 0:
                    target = str(locator["raw_responder_ip"])
                    sample["past_60s"] = {
                        "packet_count": len(window),
                        "target_packet_count": destination_packets[target],
                        "target_concentration": _rate(destination_packets[target], len(window)),
                        "target_distinct_sources": destination_distinct_sources[target],
                        "target_distinct_ports": destination_distinct_ports[target],
                        "target_syn_count": destination_syn[target],
                        "target_http_request_count": destination_http[target],
                        "target_distinct_http_methods": destination_distinct_http_methods[target],
                        "target_distinct_uri_shapes": destination_distinct_uri_shapes[target],
                    }
                    sample["past_arp_conflict"] = arp_conflict
                    sample["past_dns_conflict"] = dns_conflict
                sample["matched_packet_count"] += 1
                ordinal = int(sample["matched_packet_count"])
                bucket = packet_bucket(ordinal)
                protocols = _first(raw["frame.protocols"])
                for protocol in protocols.split(":"):
                    if protocol:
                        sample["protocols"][protocol] += 1
                method = _first(raw["http.request.method"]).upper()
                status = _first(raw["http.response.code"])
                content_type = _first(raw["http.content_type"]).casefold()
                if method:
                    sample["http_methods"][method] += 1
                if status:
                    sample["http_statuses"][status] += 1
                if content_type:
                    sample["content_types"][content_type] += 1
                sample["tcp_syn"] += is_syn
                sample["tcp_synack"] += int(bool(flags & 0x02 and flags & 0x10))
                sample["tcp_rst"] += int(bool(flags & 0x04))
                sample["tcp_fin"] += int(bool(flags & 0x01))
                frame_length = safe_int(_first(raw["frame.len"]))
                initiator = (
                    src == str(locator["raw_initiator_ip"])
                    and safe_int(_first(raw["tcp.srcport"]) or _first(raw["udp.srcport"]))
                    == int(locator["raw_initiator_port"])
                )
                sample["initiator_bytes" if initiator else "responder_bytes"] += frame_length
                payload_hex = _first(raw["tcp.payload"]) or _first(raw["udp.payload"]) or _first(raw["data.data"])
                compact = "".join(character for character in payload_hex if character in "0123456789abcdefABCDEF")
                if compact and len(compact) % 2 == 0:
                    sample["payload_frame_count"] += 1
                    sample["payload_bytes"] += len(compact) // 2
                    sample["payload_frames_by_bucket"][bucket] += 1
                    decoded = decode_hex_payload(compact)
                    sanitized = sanitize_payload_text(decoded, max_chars=768) if decoded else None
                    if sanitized:
                        if len(sample["decoded_fragments_by_bucket"][bucket]) < 5:
                            sample["decoded_fragments_by_bucket"][bucket].append(sanitized)
                        sample["payload_semantics_by_bucket"][bucket].update(
                            payload_semantics((sanitized,))
                        )
                break

            window.append((timestamp, src, dst, dport, is_syn, is_http, http_method, uri_shape))
            destination_packets[dst] += 1
            source_key = (dst, src)
            if destination_sources[source_key] == 0:
                destination_distinct_sources[dst] += 1
            destination_sources[source_key] += 1
            port_key = (dst, dport)
            if destination_ports[port_key] == 0:
                destination_distinct_ports[dst] += 1
            destination_ports[port_key] += 1
            destination_syn[dst] += is_syn
            destination_http[dst] += is_http
            if http_method:
                method_key = (dst, http_method)
                if destination_http_methods[method_key] == 0:
                    destination_distinct_http_methods[dst] += 1
                destination_http_methods[method_key] += 1
            if uri_shape:
                uri_key = (dst, uri_shape)
                if destination_uri_shapes[uri_key] == 0:
                    destination_distinct_uri_shapes[dst] += 1
                destination_uri_shapes[uri_key] += 1
        process.stdout.close()
        returncode = process.wait()
        stderr_handle.seek(0)
        stderr = stderr_handle.read()[-8000:].strip()
    if returncode != 0:
        raise RuntimeError(f"tshark failed for {capture_id}: {stderr}")

    missing = sorted(
        sample_id for sample_id, row in samples.items() if row["matched_packet_count"] == 0
    )
    if missing:
        raise ValueError(f"raw session match incomplete for {capture_id}: {len(missing)}")
    return {
        "audit_version": EVIDENCE_SALVAGE_AUDIT_VERSION,
        "capture_id_backend_only": capture_id,
        "pcap_path_backend_only": str(pcap),
        "pcap_sha256": observed_sha256,
        "selected_sample_count": len(samples),
        "tshark_rows_read": total_rows,
        "ip_rows_read": ip_rows,
        "arp_rows_read": arp_rows,
        "capture_arp_mapping_conflict": arp_conflict,
        "capture_dns_mapping_conflict": dns_conflict,
        "raw_scanner_version": "RAW_CLASS_CONDITIONAL_SCANNER_V3",
        "tshark_fields": list(RAW_FIELDS),
        "samples": [_json_safe_raw_sample(samples[key]) for key in sorted(samples)],
    }


def _classification_metric(rows: list[dict[str, Any]]) -> dict[str, Any]:
    passed = [row for row in rows if row.get("status") == "PASS"]
    return {
        "n": len(passed),
        "top1_correct": sum(bool(row["top1_correct"]) for row in passed),
        "top1_rate": _rate(sum(bool(row["top1_correct"]) for row in passed), len(passed)),
        "top2_contains_gt": sum(bool(row["top2_contains_gt"]) for row in passed),
        "top2_rate": _rate(sum(bool(row["top2_contains_gt"]) for row in passed), len(passed)),
    }


def _cross_table(
    *,
    samples: list[dict[str, Any]],
    deepseek: list[dict[str, Any]],
    qwen: list[dict[str, Any]],
    availability: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    deepseek_by_id = {row["evidence_state_id"]: row for row in deepseek}
    qwen_by_id = {row["evidence_state_id"]: row for row in qwen}
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for sample in samples:
        grouped[(sample["fine_label_backend_only"], sample["stage_type"])].append(sample)
    result = []
    for (label, stage), members in sorted(grouped.items()):
        state_ids = [str(row["evidence_state_id"]) for row in members]
        teacher_count = sum(bool(row["teacher_sufficient_backend_only"]) for row in members)
        result.append(
            {
                "class": label,
                "stage": stage,
                "n": len(members),
                "payload_available": sum(
                    bool(availability[row["sample_id"]]["payload_capability_available"])
                    for row in members
                ),
                "payload_visible": sum(
                    bool(availability[row["sample_id"]]["payload_visible_current"])
                    for row in members
                ),
                "teacher_sufficient": teacher_count,
                "teacher_sufficient_rate": _rate(teacher_count, len(members)),
                "deepseek": _classification_metric([deepseek_by_id[state_id] for state_id in state_ids]),
                "qwen": _classification_metric([qwen_by_id[state_id] for state_id in state_ids]),
            }
        )
    return result


def _class_availability(
    samples: list[dict[str, Any]], availability: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    result = []
    for label in NEAR_CLASSES:
        members = [row for row in samples if row["fine_label_backend_only"] == label]
        fields = (
            "payload_raw_present",
            "payload_capability_available",
            "payload_visible_current",
            "application_available",
            "application_visible_current",
            "temporal_available",
            "temporal_visible_current",
            "relation_available",
            "relation_visible_current",
        )
        row: dict[str, Any] = {"class": label, "sample_n": len(members)}
        for field in fields:
            count = sum(bool(availability[item["sample_id"]][field]) for item in members)
            row[field + "_n"] = count
            row[field + "_rate"] = _rate(count, len(members))
        result.append(row)
    return result


def _current_support(*, label: str, snapshot: dict[str, Any], initial: dict[str, Any]) -> bool:
    visible = _snapshot_observations(snapshot)
    summary = initial["session_summary"]
    session = set()
    if summary.get("handshake_state") in {"ESTABLISHED_OPEN", "ESTABLISHED_CLOSED"}:
        session.add("established_exchange")
    app_features = application_semantics(visible["application"])
    if "http" in app_features:
        session.add("http_activity")
    temporal_features = temporal_semantics(
        visible["temporal"] or {},
        handshake_state=str(summary.get("handshake_state", "")),
    )
    relation_features = set()
    if (visible["relation"] or {}).get("repeated_relation"):
        relation_features.add("repeated_exact_relation")
    return class_relevant_signal(
        label,
        payload=payload_semantics(visible["payload_fragments"]),
        application=app_features,
        temporal=temporal_features,
        relation=relation_features,
        session=session,
    )


def _assess_sample(
    *,
    sample: dict[str, Any],
    initial: dict[str, Any],
    temporal: dict[str, Any],
    relation: dict[str, Any],
    application: dict[str, Any] | None,
    availability: dict[str, Any],
    snapshot: dict[str, Any],
    raw: dict[str, Any],
    capture_summary: dict[str, Any],
) -> dict[str, Any]:
    label = str(sample["fine_label_backend_only"])
    summary = initial["session_summary"]
    handshake = str(summary.get("handshake_state", ""))
    application_features = application_semantics(application)
    current_temporal = temporal_semantics(temporal, handshake_state=handshake)
    current_relation = relation_semantics(relation)
    bucket_features = {
        name: set(raw.get("payload_semantics_by_bucket", {}).get(name, ()))
        for name in ("first_8", "packet_9_16", "after_16")
    }
    all_raw_payload_features = set().union(*bucket_features.values())
    session_features: set[str] = set()
    protocol_names = {str(name).casefold() for name in raw.get("protocols", {})}
    if raw.get("http_methods") or "http" in protocol_names:
        session_features.add("http_activity")
    if "mqtt" in protocol_names:
        session_features.add("mqtt_activity")
    if handshake in {"ESTABLISHED_OPEN", "ESTABLISHED_CLOSED"}:
        session_features.add("established_exchange")
    if raw["matched_packet_count"] and raw["tcp_syn"] / raw["matched_packet_count"] >= 0.5:
        session_features.add("high_syn_ratio")
    if raw["initiator_bytes"] and raw["responder_bytes"]:
        session_features.add("bidirectional_exchange")
    if raw["payload_bytes"] >= 1024 and raw["initiator_bytes"] > 1.5 * max(1, raw["responder_bytes"]):
        session_features.add("large_client_body")

    improved_temporal = set(current_temporal)
    past = raw.get("past_60s") or {}
    if int(past.get("target_distinct_ports") or 0) >= 5:
        improved_temporal.add("port_diversity")
    if int(past.get("target_syn_count") or 0) >= 20:
        improved_temporal.update({"session_burst", "incomplete_handshake_burst"})
    if float(past.get("target_concentration") or 0.0) >= 0.75:
        improved_temporal.add("target_concentration")
    if int(past.get("target_syn_count") or 0) >= 1000:
        improved_temporal.add("extreme_connection_rate_proxy")
    if int(past.get("target_distinct_ports") or 0) >= 5 and int(past.get("target_syn_count") or 0) >= 5:
        improved_temporal.add("probe_burst")
    if int(past.get("target_http_request_count") or 0) >= 20:
        improved_temporal.update({"session_burst", "target_concentration"})
    if (
        int(past.get("target_http_request_count") or 0) >= 20
        and (
            int(past.get("target_distinct_uri_shapes") or 0) >= 5
            or int(past.get("target_distinct_http_methods") or 0) >= 3
        )
    ):
        improved_temporal.add("probe_burst")
    if (
        int(temporal.get("prior_session_count") or 0) >= 5
        and int(temporal.get("same_destination_distinct_source_count") or 0) >= 5
        and "bidirectional_exchange" in session_features
        and int(raw["matched_packet_count"]) >= 6
        and int(raw["payload_frame_count"]) > 0
    ):
        improved_temporal.add("periodic_service_pattern")

    improved_relation = relation_semantics(
        relation,
        raw_arp_conflict=bool(raw.get("past_arp_conflict")),
        raw_dns_conflict=bool(raw.get("past_dns_conflict")),
    )
    capture_mechanism = (
        label == "MITM"
        and bool(
            capture_summary.get("capture_arp_mapping_conflict")
            or capture_summary.get("capture_dns_mapping_conflict")
        )
    )
    payload_class_relevant = class_relevant_signal(label, payload=all_raw_payload_features)
    application_relevant = class_relevant_signal(label, application=application_features)
    current_temporal_relevant = class_relevant_signal(label, temporal=current_temporal, session=session_features)
    improved_temporal_relevant = class_relevant_signal(label, temporal=improved_temporal, session=session_features)
    current_relation_relevant = class_relevant_signal(label, relation=current_relation)
    improved_relation_relevant = class_relevant_signal(label, relation=improved_relation)
    session_direct_relevant = class_relevant_signal(
        label,
        payload=all_raw_payload_features,
        application=application_features,
        session=session_features,
    )
    partial_session_signal = session_direct_relevant
    if label == "DDoS_HTTP":
        partial_session_signal = "http_activity" in session_features
    elif label in {"DDoS_TCP", "Port_Scanning"}:
        partial_session_signal = "high_syn_ratio" in session_features or handshake == "INCOMPLETE_HANDSHAKE"
    elif label == "Normal":
        partial_session_signal = {"mqtt_activity", "established_exchange"} <= session_features or payload_class_relevant

    current_support = _current_support(label=label, snapshot=snapshot, initial=initial)
    e0 = class_relevant_signal(label, session=session_features)
    first8_support = class_relevant_signal(label, payload=bucket_features["first_8"])
    packet9_support = class_relevant_signal(label, payload=bucket_features["packet_9_16"])
    after16_support = class_relevant_signal(label, payload=bucket_features["after_16"])
    basic_app_support = class_relevant_signal(
        label,
        application=application_features,
        session=session_features,
    )
    e1 = e0 or first8_support or basic_app_support
    e2 = e1 or packet9_support
    e3 = e2 or application_relevant
    e4 = e3 or improved_temporal_relevant
    e5 = e4 or improved_relation_relevant
    full_support = e5 or after16_support or session_direct_relevant
    raw_signal_present = bool(
        full_support
        or partial_session_signal
        or improved_temporal_relevant
        or improved_relation_relevant
        or capture_mechanism
    )
    temporal_gap = improved_temporal_relevant and (
        not current_temporal_relevant
        or (not current_support and label in {"Backdoor", "DDoS_HTTP", "DDoS_TCP", "Port_Scanning", "Vulnerability_scanner"})
    )
    relation_gap = improved_relation_relevant and not current_relation_relevant
    failure_mode = choose_failure_mode(
        current_support=current_support,
        full_support=full_support,
        raw_signal_present=raw_signal_present,
        session_retains_signal=partial_session_signal,
        payload_capability_available=bool(
            payload_class_relevant and availability["payload_capability_available"]
        ),
        payload_visible_current=bool(availability["payload_visible_current"]),
        application_available=bool(application_relevant and availability["application_available"]),
        application_visible_current=bool(availability["application_visible_current"]),
        temporal_gap=temporal_gap,
        relation_gap=relation_gap,
    )
    if failure_mode == "AMBIGUOUS" and payload_class_relevant and not availability["payload_capability_available"]:
        failure_mode = "PAYLOAD_MATERIALIZATION_LOSS"
    if failure_mode == "AMBIGUOUS" and application_relevant and not availability["application_available"]:
        failure_mode = "APPLICATION_EXTRACTION_LOSS"
    if failure_mode == "AMBIGUOUS" and label == "Normal" and basic_app_support:
        failure_mode = "APPLICATION_EXTRACTION_LOSS"
    rag_useful = bool(
        full_support
        and label in {"Backdoor", "DDoS_HTTP", "DDoS_TCP", "MITM", "Port_Scanning", "Vulnerability_scanner"}
    )
    return {
        "sample_id": sample["sample_id"],
        "evidence_state_id": sample["evidence_state_id"],
        "fine_label_backend_only": label,
        "stage_type": sample["stage_type"],
        "raw_signal_present": raw_signal_present,
        "session_retains_signal": partial_session_signal,
        "raw_payload_present": bool(raw["payload_frame_count"]),
        "payload_capability_available": bool(availability["payload_capability_available"]),
        "payload_visible_current": bool(availability["payload_visible_current"]),
        "payload_class_relevant_signal": payload_class_relevant,
        "application_available": bool(availability["application_available"]),
        "application_visible_current": bool(availability["application_visible_current"]),
        "application_class_relevant_signal": application_relevant,
        "temporal_class_relevant_signal": current_temporal_relevant,
        "relation_class_relevant_signal": current_relation_relevant,
        "signal_first_8": first8_support,
        "signal_packet_9_16": packet9_support,
        "signal_after_16": after16_support,
        "current_evidence_supports_label": current_support,
        "full_observational_evidence_supports_label": full_support,
        "failure_mode": failure_mode,
        "evidence_ladder": {
            "E0_CURRENT_INITIAL": e0,
            "E1_BASIC_V2": e1,
            "E2_PACKET_PAYLOAD_EXPANSION": e2,
            "E3_APPLICATION": e3,
            "E4_TEMPORAL": e4,
            "E5_RELATION": e5,
            "FULL_OBSERVATIONAL": full_support,
        },
        "rag_potentially_useful": rag_useful,
        "observational_features": {
            "raw_payload_by_bucket": {key: sorted(value) for key, value in sorted(bucket_features.items())},
            "application": sorted(application_features),
            "current_temporal": sorted(current_temporal),
            "improved_temporal": sorted(improved_temporal),
            "current_relation": sorted(current_relation),
            "improved_relation": sorted(improved_relation),
            "session": sorted(session_features),
            "capture_mitm_mechanism": capture_mechanism,
        },
        "raw_locator_audit": {
            "matched_packet_count": raw["matched_packet_count"],
            "payload_frame_count": raw["payload_frame_count"],
            "payload_bytes": raw["payload_bytes"],
            "past_60s": raw.get("past_60s") or {},
        },
    }


def _dominant(counter: Counter[str]) -> str:
    if not counter:
        return "AMBIGUOUS"
    maximum = max(counter.values())
    return sorted(key for key, value in counter.items() if value == maximum)[0]


def _aggregate_classes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for label in NEAR_CLASSES:
        members = [row for row in rows if row["fine_label_backend_only"] == label]
        n = len(members)

        def count(key: str) -> int:
            return sum(bool(row[key]) for row in members)

        def ladder_count(key: str) -> int:
            return sum(bool(row["evidence_ladder"][key]) for row in members)

        basic_rate = _rate(ladder_count("E1_BASIC_V2"), n)
        full_rate = _rate(ladder_count("FULL_OBSERVATIONAL"), n)
        raw_rate = _rate(count("raw_signal_present"), n)
        retained_rate = _rate(count("session_retains_signal"), n)
        if raw_rate >= 0.5 and retained_rate < 0.5:
            salvageability = "SESSIONIZATION_OR_GRANULARITY_RISK"
        elif basic_rate >= 0.5:
            salvageability = "SALVAGEABLE_WITH_BASIC_V2"
        elif full_rate >= 0.5:
            salvageability = "SALVAGEABLE_WITH_RICHER_EVIDENCE"
        elif raw_rate < 0.5:
            salvageability = "NETWORK_OBSERVABILITY_LIMITED"
        elif label == "Port_Scanning" and full_rate < 0.5:
            salvageability = "SESSIONIZATION_OR_GRANULARITY_RISK"
        else:
            salvageability = "INCONCLUSIVE"
        recommended_basic, recommended_tool, network_risk, session_risk = RECOMMENDATIONS[label]
        result_row = {
            "class": label,
            "sample_count": n,
            "raw_signal_present_rate": raw_rate,
            "session_retains_signal_rate": retained_rate,
            "payload_raw_present_rate": _rate(count("raw_payload_present"), n),
            "payload_capability_rate": _rate(count("payload_capability_available"), n),
            "payload_visible_rate": _rate(count("payload_visible_current"), n),
            "payload_class_relevant_rate": _rate(count("payload_class_relevant_signal"), n),
            "first8_payload_signal_rate": _rate(count("signal_first_8"), n),
            "later_payload_signal_rate": _rate(sum(bool(row["signal_packet_9_16"] or row["signal_after_16"]) for row in members), n),
            "payload_not_primary_signal_rate": _rate(sum(bool(row["raw_payload_present"] and not row["payload_class_relevant_signal"]) for row in members), n),
            "application_relevant_rate": _rate(count("application_class_relevant_signal"), n),
            "temporal_relevant_rate": _rate(count("temporal_class_relevant_signal"), n),
            "relation_relevant_rate": _rate(count("relation_class_relevant_signal"), n),
            "current_evidence_relevant_rate": _rate(count("current_evidence_supports_label"), n),
            "basic_v2_relevant_rate": basic_rate,
            "full_observational_relevant_rate": full_rate,
            "evidence_ladder": {
                key: {"count": ladder_count(key), "rate": _rate(ladder_count(key), n)}
                for key in (
                    "E0_CURRENT_INITIAL", "E1_BASIC_V2", "E2_PACKET_PAYLOAD_EXPANSION",
                    "E3_APPLICATION", "E4_TEMPORAL", "E5_RELATION", "FULL_OBSERVATIONAL",
                )
            },
            "dominant_failure_mode": _dominant(Counter(row["failure_mode"] for row in members)),
            "failure_mode_distribution": dict(sorted(Counter(row["failure_mode"] for row in members).items())),
            "recommended_basic_evidence": recommended_basic,
            "recommended_next_tool": recommended_tool,
            "network_observability_risk": network_risk,
            "sessionization_risk": session_risk,
            "salvageability": salvageability,
            "rag_potentially_useful_rate": _rate(count("rag_potentially_useful"), n),
        }
        validate_assessment(
            {"failure_mode": result_row["dominant_failure_mode"], "salvageability": result_row["salvageability"]}
        )
        result.append(result_row)
    return result


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(path.stat().st_size).encode("ascii"))
        digest.update(b"\0")
        digest.update(_sha256(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _report_table_availability(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| class | n | raw payload | payload capability | payload visible | application | application visible | temporal visible | relation visible |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        n = row["sample_n"]
        cell = lambda key: f'{row[key + "_n"]}/{n} ({_pct(row[key + "_rate"])})'
        lines.append(
            f'| {row["class"]} | {n} | {cell("payload_raw_present")} | '
            f'{cell("payload_capability_available")} | {cell("payload_visible_current")} | '
            f'{cell("application_available")} | {cell("application_visible_current")} | '
            f'{cell("temporal_visible_current")} | {cell("relation_visible_current")} |'
        )
    return "\n".join(lines)


def _report_table_cross(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| class | stage | n | payload available | payload visible | Teacher sufficient | DeepSeek T1/T2 | Qwen T1/T2 |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        ds_metric, qw_metric = row["deepseek"], row["qwen"]
        lines.append(
            f'| {row["class"]} | {row["stage"]} | {row["n"]} | '
            f'{row["payload_available"]} | {row["payload_visible"]} | '
            f'{row["teacher_sufficient"]}/{row["n"]} ({_pct(row["teacher_sufficient_rate"])}) | '
            f'{ds_metric["top1_correct"]}/{ds_metric["n"]} ({_pct(ds_metric["top1_rate"])}) / '
            f'{ds_metric["top2_contains_gt"]}/{ds_metric["n"]} ({_pct(ds_metric["top2_rate"])}) | '
            f'{qw_metric["top1_correct"]}/{qw_metric["n"]} ({_pct(qw_metric["top1_rate"])}) / '
            f'{qw_metric["top2_contains_gt"]}/{qw_metric["n"]} ({_pct(qw_metric["top2_rate"])}) |'
        )
    return "\n".join(lines)


def _report_table_coverage(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| class | n | raw signal | retained | raw payload | capability | visible | relevant payload | first8 | later | app | current temporal | current relation | current snapshot | Basic-v2 | FULL | dominant failure | salvageability |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    keys = (
        "raw_signal_present_rate",
        "session_retains_signal_rate",
        "payload_raw_present_rate",
        "payload_capability_rate",
        "payload_visible_rate",
        "payload_class_relevant_rate",
        "first8_payload_signal_rate",
        "later_payload_signal_rate",
        "application_relevant_rate",
        "temporal_relevant_rate",
        "relation_relevant_rate",
        "current_evidence_relevant_rate",
        "basic_v2_relevant_rate",
        "full_observational_relevant_rate",
    )
    for row in rows:
        rates = " | ".join(_pct(row[key]) for key in keys)
        lines.append(
            f'| {row["class"]} | {row["sample_count"]} | {rates} | '
            f'{row["dominant_failure_mode"]} | {row["salvageability"]} |'
        )
    return "\n".join(lines)


def _report_table_ladder(rows: list[dict[str, Any]]) -> str:
    stages = (
        "E0_CURRENT_INITIAL",
        "E1_BASIC_V2",
        "E2_PACKET_PAYLOAD_EXPANSION",
        "E3_APPLICATION",
        "E4_TEMPORAL",
        "E5_RELATION",
        "FULL_OBSERVATIONAL",
    )
    lines = [
        "| class | E0 | E1 | E2 | E3 | E4 | E5 | FULL | RAG potentially useful |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        cells = [
            f'{row["evidence_ladder"][stage]["count"]}/{row["sample_count"]} '
            f'({_pct(row["evidence_ladder"][stage]["rate"])})'
            for stage in stages
        ]
        lines.append(
            f'| {row["class"]} | ' + " | ".join(cells) + f' | {_pct(row["rag_potentially_useful_rate"])} |'
        )
    return "\n".join(lines)


def _class_findings(rows: list[dict[str, Any]]) -> str:
    by_class = {row["class"]: row for row in rows}
    explanations = {
        "Backdoor": "The sampled target sessions are mostly one/two-packet incomplete TCP exchanges to a stable service; the audited raw sessions have no decoded command payload. Service-normalized periodic/C2 behavior may help, but Backdoor versus Ransomware remains a granularity/observability risk.",
        "DDoS_HTTP": "HTTP exists in a subset of full sessions, while a single request is not sufficient. The discriminating signal is HTTP-aware rate, same-target concentration, concurrency/burst, and response behavior; current Temporal omits HTTP request counts.",
        "DDoS_TCP": "Payload is present but generic and is not a class signal. Near-unanimous incomplete SYN behavior plus extreme same-target past rate is the useful path, so this class is Temporal-first rather than Payload-first.",
        "MITM": "The raw capture contains repeated ARP replies in which one MAC claims multiple protocol IPs. Those non-IP relation events are excluded from the current IP session builder, so ordinary DNS/multicast target sessions cannot inherit the mechanism without a safe relation/path view.",
        "Normal": "Established MQTT telemetry sessions and bounded payload provide useful benign application evidence, though capture-specific sensor text must be guarded against shortcut learning.",
        "Password": "Explicit credential-form structure is network-visible in 8/30 sampled sessions. The remaining available HTTP evidence is mostly a login page/request without an observed attempt; repeated-auth/application outcomes are legitimate next evidence but are not established for every session.",
        "Port_Scanning": "Short incomplete connections are retained but overlap TCP flooding. In the audited raw range the SYN traffic targets one destination IP:port, so classic port-diversity evidence is absent; this capture/session label needs a granularity warning rather than assumed scan semantics.",
        "Ransomware": "Most sampled sessions are generic incomplete TCP or background name/time traffic and contain no network-visible ransomware semantics. Host-side encryption is not inferred; this remains a real network-observability/task-granularity warning.",
        "SQL_injection": "Sanitized SQL expression/request structure is a strong real-network positive control and is often recoverable in early bounded payload.",
        "Uploading": "Payload/Application is available for a subset, but class-relevant transferred script content appears in only 2/30 sampled sessions; many targets are generic GETs or traffic to another service. Session/label granularity is the primary risk.",
        "Vulnerability_scanner": "Application is often available, but explicit probe/exploit shapes are present only in a subset; strict past-only method/URI-shape diversity adds legitimate scan evidence for some remaining sessions.",
    }
    lines = []
    for label in NEAR_CLASSES:
        row = by_class[label]
        lines.append(
            f'- **{label} → {row["salvageability"]}.** {explanations[label]} '
            f'Dominant failure: `{row["dominant_failure_mode"]}`; next: {row["recommended_next_tool"]}.'
        )
    return "\n".join(lines)


def _build_report(manifest: dict[str, Any]) -> str:
    payload_rows = [row for row in manifest["blind_audit_cross_table"] if row["stage"] == "payload"]
    payload_contributions = ", ".join(
        f'{row["class"]} n={row["n"]}, DS-T1={row["deepseek"]["top1_correct"]}'
        for row in payload_rows
    )
    return f"""# Class-Conditional Evidence Salvageability Audit v1

Status: `{manifest["EVIDENCE_SALVAGE_AUDIT_STATUS"]}`

Dataset salvageability: `{manifest["DATASET_SALVAGEABILITY"]}`

Staged Agent viability: `{manifest["STAGED_AGENT_VIABILITY"]}`

Current primary problem: `{manifest["CURRENT_PRIMARY_PROBLEM"]}`

## Scope and hard boundaries

This is a deterministic, offline diagnostic over the frozen 330-primary blind sample (seed `{EVIDENCE_SALVAGE_SEED}`), its existing 330/330 DeepSeek results, 329/330 valid raw-Qwen results, the 99/99 pair cache, Production v2 assets, and verified raw PCAPs. It does not estimate formal paper accuracy and does not modify the Evidence pipeline. Ground truth is backend-only and is used only after label-free observation features are extracted.

`FORMAL_CORPUS_MODIFIED=false`

`FORMAL_SFT_STARTED=false`

`DEEPSEEK_NEW_API_CALLS=0`

`QWEN_NEW_RUNS=0`

The formal corpus SHA256 remained `{manifest["BASE_CORPUS_SHA256"]}`. U_final isolation was checked only through the existing isolation manifest (`status=PASS`, zero U_final counts); no U_final sample/content was read.

## Zero-cost class × payload/application availability

{_report_table_availability(manifest["class_availability"])}

All 330 states have canonical Initial, Temporal, and Relation backend rows. “Raw payload” in this zero-cost table means a decodable backend raw-audit sidecar; the later RAW matrix separately counts any payload bytes observed in PCAP. “Visible” means present in that particular blind-state snapshot, not merely available to a future tool call.

## Blind Audit Cross Table

{_report_table_cross(manifest["blind_audit_cross_table"])}

The Payload-stage 70.97% is composition-bound: {payload_contributions}. Its 22/31 correct cases are SQL_injection 11, Normal 5, Password 4, and Vulnerability_scanner 2; DDoS_TCP contributes 0/3 and Uploading 0/1. It therefore does **not** establish generalized Payload value for Backdoor, MITM, Ransomware, DDoS_HTTP, DDoS_TCP, or Uploading.

## Exact session and context contract

- `SESSION_GROUPING_KEY=(L3, L4, sorted((IP,port),(IP,port)))`: order-normalized bidirectional endpoint/transport identity (`src/flowsec/production/core.py`, `canonical_endpoint_key`).
- `SESSION_DIRECTIONALITY=bidirectional aggregation; first observed packet fixes initiator/responder orientation`, and later packets receive relative direction (`src/flowsec/production/schema.py`, `SessionAccumulator.add`).
- `SESSION_TIMEOUT=60.0 seconds` from `configs/data/production_freeze_v1.yaml`.
- `SESSION_BOUNDARY_RULE=new session only when the same canonical key has an inter-packet idle gap >60s`; continuously active sessions may exceed 60 seconds (`src/flowsec/production/adapters.py`, `EdgeAdapter.process_capture`).
- `TEMPORAL_WINDOW_ROLE=external strict past-only 60s context`, reset per dataset/capture/split; equal-timestamp sessions are withheld until the full timestamp group is evaluated (`src/flowsec/production/manifests.py`).
- `RELATION_WINDOW_ROLE=external past-only exact communication-pair predecessor`, not part of session construction.

Therefore the current “session” is a bidirectional flow/connection-like aggregate. The 60s contextual window is **not** the session definition.

## Per-Class Evidence Coverage Matrix

{_report_table_coverage(manifest["per_class_evidence_coverage"])}

Raw/session coverage is from all 330 selected sessions, matched by verified PCAP identity, exact production canonical key, and frame interval. `FULL_OBSERVATIONAL` remains target-session plus legal past-only Observation; RAG is excluded. These rates are deterministic feature-audit coverage, not classifier accuracy or proof of sufficiency.

## Offline Evidence Ladder

{_report_table_ladder(manifest["per_class_evidence_coverage"])}

E0 is current Initial only; E1 adds corresponding first-8 bounded/sanitized payload and cheap deterministic application metadata; E2 adds packet/payload 9–16; E3 adds richer structured Application; E4 adds class-relevant but label-free past-only Temporal vocabulary; E5 adds relation/path signals. The ladder is simulated only—no Context-v2 asset was constructed.

## Payload location finding

`BASIC_V2_RECOMMENDED=true`, but not as a universal terminal view. First-8 payload is materially useful for SQL injection and a subset of Password/Uploading/Vulnerability sessions; later payload remains non-zero for those classes. Generic DDoS_TCP payload and random DDoS_HTTP header fragments are payload-present but not fine-class evidence. Backdoor, MITM, Port_Scanning, and Ransomware usually have no class-relevant decoded payload in the selected target sessions. First-8 metadata + corresponding bounded payload + summary + cheap app metadata is a better Basic than metadata-only Initial, while staged tools remain necessary.

## Temporal and Relation vocabulary audit

`CURRENT_TEMPORAL_FEATURES={manifest["CURRENT_TEMPORAL_FEATURES"]}`

`CURRENT_RELATION_FEATURES={manifest["CURRENT_RELATION_FEATURES"]}`

Missing Temporal vocabulary includes explicit SYN count/rate, handshake-completion counts, burstiness, HTTP request/method/URI ratios, target concentration at the relevant service, port diversity, authentication outcome sequences, and service-normalized periodicity. Missing Relation vocabulary includes destination/service fan-in/fan-out, port/path diversity, ARP identity mapping changes/conflicts, DNS answer mapping changes, and protocol/responder path changes. Low current Temporal/Relation blind accuracy therefore does not show those evidence families are useless; it shows the present vocabulary is too generic for several classes.

## Class-conditional interpretation

{_class_findings(manifest["per_class_evidence_coverage"])}

## Decision questions

1. **Does Payload 70.97% generalize?** No. It is dominated by SQL_injection/Normal plus smaller Password/Vulnerability contributions and excludes several hard classes entirely.
2. **Where do difficult classes fail?** DDoS_HTTP/DDoS_TCP are primarily feature-design/Temporal problems; MITM is a relation plus session/granularity problem; Password is payload selection plus Application/Temporal; Uploading is mixed payload/application selection and label granularity; Backdoor and especially Ransomware retain serious network-observability/granularity risk.
3. **Is Basic-v2 better?** Yes, as an initial state, because it recovers real early application/payload semantics without adding backend identity. It is not a replacement for staged acquisition.
4. **Is staged class-conditional acquisition viable?** Mixed but supported for specific classes. SQL/Password/Uploading/Vulnerability can benefit from Payload/Application, DDoS classes from Temporal, and MITM from Relation; several capture-labeled target sessions still lack a discriminating observation. RAG is potentially useful only after an Observation exists and needs protocol/threat interpretation; aggregate estimated applicability is {_pct(manifest["RAG_POTENTIALLY_USEFUL_RATE"])}.
5. **Which classes remain risky under full Observation?** Backdoor and Ransomware remain the strongest real risks; MITM additionally requires a relation observation unit that retains the captured ARP/DNS mechanism. These are mixed warnings, not a global rejection of Edge-IIoTset.

## Limitations

- This is an observation-feature coverage audit, not a trained ablation; thresholds are conservative diagnostic rules and must not be reported as paper performance.
- Fine labels are verified pure-capture labels, but capture-level purity does not guarantee every reconstructed flow contains class-specific semantics. That mismatch is precisely what the per-session audit exposes.
- Existing Application/Payload sidecars are bounded and sanitized. The raw scan locates real packet positions but never makes raw identities or unsanitized payload model-visible.
- `FULL_OBSERVATIONAL` does not include host activity, synthetic evidence, future traffic, RAG, or U_final.

## Final fields

```text
EVIDENCE_SALVAGE_AUDIT_STATUS={manifest["EVIDENCE_SALVAGE_AUDIT_STATUS"]}
DATASET_SALVAGEABILITY={manifest["DATASET_SALVAGEABILITY"]}
STAGED_AGENT_VIABILITY={manifest["STAGED_AGENT_VIABILITY"]}
CURRENT_PRIMARY_PROBLEM={manifest["CURRENT_PRIMARY_PROBLEM"]}
BASIC_V2_RECOMMENDED={str(manifest["BASIC_V2_RECOMMENDED"]).lower()}
FORMAL_CORPUS_MODIFIED=false
FORMAL_SFT_STARTED=false
DEEPSEEK_NEW_API_CALLS=0
QWEN_NEW_RUNS=0
```
"""


def run(args: argparse.Namespace) -> int:
    args.output_root.mkdir(parents=True, exist_ok=True)
    corpus_before = _sha256(args.corpus)
    if corpus_before != CORPUS_SHA256:
        raise ValueError("formal corpus SHA256 changed before audit")
    model_cache_before = {
        "deepseek": _tree_digest(args.cache_root / "deepseek"),
        "qwen": _tree_digest(args.cache_root / "qwen"),
        "pairs": _tree_digest(args.cache_root / "pairs"),
    }

    primary = _read(args.cache_root / "primary_sample_manifest.json")
    pair_manifest = _read(args.cache_root / "pairs/pair_sample_manifest.json")
    _manifest_digest(primary, PRIMARY_MANIFEST_DIGEST, "primary sample")
    _manifest_digest(pair_manifest, PAIR_MANIFEST_DIGEST, "pair sample")
    if primary["status"] != "PASS" or primary["seed"] != EVIDENCE_SALVAGE_SEED:
        raise ValueError("fixed 330 sample or leakage gate changed")
    samples = primary["samples"]
    if len(samples) != 330 or Counter(row["fine_label_backend_only"] for row in samples) != {label: 30 for label in NEAR_CLASSES}:
        raise ValueError("fixed 330 class-balanced sample changed")
    if set(row["fine_label_backend_only"] for row in samples) & PROHIBITED_CLASSES:
        raise ValueError("U_final label entered the audit sample")
    deepseek = _read(args.cache_root / "deepseek/scored_results.json")["rows"]
    qwen = _read(args.cache_root / "qwen/scored_results.json")["rows"]
    pairs = _read(args.cache_root / "pairs/deepseek/scored_results.json")["rows"]
    pair_summary = _read(args.cache_root / "pairs/deepseek/summary.json")
    if Counter(row["status"] for row in deepseek) != {"PASS": 330}:
        raise ValueError("DeepSeek 330 cache incomplete")
    if Counter(row["status"] for row in qwen) != {"PASS": 329, "QUARANTINE": 1}:
        raise ValueError("Qwen 329+1 cache incomplete")
    if Counter(row["status"] for row in pairs) != {"PASS": 99} or pair_summary["total_deepseek_requests"] != 529:
        raise ValueError("pair cache or 529-request accounting changed")

    sample_ids = [str(row["sample_id"]) for row in samples]
    state_ids = {str(row["evidence_state_id"]) for row in samples}
    snapshots = _snapshot_index(args.snapshot_universe, state_ids)
    backend_rows = _parquet_rows(args.production_root / "backend_records", sample_ids)
    initial_rows = _parquet_rows(args.production_root / "initial_model_views", sample_ids)
    temporal_rows = _parquet_rows(args.production_root / "temporal_index", sample_ids)
    relation_rows = _parquet_rows(args.production_root / "relation_index", sample_ids)
    expansion_rows = _parquet_rows(args.production_root / "expandable_packet_store", sample_ids)
    app_rows = _parquet_rows(args.near_root / "application/captures", sample_ids)
    payload_rows = _parquet_rows(args.near_root / "sanitized_payload/captures", sample_ids)
    raw_sidecar_rows = _parquet_rows(args.near_root / "sanitized_payload/backend_raw_audit", sample_ids)
    required_counts = {
        "backend": len(backend_rows), "initial": len(initial_rows), "temporal": len(temporal_rows),
        "relation": len(relation_rows),
    }
    if any(value != 330 for value in required_counts.values()):
        raise ValueError(f"Production join incomplete: {required_counts}")

    backend_by_id = {row["sample_id"]: row for row in backend_rows}
    initial_by_id = {row["sample_id"]: json.loads(row["view_json"]) for row in initial_rows}
    temporal_by_id = {row["sample_id"]: json.loads(row["context_stats_json"]) for row in temporal_rows}
    relation_by_id = {row["sample_id"]: row for row in relation_rows}
    expansion_ids = {row["sample_id"] for row in expansion_rows}
    app_by_id = {row["sample_id"]: json.loads(row["application_json"]) for row in app_rows}
    payload_by_id = {row["sample_id"]: json.loads(row["payload_json"]) for row in payload_rows}
    raw_sidecar_ids = {row["sample_id"] for row in raw_sidecar_rows}

    availability: dict[str, dict[str, Any]] = {}
    for sample in samples:
        sample_id, state_id = sample["sample_id"], sample["evidence_state_id"]
        visible = _visible_types(snapshots[state_id])
        availability[sample_id] = {
            "payload_raw_present": sample_id in raw_sidecar_ids,
            "payload_capability_available": sample_id in payload_by_id,
            "payload_visible_current": "payload" in visible,
            "application_available": sample_id in app_by_id,
            "application_visible_current": "application" in visible,
            "temporal_available": sample_id in temporal_by_id,
            "temporal_visible_current": "temporal" in visible,
            "relation_available": sample_id in relation_by_id,
            "relation_visible_current": "relation" in visible,
            "packet_9_16_available": sample_id in expansion_ids,
        }

    provenance = _read(args.production_root / "manifests/edge_label_provenance_manifest.json")
    capture_specs = {row["capture_id"]: row for row in provenance["captures"]}
    by_capture: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in backend_rows:
        by_capture[str(row["scenario_or_capture_id"])].append(row)
    raw_by_id: dict[str, dict[str, Any]] = {}
    capture_summaries: dict[str, dict[str, Any]] = {}
    for capture_id in sorted(by_capture):
        spec = capture_specs[capture_id]
        cache_path = args.output_root / "raw_checkpoints" / f"{capture_id}.json"
        selected_digest = content_digest(sorted(row["sample_id"] for row in by_capture[capture_id]))
        checkpoint = _read(cache_path) if cache_path.is_file() else None
        if not (
            checkpoint
            and checkpoint.get("pcap_sha256") == spec["pcap_sha256"]
            and checkpoint.get("selected_sample_digest") == selected_digest
            and (
                capture_id
                not in {
                    "Attack_DDoS_HTTP",
                    "Attack_MITM",
                    "Attack_Password",
                    "Attack_SQL_injection",
                    "Attack_Uploading",
                    "Attack_Vulnerability_scanner",
                }
                or checkpoint.get("raw_scanner_version") == "RAW_CLASS_CONDITIONAL_SCANNER_V3"
            )
        ):
            print(f"RAW_SCAN_START capture={capture_id} samples={len(by_capture[capture_id])}", flush=True)
            checkpoint = _capture_raw_audit(
                capture_id=capture_id,
                pcap=Path(spec["source_mapping"]["pcap"]),
                expected_sha256=str(spec["pcap_sha256"]),
                locators=by_capture[capture_id],
                tshark=args.tshark,
            )
            checkpoint["selected_sample_digest"] = selected_digest
            _write_json(cache_path, checkpoint)
            print(f"RAW_SCAN_DONE capture={capture_id} rows={checkpoint['tshark_rows_read']}", flush=True)
        capture_summaries[capture_id] = {key: value for key, value in checkpoint.items() if key != "samples"}
        for raw_row in checkpoint["samples"]:
            raw_by_id[raw_row["sample_id"]] = raw_row
    if set(raw_by_id) != set(sample_ids):
        raise ValueError(f"raw audit coverage incomplete: {len(raw_by_id)}/330")

    assessed = []
    for sample in samples:
        sample_id = sample["sample_id"]
        capture_id = backend_by_id[sample_id]["scenario_or_capture_id"]
        assessed.append(
            _assess_sample(
                sample=sample,
                initial=initial_by_id[sample_id],
                temporal=temporal_by_id[sample_id],
                relation=relation_by_id[sample_id],
                application=app_by_id.get(sample_id),
                availability=availability[sample_id],
                snapshot=snapshots[sample["evidence_state_id"]],
                raw=raw_by_id[sample_id],
                capture_summary=capture_summaries[capture_id],
            )
        )
    per_class = _aggregate_classes(assessed)
    class_availability = _class_availability(samples, availability)
    cross = _cross_table(samples=samples, deepseek=deepseek, qwen=qwen, availability=availability)
    rag_rate = _rate(sum(row["rag_potentially_useful"] for row in assessed), len(assessed))

    detailed_path = args.output_root / "sample_layer_audit.jsonl"
    capture_path = args.output_root / "capture_raw_summary.json"
    cross_path = args.output_root / "blind_cross_table.json"
    aggregate_path = args.output_root / "aggregate.json"
    _write_jsonl(detailed_path, sorted(assessed, key=lambda row: (row["fine_label_backend_only"], row["sample_id"])))
    _write_json(capture_path, capture_summaries)
    _write_json(cross_path, cross)

    ufinal = _read(args.near_root / "manifests/u_final_isolation_audit.json")
    ufinal_zero = (
        ufinal.get("status") == "PASS"
        and ufinal.get("u_final_count", 0) == 0
        and all(
            int(value) == 0
            for key, value in ufinal.get("findings", {}).items()
            if "u_final" in key
        )
    )
    manifest: dict[str, Any] = {
        "audit_version": EVIDENCE_SALVAGE_AUDIT_VERSION,
        "EVIDENCE_SALVAGE_AUDIT_STATUS": "PASS_WITH_LIMITATIONS",
        "DATASET_SALVAGEABILITY": "MIXED",
        "STAGED_AGENT_VIABILITY": "MIXED",
        "CURRENT_PRIMARY_PROBLEM": "MIXED",
        "BASIC_V2_RECOMMENDED": True,
        "FORMAL_CORPUS_MODIFIED": False,
        "FORMAL_SFT_STARTED": False,
        "DEEPSEEK_NEW_API_CALLS": 0,
        "QWEN_NEW_RUNS": 0,
        "BASE_CORPUS_SHA256": CORPUS_SHA256,
        "seed": EVIDENCE_SALVAGE_SEED,
        "primary_sample_count": len(samples),
        "raw_detailed_sample_count": len(assessed),
        "raw_capture_count": len(capture_summaries),
        "existing_cache_integrity": {
            "deepseek_valid": 330,
            "qwen_valid": 329,
            "qwen_quarantine": 1,
            "pair_valid": 99,
            "existing_deepseek_request_count": 529,
            "primary_manifest_digest": PRIMARY_MANIFEST_DIGEST,
            "pair_manifest_digest": PAIR_MANIFEST_DIGEST,
            "prompt_leakage_gate": primary["status"],
        },
        "session_contract": {
            "SESSION_GROUPING_KEY": "(l3,l4,sorted((ip,port),(ip,port)))",
            "SESSION_DIRECTIONALITY": "BIDIRECTIONAL_FIRST_PACKET_ORIENTED",
            "SESSION_TIMEOUT": 60.0,
            "SESSION_BOUNDARY_RULE": "SAME_CANONICAL_KEY_IDLE_GAP_GT_60_SECONDS",
            "TEMPORAL_WINDOW_ROLE": "EXTERNAL_STRICT_PAST_ONLY_CONTEXT",
            "RELATION_WINDOW_ROLE": "EXTERNAL_PAST_ONLY_EXACT_PAIR_PREDECESSOR",
        },
        "CURRENT_TEMPORAL_FEATURES": [
            "window_seconds", "prior_session_count", "unique_destination_count",
            "unique_destination_service_category_count", "same_destination_distinct_source_count",
            "repeated_pair_count", "incomplete_handshake_ratio", "inter_session_gap",
            "prior_packets", "prior_bytes",
        ],
        "CURRENT_RELATION_FEATURES": ["node_roles=current_source,target_cluster", "repeated_relation"],
        "class_availability": class_availability,
        "blind_audit_cross_table": cross,
        "per_class_evidence_coverage": per_class,
        "RAG_POTENTIALLY_USEFUL_RATE": rag_rate,
        "u_final_isolation_check": {"status": "PASS" if ufinal_zero else "FAIL", "content_inspected": False},
        "artifact_scope": {
            "detailed_rows_external": str(detailed_path),
            "capture_summary_external": str(capture_path),
            "cross_table_external": str(cross_path),
        },
        "limitations": [
            "Coverage is deterministic observational-feature audit, not trained-model or paper accuracy.",
            "Capture-level label purity does not imply every target flow contains class semantics.",
            "FULL_OBSERVATIONAL excludes host state, future traffic, RAG, synthetic evidence, and U_final.",
        ],
    }
    _write_json(aggregate_path, manifest)
    manifest["external_artifacts"] = {
        path.name: {"path": str(path), "size_bytes": path.stat().st_size, "sha256": _sha256(path)}
        for path in (detailed_path, capture_path, cross_path, aggregate_path)
    }
    manifest["formal_corpus_sha256_after"] = _sha256(args.corpus)
    model_cache_after = {
        "deepseek": _tree_digest(args.cache_root / "deepseek"),
        "qwen": _tree_digest(args.cache_root / "qwen"),
        "pairs": _tree_digest(args.cache_root / "pairs"),
    }
    manifest["existing_model_cache_unchanged"] = model_cache_before == model_cache_after
    if manifest["formal_corpus_sha256_after"] != CORPUS_SHA256:
        raise ValueError("formal corpus changed during audit")
    if not manifest["existing_model_cache_unchanged"]:
        raise ValueError("existing model cache changed during offline audit")
    if not ufinal_zero:
        raise ValueError("U_final isolation manifest no longer passes")
    report = _build_report(manifest)
    _write_text(args.report, report)
    _write_json(args.manifest, manifest)
    print(f"EVIDENCE_SALVAGE_AUDIT_STATUS={manifest['EVIDENCE_SALVAGE_AUDIT_STATUS']}")
    print(f"DATASET_SALVAGEABILITY={manifest['DATASET_SALVAGEABILITY']}")
    print(f"STAGED_AGENT_VIABILITY={manifest['STAGED_AGENT_VIABILITY']}")
    print("DEEPSEEK_NEW_API_CALLS=0")
    print("QWEN_NEW_RUNS=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-root", type=Path, default=Path("/root/autodl-tmp/experiments/blind_sufficiency_calibration_v1"))
    parser.add_argument("--production-root", type=Path, default=Path("/root/autodl-tmp/processed/edge_split_revision_v2"))
    parser.add_argument("--near-root", type=Path, default=Path("/root/autodl-tmp/processed/near_pretraining_v1"))
    parser.add_argument("--output-root", type=Path, default=Path("/root/autodl-tmp/experiments/evidence_salvage_audit_v1"))
    parser.add_argument("--snapshot-universe", type=Path, default=Path("/root/autodl-tmp/processed/near_pretraining_v1/sft_corpus/evidence_snapshot_universe_v1.jsonl"))
    parser.add_argument("--corpus", type=Path, default=Path("/root/autodl-tmp/processed/near_pretraining_v1/sft_corpus/final/near_sft_corpus_v2.jsonl"))
    parser.add_argument("--report", type=Path, default=Path("reports/training_readiness/evidence_salvageability_audit_v1.md"))
    parser.add_argument("--manifest", type=Path, default=Path("reports/training_readiness/evidence_salvageability_audit_v1_manifest.json"))
    parser.add_argument("--tshark", default="tshark")
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(run(parse_args()))
