#!/usr/bin/env python3
"""Run the bounded, diagnostic NF3 Dataset-v4 feasibility pilot.

This tool intentionally operates on a pre-built Git-external stratified sample.
It does not download data, train Qwen, or produce formal Evidence Utility labels.
Temporal and relation features are computed from earlier rows in the sample only;
the resulting deltas are therefore feasibility diagnostics, not paper metrics.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
import hashlib
import ipaddress
import json
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score


HORIZONS_MS = (10_000, 60_000, 300_000)

IDENTITY_COLUMNS = {
    "FLOW_START_MILLISECONDS",
    "FLOW_END_MILLISECONDS",
    "IPV4_SRC_ADDR",
    "IPV4_DST_ADDR",
    "source_dataset",
    "source_row_index",
    "Label",
    "Attack",
}
PORT_COLUMNS = {"L4_SRC_PORT", "L4_DST_PORT"}


def broad_label(source: str, fine: str) -> str | None:
    """Return a provisional broad label, preserving unsupported labels as None."""

    if fine == "Benign":
        return "Benign"
    if fine in {
        "DoS",
        "dos",
        "DoS_attacks-GoldenEye",
        "DoS_attacks-Hulk",
        "DoS_attacks-SlowHTTPTest",
        "DoS_attacks-Slowloris",
    }:
        return "DoS"
    if fine in {
        "DDoS",
        "ddos",
        "DDoS_attacks-LOIC-HTTP",
        "DDOS_attack-LOIC-UDP",
        "DDOS_attack-HOIC",
    }:
        return "DDoS"
    if fine in {"Reconnaissance", "scanning"}:
        return "Recon_Scanning"
    if fine in {"FTP-BruteForce", "SSH-Bruteforce", "password"}:
        return "Credential"
    if fine in {
        "Brute_Force_-Web",
        "Brute_Force_-XSS",
        "SQL_Injection",
        "injection",
        "xss",
    }:
        return "Web_Injection"
    if source == "cse" and fine == "Bot":
        return "Bot_C2"
    return None


def stable_fold(group: str, test_fraction: float = 0.25) -> str:
    value = int.from_bytes(
        hashlib.blake2b(group.encode("utf-8"), digest_size=8).digest(), "big"
    )
    return "test" if value / 2**64 < test_fraction else "train"


@dataclass
class RollingWindow:
    horizon_ms: int
    events: deque[tuple[int, str, str, int, int, int]] = field(
        default_factory=deque
    )
    src_count: Counter[str] = field(default_factory=Counter)
    src_bytes: Counter[str] = field(default_factory=Counter)
    src_packets: Counter[str] = field(default_factory=Counter)
    dst_count: Counter[str] = field(default_factory=Counter)
    src_dst_count: Counter[tuple[str, str]] = field(default_factory=Counter)
    src_port_count: Counter[tuple[str, int]] = field(default_factory=Counter)
    dst_src_count: Counter[tuple[str, str]] = field(default_factory=Counter)
    src_neighbor_count: Counter[tuple[str, str, int]] = field(default_factory=Counter)
    src_unique_dst: Counter[str] = field(default_factory=Counter)
    src_unique_port: Counter[str] = field(default_factory=Counter)
    dst_unique_src: Counter[str] = field(default_factory=Counter)
    src_unique_neighbor: Counter[str] = field(default_factory=Counter)

    def expire(self, now_ms: int) -> None:
        cutoff = now_ms - self.horizon_ms
        while self.events and self.events[0][0] < cutoff:
            ts, src, dst, dport, byte_count, packet_count = self.events.popleft()
            del ts
            self.src_count[src] -= 1
            self.src_bytes[src] -= byte_count
            self.src_packets[src] -= packet_count
            self.dst_count[dst] -= 1
            self._decrement_unique(self.src_dst_count, (src, dst), self.src_unique_dst, src)
            self._decrement_unique(
                self.src_port_count, (src, dport), self.src_unique_port, src
            )
            self._decrement_unique(
                self.dst_src_count, (dst, src), self.dst_unique_src, dst
            )
            self._decrement_unique(
                self.src_neighbor_count,
                (src, dst, dport),
                self.src_unique_neighbor,
                src,
            )

    @staticmethod
    def _decrement_unique(
        counts: Counter[Any], key: Any, unique: Counter[str], owner: str
    ) -> None:
        counts[key] -= 1
        if counts[key] == 0:
            del counts[key]
            unique[owner] -= 1

    def add(
        self,
        ts: int,
        src: str,
        dst: str,
        dport: int,
        byte_count: int,
        packet_count: int,
    ) -> None:
        self.events.append((ts, src, dst, dport, byte_count, packet_count))
        self.src_count[src] += 1
        self.src_bytes[src] += byte_count
        self.src_packets[src] += packet_count
        self.dst_count[dst] += 1
        self._increment_unique(self.src_dst_count, (src, dst), self.src_unique_dst, src)
        self._increment_unique(
            self.src_port_count, (src, dport), self.src_unique_port, src
        )
        self._increment_unique(
            self.dst_src_count, (dst, src), self.dst_unique_src, dst
        )
        self._increment_unique(
            self.src_neighbor_count,
            (src, dst, dport),
            self.src_unique_neighbor,
            src,
        )

    @staticmethod
    def _increment_unique(
        counts: Counter[Any], key: Any, unique: Counter[str], owner: str
    ) -> None:
        if counts[key] == 0:
            unique[owner] += 1
        counts[key] += 1

    def features(self, src: str, dst: str, dport: int) -> list[float]:
        seconds = self.horizon_ms / 1000.0
        return [
            float(self.src_count[src]),
            float(self.src_unique_dst[src]),
            float(self.src_unique_port[src]),
            float(self.src_port_count[(src, dport)]),
            float(self.dst_count[dst]),
            float(self.src_count[src]) / seconds,
            float(self.src_packets[src]) / seconds,
            float(self.src_bytes[src]) / seconds,
            float(self.src_dst_count[(src, dst)]),
            float(self.dst_unique_src[dst]),
            float(self.src_unique_neighbor[src]),
        ]


def build_past_only_features(
    table: dict[str, np.ndarray],
    *,
    history_eligible: np.ndarray | None = None,
) -> np.ndarray:
    """Build sample-local features while excluding all equal-timestamp rows.

    ``history_eligible`` is a private lookup permission mask. Every target row
    still receives features, but a masked row never enters any later row's
    history. The default preserves the preceding pilot's all-row behavior.
    """

    n = len(table["Attack"])
    if history_eligible is None:
        history_eligible = np.ones(n, dtype=bool)
    else:
        history_eligible = np.asarray(history_eligible, dtype=bool)
        if history_eligible.shape != (n,):
            raise ValueError("history_eligible must match the table row count")
    output = np.zeros((n, len(HORIZONS_MS) * 11 + 1), dtype=np.float64)
    for source in sorted(set(table["source_dataset"].tolist())):
        members = np.flatnonzero(table["source_dataset"] == source)
        ordered = members[np.argsort(table["FLOW_START_MILLISECONDS"][members], kind="stable")]
        windows = [RollingWindow(horizon) for horizon in HORIZONS_MS]
        last_source_time: dict[str, int] = {}
        cursor = 0
        while cursor < len(ordered):
            ts = int(table["FLOW_START_MILLISECONDS"][ordered[cursor]])
            end = cursor + 1
            while end < len(ordered) and int(
                table["FLOW_START_MILLISECONDS"][ordered[end]]
            ) == ts:
                end += 1
            group = ordered[cursor:end]
            for window in windows:
                window.expire(ts)
            for index in group:
                src = str(table["IPV4_SRC_ADDR"][index])
                dst = str(table["IPV4_DST_ADDR"][index])
                dport = int(table["L4_DST_PORT"][index])
                values: list[float] = []
                for window in windows:
                    values.extend(window.features(src, dst, dport))
                previous = last_source_time.get(src)
                values.append(float(ts - previous) if previous is not None else -1.0)
                output[index] = values
            for index in group:
                if not history_eligible[index]:
                    continue
                src = str(table["IPV4_SRC_ADDR"][index])
                dst = str(table["IPV4_DST_ADDR"][index])
                dport = int(table["L4_DST_PORT"][index])
                byte_count = int(table["IN_BYTES"][index]) + int(table["OUT_BYTES"][index])
                packet_count = int(table["IN_PKTS"][index]) + int(table["OUT_PKTS"][index])
                for window in windows:
                    window.add(ts, src, dst, dport, byte_count, packet_count)
                last_source_time[src] = ts
            cursor = end
    return output


def table_to_numpy(path: Path) -> dict[str, np.ndarray]:
    table = pq.read_table(path)
    return {
        name: np.asarray(table[name].to_numpy(zero_copy_only=False))
        for name in table.column_names
    }


def safe_matrix(data: dict[str, np.ndarray], *, include_ports: bool) -> tuple[np.ndarray, list[str]]:
    names = [name for name in data if name not in IDENTITY_COLUMNS]
    if not include_ports:
        names = [name for name in names if name not in PORT_COLUMNS]
    matrix = np.column_stack([np.asarray(data[name], dtype=np.float64) for name in names])
    matrix = np.nan_to_num(matrix, nan=0.0, posinf=1e15, neginf=-1e15)
    matrix = np.sign(matrix) * np.log1p(np.abs(matrix))
    return matrix, names


def ip_number(value: str) -> int:
    try:
        return int(ipaddress.ip_address(value))
    except ValueError:
        return int.from_bytes(hashlib.blake2b(value.encode(), digest_size=4).digest(), "big")


def shortcut_matrix(data: dict[str, np.ndarray]) -> np.ndarray:
    source_codes = {name: index for index, name in enumerate(sorted(set(data["source_dataset"].tolist())))}
    start = np.asarray(data["FLOW_START_MILLISECONDS"], dtype=np.int64)
    src = np.array([ip_number(str(value)) for value in data["IPV4_SRC_ADDR"]], dtype=np.uint64)
    dst = np.array([ip_number(str(value)) for value in data["IPV4_DST_ADDR"]], dtype=np.uint64)
    return np.column_stack(
        [
            src,
            dst,
            np.asarray(data["L4_SRC_PORT"], dtype=np.float64),
            np.asarray(data["L4_DST_PORT"], dtype=np.float64),
            start // 86_400_000,
            (start % 86_400_000) / 1000.0,
            np.array([source_codes[x] for x in data["source_dataset"]]),
        ]
    ).astype(np.float64)


def split_mask(data: dict[str, np.ndarray], eligible: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    split = np.full(len(eligible), "excluded", dtype=object)
    group_folds: dict[str, str] = {}
    group_counts: Counter[str] = Counter()
    for index in np.flatnonzero(eligible):
        ts = int(data["FLOW_START_MILLISECONDS"][index])
        src = str(data["IPV4_SRC_ADDR"][index])
        dst = str(data["IPV4_DST_ADDR"][index])
        pair = "|".join(sorted((src, dst)))
        group = f"{data['source_dataset'][index]}|{ts // 300_000}|{pair}"
        fold = group_folds.setdefault(group, stable_fold(group))
        split[index] = fold
        group_counts[fold] += 1
    overlap = set(k for k, v in group_folds.items() if v == "train") & set(
        k for k, v in group_folds.items() if v == "test"
    )
    return split, {
        "group_definition": "source_dataset + 5-minute UTC block + unordered endpoint pair",
        "assignment": "deterministic BLAKE2b 75/25 group hash",
        "train_rows": group_counts["train"],
        "test_rows": group_counts["test"],
        "cross_split_group_overlap": len(overlap),
    }


def fit_and_score(
    matrix: np.ndarray,
    labels: np.ndarray,
    train: np.ndarray,
    test: np.ndarray,
    *,
    seed: int,
    trees: int,
) -> dict[str, Any]:
    model = RandomForestClassifier(
        n_estimators=trees,
        max_depth=20,
        min_samples_leaf=2,
        class_weight="balanced_subsample",
        n_jobs=-1,
        random_state=seed,
    )
    model.fit(matrix[train], labels[train])
    prediction = model.predict(matrix[test])
    classes = sorted(set(labels[test].tolist()))
    return {
        "train_n": int(train.sum()),
        "test_n": int(test.sum()),
        "accuracy": float(accuracy_score(labels[test], prediction)),
        "macro_f1": float(f1_score(labels[test], prediction, labels=classes, average="macro", zero_division=0)),
        "per_class_f1": {
            label: float(score)
            for label, score in zip(
                classes,
                f1_score(labels[test], prediction, labels=classes, average=None, zero_division=0),
                strict=True,
            )
        },
        "classes": classes,
        "confusion_matrix": confusion_matrix(labels[test], prediction, labels=classes).tolist(),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    data = table_to_numpy(args.pilot)
    mapped = np.array(
        [broad_label(str(s), str(f)) for s, f in zip(data["source_dataset"], data["Attack"], strict=True)],
        dtype=object,
    )
    eligible = np.array([value is not None for value in mapped], dtype=bool)
    split, split_report = split_mask(data, eligible)
    train = eligible & (split == "train")
    test = eligible & (split == "test")
    train_classes = set(mapped[train].tolist())
    test_classes = set(mapped[test].tolist())
    common = train_classes & test_classes
    train &= np.array([value in common for value in mapped])
    test &= np.array([value in common for value in mapped])

    basic_without_ports, basic_without_names = safe_matrix(data, include_ports=False)
    basic_with_ports, basic_with_names = safe_matrix(data, include_ports=True)
    temporal_relation = build_past_only_features(data)
    full = np.column_stack([basic_without_ports, np.log1p(temporal_relation.clip(min=0))])
    shortcut = shortcut_matrix(data)

    results = {
        "status": "DIAGNOSTIC_ONLY",
        "pilot_n": len(mapped),
        "eligible_broad_n": int(eligible.sum()),
        "broad_counts": dict(sorted(Counter(mapped[eligible].tolist()).items())),
        "split": split_report,
        "feature_contract": {
            "safe_basic_without_ports": basic_without_names,
            "safe_basic_with_ports": basic_with_names,
            "temporal_horizons_seconds": [10, 60, 300],
            "temporal_relation_context": "strictly earlier rows in deterministic stratified pilot only",
            "equal_timestamp_excluded": True,
        },
        "shortcut": fit_and_score(shortcut, mapped, train, test, seed=args.seed, trees=args.trees),
        "safe_basic_without_ports": fit_and_score(
            basic_without_ports, mapped, train, test, seed=args.seed, trees=args.trees
        ),
        "safe_basic_with_ports": fit_and_score(
            basic_with_ports, mapped, train, test, seed=args.seed, trees=args.trees
        ),
        "safe_full": fit_and_score(full, mapped, train, test, seed=args.seed, trees=args.trees),
    }
    results["per_class_basic_full_delta"] = {
        label: results["safe_full"]["per_class_f1"].get(label, 0.0)
        - results["safe_basic_without_ports"]["per_class_f1"].get(label, 0.0)
        for label in sorted(common)
    }

    cross_source: dict[str, Any] = {}
    for held_out in sorted(set(data["source_dataset"].tolist())):
        source_train = eligible & (data["source_dataset"] != held_out)
        source_test = eligible & (data["source_dataset"] == held_out)
        source_common = set(mapped[source_train].tolist()) & set(mapped[source_test].tolist())
        source_train &= np.array([value in source_common for value in mapped])
        source_test &= np.array([value in source_common for value in mapped])
        if len(source_common) < 2 or source_train.sum() == 0 or source_test.sum() == 0:
            cross_source[held_out] = {"status": "INSUFFICIENT_SHARED_CLASSES", "shared_classes": sorted(source_common)}
            continue
        score = fit_and_score(
            full, mapped, source_train, source_test, seed=args.seed, trees=args.trees
        )
        score["status"] = "DIAGNOSTIC"
        score["shared_classes"] = sorted(source_common)
        cross_source[held_out] = score
    results["cross_source_safe_full"] = cross_source
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260815)
    parser.add_argument("--trees", type=int, default=120)
    args = parser.parse_args()
    result = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
