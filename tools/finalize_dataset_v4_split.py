#!/usr/bin/env python3
"""Finalize the NF3-ToN Dataset-v4 split and offline Teacher sample manifests.

This is a deterministic, zero-network data formalization tool.  It reads the
already verified official CSV member from its local archive, never calls an
LLM, and keeps row-level assets outside Git.  Tracked outputs contain only
small rules, counts, hashes, and the bounded 2,000-row sample index.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any, Iterable, Sequence
import zipfile

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from sklearn.ensemble import RandomForestClassifier


GENERATOR_VERSION = "DATASET_V4_SPLIT_GENERATOR_V1"
DEFAULT_SPLIT_SEED = 20260816
SOURCE_ARTIFACT_SHA256 = (
    "53ec8f468a43ede9b1536fabc0390af2fa33ab4312b23ce4d864f186a4651f78"
)
SOURCE_MEMBER_SUFFIX = "/data/NF-ToN-IoT-v3.csv"
SOURCE_ROW_ID_VERSION = "SOURCE_ROW_ID_CONTRACT_V1"
OBSERVATION_VERSION = "NF3_TON_OBSERVATION_V1"
GROUP_VERSION = "NF3_TON_ACTIVITY_GROUP_V1"
SPLIT_PROTOCOL = "GROUPED_TEMPORAL_HASH_70_15_15_V1"
HISTORY_SCOPE = "WITHIN_SPLIT_STRICT_END_BEFORE_TARGET_START_V1"
REFERENCE_STATE_VERSION = "NF3_TON_REFERENCE_STATE_V1"
TEACHER_INPUT_VERSION = "TEACHER_CACHE_V1_INPUT_V1"

PARTITIONS = {0: "TRAIN", 1: "VALIDATION", 2: "FINAL_TEST"}
PARTITION_CODES = {value: key for key, value in PARTITIONS.items()}
CORE_CLASS_ORDER = (
    "Backdoor",
    "Benign",
    "Credential",
    "DDoS",
    "DoS",
    "Recon_Scanning",
    "Web_Injection",
)
UNKNOWN_ROTATIONS = ("Credential", "Recon_Scanning", "Web_Injection")
FINE_TO_CANONICAL = {
    "Benign": "Benign",
    "Backdoor": "Backdoor",
    "password": "Credential",
    "ddos": "DDoS",
    "dos": "DoS",
    "scanning": "Recon_Scanning",
    "injection": "Web_Injection",
    "xss": "Web_Injection",
}
EXPECTED_SOURCE_FINE = tuple(sorted((*FINE_TO_CANONICAL, "mitm", "ransomware")))
HORIZONS_MS = (10_000, 60_000, 300_000)
REFERENCE_FOLDS = 3
REFERENCE_TREES = 80
KNOWN_FPR = 0.10

MODEL_VISIBLE_FIELDS = (
    "PROTOCOL",
    "L7_PROTO",
    "IN_BYTES",
    "IN_PKTS",
    "OUT_BYTES",
    "OUT_PKTS",
    "TCP_FLAGS",
    "CLIENT_TCP_FLAGS",
    "SERVER_TCP_FLAGS",
    "FLOW_DURATION_MILLISECONDS",
    "DURATION_IN",
    "DURATION_OUT",
    "MIN_TTL",
    "MAX_TTL",
    "LONGEST_FLOW_PKT",
    "SHORTEST_FLOW_PKT",
    "MIN_IP_PKT_LEN",
    "MAX_IP_PKT_LEN",
    "SRC_TO_DST_SECOND_BYTES",
    "DST_TO_SRC_SECOND_BYTES",
    "RETRANSMITTED_IN_BYTES",
    "RETRANSMITTED_IN_PKTS",
    "RETRANSMITTED_OUT_BYTES",
    "RETRANSMITTED_OUT_PKTS",
    "SRC_TO_DST_AVG_THROUGHPUT",
    "DST_TO_SRC_AVG_THROUGHPUT",
    "NUM_PKTS_UP_TO_128_BYTES",
    "NUM_PKTS_128_TO_256_BYTES",
    "NUM_PKTS_256_TO_512_BYTES",
    "NUM_PKTS_512_TO_1024_BYTES",
    "NUM_PKTS_1024_TO_1514_BYTES",
    "TCP_WIN_MAX_IN",
    "TCP_WIN_MAX_OUT",
    "ICMP_TYPE",
    "ICMP_IPV4_TYPE",
    "DNS_QUERY_ID",
    "DNS_QUERY_TYPE",
    "DNS_TTL_ANSWER",
    "FTP_COMMAND_RET_CODE",
    "SRC_TO_DST_IAT_MIN",
    "SRC_TO_DST_IAT_MAX",
    "SRC_TO_DST_IAT_AVG",
    "SRC_TO_DST_IAT_STDDEV",
    "DST_TO_SRC_IAT_MIN",
    "DST_TO_SRC_IAT_MAX",
    "DST_TO_SRC_IAT_AVG",
    "DST_TO_SRC_IAT_STDDEV",
)

FORBIDDEN_TEACHER_KEYS = {
    "ground_truth",
    "gt",
    "label",
    "class_index",
    "recoverable",
    "recoverable_known",
    "true_unknown",
    "unknown_rotation",
    "future_full_evidence",
    "full_evidence",
    "oof_utility_target",
    "split",
    "partition",
    "source_row_index",
    "source_fine_label",
    "canonical_label",
    "raw_ip",
    "flow_start_milliseconds",
    "flow_end_milliseconds",
}


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_file(path: Path, block_size: int = 8 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(canonical_json_bytes(record).decode("utf-8") + "\n")
    temporary.replace(path)


def source_row_id(source_row_index: int, canonical_row_digest: bytes) -> bytes:
    """Return the frozen observation identity without depending on row order in memory."""

    payload = b"\0".join(
        (
            OBSERVATION_VERSION.encode(),
            SOURCE_ARTIFACT_SHA256.encode(),
            str(source_row_index).encode(),
            canonical_row_digest,
        )
    )
    return hashlib.sha256(payload).digest()


def activity_group_digest(start_ms: int, src: bytes, dst: bytes) -> bytes:
    """Group an unordered endpoint pair inside a five-minute temporal block."""

    left, right = sorted((src, dst))
    payload = b"\0".join(
        (
            GROUP_VERSION.encode(),
            str(start_ms // 300_000).encode(),
            left,
            right,
        )
    )
    return hashlib.blake2b(payload, digest_size=16).digest()


def split_for_group(group_digest: bytes, seed: int) -> int:
    value = int.from_bytes(
        hashlib.blake2b(
            f"{seed}|split|".encode() + group_digest, digest_size=8
        ).digest(),
        "big",
    ) % 100
    if value < 70:
        return 0
    if value < 85:
        return 1
    return 2


def oof_fold_for_group(group_digest: bytes, seed: int) -> int:
    return int.from_bytes(
        hashlib.blake2b(
            f"{seed}|oof|".encode() + group_digest, digest_size=8
        ).digest(),
        "big",
    ) % REFERENCE_FOLDS


def canonical_row_digest(parts: Sequence[bytes]) -> bytes:
    """Hash a canonical JSON array of the 55 UTF-8 CSV cell strings."""

    if any(b'"' in item or b"\\" in item for item in parts):
        normalized = [item.decode("utf-8") for item in parts]
        return hashlib.sha256(canonical_json_bytes(normalized)).digest()
    payload = b'["' + b'","'.join(parts) + b'"]'
    return hashlib.sha256(payload).digest()


def confidence_bin(value: float) -> str:
    if value < 0.4:
        return "LOW"
    if value < 0.7:
        return "MID"
    return "HIGH"


def entropy(probabilities: Sequence[float]) -> float:
    return float(-sum(value * math.log(max(value, 1e-12)) for value in probabilities))


def leak_keys(value: Any, prefix: str = "") -> list[str]:
    violations: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = key.lower()
            current = f"{prefix}.{key}" if prefix else key
            if normalized in FORBIDDEN_TEACHER_KEYS:
                violations.append(current)
            violations.extend(leak_keys(nested, current))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            violations.extend(leak_keys(nested, f"{prefix}[{index}]"))
    return violations


@dataclass(frozen=True)
class PilotMeta:
    source_row_index: int
    source_row_id: bytes
    canonical_row_digest: bytes
    source_fine_label: str
    canonical_label: str | None
    flow_start_ms: int
    flow_end_ms: int
    src_code: int
    dst_code: int
    dst_port: int
    group_digest: bytes
    partition_code: int
    oof_fold: int
    critical_valid: bool


ROW_SCHEMA = pa.schema(
    [
        ("source_row_index", pa.int64()),
        ("source_row_id", pa.binary(32)),
        ("canonical_row_digest", pa.binary(32)),
        ("source_fine_label", pa.string()),
        ("canonical_label", pa.string()),
        ("flow_start_ms", pa.int64()),
        ("flow_end_ms", pa.int64()),
        ("src_code", pa.uint32()),
        ("dst_code", pa.uint32()),
        ("src_port", pa.uint16()),
        ("dst_port", pa.uint16()),
        ("protocol", pa.int16()),
        ("in_bytes", pa.int64()),
        ("out_bytes", pa.int64()),
        ("in_pkts", pa.int64()),
        ("out_pkts", pa.int64()),
        ("activity_group_digest", pa.binary(16)),
        ("partition_code", pa.int8()),
        ("oof_fold", pa.int8()),
        ("critical_valid", pa.bool_()),
        ("target_eligible", pa.bool_()),
    ]
)


def _empty_batch() -> dict[str, list[Any]]:
    return {field.name: [] for field in ROW_SCHEMA}


def _append_row(batch: dict[str, list[Any]], values: dict[str, Any]) -> None:
    for field in ROW_SCHEMA:
        batch[field.name].append(values[field.name])


def _write_batch(writer: pq.ParquetWriter, batch: dict[str, list[Any]]) -> int:
    count = len(batch["source_row_index"])
    if count:
        arrays = [pa.array(batch[field.name], type=field.type) for field in ROW_SCHEMA]
        writer.write_table(pa.Table.from_arrays(arrays, schema=ROW_SCHEMA))
    return count


def scan_official_csv(
    *,
    archive: Path,
    output_root: Path,
    pilot_indices: set[int],
    seed: int,
    batch_size: int,
) -> tuple[dict[str, Any], dict[int, PilotMeta]]:
    """Stream the complete CSV into a trusted row manifest and collect audits."""

    row_manifest = output_root / "rows" / "dataset_v4_row_manifest_v1.parquet"
    summary_path = output_root / "manifests" / "full_scan_summary.json"
    pilot_meta_path = output_root / "reference" / "pilot_source_meta.parquet"
    if row_manifest.exists() and summary_path.exists() and pilot_meta_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        expected_cache = {
            "source_artifact_sha256": SOURCE_ARTIFACT_SHA256,
            "generator_version": GENERATOR_VERSION,
            "split_seed": seed,
            "split_protocol": SPLIT_PROTOCOL,
        }
        mismatches = {
            key: (summary.get(key), value)
            for key, value in expected_cache.items()
            if summary.get(key) != value
        }
        if mismatches:
            raise RuntimeError(f"full-scan cache contract mismatch: {mismatches}")
        table = pq.read_table(pilot_meta_path)
        meta = {
            int(item["source_row_index"]): PilotMeta(
                source_row_index=int(item["source_row_index"]),
                source_row_id=bytes.fromhex(item["source_row_id"]),
                canonical_row_digest=bytes.fromhex(item["canonical_row_digest"]),
                source_fine_label=str(item["source_fine_label"]),
                canonical_label=item["canonical_label"],
                flow_start_ms=int(item["flow_start_ms"]),
                flow_end_ms=int(item["flow_end_ms"]),
                src_code=int(item["src_code"]),
                dst_code=int(item["dst_code"]),
                dst_port=int(item["dst_port"]),
                group_digest=bytes.fromhex(item["group_digest"]),
                partition_code=int(item["partition_code"]),
                oof_fold=int(item["oof_fold"]),
                critical_valid=bool(item["critical_valid"]),
            )
            for item in table.to_pylist()
        }
        return summary, meta

    row_manifest.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    pilot_meta_path.parent.mkdir(parents=True, exist_ok=True)
    partial = row_manifest.with_suffix(".parquet.partial")
    if partial.exists():
        partial.unlink()

    ip_codes: dict[bytes, int] = {}
    next_ip_code = 1

    def ip_code(value: bytes) -> int:
        nonlocal next_ip_code
        found = ip_codes.get(value)
        if found is None:
            found = next_ip_code
            next_ip_code += 1
            ip_codes[value] = found
        return found

    partition_counts: Counter[str] = Counter()
    per_class_split: dict[str, Counter[str]] = {
        label: Counter() for label in CORE_CLASS_ORDER
    }
    fine_counts: Counter[str] = Counter()
    invalid_reason_counts: Counter[str] = Counter()
    time_ranges: dict[str, list[int | None]] = {
        value: [None, None] for value in PARTITIONS.values()
    }
    pilot_meta: dict[int, PilotMeta] = {}
    batch = _empty_batch()
    source_digest = hashlib.sha256()
    started = time.monotonic()

    with zipfile.ZipFile(archive) as zipped:
        members = [name for name in zipped.namelist() if name.endswith(SOURCE_MEMBER_SUFFIX)]
        if len(members) != 1:
            raise RuntimeError(f"expected one NF3-ToN CSV member, found {members}")
        with zipped.open(members[0]) as source, pq.ParquetWriter(
            partial, ROW_SCHEMA, compression="zstd", use_dictionary=True
        ) as writer:
            header_line = source.readline()
            source_digest.update(header_line)
            header = header_line.rstrip(b"\r\n").decode("utf-8").split(",")
            if len(header) != 55:
                raise RuntimeError(f"expected 55 columns, found {len(header)}")
            positions = {name: index for index, name in enumerate(header)}
            if tuple(name for name in MODEL_VISIBLE_FIELDS if name not in positions):
                raise RuntimeError("official CSV is missing a frozen Basic field")

            for row_index, line in enumerate(source):
                source_digest.update(line)
                parts = line.rstrip(b"\r\n").split(b",")
                digest = canonical_row_digest(parts) if len(parts) == 55 else hashlib.sha256(line).digest()
                row_id = source_row_id(row_index, digest)
                critical_valid = True
                reasons: list[str] = []
                if len(parts) != 55:
                    critical_valid = False
                    reasons.append("column_count")
                    parts = parts + [b""] * max(0, 55 - len(parts))

                def required_int(index: int, name: str, minimum: int = 0) -> int:
                    nonlocal critical_valid
                    try:
                        value = int(parts[index])
                        if value < minimum:
                            raise ValueError
                        return value
                    except (ValueError, TypeError):
                        critical_valid = False
                        reasons.append(name)
                        return 0

                start_ms = required_int(positions["FLOW_START_MILLISECONDS"], "start")
                end_ms = required_int(positions["FLOW_END_MILLISECONDS"], "end")
                src_port = required_int(positions["L4_SRC_PORT"], "src_port")
                dst_port = required_int(positions["L4_DST_PORT"], "dst_port")
                protocol = required_int(positions["PROTOCOL"], "protocol")
                in_bytes = required_int(positions["IN_BYTES"], "in_bytes")
                out_bytes = required_int(positions["OUT_BYTES"], "out_bytes")
                in_pkts = required_int(positions["IN_PKTS"], "in_pkts")
                out_pkts = required_int(positions["OUT_PKTS"], "out_pkts")
                src = parts[positions["IPV4_SRC_ADDR"]]
                dst = parts[positions["IPV4_DST_ADDR"]]
                if not src:
                    critical_valid = False
                    reasons.append("src_ip")
                if not dst:
                    critical_valid = False
                    reasons.append("dst_ip")
                if end_ms < start_ms:
                    critical_valid = False
                    reasons.append("timestamp_order")
                label_raw = parts[positions["Label"]]
                fine_raw = parts[positions["Attack"]]
                try:
                    fine = fine_raw.decode("utf-8")
                except UnicodeDecodeError:
                    fine = "<INVALID_UTF8>"
                    critical_valid = False
                    reasons.append("attack_utf8")
                fine_counts[fine] += 1
                canonical = FINE_TO_CANONICAL.get(fine)
                expected_binary = b"0" if fine == "Benign" else b"1"
                if label_raw != expected_binary:
                    critical_valid = False
                    reasons.append("binary_label_consistency")
                group = (
                    activity_group_digest(start_ms, src, dst)
                    if critical_valid
                    else hashlib.blake2b(row_id, digest_size=16).digest()
                )
                partition_code = split_for_group(group, seed)
                fold = oof_fold_for_group(group, seed)
                target_eligible = critical_valid and canonical is not None
                source_code = ip_code(src) if src else 0
                destination_code = ip_code(dst) if dst else 0
                _append_row(
                    batch,
                    {
                        "source_row_index": row_index,
                        "source_row_id": row_id,
                        "canonical_row_digest": digest,
                        "source_fine_label": fine,
                        "canonical_label": canonical,
                        "flow_start_ms": start_ms,
                        "flow_end_ms": end_ms,
                        "src_code": source_code,
                        "dst_code": destination_code,
                        "src_port": min(src_port, 65535),
                        "dst_port": min(dst_port, 65535),
                        "protocol": min(protocol, 32767),
                        "in_bytes": in_bytes,
                        "out_bytes": out_bytes,
                        "in_pkts": in_pkts,
                        "out_pkts": out_pkts,
                        "activity_group_digest": group,
                        "partition_code": partition_code,
                        "oof_fold": fold,
                        "critical_valid": critical_valid,
                        "target_eligible": target_eligible,
                    },
                )
                if target_eligible:
                    partition = PARTITIONS[partition_code]
                    partition_counts[partition] += 1
                    per_class_split[str(canonical)][partition] += 1
                    current = time_ranges[partition]
                    current[0] = start_ms if current[0] is None else min(int(current[0]), start_ms)
                    current[1] = end_ms if current[1] is None else max(int(current[1]), end_ms)
                if reasons:
                    for reason in set(reasons):
                        invalid_reason_counts[reason] += 1
                if row_index in pilot_indices:
                    pilot_meta[row_index] = PilotMeta(
                        source_row_index=row_index,
                        source_row_id=row_id,
                        canonical_row_digest=digest,
                        source_fine_label=fine,
                        canonical_label=canonical,
                        flow_start_ms=start_ms,
                        flow_end_ms=end_ms,
                        src_code=source_code,
                        dst_code=destination_code,
                        dst_port=dst_port,
                        group_digest=group,
                        partition_code=partition_code,
                        oof_fold=fold,
                        critical_valid=critical_valid,
                    )
                if len(batch["source_row_index"]) >= batch_size:
                    _write_batch(writer, batch)
                    batch = _empty_batch()
                if row_index and row_index % 1_000_000 == 0:
                    elapsed = time.monotonic() - started
                    print(
                        f"SCAN_PROGRESS rows={row_index:,} elapsed={elapsed:.1f}s "
                        f"rate={row_index / max(elapsed, 1):,.0f}/s",
                        flush=True,
                    )
            _write_batch(writer, batch)

    observed_sha256 = source_digest.hexdigest()
    if observed_sha256 != SOURCE_ARTIFACT_SHA256:
        partial.unlink(missing_ok=True)
        raise RuntimeError(
            f"source artifact mismatch: {observed_sha256} != {SOURCE_ARTIFACT_SHA256}"
        )
    partial.replace(row_manifest)
    if set(pilot_meta) != pilot_indices:
        missing = sorted(pilot_indices - set(pilot_meta))[:10]
        raise RuntimeError(f"pilot source rows missing from official CSV: {missing}")
    unexpected_fine = sorted(set(fine_counts) - set(EXPECTED_SOURCE_FINE))
    if unexpected_fine:
        raise RuntimeError(f"unexpected source labels: {unexpected_fine}")

    meta_records = [
        {
            "source_row_index": value.source_row_index,
            "source_row_id": value.source_row_id.hex(),
            "canonical_row_digest": value.canonical_row_digest.hex(),
            "source_fine_label": value.source_fine_label,
            "canonical_label": value.canonical_label,
            "flow_start_ms": value.flow_start_ms,
            "flow_end_ms": value.flow_end_ms,
            "src_code": value.src_code,
            "dst_code": value.dst_code,
            "dst_port": value.dst_port,
            "group_digest": value.group_digest.hex(),
            "partition_code": value.partition_code,
            "oof_fold": value.oof_fold,
            "critical_valid": value.critical_valid,
        }
        for value in sorted(pilot_meta.values(), key=lambda item: item.source_row_index)
    ]
    pq.write_table(pa.Table.from_pylist(meta_records), pilot_meta_path, compression="zstd")
    summary = {
        "schema_version": "DATASET_V4_FULL_SCAN_SUMMARY_V1",
        "generator_version": GENERATOR_VERSION,
        "source_artifact_sha256": observed_sha256,
        "source_member": members[0],
        "source_row_count": sum(fine_counts.values()),
        "source_fine_counts": dict(sorted(fine_counts.items())),
        "target_core_row_count": sum(partition_counts.values()),
        "partition_counts": dict(sorted(partition_counts.items())),
        "per_class_split_counts": {
            label: {partition: per_class_split[label][partition] for partition in PARTITIONS.values()}
            for label in CORE_CLASS_ORDER
        },
        "time_ranges_ms": time_ranges,
        "invalid_critical_row_n": sum(1 for _ in ()) if not invalid_reason_counts else None,
        "invalid_reason_counts": dict(sorted(invalid_reason_counts.items())),
        "unknown_canonical_label_n": sum(
            count for label, count in fine_counts.items() if label not in FINE_TO_CANONICAL
        ),
        "unique_ip_code_count": len(ip_codes),
        "pilot_meta_count": len(pilot_meta),
        "split_seed": seed,
        "split_protocol": SPLIT_PROTOCOL,
        "row_manifest_path": str(row_manifest),
        "elapsed_seconds": time.monotonic() - started,
    }
    # Every invalid row contributes at least one reason, but a row can have more
    # than one.  Derive the exact row count from the persisted validity column.
    validity = pq.read_table(row_manifest, columns=["critical_valid"])["critical_valid"]
    summary["invalid_critical_row_n"] = int(
        len(validity) - pc.sum(validity.cast(pa.int64())).as_py()
    )
    write_json(summary_path, summary)
    return summary, pilot_meta


def audit_duplicates_and_groups(row_manifest: Path) -> dict[str, Any]:
    output_path = row_manifest.parent.parent / "manifests" / "identity_group_audit.json"
    if output_path.exists():
        return json.loads(output_path.read_text(encoding="utf-8"))
    table = pq.read_table(
        row_manifest,
        columns=[
            "canonical_row_digest",
            "source_row_index",
            "activity_group_digest",
            "partition_code",
            "target_eligible",
        ],
    ).combine_chunks()
    duplicate_groups = table.group_by("canonical_row_digest").aggregate(
        [
            ("source_row_index", "count"),
            ("partition_code", "min"),
            ("partition_code", "max"),
        ]
    )
    counts = duplicate_groups["source_row_index_count"].to_numpy()
    partition_min = duplicate_groups["partition_code_min"].to_numpy()
    partition_max = duplicate_groups["partition_code_max"].to_numpy()
    exact_duplicate_n = int(np.maximum(counts - 1, 0).sum())
    duplicate_group_n = int((counts > 1).sum())
    duplicate_cross_split_n = int(((counts > 1) & (partition_min != partition_max)).sum())
    group_cross = table.group_by("activity_group_digest").aggregate(
        [("partition_code", "min"), ("partition_code", "max")]
    )
    group_cross_split_n = int(
        np.count_nonzero(
            group_cross["partition_code_min"].to_numpy()
            != group_cross["partition_code_max"].to_numpy()
        )
    )
    eligible = table.filter(table["target_eligible"])
    group_counts = {
        PARTITIONS[code]: int(
            pc.count_distinct(
                eligible.filter(pc.equal(eligible["partition_code"], code))[
                    "activity_group_digest"
                ]
            ).as_py()
        )
        for code in PARTITIONS
    }
    result = {
        "schema_version": "DATASET_V4_IDENTITY_GROUP_AUDIT_V1",
        "source_row_count": len(table),
        "source_row_identity_duplicate_n": 0,
        "exact_duplicate_n": exact_duplicate_n,
        "exact_duplicate_group_n": duplicate_group_n,
        "duplicate_group_cross_split_n": duplicate_cross_split_n,
        "activity_group_cross_split_n": group_cross_split_n,
        "eligible_group_counts": group_counts,
        "status": "PASS"
        if duplicate_cross_split_n == 0 and group_cross_split_n == 0
        else "FAIL",
    }
    write_json(output_path, result)
    return result


def _group_bounds(keys: np.ndarray) -> dict[int, tuple[int, int]]:
    changes = np.flatnonzero(np.r_[True, keys[1:] != keys[:-1], True])
    return {
        int(keys[start]): (int(start), int(end))
        for start, end in zip(changes[:-1], changes[1:], strict=True)
    }


def materialize_strict_history(
    row_manifest: Path,
    pilot_meta: dict[int, PilotMeta],
    target_indices: Sequence[int],
) -> tuple[np.ndarray, list[str]]:
    """Build strict split-local completed-flow history for bounded pilot targets."""

    cache_path = row_manifest.parent.parent / "reference" / "strict_history_v1.parquet"
    if cache_path.exists():
        table = pq.read_table(cache_path)
        positions = {int(v): i for i, v in enumerate(table["source_row_index"].to_pylist())}
        names = [name for name in table.column_names if name != "source_row_index"]
        matrix = np.array(
            [
                [float(table[name][positions[index]].as_py()) for name in names]
                for index in target_indices
            ],
            dtype=np.float64,
        )
        return matrix, names

    table = pq.read_table(
        row_manifest,
        columns=[
            "flow_end_ms",
            "src_code",
            "dst_code",
            "dst_port",
            "in_bytes",
            "out_bytes",
            "in_pkts",
            "out_pkts",
            "partition_code",
            "critical_valid",
        ],
    ).combine_chunks()
    valid = table["critical_valid"].to_numpy(zero_copy_only=False).astype(bool)
    end = table["flow_end_ms"].to_numpy(zero_copy_only=False)[valid].astype(np.int64)
    src = table["src_code"].to_numpy(zero_copy_only=False)[valid].astype(np.int64)
    dst = table["dst_code"].to_numpy(zero_copy_only=False)[valid].astype(np.int64)
    dport = table["dst_port"].to_numpy(zero_copy_only=False)[valid].astype(np.int64)
    bytes_total = (
        table["in_bytes"].to_numpy(zero_copy_only=False)[valid].astype(np.int64)
        + table["out_bytes"].to_numpy(zero_copy_only=False)[valid].astype(np.int64)
    )
    packets_total = (
        table["in_pkts"].to_numpy(zero_copy_only=False)[valid].astype(np.int64)
        + table["out_pkts"].to_numpy(zero_copy_only=False)[valid].astype(np.int64)
    )
    partition = table["partition_code"].to_numpy(zero_copy_only=False)[valid].astype(np.int64)
    del table, valid

    src_order = np.lexsort((end, src, partition))
    src_keys = (partition[src_order] << 32) | src[src_order]
    src_bounds = _group_bounds(src_keys)
    src_end = end[src_order]
    src_dst = dst[src_order]
    src_dport = dport[src_order]
    src_bytes = bytes_total[src_order]
    src_packets = packets_total[src_order]
    prefix_bytes = np.r_[0, np.cumsum(src_bytes, dtype=np.int64)]
    prefix_packets = np.r_[0, np.cumsum(src_packets, dtype=np.int64)]

    dst_order = np.lexsort((end, dst, partition))
    dst_keys = (partition[dst_order] << 32) | dst[dst_order]
    dst_bounds = _group_bounds(dst_keys)
    dst_end = end[dst_order]
    dst_src = src[dst_order]

    names: list[str] = []
    for horizon in HORIZONS_MS:
        suffix = f"{horizon // 1000}s"
        names.extend(
            [
                f"source_flow_count_{suffix}",
                f"source_unique_destination_count_{suffix}",
                f"source_unique_destination_port_count_{suffix}",
                f"source_same_destination_port_count_{suffix}",
                f"destination_flow_count_{suffix}",
                f"source_flow_rate_{suffix}",
                f"source_packet_rate_{suffix}",
                f"source_byte_rate_{suffix}",
                f"source_destination_pair_count_{suffix}",
                f"destination_unique_source_count_{suffix}",
                f"source_unique_neighbor_count_{suffix}",
            ]
        )
    names.append("same_source_last_seen_gap_ms")

    output = np.zeros((len(target_indices), len(names)), dtype=np.float64)
    for output_index, source_index in enumerate(target_indices):
        meta = pilot_meta[source_index]
        src_key = (meta.partition_code << 32) | meta.src_code
        dst_key = (meta.partition_code << 32) | meta.dst_code
        src_lo, src_hi = src_bounds.get(src_key, (0, 0))
        dst_lo, dst_hi = dst_bounds.get(dst_key, (0, 0))
        source_end = src_end[src_lo:src_hi]
        destination_end = dst_end[dst_lo:dst_hi]
        upper_source = int(np.searchsorted(source_end, meta.flow_start_ms, side="left"))
        upper_destination = int(
            np.searchsorted(destination_end, meta.flow_start_ms, side="left")
        )
        values: list[float] = []
        for horizon in HORIZONS_MS:
            cutoff = meta.flow_start_ms - horizon
            lower_source = int(np.searchsorted(source_end, cutoff, side="left"))
            lower_destination = int(
                np.searchsorted(destination_end, cutoff, side="left")
            )
            absolute_source_lo = src_lo + lower_source
            absolute_source_hi = src_lo + upper_source
            absolute_destination_lo = dst_lo + lower_destination
            absolute_destination_hi = dst_lo + upper_destination
            window_dst = src_dst[absolute_source_lo:absolute_source_hi]
            window_port = src_dport[absolute_source_lo:absolute_source_hi]
            destination_sources = dst_src[
                absolute_destination_lo:absolute_destination_hi
            ]
            source_count = absolute_source_hi - absolute_source_lo
            destination_count = absolute_destination_hi - absolute_destination_lo
            byte_count = int(prefix_bytes[absolute_source_hi] - prefix_bytes[absolute_source_lo])
            packet_count = int(
                prefix_packets[absolute_source_hi] - prefix_packets[absolute_source_lo]
            )
            same_destination = window_dst == meta.dst_code
            same_destination_port = same_destination & (window_port == meta.dst_port)
            neighbor = (window_dst.astype(np.int64) << 16) | window_port
            seconds = horizon / 1000.0
            values.extend(
                [
                    float(source_count),
                    float(len(np.unique(window_dst))),
                    float(len(np.unique(window_port))),
                    float(np.count_nonzero(same_destination_port)),
                    float(destination_count),
                    float(source_count / seconds),
                    float(packet_count / seconds),
                    float(byte_count / seconds),
                    float(np.count_nonzero(same_destination)),
                    float(len(np.unique(destination_sources))),
                    float(len(np.unique(neighbor))),
                ]
            )
        previous_end = (
            int(source_end[upper_source - 1]) if upper_source > 0 else None
        )
        values.append(
            float(meta.flow_start_ms - previous_end) if previous_end is not None else -1.0
        )
        output[output_index] = values
        if output_index and output_index % 2_000 == 0:
            print(f"HISTORY_PROGRESS targets={output_index:,}/{len(target_indices):,}", flush=True)

    records = {"source_row_index": pa.array(target_indices, type=pa.int64())}
    for index, name in enumerate(names):
        records[name] = pa.array(output[:, index], type=pa.float64())
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table(records), cache_path, compression="zstd")
    return output, names


def _safe_basic(pilot: pa.Table, indices: np.ndarray) -> np.ndarray:
    matrix = np.column_stack(
        [
            np.asarray(pilot[name].to_numpy(zero_copy_only=False), dtype=np.float64)[indices]
            for name in MODEL_VISIBLE_FIELDS
        ]
    )
    matrix = np.nan_to_num(matrix, nan=0.0, posinf=1e15, neginf=-1e15)
    return np.sign(matrix) * np.log1p(np.abs(matrix))


def _aligned_probabilities(
    model: RandomForestClassifier,
    matrix: np.ndarray,
    classes: Sequence[str],
) -> np.ndarray:
    raw = model.predict_proba(matrix)
    result = np.zeros((len(matrix), len(classes)), dtype=np.float64)
    positions = {label: index for index, label in enumerate(classes)}
    for raw_index, label in enumerate(model.classes_.tolist()):
        result[:, positions[str(label)]] = raw[:, raw_index]
    return result


def _fit_reference(
    matrix: np.ndarray,
    labels: np.ndarray,
    train_mask: np.ndarray,
    *,
    seed: int,
) -> RandomForestClassifier:
    model = RandomForestClassifier(
        n_estimators=REFERENCE_TREES,
        max_depth=20,
        min_samples_leaf=2,
        class_weight="balanced_subsample",
        n_jobs=1,
        random_state=seed,
    )
    model.fit(matrix[train_mask], labels[train_mask])
    return model


def reference_predictions(
    *,
    pilot: pa.Table,
    pilot_meta: dict[int, PilotMeta],
    history: np.ndarray,
    target_indices: Sequence[int],
    seed: int,
) -> tuple[list[dict[str, Any]], dict[tuple[int, str], dict[str, Any]], dict[str, Any]]:
    """Create group-safe OOF/holdout tree reference states without final test."""

    row_positions = {
        int(value): index
        for index, value in enumerate(pilot["source_row_index"].to_pylist())
    }
    positions = np.array([row_positions[index] for index in target_indices], dtype=np.int64)
    labels = np.array(
        [pilot_meta[index].canonical_label for index in target_indices], dtype=object
    )
    basic = _safe_basic(pilot, positions)
    full = np.column_stack([basic, np.log1p(np.clip(history, 0.0, None))])
    partitions = np.array(
        [pilot_meta[index].partition_code for index in target_indices], dtype=np.int8
    )
    folds = np.array([pilot_meta[index].oof_fold for index in target_indices], dtype=np.int8)
    group_digests = np.array(
        [pilot_meta[index].group_digest for index in target_indices], dtype=object
    )
    train = partitions == PARTITION_CODES["TRAIN"]
    validation = partitions == PARTITION_CODES["VALIDATION"]
    if np.any(partitions == PARTITION_CODES["FINAL_TEST"]):
        raise RuntimeError("reference target set contains FINAL_TEST")

    basic_prob = np.zeros((len(labels), len(CORE_CLASS_ORDER)), dtype=np.float64)
    full_prob = np.zeros_like(basic_prob)
    thresholds = np.zeros(len(labels), dtype=np.float64)
    for fold in range(REFERENCE_FOLDS):
        evaluation = train & (folds == fold)
        fit = train & (folds != fold)
        if set(group_digests[evaluation]) & set(group_digests[fit]):
            raise RuntimeError(f"reference OOF group overlap in fold {fold}")
        basic_model = _fit_reference(basic, labels, fit, seed=seed + fold * 101)
        full_model = _fit_reference(full, labels, fit, seed=seed + 10_000 + fold * 101)
        basic_prob[evaluation] = _aligned_probabilities(
            basic_model, basic[evaluation], CORE_CLASS_ORDER
        )
        full_prob[evaluation] = _aligned_probabilities(
            full_model, full[evaluation], CORE_CLASS_ORDER
        )
        fit_confidence = _aligned_probabilities(
            basic_model, basic[fit], CORE_CLASS_ORDER
        ).max(axis=1)
        thresholds[evaluation] = float(np.quantile(fit_confidence, KNOWN_FPR, method="higher"))

    basic_model = _fit_reference(basic, labels, train, seed=seed + 50_000)
    full_model = _fit_reference(full, labels, train, seed=seed + 60_000)
    basic_prob[validation] = _aligned_probabilities(
        basic_model, basic[validation], CORE_CLASS_ORDER
    )
    full_prob[validation] = _aligned_probabilities(
        full_model, full[validation], CORE_CLASS_ORDER
    )
    train_confidence = _aligned_probabilities(
        basic_model, basic[train], CORE_CLASS_ORDER
    ).max(axis=1)
    thresholds[validation] = float(
        np.quantile(train_confidence, KNOWN_FPR, method="higher")
    )

    label_positions = {label: index for index, label in enumerate(CORE_CLASS_ORDER)}
    records: list[dict[str, Any]] = []
    for index, source_index in enumerate(target_indices):
        truth = str(labels[index])
        basic_prediction = CORE_CLASS_ORDER[int(np.argmax(basic_prob[index]))]
        full_prediction = CORE_CLASS_ORDER[int(np.argmax(full_prob[index]))]
        maximum = float(np.max(basic_prob[index]))
        basic_correct = basic_prediction == truth
        full_correct = full_prediction == truth
        uncertain = maximum < float(thresholds[index])
        recovered = (not basic_correct or uncertain) and full_correct
        sufficient = basic_correct and not uncertain
        records.append(
            {
                "source_row_index": source_index,
                "source_row_id": pilot_meta[source_index].source_row_id.hex(),
                "private_group_digest": pilot_meta[source_index].group_digest.hex(),
                "source_fine_label": pilot_meta[source_index].source_fine_label,
                "canonical_label": truth,
                "source_partition": PARTITIONS[pilot_meta[source_index].partition_code],
                "policy_role": "POLICY_DEMO_DEVELOPMENT"
                if pilot_meta[source_index].partition_code == PARTITION_CODES["TRAIN"]
                else "POLICY_META_EVALUATION",
                "oof_fold": int(folds[index]) if train[index] else None,
                "prediction_provenance": "GROUP_OOF_TRAIN"
                if train[index]
                else "TRAIN_FIT_VALIDATION_HOLDOUT",
                "class_order": list(CORE_CLASS_ORDER),
                "basic_probabilities": basic_prob[index].tolist(),
                "basic_prediction": basic_prediction,
                "basic_max_probability": maximum,
                "basic_uncertainty_threshold": float(thresholds[index]),
                "basic_sufficient_known": sufficient,
                "recoverable_known": recovered,
                "full_prediction": full_prediction,
                "full_true_probability": float(full_prob[index, label_positions[truth]]),
            }
        )

    unknown_predictions: dict[tuple[int, str], dict[str, Any]] = {}
    unknown_group_overlap_n = 0
    for rotation_index, holdout in enumerate(UNKNOWN_ROTATIONS):
        known_classes = tuple(label for label in CORE_CLASS_ORDER if label != holdout)
        target = labels == holdout
        target_groups = set(group_digests[target])
        fit = train & (labels != holdout) & np.array(
            [group not in target_groups for group in group_digests], dtype=bool
        )
        overlap = len(set(group_digests[fit]) & target_groups)
        unknown_group_overlap_n += overlap
        if overlap:
            raise RuntimeError(f"unknown rotation group overlap for {holdout}: {overlap}")
        model = _fit_reference(
            basic, labels, fit, seed=seed + 70_000 + rotation_index * 1_000
        )
        probabilities = _aligned_probabilities(model, basic[target], known_classes)
        fit_probabilities = _aligned_probabilities(model, basic[fit], known_classes)
        threshold = float(
            np.quantile(fit_probabilities.max(axis=1), KNOWN_FPR, method="higher")
        )
        for local_index, global_index in enumerate(np.flatnonzero(target)):
            source_index = target_indices[int(global_index)]
            prediction = known_classes[int(np.argmax(probabilities[local_index]))]
            unknown_predictions[(source_index, holdout)] = {
                "source_row_index": source_index,
                "source_row_id": pilot_meta[source_index].source_row_id.hex(),
                "private_group_digest": pilot_meta[source_index].group_digest.hex(),
                "source_fine_label": pilot_meta[source_index].source_fine_label,
                "canonical_label": holdout,
                "source_partition": PARTITIONS[pilot_meta[source_index].partition_code],
                "policy_role": "POLICY_DEMO_DEVELOPMENT"
                if pilot_meta[source_index].partition_code == PARTITION_CODES["TRAIN"]
                else "POLICY_META_EVALUATION",
                "unknown_rotation": holdout,
                "class_order": list(known_classes),
                "basic_probabilities": probabilities[local_index].tolist(),
                "basic_prediction": prediction,
                "basic_max_probability": float(np.max(probabilities[local_index])),
                "basic_uncertainty_threshold": threshold,
                "prediction_provenance": "WHOLE_CLASS_HELDOUT_TRAIN_FIT",
            }

    audit = {
        "schema_version": REFERENCE_STATE_VERSION,
        "reference_classifier": "RandomForestClassifier",
        "trees": REFERENCE_TREES,
        "max_depth": 20,
        "oof_folds": REFERENCE_FOLDS,
        "known_fpr_for_uncertainty": KNOWN_FPR,
        "train_reference_n": int(train.sum()),
        "validation_reference_n": int(validation.sum()),
        "final_test_reference_n": 0,
        "basic_sufficient_known_n": sum(
            bool(item["basic_sufficient_known"]) for item in records
        ),
        "recoverable_known_n": sum(bool(item["recoverable_known"]) for item in records),
        "unknown_rotation_candidate_n": len(unknown_predictions),
        "unknown_rotation_group_overlap_n": unknown_group_overlap_n,
        "no_self_training": True,
        "strict_history_scope": HISTORY_SCOPE,
        "model_b_training": False,
    }
    return records, unknown_predictions, audit


def _selection_hash(seed: int, candidate: dict[str, Any]) -> bytes:
    payload = "|".join(
        [
            str(seed),
            str(candidate["sampling_stratum"]),
            str(candidate["policy_role"]),
            str(candidate["balance_key"]),
            str(candidate["confidence_bin"]),
            str(candidate["source_row_id"]),
        ]
    )
    return hashlib.blake2b(payload.encode(), digest_size=16).digest()


def balanced_select(
    candidates: list[dict[str, Any]],
    *,
    target_n: int,
    seed: int,
    used_source_ids: set[str],
) -> list[dict[str, Any]]:
    cells: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        if candidate["source_row_id"] in used_source_ids:
            continue
        cells[(candidate["balance_key"], candidate["confidence_bin"])].append(candidate)
    for values in cells.values():
        values.sort(key=lambda item: _selection_hash(seed, item))
    keys = sorted(cells)
    selected: list[dict[str, Any]] = []
    cursor = 0
    while len(selected) < target_n and keys:
        key = keys[cursor % len(keys)]
        values = cells[key]
        while values and values[0]["source_row_id"] in used_source_ids:
            values.pop(0)
        if values:
            item = values.pop(0)
            selected.append(item)
            used_source_ids.add(item["source_row_id"])
        else:
            keys.remove(key)
            cursor -= 1
        cursor += 1
    if len(selected) != target_n:
        raise RuntimeError(f"sampling shortfall: selected {len(selected)} of {target_n}")
    return selected


def teacher_payload(
    *,
    candidate: dict[str, Any],
    basic_values: dict[str, float | None],
) -> dict[str, Any]:
    probabilities = [float(value) for value in candidate["basic_probabilities"]]
    class_order = [str(value) for value in candidate["class_order"]]
    probability_map = {
        label: value for label, value in zip(class_order, probabilities, strict=True)
    }
    ordered = sorted(probabilities)
    payload = {
        "schema_version": TEACHER_INPUT_VERSION,
        "sample_id": candidate["source_row_id"],
        "current_evidence_card": {
            "BASIC": {
                "schema_version": "NF3_TON_BASIC_CARD_V1",
                "features": basic_values,
                "missing_fields": [
                    name for name, value in basic_values.items() if value is None
                ],
            },
            "TEMPORAL": None,
            "RELATION": None,
        },
        "known_prediction_summary": {
            "class_map_version": candidate["class_map_version"],
            "known_class_probabilities": probability_map,
            "predicted_class": candidate["basic_prediction"],
            "max_probability": float(max(probabilities)),
            "top1_top2_margin": float(ordered[-1] - ordered[-2]),
            "entropy": entropy(probabilities),
        },
        "current_evidence_mask": {
            "BASIC": True,
            "TEMPORAL": False,
            "RELATION": False,
        },
        "available_next_evidence": ["TEMPORAL", "RELATION"],
    }
    violations = leak_keys(payload)
    if violations:
        raise RuntimeError(f"Teacher payload leakage keys: {violations}")
    return payload


def materialize_teacher_samples(
    *,
    repo_root: Path,
    output_root: Path,
    pilot: pa.Table,
    pilot_meta: dict[int, PilotMeta],
    known_records: list[dict[str, Any]],
    unknown_records: dict[tuple[int, str], dict[str, Any]],
    seed: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    design = json.loads(
        (repo_root / "configs/dataset_v4/teacher_cache_v1_sampling_manifest_design.json").read_text(
            encoding="utf-8"
        )
    )
    sampling_seed = int(design["sampling_seed"])
    quotas = {
        (item["stratum"], "POLICY_DEMO_DEVELOPMENT"): item[
            "policy_demo_development_n"
        ]
        for item in design["strata"]
    }
    quotas.update(
        {
            (item["stratum"], "POLICY_META_EVALUATION"): item[
                "policy_meta_evaluation_n"
            ]
            for item in design["strata"]
        }
    )

    candidates: list[dict[str, Any]] = []
    for record in known_records:
        if record["basic_sufficient_known"]:
            stratum = "BASIC_SUFFICIENT_KNOWN"
        elif record["recoverable_known"]:
            stratum = "RECOVERABLE_KNOWN"
        else:
            continue
        candidate = dict(record)
        candidate.update(
            {
                "sampling_stratum": stratum,
                "balance_key": record["canonical_label"],
                "confidence_bin": confidence_bin(record["basic_max_probability"]),
                "unknown_rotation": None,
                "class_map_version": "CANONICAL_TAXONOMY_V1",
            }
        )
        candidates.append(candidate)
    for (_, holdout), record in unknown_records.items():
        candidate = dict(record)
        opaque_rotation = hashlib.sha256(
            f"CANONICAL_TAXONOMY_V1|heldout|{holdout}".encode()
        ).hexdigest()[:12]
        candidate.update(
            {
                "sampling_stratum": "TRUE_UNKNOWN_ROTATIONS",
                "balance_key": holdout,
                "confidence_bin": confidence_bin(record["basic_max_probability"]),
                "class_map_version": f"KNOWN_CLASS_MAP_V1_{opaque_rotation}",
            }
        )
        candidates.append(candidate)

    used: set[str] = set()
    selected: list[dict[str, Any]] = []
    cell_allocation_audit: dict[str, dict[str, Any]] = {}
    # Reserve whole-class Unknown rows first, then the two disjoint Known states.
    stratum_order = (
        "TRUE_UNKNOWN_ROTATIONS",
        "RECOVERABLE_KNOWN",
        "BASIC_SUFFICIENT_KNOWN",
    )
    for stratum in stratum_order:
        for role in ("POLICY_DEMO_DEVELOPMENT", "POLICY_META_EVALUATION"):
            pool = [
                item
                for item in candidates
                if item["sampling_stratum"] == stratum and item["policy_role"] == role
            ]
            available_pool = [
                item for item in pool if item["source_row_id"] not in used
            ]
            chosen = balanced_select(
                pool,
                target_n=int(quotas[(stratum, role)]),
                seed=sampling_seed,
                used_source_ids=used,
            )
            selected.extend(chosen)
            eligible_cells = Counter(
                f"{item['balance_key']}|{item['confidence_bin']}"
                for item in available_pool
            )
            selected_cells = Counter(
                f"{item['balance_key']}|{item['confidence_bin']}" for item in chosen
            )
            keys = sorted(eligible_cells)
            target = int(quotas[(stratum, role)])
            base, remainder = divmod(target, len(keys))
            ideal = {
                key: base + int(index < remainder) for index, key in enumerate(keys)
            }
            shortfalls = {
                key: max(ideal[key] - selected_cells[key], 0) for key in keys
            }
            cell_allocation_audit[f"{stratum}|{role}"] = {
                "target_n": target,
                "eligible_n": len(available_pool),
                "eligible_cell_counts": dict(sorted(eligible_cells.items())),
                "largest_remainder_equal_cell_quotas": ideal,
                "selected_cell_counts": dict(sorted(selected_cells.items())),
                "capacity_shortfalls": {
                    key: value for key, value in shortfalls.items() if value
                },
                "redistributed_n": sum(
                    max(selected_cells[key] - ideal[key], 0) for key in keys
                ),
            }

    pilot_positions = {
        int(value): index
        for index, value in enumerate(pilot["source_row_index"].to_pylist())
    }
    teacher_requests: list[dict[str, Any]] = []
    offline_records: list[dict[str, Any]] = []
    tracked_samples: list[dict[str, Any]] = []
    for candidate in sorted(
        selected,
        key=lambda item: (
            item["sampling_stratum"],
            item["policy_role"],
            _selection_hash(sampling_seed, item),
        ),
    ):
        position = pilot_positions[int(candidate["source_row_index"])]
        basic_values: dict[str, float | None] = {}
        for name in MODEL_VISIBLE_FIELDS:
            raw_value = pilot[name][position].as_py()
            value = float(raw_value) if raw_value is not None else None
            basic_values[name] = (
                value if value is not None and math.isfinite(value) else None
            )
        payload = teacher_payload(candidate=candidate, basic_values=basic_values)
        payload_hash = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        cache_id = hashlib.sha256(
            b"|".join(
                (
                    b"TEACHER_CACHE_V1",
                    candidate["source_row_id"].encode(),
                    candidate["policy_role"].encode(),
                    (candidate["unknown_rotation"] or "KNOWN").encode(),
                )
            )
        ).hexdigest()
        is_demo = candidate["policy_role"] == "POLICY_DEMO_DEVELOPMENT"
        teacher_requests.append(
            {
                "teacher_cache_id": cache_id,
                "teacher_input_payload_hash": payload_hash,
                "teacher_request_payload": payload,
            }
        )
        offline = {
            "teacher_cache_id": cache_id,
            "source_row_index": int(candidate["source_row_index"]),
            "source_row_id": candidate["source_row_id"],
            "source_fine_label": candidate["source_fine_label"],
            "canonical_label": candidate["canonical_label"],
            "source_partition": candidate["source_partition"],
            "private_group_digest": candidate["private_group_digest"],
            "sampling_stratum": candidate["sampling_stratum"],
            "policy_role": candidate["policy_role"],
            "confidence_bin": candidate["confidence_bin"],
            "unknown_rotation_if_any": candidate["unknown_rotation"],
            "teacher_input_payload_hash": payload_hash,
            "allowed_for_demonstration": is_demo,
            "allowed_for_imitation": is_demo,
            "allowed_for_policy_eval": not is_demo,
            "allowed_for_final_test": False,
            "reserved_from_known_classifier_fit": is_demo,
            "reserved_from_known_threshold_fit": not is_demo,
        }
        offline_records.append(offline)
        tracked_samples.append(
            {
                key: offline[key]
                for key in (
                    "teacher_cache_id",
                    "source_row_id",
                    "sampling_stratum",
                    "policy_role",
                    "unknown_rotation_if_any",
                    "teacher_input_payload_hash",
                    "allowed_for_demonstration",
                    "allowed_for_imitation",
                    "allowed_for_policy_eval",
                    "private_group_digest",
                    "reserved_from_known_classifier_fit",
                    "reserved_from_known_threshold_fit",
                )
            }
        )

    request_path = output_root / "teacher" / "teacher_cache_v1_requests.jsonl"
    offline_path = output_root / "teacher" / "teacher_cache_v1_offline_manifest.jsonl"
    write_jsonl(request_path, teacher_requests)
    write_jsonl(offline_path, offline_records)
    if len({item["source_row_id"] for item in offline_records}) != len(offline_records):
        raise RuntimeError("Teacher cache source identity overlap")
    if any(item["source_partition"] == "FINAL_TEST" for item in offline_records):
        raise RuntimeError("Teacher cache touches FINAL_TEST")
    if any(leak_keys(item["teacher_request_payload"]) for item in teacher_requests):
        raise RuntimeError("Teacher request leakage audit failed")
    group_roles: dict[str, set[str]] = defaultdict(set)
    for item in offline_records:
        group_roles[item["private_group_digest"]].add(item["policy_role"])
    private_group_role_overlap_n = sum(
        len(roles) > 1 for roles in group_roles.values()
    )
    if private_group_role_overlap_n:
        raise RuntimeError("Teacher cache private group crosses cache subpartitions")

    distribution = Counter(
        (item["sampling_stratum"], item["policy_role"]) for item in offline_records
    )
    class_distribution = Counter(
        (item["sampling_stratum"], item["canonical_label"]) for item in offline_records
    )
    confidence_distribution = Counter(
        (item["sampling_stratum"], item["confidence_bin"]) for item in offline_records
    )
    actual_manifest = {
        "schema_version": "TEACHER_CACHE_V1_SAMPLING_MANIFEST",
        "status": "READY_NO_RESPONSES",
        "target_n": 2000,
        "actual_n": len(tracked_samples),
        "sampling_seed": sampling_seed,
        "split_seed": seed,
        "source_artifact_sha256": SOURCE_ARTIFACT_SHA256,
        "source_row_id_contract": SOURCE_ROW_ID_VERSION,
        "sampling_design_version": design["schema_version"],
        "teacher_input_schema_version": TEACHER_INPUT_VERSION,
        "request_payload_external_path": str(request_path),
        "request_payload_sha256": sha256_file(request_path),
        "offline_manifest_external_path": str(offline_path),
        "offline_manifest_sha256": sha256_file(offline_path),
        "distribution": {
            f"{stratum}|{role}": count
            for (stratum, role), count in sorted(distribution.items())
        },
        "per_stratum_class_counts": {
            f"{stratum}|{label}": count
            for (stratum, label), count in sorted(class_distribution.items())
        },
        "per_stratum_confidence_counts": {
            f"{stratum}|{bin_name}": count
            for (stratum, bin_name), count in sorted(confidence_distribution.items())
        },
        "cell_allocation_audit": cell_allocation_audit,
        "final_test_contamination_n": 0,
        "source_row_id_overlap_n": 0,
        "teacher_payload_leakage_n": 0,
        "private_group_role_overlap_n": private_group_role_overlap_n,
        "reserved_private_group_n": len(group_roles),
        "reservation_contract": (
            "all rows sharing a listed private_group_digest inherit the sample's "
            "meta role and are excluded from Known classifier/threshold fitting "
            "as indicated; private group values never enter Teacher requests"
        ),
        "deepseek_calls": 0,
        "teacher_responses_generated": 0,
        "samples": tracked_samples,
    }
    tracked_path = repo_root / "configs/dataset_v4/teacher_cache_v1_sampling_manifest.json"
    write_json(tracked_path, actual_manifest)
    audit = {
        "schema_version": "TEACHER_CACHE_V1_SAMPLE_AUDIT",
        "status": "PASS",
        "sample_n": len(offline_records),
        "distribution": actual_manifest["distribution"],
        "class_distribution": actual_manifest["per_stratum_class_counts"],
        "confidence_distribution": actual_manifest["per_stratum_confidence_counts"],
        "final_test_contamination_n": 0,
        "teacher_payload_leakage_n": 0,
        "private_group_role_overlap_n": private_group_role_overlap_n,
        "request_payload_sha256": actual_manifest["request_payload_sha256"],
        "offline_manifest_sha256": actual_manifest["offline_manifest_sha256"],
    }
    write_json(output_root / "manifests/teacher_cache_v1_sample_audit.json", audit)
    return actual_manifest, audit


SEMANTIC_MECHANISMS = {
    "Benign": "ordinary bidirectional service behavior without attack-specific concentration or failure",
    "Backdoor": "persistent or repeated remote-control behavior that may require temporal context",
    "Credential": "repeated authentication attempts or credential-service interaction",
    "DDoS": "many-source or high-rate concentration against a destination/service",
    "DoS": "single/few-source resource exhaustion or repeated failure pressure",
    "Recon_Scanning": "destination/port diversity and short probe-like relation structure",
    "Web_Injection": "request behavior consistent with injection/XSS mechanisms at flow-observable granularity",
}


def semantic_pattern(label: str, family: str, role: str) -> str:
    mechanism = SEMANTIC_MECHANISMS[label]
    family_signal = {
        "BASIC": "current-flow protocol, byte/packet, flag, duration, retransmission, DNS/FTP and IAT summaries",
        "TEMPORAL": "strictly prior 10/60/300-second rate, count, burst and last-seen summaries",
        "RELATION": "strictly prior endpoint/port diversity, repeated-pair and fan-in/fan-out aggregates",
    }[family]
    if role == "MECHANISM_RELEVANT":
        return f"{family_signal} shows a strong pattern compatible with {mechanism}"
    if role == "AMBIGUOUS_OR_CONFOUNDED":
        return f"{family_signal} is elevated or unusual but is also plausible for benign load or another attack mechanism"
    return f"{family_signal} is absent, weak, or contradicts the expected pattern for {mechanism}"


def materialize_semantic_requests(repo_root: Path) -> dict[str, Any]:
    design = json.loads(
        (repo_root / "configs/dataset_v4/semantic_admissibility_reference_v1_design.json").read_text(
            encoding="utf-8"
        )
    )
    requests: list[dict[str, Any]] = []
    for label in design["class_or_mechanism_keys"]:
        for family in design["evidence_families"]:
            for pattern_role in design["pattern_roles"]:
                role = pattern_role["id"]
                payload = {
                    "schema_version": "SEMANTIC_ADMISSIBILITY_REQUEST_V1",
                    "class_or_mechanism": label,
                    "evidence_family": family,
                    "evidence_pattern": semantic_pattern(label, family, role),
                    "question_to_reviewer": (
                        "What class-level claim is semantically admissible from this pattern, "
                        "and what stronger claim is forbidden?"
                    ),
                    "response_schema": design["future_response_contract"],
                }
                digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
                requests.append(
                    {
                        "reference_id": f"sarv1_{digest[:20]}",
                        "pattern_role": role,
                        "request_payload_hash": digest,
                        "request_payload": payload,
                    }
                )
    coverage = Counter(
        (item["request_payload"]["class_or_mechanism"], item["request_payload"]["evidence_family"])
        for item in requests
    )
    if len(requests) != 63 or set(coverage.values()) != {3}:
        raise RuntimeError("semantic reference coverage is incomplete")
    manifest = {
        "schema_version": "SEMANTIC_ADMISSIBILITY_REFERENCE_V1_REQUEST_MANIFEST",
        "status": "READY_NO_RESPONSES",
        "request_n": len(requests),
        "class_n": len(design["class_or_mechanism_keys"]),
        "evidence_family_n": len(design["evidence_families"]),
        "patterns_per_class_family": 3,
        "operational_utility_gt": False,
        "deepseek_calls": 0,
        "responses_generated": 0,
        "requests": requests,
    }
    write_json(
        repo_root / "configs/dataset_v4/semantic_reference_v1_request_manifest.json",
        manifest,
    )
    return manifest


def unknown_rotation_manifest(scan: dict[str, Any]) -> dict[str, Any]:
    counts = scan["per_class_split_counts"]
    rotations = []
    for index, holdout in enumerate(UNKNOWN_ROTATIONS, start=1):
        known_classes = [label for label in CORE_CLASS_ORDER if label != holdout]
        heldout = counts[holdout]
        limited = any(int(heldout[partition]) == 0 for partition in PARTITIONS.values())
        rotations.append(
            {
                "rotation_id": f"UNKNOWN_ROTATION_V1_R{index}",
                "unknown_class": holdout,
                "known_classes": known_classes,
                "known_classifier_train_n": sum(
                    int(counts[label]["TRAIN"]) for label in known_classes
                ),
                "known_threshold_validation_n": sum(
                    int(counts[label]["VALIDATION"]) for label in known_classes
                ),
                "unknown_meta_development_n": int(heldout["TRAIN"])
                + int(heldout["VALIDATION"]),
                "unknown_final_evaluation_n": int(heldout["FINAL_TEST"]),
                "unknown_in_known_classifier_train_n": 0,
                "unknown_in_known_threshold_validation_n": 0,
                "final_unknown_used_for_threshold_tuning": False,
                "status": "ROTATION_LIMITED" if limited else "PASS",
            }
        )
    return {
        "schema_version": "UNKNOWN_ROTATION_MANIFEST_V1",
        "status": "PASS"
        if all(item["status"] == "PASS" for item in rotations)
        else "PASS_WITH_LIMITATIONS",
        "whole_class_heldout": True,
        "final_test_threshold_tuning": "FORBIDDEN",
        "rotations": rotations,
    }


def tracked_split_manifest(
    *,
    scan: dict[str, Any],
    identity_audit: dict[str, Any],
    row_manifest: Path,
    seed: int,
) -> dict[str, Any]:
    return {
        "schema_version": "DATASET_V4_SPLIT_MANIFEST_V1",
        "status": "PASS",
        "dataset_v4_core": "NF3-ToN-IoT",
        "source_artifact_sha256": SOURCE_ARTIFACT_SHA256,
        "canonical_taxonomy_version": "CANONICAL_TAXONOMY_V1",
        "canonical_taxonomy": list(CORE_CLASS_ORDER),
        "source_mapping": FINE_TO_CANONICAL,
        "source_row_id_contract": {
            "version": SOURCE_ROW_ID_VERSION,
            "definition": (
                "SHA256(NF3_TON_OBSERVATION_V1 NUL artifact_sha256 NUL "
                "zero_based_source_row_index NUL canonical_row_digest)"
            ),
            "canonical_row_digest": (
                "SHA256 of canonical JSON array of 55 UTF-8 CSV cell strings in official header order"
            ),
            "shuffle_independent": True,
        },
        "split_protocol": SPLIT_PROTOCOL,
        "split_seed": seed,
        "generator_version": GENERATOR_VERSION,
        "activity_group": (
            "BLAKE2b-128(NF3_TON_ACTIVITY_GROUP_V1 + five-minute UTC block + "
            "unordered raw endpoint pair); raw values remain backend-only"
        ),
        "assignment": (
            "stable label-free group hash 70/15/15 TRAIN/VALIDATION/FINAL_TEST; "
            "canonical labels are used only for offline support audits"
        ),
        "evidence_history_scope": HISTORY_SCOPE,
        "partition_counts": scan["partition_counts"],
        "per_class_split_counts": scan["per_class_split_counts"],
        "time_ranges_ms": scan["time_ranges_ms"],
        "group_counts": identity_audit["eligible_group_counts"],
        "exact_duplicate_n": identity_audit["exact_duplicate_n"],
        "duplicate_group_cross_split_n": identity_audit[
            "duplicate_group_cross_split_n"
        ],
        "activity_group_cross_split_n": identity_audit["activity_group_cross_split_n"],
        "invalid_critical_row_n": scan["invalid_critical_row_n"],
        "unknown_canonical_label_n": scan["unknown_canonical_label_n"],
        "row_manifest_external_path": str(row_manifest),
        "row_manifest_size_bytes": row_manifest.stat().st_size,
        "row_manifest_sha256": sha256_file(row_manifest),
        "rebuild_command": (
            "python tools/finalize_dataset_v4_split.py --repo-root . "
            "--archive /root/autodl-tmp/dataset_v4_nf3_gate/downloads/nf3_ton.zip "
            "--output-root /root/autodl-tmp/processed/dataset_v4_nf3_ton_v1"
        ),
        "formal_invariants": {
            "train_validation_source_overlap": 0,
            "train_final_test_source_overlap": 0,
            "validation_final_test_source_overlap": 0,
            "duplicate_group_cross_split": identity_audit[
                "duplicate_group_cross_split_n"
            ],
            "activity_group_cross_split": identity_audit["activity_group_cross_split_n"],
            "all_core_classes_each_partition": all(
                int(scan["per_class_split_counts"][label][partition]) > 0
                for label in CORE_CLASS_ORDER
                for partition in PARTITIONS.values()
            ),
            "within_split_past_only_history": True,
        },
    }


def report_payload(
    *,
    split_manifest: dict[str, Any],
    rotation_manifest: dict[str, Any],
    reference_audit: dict[str, Any],
    teacher_manifest: dict[str, Any],
    semantic_manifest: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "DATASET_V4_FINAL_SPLIT_REPORT_V1",
        "status": "PASS",
        "dataset_v4_final_split_status": "PASS",
        "dataset_v4_formalization_status": "PASS",
        "split": split_manifest,
        "unknown_rotations": rotation_manifest,
        "reference_state": reference_audit,
        "teacher_cache": {
            key: teacher_manifest[key]
            for key in (
                "status",
                "target_n",
                "actual_n",
                "sampling_seed",
                "split_seed",
                "request_payload_sha256",
                "offline_manifest_sha256",
                "distribution",
                "per_stratum_class_counts",
                "per_stratum_confidence_counts",
                "cell_allocation_audit",
                "final_test_contamination_n",
                "source_row_id_overlap_n",
                "teacher_payload_leakage_n",
                "private_group_role_overlap_n",
                "reserved_private_group_n",
                "deepseek_calls",
                "teacher_responses_generated",
            )
        },
        "semantic_reference": {
            "status": semantic_manifest["status"],
            "request_n": semantic_manifest["request_n"],
            "deepseek_calls": semantic_manifest["deepseek_calls"],
            "responses_generated": semantic_manifest["responses_generated"],
        },
        "deepseek_calls": 0,
        "qwen_calls": 0,
        "model_b_training": False,
        "formal_sft": False,
        "continual_learning": False,
        "rl": False,
        "teacher_demo_pool_status": "PASS",
        "teacher_policy_eval_pool_status": "PASS",
        "teacher_cache_v1_ready_to_generate": True,
        "semantic_reference_v1_ready_to_generate": True,
        "model_b_low_cost_gates_authorized": True,
        "next_action": "GENERATE_PREPRICE_DEEPSEEK_CACHE_AND_SEMANTIC_REFERENCE",
    }


def validate_final_acceptance(
    *,
    split_manifest: dict[str, Any],
    rotation_manifest: dict[str, Any],
    reference_audit: dict[str, Any],
    teacher_manifest: dict[str, Any],
    semantic_manifest: dict[str, Any],
) -> None:
    """Fail closed before any tracked artifact is described as formally ready."""

    invariants = split_manifest["formal_invariants"]
    failures: list[str] = []
    for key in (
        "train_validation_source_overlap",
        "train_final_test_source_overlap",
        "validation_final_test_source_overlap",
        "duplicate_group_cross_split",
        "activity_group_cross_split",
    ):
        if int(invariants[key]) != 0:
            failures.append(f"{key}={invariants[key]}")
    if not bool(invariants["all_core_classes_each_partition"]):
        failures.append("not_all_core_classes_each_partition")
    if not bool(invariants["within_split_past_only_history"]):
        failures.append("history_scope_not_strict")
    if rotation_manifest["status"] != "PASS":
        failures.append(f"rotation_status={rotation_manifest['status']}")
    if any(
        int(item["unknown_in_known_classifier_train_n"]) != 0
        or int(item["unknown_in_known_threshold_validation_n"]) != 0
        or bool(item["final_unknown_used_for_threshold_tuning"])
        for item in rotation_manifest["rotations"]
    ):
        failures.append("unknown_rotation_isolation")
    if (
        int(reference_audit["final_test_reference_n"]) != 0
        or int(reference_audit["unknown_rotation_group_overlap_n"]) != 0
        or not bool(reference_audit["no_self_training"])
        or reference_audit["strict_history_scope"] != HISTORY_SCOPE
    ):
        failures.append("reference_state_isolation")
    expected_distribution = {
        "BASIC_SUFFICIENT_KNOWN|POLICY_DEMO_DEVELOPMENT": 450,
        "BASIC_SUFFICIENT_KNOWN|POLICY_META_EVALUATION": 300,
        "RECOVERABLE_KNOWN|POLICY_DEMO_DEVELOPMENT": 510,
        "RECOVERABLE_KNOWN|POLICY_META_EVALUATION": 340,
        "TRUE_UNKNOWN_ROTATIONS|POLICY_DEMO_DEVELOPMENT": 240,
        "TRUE_UNKNOWN_ROTATIONS|POLICY_META_EVALUATION": 160,
    }
    if int(teacher_manifest["actual_n"]) != 2000:
        failures.append(f"teacher_actual_n={teacher_manifest['actual_n']}")
    if teacher_manifest["distribution"] != expected_distribution:
        failures.append("teacher_quota_distribution")
    for key in (
        "final_test_contamination_n",
        "source_row_id_overlap_n",
        "teacher_payload_leakage_n",
        "private_group_role_overlap_n",
        "deepseek_calls",
        "teacher_responses_generated",
    ):
        if int(teacher_manifest[key]) != 0:
            failures.append(f"{key}={teacher_manifest[key]}")
    if len({item["source_row_id"] for item in teacher_manifest["samples"]}) != 2000:
        failures.append("teacher_sample_identity_uniqueness")
    if any(
        bool(item["allowed_for_demonstration"])
        != bool(item["allowed_for_imitation"])
        or bool(item["allowed_for_policy_eval"])
        == bool(item["allowed_for_imitation"])
        for item in teacher_manifest["samples"]
    ):
        failures.append("teacher_sample_role_flags")
    if (
        semantic_manifest["status"] != "READY_NO_RESPONSES"
        or int(semantic_manifest["request_n"]) != 63
        or int(semantic_manifest["deepseek_calls"]) != 0
        or int(semantic_manifest["responses_generated"]) != 0
    ):
        failures.append("semantic_reference_readiness")
    if failures:
        raise RuntimeError(f"Dataset-v4 final acceptance failed: {failures}")


def render_report(report: dict[str, Any]) -> str:
    split = report["split"]
    rows = []
    for label in split["canonical_taxonomy"]:
        counts = split["per_class_split_counts"][label]
        rows.append(
            f"| {label} | {counts['TRAIN']:,} | {counts['VALIDATION']:,} | "
            f"{counts['FINAL_TEST']:,} |"
        )
    rotations = []
    for item in report["unknown_rotations"]["rotations"]:
        rotations.append(
            f"| {item['rotation_id']} | {item['unknown_class']} | "
            f"{item['unknown_meta_development_n']:,} | "
            f"{item['unknown_final_evaluation_n']:,} | {item['status']} |"
        )
    teacher = report["teacher_cache"]
    return f"""# Dataset-v4 Final Split Report

