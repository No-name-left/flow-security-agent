from __future__ import annotations

import bisect
import hashlib
import os
import subprocess
import tempfile
from abc import ABC, abstractmethod
from collections import Counter, OrderedDict, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from flowsec.production.core import (
    canonical_endpoint_identity,
    canonical_endpoint_key,
    choose_gap_seconds,
    chronological_split,
    combine_hashes,
    first_value,
    hash_identity,
    parse_flags,
    safe_float,
    safe_int,
    service_category,
    sha256_file,
)
from flowsec.production.label_provenance import assign_session_label
from flowsec.production.schema import (
    Packet,
    SessionAccumulator,
    canonical_json,
    content_hash,
    initial_model_view,
    stable_sample_id,
)
from flowsec.production.storage import ProductionCatalog


@dataclass(slots=True)
class AdapterResult:
    dataset: str
    capture_id: str
    source_hashes: dict[str, str]
    source_verified: bool
    records: int
    retained_candidates: int
    quarantined: int
    parse: dict[str, Any]
    label_counts: dict[str, int]
    coarse_counts: dict[str, int]
    split_counts: dict[str, int]
    duration_statistics: dict[str, Any]
    anomaly_ids: list[str]
    match: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "capture_id": self.capture_id,
            "source_hashes": self.source_hashes,
            "source_verified": self.source_verified,
            "records": self.records,
            "retained_candidates": self.retained_candidates,
            "quarantined": self.quarantined,
            "parse": self.parse,
            "label_counts": self.label_counts,
            "coarse_counts": self.coarse_counts,
            "split_counts": self.split_counts,
            "duration_statistics": self.duration_statistics,
            "anomaly_ids": self.anomaly_ids,
            "match": self.match,
        }


class ProductionAdapter(ABC):
    def __init__(
        self,
        *,
        catalog: ProductionCatalog,
        dataset_root: Path,
        config: dict[str, Any],
        processing: dict[str, Any],
        tshark_bin: str,
        mode: str,
        sample_sessions: int,
    ) -> None:
        self.catalog = catalog
        self.dataset_root = dataset_root
        self.config = config
        self.processing = processing
        self.tshark_bin = tshark_bin
        self.mode = mode
        self.sample_sessions = sample_sessions

    @abstractmethod
    def process_capture(self, spec: dict[str, Any]) -> AdapterResult:
        raise NotImplementedError


