from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Hashable

import numpy as np
import pyarrow.csv as pacsv


KeyBuilder = Callable[[str, str], Hashable]


def _directed_pair(source: str, destination: str) -> tuple[str, str]:
    return source, destination


def _unordered_pair(source: str, destination: str) -> tuple[str, str]:
    return (source, destination) if source <= destination else (destination, source)


def _source_host(source: str, destination: str) -> str:
    del destination
    return source


CANDIDATE_BUILDERS: dict[str, KeyBuilder] = {
    "directed_pair_episode": _directed_pair,
    "unordered_pair_episode": _unordered_pair,
    "source_host_episode": _source_host,
}


@dataclass
class _GapProfile:
    previous: dict[Hashable, int] = field(default_factory=dict)
    seen_gap_count: int = 0
    positive_gap_count: int = 0
    negative_gap_count: int = 0
    sampled_positive_gaps: list[int] = field(default_factory=list)


def collect_gap_profiles(
    csv_path: Path,
    *,
    candidate_names: tuple[str, ...] = tuple(CANDIDATE_BUILDERS),
    sample_every: int = 100,
    block_size: int = 16 * 1024 * 1024,
) -> dict[str, Any]:
    builders = {name: CANDIDATE_BUILDERS[name] for name in candidate_names}
    profiles = {name: _GapProfile() for name in candidate_names}
    reader = pacsv.open_csv(
        csv_path,
        read_options=pacsv.ReadOptions(block_size=block_size, use_threads=True),
        convert_options=pacsv.ConvertOptions(
            include_columns=[
                "FLOW_START_MILLISECONDS",
                "IPV4_SRC_ADDR",
                "IPV4_DST_ADDR",
            ]
        ),
    )
    total_rows = 0
    global_order_violations = 0
    previous_global: int | None = None

    for batch in reader:
        starts = batch.column(0).to_numpy(zero_copy_only=False)
        sources = batch.column(1).to_pylist()
        destinations = batch.column(2).to_pylist()
        for timestamp, source, destination in zip(starts, sources, destinations, strict=True):
            value = int(timestamp)
            if previous_global is not None and value < previous_global:
                global_order_violations += 1
            previous_global = value
            total_rows += 1
            for name, builder in builders.items():
                profile = profiles[name]
                key = builder(source, destination)
                previous = profile.previous.get(key)
                if previous is not None:
                    gap = value - previous
                    profile.seen_gap_count += 1
                    if gap < 0:
                        profile.negative_gap_count += 1
                    elif gap > 0:
                        profile.positive_gap_count += 1
                        if profile.positive_gap_count % sample_every == 0:
                            profile.sampled_positive_gaps.append(gap)
                profile.previous[key] = value

    output: dict[str, Any] = {
        "row_count": total_rows,
        "global_timestamp_order_violations": global_order_violations,
        "sample_every": sample_every,
        "candidates": {},
    }
    quantiles = [0.5, 0.75, 0.9, 0.95, 0.99, 0.995, 0.997, 0.998, 0.999, 0.9995, 0.9999]
    for name, profile in profiles.items():
        sample = np.asarray(profile.sampled_positive_gaps, dtype=np.int64)
        output["candidates"][name] = {
            "key_count": len(profile.previous),
            "gap_count": profile.seen_gap_count,
            "positive_gap_count": profile.positive_gap_count,
            "negative_gap_count": profile.negative_gap_count,
            "sample_size": int(sample.size),
            "positive_gap_quantiles_ms": {
                str(quantile): int(np.quantile(sample, quantile)) if sample.size else None
                for quantile in quantiles
            },
            "sampled_positive_gap_max_ms": int(sample.max()) if sample.size else None,
        }
    return output


@dataclass
class _ActiveGroup:
    last_timestamp: int
    size: int
    labels: Counter[str]


@dataclass
class _GroupSummary:
    active: dict[Hashable, _ActiveGroup] = field(default_factory=dict)
    sizes: list[int] = field(default_factory=list)
    per_label_groups: Counter[str] = field(default_factory=Counter)
    pure_groups: int = 0
    sum_dominant_rows: int = 0
    total_rows: int = 0

    def finalize(self, group: _ActiveGroup) -> None:
        self.sizes.append(group.size)
        self.total_rows += group.size
        dominant = max(group.labels.values())
        self.sum_dominant_rows += dominant
        if len(group.labels) == 1:
            self.pure_groups += 1
        for label in group.labels:
            self.per_label_groups[label] += 1


def evaluate_group_candidates(
    csv_path: Path,
    thresholds_ms: dict[str, int],
    *,
    block_size: int = 16 * 1024 * 1024,
) -> dict[str, Any]:
    builders = {name: CANDIDATE_BUILDERS[name] for name in thresholds_ms}
    summaries = {name: _GroupSummary() for name in thresholds_ms}
    reader = pacsv.open_csv(
        csv_path,
        read_options=pacsv.ReadOptions(block_size=block_size, use_threads=True),
        convert_options=pacsv.ConvertOptions(
            include_columns=[
                "FLOW_START_MILLISECONDS",
                "IPV4_SRC_ADDR",
                "IPV4_DST_ADDR",
                "Attack",
            ]
        ),
    )
    row_count = 0
    for batch in reader:
        starts = batch.column(0).to_numpy(zero_copy_only=False)
        sources = batch.column(1).to_pylist()
        destinations = batch.column(2).to_pylist()
        labels = batch.column(3).to_pylist()
        for timestamp, source, destination, label in zip(
            starts, sources, destinations, labels, strict=True
        ):
            value = int(timestamp)
            row_count += 1
            for name, builder in builders.items():
                summary = summaries[name]
                key = builder(source, destination)
                group = summary.active.get(key)
                if group is None:
                    summary.active[key] = _ActiveGroup(value, 1, Counter({label: 1}))
                    continue
                if value - group.last_timestamp > thresholds_ms[name]:
                    summary.finalize(group)
                    summary.active[key] = _ActiveGroup(value, 1, Counter({label: 1}))
                else:
                    group.last_timestamp = value
                    group.size += 1
                    group.labels[label] += 1

    output: dict[str, Any] = {"row_count": row_count, "candidates": {}}
    for name, summary in summaries.items():
        for group in summary.active.values():
            summary.finalize(group)
        sizes = np.asarray(summary.sizes, dtype=np.int64)
        group_count = int(sizes.size)
        output["candidates"][name] = {
            "threshold_ms": thresholds_ms[name],
            "group_count": group_count,
            "group_size": {
                "median": float(np.median(sizes)) if group_count else None,
                "p90": float(np.quantile(sizes, 0.9)) if group_count else None,
                "p99": float(np.quantile(sizes, 0.99)) if group_count else None,
                "maximum": int(sizes.max()) if group_count else None,
            },
            "pure_group_fraction": summary.pure_groups / group_count if group_count else None,
            "flow_weighted_label_purity": (
                summary.sum_dominant_rows / summary.total_rows if summary.total_rows else None
            ),
            "per_label_group_count": dict(sorted(summary.per_label_groups.items())),
            "largest_group_flow_fraction": (
                int(sizes.max()) / summary.total_rows if summary.total_rows else None
            ),
            "supports_three_way_split_by_label": {
                label: count >= 3 for label, count in sorted(summary.per_label_groups.items())
            },
            "supports_train_five_fold_by_label_upper_bound": {
                label: count >= 8 for label, count in sorted(summary.per_label_groups.items())
            },
        }
    return output


def write_grouping_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