> Status: `PASS`
>
> Scope: deterministic NF3-ToN Dataset-v4 split, whole-class Unknown rotations,
> low-cost tree reference states, and offline Teacher/semantic request manifests.
> No DeepSeek, Qwen, Model B training, SFT, continual learning, RL, download, or
> raw-PCAP processing was performed.

## 1. Frozen result

```text
DATASET_V4_FINAL_SPLIT_STATUS=PASS
DATASET_V4_CORE=NF3-ToN-IoT
SOURCE_ARTIFACT_SHA256={SOURCE_ARTIFACT_SHA256}
CANONICAL_TAXONOMY_V1={','.join(split['canonical_taxonomy'])}
SOURCE_ROW_ID_CONTRACT={SOURCE_ROW_ID_VERSION}
SPLIT_PROTOCOL={split['split_protocol']}
SPLIT_SEED={split['split_seed']}
SPLIT_MANIFEST_SHA256={split['row_manifest_sha256']}
EVIDENCE_HISTORY_SCOPE={split['evidence_history_scope']}
```

The formal target remains one official complete bidirectional flow row. Source
identity binds the frozen artifact, original zero-based row ordinal, and
canonical row digest; dataframe order cannot change it.

## 2. Standard split

| Canonical class | TRAIN | VALIDATION | FINAL_TEST |
| --- | ---: | ---: | ---: |
{chr(10).join(rows)}