def _tshark_command(tshark_bin: str, path: Path) -> tuple[list[str], list[str]]:
    fields = [
        "frame.number",
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
    command = [
        tshark_bin,
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
    for field in fields:
        command.extend(["-e", field])
    return command, fields


def _packet_from_fields(parts: list[str]) -> Packet | None:
    frame_number = safe_int(first_value(parts[0]), -1)
    timestamp = safe_float(first_value(parts[1]), -1.0)
    src4, src6 = first_value(parts[3]), first_value(parts[4])
    dst4, dst6 = first_value(parts[5]), first_value(parts[6])
    src, dst = src4 or src6, dst4 or dst6
    if frame_number < 0 or timestamp < 0 or not src or not dst:
        return None
    l3 = "IPv4" if src4 else "IPv6"
    ip_protocol = safe_int(first_value(parts[7]) or first_value(parts[8]))
    tcp_s, tcp_d = safe_int(first_value(parts[9])), safe_int(first_value(parts[10]))
    udp_s, udp_d = safe_int(first_value(parts[11])), safe_int(first_value(parts[12]))
    if tcp_s or tcp_d or ip_protocol == 6:
        l4, sport, dport = "TCP", tcp_s, tcp_d
    elif udp_s or udp_d or ip_protocol == 17:
        l4, sport, dport = "UDP", udp_s, udp_d
    elif ip_protocol in {1, 58}:
        l4, sport, dport = "ICMP", 0, 0
    else:
        l4, sport, dport = f"IP_{ip_protocol}" if ip_protocol else "IP_OTHER", 0, 0
    return Packet(
        frame_number=frame_number,
        timestamp=timestamp,
        packet_length=safe_int(first_value(parts[2])),
        src=src,
        dst=dst,
        l3_protocol=l3,
        l4_protocol=l4,
        sport=sport,
        dport=dport,
        tcp_flags=parse_flags(parts[13]),
    )


def iter_tshark_packets(tshark_bin: str, path: Path) -> tuple[Iterator[Packet], dict[str, Any]]:
    command, fields = _tshark_command(tshark_bin, path)
    state: dict[str, Any] = {
        "command": command,
        "parsed_ip_packets": 0,
        "skipped_non_ip_or_unparseable": 0,
        "returncode": None,
        "stderr": "",
    }

    def iterator() -> Iterator[Packet]:
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
            for line in process.stdout:
                parts = line.rstrip("\r\n").split("\t")
                if len(parts) < len(fields):
                    parts.extend([""] * (len(fields) - len(parts)))
                packet = _packet_from_fields(parts)
                if packet is None:
                    state["skipped_non_ip_or_unparseable"] += 1
                    continue
                state["parsed_ip_packets"] += 1
                yield packet
            process.stdout.close()
            state["returncode"] = process.wait()
            stderr_handle.seek(0)
            state["stderr"] = stderr_handle.read()[-8000:].strip()

    return iterator(), state


def _quantize(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 2)
    if isinstance(value, list):
        return [_quantize(item) for item in value]
    if isinstance(value, dict):
        return {key: _quantize(item) for key, item in value.items()}
    return value


def _catalog_record(
    *,
    dataset: str,
    dataset_version: str,
    label_schema_id: str,
    capture_id: str,
    source_hash: str,
    source_file: str,
    source_verified: bool,
    fine_label: str,
    coarse_label: str,
    base_split: str,
    session: SessionAccumulator,
    deterministic_ordinal: int,
    anomaly_ids: list[str],
    service_hint: str = "",
    summary_override: dict[str, Any] | None = None,
    application_capability: bool = False,
    original_label: str = "",
    exclusion_reason: str = "",
) -> dict[str, Any]:
    service, service_source = service_category(
        session.l4_protocol,
        session.initiator_port,
        session.responder_port,
        service_hint,
    )
    summary = session.summary(service, service_source)
    if summary_override:
        summary.update(summary_override)
    capabilities = ["temporal_context", "relation_context", "service_diagnostic"]
    if session.packet_count > 8:
        capabilities.append("packet_expand_9_16")
    if application_capability:
        capabilities.append("application_evidence")
    missing = ["sanitized_payload"]
    if not application_capability:
        missing.append("application_evidence")
    identity = canonical_endpoint_identity(
        session.l3_protocol,
        session.l4_protocol,
        session.initiator_ip,
        session.initiator_port,
        session.responder_ip,
        session.responder_port,
    )
    sample_id = stable_sample_id(
        dataset_version=dataset_version,
        source_content_hash=source_hash,
        canonical_session_identity=identity,
        start_microseconds=round(session.start * 1_000_000),
        deterministic_ordinal=deterministic_ordinal,
    )
    view = initial_model_view(
        label_schema_id=label_schema_id,
        packets=session.first_packets,
        summary=summary,
        capabilities=capabilities,
        missing_fields=missing,
        include_service=False,
    )
    endpoint_salt = content_hash({"dataset_version": dataset_version, "purpose": "backend_index"})
    src_hash = hash_identity(
        [session.initiator_ip, session.initiator_port, session.l4_protocol], endpoint_salt
    )
    dst_hash = hash_identity(
        [session.responder_ip, session.responder_port, session.l4_protocol], endpoint_salt
    )
    pair_hash = hash_identity(sorted([src_hash, dst_hash]), endpoint_salt)
    exact = content_hash(
        {
            "source_hash": source_hash,
            "identity": identity,
            "start_us": round(session.start * 1_000_000),
            "end_us": round(session.end * 1_000_000),
            "first_frame": session.first_frame_number,
            "last_frame": session.last_frame_number,
        }
    )
    reverse = content_hash(
        {
            "source_hash": source_hash,
            "pair_hash": pair_hash,
            "start_us": round(session.start * 1_000_000),
            "end_us": round(session.end * 1_000_000),
            "packet_lengths": [item["packet_length"] for item in session.first_packets],
        }
    )
    return {
        "sample_id": sample_id,
        "dataset": dataset,
        "dataset_version": dataset_version,
        "capture_id": capture_id,
        "source_hash": source_hash,
        "source_file": source_file,
        "timestamp_start": session.start,
        "timestamp_end": session.end,
        "raw_initiator_ip": session.initiator_ip,
        "raw_responder_ip": session.responder_ip,
        "raw_initiator_port": session.initiator_port,
        "raw_responder_port": session.responder_port,
        "l3_protocol": session.l3_protocol,
        "l4_protocol": session.l4_protocol,
        "first_frame": session.first_frame_number,
        "last_frame": session.last_frame_number,
        "fine_label": fine_label,
        "coarse_label": coarse_label,
        "base_split": base_split,
        "packet_sequence_json": canonical_json(session.first_packets),
        "session_summary_json": canonical_json(summary),
        "capabilities_json": canonical_json(sorted(capabilities)),
        "missing_fields_json": canonical_json(sorted(missing)),
        "anomaly_ids_json": canonical_json(sorted(anomaly_ids)),
        "original_label": original_label or fine_label,
        "evidence_signature": content_hash(view),
        "exact_signature": exact,
        "reverse_signature": reverse,
        "near_signature": content_hash(_quantize(view)),
        "source_identity_hash": src_hash,
        "destination_identity_hash": dst_hash,
        "communication_pair_hash": pair_hash,
        "source_verified": int(source_verified),
        "retained": 0 if exclusion_reason else 1,
        "exclusion_reason": exclusion_reason,
    }


class EdgeAdapter(ProductionAdapter):
    def process_capture(self, spec: dict[str, Any]) -> AdapterResult:
        dataset = str(self.config["dataset_name"])
        capture_id = str(spec["id"])
        pcap = self.dataset_root / spec["pcap"]
        label_csv = self.dataset_root / spec["csv"]
        if not pcap.is_file() or not label_csv.is_file():
            raise FileNotFoundError(f"missing Edge source for {capture_id}: {pcap} / {label_csv}")
        pcap_hash = str(spec.get("_pcap_sha256") or sha256_file(pcap))
        csv_hash = str(spec.get("_csv_sha256") or sha256_file(label_csv))
        source_hash = combine_hashes([pcap_hash, csv_hash])
        expected_label = str(spec["fine_label"])
        provenance = spec.get("_label_provenance")
        label_decision = assign_session_label(
            expected_label=expected_label,
            capture_provenance=provenance,
            direct_labels=(),
            session_capture_id=capture_id,
        )
        if label_decision["quarantined"]:
            raise ValueError(
                f"PROVENANCE_CAPTURE_LABEL_FAIL for {capture_id}: "
                f"{label_decision['reason']}"
            )
        source_verified = bool(
            provenance
            and provenance.get("pcap_sha256") == pcap_hash
            and provenance.get("companion_csv_sha256") == csv_hash
        )
        if not source_verified:
            raise ValueError(f"PROVENANCE_CAPTURE_LABEL_FAIL for {capture_id}: hash mismatch")
        anomaly_ids = [str(spec["anomaly"])] if spec.get("anomaly") else []
        self.catalog.delete_capture(dataset, capture_id)
        packets, parse_state = iter_tshark_packets(self.tshark_bin, pcap)
        active: OrderedDict[tuple[Any, ...], SessionAccumulator] = OrderedDict()
        durations: list[float] = []
        rows: list[dict[str, Any]] = []
        record_count = 0
        timeout = float(self.processing["session_timeout_seconds"])
        fine = str(label_decision["assigned_label"])
        coarse = str(self.config["coarse_mapping"][fine])

        def emit(session: SessionAccumulator) -> None:
            nonlocal record_count
            durations.append(max(0.0, session.end - session.start))
            rows.append(
                _catalog_record(
                    dataset=dataset,
                    dataset_version=str(self.config["dataset_version"]),
                    label_schema_id=str(self.config["label_schema_id"]),
                    capture_id=capture_id,
                    source_hash=source_hash,
                    source_file=pcap.name,
                    source_verified=source_verified,
                    fine_label=fine,
                    coarse_label=coarse,
                    base_split="unassigned",
                    session=session,
                    deterministic_ordinal=session.first_frame_number,
                    anomaly_ids=anomaly_ids,
                )
            )
            record_count += 1
            if len(rows) >= 5000:
                self.catalog.insert_records(rows)
                rows.clear()

        for packet in packets:
            while active:
                oldest_key = next(iter(active))
                oldest = active[oldest_key]
                if packet.timestamp - oldest.end <= timeout:
                    break
                active.popitem(last=False)
                emit(oldest)
                if self.mode == "sample" and record_count >= self.sample_sessions:
                    break
            if self.mode == "sample" and record_count >= self.sample_sessions:
                break
            key = canonical_endpoint_key(packet)
            session = active.pop(key, None)
            if session is None or packet.timestamp - session.end > timeout:
                if session is not None:
                    emit(session)
                session = SessionAccumulator(
                    canonical_key=key,
                    initiator_ip=packet.src,
                    responder_ip=packet.dst,
                    initiator_port=packet.sport,
                    responder_port=packet.dport,
                    l3_protocol=packet.l3_protocol,
                    l4_protocol=packet.l4_protocol,
                    start=packet.timestamp,
                    end=packet.timestamp,
                    first_frame_number=packet.frame_number,
                    last_frame_number=packet.frame_number,
                )
            session.add(packet, int(self.processing["packet_store_limit"]))
            active[key] = session
        if not (self.mode == "sample" and record_count >= self.sample_sessions):
            for session in active.values():
                emit(session)
        if rows:
            self.catalog.insert_records(rows)

        returncode = parse_state["returncode"]
        accepted_partial = bool(anomaly_ids and parse_state["parsed_ip_packets"] > 0)
        if returncode not in {0, None} and not accepted_partial:
            raise RuntimeError(
                f"tshark failed for {capture_id} with {returncode}: {parse_state['stderr']}"
            )
        if parse_state["skipped_non_ip_or_unparseable"]:
            reason = "non_ip_or_unparseable_packet"
            repro = content_hash([dataset, capture_id, source_hash, reason])
            self.catalog.insert_quarantine(
                reproducibility_id=repro,
                dataset=dataset,
                capture_id=capture_id,
                source_hash=source_hash,
                reason=reason,
                severity="INFO",
                count=int(parse_state["skipped_non_ip_or_unparseable"]),
                details={"tshark_returncode": returncode},
            )
        if returncode not in {0, None}:
            reason = "known_publisher_source_partial_tail"
            repro = content_hash([dataset, capture_id, source_hash, reason])
            self.catalog.insert_quarantine(
                reproducibility_id=repro,
                dataset=dataset,
                capture_id=capture_id,
                source_hash=source_hash,
                reason=reason,
                severity="PASS_WITH_LIMITATION",
                count=1,
                details={"returncode": returncode, "stderr": parse_state["stderr"]},
            )

        minimum = float(self.catalog.scalar(
            "SELECT MIN(timestamp_start) FROM records WHERE dataset=? AND capture_id=?",
            (dataset, capture_id),
        ))
        maximum = float(self.catalog.scalar(
            "SELECT MAX(timestamp_end) FROM records WHERE dataset=? AND capture_id=?",
            (dataset, capture_id),
        ))
        gap = choose_gap_seconds(
            capture_span=max(0.001, maximum - minimum),
            session_durations=durations,
            fixed_safety_seconds=float(self.processing["fixed_gap_safety_seconds"]),
            long_session_quantile=float(self.processing["long_session_quantile"]),
            max_gap_fraction=float(self.processing["max_gap_fraction_for_usability"]),
        )
        updates: list[tuple[str, str, int, int]] = []
        split_counts: Counter[str] = Counter()
        for record_id, start, end in self.catalog.query(
            "SELECT record_id,timestamp_start,timestamp_end FROM records WHERE dataset=? AND capture_id=?",
            (dataset, capture_id),
        ):
            split, exclusion = chronological_split(
                float(start),
                float(end),
                minimum,
                maximum,
                float(gap["effective_gap_seconds"]),
            )
            split_counts[split] += 1
            updates.append((split, exclusion or "", int(not exclusion), int(record_id)))
            if len(updates) >= 10000:
                self.catalog.connection.executemany(
                    "UPDATE records SET base_split=?,exclusion_reason=?,retained=? WHERE record_id=?",
                    updates,
                )
                self.catalog.connection.commit()
                updates.clear()
        if updates:
            self.catalog.connection.executemany(
                "UPDATE records SET base_split=?,exclusion_reason=?,retained=? WHERE record_id=?",
                updates,
            )
            self.catalog.connection.commit()
        boundary_count = split_counts["quarantine"]
        if boundary_count:
            reason = "split_boundary_or_gap"
            self.catalog.insert_quarantine(
                reproducibility_id=content_hash([dataset, capture_id, source_hash, reason]),
                dataset=dataset,
                capture_id=capture_id,
                source_hash=source_hash,
                reason=reason,
                severity="INFO",
                count=boundary_count,
                details=gap,
            )
        duration_stats = {
            **gap,
            "minimum_timestamp": minimum,
            "maximum_timestamp": maximum,
            "capture_span_seconds": maximum - minimum,
            "session_duration_max_seconds": max(durations, default=0.0),
        }
        return AdapterResult(
            dataset=dataset,
            capture_id=capture_id,
            source_hashes={"pcap_sha256": pcap_hash, "label_csv_sha256": csv_hash, "combined": source_hash},
            source_verified=source_verified,
            records=record_count,
            retained_candidates=record_count - boundary_count,
            quarantined=boundary_count + int(parse_state["skipped_non_ip_or_unparseable"]),
            parse={**parse_state, "accepted_partial": accepted_partial},
            label_counts={fine: record_count},
            coarse_counts={coarse: record_count},
            split_counts=dict(split_counts),
            duration_statistics=duration_stats,
            anomaly_ids=anomaly_ids,
            match={"label_provenance": label_decision},
        )


def parse_zeek_log(path: Path) -> Iterator[tuple[int, dict[str, str]]]:
    fields: list[str] = []
    row_number = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith("#fields"):
                fields = line.split()[1:]
                continue
            if not line or line.startswith("#"):
                continue
            row_number += 1
            values = line.split()
            if len(values) != len(fields):
                yield row_number, {"_parse_error": "field_count_mismatch"}
                continue
            yield row_number, dict(zip(fields, values))


def iot_labels(config: dict[str, Any], label: str, detailed: str) -> tuple[str, str]:
    if label.lower() == "benign":
        return "Benign", "Benign"
    fine = detailed if detailed not in {"", "-", "(empty)"} else "Malicious-Unspecified"
    lowered = fine.lower()
    rules = config["coarse_rules"]
    coarse = str(rules["fallback"])
    for token in ("ddos", "partofahorizontalportscan", "filedownload", "c&c", "heartbeat", "attack"):
        if token in lowered:
            coarse = str(rules[token])
            break
    return fine, coarse


class IoT23Adapter(ProductionAdapter):
    def process_capture(self, spec: dict[str, Any]) -> AdapterResult:
        dataset = str(self.config["dataset_name"])
        capture_id = str(spec["id"])
        pcap = self.dataset_root / spec["pcap"]
        log = self.dataset_root / spec["log"]
        if not pcap.is_file() or not log.is_file():
            raise FileNotFoundError(f"missing IoT-23 source for {capture_id}: {pcap} / {log}")
        pcap_hash = str(spec.get("_pcap_sha256") or sha256_file(pcap))
        log_hash = str(spec.get("_log_sha256") or sha256_file(log))
        source_verified = (
            pcap_hash == str(spec["pcap_sha256"]) and log_hash == str(spec["log_sha256"])
        )
        if not source_verified:
            raise ValueError(f"source hash mismatch for {capture_id}")
        source_hash = combine_hashes([pcap_hash, log_hash])
        anomaly_ids = [str(spec["anomaly"])] if spec.get("anomaly") else []
        self.catalog.delete_capture(dataset, capture_id)
        packet_iter, parse_state = iter_tshark_packets(self.tshark_bin, pcap)
        grouped: dict[tuple[Any, ...], list[Packet]] = defaultdict(list)
        for packet in packet_iter:
            grouped[canonical_endpoint_key(packet)].append(packet)
        index = {
            key: ([packet.timestamp for packet in packets], packets)
            for key, packets in grouped.items()
        }
        accepted_partial = bool(anomaly_ids and parse_state["parsed_ip_packets"] > 0)
        if parse_state["returncode"] not in {0, None} and not accepted_partial:
            raise RuntimeError(
                f"tshark failed for {capture_id}: {parse_state['returncode']} {parse_state['stderr']}"
            )

        rows: list[dict[str, Any]] = []
        label_counts: Counter[str] = Counter()
        coarse_counts: Counter[str] = Counter()
        split_counts: Counter[str] = Counter()
        unmatched_reasons: Counter[str] = Counter()
        matched = 0
        parsed_rows = 0
        matched_packet_counts: list[int] = []
        role = str(spec["role"])
        for row_number, row in parse_zeek_log(log):
            parsed_rows += 1
            if "_parse_error" in row:
                unmatched_reasons[row["_parse_error"]] += 1
                continue
            proto = row.get("proto", "").upper()
            sport, dport = safe_int(row.get("id.orig_p")), safe_int(row.get("id.resp_p"))
            if proto in {"ICMP", "ICMPV6"}:
                proto, sport, dport = "ICMP", 0, 0
            l3 = "IPv6" if ":" in row.get("id.orig_h", "") else "IPv4"
            key = canonical_endpoint_identity(
                l3,
                proto,
                row.get("id.orig_h", ""),
                sport,
                row.get("id.resp_h", ""),
                dport,
            )
            start = safe_float(row.get("ts"), -1.0)
            duration = max(0.0, safe_float(row.get("duration")))
            expected_packets = safe_int(row.get("orig_pkts")) + safe_int(row.get("resp_pkts"))
            selected: list[Packet] = []
            if key in index and start >= 0:
                times, candidates = index[key]
                left = bisect.bisect_left(times, start - 0.002)
                right = bisect.bisect_right(times, start + max(duration, 0.25) + 0.5)
                selected = candidates[left:right]
                if expected_packets and len(selected) > expected_packets + 4:
                    selected = selected[: expected_packets + 4]
            detailed = row.get("detailed-label", row.get("det_label", "-"))
            fine, coarse = iot_labels(self.config, row.get("label", ""), detailed)
            label_counts[fine] += 1
            coarse_counts[coarse] += 1
            if not selected:
                unmatched_reasons["no_packet_match_within_strict_gate_window"] += 1
                continue
            matched += 1
            matched_packet_counts.append(len(selected))
            if role in {"train", "validation", "test"}:
                base_split, exclusion = role, ""
            elif role == "unknown_probe":
                base_split = "unknown_probe" if coarse == "FileTransfer" else "quarantine"
                exclusion = "" if coarse == "FileTransfer" else "unknown_probe_non_target_label"
            elif role == "unknown_pool":
                if fine == "PartOfAHorizontalPortScan":
                    base_split, exclusion = "unknown_dev", ""
                elif fine == "Attack":
                    base_split, exclusion = "unknown_final", ""
                else:
                    base_split, exclusion = "quarantine", "unknown_pool_non_target_label"
            else:
                raise ValueError(f"unknown IoT-23 scenario role: {role}")
            split_counts[base_split] += 1
            first = selected[0]
            session = SessionAccumulator(
                canonical_key=key,
                initiator_ip=row["id.orig_h"],
                responder_ip=row["id.resp_h"],
                initiator_port=sport,
                responder_port=dport,
                l3_protocol=l3,
                l4_protocol=proto,
                start=start,
                end=start,
                first_frame_number=first.frame_number,
                last_frame_number=first.frame_number,
            )
            for packet in selected:
                session.add(packet, int(self.processing["packet_store_limit"]))
            summary_override = {
                "duration": duration,
                "initiator_packets": safe_int(row.get("orig_pkts")),
                "responder_packets": safe_int(row.get("resp_pkts")),
                "initiator_bytes": safe_int(row.get("orig_ip_bytes")),
                "responder_bytes": safe_int(row.get("resp_ip_bytes")),
                "handshake_state": row.get("conn_state", "") or session.handshake_state,
            }
            rows.append(
                _catalog_record(
                    dataset=dataset,
                    dataset_version=str(self.config["dataset_version"]),
                    label_schema_id=str(self.config["label_schema_id"]),
                    capture_id=capture_id,
                    source_hash=source_hash,
                    source_file=pcap.name,
                    source_verified=source_verified,
                    fine_label=fine,
                    coarse_label=coarse,
                    base_split=base_split,
                    session=session,
                    deterministic_ordinal=row_number,
                    anomaly_ids=anomaly_ids,
                    service_hint=row.get("service", ""),
                    summary_override=summary_override,
                    application_capability=False,
                    original_label=f"{row.get('label', '')}|{detailed}",
                    exclusion_reason=exclusion,
                )
            )
            if len(rows) >= 5000:
                self.catalog.insert_records(rows)
                rows.clear()
            if self.mode == "sample" and matched >= self.sample_sessions:
                break
        if rows:
            self.catalog.insert_records(rows)
        for reason, count in unmatched_reasons.items():
            self.catalog.insert_quarantine(
                reproducibility_id=content_hash([dataset, capture_id, source_hash, reason]),
                dataset=dataset,
                capture_id=capture_id,
                source_hash=source_hash,
                reason=reason,
                severity="PASS_WITH_LIMITATION" if "no_packet_match" in reason else "WARNING",
                count=count,
                details={"strict_matching": True},
            )
        if parse_state["returncode"] not in {0, None}:
            reason = "known_official_pcap_tail_truncation"
            self.catalog.insert_quarantine(
                reproducibility_id=content_hash([dataset, capture_id, source_hash, reason]),
                dataset=dataset,
                capture_id=capture_id,
                source_hash=source_hash,
                reason=reason,
                severity="PASS_WITH_LIMITATION",
                count=1,
                details={"returncode": parse_state["returncode"], "stderr": parse_state["stderr"]},
            )
        quarantined = sum(unmatched_reasons.values()) + split_counts["quarantine"]
        return AdapterResult(
            dataset=dataset,
            capture_id=capture_id,
            source_hashes={"pcap_sha256": pcap_hash, "log_sha256": log_hash, "combined": source_hash},
            source_verified=source_verified,
            records=matched,
            retained_candidates=matched - split_counts["quarantine"],
            quarantined=quarantined,
            parse={**parse_state, "accepted_partial": accepted_partial},
            label_counts=dict(label_counts),
            coarse_counts=dict(coarse_counts),
            split_counts=dict(split_counts),
            duration_statistics={},
            anomaly_ids=anomaly_ids,
            match={
                "log_rows": parsed_rows,
                "matched_records": matched,
                "unmatched_records": sum(unmatched_reasons.values()),
                "match_rate": matched / parsed_rows if parsed_rows else 0.0,
                "unmatched_reasons": dict(unmatched_reasons),
                "matched_packet_count_median": (
                    sorted(matched_packet_counts)[len(matched_packet_counts) // 2]
                    if matched_packet_counts
                    else 0
                ),
                "matching_rule": "Gate-exact five-tuple plus [-0.002s, start+max(duration,0.25)+0.5s], capped at expected_packets+4",
            },
        )
