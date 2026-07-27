from __future__ import annotations

import hashlib
import json
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.compute as pc

from .schema import DatasetContract


@dataclass
class _ColumnAccumulator:
    null_count: int = 0
    nan_count: int = 0
    positive_inf_count: int = 0
    negative_inf_count: int = 0
    zero_count: int = 0
    negative_count: int = 0
    minimum: Any | None = None
    maximum: Any | None = None
    counts: Counter[Any] = field(default_factory=Counter)

    def update_min_max(self, minimum: Any, maximum: Any) -> None:
        if minimum is not None and (self.minimum is None or minimum < self.minimum):
            self.minimum = minimum
        if maximum is not None and (self.maximum is None or maximum > self.maximum):
            self.maximum = maximum


def _value_counts(array: pa.Array) -> Counter[Any]:
    result: Counter[Any] = Counter()
    for item in pc.value_counts(array).to_pylist():
        result[item["values"]] += item["counts"]
    return result


def _update_numeric(acc: _ColumnAccumulator, array: pa.Array) -> None:
    valid = pc.drop_null(array)
    if len(valid) == 0:
        return
    values = valid.to_numpy(zero_copy_only=False)
    if pa.types.is_floating(valid.type):
        acc.nan_count += int(np.isnan(values).sum())
        acc.positive_inf_count += int(np.isposinf(values).sum())
        acc.negative_inf_count += int(np.isneginf(values).sum())
        values = values[np.isfinite(values)]
    if values.size == 0:
        return
    acc.zero_count += int(np.count_nonzero(values == 0))
    acc.negative_count += int(np.count_nonzero(values < 0))
    acc.update_min_max(values.min().item(), values.max().item())


def _count_duplicate_lines(
    csv_path: Path,
    *,
    temp_parent: Path,
    partition_count: int = 64,
) -> dict[str, Any]:
    """Count exact textual duplicate data rows using partitioned BLAKE2b-128 hashes."""

    temp_parent.mkdir(parents=True, exist_ok=True)
    temporary_files = [
        tempfile.NamedTemporaryFile(
            mode="w+b",
            prefix=f"duplicate-hashes-{index:02d}-",
            suffix=".bin",
            dir=temp_parent,
            delete=False,
        )
        for index in range(partition_count)
    ]
    paths = [Path(handle.name) for handle in temporary_files]
    handles = temporary_files
    try:
        row_count = 0
        try:
            with csv_path.open("rb", buffering=8 * 1024 * 1024) as source:
                source.readline()
                for line in source:
                    normalized = line.rstrip(b"\r\n")
                    digest = hashlib.blake2b(normalized, digest_size=16).digest()
                    handles[digest[0] % partition_count].write(digest)
                    row_count += 1
        finally:
            for handle in handles:
                handle.close()

        duplicate_rows = 0
        duplicate_groups = 0
        maximum_multiplicity = 1 if row_count else 0
        for part in paths:
            hashes = np.fromfile(part, dtype="V16")
            if hashes.size < 2:
                continue
            hashes.sort()
            equal_previous = hashes[1:] == hashes[:-1]
            duplicate_rows += int(equal_previous.sum())
            if not equal_previous.any():
                continue
            starts = np.flatnonzero(np.r_[True, hashes[1:] != hashes[:-1]])
            lengths = np.diff(np.r_[starts, hashes.size])
            repeated = lengths[lengths > 1]
            duplicate_groups += int(repeated.size)
            maximum_multiplicity = max(maximum_multiplicity, int(repeated.max(initial=1)))
    finally:
        for handle in handles:
            if not handle.closed:
                handle.close()
        for path in paths:
            path.unlink(missing_ok=True)

    return {
        "method": "exact CSV data-line equality via partitioned BLAKE2b-128",
        "hash_collision_note": "128-bit collision risk is negligible but not mathematically zero",
        "rows_hashed": row_count,
        "duplicate_rows_beyond_first": duplicate_rows,
        "duplicate_groups": duplicate_groups,
        "maximum_multiplicity": maximum_multiplicity,
    }