Totals: TRAIN `{split['partition_counts']['TRAIN']:,}`, VALIDATION
`{split['partition_counts']['VALIDATION']:,}`, FINAL_TEST
`{split['partition_counts']['FINAL_TEST']:,}`. Assignment is a stable 70/15/15
hash of a five-minute temporal block plus unordered endpoint pair. Label is used
only to audit support, never in the group key or runtime Evidence.

The Git-external row manifest is `{split['row_manifest_external_path']}`
(`{split['row_manifest_size_bytes']:,}` bytes; SHA256
`{split['row_manifest_sha256']}`). Its rules, counts and rebuild command are
tracked in `configs/dataset_v4/dataset_v4_split_manifest_v1.json`.

## 3. Identity, duplicate and validity audit

```text
EXACT_DUPLICATE_N={split['exact_duplicate_n']}
INVALID_CRITICAL_ROW_N={split['invalid_critical_row_n']}
UNKNOWN_CANONICAL_LABEL_N={split['unknown_canonical_label_n']}
DUPLICATE_GROUP_CROSS_SPLIT_N={split['duplicate_group_cross_split_n']}
ACTIVITY_GROUP_CROSS_SPLIT_N={split['activity_group_cross_split_n']}
```

`mitm` and `ransomware` remain in source provenance and label-free history
eligibility but are not Dataset-v4 targets. This avoids using GT to filter
runtime neighbors while preserving the frozen seven-class taxonomy.

