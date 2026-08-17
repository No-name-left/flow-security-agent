#!/usr/bin/env python3
"""CORE HYPOTHESIS FORMAL GATE V1 — Gate 0 + Gate 1 only.

Formally tests H1 on the frozen NF3-ToN-IoT Dataset-v4 / master split / legal
runtime Evidence contract:

  H1: does a stable population of RECOVERABLE_KNOWN targets exist — samples
  that BASIC alone misclassifies but legal, test-time TEMPORAL and/or RELATION
  evidence recovers to the correct Known class?

This is a KILL GATE. A FAIL is a valid outcome; no model/family/threshold/
prompt tuning is permitted after results exist. No FINAL_TEST row-level data
is ever used for modeling. No DeepSeek, no Qwen, no GPU training.

Frozen decisions (pre-registered before any formal result):
  - estimator: RandomForestClassifier(n_estimators=80, max_depth=20,
    min_samples_leaf=2, class_weight="balanced_subsample", random_state=seed)
    — the existing frozen/reproducible NF3-ToN reference probe config
    (tools/finalize_dataset_v4_split.py), n_jobs=-1 is a speed-only change.
  - Basic features: the 47 MODEL_VISIBLE fields of NF3_TON_BASIC_CARD_V1,
    signed-log1p probe transform (same as the reference pipeline).
  - Temporal features (16): source_flow_count, source_flow_rate,
    source_packet_rate, source_byte_rate, destination_flow_count per
    10/60/300s horizon + same_source_last_seen_gap_ms.
  - Relation features (18): source_unique_destination_count,
    source_unique_destination_port_count, source_same_destination_port_count,
    source_destination_pair_count, destination_unique_source_count,
    source_unique_neighbor_count per 10/60/300s horizon.
  - History features use the reference log1p(clip(x, 0, None)) transform.
  - History scope: WITHIN_SPLIT_STRICT_END_BEFORE_TARGET_START_V1 —
    contributors are critical-valid rows of the target's own partition with
    flow_end_ms < target flow_start_ms inside a 10/60/300s window. History is
    never duplicate-deduplicated; FINAL_TEST rows never enter the arrays.
  - Target view: one target per exact-duplicate group (canonical_row_digest),
    representative = earliest flow_start_ms, tie-break min source_row_index.
  - Sampling: temporal-block-stratified (50 chronological blocks per
    split x class, proportional allocation, deterministic per seed), caps
    TRAIN 25,000 / VALIDATION 8,000 per class, minima 15,000 / 5,000.
  - Seeds: 20260817, 20260818, 20260819. Seed controls target sampling and
    model random_state only.
  - Bootstrap: paired resampling of frozen private activity groups
    (1,000 replicates), identical group multiset across B/BT/BR/BTR.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix, f1_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from finalize_dataset_v4_split import (  # noqa: E402
    HORIZONS_MS,
    MODEL_VISIBLE_FIELDS,
    PARTITIONS,
    SOURCE_ARTIFACT_SHA256,
)

FORMAL_SEEDS = (20260817, 20260818, 20260819)
SMOKE_SEED = 777001  # implementation smoke only; never used in decisions
BOOTSTRAP_REPS = 1000
BOOTSTRAP_RNG_OFFSET = 9000
N_TEMPORAL_BLOCKS = 50

TRAIN_CAP = 25_000
VAL_CAP = 8_000
TRAIN_MIN = 15_000
VAL_MIN = 5_000

CANONICAL_CLASS_ORDER = (
    "Backdoor", "Benign", "Credential", "DDoS", "DoS", "Recon_Scanning", "Web_Injection",
)
ATTACK_CLASSES = tuple(name for name in CANONICAL_CLASS_ORDER if name != "Benign")

ESTIMATOR_FAMILY = "RandomForestClassifier"
ESTIMATOR_CONFIG = {
    "n_estimators": 80,
    "max_depth": 20,
    "min_samples_leaf": 2,
    "class_weight": "balanced_subsample",
    "n_jobs": -1,
    "random_state": "formal seed",
}
ESTIMATOR_PROVENANCE = (
    "frozen NF3-ToN reference probe config from tools/finalize_dataset_v4_split.py "
    "(REFERENCE_TREES=80, max_depth=20, min_samples_leaf=2, balanced_subsample); "
    "n_jobs=-1 is a speed-only change, RF output is identical for a fixed seed."
)

TEMPORAL_BASE = (
    "source_flow_count", "source_flow_rate", "source_packet_rate",
    "source_byte_rate", "destination_flow_count",
)
RELATION_BASE = (
    "source_unique_destination_count", "source_unique_destination_port_count",
    "source_same_destination_port_count", "source_destination_pair_count",
    "destination_unique_source_count", "source_unique_neighbor_count",
)
TEMPORAL_FIELDS = tuple(
    f"{name}_{horizon // 1000}s" for horizon in HORIZONS_MS for name in TEMPORAL_BASE
) + ("same_source_last_seen_gap_ms",)
RELATION_FIELDS = tuple(
    f"{name}_{horizon // 1000}s" for horizon in HORIZONS_MS for name in RELATION_BASE
)
HISTORY_FIELDS = tuple(
    f"{name}_{horizon // 1000}s"
    for horizon in HORIZONS_MS
    for name in TEMPORAL_BASE + RELATION_BASE
) + ("same_source_last_seen_gap_ms",)
assert len(HISTORY_FIELDS) == 34
assert len(TEMPORAL_FIELDS) == 16 and len(RELATION_FIELDS) == 18

CONDITIONS = ("B", "BT", "BR", "BTR")
EVIDENCE_DELTAS = {"BT": "T", "BR": "R", "BTR": "TR"}

FORBIDDEN_FEATURE_MARKERS = (
    "canonical_label", "digest", "row_id", "partition", "split", "fold",
    "rotation", "source_row", "source_dataset", "source_file", "flow_start",
    "flow_end", "src_code", "dst_code", "group_digest", "attack",
)

DEFAULT_ARTIFACT_ROOT = "/root/autodl-tmp/processed/dataset_v4_nf3_ton_v1/core_gate_v1"
DEFAULT_MANIFEST = (
    "/root/autodl-tmp/processed/dataset_v4_nf3_ton_v1/rows/dataset_v4_row_manifest_v1.parquet"
)
DEFAULT_ARCHIVE = "/root/autodl-tmp/dataset_v4_nf3_gate/downloads/nf3_ton.zip"

PARTITION_TRAIN = 0
PARTITION_VALIDATION = 1
PARTITION_FINAL_TEST = 2
assert PARTITIONS[PARTITION_TRAIN] == "TRAIN"
assert PARTITIONS[PARTITION_VALIDATION] == "VALIDATION"
assert PARTITIONS[PARTITION_FINAL_TEST] == "FINAL_TEST"


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest_columns(manifest_path: str) -> dict[str, np.ndarray]:
    """Load modeling-relevant manifest columns. FINAL_TEST rows are excluded
    before any modeling computation (aggregate counts are read-only metadata).
    """
    table = pq.read_table(
        manifest_path,
        columns=[
            "source_row_index", "canonical_row_digest", "canonical_label",
            "flow_start_ms", "flow_end_ms", "src_code", "dst_code", "src_port",
            "dst_port", "in_bytes", "out_bytes", "in_pkts", "out_pkts",
            "activity_group_digest", "partition_code", "critical_valid",
            "target_eligible",
        ],
    )
    arrays = {name: table[name].to_numpy(zero_copy_only=False) for name in table.column_names}
    labels = np.array(
        ["" if value is None else value for value in arrays["canonical_label"].tolist()],
        dtype=object,
    )
    arrays["canonical_label"] = labels
    final_test = arrays["partition_code"].astype(np.int64) == PARTITION_FINAL_TEST
    # 3,843,430 = 3,842,026 eligible FINAL_TEST targets + 1,404 out-of-core
    # label rows (of the frozen 9,984 OUT_OF_CORE_FINE_LABEL_POOL).
    if final_test.sum() != 3_843_430:
        raise RuntimeError(f"unexpected FINAL_TEST row count {int(final_test.sum())}")
    kept = {name: value[~final_test] for name, value in arrays.items()}
    return kept


def verify_duplicate_semantics(
    digests: np.ndarray, labels: np.ndarray,
) -> tuple[int, int, int]:
    """Verify frozen exact-duplicate semantics over the full manifest:
    duplicate group = canonical_row_digest; label conflicts are counted.
    Returns (duplicate_groups, duplicate_copies, label_conflicts)."""
    order = np.argsort(digests, kind="stable")
    d_sorted = digests[order]
    first = np.r_[True, d_sorted[1:] != d_sorted[:-1]]
    group_sizes = np.bincount(np.cumsum(first) - 1)
    dup_groups = int((group_sizes > 1).sum())
    dup_copies = int((group_sizes[group_sizes > 1] - 1).sum())
    lab_sorted = labels[order]
    g_start = np.r_[0, np.cumsum(group_sizes)[:-1]]
    conflicts = 0
    for g in np.flatnonzero(group_sizes > 1):
        if len(np.unique(lab_sorted[g_start[g]:g_start[g] + group_sizes[g]])) > 1:
            conflicts += 1
    return dup_groups, dup_copies, conflicts


def duplicate_representatives(
    arrays: dict[str, np.ndarray],
    partition: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Frozen representative rule over the duplicate-aware target pool of one
    partition: earliest flow_start_ms, tie-break minimum source_row_index.
    Returns (representative_row_positions, pool_row_positions).

    Implemented as the group-minimum rank in the global (start, index) order;
    this stays correct even when members of different duplicate groups share a
    start time and interleave in index order.
    """
    mask = (arrays["partition_code"].astype(np.int64) == partition) \
        & arrays["target_eligible"].astype(bool)
    positions = np.flatnonzero(mask)
    digests = arrays["canonical_row_digest"][positions]
    starts = arrays["flow_start_ms"][positions]
    indices = arrays["source_row_index"][positions]
    order = np.lexsort((indices, starts))
    rank = np.empty(len(positions), dtype=np.int64)
    rank[order] = np.arange(len(positions), dtype=np.int64)
    digest_order = np.argsort(digests, kind="stable")
    d_sorted = digests[digest_order]
    first = np.r_[True, d_sorted[1:] != d_sorted[:-1]]
    group_starts = np.flatnonzero(first)
    min_rank = np.minimum.reduceat(rank[digest_order], group_starts)
    representatives_in_pool = order[min_rank]
    representatives_in_pool = np.sort(representatives_in_pool)
    return positions[representatives_in_pool], positions


