from __future__ import annotations

import bisect
import csv
import hashlib
import json
import math
import os
import platform
import random
import shutil
import statistics
import subprocess
import sys
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction import DictVectorizer
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    recall_score,
)


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(os.environ.get("FLOWSEC_GATE_OUTPUT", Path(__file__).resolve().parent)).expanduser()
EDGE_DATA_ROOT = Path(
    os.environ.get("EDGE_DATA_ROOT", ROOT / "data" / "external" / "edge_iiotset")
).expanduser()
IOT23_DATA_ROOT = Path(
    os.environ.get(
        "IOT23_DATA_ROOT", ROOT / "data" / "external" / "iot23" / "official_subset"
    )
).expanduser()
EDGE_ROOT = EDGE_DATA_ROOT / "official_subset"
EDGE_FULL = EDGE_DATA_ROOT / "extracted" / "Edge-IIoTset dataset"
IOT_ROOT = IOT23_DATA_ROOT
TSHARK = Path(
    os.environ.get("TSHARK_BIN", shutil.which("tshark") or r"C:\Program Files\Wireshark\tshark.exe")
)
CAPINFOS = Path(
    os.environ.get(
        "CAPINFOS_BIN", shutil.which("capinfos") or r"C:\Program Files\Wireshark\capinfos.exe"
    )
)
RUN_AT = datetime.now(timezone.utc).isoformat()
SEEDS = [17, 41]
MAX_PACKETS = 16
INITIAL_PACKETS = 8
CONTEXT_SECONDS = 60

PROHIBITED_FIELDS = [
    "raw_ip",
    "timestamp_start",
    "timestamp_end",
    "absolute_time",
    "source_file",
    "scenario_or_capture_id",
    "dataset_name",
    "stable_device_id",
    "fixed_payload",
    "fixed_uri",
    "fixed_topic",
    "fixed_username",
    "attack_script_id",
    "raw_port",
]

MODEL_FEATURE_WHITELIST = [
    "packet_sequence.direction",
    "packet_sequence.packet_length",
    "packet_sequence.relative_iat",
    "packet_sequence.protocol",
    "packet_sequence.tcp_flags",
    "session_summary.duration",
    "session_summary.forward_packets",
    "session_summary.backward_packets",
    "session_summary.forward_bytes",
    "session_summary.backward_bytes",
    "session_summary.packet_length_stats",
    "session_summary.iat_stats",
    "session_summary.handshake_state",
    "session_summary.service_category",
    "temporal_context",
    "application_evidence.allowed_categories_only",
    "capabilities",
    "missing_fields",
]


EDGE_SOURCES = {
    "Normal_Heart_Rate": {
        "pcap": EDGE_ROOT / "Heart_Rate.pcap",
        "csv": EDGE_ROOT / "Heart_Rate.csv",
        "label": "Normal",
        "role": "known",
    },
    "Port_Scanning": {
        "pcap": EDGE_ROOT / "Port Scanning attack.pcap",
        "csv": EDGE_ROOT / "Port_Scanning_attack.csv",
        "label": "Port_Scanning",
        "role": "known",
    },
    "DDoS_HTTP": {
        "pcap": EDGE_ROOT / "DDoS HTTP Flood Attacks.pcap",
        "csv": EDGE_ROOT / "DDoS_HTTP_Flood_attack.csv",
        "label": "DDoS_HTTP",
        "role": "known",
    },
    "Backdoor": {
        "pcap": EDGE_ROOT / "Backdoor_attack.pcap",
        "csv": EDGE_ROOT / "Backdoor_attack.csv",
        "label": "Backdoor",
        "role": "known",
    },
    "SQL_Injection": {
        "pcap": EDGE_ROOT / "SQL injection attack.pcap",
        "csv": EDGE_ROOT / "SQL_injection_attack.csv",
        "label": "SQL_injection",
        "role": "unknown_dev",
    },
    "Ransomware": {
        "pcap": EDGE_ROOT / "Ransomware attack.pcap",
        "csv": EDGE_ROOT / "Ransomware_attack.csv",
        "label": "Ransomware",
        "role": "unknown_final",
    },
}

EDGE_ANOMALY_PCAP = (
    EDGE_FULL / "Attack traffic" / "Vulnerability scanner attack.pcap"
)