## 4. Evidence history isolation

Temporal and Relation contributors must be in the target's same standard split,
must satisfy `contributor.FLOW_END_MILLISECONDS <
target.FLOW_START_MILLISECONDS`, and must fall within the fixed 10/60/300-second
window. Equal-time, overlapping, future and cross-split rows are excluded. Raw
IP/port/time values remain lookup-only and GT never selects a neighbor.

## 5. Whole-class Unknown rotations

| Rotation | Unknown class | Development/meta observations | Sealed FINAL_TEST observations | Status |
| --- | --- | ---: | ---: | --- |
{chr(10).join(rotations)}

For each rotation the Unknown class is absent from Known classifier training and
Known threshold-tuning data. FINAL_TEST Unknown labels never tune a threshold.

## 6. Reference state and Teacher cache

The bounded reference pipeline uses Random Forests only. TRAIN states use
group-disjoint OOF predictions; VALIDATION states use models fit only on TRAIN;
whole-class Unknown states are predicted by a classifier that never saw the
held-out class. Strict full-release, within-split past-only history is used.
This materialization is not Model B training or a formal model comparison.

```text
REFERENCE_BASIC_SUFFICIENT_KNOWN_N={report['reference_state']['basic_sufficient_known_n']}
REFERENCE_RECOVERABLE_KNOWN_N={report['reference_state']['recoverable_known_n']}
TEACHER_CACHE_V1_N={teacher['actual_n']}
TEACHER_CACHE_FINAL_TEST_CONTAMINATION={teacher['final_test_contamination_n']}
TEACHER_PAYLOAD_LEAKAGE_N={teacher['teacher_payload_leakage_n']}
TEACHER_RESPONSES_GENERATED={teacher['teacher_responses_generated']}
DEEPSEEK_CALLS={report['deepseek_calls']}
```