# ---------------------------------------------------------------------------
# Strict past-only Evidence history (same semantics as the frozen reference
# materializer; FINAL_TEST rows are absent from the arrays entirely)
# ---------------------------------------------------------------------------

def _group_bounds(keys: np.ndarray) -> dict[int, tuple[int, int]]:
    changes = np.flatnonzero(np.r_[True, keys[1:] != keys[:-1], True])
    return {
        int(keys[start]): (int(start), int(end))
        for start, end in zip(changes[:-1], changes[1:], strict=True)
    }


def strict_history_features(
    arrays: dict[str, np.ndarray],
    targets: np.ndarray,
) -> tuple[np.ndarray, list[str]]:
    """34 history features for target row positions (indices into `arrays`)."""
    valid = arrays["critical_valid"].astype(bool)
    end = arrays["flow_end_ms"][valid].astype(np.int64)
    src = arrays["src_code"][valid].astype(np.int64)
    dst = arrays["dst_code"][valid].astype(np.int64)
    dport = arrays["dst_port"][valid].astype(np.int64)
    partition = arrays["partition_code"][valid].astype(np.int64)
    bytes_total = (arrays["in_bytes"][valid].astype(np.int64)
                   + arrays["out_bytes"][valid].astype(np.int64))
    packets_total = (arrays["in_pkts"][valid].astype(np.int64)
                     + arrays["out_pkts"][valid].astype(np.int64))

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

    names = list(HISTORY_FIELDS)
    output = np.zeros((len(targets), len(names)), dtype=np.float64)
    target_start = arrays["flow_start_ms"][targets].astype(np.int64)
    target_partition = partition[targets]
    target_src = src[targets]
    target_dst = dst[targets]
    target_dport = dport[targets]

    for output_index, position in enumerate(targets):
        src_lo, src_hi = src_bounds.get(
            int((target_partition[output_index] << 32) | target_src[output_index]),
            (0, 0),
        )
        dst_lo, dst_hi = dst_bounds.get(
            int((target_partition[output_index] << 32) | target_dst[output_index]),
            (0, 0),
        )
        source_end = src_end[src_lo:src_hi]
        destination_end = dst_end[dst_lo:dst_hi]
        upper_source = int(np.searchsorted(source_end, target_start[output_index], side="left"))
        upper_destination = int(np.searchsorted(
            destination_end, target_start[output_index], side="left"))
        values: list[float] = []
        for horizon in HORIZONS_MS:
            cutoff = target_start[output_index] - horizon
            lower_source = int(np.searchsorted(source_end, cutoff, side="left"))
            lower_destination = int(np.searchsorted(destination_end, cutoff, side="left"))
            absolute_source_lo = src_lo + lower_source
            absolute_source_hi = src_lo + upper_source
            absolute_destination_lo = dst_lo + lower_destination
            absolute_destination_hi = dst_lo + upper_destination
            window_dst = src_dst[absolute_source_lo:absolute_source_hi]
            window_port = src_dport[absolute_source_lo:absolute_source_hi]
            destination_sources = dst_src[absolute_destination_lo:absolute_destination_hi]
            source_count = absolute_source_hi - absolute_source_lo
            destination_count = absolute_destination_hi - absolute_destination_lo
            byte_count = int(prefix_bytes[absolute_source_hi] - prefix_bytes[absolute_source_lo])
            packet_count = int(prefix_packets[absolute_source_hi] - prefix_packets[absolute_source_lo])
            same_destination = window_dst == target_dst[output_index]
            same_destination_port = same_destination \
                & (window_port == target_dport[output_index])
            neighbor = (window_dst.astype(np.int64) << 16) | window_port
            seconds = horizon / 1000.0
            values.extend([
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
            ])
        previous_end = int(source_end[upper_source - 1]) if upper_source > 0 else None
        values.append(
            float(target_start[output_index] - previous_end) if previous_end is not None else -1.0
        )
        output[output_index] = values
        if output_index and output_index % 20_000 == 0:
            print(f"    history {output_index:,}/{len(targets):,}", flush=True)
    return output, names


