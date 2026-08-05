from __future__ import annotations

import bisect
import csv
import hashlib
import ipaddress
import json
import math
import re
import socket
import statistics
import struct
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split


ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data" / "external" / "edge_iiotset" / "official_subset"
OUT = Path(__file__).resolve().parent
RESULT_JSON = OUT / "probe_results.json"

PAIR_NAMES = {
    "Normal_Heart_Rate": ("Heart_Rate.csv", "Heart_Rate.pcap", "Normal"),
    "Scanning_Port": ("Port_Scanning_attack.csv", "Port Scanning attack.pcap", "Port_Scanning"),
    "Injection_SQL": ("SQL_injection_attack.csv", "SQL injection attack.pcap", "SQL_injection"),
    "MITM": ("MITM_attack.csv", "MITM%20(ARP%20spoofing%20+%20DNS)%20Attack.pcap", "MITM"),
    "Malware_Backdoor": ("Backdoor_attack.csv", "Backdoor_attack.pcap", "Backdoor"),
    "Malware_Ransomware": ("Ransomware_attack.csv", "Ransomware attack.pcap", "Ransomware"),
    "DDoS_HTTP": ("DDoS_HTTP_Flood_attack.csv", "DDoS HTTP Flood Attacks.pcap", "DDoS_HTTP"),
}