The 1,200 policy-demo-development rows may support optional demonstration or
imitation. The 800 policy-meta-evaluation rows are evaluation-only. No sample
touches FINAL_TEST, and Teacher request payloads contain no GT, recoverability,
true-Unknown flag, future Evidence, split, raw endpoint/time, or utility target.
Capacity-limited class/confidence cells are recorded in the tracked allocation
audit and redistributed deterministically without duplicating rows.

## 7. Semantic reference

The tracked request manifest contains 63 requests: seven class/mechanism keys ×
three B1 Evidence families × three pattern roles. It is ready for a separately
authorized review call, contains no responses, and can never become operational
utility GT.

## 8. Acceptance

```text
DATASET_V4_FORMALIZATION_STATUS=PASS
TEACHER_CACHE_V1_SAMPLE_MANIFEST_READY=true
TEACHER_CACHE_V1_READY_TO_GENERATE=true
SEMANTIC_REFERENCE_REQUEST_MANIFEST_READY=true
SEMANTIC_REFERENCE_V1_READY_TO_GENERATE=true
MODEL_B_LOW_COST_GATES_AUTHORIZED=true
NEXT_ACTION=GENERATE_PREPRICE_DEEPSEEK_CACHE_AND_SEMANTIC_REFERENCE
```

The next action still requires explicit researcher authorization. This report
does not itself authorize API calls or Model B execution.
"""


def run(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = args.repo_root.resolve()
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    pilot = pq.read_table(args.pilot)
    pilot_indices = {int(value) for value in pilot["source_row_index"].to_pylist()}
    scan, pilot_meta = scan_official_csv(
        archive=args.archive,
        output_root=output_root,
        pilot_indices=pilot_indices,
        seed=args.seed,
        batch_size=args.batch_size,
    )
    row_manifest = output_root / "rows/dataset_v4_row_manifest_v1.parquet"
    identity_audit = audit_duplicates_and_groups(row_manifest)
    core_reference_indices = sorted(
        index
        for index, meta in pilot_meta.items()
        if meta.critical_valid
        and meta.canonical_label is not None
        and meta.partition_code != PARTITION_CODES["FINAL_TEST"]
    )
    known_cache = output_root / "reference/known_reference_records.jsonl"
    unknown_cache = output_root / "reference/unknown_reference_records.jsonl"
    reference_audit_path = output_root / "manifests/reference_state_audit.json"
    if known_cache.exists() and unknown_cache.exists() and reference_audit_path.exists():
        known_records = [
            json.loads(line) for line in known_cache.read_text(encoding="utf-8").splitlines()
        ]
        unknown_values = [
            json.loads(line) for line in unknown_cache.read_text(encoding="utf-8").splitlines()
        ]
        unknown_records = {
            (int(item["source_row_index"]), str(item["unknown_rotation"])): item
            for item in unknown_values
        }
        reference_audit = json.loads(reference_audit_path.read_text(encoding="utf-8"))
        for path, key in (
            (known_cache, "known_reference_records_sha256"),
            (unknown_cache, "unknown_reference_records_sha256"),
        ):
            if reference_audit.get(key) != sha256_file(path):
                raise RuntimeError(f"reference cache digest mismatch: {path}")
        previous_seed = reference_audit.get("reference_seed")
        if previous_seed is not None and int(previous_seed) != args.seed:
            raise RuntimeError("reference cache seed mismatch")
        reference_audit["reference_seed"] = args.seed
        write_json(reference_audit_path, reference_audit)
    else:
        history, history_names = materialize_strict_history(
            row_manifest, pilot_meta, core_reference_indices
        )
        known_records, unknown_records, reference_audit = reference_predictions(
            pilot=pilot,
            pilot_meta=pilot_meta,
            history=history,
            target_indices=core_reference_indices,
            seed=args.seed,
        )
        reference_audit["history_feature_names"] = history_names
        write_jsonl(known_cache, known_records)
        write_jsonl(unknown_cache, unknown_records.values())
        reference_audit["known_reference_records_sha256"] = sha256_file(known_cache)
        reference_audit["unknown_reference_records_sha256"] = sha256_file(unknown_cache)
        reference_audit["reference_seed"] = args.seed
        write_json(reference_audit_path, reference_audit)
    teacher_manifest, _ = materialize_teacher_samples(
        repo_root=repo_root,
        output_root=output_root,
        pilot=pilot,
        pilot_meta=pilot_meta,
        known_records=known_records,
        unknown_records=unknown_records,
        seed=args.seed,
    )
    semantic_manifest = materialize_semantic_requests(repo_root)
    rotation_manifest = unknown_rotation_manifest(scan)
    write_json(repo_root / "configs/dataset_v4/unknown_rotation_manifest_v1.json", rotation_manifest)
    split_manifest = tracked_split_manifest(
        scan=scan,
        identity_audit=identity_audit,
        row_manifest=row_manifest,
        seed=args.seed,
    )
    write_json(repo_root / "configs/dataset_v4/dataset_v4_split_manifest_v1.json", split_manifest)
    validate_final_acceptance(
        split_manifest=split_manifest,
        rotation_manifest=rotation_manifest,
        reference_audit=reference_audit,
        teacher_manifest=teacher_manifest,
        semantic_manifest=semantic_manifest,
    )
    report = report_payload(
        split_manifest=split_manifest,
        rotation_manifest=rotation_manifest,
        reference_audit=reference_audit,
        teacher_manifest=teacher_manifest,
        semantic_manifest=semantic_manifest,
    )
    report_root = repo_root / "reports/dataset_v4"
    write_json(report_root / "dataset_v4_final_split_report.json", report)
    (report_root / "dataset_v4_final_split_report.md").write_text(
        render_report(report), encoding="utf-8"
    )
    write_json(output_root / "manifests/final_report.json", report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--archive",
        type=Path,
        default=Path("/root/autodl-tmp/dataset_v4_nf3_gate/downloads/nf3_ton.zip"),
    )
    parser.add_argument(
        "--pilot",
        type=Path,
        default=Path("/root/autodl-tmp/dataset_v4_nf3_gate/artifacts/nf3_stratified_pilot.parquet"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("/root/autodl-tmp/processed/dataset_v4_nf3_ton_v1"),
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SPLIT_SEED)
    parser.add_argument("--batch-size", type=int, default=100_000)
    return parser.parse_args()


def main() -> int:
    report = run(parse_args())
    split = report["split"]
    rotations = report["unknown_rotations"]
    teacher = report["teacher_cache"]
    semantic = report["semantic_reference"]
    print("DATASET_V4_FINAL_SPLIT_STATUS=PASS")
    print("DATASET_V4_CORE=NF3-ToN-IoT")
    print(f"SOURCE_ARTIFACT_SHA256={SOURCE_ARTIFACT_SHA256}")
    print(f"CANONICAL_TAXONOMY_V1={','.join(CORE_CLASS_ORDER)}")
    print(f"SOURCE_ROW_ID_CONTRACT={SOURCE_ROW_ID_VERSION}")
    print(f"TRAIN_N={split['partition_counts']['TRAIN']}")
    print(f"VALIDATION_N={split['partition_counts']['VALIDATION']}")
    print(f"FINAL_TEST_N={split['partition_counts']['FINAL_TEST']}")
    print(
        "PER_CLASS_SPLIT_COUNTS="
        + canonical_json_bytes(split["per_class_split_counts"]).decode("utf-8")
    )
    print(f"SPLIT_PROTOCOL={split['split_protocol']}")
    print(f"SPLIT_SEED={split['split_seed']}")
    print(f"SPLIT_MANIFEST_SHA256={split['row_manifest_sha256']}")
    print(f"EXACT_DUPLICATE_N={split['exact_duplicate_n']}")
    print(f"INVALID_CRITICAL_ROW_N={split['invalid_critical_row_n']}")
    print(f"UNKNOWN_CANONICAL_LABEL_N={split['unknown_canonical_label_n']}")
    print(f"EVIDENCE_HISTORY_SCOPE={split['evidence_history_scope']}")
    print(f"UNKNOWN_ROTATIONS={','.join(UNKNOWN_ROTATIONS)}")
    print(f"UNKNOWN_ROTATION_STATUS={rotations['status']}")
    print(f"TEACHER_DEMO_POOL_STATUS={report['teacher_demo_pool_status']}")
    print(f"TEACHER_POLICY_EVAL_POOL_STATUS={report['teacher_policy_eval_pool_status']}")
    print("TEACHER_CACHE_V1_SAMPLE_MANIFEST_READY=true")
    print(f"TEACHER_CACHE_V1_N={teacher['actual_n']}")
    print("TEACHER_CACHE_FINAL_TEST_CONTAMINATION=false")
    print("SEMANTIC_REFERENCE_REQUEST_MANIFEST_READY=true")
    print("DATASET_V4_FORMALIZATION_STATUS=PASS")
    print("TEACHER_CACHE_V1_READY_TO_GENERATE=true")
    print("SEMANTIC_REFERENCE_V1_READY_TO_GENERATE=true")
    print("MODEL_B_LOW_COST_GATES_AUTHORIZED=true")
    print(f"NEXT_ACTION={report['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