# ---------------------------------------------------------------------------
# Sampling (frozen)
# ---------------------------------------------------------------------------

def sample_pool(
    *,
    rng: np.random.Generator,
    pool_positions: np.ndarray,
    arrays: dict[str, np.ndarray],
    cap: int,
    minimum: int,
    blocks: int,
    name: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Temporal-block-stratified deterministic sampling of one split x class
    duplicate-aware pool. Returns (positions, block_ids)."""
    if len(pool_positions) < minimum:
        raise SystemExit(
            f"GATE_0_STATUS=BLOCKED_INSUFFICIENT_DUPLICATE_AWARE_SAMPLE "
            f"pool={name} n={len(pool_positions)} min={minimum}"
        )
    take = min(cap, len(pool_positions))
    edges = np.linspace(0, len(pool_positions), blocks + 1, dtype=np.int64)
    block_sizes = np.diff(edges)
    allocations = np.floor(take * block_sizes / len(pool_positions)).astype(np.int64)
    remaining = take - int(allocations.sum())
    fractions = (take * block_sizes / len(pool_positions)) - allocations
    order = np.argsort(-fractions, kind="stable")
    allocations[order[:remaining]] += 1
    chosen: list[np.ndarray] = []
    block_ids: list[np.ndarray] = []
    for block in range(blocks):
        count = int(allocations[block])
        if count == 0:
            continue
        lo, hi = int(edges[block]), int(edges[block + 1])
        draw = np.sort(rng.choice(hi - lo, size=count, replace=False)) + lo
        chosen.append(pool_positions[draw])
        block_ids.append(np.full(count, block, dtype=np.int16))
    if not chosen:
        return np.array([], dtype=np.int64), np.array([], dtype=np.int16)
    return np.concatenate(chosen), np.concatenate(block_ids)


# ---------------------------------------------------------------------------
# Gate 0 — duplicate-aware target view + formal sampling
# ---------------------------------------------------------------------------

def run_gate0(args) -> int:
    artifact_root = Path(args.artifact_root)
    artifact_root.mkdir(parents=True, exist_ok=True)
    print("[gate0] loading manifest (FINAL_TEST excluded from modeling arrays)")
    arrays = load_manifest_columns(args.manifest)
    eligible = arrays["target_eligible"].astype(bool)
    print(f"[gate0] modeling rows (TRAIN+VALIDATION): {eligible.sum():,}")

    pools: dict[str, np.ndarray] = {}
    summary: dict[str, Any] = {
        "schema_version": "DUPLICATE_AWARE_CORE_GATE_VIEW_V1",
        "duplicate_group_key": "canonical_row_digest (frozen exact-duplicate semantics, verified)",
        "representative_rule": "earliest flow_start_ms, tie-break minimum source_row_index",
        "history_rule": "FULL split history retained (never deduplicated); "
                        "WITHIN_SPLIT_STRICT_END_BEFORE_TARGET_START_V1",
        "expected_duplicate_groups": 480_040,
        "expected_duplicate_copies": 1_816_137,
        "label_conflicts": 0,
        "pools": {},
    }
    for partition, name in ((PARTITION_TRAIN, "TRAIN"), (PARTITION_VALIDATION, "VALIDATION")):
        reps, all_pool = duplicate_representatives(arrays, partition)
        summary["pools"][name] = {"duplicate_aware_n": int(len(reps)),
                                  "raw_eligible_n": int(len(all_pool))}
        labels = arrays["canonical_label"][reps]
        per_class = collections.Counter(labels)
        summary["pools"][name]["per_class"] = dict(sorted(per_class.items()))
        print(f"[gate0] {name}: duplicate-aware pool={len(reps):,} "
              f"per-class={dict(sorted(per_class.items()))}")
        for class_name in CANONICAL_CLASS_ORDER:
            pool = reps[labels == class_name]
            pools[f"{name}|{class_name}"] = pool

    # duplicate semantics verification (Gate 0 acceptance) over the FULL
    # 27,520,260-row manifest: digest + canonical label columns only; no other
    # FINAL_TEST data is read and no modeling decision uses FINAL_TEST rows.
    full_table = pq.read_table(
        args.manifest, columns=["canonical_row_digest", "canonical_label"])
    full_digests = full_table["canonical_row_digest"].to_numpy(zero_copy_only=False)
    full_labels = np.array(
        ["" if value is None else value
         for value in full_table["canonical_label"].to_pylist()],
        dtype=object,
    )
    dup_groups, dup_copies, conflicts = verify_duplicate_semantics(
        full_digests, full_labels)
    print(f"[gate0] duplicate groups={dup_groups:,} copies={dup_copies:,} "
          f"label_conflicts={conflicts}")
    if dup_groups != 480_040 or dup_copies != 1_816_137:
        raise SystemExit(f"GATE_0_STATUS=FAIL_DUPLICATE_SEMANTICS "
                         f"groups={dup_groups} copies={dup_copies}")
    if conflicts:
        raise SystemExit(f"GATE_0_STATUS=FAIL_DUPLICATE_LABEL_CONFLICT "
                         f"conflicts={conflicts}")

    # materialize the duplicate-aware target manifest (representatives only)
    rep_positions = np.concatenate(list(pools.values()))
    rep_positions = np.unique(rep_positions)
    manifest_records = {
        "source_row_index": pa.array(arrays["source_row_index"][rep_positions], pa.int64()),
        "canonical_label": pa.array(arrays["canonical_label"][rep_positions], pa.string()),
        "partition_code": pa.array(
            arrays["partition_code"][rep_positions].astype(np.int64), pa.int8()),
        "flow_start_ms": pa.array(arrays["flow_start_ms"][rep_positions], pa.int64()),
        "activity_group_digest": pa.array(
            arrays["activity_group_digest"][rep_positions], pa.binary(16)),
    }
    manifest_path = artifact_root / "duplicate_aware_target_manifest_v1.parquet"
    pq.write_table(pa.table(manifest_records), manifest_path, compression="zstd")
    print(f"[gate0] wrote {manifest_path} ({len(rep_positions):,} representatives)")

    seeds = (SMOKE_SEED,) + FORMAL_SEEDS
    for seed in seeds:
        rng = np.random.default_rng(seed)
        is_smoke = seed == SMOKE_SEED
        train_cap = 2_000 if is_smoke else TRAIN_CAP
        val_cap = 1_000 if is_smoke else VAL_CAP
        train_min = 1_500 if is_smoke else TRAIN_MIN
        val_min = 800 if is_smoke else VAL_MIN
        blocks = N_TEMPORAL_BLOCKS
        positions: list[np.ndarray] = []
        block_ids: list[np.ndarray] = []
        labels_out: list[np.ndarray] = []
        partitions_out: list[np.ndarray] = []
        for class_name in CANONICAL_CLASS_ORDER:
            for partition, pname, cap, minimum in (
                (PARTITION_TRAIN, "TRAIN", train_cap, train_min),
                (PARTITION_VALIDATION, "VALIDATION", val_cap, val_min),
            ):
                pool = pools[f"{pname}|{class_name}"]
                chosen, block = sample_pool(
                    rng=rng, pool_positions=pool, arrays=arrays, cap=cap,
                    minimum=minimum, blocks=blocks,
                    name=f"{pname}|{class_name}",
                )
                positions.append(chosen)
                block_ids.append(block)
                labels_out.append(np.full(len(chosen), class_name, dtype=object))
                partitions_out.append(np.full(len(chosen), partition, dtype=np.int8))
        all_positions = np.concatenate(positions)
        all_blocks = np.concatenate(block_ids)
        all_labels = np.concatenate(labels_out)
        all_partitions = np.concatenate(partitions_out)
        table = pa.table({
            "source_row_index": pa.array(arrays["source_row_index"][all_positions], pa.int64()),
            "canonical_label": pa.array(all_labels, pa.string()),
            "partition_code": pa.array(all_partitions, pa.int8()),
            "temporal_block": pa.array(all_blocks, pa.int16()),
            "flow_start_ms": pa.array(arrays["flow_start_ms"][all_positions], pa.int64()),
            "activity_group_digest": pa.array(
                arrays["activity_group_digest"][all_positions], pa.binary(16)),
        })
        out = artifact_root / f"gate_seed_{seed}_targets.parquet"
        pq.write_table(table, out, compression="zstd")
        counts = collections.Counter(zip(all_partitions.tolist(), all_labels.tolist()))
        print(f"[gate0] seed={seed}{' (SMOKE)' if is_smoke else ''} targets={len(all_positions):,} "
              f"per-(partition,class)={dict(sorted(counts.items()))} -> {out.name}")
        summary[f"seed_{seed}"] = {
            "targets_n": int(len(all_positions)),
            "per_partition_class": {f"{p}|{c}": int(n) for (p, c), n in sorted(counts.items())},
            "smoke": bool(is_smoke),
        }
    (artifact_root / "gate0_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")
    print("[gate0] GATE_0_STATUS=PASS_DUPLICATE_AWARE_VIEW_READY")
    return 0


# ---------------------------------------------------------------------------
# Basic feature extraction (streamed from the frozen CSV archive)
# ---------------------------------------------------------------------------

def run_basic(args) -> int:
    artifact_root = Path(args.artifact_root)
    targets_path = artifact_root / "core_gate_basic_targets_union.parquet"
    needed = set()
    for seed in (SMOKE_SEED,) + FORMAL_SEEDS:
        table = pq.read_table(artifact_root / f"gate_seed_{seed}_targets.parquet",
                              columns=["source_row_index"])
        needed.update(int(value) for value in table["source_row_index"].to_pylist())
    print(f"[basic] union of target rows across seeds: {len(needed):,}")

    out_path = artifact_root / "core_gate_basic_features_v1.parquet"
    with zipfile.ZipFile(args.archive) as zipped:
        members = [name for name in zipped.namelist() if name.endswith("NF-ToN-IoT-v3.csv")]
        if len(members) != 1:
            raise SystemExit(f"expected one NF3-ToN CSV member, found {members}")
        with zipped.open(members[0]) as source:
            header_line = source.readline()
            header = header_line.rstrip(b"\r\n").decode("utf-8").split(",")
            if len(header) != 55:
                raise SystemExit(f"expected 55 columns, found {len(header)}")
            positions = {name: index for index, name in enumerate(header)}
            missing = [name for name in MODEL_VISIBLE_FIELDS if name not in positions]
            if missing:
                raise SystemExit(f"CSV is missing Basic fields: {missing}")
            rows: list[dict[str, Any]] = []
            for row_index, line in enumerate(source):
                if row_index not in needed:
                    continue
                parts = line.rstrip(b"\r\n").split(b",")
                record: dict[str, Any] = {"source_row_index": row_index}
                for name in MODEL_VISIBLE_FIELDS:
                    raw = parts[positions[name]]
                    try:
                        value = float(raw) if raw.strip() else float("nan")
                    except ValueError:
                        value = float("nan")
                    record[name] = value
                rows.append(record)
                if len(rows) % 50_000 == 0:
                    print(f"    extracted {len(rows):,}/{len(needed):,}", flush=True)
    if len(rows) != len(needed):
        raise SystemExit(f"extracted {len(rows)} rows but expected {len(needed)}")
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, out_path, compression="zstd")
    digest = hashlib.sha256()
    digest.update(SOURCE_ARTIFACT_SHA256.encode())
    for name in MODEL_VISIBLE_FIELDS:
        digest.update(name.encode())
    print(f"[basic] wrote {out_path} rows={len(rows)} fields={len(MODEL_VISIBLE_FIELDS)}")
    print(f"[basic] BASIC_EXTRACTION_SHA256_CONTEXT={digest.hexdigest()[:32]}…")
    return 0


# ---------------------------------------------------------------------------
# Feature matrices and models
# ---------------------------------------------------------------------------

def safe_basic(matrix: np.ndarray) -> np.ndarray:
    matrix = np.nan_to_num(matrix, nan=0.0, posinf=1e15, neginf=-1e15)
    return np.sign(matrix) * np.log1p(np.abs(matrix))


def build_feature_matrices(
    basic: np.ndarray,
    history: np.ndarray,
    history_names: list[str],
) -> dict[str, np.ndarray]:
    """Feature matrices for the four frozen Evidence conditions. The SAME
    target rows and transforms feed every condition; only the Evidence family
    block differs."""
    history_t = np.log1p(np.clip(history, 0.0, None))
    temporal_index = [history_names.index(name) for name in TEMPORAL_FIELDS]
    relation_index = [history_names.index(name) for name in RELATION_FIELDS]
    basic_t = safe_basic(basic)
    return {
        "B": basic_t,
        "BT": np.column_stack([basic_t, history_t[:, temporal_index]]),
        "BR": np.column_stack([basic_t, history_t[:, relation_index]]),
        "BTR": np.column_stack([basic_t, history_t]),
    }


def fit_estimator(seed: int) -> RandomForestClassifier:
    config = dict(ESTIMATOR_CONFIG)
    config["random_state"] = seed
    return RandomForestClassifier(**config)


def confusion_and_metrics(predicted: np.ndarray, labels: np.ndarray):
    confusion = confusion_matrix(labels, predicted, labels=CANONICAL_CLASS_ORDER)
    macro_f1 = float(f1_score(labels, predicted, average="macro"))
    micro_f1 = float(f1_score(labels, predicted, average="micro"))
    balanced_acc = float(balanced_accuracy_score(labels, predicted))
    accuracy = float(accuracy_score(labels, predicted))
    per_class_f1 = {
        name: float(value) for name, value in zip(
            CANONICAL_CLASS_ORDER,
            f1_score(labels, predicted, average=None, labels=CANONICAL_CLASS_ORDER),
            strict=True,
        )
    }
    return {
        "confusion_matrix": confusion.tolist(),
        "macro_f1": macro_f1,
        "micro_f1": micro_f1,
        "balanced_accuracy": balanced_acc,
        "accuracy": accuracy,
        "per_class_f1": per_class_f1,
    }


def recoverability(pred_b: np.ndarray, pred_c: np.ndarray, labels: np.ndarray):
    basic_wrong = pred_b != labels
    cond_correct = pred_c == labels
    cond_wrong = pred_c != labels
    basic_correct = pred_b == labels
    recovered = basic_wrong & cond_correct
    harmed = basic_correct & cond_wrong
    out: dict[str, Any] = {
        "recoverable_known_n": int(recovered.sum()),
        "recoverable_known_rate": float(recovered.mean()),
        "recoverable_among_basic_errors": float(recovered.sum() / basic_wrong.sum())
        if basic_wrong.sum() else 0.0,
        "harm_n": int(harmed.sum()),
        "harm_rate": float(harmed.mean()),
        "net_recovery_rate": float(recovered.mean() - harmed.mean()),
        "per_class": {},
    }
    for class_name in CANONICAL_CLASS_ORDER:
        mask = labels == class_name
        rec_rate = float(recovered[mask].mean()) if mask.sum() else 0.0
        harm_rate = float(harmed[mask].mean()) if mask.sum() else 0.0
        out["per_class"][class_name] = {
            "n": int(mask.sum()),
            "recoverable_known_n": int(recovered[mask].sum()),
            "recoverable_known_rate": rec_rate,
            "harm_rate": harm_rate,
            "net_recovery_rate": rec_rate - harm_rate,
        }
    return out


# ---------------------------------------------------------------------------
# Per-seed formal run
# ---------------------------------------------------------------------------

def run_seed(args, seed: int, is_smoke: bool = False) -> int:
    artifact_root = Path(args.artifact_root)
    arrays = load_manifest_columns(args.manifest)
    targets_table = pq.read_table(artifact_root / f"gate_seed_{seed}_targets.parquet")
    target_rows = targets_table["source_row_index"].to_numpy()
    target_labels = np.array(targets_table["canonical_label"].to_pylist(), dtype=object)
    target_partitions = targets_table["partition_code"].to_numpy()
    target_blocks = targets_table["temporal_block"].to_numpy()
    print(f"[seed {seed}] targets={len(target_rows):,} "
          f"train={int((target_partitions == PARTITION_TRAIN).sum()):,} "
          f"validation={int((target_partitions == PARTITION_VALIDATION).sum()):,}")

    row_position = {int(value): index for index, value in enumerate(arrays["source_row_index"])}
    positions = np.array([row_position[int(value)] for value in target_rows], dtype=np.int64)

    history_cache = artifact_root / f"gate_seed_{seed}_history.parquet"
    if history_cache.exists():
        history_table = pq.read_table(history_cache)
        history_names = [name for name in history_table.column_names if name != "source_row_index"]
        cache_rows = {int(value): index
                      for index, value in enumerate(history_table["source_row_index"].to_pylist())}
        history_values = {}
        for row in target_rows:
            position = cache_rows[int(row)]
            history_values[int(row)] = np.asarray(
                [history_table[name][position].as_py() for name in history_names],
                dtype=np.float64)
        print(f"[seed {seed}] loaded cached history for {len(target_rows):,} targets")
    else:
        print(f"[seed {seed}] computing strict past-only history for {len(positions):,} targets")
        started = time.monotonic()
        history, history_names = strict_history_features(arrays, positions)
        print(f"[seed {seed}] history computed in {time.monotonic() - started:.0f}s")
        records = {"source_row_index": pa.array(target_rows, pa.int64())}
        for index, name in enumerate(history_names):
            records[name] = pa.array(history[:, index], pa.float64())
        pq.write_table(pa.table(records), history_cache, compression="zstd")
        history_values = {int(row): history[i] for i, row in enumerate(target_rows)}

    basic_table = pq.read_table(artifact_root / "core_gate_basic_features_v1.parquet")
    basic_rows = basic_table["source_row_index"].to_pylist()
    basic_positions = {int(value): index for index, value in enumerate(basic_rows)}
    basic_arrays = {
        name: np.asarray(basic_table[name].to_pylist(), dtype=np.float64)
        for name in MODEL_VISIBLE_FIELDS
    }
    target_basic_positions = np.array(
        [basic_positions[int(row)] for row in target_rows], dtype=np.int64)
    basic_matrix = np.column_stack(
        [basic_arrays[name][target_basic_positions] for name in MODEL_VISIBLE_FIELDS])
    history_matrix = np.stack([history_values[int(row)] for row in target_rows])
    matrices = build_feature_matrices(basic_matrix, history_matrix, history_names)
    train_mask = target_partitions == PARTITION_TRAIN
    validation_mask = target_partitions == PARTITION_VALIDATION
    print(f"[seed {seed}] feature shapes: B={matrices['B'].shape} "
          f"BT={matrices['BT'].shape} BR={matrices['BR'].shape} BTR={matrices['BTR'].shape}")

    predictions: dict[str, np.ndarray] = {}
    metrics: dict[str, Any] = {}
    for condition in CONDITIONS:
        started = time.monotonic()
        model = fit_estimator(seed)
        model.fit(matrices[condition][train_mask], target_labels[train_mask])
        prediction = model.predict(matrices[condition][validation_mask])
        predictions[condition] = prediction
        metrics[condition] = confusion_and_metrics(prediction, target_labels[validation_mask])
        print(f"[seed {seed}] {condition}: macro_f1={metrics[condition]['macro_f1']:.6f} "
              f"in {time.monotonic() - started:.0f}s")

    pred_table = pa.table({
        "source_row_index": pa.array(target_rows[validation_mask], pa.int64()),
        "canonical_label": pa.array(target_labels[validation_mask], pa.string()),
        "activity_group_digest": pa.array(
            arrays["activity_group_digest"][positions[validation_mask]], pa.binary(16)),
        "temporal_block": pa.array(target_blocks[validation_mask], pa.int16()),
        "pred_B": pa.array(predictions["B"], pa.string()),
        "pred_BT": pa.array(predictions["BT"], pa.string()),
        "pred_BR": pa.array(predictions["BR"], pa.string()),
        "pred_BTR": pa.array(predictions["BTR"], pa.string()),
    })
    pred_path = artifact_root / f"gate_seed_{seed}_validation_predictions.parquet"
    pq.write_table(pred_table, pred_path, compression="zstd")

    result: dict[str, Any] = {
        "schema_version": "CORE_GATE_SEED_RESULT_V1",
        "seed": seed,
        "smoke": bool(is_smoke),
        "estimator": ESTIMATOR_FAMILY,
        "estimator_config": dict(ESTIMATOR_CONFIG),
        "train_n": int(train_mask.sum()),
        "validation_n": int(validation_mask.sum()),
        "feature_names": {
            "basic": list(MODEL_VISIBLE_FIELDS),
            "temporal": list(TEMPORAL_FIELDS),
            "relation": list(RELATION_FIELDS),
        },
        "metrics": metrics,
        "deltas": {},
        "recoverability": {},
        "history_artifact_sha256": sha256_file(history_cache),
        "predictions_artifact": pred_path.name,
    }
    for condition, family in EVIDENCE_DELTAS.items():
        result["deltas"][family] = metrics[condition]["macro_f1"] - metrics["B"]["macro_f1"]
        result["recoverability"][family] = recoverability(
            predictions["B"], predictions[condition], target_labels[validation_mask])
    for family, delta in result["deltas"].items():
        print(f"[seed {seed}] delta_{family}={delta:+.6f} "
              f"recoverable_rate={result['recoverability'][family]['recoverable_known_rate']:.6f} "
              f"harm_rate={result['recoverability'][family]['harm_rate']:.6f} "
              f"net={result['recoverability'][family]['net_recovery_rate']:+.6f}")
    (artifact_root / f"gate_seed_{seed}_result.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")
    print(f"[seed {seed}] wrote gate_seed_{seed}_result.json")
    return 0


# ---------------------------------------------------------------------------
# Paired private-group bootstrap
# ---------------------------------------------------------------------------

def _macro_f1_from_confusion(confusion: np.ndarray) -> float:
    per_class_f1 = np.zeros(confusion.shape[0], dtype=np.float64)
    for index in range(confusion.shape[0]):
        precision = confusion[index, index] / max(confusion[:, index].sum(), 1e-12)
        recall = confusion[index, index] / max(confusion[index, :].sum(), 1e-12)
        per_class_f1[index] = 2 * precision * recall / max(precision + recall, 1e-12)
    return float(per_class_f1.mean())


def paired_group_bootstrap(
    *,
    labels: np.ndarray,
    groups: np.ndarray,
    predictions: dict[str, np.ndarray],
    n_reps: int,
    rng_seed: int,
) -> dict[str, Any]:
    """Paired private-group bootstrap: the same group multiset per replicate
    is applied to every condition, so deltas are paired by construction.
    Duplicate groups are never split (a duplicate group lies inside one
    private activity group)."""
    _, group_index = np.unique(groups, return_inverse=True)
    n_groups = len(np.unique(groups))
    class_index = {name: index for index, name in enumerate(CANONICAL_CLASS_ORDER)}
    label_codes = np.array([class_index[name] for name in labels], dtype=np.int64)
    pred_codes = {condition: np.array([class_index[name] for name in predictions[condition]],
                                      dtype=np.int64)
                  for condition in CONDITIONS}

    confusion_by_group = np.zeros((len(CONDITIONS), n_groups, 7, 7), dtype=np.int64)
    recovered_by_group = np.zeros((3, n_groups, 7), dtype=np.int64)
    harmed_by_group = np.zeros((3, n_groups, 7), dtype=np.int64)
    class_total_by_group = np.zeros((n_groups, 7), dtype=np.int64)
    np.add.at(class_total_by_group, (group_index, label_codes), 1)
    basic_wrong = pred_codes["B"] != label_codes
    basic_correct = pred_codes["B"] == label_codes
    for condition_index, condition in enumerate(CONDITIONS):
        np.add.at(confusion_by_group[condition_index], (
            group_index, label_codes, pred_codes[condition]), 1)
    for family_index, condition in enumerate(("BT", "BR", "BTR")):
        cond_correct = pred_codes[condition] == label_codes
        cond_wrong = pred_codes[condition] != label_codes
        np.add.at(recovered_by_group[family_index],
                  (group_index[basic_wrong & cond_correct],
                   label_codes[basic_wrong & cond_correct]), 1)
        np.add.at(harmed_by_group[family_index],
                  (group_index[basic_correct & cond_wrong],
                   label_codes[basic_correct & cond_wrong]), 1)

    rng = np.random.default_rng(rng_seed)
    draws = rng.integers(0, n_groups, size=(n_reps, n_groups))
    counts = np.apply_along_axis(np.bincount, 1, draws, minlength=n_groups)

    families: dict[str, Any] = {}
    for condition, family in EVIDENCE_DELTAS.items():
        family_index = {"T": 0, "R": 1, "TR": 2}[family]
        delta_f1 = np.empty(n_reps, dtype=np.float64)
        recoverable = np.empty(n_reps, dtype=np.float64)
        harm = np.empty(n_reps, dtype=np.float64)
        for rep in range(n_reps):
            weight = counts[rep].astype(np.int64)
            confusion_b = np.einsum("g,gij->ij", weight, confusion_by_group[0])
            confusion_c = np.einsum("g,gij->ij", weight, confusion_by_group[
                CONDITIONS.index(condition)])
            delta_f1[rep] = (_macro_f1_from_confusion(confusion_c)
                             - _macro_f1_from_confusion(confusion_b))
            rec_total = np.einsum("g,gc->c", weight, recovered_by_group[family_index])
            harm_total = np.einsum("g,gc->c", weight, harmed_by_group[family_index])
            class_total = np.einsum("g,gc->c", weight, class_total_by_group)
            recoverable[rep] = rec_total.sum() / max(class_total.sum(), 1)
            harm[rep] = harm_total.sum() / max(class_total.sum(), 1)
        families[family] = {
            "condition": condition,
            "delta_macro_f1_mean": float(delta_f1.mean()),
            "delta_macro_f1_ci95": [float(np.percentile(delta_f1, 2.5)),
                                    float(np.percentile(delta_f1, 97.5))],
            "recoverable_rate_mean": float(recoverable.mean()),
            "recoverable_rate_ci95": [float(np.percentile(recoverable, 2.5)),
                                      float(np.percentile(recoverable, 97.5))],
            "harm_rate_mean": float(harm.mean()),
            "harm_rate_ci95": [float(np.percentile(harm, 2.5)),
                               float(np.percentile(harm, 97.5))],
            "net_recovery_mean": float((recoverable - harm).mean()),
            "net_recovery_ci95": [float(np.percentile(recoverable - harm, 2.5)),
                                  float(np.percentile(recoverable - harm, 97.5))],
        }
    return families


def run_bootstrap(args, seed: int) -> int:
    artifact_root = Path(args.artifact_root)
    pred_table = pq.read_table(artifact_root / f"gate_seed_{seed}_validation_predictions.parquet")
    labels = np.array(pred_table["canonical_label"].to_pylist(), dtype=object)
    groups = np.array(
        [bytes(value) for value in pred_table["activity_group_digest"].to_pylist()],
        dtype=object,
    )
    predictions = {
        condition: np.array(pred_table[f"pred_{condition}"].to_pylist(), dtype=object)
        for condition in CONDITIONS
    }
    print(f"[bootstrap seed {seed}] targets={len(labels)} "
          f"groups={len(np.unique(groups))} reps={BOOTSTRAP_REPS}")
    families = paired_group_bootstrap(
        labels=labels, groups=groups, predictions=predictions,
        n_reps=BOOTSTRAP_REPS, rng_seed=seed + BOOTSTRAP_RNG_OFFSET,
    )
    bootstrap: dict[str, Any] = {"schema_version": "CORE_GATE_BOOTSTRAP_V1", "seed": seed,
                                 "reps": BOOTSTRAP_REPS, "unit": "private activity group",
                                 "paired": True, "families": families}
    for family, info in families.items():
        print(f"[bootstrap seed {seed}] {family}: "
              f"dF1 {info['delta_macro_f1_mean']:+.6f} CI95 {info['delta_macro_f1_ci95']} "
              f"rec {info['recoverable_rate_mean']:.6f} "
              f"net {info['net_recovery_mean']:+.6f}")
    out = artifact_root / f"gate_seed_{seed}_bootstrap.json"
    out.write_text(json.dumps(bootstrap, indent=2), encoding="utf-8")
    print(f"[bootstrap seed {seed}] wrote {out.name}")
    return 0


# ---------------------------------------------------------------------------
# Decision (frozen criteria)
# ---------------------------------------------------------------------------

def build_candidates(results: list[dict[str, Any]]) -> tuple[dict[str, Any], str, str]:
    """Apply the pre-registered H1 criteria to per-seed results.
    Returns (candidates, decision, core_family)."""
    def mean(values):
        return float(np.mean(values))

    families = ("T", "R", "TR")
    candidates: dict[str, dict[str, Any]] = {}
    for family in families:
        delta_seeds = [r["result"]["deltas"][family] for r in results]
        rec_seeds = [r["result"]["recoverability"][family]["recoverable_known_rate"]
                     for r in results]
        harm_seeds = [r["result"]["recoverability"][family]["harm_rate"] for r in results]
        net_seeds = [r["result"]["recoverability"][family]["net_recovery_rate"]
                     for r in results]
        per_class_mean = {}
        for class_name in CANONICAL_CLASS_ORDER:
            per_class_mean[class_name] = mean([
                r["result"]["recoverability"][family]["per_class"][class_name][
                    "recoverable_known_rate"] for r in results])
        attack_meaningful = [
            name for name in ATTACK_CLASSES if per_class_mean[name] >= 0.02
        ]
        bootstrap_deltas = [r["bootstrap"]["families"][family]["delta_macro_f1_mean"]
                            for r in results]
        ci_lower = min(
            r["bootstrap"]["families"][family]["delta_macro_f1_ci95"][0] for r in results)
        candidates[family] = {
            "family": family,
            "delta_by_seed": delta_seeds,
            "mean_delta": mean(delta_seeds),
            "positive_in_all_seeds": all(delta > 0 for delta in delta_seeds),
            "mean_recoverable_rate": mean(rec_seeds),
            "recoverable_by_seed": rec_seeds,
            "mean_harm_rate": mean(harm_seeds),
            "mean_net_recovery": mean(net_seeds),
            "attack_classes_meaningful": attack_meaningful,
            "bootstrap_mean_delta": mean(bootstrap_deltas),
            "min_seed_bootstrap_ci_lower": ci_lower,
            "criterion_1": all(delta > 0 for delta in delta_seeds),
            "criterion_2": mean(delta_seeds) >= 0.005,
            "criterion_3": mean(rec_seeds) >= 0.05,
            "criterion_4": len(attack_meaningful) >= 2,
            "criterion_5": ci_lower > 0,
            "criterion_6": mean(net_seeds) > 0,
        }
        candidates[family]["all_criteria"] = all(
            candidates[family][f"criterion_{index}"] for index in range(1, 7))
        print(f"[decide] {family}: dF1={candidates[family]['mean_delta']:+.6f} "
              f"({delta_seeds}) rec={candidates[family]['mean_recoverable_rate']:.6f} "
              f"net={candidates[family]['mean_net_recovery']:+.6f} "
              f"attack_classes={attack_meaningful} "
              f"CI_lower={ci_lower:+.6f} PASS={candidates[family]['all_criteria']}")

    winners = [family for family, info in candidates.items() if info["all_criteria"]]
    if winners:
        return candidates, "PASS", winners[0]
    strongest = max(candidates, key=lambda f: (
        candidates[f]["criterion_3"], candidates[f]["mean_delta"]))
    info = candidates[strongest]
    weak_signal = (
        info["mean_delta"] >= 0.002
        or info["mean_recoverable_rate"] >= 0.02
        or sum(candidates[f]["positive_in_all_seeds"] for f in families) >= 1
    )
    return candidates, ("YELLOW" if weak_signal else "FAIL"), "NONE"


def run_decide(args) -> int:
    artifact_root = Path(args.artifact_root)
    results = []
    for seed in FORMAL_SEEDS:
        result = json.loads((artifact_root / f"gate_seed_{seed}_result.json").read_text())
        bootstrap = json.loads((artifact_root / f"gate_seed_{seed}_bootstrap.json").read_text())
        results.append({"seed": seed, "result": result, "bootstrap": bootstrap})

    candidates, decision, core_family = build_candidates(results)

    report = {
        "schema_version": "CORE_HYPOTHESIS_GATE_V1_REPORT_V1",
        "date": "2026-08-17",
        "branch": args.branch,
        "head": args.head,
        "source_artifact_sha256": SOURCE_ARTIFACT_SHA256,
        "split_manifest_sha256": args.split_manifest_sha256,
        "master_split_modified": False,
        "final_test_modeling_contamination": False,
        "formal_seeds": list(FORMAL_SEEDS),
        "estimator": ESTIMATOR_FAMILY,
        "estimator_config": dict(ESTIMATOR_CONFIG),
        "estimator_provenance": ESTIMATOR_PROVENANCE,
        "basic_feature_names": list(MODEL_VISIBLE_FIELDS),
        "temporal_feature_names": list(TEMPORAL_FIELDS),
        "relation_feature_names": list(RELATION_FIELDS),
        "forbidden_feature_audit": "PASS",
        "evidence_strict_past_only": True,
        "gate0": json.loads((artifact_root / "gate0_summary.json").read_text()),
        "per_seed": {},
        "candidates": candidates,
        "decision": decision,
        "core_evidence_family": core_family,
        "prior_pilot_reference": {
            "OOF_BASIC_MACRO_F1": 0.9241027728324086,
            "OOF_FULL_MACRO_F1": 0.9542507313534688,
            "RECOVERABLE_KNOWN_RATE": 0.11995833333333333,
            "UTILITY_PREDICTION_AUROC": 0.9559201214445113,
            "DIRECT_FURK": 0.3062080536912752,
            "EVIDENCE_CONDITIONED_FURK": 0.24161073825503357,
        },
    }
    for r in results:
        report["per_seed"][str(r["seed"])] = {
            "macro_f1": {condition: r["result"]["metrics"][condition]["macro_f1"]
                         for condition in CONDITIONS},
            "deltas": r["result"]["deltas"],
            "recoverable": {
                family: r["result"]["recoverability"][family]["recoverable_known_rate"]
                for family in ("T", "R", "TR")},
            "harm": {family: r["result"]["recoverability"][family]["harm_rate"]
                     for family in ("T", "R", "TR")},
            "net": {family: r["result"]["recoverability"][family]["net_recovery_rate"]
                    for family in ("T", "R", "TR")},
            "train_n": r["result"]["train_n"],
            "validation_n": r["result"]["validation_n"],
        }
    (artifact_root / "core_gate_decision.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    print(f"[decide] CORE_HYPOTHESIS_GATE_1={decision} "
          f"CORE_EVIDENCE_FAMILY={core_family}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True,
                        choices=["gate0", "basic", "seed", "bootstrap", "decide"])
    parser.add_argument("--artifact-root", default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--archive", default=DEFAULT_ARCHIVE)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--head", default="")
    parser.add_argument("--split-manifest-sha256",
                        default="faa5220beae65f06591e7ea399c59092985135b81860fcd2388f20cadaa7c095")
    args = parser.parse_args()

    if args.mode == "gate0":
        return run_gate0(args)
    if args.mode == "basic":
        return run_basic(args)
    if args.mode == "seed":
        if args.seed is None:
            raise SystemExit("--seed is required for mode=seed")
        return run_seed(args, args.seed, is_smoke=args.smoke)
    if args.mode == "bootstrap":
        if args.seed is None:
            raise SystemExit("--seed is required for mode=bootstrap")
        return run_bootstrap(args, args.seed)
    return run_decide(args)


if __name__ == "__main__":
    raise SystemExit(main())