COARSE = {
    "DDoS_HTTP": "DoS_DDoS",
    "DDoS_ICMP": "DoS_DDoS",
    "DDoS_TCP": "DoS_DDoS",
    "DDoS_UDP": "DoS_DDoS",
    "Fingerprinting": "Information_Gathering",
    "Port_Scanning": "Information_Gathering",
    "Vulnerability_scanner": "Information_Gathering",
    "MITM": "MITM",
    "SQL_injection": "Injection",
    "XSS": "Injection",
    "Backdoor": "Malware",
    "Password": "Malware",
    "Ransomware": "Malware",
    "Uploading": "Malware",
    "Normal": "Normal",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def quantiles(values: Iterable[float]) -> dict[str, float | None]:
    xs = np.asarray(list(values), dtype=float)
    if not len(xs):
        return {"min": None, "p25": None, "median": None, "p75": None, "p95": None, "max": None}
    return {
        "min": float(np.min(xs)),
        "p25": float(np.percentile(xs, 25)),
        "median": float(np.median(xs)),
        "p75": float(np.percentile(xs, 75)),
        "p95": float(np.percentile(xs, 95)),
        "max": float(np.max(xs)),
    }


def nonzero(value: Any) -> bool:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False
    text = str(value).strip()
    return text not in {"", "0", "0.0", "nan", "None"}


def parse_port(value: Any) -> int | None:
    if not nonzero(value):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


TIME_RE = re.compile(r"(?P<h>\d{1,2}):(?P<m>\d{2}):(?P<s>\d{2}(?:\.\d+)?)")


def csv_seconds_of_day(value: Any) -> float | None:
    match = TIME_RE.search(str(value))
    if not match:
        return None
    return int(match["h"]) * 3600 + int(match["m"]) * 60 + float(match["s"])


@dataclass
class Packet:
    ts: float
    length: int
    src: str | None
    dst: str | None
    proto: str
    sport: int | None = None
    dport: int | None = None
    tcp_flags: int | None = None
    payload_len: int | None = None


def pcap_packets(path: Path) -> Iterable[Packet]:
    with path.open("rb") as handle:
        header = handle.read(24)
        if len(header) != 24:
            raise ValueError("truncated pcap global header")
        magic = header[:4]
        formats = {
            b"\xd4\xc3\xb2\xa1": ("<", 1_000_000),
            b"\xa1\xb2\xc3\xd4": (">", 1_000_000),
            b"\x4d\x3c\xb2\xa1": ("<", 1_000_000_000),
            b"\xa1\xb2\x3c\x4d": (">", 1_000_000_000),
        }
        if magic not in formats:
            raise ValueError(f"unsupported pcap magic {magic.hex()}")
        endian, divisor = formats[magic]
        network = struct.unpack(endian + "I", header[20:24])[0]
        if network != 1:
            raise ValueError(f"unsupported link type {network}; expected Ethernet")
        ph = struct.Struct(endian + "IIII")
        while True:
            raw = handle.read(16)
            if not raw:
                break
            if len(raw) != 16:
                raise ValueError("truncated pcap packet header")
            ts_sec, ts_frac, incl_len, orig_len = ph.unpack(raw)
            data = handle.read(incl_len)
            if len(data) != incl_len:
                raise ValueError("truncated pcap packet data")
            ts = ts_sec + ts_frac / divisor
            yield parse_ethernet(ts, orig_len, data)


def parse_ethernet(ts: float, orig_len: int, data: bytes) -> Packet:
    if len(data) < 14:
        return Packet(ts, orig_len, None, None, "TRUNCATED")
    eth_type = struct.unpack("!H", data[12:14])[0]
    offset = 14
    while eth_type in (0x8100, 0x88A8) and len(data) >= offset + 4:
        eth_type = struct.unpack("!H", data[offset + 2 : offset + 4])[0]
        offset += 4
    if eth_type == 0x0800 and len(data) >= offset + 20:
        ihl = (data[offset] & 0x0F) * 4
        if ihl < 20 or len(data) < offset + ihl:
            return Packet(ts, orig_len, None, None, "IPv4_TRUNCATED")
        total_len = struct.unpack("!H", data[offset + 2 : offset + 4])[0]
        proto_num = data[offset + 9]
        src = socket.inet_ntoa(data[offset + 12 : offset + 16])
        dst = socket.inet_ntoa(data[offset + 16 : offset + 20])
        return parse_transport(ts, orig_len, src, dst, proto_num, data, offset + ihl, total_len - ihl)
    if eth_type == 0x86DD and len(data) >= offset + 40:
        proto_num = data[offset + 6]
        src = str(ipaddress.IPv6Address(data[offset + 8 : offset + 24]))
        dst = str(ipaddress.IPv6Address(data[offset + 24 : offset + 40]))
        payload_len = struct.unpack("!H", data[offset + 4 : offset + 6])[0]
        return parse_transport(ts, orig_len, src, dst, proto_num, data, offset + 40, payload_len)
    if eth_type == 0x0806 and len(data) >= offset + 28:
        src = socket.inet_ntoa(data[offset + 14 : offset + 18])
        dst = socket.inet_ntoa(data[offset + 24 : offset + 28])
        return Packet(ts, orig_len, src, dst, "ARP")
    return Packet(ts, orig_len, None, None, f"ETH_0x{eth_type:04x}")


def parse_transport(
    ts: float,
    orig_len: int,
    src: str,
    dst: str,
    proto_num: int,
    data: bytes,
    offset: int,
    ip_payload_len: int,
) -> Packet:
    if proto_num == 6 and len(data) >= offset + 20:
        sport, dport = struct.unpack("!HH", data[offset : offset + 4])
        data_offset = (data[offset + 12] >> 4) * 4
        flags = data[offset + 13]
        return Packet(ts, orig_len, src, dst, "TCP", sport, dport, flags, max(0, ip_payload_len - data_offset))
    if proto_num == 17 and len(data) >= offset + 8:
        sport, dport, udp_len = struct.unpack("!HHH", data[offset : offset + 6])
        return Packet(ts, orig_len, src, dst, "UDP", sport, dport, None, max(0, udp_len - 8))
    names = {1: "ICMP", 2: "IGMP", 58: "ICMPv6"}
    return Packet(ts, orig_len, src, dst, names.get(proto_num, f"IP_{proto_num}"), payload_len=max(0, ip_payload_len))


@dataclass
class Session:
    capture: str
    key: tuple[Any, ...]
    start: float
    end: float
    initiator: str | None
    target: str | None
    target_port: int | None
    packets: int = 0
    bytes: int = 0
    directions: set[int] = field(default_factory=set)
    syn: int = 0
    synack: int = 0
    rst: int = 0
    fin: int = 0
    first_packets: list[dict[str, Any]] = field(default_factory=list)

    @property
    def bidirectional(self) -> bool:
        return len(self.directions) > 1

    @property
    def incomplete_handshake(self) -> bool:
        return self.syn > 0 and self.synack == 0


def packet_key(packet: Packet) -> tuple[tuple[Any, ...], int]:
    a = (packet.src or "?", packet.sport or 0)
    b = (packet.dst or "?", packet.dport or 0)
    if a <= b:
        return (packet.proto, a, b), 1
    return (packet.proto, b, a), -1


def sessionize(capture: str, packets: list[Packet], idle: float) -> list[Session]:
    active: dict[tuple[Any, ...], Session] = {}
    completed: list[Session] = []
    for packet in packets:
        key, direction = packet_key(packet)
        session = active.get(key)
        if session is None or packet.ts - session.end > idle:
            if session is not None:
                completed.append(session)
            session = Session(capture, key, packet.ts, packet.ts, packet.src, packet.dst, packet.dport)
            active[key] = session
        iat = max(0.0, packet.ts - session.end) if session.packets else 0.0
        session.end = packet.ts
        session.packets += 1
        session.bytes += packet.length
        session.directions.add(direction)
        flags = packet.tcp_flags or 0
        session.fin += int(bool(flags & 0x01))
        session.syn += int(bool(flags & 0x02) and not bool(flags & 0x10))
        session.rst += int(bool(flags & 0x04))
        session.synack += int(bool(flags & 0x02) and bool(flags & 0x10))
        if len(session.first_packets) < 32:
            session.first_packets.append(
                {
                    "d": direction,
                    "l": packet.length,
                    "iat_ms": round(iat * 1000, 3),
                    "p": packet.proto,
                    "f": packet.tcp_flags,
                }
            )
    completed.extend(active.values())
    return sorted(completed, key=lambda x: (x.start, x.key))


def csv_profile(path: Path) -> dict[str, Any]:
    labels: Counter[str] = Counter()
    binary: Counter[str] = Counter()
    rows = 0
    sample_frames: list[pd.DataFrame] = []
    use = [
        "frame.time",
        "ip.src_host",
        "ip.dst_host",
        "tcp.srcport",
        "tcp.dstport",
        "udp.port",
        "tcp.flags",
        "tcp.len",
        "tcp.payload",
        "http.file_data",
        "http.request.full_uri",
        "mqtt.msg",
        "Attack_label",
        "Attack_type",
    ]
    for chunk in pd.read_csv(path, usecols=use, chunksize=50_000, low_memory=False):
        rows += len(chunk)
        labels.update(chunk["Attack_type"].astype(str))
        binary.update(chunk["Attack_label"].astype(str))
        if sum(len(x) for x in sample_frames) < 50_000:
            sample_frames.append(chunk.head(50_000 - sum(len(x) for x in sample_frames)))
    sample = pd.concat(sample_frames, ignore_index=True) if sample_frames else pd.DataFrame(columns=use)
    identities = sample[["ip.src_host", "ip.dst_host"]].astype(str)
    return {
        "rows": rows,
        "columns": len(pd.read_csv(path, nrows=0).columns),
        "attack_type_counts": dict(labels),
        "attack_label_counts": dict(binary),
        "sample_exact_duplicate_rows": int(sample.duplicated().sum()),
        "sample_rows": len(sample),
        "timestamp_parse_rate": float(sample["frame.time"].map(csv_seconds_of_day).notna().mean()) if len(sample) else 0.0,
        "unique_src_sample": int(identities["ip.src_host"].nunique()),
        "unique_dst_sample": int(identities["ip.dst_host"].nunique()),
        "observable_rates_sample": {
            column: float(sample[column].map(nonzero).mean()) if len(sample) else 0.0
            for column in [
                "tcp.srcport",
                "tcp.dstport",
                "udp.port",
                "tcp.flags",
                "tcp.len",
                "tcp.payload",
                "http.file_data",
                "http.request.full_uri",
                "mqtt.msg",
            ]
        },
    }


def sequential_alignment(path: Path, packets: list[Packet], limit: int = 5000) -> dict[str, Any]:
    use = ["frame.time", "ip.src_host", "ip.dst_host", "tcp.srcport", "tcp.dstport", "udp.port"]
    frame = pd.read_csv(path, usecols=use, nrows=limit, low_memory=False)
    n = min(len(frame), len(packets), limit)
    address_checked = address_match = port_checked = port_match = 0
    deltas: list[float] = []
    for idx in range(n):
        row = frame.iloc[idx]
        packet = packets[idx]
        src = str(row["ip.src_host"]).strip()
        dst = str(row["ip.dst_host"]).strip()
        if src not in {"", "0", "0.0", "nan"} and dst not in {"", "0", "0.0", "nan"} and packet.src and packet.dst:
            address_checked += 1
            address_match += int(src == packet.src and dst == packet.dst)
        sport = parse_port(row["tcp.srcport"])
        dport = parse_port(row["tcp.dstport"])
        if sport is None and dport is None:
            udp = parse_port(row["udp.port"])
            if udp is not None:
                sport = dport = udp
        if sport is not None and packet.sport is not None:
            port_checked += 1
            port_match += int(sport == packet.sport and (dport is None or dport == packet.dport))
        sod = csv_seconds_of_day(row["frame.time"])
        if sod is not None:
            deltas.append(((packet.ts % 86400) - sod + 43200) % 86400 - 43200)
    median_delta = float(statistics.median(deltas)) if deltas else None
    residuals = [abs(x - median_delta) for x in deltas] if deltas and median_delta is not None else []
    return {
        "sequential_rows_checked": n,
        "address_checked": address_checked,
        "address_match_rate": address_match / address_checked if address_checked else None,
        "port_checked": port_checked,
        "port_match_rate": port_match / port_checked if port_checked else None,
        "timestamp_rows_checked": len(deltas),
        "median_clock_offset_seconds": median_delta,
        "timestamp_residual_p95_seconds": float(np.percentile(residuals, 95)) if residuals else None,
    }


def summarize_sessions(capture: str, label: str, sessions: list[Session], idle: int) -> dict[str, Any]:
    packets = [s.packets for s in sessions]
    durations = [s.end - s.start for s in sessions]
    return {
        "capture": capture,
        "label": label,
        "idle_seconds": idle,
        "sessions": len(sessions),
        "packets": int(sum(packets)),
        "packet_count": quantiles(packets),
        "duration_seconds": quantiles(durations),
        "bidirectional_ratio": float(np.mean([s.bidirectional for s in sessions])) if sessions else 0.0,
        "coverage_ge_8": float(np.mean([s.packets >= 8 for s in sessions])) if sessions else 0.0,
        "coverage_ge_16": float(np.mean([s.packets >= 16 for s in sessions])) if sessions else 0.0,
        "coverage_ge_32": float(np.mean([s.packets >= 32 for s in sessions])) if sessions else 0.0,
        "incomplete_handshake_ratio": float(np.mean([s.incomplete_handshake for s in sessions])) if sessions else 0.0,
        "missing_initiator_ratio": float(np.mean([not s.initiator or s.initiator == "?" for s in sessions])) if sessions else 0.0,
        "missing_target_port_ratio": float(np.mean([s.target_port is None for s in sessions])) if sessions else 0.0,
    }


def temporal_summary(sessions: list[Session], window: int) -> dict[str, Any]:
    ordered = sorted(sessions, key=lambda s: s.start)
    q: deque[Session] = deque()
    src_counts: Counter[str] = Counter()
    pair_counts: Counter[tuple[str, str]] = Counter()
    dest_counts: Counter[str] = Counter()
    port_counts: Counter[int] = Counter()
    target_sources: dict[str, Counter[str]] = defaultdict(Counter)
    src_times: dict[str, deque[float]] = defaultdict(deque)
    total_packets = total_bytes = incomplete = 0
    last_src_time: dict[str, float] = {}
    metrics: list[dict[str, float]] = []

    def add(s: Session, sign: int) -> None:
        nonlocal total_packets, total_bytes, incomplete
        src, dst = s.initiator or "?", s.target or "?"
        src_counts[src] += sign
        pair_counts[(src, dst)] += sign
        dest_counts[dst] += sign
        if s.target_port is not None:
            port_counts[s.target_port] += sign
        target_sources[dst][src] += sign
        if sign > 0:
            src_times[src].append(s.start)
        elif src_times[src]:
            if src_times[src][0] == s.start:
                src_times[src].popleft()
            else:
                try:
                    src_times[src].remove(s.start)
                except ValueError:
                    pass
            if not src_times[src]:
                del src_times[src]
        total_packets += sign * s.packets
        total_bytes += sign * s.bytes
        incomplete += sign * int(s.incomplete_handshake)
        for counter in (src_counts, pair_counts, dest_counts, port_counts):
            for key in [key for key, value in counter.items() if value <= 0]:
                del counter[key]
        for dst_key in [dst]:
            for src_key in [key for key, value in target_sources[dst_key].items() if value <= 0]:
                del target_sources[dst_key][src_key]
            if not target_sources[dst_key]:
                del target_sources[dst_key]

    for session in ordered:
        while q and session.start - q[0].start > window:
            add(q.popleft(), -1)
        src, dst = session.initiator or "?", session.target or "?"
        recent = list(src_times.get(src, ()))[-6:]
        recent_iats = [b - a for a, b in zip(recent, recent[1:])]
        mean_iat = statistics.mean(recent_iats) if recent_iats else 0.0
        periodicity_cv = (
            statistics.pstdev(recent_iats) / mean_iat
            if len(recent_iats) >= 2 and mean_iat > 0
            else math.nan
        )
        metrics.append(
            {
                "prior_sessions": len(q),
                "same_source_sessions": src_counts.get(src, 0),
                "distinct_destinations": len(dest_counts),
                "distinct_ports": len(port_counts),
                "same_target_distinct_sources": len(target_sources.get(dst, {})),
                "repeated_source_target": pair_counts.get((src, dst), 0),
                "prior_packets": total_packets,
                "prior_bytes": total_bytes,
                "incomplete_ratio": incomplete / len(q) if q else 0.0,
                "same_source_interval": session.start - last_src_time[src] if src in last_src_time else math.nan,
                "periodicity_cv": periodicity_cv,
            }
        )
        last_src_time[src] = session.start
        q.append(session)
        add(session, 1)
    return {
        "window_seconds": window,
        "anchors": len(metrics),
        "anchors_with_history_ratio": float(np.mean([m["prior_sessions"] > 0 for m in metrics])) if metrics else 0.0,
        **{
            key: quantiles(m[key] for m in metrics if not math.isnan(m[key]))
            for key in [
                "prior_sessions",
                "same_source_sessions",
                "distinct_destinations",
                "distinct_ports",
                "same_target_distinct_sources",
                "repeated_source_target",
                "prior_packets",
                "prior_bytes",
                "incomplete_ratio",
                "same_source_interval",
                "periodicity_cv",
            ]
        },
    }


def compact_card(session: Session, n: int, add_context: bool = False, add_app: bool = False, rag_chars: int = 0) -> str:
    card: dict[str, Any] = {
        "packets": session.first_packets[:n],
        "summary": {
            "duration_ms": round((session.end - session.start) * 1000, 3),
            "packets": session.packets,
            "bytes": session.bytes,
            "bidirectional": session.bidirectional,
            "syn": session.syn,
            "synack": session.synack,
            "rst": session.rst,
            "fin": session.fin,
        },
        "missing": [],
    }
    if add_context:
        card["past_context"] = {
            "window_s": 60,
            "same_source_sessions": 12,
            "distinct_destinations": 5,
            "distinct_ports": 7,
            "same_target_distinct_sources": 3,
            "repeated_source_target": 2,
            "incomplete_handshake_ratio": 0.25,
        }
    if add_app:
        card["application_evidence"] = {
            "http_method": "GET",
            "uri_shape": "/redacted/path?key=<value>",
            "mqtt_topic": "redacted/topic",
            "payload_excerpt_hex": "00" * 48,
        }
    if rag_chars:
        card["rag"] = "K" * rag_chars
    return json.dumps(card, ensure_ascii=False, separators=(",", ":"))


def llm_lengths(sessions: list[Session]) -> dict[str, Any]:
    usable = [s for s in sessions if s.first_packets]
    if len(usable) > 300:
        indices = np.linspace(0, len(usable) - 1, 300, dtype=int)
        usable = [usable[i] for i in indices]
    result: dict[str, Any] = {"sessions_sampled": len(usable), "tokenizer": "not installed; chars/4 to chars/3 estimate"}
    for n in (8, 16, 32):
        chars = [len(compact_card(s, n)) for s in usable]
        result[f"packets_{n}"] = {
            "chars": quantiles(chars),
            "approx_tokens_median_range": [round(np.median(chars) / 4), round(np.median(chars) / 3)] if chars else [0, 0],
        }
    for name, kwargs in {
        "n16_plus_context": {"n": 16, "add_context": True},
        "n16_context_application": {"n": 16, "add_context": True, "add_app": True},
        "n16_context_application_rag": {"n": 16, "add_context": True, "add_app": True, "rag_chars": 1800},
    }.items():
        chars = [len(compact_card(s, **kwargs)) for s in usable]
        result[name] = {
            "chars": quantiles(chars),
            "approx_tokens_median_range": [round(np.median(chars) / 4), round(np.median(chars) / 3)] if chars else [0, 0],
        }
    return result


def leakage_diagnostic(ml_path: Path) -> dict[str, Any]:
    frame = pd.read_csv(ml_path, low_memory=False)
    full_rows = len(frame)
    full_duplicates = int(frame.duplicated().sum())
    frame = frame.drop_duplicates().reset_index(drop=True)
    if len(frame) > 80_000:
        sampled, _ = train_test_split(frame, train_size=80_000, stratify=frame["Attack_type"], random_state=20260805)
        frame = sampled.reset_index(drop=True)
    y = frame["Attack_type"].astype(str)

    def time_value(value: Any) -> float:
        parsed = csv_seconds_of_day(value)
        return parsed if parsed is not None else -1.0

    shortcut = pd.DataFrame(index=frame.index)
    shortcut["src"] = pd.factorize(frame["ip.src_host"].astype(str), sort=True)[0]
    shortcut["dst"] = pd.factorize(frame["ip.dst_host"].astype(str), sort=True)[0]
    shortcut["time"] = frame["frame.time"].map(time_value)
    for column in ["tcp.srcport", "tcp.dstport", "udp.port", "http.tls_port"]:
        shortcut[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    for column in ["http.request.method", "http.request.full_uri", "mqtt.topic", "mqtt.protoname", "dns.qry.name"]:
        shortcut[column] = pd.factorize(frame[column].astype(str), sort=True)[0]
    shortcut["tcp_payload_chars"] = frame["tcp.payload"].astype(str).str.len()
    shortcut["http_data_chars"] = frame["http.file_data"].astype(str).str.len()

    excluded_tokens = (
        "time",
        "host",
        "proto_ipv4",
        "port",
        "checksum",
        "ack_raw",
        "payload",
        "file_data",
        "full_uri",
        "uri.query",
        "referer",
        "options",
        "seq",
        "stream",
        "transmit_timestamp",
        "retransmit_request_in",
        "msg",
        "topic",
        "protoname",
        "trans_id",
        "Attack_",
    )
    numeric = frame.select_dtypes(include=[np.number]).columns
    allowed_cols = [c for c in numeric if not any(token in c for token in excluded_tokens)]
    allowed = frame[allowed_cols].apply(pd.to_numeric, errors="coerce").fillna(0)
    with_ports = allowed.copy()
    for column in ["tcp.srcport", "tcp.dstport", "udp.port", "http.tls_port"]:
        with_ports[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)

    def run_model(x: pd.DataFrame, split: str) -> dict[str, Any]:
        if split == "random":
            train_idx, test_idx = train_test_split(
                np.arange(len(x)), test_size=0.25, stratify=y, random_state=20260805
            )
        else:
            src = frame["ip.src_host"].astype(str)
            dst = frame["ip.dst_host"].astype(str)
            groups = np.where(src <= dst, src + "|" + dst, dst + "|" + src)
            splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=20260805)
            train_idx, test_idx = next(splitter.split(x, y, groups))
        model = RandomForestClassifier(
            n_estimators=60,
            max_depth=18,
            min_samples_leaf=2,
            class_weight="balanced_subsample",
            n_jobs=1,
            random_state=20260805,
        )
        model.fit(x.iloc[train_idx], y.iloc[train_idx])
        pred = model.predict(x.iloc[test_idx])
        return {
            "train_rows": len(train_idx),
            "test_rows": len(test_idx),
            "test_classes": sorted(set(y.iloc[test_idx])),
            "accuracy": float(accuracy_score(y.iloc[test_idx], pred)),
            "macro_f1": float(f1_score(y.iloc[test_idx], pred, average="macro", zero_division=0)),
        }

    return {
        "full_rows": full_rows,
        "exact_duplicates": full_duplicates,
        "duplicate_rate": full_duplicates / full_rows,
        "diagnostic_sample_rows_after_dedup": len(frame),
        "allowed_numeric_columns": allowed_cols,
        "shortcut_only_random": run_model(shortcut, "random"),
        "behavior_plus_ports_random": run_model(with_ports, "random"),
        "behavior_no_ports_random": run_model(allowed, "random"),
        "behavior_no_ports_endpoint_group_split": run_model(allowed, "group"),
        "warning": "Diagnostic only. The ML CSV has no capture/run identifier, so endpoint-group split is not a substitute for capture/time-aware evaluation.",
    }


def write_csvs(result: dict[str, Any]) -> None:
    with (OUT / "class_counts.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["label", "coarse_label", "ml_rows", "role_note"])
        writer.writeheader()
        for label, count in sorted(result["ml_dataset"]["attack_type_counts"].items()):
            writer.writerow(
                {
                    "label": label,
                    "coarse_label": COARSE.get(label, "UNCONFIRMED"),
                    "ml_rows": count,
                    "role_note": "local ML selected CSV; not raw packet/session count",
                }
            )
    fields = [
        "capture",
        "label",
        "idle_seconds",
        "sessions",
        "packets",
        "packet_min",
        "packet_median",
        "packet_p95",
        "packet_max",
        "bidirectional_ratio",
        "coverage_ge_8",
        "coverage_ge_16",
        "coverage_ge_32",
        "incomplete_handshake_ratio",
        "missing_initiator_ratio",
        "missing_target_port_ratio",
    ]
    with (OUT / "session_statistics.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in result["session_statistics"]:
            writer.writerow(
                {
                    **{key: row[key] for key in fields if key in row and not key.startswith("packet_")},
                    "packet_min": row["packet_count"]["min"],
                    "packet_median": row["packet_count"]["median"],
                    "packet_p95": row["packet_count"]["p95"],
                    "packet_max": row["packet_count"]["max"],
                }
            )


def main() -> None:
    result: dict[str, Any] = {
        "scope": "official author-Kaggle subset plus local ML selected CSV",
        "data_dir": str(DATA),
        "files": {},
        "pairs": {},
        "session_statistics": [],
        "temporal": {},
    }
    for path in sorted(DATA.iterdir()):
        if path.is_file():
            result["files"][path.name] = {"bytes": path.stat().st_size, "sha256": sha256(path)}

    ml = pd.read_csv(DATA / "ML-EdgeIIoT-dataset.csv", low_memory=False)
    result["ml_dataset"] = {
        "rows": len(ml),
        "columns": list(ml.columns),
        "column_count": len(ml.columns),
        "attack_label_counts": {str(k): int(v) for k, v in ml["Attack_label"].value_counts(dropna=False).items()},
        "attack_type_counts": {str(k): int(v) for k, v in ml["Attack_type"].value_counts(dropna=False).items()},
        "exact_duplicates": int(ml.duplicated().sum()),
    }
    del ml

    all_sessions_60: list[Session] = []
    for pair_name, (csv_name, pcap_name, expected_label) in PAIR_NAMES.items():
        csv_path, pcap_path = DATA / csv_name, DATA / pcap_name
        profile = csv_profile(csv_path)
        packets = list(pcap_packets(pcap_path))
        protocol_counts = Counter(packet.proto for packet in packets)
        alignment = sequential_alignment(csv_path, packets)
        pair = {
            "expected_label": expected_label,
            "csv_file": csv_name,
            "pcap_file": pcap_name,
            "csv": profile,
            "pcap_packets": len(packets),
            "pcap_protocol_counts": dict(protocol_counts),
            "pcap_first_ts": packets[0].ts if packets else None,
            "pcap_last_ts": packets[-1].ts if packets else None,
            "pcap_chronological": all(a.ts <= b.ts for a, b in zip(packets, packets[1:])),
            "packet_count_difference": profile["rows"] - len(packets),
            "alignment": alignment,
        }
        result["pairs"][pair_name] = pair
        for idle in (30, 60):
            sessions = sessionize(pair_name, packets, idle)
            result["session_statistics"].append(summarize_sessions(pair_name, expected_label, sessions, idle))
            if idle == 60:
                all_sessions_60.extend(sessions)
                result["temporal"][pair_name] = {
                    "30s": temporal_summary(sessions, 30),
                    "60s": temporal_summary(sessions, 60),
                }

    result["llm_input"] = llm_lengths(all_sessions_60)
    result["leakage"] = leakage_diagnostic(DATA / "ML-EdgeIIoT-dataset.csv")
    counts = result["ml_dataset"]["attack_type_counts"]
    result["ku_candidates"] = {
        "near": {
            "u_dev": ["Fingerprinting", "XSS"],
            "u_final": ["DDoS_HTTP", "Port_Scanning", "SQL_injection", "Ransomware"],
        },
        "far": {
            "u_dev": ["Backdoor", "Uploading"],
            "u_final": ["MITM", "SQL_injection", "XSS", "Ransomware"],
        },
        "mixed": {
            "u_dev": ["Fingerprinting", "Backdoor"],
            "u_final": ["DDoS_HTTP", "MITM", "XSS", "Ransomware"],
        },
        "all_classes_ge_10_ml_rows": all(count >= 10 for label, count in counts.items() if label != "Normal"),
        "limitation": "ML rows support sample-level 1/5/10-shot. Independent run/capture query separation is not established by the selected CSV or one-PCAP-per-attack layout.",
    }
    attack_labels = sorted(label for label in counts if label != "Normal")
    for spec in result["ku_candidates"].values():
        if isinstance(spec, dict) and "u_dev" in spec:
            spec["k_known"] = sorted(set(attack_labels) - set(spec["u_dev"]) - set(spec["u_final"]))
            spec["counts"] = {label: counts[label] for label in spec["u_dev"] + spec["u_final"] + spec["k_known"]}

    RESULT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    write_csvs(result)
    print(json.dumps({"result": str(RESULT_JSON), "pairs": len(result["pairs"]), "sessions_rows": len(result["session_statistics"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