def audit_csv(
    csv_path: Path,
    contract: DatasetContract,
    *,
    block_size: int = 16 * 1024 * 1024,
    duplicate_temp_parent: Path | None = None,
) -> dict[str, Any]:
    reader = pacsv.open_csv(
        csv_path,
        read_options=pacsv.ReadOptions(block_size=block_size, use_threads=True),
    )
    actual_schema = [(field.name, str(field.type)) for field in reader.schema]
    contract.validate_actual_schema(actual_schema)

    accumulators = {name: _ColumnAccumulator() for name in contract.field_names}
    categorical = set(contract.categorical_fields)
    row_count = 0
    batch_count = 0
    timestamp_order_violations = 0
    previous_start: int | None = None
    end_before_start = 0
    binary_attack_mismatches = 0
    invariant_violations: Counter[str] = Counter()

    for batch in reader:
        batch_count += 1
        row_count += batch.num_rows
        for index, field in enumerate(reader.schema):
            array = batch.column(index)
            acc = accumulators[field.name]
            acc.null_count += array.null_count
            if pa.types.is_integer(field.type) or pa.types.is_floating(field.type):
                _update_numeric(acc, array)
            if field.name in categorical or pa.types.is_string(field.type):
                acc.counts.update(_value_counts(array))

        start = batch.column(reader.schema.get_field_index("FLOW_START_MILLISECONDS")).to_numpy(
            zero_copy_only=False
        )
        end = batch.column(reader.schema.get_field_index("FLOW_END_MILLISECONDS")).to_numpy(
            zero_copy_only=False
        )
        if previous_start is not None and start.size and start[0] < previous_start:
            timestamp_order_violations += 1
        if start.size > 1:
            timestamp_order_violations += int(np.count_nonzero(np.diff(start) < 0))
        if start.size:
            previous_start = int(start[-1])
        end_before_start += int(np.count_nonzero(end < start))
        def values(name: str) -> np.ndarray:
            return batch.column(reader.schema.get_field_index(name)).to_numpy(
                zero_copy_only=False
            )

        available = set(reader.schema.names)
        if "FLOW_DURATION_MILLISECONDS" in available:
            duration = values("FLOW_DURATION_MILLISECONDS")
            invariant_violations["duration_vs_timestamps_tolerance_gt_1ms"] += int(
                np.count_nonzero(np.abs((end - start) - duration) > 1)
            )
        for minimum_name, maximum_name, violation_name in (
            ("MIN_TTL", "MAX_TTL", "min_ttl_gt_max_ttl"),
            (
                "SHORTEST_FLOW_PKT",
                "LONGEST_FLOW_PKT",
                "shortest_flow_pkt_gt_longest_flow_pkt",
            ),
            ("MIN_IP_PKT_LEN", "MAX_IP_PKT_LEN", "min_ip_pkt_len_gt_max_ip_pkt_len"),
        ):
            if {minimum_name, maximum_name}.issubset(available):
                invariant_violations[violation_name] += int(
                    np.count_nonzero(values(minimum_name) > values(maximum_name))
                )
        for prefix in ("SRC_TO_DST", "DST_TO_SRC"):
            required = {
                f"{prefix}_IAT_MIN",
                f"{prefix}_IAT_AVG",
                f"{prefix}_IAT_MAX",
            }
            if not required.issubset(available):
                continue
            minimum = values(f"{prefix}_IAT_MIN")
            average = values(f"{prefix}_IAT_AVG")
            maximum = values(f"{prefix}_IAT_MAX")
            invariant_violations[f"{prefix.lower()}_iat_min_gt_avg"] += int(
                np.count_nonzero(minimum > average)
            )
            invariant_violations[f"{prefix.lower()}_iat_avg_gt_max"] += int(
                np.count_nonzero(average > maximum)
            )

        binary = batch.column(reader.schema.get_field_index(contract.binary_label_field)).to_numpy(
            zero_copy_only=False
        )
        attacks = np.asarray(
            batch.column(reader.schema.get_field_index(contract.multiclass_label_field)).to_pylist(),
            dtype=object,
        )
        expected_binary = attacks != "Benign"
        binary_attack_mismatches += int(np.count_nonzero(binary != expected_binary.astype(binary.dtype)))

    result: dict[str, Any] = {
        "source_file": csv_path.name,
        "source_bytes": csv_path.stat().st_size,
        "row_count": row_count,
        "csv_line_count_including_header": row_count + 1,
        "batch_count": batch_count,
        "column_count": len(reader.schema),
        "schema": [{"name": name, "dtype": dtype} for name, dtype in actual_schema],
        "schema_fingerprint": contract.fingerprint,
        "expected_extracted_feature_count": contract.expected_extracted_feature_count,
        "feature_columns_in_csv": len(reader.schema) - 2,
        "timestamp_order_violations": timestamp_order_violations,
        "end_before_start_rows": end_before_start,
        "binary_attack_mismatch_rows": binary_attack_mismatches,
        "strong_invariant_violations": dict(sorted(invariant_violations.items())),
    }

    column_stats: dict[str, Any] = {}
    constant_columns: list[str] = []
    near_constant_columns: list[dict[str, Any]] = []
    sparse_zero_columns: list[dict[str, Any]] = []
    for name, acc in accumulators.items():
        top_value = None
        top_count = 0
        if acc.counts:
            top_value, top_count = acc.counts.most_common(1)[0]
        if acc.minimum is not None and acc.minimum == acc.maximum:
            constant_columns.append(name)
        elif acc.counts and len(acc.counts) == 1:
            constant_columns.append(name)
        zero_ratio = acc.zero_count / row_count if row_count else 0.0
        top_ratio = top_count / row_count if row_count else 0.0
        dominant_ratio = max(zero_ratio, top_ratio)
        if dominant_ratio >= contract.near_constant_threshold and name not in constant_columns:
            near_constant_columns.append(
                {
                    "name": name,
                    "dominant_ratio": dominant_ratio,
                    "dominant_value": top_value if top_ratio >= zero_ratio else 0,
                }
            )
        if zero_ratio >= 0.95:
            sparse_zero_columns.append({"name": name, "zero_ratio": zero_ratio})
        column_stats[name] = {
            "null_count": acc.null_count,
            "nan_count": acc.nan_count,
            "positive_inf_count": acc.positive_inf_count,
            "negative_inf_count": acc.negative_inf_count,
            "zero_count": acc.zero_count,
            "negative_count": acc.negative_count,
            "minimum": acc.minimum,
            "maximum": acc.maximum,
            "cardinality": len(acc.counts) if acc.counts else None,
            "top_value": top_value,
            "top_count": top_count if acc.counts else None,
        }

    result["column_stats"] = column_stats
    result["constant_columns"] = sorted(constant_columns)
    result["near_constant_columns"] = sorted(near_constant_columns, key=lambda item: item["name"])
    result["sparse_zero_columns"] = sorted(sparse_zero_columns, key=lambda item: item["name"])
    result["binary_distribution"] = {
        str(key): value
        for key, value in sorted(accumulators[contract.binary_label_field].counts.items())
    }
    result["multiclass_distribution"] = dict(
        sorted(accumulators[contract.multiclass_label_field].counts.items())
    )
    canonical_distribution: Counter[str] = Counter()
    for raw_label, count in accumulators[contract.multiclass_label_field].counts.items():
        canonical = contract.canonical_multiclass_mapping.get(raw_label, raw_label)
        canonical_distribution[canonical] += count
    result["canonical_multiclass_distribution"] = dict(sorted(canonical_distribution.items()))
    result["unknown_binary_values"] = sorted(
        set(accumulators[contract.binary_label_field].counts) - set(contract.expected_binary_values)
    )
    result["unknown_multiclass_values"] = sorted(
        set(accumulators[contract.multiclass_label_field].counts)
        - set(contract.expected_multiclass_values)
    )
    result["model_feature_count"] = len(contract.model_feature_names)
    result["model_features"] = list(contract.model_feature_names)
    result["feature_roles"] = {
        field.name: {
            "role": field.role.value,
            "allowed_uses": list(field.allowed_uses),
        }
        for field in contract.fields
    }
    if duplicate_temp_parent is not None:
        result["duplicates"] = _count_duplicate_lines(
            csv_path,
            temp_parent=duplicate_temp_parent,
        )
    return result


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