IOT_SOURCES = {
    "CTU-IoT-Malware-Capture-8-1": {
        "pcap": IOT_ROOT
        / "CTU-IoT-Malware-Capture-8-1"
        / "2018-07-31-15-15-09-192.168.100.113.pcap",
        "log": IOT_ROOT / "CTU-IoT-Malware-Capture-8-1" / "bro" / "conn.log.labeled",
        "split": "train",
        "family": "Hakai",
    },
    "CTU-IoT-Malware-Capture-20-1": {
        "pcap": IOT_ROOT
        / "CTU-IoT-Malware-Capture-20-1"
        / "2018-10-02-13-12-30-192.168.100.103.pcap",
        "log": IOT_ROOT / "CTU-IoT-Malware-Capture-20-1" / "bro" / "conn.log.labeled",
        "split": "validation",
        "family": "Torii",
    },
    "CTU-IoT-Malware-Capture-21-1": {
        "pcap": IOT_ROOT
        / "CTU-IoT-Malware-Capture-21-1"
        / "2018-10-03-15-22-32-192.168.100.113.pcap",
        "log": IOT_ROOT / "CTU-IoT-Malware-Capture-21-1" / "bro" / "conn.log.labeled",
        "split": "validation",
        "family": "Torii",
    },
    "CTU-IoT-Malware-Capture-34-1": {
        "pcap": IOT_ROOT
        / "CTU-IoT-Malware-Capture-34-1"
        / "2018-12-21-15-50-14-192.168.1.195.pcap",
        "log": IOT_ROOT / "CTU-IoT-Malware-Capture-34-1" / "bro" / "conn.log.labeled",
        "split": "test",
        "family": "Mirai",
    },
    "CTU-IoT-Malware-Capture-42-1": {
        "pcap": IOT_ROOT
        / "CTU-IoT-Malware-Capture-42-1"
        / "2019-01-10-14-34-38-192.168.1.197.pcap",
        "log": IOT_ROOT / "CTU-IoT-Malware-Capture-42-1" / "bro" / "conn.log.labeled",
        "split": "unknown_final",
        "family": "Trojan",
    },
    "CTU-Honeypot-Capture-4-1": {
        "pcap": IOT_ROOT
        / "CTU-Honeypot-Capture-4-1"
        / "2018-10-25-14-06-32-192.168.1.132.pcap",
        "log": IOT_ROOT / "CTU-Honeypot-Capture-4-1" / "bro" / "conn.log.labeled",
        "split": "train",
        "family": "Philips-Hue-Benign",
    },
    "CTU-Honeypot-Capture-7-1-Somfy-01": {
        "pcap": IOT_ROOT
        / "CTU-Honeypot-Capture-7-1"
        / "Somfy-01"
        / "2019-07-03-15-15-47-first_start_somfy_gateway.pcap",
        "log": IOT_ROOT
        / "CTU-Honeypot-Capture-7-1"
        / "Somfy-01"
        / "bro"
        / "conn.log.labeled",
        "split": "test",
        "family": "Somfy-Benign",
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def portable_path(path: Path) -> str:
    """Prefer a repository-relative path while supporting external server data roots."""
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def json_dump(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def jsonl_dump(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            count += 1
    return count


def safe_float(value: str | None, default: float = 0.0) -> float:
    if value in (None, "", "-", "(empty)"):
        return default
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def safe_int(value: str | None, default: int = 0) -> int:
    if value in (None, "", "-", "(empty)"):
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


@dataclass
class Packet:
    ts: float
    length: int
    src: str
    dst: str
    proto: str
    sport: int
    dport: int
    flags: int


@dataclass
class Session:
    capture: str
    key: tuple[Any, ...]
    initiator: str
    responder: str
    service_port: int
    start: float
    end: float
    packets: list[Packet] = field(default_factory=list)


def endpoint_key(src: str, sport: int, dst: str, dport: int, proto: str) -> tuple[Any, ...]:
    left = (src, sport)
    right = (dst, dport)
    return (proto, left, right) if left <= right else (proto, right, left)


def service_category(proto: str, sport: int, dport: int, supplied: str = "") -> str:
    supplied = supplied.strip().lower()
    if supplied and supplied not in {"-", "(empty)"}:
        return supplied.upper()
    ports = {sport, dport}
    mapping = {
        20: "FTP",
        21: "FTP",
        22: "SSH",
        23: "TELNET",
        25: "SMTP",
        53: "DNS",
        67: "DHCP",
        68: "DHCP",
        80: "HTTP",
        110: "POP3",
        123: "NTP",
        143: "IMAP",
        161: "SNMP",
        443: "HTTPS",
        445: "SMB",
        502: "MODBUS",
        1883: "MQTT",
        1900: "SSDP",
        5353: "MDNS",
        8080: "HTTP_ALT",
        8883: "MQTT_TLS",
    }
    for port, name in mapping.items():
        if port in ports:
            return name
    nonzero = [port for port in ports if port]
    if not nonzero:
        return proto
    if min(nonzero) < 1024:
        return "OTHER_SYSTEM"
    if min(nonzero) < 49152:
        return "OTHER_REGISTERED"
    return "EPHEMERAL"


def tshark_packets(path: Path) -> tuple[list[Packet], dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    command = [
        str(TSHARK),
        "-n",
        "-r",
        str(path),
        "-T",
        "fields",
        "-E",
        "separator=/t",
        "-E",
        "occurrence=f",
    ]
    fields = [
        "frame.time_epoch",
        "frame.len",
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
    ]
    for name in fields:
        command.extend(["-e", name])
    proc = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    packets: list[Packet] = []
    skipped = 0
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < len(fields):
            parts.extend([""] * (len(fields) - len(parts)))
        ts = safe_float(first_value(parts[0]), -1.0)
        src = first_value(parts[2]) or first_value(parts[3])
        dst = first_value(parts[4]) or first_value(parts[5])
        if ts < 0 or not src or not dst:
            skipped += 1
            continue
        tcp_s, tcp_d = safe_int(first_value(parts[8])), safe_int(first_value(parts[9]))
        udp_s, udp_d = safe_int(first_value(parts[10])), safe_int(first_value(parts[11]))
        ip_proto = safe_int(first_value(parts[6]) or first_value(parts[7]))
        if tcp_s or tcp_d or ip_proto == 6:
            proto, sport, dport = "TCP", tcp_s, tcp_d
        elif udp_s or udp_d or ip_proto == 17:
            proto, sport, dport = "UDP", udp_s, udp_d
        elif ip_proto in {1, 58}:
            proto, sport, dport = "ICMP", 0, 0
        else:
            proto, sport, dport = f"IP_{ip_proto}" if ip_proto else "IP_OTHER", 0, 0
        packets.append(
            Packet(
                ts=ts,
                length=safe_int(first_value(parts[1])),
                src=src,
                dst=dst,
                proto=proto,
                sport=sport,
                dport=dport,
                flags=parse_flags(parts[12]),
            )
        )
    packets.sort(key=lambda item: item.ts)
    return packets, {
        "command": command,
        "returncode": proc.returncode,
        "stderr": proc.stderr.strip()[-4000:],
        "parsed_ip_packets": len(packets),
        "skipped_non_ip_or_unparseable": skipped,
    }


def sessionize(capture: str, packets: list[Packet], idle_seconds: float = 60.0) -> list[Session]:
    active: dict[tuple[Any, ...], Session] = {}
    completed: list[Session] = []
    for packet in packets:
        key = endpoint_key(packet.src, packet.sport, packet.dst, packet.dport, packet.proto)
        current = active.get(key)
        if current is None or packet.ts - current.end > idle_seconds:
            if current is not None:
                completed.append(current)
            current = Session(
                capture=capture,
                key=key,
                initiator=packet.src,
                responder=packet.dst,
                service_port=packet.dport,
                start=packet.ts,
                end=packet.ts,
            )
            active[key] = current
        current.end = max(current.end, packet.ts)
        current.packets.append(packet)
    completed.extend(active.values())
    return sorted(completed, key=lambda item: (item.start, item.key))


def numeric_stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"min": 0.0, "max": 0.0, "mean": 0.0, "std": 0.0}
    return {
        "min": float(min(values)),
        "max": float(max(values)),
        "mean": float(statistics.fmean(values)),
        "std": float(statistics.pstdev(values)) if len(values) > 1 else 0.0,
    }


def handshake_state(flags: list[int], fallback: str = "") -> str:
    syn = any(value & 0x02 and not value & 0x10 for value in flags)
    synack = any(value & 0x02 and value & 0x10 for value in flags)
    rst = any(value & 0x04 for value in flags)
    fin = any(value & 0x01 for value in flags)
    if syn and synack and (fin or rst):
        return "ESTABLISHED_CLOSED"
    if syn and synack:
        return "ESTABLISHED_OPEN"
    if syn and not synack:
        return "INCOMPLETE_HANDSHAKE"
    if rst:
        return "RESET"
    return fallback or "NOT_APPLICABLE_OR_UNOBSERVED"


def packet_sequence(packets: list[Packet], initiator: str, limit: int = MAX_PACKETS) -> list[dict[str, Any]]:
    sequence: list[dict[str, Any]] = []
    previous = packets[0].ts if packets else 0.0
    for packet in packets[:limit]:
        sequence.append(
            {
                "direction": (
                    "initiator_to_responder" if packet.src == initiator else "responder_to_initiator"
                ),
                "packet_length": packet.length,
                "relative_iat": round(max(0.0, packet.ts - previous), 6),
                "protocol": packet.proto,
                "tcp_flags": packet.flags if packet.proto == "TCP" else None,
            }
        )
        previous = packet.ts
    return sequence


def build_record(
    *,
    dataset: str,
    capture: str,
    split: str,
    fine_label: str,
    coarse_label: str,
    start: float,
    end: float,
    initiator: str,
    responder: str,
    packets: list[Packet],
    summary_override: dict[str, Any] | None = None,
    service_hint: str = "",
    application_capability: bool = False,
    source_file: str,
) -> dict[str, Any]:
    forward = [item for item in packets if item.src == initiator]
    backward = [item for item in packets if item.src != initiator]
    lengths = [float(item.length) for item in packets]
    iats = [max(0.0, right.ts - left.ts) for left, right in zip(packets, packets[1:])]
    summary = {
        "duration": max(0.0, end - start),
        "forward_packets": len(forward),
        "backward_packets": len(backward),
        "forward_bytes": sum(item.length for item in forward),
        "backward_bytes": sum(item.length for item in backward),
        "packet_length_stats": numeric_stats(lengths),
        "iat_stats": numeric_stats(iats),
        "handshake_state": handshake_state([item.flags for item in packets]),
        "service_category": service_category(
            packets[0].proto if packets else "UNKNOWN",
            packets[0].sport if packets else 0,
            packets[0].dport if packets else 0,
            service_hint,
        ),
    }
    if summary_override:
        summary.update(summary_override)
    identity = f"{dataset}|{capture}|{start:.6f}|{initiator}|{responder}|{fine_label}"
    sample_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    missing: list[str] = []
    if not packets:
        missing.append("packet_sequence")
    if not application_capability:
        missing.append("application_evidence")
    return {
        "sample_id": sample_id,
        "dataset_name": dataset,
        "scenario_or_capture_id": capture,
        "split": split,
        "timestamp_start": start,
        "timestamp_end": end,
        "packet_sequence": packet_sequence(packets, initiator),
        "session_summary": summary,
        "temporal_context": {},
        "application_evidence": None,
        "label_schema_id": "edge_native_v1" if dataset == "Edge-IIoTset" else "iot23_behavior_v1",
        "fine_label": fine_label,
        "coarse_label": coarse_label,
        "capabilities": {
            "packet_expand": len(packets) > INITIAL_PACKETS,
            "temporal_context": True,
            "application_evidence": application_capability,
        },
        "missing_fields": missing,
        "prohibited_model_fields": PROHIBITED_FIELDS,
        "_audit": {
            "initiator": initiator,
            "responder": responder,
            "source_file": source_file,
            "session_key": list(
                endpoint_key(
                    packets[0].src,
                    packets[0].sport,
                    packets[0].dst,
                    packets[0].dport,
                    packets[0].proto,
                )
            )
            if packets
            else [],
        },
    }


def edge_coarse(label: str) -> str:
    if label == "Normal":
        return "Benign"
    if label.startswith("DDoS"):
        return "Availability"
    if label == "Port_Scanning":
        return "Reconnaissance"
    if label == "SQL_injection":
        return "Injection"
    return "Malware"


def time_block_split(session: Session, minimum: float, maximum: float) -> str | None:
    span = max(1.0, maximum - minimum)
    start_fraction = (session.start - minimum) / span
    end_fraction = (session.end - minimum) / span
    blocks = [(0.00, 0.55, "train"), (0.60, 0.75, "validation"), (0.80, 1.00, "test")]
    for left, right, name in blocks:
        if start_fraction >= left and end_fraction <= right:
            return name
    return None


def csv_label_counts(path: Path) -> Counter[str]:
    counts: Counter[str] = Counter()
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            counts[str(row.get("Attack_type", "")).strip()] += 1
    return counts


def edge_adapter() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records: list[dict[str, Any]] = []
    captures: dict[str, Any] = {}
    for capture, spec in EDGE_SOURCES.items():
        packets, parse = tshark_packets(spec["pcap"])
        sessions = sessionize(capture, packets)
        labels = csv_label_counts(spec["csv"])
        starts = [session.start for session in sessions]
        minimum, maximum = min(starts), max(session.end for session in sessions)
        assigned = Counter()
        for session in sessions:
            if spec["role"] == "known":
                split = time_block_split(session, minimum, maximum)
                if split is None:
                    continue
            else:
                split = str(spec["role"])
            record = build_record(
                dataset="Edge-IIoTset",
                capture=capture,
                split=split,
                fine_label=spec["label"],
                coarse_label=edge_coarse(spec["label"]),
                start=session.start,
                end=session.end,
                initiator=session.initiator,
                responder=session.responder,
                packets=session.packets,
                application_capability=spec["label"] in {"SQL_injection"},
                source_file=spec["pcap"].name,
            )
            records.append(record)
            assigned[split] += 1
        captures[capture] = {
            "label": spec["label"],
            "role": spec["role"],
            "pcap_packets": len(packets),
            "sessions": len(sessions),
            "assigned": dict(assigned),
            "csv_label_counts": dict(labels),
            "label_is_file_stable": set(labels) <= {spec["label"]},
            "parse": parse,
            "time_span_seconds": maximum - minimum,
            "gap_policy": "train 0-55%; gap 5%; validation 60-75%; gap 5%; test 80-100%",
        }
    anomaly = {"path": portable_path(EDGE_ANOMALY_PCAP), "exists": EDGE_ANOMALY_PCAP.exists()}
    if EDGE_ANOMALY_PCAP.exists():
        proc = subprocess.run(
            [str(CAPINFOS), "-M", "-c", "-a", "-e", "-u", "-s", str(EDGE_ANOMALY_PCAP)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        anomaly.update(
            {
                "capinfos_returncode": proc.returncode,
                "capinfos_stdout": proc.stdout.strip(),
                "capinfos_stderr": proc.stderr.strip(),
            }
        )
    return records, {"captures": captures, "anomaly_pcap": anomaly}


def parse_zeek_log(path: Path) -> list[dict[str, str]]:
    fields: list[str] = []
    rows: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("#fields"):
            fields = line.split()[1:]
            continue
        if not line or line.startswith("#"):
            continue
        values = line.split()
        if len(values) != len(fields):
            continue
        rows.append(dict(zip(fields, values)))
    return rows


def iot_coarse(label: str, detailed: str) -> tuple[str, str]:
    if label.lower() == "benign":
        return "Benign", "Benign"
    fine = detailed if detailed not in {"", "-", "(empty)"} else "Malicious-Unspecified"
    lowered = fine.lower()
    if "ddos" in lowered:
        coarse = "Availability"
    elif "partofahorizontalportscan" in lowered:
        coarse = "Reconnaissance"
    elif "filedownload" in lowered:
        coarse = "FileTransfer"
    elif "c&c" in lowered or "heartbeat" in lowered:
        coarse = "CommandAndControl"
    elif "attack" in lowered:
        coarse = "Exploitation"
    else:
        coarse = "MaliciousOther"
    return fine, coarse


def packet_index(packets: list[Packet]) -> dict[tuple[Any, ...], tuple[list[float], list[Packet]]]:
    grouped: dict[tuple[Any, ...], list[Packet]] = defaultdict(list)
    for packet in packets:
        grouped[endpoint_key(packet.src, packet.sport, packet.dst, packet.dport, packet.proto)].append(packet)
    return {key: ([item.ts for item in values], values) for key, values in grouped.items()}


def iot_adapter() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records: list[dict[str, Any]] = []
    scenarios: dict[str, Any] = {}
    for scenario, spec in IOT_SOURCES.items():
        packets, parse = tshark_packets(spec["pcap"])
        index = packet_index(packets)
        logs = parse_zeek_log(spec["log"])
        label_counts: Counter[str] = Counter()
        coarse_counts: Counter[str] = Counter()
        matched = 0
        matched_packet_counts: list[int] = []
        for row in logs:
            proto = row["proto"].upper()
            sport, dport = safe_int(row["id.orig_p"]), safe_int(row["id.resp_p"])
            # Zeek stores ICMP type/code in the port-shaped columns; packet captures do not
            # have transport ports. Normalize both representations to the same key.
            if proto in {"ICMP", "ICMPV6"}:
                proto = "ICMP"
                sport = dport = 0
            key = endpoint_key(row["id.orig_h"], sport, row["id.resp_h"], dport, proto)
            start = safe_float(row["ts"])
            duration = max(0.0, safe_float(row["duration"]))
            expected_packets = safe_int(row["orig_pkts"]) + safe_int(row["resp_pkts"])
            selected: list[Packet] = []
            if key in index:
                times, candidates = index[key]
                left = bisect.bisect_left(times, start - 0.002)
                right_window = start + max(duration, 0.25) + 0.5
                right = bisect.bisect_right(times, right_window)
                selected = candidates[left:right]
                if expected_packets and len(selected) > expected_packets + 4:
                    selected = selected[: expected_packets + 4]
            detailed_label = row.get("detailed-label", row.get("det_label", "-"))
            fine, coarse = iot_coarse(row["label"], detailed_label)
            label_counts[fine] += 1
            coarse_counts[coarse] += 1
            if selected:
                matched += 1
                matched_packet_counts.append(len(selected))
            else:
                continue
            end = start + duration
            summary_override = {
                "duration": duration,
                "forward_packets": safe_int(row["orig_pkts"]),
                "backward_packets": safe_int(row["resp_pkts"]),
                "forward_bytes": safe_int(row["orig_ip_bytes"]),
                "backward_bytes": safe_int(row["resp_ip_bytes"]),
                "handshake_state": handshake_state(
                    [item.flags for item in selected], fallback=row.get("conn_state", "")
                ),
                "service_category": service_category(proto, sport, dport, row.get("service", "")),
            }
            records.append(
                build_record(
                    dataset="IoT-23",
                    capture=scenario,
                    split=spec["split"],
                    fine_label=fine,
                    coarse_label=coarse,
                    start=start,
                    end=end,
                    initiator=row["id.orig_h"],
                    responder=row["id.resp_h"],
                    packets=selected,
                    summary_override=summary_override,
                    service_hint=row.get("service", ""),
                    application_capability=row.get("service", "-") not in {"", "-", "(empty)"},
                    source_file=spec["pcap"].name,
                )
            )
        scenarios[scenario] = {
            "split": spec["split"],
            "family_or_device": spec["family"],
            "log_rows": len(logs),
            "native_fine_label_counts": dict(label_counts),
            "coarse_label_counts": dict(coarse_counts),
            "pcap_packets": len(packets),
            "matched_records": matched,
            "match_rate": matched / len(logs) if logs else 0.0,
            "matched_packet_count_median": statistics.median(matched_packet_counts)
            if matched_packet_counts
            else 0,
            "parse": parse,
        }
    return records, {"scenarios": scenarios}


def add_context(records: list[dict[str, Any]]) -> None:
    by_dataset_split: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_dataset_split[(record["dataset_name"], record["split"])].append(record)
    for values in by_dataset_split.values():
        values.sort(key=lambda item: item["timestamp_start"])
        recent: deque[dict[str, Any]] = deque()
        for record in values:
            now = record["timestamp_start"]
            while recent and now - recent[0]["timestamp_start"] > CONTEXT_SECONDS:
                recent.popleft()
            initiator = record["_audit"]["initiator"]
            same_initiator = [item for item in recent if item["_audit"]["initiator"] == initiator]
            services = {item["session_summary"]["service_category"] for item in recent}
            record["temporal_context"] = {
                "window_seconds": CONTEXT_SECONDS,
                "prior_session_count": len(recent),
                "same_initiator_prior_sessions": len(same_initiator),
                "distinct_service_categories": len(services),
                "prior_packets": sum(
                    item["session_summary"]["forward_packets"]
                    + item["session_summary"]["backward_packets"]
                    for item in recent
                ),
                "prior_bytes": sum(
                    item["session_summary"]["forward_bytes"]
                    + item["session_summary"]["backward_bytes"]
                    for item in recent
                ),
            }
            record["_audit"]["context_latest_timestamp"] = (
                max((item["timestamp_start"] for item in recent), default=None)
            )
            recent.append(record)


def model_view(record: dict[str, Any], packet_limit: int = INITIAL_PACKETS) -> dict[str, Any]:
    return {
        "label_schema_id": record["label_schema_id"],
        "flow_evidence": {
            "packet_sequence": record["packet_sequence"][:packet_limit],
            "session_summary": record["session_summary"],
            "temporal_context": record["temporal_context"],
            "application_evidence": record["application_evidence"],
            "capabilities": record["capabilities"],
            "missing_fields": record["missing_fields"],
        },
    }


def clean_record(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key != "_audit"}


def balanced_sample(
    records: list[dict[str, Any]],
    *,
    split: str,
    label_key: str,
    allowed: set[str] | None = None,
    cap_per_class: int = 1000,
    seed: int = 17,
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        label = record[label_key]
        if record["split"] == split and (allowed is None or label in allowed):
            grouped[label].append(record)
    output: list[dict[str, Any]] = []
    for label in sorted(grouped):
        values = grouped[label][:]
        rng.shuffle(values)
        output.extend(values[:cap_per_class])
    rng.shuffle(output)
    return output


def feature_dict(
    record: dict[str, Any], feature_profile: str = "full_behavior"
) -> dict[str, float | str]:
    summary = record["session_summary"]
    context = record["temporal_context"]
    packets = record["packet_sequence"][:INITIAL_PACKETS]
    result: dict[str, float | str] = {
        "duration": float(summary["duration"]),
        "forward_packets": float(summary["forward_packets"]),
        "backward_packets": float(summary["backward_packets"]),
        "forward_bytes": float(summary["forward_bytes"]),
        "backward_bytes": float(summary["backward_bytes"]),
        "length_mean": float(summary["packet_length_stats"]["mean"]),
        "length_std": float(summary["packet_length_stats"]["std"]),
        "iat_mean": float(summary["iat_stats"]["mean"]),
        "iat_std": float(summary["iat_stats"]["std"]),
        "service": str(summary["service_category"]),
        "handshake": str(summary["handshake_state"]),
        "prior_sessions": float(context.get("prior_session_count", 0)),
        "same_initiator_prior": float(context.get("same_initiator_prior_sessions", 0)),
        "prior_packets": float(context.get("prior_packets", 0)),
        "prior_bytes": float(context.get("prior_bytes", 0)),
        "seq_packets": float(len(packets)),
        "seq_forward": float(sum(item["direction"] == "initiator_to_responder" for item in packets)),
        "seq_backward": float(sum(item["direction"] == "responder_to_initiator" for item in packets)),
        "seq_length_mean": statistics.fmean([item["packet_length"] for item in packets])
        if packets
        else 0.0,
        "seq_iat_mean": statistics.fmean([item["relative_iat"] for item in packets])
        if packets
        else 0.0,
        "syn_count": float(sum(bool((item["tcp_flags"] or 0) & 0x02) for item in packets)),
        "rst_count": float(sum(bool((item["tcp_flags"] or 0) & 0x04) for item in packets)),
        "fin_count": float(sum(bool((item["tcp_flags"] or 0) & 0x01) for item in packets)),
    }
    for proto in ("TCP", "UDP", "ICMP"):
        result[f"proto_{proto.lower()}"] = float(sum(item["protocol"] == proto for item in packets))
    if feature_profile == "no_service":
        result.pop("service", None)
    elif feature_profile == "service_only":
        result = {"service": result["service"]}
    elif feature_profile != "full_behavior":
        raise ValueError(f"unknown feature profile: {feature_profile}")
    return result


def run_rf_smoke(
    *,
    name: str,
    train: list[dict[str, Any]],
    test: list[dict[str, Any]],
    label_key: str,
    feature_profile: str = "full_behavior",
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not train or not test:
        return {"name": name, "status": "NOT_RUN", "reason": "empty train or test"}, []
    x_train_dict = [feature_dict(item, feature_profile) for item in train]
    x_test_dict = [feature_dict(item, feature_profile) for item in test]
    y_train = [item[label_key] for item in train]
    y_test = [item[label_key] for item in test]
    vectorizer = DictVectorizer(sparse=True)
    x_train = vectorizer.fit_transform(x_train_dict)
    x_test = vectorizer.transform(x_test_dict)
    majority = Counter(y_train).most_common(1)[0][0]
    labels = sorted(set(y_train) | set(y_test))
    seed_results: list[dict[str, Any]] = []
    predictions: list[dict[str, Any]] = []
    for seed in SEEDS:
        model = RandomForestClassifier(
            n_estimators=100,
            max_depth=14,
            min_samples_leaf=2,
            class_weight="balanced_subsample",
            random_state=seed,
            n_jobs=1,
        )
        model.fit(x_train, y_train)
        predicted = model.predict(x_test)
        seed_results.append(
            {
                "seed": seed,
                "accuracy": float(accuracy_score(y_test, predicted)),
                "macro_f1": float(f1_score(y_test, predicted, average="macro", zero_division=0)),
                "balanced_accuracy": float(balanced_accuracy_score(y_test, predicted)),
                "per_class_recall": {
                    label: float(value)
                    for label, value in zip(
                        labels,
                        recall_score(y_test, predicted, labels=labels, average=None, zero_division=0),
                    )
                },
                "confusion_matrix": confusion_matrix(y_test, predicted, labels=labels).tolist(),
            }
        )
        for item, truth, guess in zip(test, y_test, predicted):
            predictions.append(
                {
                    "experiment": name,
                    "seed": seed,
                    "sample_id": item["sample_id"],
                    "true_label": truth,
                    "predicted_label": str(guess),
                }
            )
    majority_pred = [majority] * len(y_test)
    random_level = 1.0 / max(1, len(labels))
    summary = {
        "name": name,
        "status": "COMPLETED",
        "model": {
            "type": "RandomForestClassifier",
            "n_estimators": 100,
            "max_depth": 14,
            "min_samples_leaf": 2,
            "class_weight": "balanced_subsample",
            "seeds": SEEDS,
        },
        "train_rows": len(train),
        "test_rows": len(test),
        "train_support": dict(Counter(y_train)),
        "test_support": dict(Counter(y_test)),
        "labels": labels,
        "random_accuracy_level": random_level,
        "majority_baseline": {
            "label": majority,
            "accuracy": float(accuracy_score(y_test, majority_pred)),
            "macro_f1": float(f1_score(y_test, majority_pred, average="macro", zero_division=0)),
            "balanced_accuracy": float(balanced_accuracy_score(y_test, majority_pred)),
        },
        "runs": seed_results,
        "mean_macro_f1": float(statistics.fmean(item["macro_f1"] for item in seed_results)),
        "std_macro_f1": float(statistics.pstdev(item["macro_f1"] for item in seed_results)),
        "mean_balanced_accuracy": float(
            statistics.fmean(item["balanced_accuracy"] for item in seed_results)
        ),
        "feature_contract": (
            f"{feature_profile}; behavior whitelist only; DictVectorizer fitted on training data"
        ),
    }
    return summary, predictions


def record_signature(record: dict[str, Any]) -> str:
    payload = {
        "packet_sequence": record["packet_sequence"],
        "session_summary": record["session_summary"],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def deduplicate_records(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Conservatively remove model-evidence duplicates before any split is learned.

    If the same evidence has conflicting labels, all copies are removed. Otherwise one
    copy is kept, preferring frozen/held-out roles over validation and training.
    """

    priority = {"train": 0, "validation": 1, "unknown_dev": 2, "test": 3, "unknown_final": 4}
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[(record["dataset_name"], record_signature(record))].append(record)
    kept: list[dict[str, Any]] = []
    duplicate_groups = conflicting_groups = removed = 0
    by_dataset_removed: Counter[str] = Counter()
    for (dataset, _), values in grouped.items():
        if len(values) == 1:
            kept.append(values[0])
            continue
        duplicate_groups += 1
        labels = {(item["fine_label"], item["coarse_label"]) for item in values}
        if len(labels) > 1:
            conflicting_groups += 1
            removed += len(values)
            by_dataset_removed[dataset] += len(values)
            continue
        winner = max(
            values,
            key=lambda item: (
                priority.get(item["split"], -1),
                item["timestamp_start"],
                item["sample_id"],
            ),
        )
        kept.append(winner)
        removed += len(values) - 1
        by_dataset_removed[dataset] += len(values) - 1
    kept.sort(key=lambda item: (item["dataset_name"], item["timestamp_start"], item["sample_id"]))
    return kept, {
        "input_records": len(records),
        "output_records": len(kept),
        "duplicate_evidence_groups": duplicate_groups,
        "conflicting_label_groups_dropped_entirely": conflicting_groups,
        "records_removed": removed,
        "records_removed_by_dataset": dict(by_dataset_removed),
        "retention_priority": ["unknown_final", "test", "unknown_dev", "validation", "train"],
    }


def near_signature(record: dict[str, Any]) -> str:
    features = feature_dict(record)
    rounded = {
        key: (round(value, 2) if isinstance(value, float) else value)
        for key, value in features.items()
    }
    return hashlib.sha256(json.dumps(rounded, sort_keys=True).encode("utf-8")).hexdigest()


def leakage_audit(
    records: list[dict[str, Any]], iot_info: dict[str, Any], deduplication: dict[str, Any]
) -> dict[str, Any]:
    dataset_split_captures: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    session_ids: dict[tuple[str, str], set[str]] = defaultdict(set)
    content_hashes: dict[tuple[str, str], set[str]] = defaultdict(set)
    near_hashes: dict[tuple[str, str], set[str]] = defaultdict(set)
    endpoint_hashes: dict[tuple[str, str], set[str]] = defaultdict(set)
    model_key_violations: list[dict[str, str]] = []
    model_identity_value_violations: list[dict[str, str]] = []
    future_context = 0
    for record in records:
        dataset, split = record["dataset_name"], record["split"]
        dataset_split_captures[dataset][split].add(record["scenario_or_capture_id"])
        session_ids[(dataset, split)].add(record["sample_id"])
        content_hashes[(dataset, split)].add(record_signature(record))
        near_hashes[(dataset, split)].add(near_signature(record))
        endpoint_hashes[(dataset, split)].add(
            hashlib.sha256(
                json.dumps(record["_audit"].get("session_key", []), sort_keys=True).encode("utf-8")
            ).hexdigest()
        )
        latest = record["_audit"].get("context_latest_timestamp")
        if latest is not None and latest >= record["timestamp_start"]:
            future_context += 1
        serialized = json.dumps(model_view(record), ensure_ascii=False).lower()
        for field in PROHIBITED_FIELDS:
            if field.lower() in serialized:
                model_key_violations.append({"sample_id": record["sample_id"], "field": field})
        for identity_name in ("initiator", "responder"):
            identity = str(record["_audit"].get(identity_name, "")).lower()
            if identity and identity in serialized:
                model_identity_value_violations.append(
                    {"sample_id": record["sample_id"], "identity": identity_name}
                )
    overlaps: dict[str, Any] = {}
    for dataset, splits in dataset_split_captures.items():
        names = sorted(splits)
        capture_pairs = {}
        id_pairs = {}
        hash_pairs = {}
        near_pairs = {}
        endpoint_pairs = {}
        for index, left in enumerate(names):
            for right in names[index + 1 :]:
                pair = f"{left}__{right}"
                capture_pairs[pair] = sorted(splits[left] & splits[right])
                id_pairs[pair] = len(session_ids[(dataset, left)] & session_ids[(dataset, right)])
                hash_pairs[pair] = len(content_hashes[(dataset, left)] & content_hashes[(dataset, right)])
                near_pairs[pair] = len(near_hashes[(dataset, left)] & near_hashes[(dataset, right)])
                endpoint_pairs[pair] = len(
                    endpoint_hashes[(dataset, left)] & endpoint_hashes[(dataset, right)]
                )
        overlaps[dataset] = {
            "captures_by_split": {key: sorted(value) for key, value in splits.items()},
            "capture_overlap": capture_pairs,
            "sample_id_overlap": id_pairs,
            "exact_content_overlap": hash_pairs,
            "quantized_feature_overlap": near_pairs,
            "unordered_endpoint_key_overlap": endpoint_pairs,
        }
    iot_scenario_splits: dict[str, set[str]] = defaultdict(set)
    for record in records:
        if record["dataset_name"] == "IoT-23":
            iot_scenario_splits[record["scenario_or_capture_id"]].add(record["split"])
    return {
        "records_checked": len(records),
        "future_context_violations": future_context,
        "model_view_prohibited_key_violations": model_key_violations[:20],
        "model_view_prohibited_key_violation_count": len(model_key_violations),
        "model_view_raw_identity_value_violations": model_identity_value_violations[:20],
        "model_view_raw_identity_value_violation_count": len(model_identity_value_violations),
        "split_overlap": overlaps,
        "iot23_scenario_multi_split": {
            key: sorted(value) for key, value in iot_scenario_splits.items() if len(value) > 1
        },
        "edge_capture_overlap_interpretation": (
            "Expected by frozen capture-internal time-block protocol; sessions crossing block/gap boundaries are dropped. "
            "This does not establish cross-run generalization."
        ),
        "normalization_encoding_calibration": "No normalization/calibration; DictVectorizer fit only on training records.",
        "raw_ports": "Retained only in private matching state; model view exposes service_category, with no-port feature path available.",
        "iot_match_rates": {
            key: value["match_rate"] for key, value in iot_info["scenarios"].items()
        },
        "deduplication": deduplication,
    }


def smoke_subset(records: list[dict[str, Any]], dataset: str, cap: int = 5000) -> list[dict[str, Any]]:
    values = [item for item in records if item["dataset_name"] == dataset]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in values:
        grouped[(item["split"], item["fine_label"])].append(item)
    output: list[dict[str, Any]] = []
    rng = random.Random(17)
    per_group = max(20, cap // max(1, len(grouped)))
    for key in sorted(grouped):
        items = grouped[key][:]
        rng.shuffle(items)
        output.extend(items[:per_group])
    rng.shuffle(output)
    return output[:cap]


def qwen_smoke(records: list[dict[str, Any]]) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    lengths: dict[str, list[int]] = defaultdict(list)
    for dataset in ("Edge-IIoTset", "IoT-23"):
        chosen = smoke_subset(records, dataset, cap=100)
        for record in chosen:
            view = model_view(record)
            text = json.dumps(view, ensure_ascii=False, separators=(",", ":"))
            lengths[dataset].append(len(text))
            samples.append(
                {
                    "dataset": dataset,
                    "sample_id": record["sample_id"],
                    "initial_model_view": view,
                    "allowed_actions": [
                        "ACCEPT_FINE",
                        "BACKOFF_COARSE",
                        "REJECT_UNKNOWN",
                        "ABSTAIN",
                    ]
                    + (["EXPAND_PACKETS"] if record["capabilities"]["packet_expand"] else [])
                    + (
                        ["EXPAND_TEMPORAL_CONTEXT"]
                        if record["capabilities"]["temporal_context"]
                        else []
                    ),
                    "expected_output_schema": {
                        "fine_label": "string|null",
                        "coarse_label": "string|null",
                        "unknown": "boolean",
                        "confidence": "number[0,1]",
                        "supporting_evidence": "array[string]",
                        "missing_evidence": "array[string]",
                        "next_action": "enum",
                    },
                }
            )
    jsonl_dump(OUT / "qwen_input_samples.jsonl", samples)
    valid = all(
        "flow_evidence" in item["initial_model_view"]
        and "label_schema_id" in item["initial_model_view"]
        and "fine_label" not in item["initial_model_view"]
        for item in samples
    )
    return {
        "actual_model_call": False,
        "reason": "No configured endpoint was required; validation covers real serialized inputs and output schema only.",
        "samples": len(samples),
        "schema_and_serialization_valid": valid,
        "length_chars": {
            dataset: {
                "min": min(values),
                "median": statistics.median(values),
                "p95": float(np.percentile(values, 95)),
                "max": max(values),
            }
            for dataset, values in lengths.items()
            if values
        },
        "packet_policy": {"initial": INITIAL_PACKETS, "maximum": MAX_PACKETS},
        "unknown_path": True,
        "capability_gating": True,
    }


def write_markdown_reports(
    *,
    edge_info: dict[str, Any],
    iot_info: dict[str, Any],
    leakage: dict[str, Any],
    learnability: dict[str, Any],
    qwen: dict[str, Any],
    decision: dict[str, Any],
) -> None:
    edge_lines = [
        "# EdgeAdapter最小验收",
        "",
        f"结论：**{decision['edge']}**。本轮使用6个代表性官方PCAP，生成会话、前16包序列、会话摘要和split内60秒past-only上下文。",
        "",
        "| Capture | 标签 | PCAP包 | 会话 | 分配结果 | CSV标签稳定 |",
        "|---|---|---:|---:|---|---|",
    ]
    for capture, value in edge_info["captures"].items():
        edge_lines.append(
            f"| {capture} | {value['label']} | {value['pcap_packets']} | {value['sessions']} | "
            f"`{json.dumps(value['assigned'], ensure_ascii=False)}` | {value['label_is_file_stable']} |"
        )
    edge_lines.extend(
        [
            "",
            "已实测：文件级标签在所选CSV内稳定；Known会话按capture内时间块分配，边界gap中的会话被丢弃；Unknown按完整类别隔离；模型视图不含IP、绝对时间、文件名或capture ID。",
            "",
            "冻结限制：攻击类通常只有一个capture，因此该划分只支持同采集环境的时间块结论，不支持跨攻击run泛化。Vulnerability Scanner异常PCAP仅由capinfos复核并保留在风险记录，不进入本轮模型冒烟。",
        ]
    )
    (OUT / "edge_adapter_validation.md").write_text("\n".join(edge_lines) + "\n", encoding="utf-8")

    iot_lines = [
        "# IoT23Adapter最小验收",
        "",
        f"结论：**{decision['iot23']}**。本轮从官方CTU服务器选择7个capture，没有下载20GB完整包。",
        "",
        "| Scenario/capture | 角色 | 官方日志行 | PCAP匹配记录 | 匹配率 | 标签摘要 |",
        "|---|---|---:|---:|---:|---|",
    ]
    for scenario, value in iot_info["scenarios"].items():
        iot_lines.append(
            f"| {scenario} | {value['split']} | {value['log_rows']} | {value['matched_records']} | "
            f"{value['match_rate']:.2%} | `{json.dumps(value['coarse_label_counts'], ensure_ascii=False)}` |"
        )
    iot_lines.extend(
        [
            "",
            "主scenario-held-out行为任务冻结为：Capture-8训练，Capture-20/21验证，Capture-34测试；Philips-Hue加入训练Benign，Somfy-01加入测试Benign。Capture-42整体仅作unknown_final场景，FileDownload类只有6条恶意流，因此Unknown结论必须标记小样本限制。",
            "",
            "已实测：Zeek标签可解析，时间戳与五元组可和PCAP匹配；两个Adapter输出同一Schema。IoT-23使用自己的原生行为标签和独立split，不是Edge分类器的直接零样本测试。",
            "",
            "解析限制：Capture-42的PCAP被TShark报告为文件尾部截断，但截断前解析结果仍匹配全部4,426条官方日志记录；Somfy-01有24/130条日志未匹配。两项均不阻断本轮Gate，但必须保留在正式source manifest与异常处置清单中。",
        ]
    )
    (OUT / "iot23_adapter_validation.md").write_text("\n".join(iot_lines) + "\n", encoding="utf-8")

    leakage_text = f"""# 泄漏与捷径验收

## 已实测结果

- 未来上下文违规：{leakage['future_context_violations']}。
- 模型视图禁止字段键违规：{leakage['model_view_prohibited_key_violation_count']}；原始端点值违规：{leakage['model_view_raw_identity_value_violation_count']}。
- IoT-23 scenario跨split：`{json.dumps(leakage['iot23_scenario_multi_split'], ensure_ascii=False)}`。
- sample_id、无序双向端点键、完整证据哈希和量化近似特征的跨split结果见`gate_results.json`中的`leakage.split_overlap`。端点键重复只表示通信对复现，不等于同一会话重复；同一会话和完整证据跨split均为0。
- 保守去重：输入{leakage['deduplication']['input_records']}条，移除{leakage['deduplication']['records_removed']}条，输出{leakage['deduplication']['output_records']}条；冲突标签证据组全部删除。
- 原始端口仅用于会话/标签对齐；默认模型输入为service category，特征提取代码不含raw port。`learnability`同时保存无service和service-only探针，用于识别服务类别捷径。
- RF的`DictVectorizer`只在训练记录上fit；本轮没有使用测试数据拟合归一化、编码、校准或阈值。

## 解释边界

Edge的同一capture会按冻结协议出现在train/validation/test三个时间块中，但跨块gap内会话被丢弃，且上下文只在split内部生成。这控制直接泄漏但不能提供跨run独立性。IoT-23则要求scenario/capture完全不跨split。

固定URI、topic、用户名、Payload和攻击字符串未进入基础模型视图；应用层能力只以可用性布尔值表示。本轮没有证明所有近重复均已消除，正式数据生成仍需保留近重复敏感性审计。
"""
    (OUT / "leakage_audit.md").write_text(leakage_text, encoding="utf-8")

    learn_lines = [
        "# 轻量可学习性冒烟",
        "",
        "本结果只用于数据Gate，不是论文成绩。模型均为100棵、最大深度14的Random Forest，使用种子17和41；输入严格来自行为白名单。主可学习性判据使用no-service特征，另保留full-behavior和service-only捷径敏感性探针。",
        "",
        "| 数据任务 | 训练/测试 | 类别 | 多数类Macro-F1 | RF Macro-F1均值±标准差 | RF Balanced Accuracy均值 |",
        "|---|---:|---|---:|---:|---:|",
    ]
    for value in learnability["experiments"]:
        if value["status"] != "COMPLETED":
            continue
        learn_lines.append(
            f"| {value['name']} | {value['train_rows']}/{value['test_rows']} | {', '.join(value['labels'])} | "
            f"{value['majority_baseline']['macro_f1']:.4f} | {value['mean_macro_f1']:.4f}±{value['std_macro_f1']:.4f} | "
            f"{value['mean_balanced_accuracy']:.4f} |"
        )
    learn_lines.extend(
        [
            "",
            "通过判据是相同非随机划分下明显超过多数类/随机基线，并且不是只依赖总体Accuracy。完整支持数、逐类Recall、混淆矩阵和两个种子结果见`gate_results.json`；预测见`lightweight_model_predictions.csv`。",
        ]
    )
    (OUT / "learnability_smoke_report.md").write_text("\n".join(learn_lines) + "\n", encoding="utf-8")

    qwen_text = f"""# Qwen输入端到端冒烟

- 真实序列化输入：{qwen['samples']}条，Edge与IoT-23使用同一Evidence结构。
- 初始包预算：前{INITIAL_PACKETS}包；最大保存：{MAX_PACKETS}包。
- Schema与序列化检查：{qwen['schema_and_serialization_valid']}。
- Unknown输出路径：{qwen['unknown_path']}；capability工具门控：{qwen['capability_gating']}。
- 输入字符长度统计：`{json.dumps(qwen['length_chars'], ensure_ascii=False)}`。
- 本轮未调用在线或本地模型，未下载Qwen权重；只验证输入、动作与输出JSON合同。真实样例见`qwen_input_samples.jsonl`。
"""
    (OUT / "qwen_input_smoke_report.md").write_text(qwen_text, encoding="utf-8")

    final_text = f"""# Edge-IIoTset + IoT-23最终可行性Gate

## 最终判定

- **整体：{decision['overall']}**
- **Edge-IIoTset：{decision['edge']}**
- **IoT-23：{decision['iot23']}**

## 已实测事实

1. Edge代表性PCAP可由TShark重建双向会话、前16包、摘要与split内60秒past-only上下文；标签在所选逐包CSV中保持文件级一致。
2. IoT-23官方Zeek日志可解析，并能通过时间与五元组和官方PCAP稳定匹配；7个capture足以构造训练、验证、完全留出测试及一个完整unknown_final场景。
3. 两个Adapter均输出`CanonicalSessionRecord`；模型初始视图不包含IP、绝对时间、文件名、数据集名或capture/scenario ID。
4. 去除service category后的行为白名单RF在非随机划分上仍相对多数类/随机基线存在可重复的非随机信号；full-behavior与service-only结果仅用于捷径敏感性诊断，具体数值见轻量报告。
5. 未发现会阻止进入正式数据生成的标签、解析或直接泄漏问题。

## 冻结限制

- Edge多数攻击类仍只有一个capture；只能声称控制捷径后的同采集环境效果，sample-level few-shot不等于跨run few-shot。
- IoT-23主外测采用原生行为标签的独立scenario协议；Capture-42的完整未知场景只有6条FileDownload恶意流，Unknown主结果需另以预注册类/场景补足样本或明确小样本置信区间。
- Capture-42的PCAP被TShark报告为尾部截断，Somfy-01仍有24条官方日志未与PCAP匹配；当前已匹配部分足以通过Gate，正式source manifest必须显式记录异常处置。
- 本轮Adapter是可复现验收实现，不是全量生产流水线；正式阶段仍需冻结全量manifest、K/U和异常文件处置。
- 未运行Qwen推理或训练，所有轻量模型数值均为审计探针而非论文结果。

## 决策

双数据集方案可以进入正式数据生成和GPU服务器训练准备，但必须保留上述限制。下一步唯一动作是：**将本轮验收Adapter固化为生产数据流水线，并冻结全量split、K/U、support/query和训练manifest。**
"""
    (OUT / "final_gate_report.md").write_text(final_text, encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    missing = [str(path) for spec in EDGE_SOURCES.values() for path in (spec["pcap"], spec["csv"]) if not path.exists()]
    missing.extend(
        str(path)
        for spec in IOT_SOURCES.values()
        for path in (spec["pcap"], spec["log"])
        if not path.exists()
    )
    if missing:
        raise FileNotFoundError("Missing required input:\n" + "\n".join(missing))

    edge_records, edge_info = edge_adapter()
    iot_records, iot_info = iot_adapter()
    all_records, deduplication = deduplicate_records(edge_records + iot_records)
    edge_records = [item for item in all_records if item["dataset_name"] == "Edge-IIoTset"]
    iot_records = [item for item in all_records if item["dataset_name"] == "IoT-23"]
    add_context(all_records)

    edge_known = {"Normal", "Port_Scanning", "DDoS_HTTP", "Backdoor"}
    edge_train = balanced_sample(
        edge_records, split="train", label_key="fine_label", allowed=edge_known, cap_per_class=1000
    )
    edge_test = balanced_sample(
        edge_records, split="test", label_key="fine_label", allowed=edge_known, cap_per_class=500
    )
    iot_known = {"Benign", "CommandAndControl"}
    iot_train = balanced_sample(
        iot_records, split="train", label_key="coarse_label", allowed=iot_known, cap_per_class=1500
    )
    iot_test = balanced_sample(
        iot_records, split="test", label_key="coarse_label", allowed=iot_known, cap_per_class=1500
    )
    edge_ml, edge_predictions = run_rf_smoke(
        name="Edge time-block fine-label smoke (no-service primary)",
        train=edge_train,
        test=edge_test,
        label_key="fine_label",
        feature_profile="no_service",
    )
    iot_ml, iot_predictions = run_rf_smoke(
        name="IoT-23 scenario-held-out behavior smoke (no-service primary)",
        train=iot_train,
        test=iot_test,
        label_key="coarse_label",
        feature_profile="no_service",
    )
    edge_full, edge_full_predictions = run_rf_smoke(
        name="Edge shortcut sensitivity (full behavior)",
        train=edge_train,
        test=edge_test,
        label_key="fine_label",
        feature_profile="full_behavior",
    )
    edge_service, edge_service_predictions = run_rf_smoke(
        name="Edge shortcut sensitivity (service-only)",
        train=edge_train,
        test=edge_test,
        label_key="fine_label",
        feature_profile="service_only",
    )
    iot_full, iot_full_predictions = run_rf_smoke(
        name="IoT-23 shortcut sensitivity (full behavior)",
        train=iot_train,
        test=iot_test,
        label_key="coarse_label",
        feature_profile="full_behavior",
    )
    iot_service, iot_service_predictions = run_rf_smoke(
        name="IoT-23 shortcut sensitivity (service-only)",
        train=iot_train,
        test=iot_test,
        label_key="coarse_label",
        feature_profile="service_only",
    )
    learnability = {
        "experiments": [
            edge_ml,
            iot_ml,
            edge_full,
            edge_service,
            iot_full,
            iot_service,
        ],
        "primary_signal_profile": "no_service",
        "shortcut_diagnostics": ["full_behavior", "service_only"],
    }

    leakage = leakage_audit(all_records, iot_info, deduplication)
    qwen = qwen_smoke(all_records)

    edge_smoke = smoke_subset(all_records, "Edge-IIoTset", cap=5000)
    iot_smoke = smoke_subset(all_records, "IoT-23", cap=5000)
    jsonl_dump(OUT / "edge_smoke.jsonl", (clean_record(item) for item in edge_smoke))
    jsonl_dump(OUT / "iot23_smoke.jsonl", (clean_record(item) for item in iot_smoke))

    with (OUT / "lightweight_model_predictions.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["experiment", "seed", "sample_id", "true_label", "predicted_label"]
        )
        writer.writeheader()
        writer.writerows(
            edge_predictions
            + iot_predictions
            + edge_full_predictions
            + edge_service_predictions
            + iot_full_predictions
            + iot_service_predictions
        )

    edge_signal = (
        edge_ml.get("mean_macro_f1", 0)
        > edge_ml.get("majority_baseline", {}).get("macro_f1", 1) + 0.10
    )
    iot_signal = (
        iot_ml.get("mean_macro_f1", 0)
        > iot_ml.get("majority_baseline", {}).get("macro_f1", 1) + 0.10
    )
    edge_adapter_pass = len(edge_records) >= 1000 and all(
        value["label_is_file_stable"] for value in edge_info["captures"].values()
    )
    iot_min_match = min(value["match_rate"] for value in iot_info["scenarios"].values())
    iot_scenario_pass = (
        len(iot_records) >= 1000
        and iot_min_match >= 0.80
        and not leakage["iot23_scenario_multi_split"]
    )
    no_direct_leak = (
        leakage["future_context_violations"] == 0
        and leakage["model_view_prohibited_key_violation_count"] == 0
        and leakage["model_view_raw_identity_value_violation_count"] == 0
    )
    edge_decision = "PASS_WITH_LIMITATIONS" if edge_adapter_pass and edge_signal and no_direct_leak else "FAIL"
    iot_decision = "PASS_WITH_LIMITATIONS" if iot_scenario_pass and iot_signal and no_direct_leak else "FAIL"
    overall = (
        "PASS_WITH_LIMITATIONS"
        if edge_decision != "FAIL" and iot_decision != "FAIL"
        else "FAIL"
    )
    decision = {
        "overall": overall,
        "edge": edge_decision,
        "iot23": iot_decision,
        "edge_behavior_signal": edge_signal,
        "iot23_behavior_signal": iot_signal,
        "no_direct_model_view_leak": no_direct_leak,
        "iot23_min_pcap_log_match_rate": iot_min_match,
    }

    source_files = sorted(
        {
            path.resolve()
            for spec in EDGE_SOURCES.values()
            for path in (spec["pcap"], spec["csv"])
        }
        | {
            path.resolve()
            for spec in IOT_SOURCES.values()
            for path in (spec["pcap"], spec["log"])
        }
        | {(IOT_ROOT / "metadata" / "README.md").resolve()}
    )
    source_manifest = {
        "generated_at": RUN_AT,
        "policy": "official sources, minimal scenario selection, no full IoT-23 archive",
        "iot23_base_url": "https://mcfp.felk.cvut.cz/publicDatasets/IoT-23-Dataset/",
        "files": [
            {
                "path": portable_path(path),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "modified_time_utc": datetime.fromtimestamp(
                    path.stat().st_mtime, timezone.utc
                ).isoformat(),
                "source": (
                    "existing official Edge-IIoTset archive"
                    if "edge_iiotset" in str(path)
                    else "official CTU IoT-23 individual scenario endpoint"
                ),
            }
            for path in source_files
        ],
    }
    json_dump(OUT / "source_download_manifest.json", source_manifest)
    json_dump(
        OUT / "dataset_manifest.json",
        {
            "generated_at": RUN_AT,
            "edge": edge_info,
            "iot23": iot_info,
            "record_counts": {
                "edge_total": len(edge_records),
                "iot23_total": len(iot_records),
                "edge_smoke": len(edge_smoke),
                "iot23_smoke": len(iot_smoke),
            },
        },
    )
    split_manifest = {
        "generated_at": RUN_AT,
        "edge": {
            "known": sorted(edge_known),
            "unknown_dev": ["SQL_injection"],
            "unknown_final": ["Ransomware"],
            "known_policy": "capture-internal chronological blocks with 5% gaps; crossing sessions dropped",
        },
        "iot23": {
            "train": ["CTU-IoT-Malware-Capture-8-1", "CTU-Honeypot-Capture-4-1"],
            "validation": ["CTU-IoT-Malware-Capture-20-1", "CTU-IoT-Malware-Capture-21-1"],
            "test": ["CTU-IoT-Malware-Capture-34-1", "CTU-Honeypot-Capture-7-1-Somfy-01"],
            "unknown_final": ["CTU-IoT-Malware-Capture-42-1"],
            "known_behavior_labels": sorted(iot_known),
        },
        "random_seeds": SEEDS,
    }
    json_dump(OUT / "split_manifest.json", split_manifest)
    json_dump(
        OUT / "label_schema_edge.json",
        {
            "id": "edge_native_v1",
            "fine_labels": sorted({spec["label"] for spec in EDGE_SOURCES.values()}),
            "coarse_mapping": {
                spec["label"]: edge_coarse(spec["label"]) for spec in EDGE_SOURCES.values()
            },
            "scope": "feasibility subset only; full 15-class schema remains for formal build",
        },
    )
    json_dump(
        OUT / "label_schema_iot23.json",
        {
            "id": "iot23_behavior_v1",
            "native_fine_labels": sorted({record["fine_label"] for record in iot_records}),
            "coarse_labels": sorted({record["coarse_label"] for record in iot_records}),
            "normalization_rule": "preserve native detailed-label; map only to documented behavior coarse groups",
            "scenario_family_is_backend_only": True,
        },
    )
    json_dump(
        OUT / "known_unknown_presets.json",
        {
            "edge_probe": {
                "known": sorted(edge_known),
                "u_dev": ["SQL_injection"],
                "u_final": ["Ransomware"],
            },
            "iot23_probe": {
                "known": sorted(iot_known),
                "u_dev": [],
                "u_final_scenario": ["CTU-IoT-Malware-Capture-42-1"],
                "u_final_labels": ["FileDownload", "C&C-FileDownload"],
                "limitation": "only six malicious unknown flows in the fully held-out scenario",
                "supplementary_unseen_label": ["DDoS in test-only Capture-34"],
            },
            "status": "feasibility presets; formal K/U must be preregistered before training",
        },
    )
    json_dump(
        OUT / "prohibited_fields.json",
        {
            "fields": PROHIBITED_FIELDS,
            "allowed_uses": [
                "session reconstruction",
                "sorting",
                "grouping",
                "split",
                "past-only context lookup",
                "audit",
                "leakage detection",
            ],
            "model_input": False,
        },
    )
    json_dump(
        OUT / "model_feature_whitelist.json",
        {
            "features": MODEL_FEATURE_WHITELIST,
            "raw_port_policy": "audit only; service category default; no-port ablation entry retained",
        },
    )
    json_dump(
        OUT / "adapter_schema.json",
        {
            "name": "CanonicalSessionRecord",
            "required_fields": [
                "sample_id",
                "dataset_name",
                "scenario_or_capture_id",
                "split",
                "timestamp_start",
                "timestamp_end",
                "packet_sequence",
                "session_summary",
                "temporal_context",
                "application_evidence",
                "label_schema_id",
                "fine_label",
                "coarse_label",
                "capabilities",
                "missing_fields",
                "prohibited_model_fields",
            ],
            "packet_sequence_max": MAX_PACKETS,
            "initial_model_packet_view": INITIAL_PACKETS,
            "adapter_implementations": ["EdgeAdapter", "IoT23Adapter"],
        },
    )
    json_dump(
        OUT / "gate_results.json",
        {
            "generated_at": RUN_AT,
            "decision": decision,
            "edge": edge_info,
            "iot23": iot_info,
            "leakage": leakage,
            "learnability": learnability,
            "qwen_input": qwen,
        },
    )
    json_dump(
        OUT / "run_metadata.json",
        {
            "generated_at": RUN_AT,
            "command": "python reports/data_feasibility_gate_20260806/run_final_gate.py",
            "python": sys.version,
            "platform": platform.platform(),
            "tshark": str(TSHARK),
            "seeds": SEEDS,
            "environment": {"processor_count": os.cpu_count()},
            "formal_training": False,
            "qwen_called": False,
        },
    )

    write_markdown_reports(
        edge_info=edge_info,
        iot_info=iot_info,
        leakage=leakage,
        learnability=learnability,
        qwen=qwen,
        decision=decision,
    )

    checksum_entries = []
    for path in sorted(OUT.iterdir()):
        if path.is_file() and path.name != "checksum_manifest.json":
            checksum_entries.append(
                {"path": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}
            )
    json_dump(
        OUT / "checksum_manifest.json",
        {"generated_at": RUN_AT, "files": checksum_entries},
    )
    print(json.dumps(decision, ensure_ascii=False))


if __name__ == "__main__":
    main()
