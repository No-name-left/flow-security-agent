from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path


REPORT = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data" / "external" / "edge_iiotset" / "extracted"


def load_probe_module():
    path = REPORT / "run_minimal_probe.py"
    spec = importlib.util.spec_from_file_location("edge_probe", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            h.update(block)
    return h.hexdigest()


def count_lines(path: Path) -> int:
    count = 0
    last = b""
    with path.open("rb") as stream:
        while block := stream.read(16 * 1024 * 1024):
            count += block.count(b"\n")
            last = block[-1:]
    return max(0, count + int(last not in {b"", b"\n"}) - 1)


def label_for(path: Path) -> str:
    rel = path.relative_to(DATA).as_posix()
    if "/Normal traffic/" in f"/{rel}":
        return "Normal"
    name = path.stem.lower()
    rules = [
        ("backdoor", "Backdoor"), ("ddos_http", "DDoS_HTTP"),
        ("ddos http", "DDoS_HTTP"), ("ddos_icmp", "DDoS_ICMP"),
        ("ddos icmp", "DDoS_ICMP"), ("ddos_tcp", "DDoS_TCP"),
        ("ddos tcp", "DDoS_TCP"), ("ddos_udp", "DDoS_UDP"),
        ("ddos udp", "DDoS_UDP"), ("mitm", "MITM"),
        ("fingerprinting", "Fingerprinting"), ("password", "Password"),
        ("port_scanning", "Port_Scanning"), ("port scanning", "Port_Scanning"),
        ("ransomware", "Ransomware"), ("sql_injection", "SQL_injection"),
        ("sql injection", "SQL_injection"), ("uploading", "Uploading"),
        ("vulnerability", "Vulnerability_scanner"), ("xss", "XSS"),
    ]
    for needle, label in rules:
        if needle in name:
            return label
    return "N/A"


def category_for(path: Path) -> str:
    rel = path.relative_to(DATA).as_posix()
    if "Attack traffic/" in rel:
        return "raw_attack"
    if "Normal traffic/" in rel:
        return "raw_normal"
    if "Selected dataset for ML and DL/" in rel:
        return "selected_ml_dl"
    return "documentation"


def session_counts(path: Path, probe) -> dict:
    active = {30: {}, 60: {}}
    sessions = Counter()
    packets = 0
    nonmonotonic = 0
    last_capture_ts = None
    first_ts = last_ts = None
    protocols = Counter()
    parse_error = None
    try:
        for packet in probe.pcap_packets(path):
            packets += 1
            protocols[packet.proto] += 1
            first_ts = packet.ts if first_ts is None else min(first_ts, packet.ts)
            last_ts = packet.ts if last_ts is None else max(last_ts, packet.ts)
            if last_capture_ts is not None and packet.ts < last_capture_ts:
                nonmonotonic += 1
            last_capture_ts = packet.ts
            key, _ = probe.packet_key(packet)
            for idle in (30, 60):
                prior = active[idle].get(key)
                if prior is None or packet.ts - prior > idle:
                    sessions[idle] += 1
                active[idle][key] = max(packet.ts, prior) if prior is not None else packet.ts
    except (EOFError, ValueError) as exc:
        parse_error = f"{type(exc).__name__}: {exc}"
    return {
        "packets": packets,
        "sessions_30s": sessions[30],
        "sessions_60s": sessions[60],
        "nonmonotonic_packets": nonmonotonic,
        "first_ts": first_ts,
        "last_ts": last_ts,
        "protocols": dict(protocols),
        "complete": parse_error is None,
        "parse_error": parse_error,
    }


def main() -> None:
    probe = load_probe_module()
    files = sorted(p for p in DATA.rglob("*") if p.is_file())
    inventory = []
    raw_csv_rows = Counter()
    pcap_by_label = Counter()
    sess30_by_label = Counter()
    sess60_by_label = Counter()
    pcap_details = {}
    for index, path in enumerate(files, 1):
        rel = path.relative_to(DATA).as_posix()
        label = label_for(path)
        row = {
            "official_path": rel,
            "category": category_for(path),
            "format": path.suffix.lower().lstrip("."),
            "label_or_source": label,
            "local_status": "verified_extracted",
            "bytes": path.stat().st_size,
            "sha256": digest(path),
        }
        inventory.append(row)
        print(f"[{index}/{len(files)}] {rel}", flush=True)
        if path.suffix.lower() == ".csv" and row["category"].startswith("raw_"):
            raw_csv_rows[label] += count_lines(path)
        if path.suffix.lower() == ".pcap":
            detail = session_counts(path, probe)
            detail.update({"label": label, "path": rel})
            pcap_details[rel] = detail
            pcap_by_label[label] += detail["packets"]
            sess30_by_label[label] += detail["sessions_30s"]
            sess60_by_label[label] += detail["sessions_60s"]
    with (REPORT / "file_inventory.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(inventory[0]))
        writer.writeheader()
        writer.writerows(inventory)
    result = {
        "files": inventory,
        "raw_csv_rows_by_label": dict(raw_csv_rows),
        "pcap_packets_by_label": dict(pcap_by_label),
        "sessions_30s_by_label": dict(sess30_by_label),
        "sessions_60s_by_label": dict(sess60_by_label),
        "pcap_details": pcap_details,
    }
    (REPORT / "full_inventory_probe.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
