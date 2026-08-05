#!/usr/bin/env python3
"""Reproduce the August 2026 dataset-unblocking audit.

The script performs no model training and downloads nothing.  It consumes the
official CasinoLimit metadata plus ``labelled_flows.zip`` and the selectively
cached UWF Parquet/metrics files.  Outputs are evidence tables for the
``2026-08-unblocking`` report; policy decisions remain explicit in the reports.
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import hashlib
import io
import json
import math
import re
import statistics
import unicodedata
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

import numpy as np
import pandas as pd

from formal_selection_audit import OBSERVABILITY, load_stix, map_attack_id


AUDIT_SEED = 20260804
CASINO_MD5 = "4958750766c5140919e7e584b2d9bed6"
FLOW_COLUMNS = ["timestamp", "src_ip", "dst_ip", "src_port", "dst_port"]


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def digest(path: Path, algorithm: str = "sha256") -> str:
    h = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_instance(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value)).strip().casefold()
    return re.sub(r"\s+", "", value)


def clean_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = str(value).strip()
    return "" if text.casefold() in {"", "nan", "none", "null", "<na>"} else text


def clean_port(value: Any) -> int | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if not number.is_integer() or not 0 <= number <= 65535:
        return None
    return int(number)


def percentile(values: Iterable[int], q: float) -> float:
    values = list(values)
    return float(np.percentile(values, q)) if values else 0.0


class CountingReader:
    """Count physical and non-RFC rows while pandas consumes a ZipExtFile."""

    def __init__(self, raw: Any) -> None:
        self.raw = raw
        self.newlines = 0
        self.nonstandard_rows = 0
        self._tail = b""
        self._line_index = 0

    def _inspect_complete_lines(self, data: bytes, eof: bool = False) -> None:
        combined = self._tail + data
        parts = combined.split(b"\n")
        if not eof:
            self._tail = parts.pop()
        else:
            self._tail = b""
        for line in parts:
            line = line.rstrip(b"\r")
            if self._line_index > 0 and line and line.count(b",") != 11:
                self.nonstandard_rows += 1
            self._line_index += 1

    def read(self, size: int = -1) -> bytes:
        data = self.raw.read(size)
        self.newlines += data.count(b"\n")
        self._inspect_complete_lines(data, eof=not data)
        return data

    def readable(self) -> bool:
        return True


@dataclass(frozen=True)
class RelationLabel:
    label_id: str
    technique: str
    doubt: bool
    raw: dict[str, Any]


def wildcard_mask(values: pd.Series, pattern: str) -> pd.Series:
    pattern = clean_text(pattern)
    if not pattern:
        return pd.Series(False, index=values.index)
    if "*" in pattern or "?" in pattern:
        return values.astype(str).map(lambda item: fnmatch.fnmatchcase(item, pattern))
    return values.astype(str).eq(pattern)


def exact_mask(values: pd.Series, expected: str) -> pd.Series:
    expected = clean_text(expected)
    if not expected or "*" in expected or "?" in expected:
        return pd.Series(False, index=values.index)
    return values.astype(str).eq(expected)


def port_mask(values: pd.Series, expected: int | None, allow_missing_relation: bool) -> pd.Series:
    if expected is None:
        return pd.Series(bool(allow_missing_relation), index=values.index)
    return values.eq(expected)


def candidate_payload(frame: pd.DataFrame, positions: np.ndarray, start_ns: np.datetime64) -> dict[str, Any]:
    if len(positions) == 0:
        return {}
    pos = int(positions[0])
    row = frame.iloc[pos]
    delta_ms = float((row["timestamp"].to_datetime64() - start_ns) / np.timedelta64(1, "ms"))
    return {
        "flow_row": pos,
        "timestamp": row["timestamp"].isoformat(),
        "src_ip": clean_text(row["src_ip"]),
        "dst_ip": clean_text(row["dst_ip"]),
        "src_port": None if pd.isna(row["src_port"]) else int(row["src_port"]),
        "dst_port": None if pd.isna(row["dst_port"]) else int(row["dst_port"]),
        "time_delta_ms_from_relation_start": delta_ms,
    }


def summarize_neighbors(frame: pd.DataFrame, left: int, right: int, limit: int = 3) -> str:
    records = []
    for pos in range(left, min(right, left + limit)):
        row = frame.iloc[pos]
        records.append(
            {
                "row": pos,
                "ts": row["timestamp"].isoformat(),
                "src": clean_text(row["src_ip"]),
                "dst": clean_text(row["dst_ip"]),
                "sp": None if pd.isna(row["src_port"]) else int(row["src_port"]),
                "dp": None if pd.isna(row["dst_port"]) else int(row["dst_port"]),
            }
        )
    return json.dumps(records, ensure_ascii=False, separators=(",", ":"))


def load_relation_labels(base: Path, instance: str, relations: dict[str, Any]) -> dict[str, list[RelationLabel]]:
    labels = json.loads((base / "system_labels" / f"{instance}.json").read_text(encoding="utf-8"))
    by_uid: dict[str, list[RelationLabel]] = defaultdict(list)
    for label_id, label in labels.items():
        technique = label["technique"].split(":", 1)[0].strip()
        entry = RelationLabel(label_id, technique, bool(label.get("doubt")), label)
        for uid in label.get("event_uids", []):
            by_uid[str(uid)].append(entry)
    result: dict[str, list[RelationLabel]] = {}
    for relation_id, relation in relations.items():
        joined: list[RelationLabel] = []
        for uid in relation.get("event_uids", []):
            joined.extend(by_uid.get(str(uid), []))
        result[relation_id] = joined
    return result


def read_flow_member(archive: zipfile.ZipFile, member: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    with archive.open(member) as raw:
        counted = CountingReader(raw)
        # The official export leaves commas inside the trailing proctitles and
        # labels fields unquoted.  Those rows are not RFC-compliant CSV, but the
        # five leading join fields remain unambiguous.  Reading only named join
        # columns preserves labelled traffic instead of systematically dropping
        # it; CountingReader records the non-standard rows separately.
        chunks = pd.read_csv(
            counted,
            usecols=FLOW_COLUMNS,
            skipinitialspace=True,
            engine="c",
            chunksize=500_000,
            low_memory=False,
        )
        retained = [chunk.copy() for chunk in chunks]
        frame = pd.concat(retained, ignore_index=True) if retained else pd.DataFrame(columns=FLOW_COLUMNS)
    physical_rows = max(0, counted.newlines - 1)
    for column in ["src_ip", "dst_ip"]:
        frame[column] = frame[column].map(clean_text)
    for column in ["src_port", "dst_port"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("Int64")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"].map(clean_text), errors="coerce")
    invalid_time = int(frame["timestamp"].isna().sum())
    frame = frame.dropna(subset=["timestamp"]).reset_index(drop=True)
    monotonic = bool(frame["timestamp"].is_monotonic_increasing)
    if not monotonic:
        frame = frame.sort_values("timestamp", kind="stable").reset_index(drop=True)
    return frame, {
        "physical_data_rows": physical_rows,
        "parsed_rows": len(frame),
        "unquoted_trailing_field_rows": counted.nonstandard_rows,
        "malformed_or_skipped_rows": max(0, physical_rows - len(frame) - invalid_time),
        "invalid_timestamp_rows": invalid_time,
        "timestamp_monotonic_before_sort": monotonic,
    }


def relation_match(
    frame: pd.DataFrame,
    relation: dict[str, Any],
) -> dict[str, Any]:
    data = relation.get("data") or {}
    start = pd.to_datetime(clean_text(data.get("start_time")), errors="coerce")
    end = pd.to_datetime(clean_text(data.get("end_time")), errors="coerce")
    if pd.isna(start) or pd.isna(end) or end < start:
        return {
            "parse_error": "invalid_relation_time",
            "time_only_hits": 0,
            "selected_positions": np.array([], dtype=int),
            "selected_rule": "R5",
            "zero_hit_reason": "invalid_relation_time",
            "manual_review_required": True,
        }

    timestamps = frame["timestamp"].to_numpy(dtype="datetime64[ns]")
    start_ns, end_ns = start.to_datetime64(), end.to_datetime64()
    left = int(np.searchsorted(timestamps, start_ns, side="left"))
    right = int(np.searchsorted(timestamps, end_ns, side="right"))
    window = frame.iloc[left:right]
    local = np.arange(left, right, dtype=int)

    src_ip = clean_text(data.get("src_ip"))
    dst_ip = clean_text(data.get("dst_ip"))
    src_port = clean_port(data.get("src_port"))
    dst_port = clean_port(data.get("dst_port"))
    explicit_wildcard = any(token in src_ip + dst_ip for token in "*?")
    missing_port = src_port is None or dst_port is None

    strict_ready = bool(src_ip and dst_ip and not explicit_wildcard and src_port is not None and dst_port is not None)
    if len(window):
        strict_direct = (
            exact_mask(window["src_ip"], src_ip)
            & exact_mask(window["dst_ip"], dst_ip)
            & port_mask(window["src_port"], src_port, False)
            & port_mask(window["dst_port"], dst_port, False)
        ) if strict_ready else pd.Series(False, index=window.index)
        strict_reverse = (
            exact_mask(window["dst_ip"], src_ip)
            & exact_mask(window["src_ip"], dst_ip)
            & port_mask(window["dst_port"], src_port, False)
            & port_mask(window["src_port"], dst_port, False)
        ) if strict_ready else pd.Series(False, index=window.index)

        endpoints_direct = wildcard_mask(window["src_ip"], src_ip) & wildcard_mask(window["dst_ip"], dst_ip)
        endpoints_reverse = wildcard_mask(window["dst_ip"], src_ip) & wildcard_mask(window["src_ip"], dst_ip)
        ports_direct = port_mask(window["src_port"], src_port, True) & port_mask(window["dst_port"], dst_port, True)
        ports_reverse = port_mask(window["dst_port"], src_port, True) & port_mask(window["src_port"], dst_port, True)
        endpoint_any = endpoints_direct | endpoints_reverse
        endpoint_port_any = (endpoints_direct & ports_direct) | (endpoints_reverse & ports_reverse)
    else:
        strict_direct = strict_reverse = endpoint_any = endpoint_port_any = pd.Series(dtype=bool)
        endpoints_direct = endpoints_reverse = ports_direct = ports_reverse = pd.Series(dtype=bool)

    strict_positions = local[strict_direct.to_numpy(dtype=bool)] if len(window) else np.array([], dtype=int)
    reverse_positions = local[strict_reverse.to_numpy(dtype=bool)] if len(window) else np.array([], dtype=int)
    normalized_positions = np.unique(np.concatenate([strict_positions, reverse_positions]))
    endpoint_positions = local[endpoint_any.to_numpy(dtype=bool)] if len(window) else np.array([], dtype=int)
    endpoint_port_positions = local[endpoint_port_any.to_numpy(dtype=bool)] if len(window) else np.array([], dtype=int)
    wildcard_positions = endpoint_port_positions if explicit_wildcard else np.array([], dtype=int)

    if len(strict_positions):
        selected, rule = strict_positions, "R0"
    elif len(reverse_positions):
        selected, rule = reverse_positions, "R1"
    elif len(normalized_positions):
        selected, rule = normalized_positions, "R2"
    elif len(endpoint_port_positions):
        if explicit_wildcard and missing_port:
            selected, rule = endpoint_port_positions, "R3+R4"
        elif explicit_wildcard:
            selected, rule = endpoint_port_positions, "R3"
        elif missing_port:
            selected, rule = endpoint_port_positions, "R4"
        else:
            selected, rule = endpoint_port_positions, "R2"
    else:
        selected, rule = np.array([], dtype=int), "R5"

    anomaly_positions = np.array([], dtype=int)
    anomaly_kind = ""
    if len(selected) == 0 and len(window):
        transformed_src = src_ip
        transformed_dst = dst_ip
        if src_ip.startswith("10.35."):
            transformed_src = "10.135." + src_ip[len("10.35."):]
            anomaly_kind = "diagnostic_10.35_to_10.135"
        elif src_ip.startswith("10.135."):
            transformed_src = "10.35." + src_ip[len("10.135."):]
            anomaly_kind = "diagnostic_10.135_to_10.35"
        if dst_ip.startswith("10.35."):
            transformed_dst = "10.135." + dst_ip[len("10.35."):]
            anomaly_kind = anomaly_kind or "diagnostic_10.35_to_10.135"
        elif dst_ip.startswith("10.135."):
            transformed_dst = "10.35." + dst_ip[len("10.135."):]
            anomaly_kind = anomaly_kind or "diagnostic_10.135_to_10.35"
        if anomaly_kind:
            ad = wildcard_mask(window["src_ip"], transformed_src) & wildcard_mask(window["dst_ip"], transformed_dst)
            ar = wildcard_mask(window["dst_ip"], transformed_src) & wildcard_mask(window["src_ip"], transformed_dst)
            ap = (ad & ports_direct) | (ar & ports_reverse)
            anomaly_positions = local[ap.to_numpy(dtype=bool)]

    if len(window) == 0:
        reason = "no_flow_in_closed_time_interval"
    elif len(endpoint_positions) == 0:
        reason = "endpoint_mismatch"
    elif len(endpoint_port_positions) == 0:
        reason = "available_port_constraint_mismatch"
    else:
        reason = ""

    direction = ""
    if len(selected) and len(window):
        selected_local = selected - left
        direct_selected = bool((endpoints_direct & ports_direct).to_numpy(dtype=bool)[selected_local].any())
        reverse_selected = bool((endpoints_reverse & ports_reverse).to_numpy(dtype=bool)[selected_local].any())
        direction = "both" if direct_selected and reverse_selected else ("direct" if direct_selected else "reverse")

    nearest_delta_ms: float | None = None
    if len(timestamps):
        insertion = int(np.searchsorted(timestamps, start_ns))
        candidates = [i for i in [insertion - 1, insertion] if 0 <= i < len(timestamps)]
        if candidates:
            nearest_delta_ms = min(abs(float((timestamps[i] - start_ns) / np.timedelta64(1, "ms"))) for i in candidates)

    # Tolerance results are diagnostics only.  They quantify millisecond
    # rounding sensitivity and are never promoted to the selected rule without
    # an independently approved policy/human review.
    tolerance_hits: dict[int, int] = {}
    if len(timestamps):
        for tolerance_ms in [1, 10, 100, 1000]:
            delta = np.timedelta64(tolerance_ms, "ms")
            t_left = int(np.searchsorted(timestamps, start_ns - delta, side="left"))
            t_right = int(np.searchsorted(timestamps, end_ns + delta, side="right"))
            extended = frame.iloc[t_left:t_right]
            if len(extended):
                ed = wildcard_mask(extended["src_ip"], src_ip) & wildcard_mask(extended["dst_ip"], dst_ip)
                er = wildcard_mask(extended["dst_ip"], src_ip) & wildcard_mask(extended["src_ip"], dst_ip)
                epd = port_mask(extended["src_port"], src_port, True) & port_mask(extended["dst_port"], dst_port, True)
                epr = port_mask(extended["dst_port"], src_port, True) & port_mask(extended["src_port"], dst_port, True)
                tolerance_hits[tolerance_ms] = int(((ed & epd) | (er & epr)).sum())
            else:
                tolerance_hits[tolerance_ms] = 0
    else:
        tolerance_hits = {value: 0 for value in [1, 10, 100, 1000]}

    return {
        "parse_error": "",
        "start_ns": start_ns,
        "left": left,
        "right": right,
        "time_only_hits": len(window),
        "strict_directed_hits": len(strict_positions),
        "reverse_hits": len(reverse_positions),
        "direction_normalized_hits": len(normalized_positions),
        "bidirectional_endpoint_set_hits": len(endpoint_positions),
        "endpoint_hits": len(endpoint_positions),
        "endpoint_port_hits": len(endpoint_port_positions),
        "wildcard_hits": len(wildcard_positions),
        "selected_positions": selected,
        "selected_rule": rule,
        "selected_direction": direction,
        "zero_hit_reason": reason,
        "manual_review_required": bool(len(selected) != 1 or rule != "R0"),
        "anomaly_candidate_hits": len(anomaly_positions),
        "anomaly_kind": anomaly_kind if len(anomaly_positions) else "",
        "anomaly_positions": anomaly_positions,
        "nearest_time_delta_ms": nearest_delta_ms,
        "tolerance_1ms_endpoint_port_hits": tolerance_hits[1],
        "tolerance_10ms_endpoint_port_hits": tolerance_hits[10],
        "tolerance_100ms_endpoint_port_hits": tolerance_hits[100],
        "tolerance_1000ms_endpoint_port_hits": tolerance_hits[1000],
        "explicit_wildcard": explicit_wildcard,
        "missing_relation_port": missing_port,
    }


def casino_audit(cache: Path, report: Path, stix: dict[str, Any]) -> dict[str, Any]:
    base = cache / "downloads" / "casinolimit_output" / "output"
    flow_zip = cache / "downloads" / "casinolimit_labelled_flows.zip"
    if digest(flow_zip, "md5") != CASINO_MD5:
        raise RuntimeError("CasinoLimit labelled_flows.zip MD5 mismatch")

    system_paths = sorted((base / "system_labels").glob("*.json"))
    relation_paths = sorted((base / "relations").glob("*_relations.json"))
    relation_instances = {normalize_instance(p.stem.removesuffix("_relations")): p for p in relation_paths}
    label_instances = {normalize_instance(p.stem): p for p in system_paths}

    all_support: dict[str, set[str]] = defaultdict(set)
    reliable_support: dict[str, set[str]] = defaultdict(set)
    raw_records: Counter[str] = Counter()
    doubt_records: Counter[str] = Counter()
    for path in system_paths:
        instance = normalize_instance(path.stem)
        for label in json.loads(path.read_text(encoding="utf-8")).values():
            technique = label["technique"].split(":", 1)[0].strip()
            all_support[technique].add(instance)
            raw_records[technique] += 1
            if label.get("doubt"):
                doubt_records[technique] += 1
            else:
                reliable_support[technique].add(instance)

    result_rows: list[dict[str, Any]] = []
    relation_base: dict[tuple[str, str], dict[str, Any]] = {}
    parse_stats: list[dict[str, Any]] = []
    relation_support: dict[str, set[str]] = defaultdict(set)
    joined_instances: dict[str, set[str]] = defaultdict(set)
    reliable_joined_instances: dict[str, set[str]] = defaultdict(set)
    joined_relations: dict[str, set[tuple[str, str]]] = defaultdict(set)
    flow_ids: dict[str, set[tuple[str, int]]] = defaultdict(set)
    flow_ids_by_instance: dict[str, dict[str, set[int]]] = defaultdict(lambda: defaultdict(set))

    with zipfile.ZipFile(flow_zip) as archive:
        member_map: dict[str, str] = {}
        collisions: dict[str, list[str]] = defaultdict(list)
        for name in archive.namelist():
            if not name.casefold().endswith(".csv"):
                continue
            key = normalize_instance(PurePosixPath(name).stem)
            collisions[key].append(name)
            if key not in member_map:
                member_map[key] = name
        duplicate_member_keys = {key: names for key, names in collisions.items() if len(names) > 1}

        for index, (instance, relation_path) in enumerate(sorted(relation_instances.items()), 1):
            relations = json.loads(relation_path.read_text(encoding="utf-8"))
            labels_by_relation = load_relation_labels(base, instance, relations)
            member = member_map.get(instance)
            if member is None:
                for relation_id, relation in relations.items():
                    base_row = {
                        "relation_id": relation_id,
                        "instance": instance,
                        "time_only_hits": 0,
                        "strict_directed_hits": 0,
                        "reverse_hits": 0,
                        "direction_normalized_hits": 0,
                        "bidirectional_endpoint_set_hits": 0,
                        "endpoint_hits": 0,
                        "endpoint_port_hits": 0,
                        "wildcard_hits": 0,
                        "ambiguous_hit_count": 0,
                        "selected_rule": "R5",
                        "selected_hit_count": 0,
                        "zero_hit_reason": "missing_flow_member",
                        "manual_review_required": True,
                        "parse_error": "missing_flow_member",
                    }
                    relation_base[(instance, relation_id)] = base_row
                continue

            frame, stats = read_flow_member(archive, member)
            stats.update({"instance": instance, "member": member})
            parse_stats.append(stats)
            for relation_id, relation in relations.items():
                matched = relation_match(frame, relation)
                selected = matched.pop("selected_positions", np.array([], dtype=int))
                anomaly = matched.pop("anomaly_positions", np.array([], dtype=int))
                candidate_positions = selected if len(selected) else anomaly
                candidate = candidate_payload(frame, candidate_positions, matched.get("start_ns", np.datetime64("NaT")))
                start_ns = matched.pop("start_ns", None)
                left = matched.pop("left", 0)
                right = matched.pop("right", 0)
                labels = labels_by_relation.get(relation_id, [])
                base_row = {
                    "relation_id": relation_id,
                    "instance": instance,
                    **matched,
                    "ambiguous_hit_count": len(selected) if len(selected) > 1 else 0,
                    "selected_hit_count": len(selected),
                    "relation_event_uids": "|".join(map(str, relation.get("event_uids", []))),
                    "relation_raw": json.dumps(relation, ensure_ascii=False, separators=(",", ":")),
                    "candidate_flow": json.dumps(candidate, ensure_ascii=False, separators=(",", ":")) if candidate else "",
                    "neighbor_flows": summarize_neighbors(frame, left, right),
                    "label_multiplicity": len(labels),
                }
                relation_base[(instance, relation_id)] = base_row
                output_labels = labels or [RelationLabel("", "", False, {})]
                for label in output_labels:
                    row = {
                        **base_row,
                        "technique": label.technique,
                        "doubt": label.doubt,
                        "system_label_id": label.label_id,
                        "system_label_raw": json.dumps(label.raw, ensure_ascii=False, separators=(",", ":")) if label.raw else "",
                    }
                    result_rows.append(row)
                    if label.technique:
                        relation_support[label.technique].add(instance)
                        if len(selected):
                            joined_instances[label.technique].add(instance)
                            joined_relations[label.technique].add((instance, relation_id))
                            if not label.doubt:
                                reliable_joined_instances[label.technique].add(instance)
                            for pos in selected:
                                flow_ids[label.technique].add((instance, int(pos)))
                                flow_ids_by_instance[label.technique][instance].add(int(pos))
            print(f"CasinoLimit {index:02d}/{len(relation_instances)} {instance}: rows={len(frame)} relations={len(relations)}")

    join_columns = [
        "relation_id", "instance", "technique", "doubt", "system_label_id", "relation_event_uids",
        "strict_directed_hits", "reverse_hits", "direction_normalized_hits", "bidirectional_endpoint_set_hits",
        "time_only_hits", "endpoint_hits", "endpoint_port_hits", "wildcard_hits", "anomaly_candidate_hits",
        "anomaly_kind", "ambiguous_hit_count", "selected_rule", "selected_direction", "selected_hit_count",
        "zero_hit_reason", "manual_review_required", "nearest_time_delta_ms", "explicit_wildcard",
        "missing_relation_port", "tolerance_1ms_endpoint_port_hits", "tolerance_10ms_endpoint_port_hits",
        "tolerance_100ms_endpoint_port_hits", "tolerance_1000ms_endpoint_port_hits", "parse_error",
        "label_multiplicity",
    ]
    write_csv(report / "03_casinolimit_join_results.csv", result_rows, join_columns)

    # Greedy stratified manual queue: technique diversity, then instance diversity,
    # then difficult/doubt examples.  Recommendations are explicitly not gold.
    eligible = [row for row in result_rows if row["technique"]]
    eligible.sort(
        key=lambda row: (
            row["selected_hit_count"] > 0,
            row["ambiguous_hit_count"] == 0,
            not row["doubt"],
            row["technique"],
            row["instance"],
            row["relation_id"],
        )
    )
    selected_queue: list[dict[str, Any]] = []
    seen_relations: set[tuple[str, str]] = set()
    seen_techniques: set[str] = set()
    seen_instances: set[str] = set()

    def add_queue(row: dict[str, Any]) -> None:
        key = (row["instance"], row["relation_id"])
        if key not in seen_relations:
            selected_queue.append(row)
            seen_relations.add(key)
            seen_techniques.add(row["technique"])
            seen_instances.add(row["instance"])

    for row in eligible:
        if row["technique"] not in seen_techniques:
            add_queue(row)
    for row in eligible:
        if len(seen_instances) >= 20:
            break
        if row["instance"] not in seen_instances:
            add_queue(row)
    for row in eligible:
        if len(selected_queue) >= 45:
            break
        if row["doubt"] or row["selected_hit_count"] == 0 or row["ambiguous_hit_count"]:
            add_queue(row)

    queue_rows: list[dict[str, Any]] = []
    for row in selected_queue:
        if row["selected_hit_count"] == 0:
            judgement = "R5：自动规则未命中；异常诊断候选不得用于训练。"
            question = "relation是否存在地址/时间/成员错误，还是确实无对应Flow？"
        elif row["selected_hit_count"] > 1:
            judgement = "自动规则得到多条Flow；尚不能认定每条都承载该Technique。"
            question = "这些Flow是同一活动的双向/重复记录，还是需要进一步选择anchor？"
        else:
            judgement = f"{row['selected_rule']}得到唯一候选；仍需人工核验relation语义。"
            question = "候选Flow是否与system label的行为语义一致？"
        category = OBSERVABILITY.get(row["technique"], ("D", ""))[0]
        queue_rows.append(
            {
                "instance": row["instance"],
                "relation_id": row["relation_id"],
                "technique": row["technique"],
                "observability_category": category,
                "doubt": row["doubt"],
                "selected_rule": row["selected_rule"],
                "selected_hit_count": row["selected_hit_count"],
                "anomaly_candidate_hits": row["anomaly_candidate_hits"],
                "relation_raw": row["relation_raw"],
                "system_label_raw": row["system_label_raw"],
                "candidate_flow": row["candidate_flow"],
                "time_delta_ms": json.loads(row["candidate_flow"]).get("time_delta_ms_from_relation_start") if row["candidate_flow"] else "",
                "direction": row["selected_direction"],
                "relation_ips_ports": json.dumps(json.loads(row["relation_raw"]).get("data", {}), ensure_ascii=False, separators=(",", ":")),
                "neighbor_flows": row["neighbor_flows"],
                "automatic_judgement_not_gold": judgement,
                "human_question": question,
                "human_decision": "",
                "human_selected_flow_ids": "",
                "reviewer": "",
                "reviewed_at": "",
                "review_notes": "",
            }
        )
    queue_columns = [
        "instance", "relation_id", "technique", "observability_category", "doubt", "selected_rule",
        "selected_hit_count", "anomaly_candidate_hits", "relation_raw", "system_label_raw", "candidate_flow",
        "time_delta_ms", "direction", "relation_ips_ports", "neighbor_flows", "automatic_judgement_not_gold",
        "human_question", "human_decision", "human_selected_flow_ids", "reviewer", "reviewed_at", "review_notes",
    ]
    write_csv(report / "04_casinolimit_manual_review_queue.csv", queue_rows, queue_columns)

    technique_rows: list[dict[str, Any]] = []
    all_techniques = sorted(all_support)
    for technique in all_techniques:
        mapped = map_attack_id(technique, stix)
        parent = mapped.get("parent_id_v19_1") or technique
        name = mapped.get("parent_name_v19_1") or mapped.get("technique_name_v19_1") or ""
        category, _ = OBSERVABILITY.get(parent, ("D", "Flow schema cannot establish the host/content action."))
        relation_instances_n = len(relation_support[technique])
        reliable_joined_n = len(reliable_joined_instances[technique])
        joined_rel_n = len(joined_relations[technique])
        per_activity = [len(ids) for ids in flow_ids_by_instance[technique].values()]
        reliable_relation_instances = {
            row["instance"] for row in result_rows
            if row["technique"] == technique and not row["doubt"]
        }
        denominator = len(reliable_relation_instances)
        coverage = reliable_joined_n / denominator if denominator else 0.0
        if reliable_joined_n >= 15 and coverage >= 0.8:
            quality = "high_auto_pending_manual"
        elif reliable_joined_n >= 5 and coverage >= 0.5:
            quality = "medium_auto_pending_manual"
        elif joined_rel_n:
            quality = "low_or_sparse"
        else:
            quality = "unjoined"
        all_doubt = raw_records[technique] > 0 and doubt_records[technique] == raw_records[technique]
        label_confidence = "all_doubt" if all_doubt else ("mixed" if doubt_records[technique] else "non_doubt")
        known = bool(
            category in {"B", "C"}
            and not all_doubt
            and reliable_joined_n >= 15
            and coverage >= 0.8
            and mapped["mapping_status"] == "EXACT_ACTIVE"
        )
        heldout = bool(
            category in {"B", "C"}
            and not known
            and not all_doubt
            and reliable_joined_n >= 10
            and coverage >= 0.7
            and mapped["mapping_status"] == "EXACT_ACTIVE"
        )
        fewshot = bool((known or heldout) and reliable_joined_n >= 20)
        reasons = []
        if mapped["mapping_status"] != "EXACT_ACTIVE":
            reasons.append(mapped["mapping_status"])
        if category == "D":
            reasons.append("Flow evidence insufficient")
        if all_doubt:
            reasons.append("all labels doubt")
        if reliable_joined_n < 10:
            reasons.append("<10 reliable joined instances")
        if coverage < 0.7 and denominator:
            reasons.append("low automatic join coverage")
        technique_rows.append(
            {
                "parent_technique": parent,
                "name": name,
                "raw_instance_support": len(all_support[technique]),
                "reliable_instance_support": len(reliable_support[technique]),
                "relation_instance_support": relation_instances_n,
                "reliable_joined_instance_support": reliable_joined_n,
                "independent_participant_support": "unavailable_in_public_metadata",
                "joined_relation_count": joined_rel_n,
                "joined_flow_count": len(flow_ids[technique]),
                "median_joined_flows_per_activity": statistics.median(per_activity) if per_activity else 0,
                "observability_category": category,
                "label_confidence": label_confidence,
                "join_quality": quality,
                "single_flow_feasible": "partial" if category == "C" and reliable_joined_n else "no",
                "context_feasible": bool(category in {"B", "C"} and reliable_joined_n >= 5),
                "episode_feasible": "pending_manual_and_episode_gate" if reliable_joined_n >= 5 else "no",
                "known_train_candidate": known,
                "heldout_candidate": heldout,
                "fewshot_candidate": fewshot,
                "attribution_only": bool(category == "D" or (not known and not heldout)),
                "exclusion_reason": "; ".join(reasons),
            }
        )
    technique_columns = [
        "parent_technique", "name", "raw_instance_support", "reliable_instance_support",
        "relation_instance_support", "reliable_joined_instance_support", "independent_participant_support",
        "joined_relation_count", "joined_flow_count", "median_joined_flows_per_activity",
        "observability_category", "label_confidence", "join_quality", "single_flow_feasible",
        "context_feasible", "episode_feasible", "known_train_candidate", "heldout_candidate",
        "fewshot_candidate", "attribution_only", "exclusion_reason",
    ]
    write_csv(report / "06_casinolimit_final_technique_matrix.csv", technique_rows, technique_columns)

    def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
        selected = [int(row["selected_hit_count"]) for row in rows]
        total = len(rows)
        return {
            "rows": total,
            "coverage": sum(value > 0 for value in selected) / total if total else 0,
            "zero_hit_rate": sum(value == 0 for value in selected) / total if total else 0,
            "unique_hit_rate": sum(value == 1 for value in selected) / total if total else 0,
            "ambiguous_hit_rate": sum(value > 1 for value in selected) / total if total else 0,
            "median_candidate_count": statistics.median(selected) if selected else 0,
            "p95_candidate_count": percentile(selected, 95),
        }

    non_doubt = [row for row in result_rows if row["technique"] and not row["doubt"]]
    labelled = [row for row in result_rows if row["technique"]]
    by_rule = {rule: aggregate([row for row in labelled if row["selected_rule"] == rule]) for rule in sorted({row["selected_rule"] for row in labelled})}
    by_technique = {tech: aggregate([row for row in labelled if row["technique"] == tech]) for tech in sorted({row["technique"] for row in labelled})}
    by_instance = {inst: aggregate([row for row in labelled if row["instance"] == inst]) for inst in sorted({row["instance"] for row in labelled})}
    by_observability = {
        category: aggregate([row for row in labelled if OBSERVABILITY.get(row["technique"], ("D", ""))[0] == category])
        for category in ["A", "B", "C", "D"]
    }
    return {
        "system_label_instances": len(system_paths),
        "flow_members": len(member_map),
        "relation_instances": len(relation_paths),
        "system_label_records": sum(raw_records.values()),
        "distinct_raw_techniques": len(all_techniques),
        "relation_records": len(relation_base),
        "expanded_relation_label_rows": len(labelled),
        "unlinked_relation_records": sum(not row["technique"] for row in result_rows),
        "duplicate_flow_member_keys": duplicate_member_keys,
        "flow_members_without_system_label": sorted(set(member_map) - set(label_instances)),
        "system_labels_without_flow_member": sorted(set(label_instances) - set(member_map)),
        "parse_stats": parse_stats,
        "join_quality": {
            "all_labelled": aggregate(labelled),
            "non_doubt": aggregate(non_doubt),
            "by_rule": by_rule,
            "by_technique": by_technique,
            "by_instance": by_instance,
            "by_observability": by_observability,
            "zero_reasons": dict(Counter(row["zero_hit_reason"] or "matched" for row in labelled)),
        },
        "manual_queue": {
            "rows": len(queue_rows),
            "instances": len({row["instance"] for row in queue_rows}),
            "techniques": len({row["technique"] for row in queue_rows}),
            "doubt_rows": sum(bool(row["doubt"]) for row in queue_rows),
            "status": "AI_RECOMMENDATIONS_ONLY_NOT_HUMAN_GOLD",
        },
        "technique_rows": technique_rows,
    }


def parse_metrics(path: Path, dataset: str) -> list[dict[str, Any]]:
    frame = pd.read_csv(path, dtype=str).fillna("0")
    rows = []
    for _, row in frame.iterrows():
        label = str(row["label_technique"])
        if not re.fullmatch(r"T\d{4}(?:\.\d{3})?", label):
            continue
        for week in frame.columns[1:]:
            try:
                count = int(float(row[week]))
            except ValueError:
                count = 0
            if count:
                rows.append({"dataset": dataset, "week": week, "technique": label, "flow_count": count})
    return rows


def uwf_audit(cache: Path, report: Path) -> dict[str, Any]:
    downloads = cache / "downloads"
    cached_files = sorted(downloads.glob("uwf_*.parquet"))
    activity_rows: list[dict[str, Any]] = []
    represented: set[tuple[str, str, str]] = set()

    file_meta = {
        "uwf_data24_2024-10-27.parquet": ("UWF-ZeekData24", "2024-10-27 - 2024-11-03"),
        "uwf_data24_2024-11-03.parquet": ("UWF-ZeekData24", "2024-11-03 - 2024-11-10"),
        "uwf_fall24_2_2024-10-27.parquet": ("UWF-ZeekDataFall24-2", "2024-10-27 - 2024-11-03"),
        "uwf_fall24_2_2024-11-03.parquet": ("UWF-ZeekDataFall24-2", "2024-11-03 - 2024-11-10"),
        "uwf_sum25_1_2025-06-08.parquet": ("UWF-ZeekDataSum25-1", "2025-06-08 - 2025-06-15"),
        "uwf_sum25_2_2025-06-08.parquet": ("UWF-ZeekDataSum25-2", "2025-06-08 - 2025-06-15"),
    }
    for path in cached_files:
        if path.name not in file_meta:
            continue
        dataset, week = file_meta[path.name]
        frame = pd.read_parquet(
            path,
            columns=["ts", "src_ip_zeek", "dest_ip_zeek", "label_technique"],
        )
        frame = frame[frame["label_technique"].astype(str).str.match(r"T\d{4}(?:\.\d{3})?$")].copy()
        for technique, group in frame.groupby("label_technique"):
            group = group.sort_values("ts", kind="stable").copy()
            # A 60 s gap + source endpoint defines only a diagnostic cluster.
            # Public mission IDs are absent, so these clusters are never shots.
            group["new_cluster"] = group.groupby("src_ip_zeek")["ts"].diff().fillna(np.inf).gt(60)
            group["cluster"] = group.groupby("src_ip_zeek")["new_cluster"].cumsum().astype(int)
            for (source, cluster), segment in group.groupby(["src_ip_zeek", "cluster"], sort=True):
                activity_id = f"derived60:{path.stem}:{technique}:{source}:{cluster}"
                activity_rows.append(
                    {
                        "dataset_version": dataset,
                        "week": week,
                        "activity_id": activity_id,
                        "activity_id_quality": "heuristic_60s_source_cluster_not_mission_ground_truth",
                        "parent_technique": technique,
                        "flow_count": len(segment),
                        "start_time": datetime.fromtimestamp(float(segment["ts"].min()), timezone.utc).isoformat(),
                        "end_time": datetime.fromtimestamp(float(segment["ts"].max()), timezone.utc).isoformat(),
                        "source_count": segment["src_ip_zeek"].nunique(),
                        "destination_count": segment["dest_ip_zeek"].nunique(),
                        "mission_source": "public_processed_parquet; original mission logs described but not published in download tree",
                        "anchor_feasible": "candidate_only",
                        "episode_feasible": "no_confirmed_activity_boundary",
                        "shot_eligible": False,
                        "split_group": f"{dataset}|{week}",
                    }
                )
            represented.add((dataset, week, str(technique)))

    metric_rows = []
    for filename, dataset in [
        ("uwf_data24_technique_metrics.csv", "UWF-ZeekData24"),
        ("uwf_sum25_1_technique_metrics.csv", "UWF-ZeekDataSum25-1"),
        ("uwf_sum25_2_technique_metrics.csv", "UWF-ZeekDataSum25-2"),
    ]:
        metric_rows.extend(parse_metrics(cache / "metadata" / filename, dataset))
    for row in metric_rows:
        key = (row["dataset"], row["week"], row["technique"])
        if key in represented:
            continue
        activity_rows.append(
            {
                "dataset_version": row["dataset"],
                "week": row["week"],
                "activity_id": "UNAVAILABLE_FROM_PUBLIC_AGGREGATE",
                "activity_id_quality": "weekly_aggregate_only",
                "parent_technique": row["technique"],
                "flow_count": row["flow_count"],
                "start_time": "",
                "end_time": "",
                "source_count": "",
                "destination_count": "",
                "mission_source": "official_weekly_technique_metrics_only",
                "anchor_feasible": "no",
                "episode_feasible": "no",
                "shot_eligible": False,
                "split_group": f"{row['dataset']}|{row['week']}",
            }
        )

    columns = [
        "dataset_version", "week", "activity_id", "activity_id_quality", "parent_technique", "flow_count",
        "start_time", "end_time", "source_count", "destination_count", "mission_source", "anchor_feasible",
        "episode_feasible", "shot_eligible", "split_group",
    ]
    write_csv(report / "09_uwf_activity_technique_matrix.csv", activity_rows, columns)

    techniques = sorted({row["parent_technique"] for row in activity_rows})
    conservative_groups = {
        technique: len({row["split_group"] for row in activity_rows if row["parent_technique"] == technique})
        for technique in techniques
    }
    derived_clusters = Counter(
        row["parent_technique"] for row in activity_rows
        if row["activity_id_quality"].startswith("heuristic")
    )
    post_june_15 = [
        row for row in metric_rows
        if row["dataset"] == "UWF-ZeekDataSum25-1" and row["week"] >= "2025-06-15"
    ]
    return {
        "public_mission_logs_found": False,
        "paper_mission_log_count": 29550,
        "paper_mission_design": "technique, source/destination, ports, UTC start/end; joined with one-minute slop",
        "public_download_tree": "csv_and_parquet_only",
        "fine_grained_activity_status": "HEURISTIC_ONLY_NOT_SHOT_ELIGIBLE",
        "cached_parquet_files": [path.name for path in cached_files],
        "activity_rows": len(activity_rows),
        "derived_cluster_counts": dict(derived_clusters),
        "conservative_week_group_counts": conservative_groups,
        "post_2025_06_15_sum25_1": post_june_15,
        "shot_eligible_rows": sum(bool(row["shot_eligible"]) for row in activity_rows),
    }


def cross_dataset_matrix(casino: dict[str, Any], uwf: dict[str, Any], report: Path) -> list[dict[str, Any]]:
    casino_rows = {row["parent_technique"]: row for row in casino["technique_rows"]}
    uwf_rows = pd.read_csv(report / "09_uwf_activity_technique_matrix.csv", encoding="utf-8-sig")
    uwf_techniques = set(uwf_rows["parent_technique"].dropna().astype(str))
    techniques = sorted(set(casino_rows) | uwf_techniques)
    rows = []
    for technique in techniques:
        c = casino_rows.get(technique, {})
        u = uwf_rows[uwf_rows["parent_technique"].astype(str) == technique]
        conservative_groups = int(u["split_group"].nunique()) if len(u) else 0
        behavior_comparable = technique in {"T1018", "T1046", "T1595"}
        schema_compatible = behavior_comparable
        reliable_casino = int(c.get("reliable_joined_instance_support", 0) or 0)
        reliable_uwf = 0  # no published mission/activity IDs; derived clusters are not gold
        cross_feasible = False
        reason = []
        if not c:
            reason.append("absent from CasinoLimit labels")
        if technique not in uwf_techniques:
            reason.append("absent from audited UWF labels")
        if behavior_comparable:
            reason.append("Flow behavior/schema conceptually comparable")
        if len(u):
            reason.append("UWF lacks public confirmed activity IDs")
        if reliable_casino == 0 and c:
            reason.append("no reliable joined CasinoLimit instance")
        rows.append(
            {
                "technique": technique,
                "CasinoLimit_reliable_activity_count": reliable_casino,
                "UWF_reliable_activity_count": reliable_uwf,
                "UWF_conservative_week_group_count": conservative_groups,
                "CasinoLimit_observability": c.get("observability_category", "absent"),
                "UWF_observability": OBSERVABILITY.get(technique, ("D", ""))[0] if technique in uwf_techniques else "absent",
                "schema_compatible": schema_compatible,
                "behavior_semantically_comparable": behavior_comparable,
                "cross_source_train_test_feasible": cross_feasible,
                "K_core_candidate": False,
                "reason": "; ".join(reason),
            }
        )
    columns = [
        "technique", "CasinoLimit_reliable_activity_count", "UWF_reliable_activity_count",
        "UWF_conservative_week_group_count", "CasinoLimit_observability", "UWF_observability",
        "schema_compatible", "behavior_semantically_comparable", "cross_source_train_test_feasible",
        "K_core_candidate", "reason",
    ]
    write_csv(report / "10_cross_dataset_technique_overlap.csv", rows, columns)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()
    cache = args.cache_root.resolve()
    report = args.report_dir.resolve()
    report.mkdir(parents=True, exist_ok=True)
    stix_path = cache / "metadata" / "enterprise-attack-19.1.json"
    stix = load_stix(stix_path)
    casino = casino_audit(cache, report, stix)
    uwf = uwf_audit(cache, report)
    overlap = cross_dataset_matrix(casino, uwf, report)
    summary = {
        "audit_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "audit_seed": AUDIT_SEED,
        "attack_version": "Enterprise ATT&CK v19.1",
        "attack_stix_sha256": digest(stix_path),
        "casino": casino,
        "uwf": uwf,
        "cross_dataset": {
            "exact_overlap": sorted(
                row["technique"] for row in overlap
                if row["CasinoLimit_observability"] != "absent" and row["UWF_observability"] != "absent"
            ),
            "reliable_cross_source_k_core": sorted(row["technique"] for row in overlap if row["K_core_candidate"]),
        },
        "decision_snapshot": {
            "tier": "NO-GO / data supplementation",
            "formal_training_go": False,
            "K_known": [],
            "K_pseudo_unknown": [],
            "K_final_unknown": [],
            "K_attribution_only": sorted(
                row["parent_technique"] for row in casino["technique_rows"]
                if row["parent_technique"] != "T1562"
            ),
            "shot_protocol": "not released; use 1/3/5 only after independently confirmed activity support",
            "episode_gate_passed": False,
            "fallback_input": "Anchor Flow or fixed past-only aggregate statistics",
            "data_supplementation_required": True,
            "blocking_reasons": [
                "no CasinoLimit parent Technique is automatically approved for supervision before human review",
                "UWF public files do not expose confirmed mission/activity IDs",
                "no reliable cross-source K_core is established",
                "no independent final-held-out class and shot/query protocol can be frozen",
            ],
        },
        "formal_training_started": False,
        "model_weights_downloaded": False,
        "pcap_downloaded": False,
    }
    write_json(report / "audit_summary.json", summary)
    print(json.dumps({"status": "ok", "report": str(report)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
