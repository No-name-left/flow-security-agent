#!/usr/bin/env python3
"""Reproduce the UWF main-dataset validation audit (CPU only).

The script consumes the UWF Parquet files already stored in the shared
``dataset_audit_cache``.  It never downloads data, starts a GPU workload, or
trains a language model.  Outputs are descriptive evidence tables and small
CPU probes; the research decision remains explicit in the accompanying report.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


AUDIT_SEED = 20260804
VERSION_NAMES = {
    "data22": "UWF-ZeekData22",
    "data24": "UWF-ZeekData24",
    "fall22": "UWF-ZeekDataFall22",
    "fall24_2": "UWF-ZeekDataFall24-2",
    "sum25_1": "UWF-ZeekDataSum25-1",
    "sum25_2": "UWF-ZeekDataSum25-2",
}
FILE_RE = re.compile(
    r"^uwf_(data22|data24|fall22|fall24_2|sum25_1|sum25_2)_(\d{4}-\d{2}-\d{2})\.parquet$"
)
MODEL_FEATURES = [
    "duration",
    "missed_bytes",
    "orig_bytes",
    "orig_ip_bytes",
    "orig_pkts",
    "resp_bytes",
    "resp_ip_bytes",
    "resp_pkts",
    "src_port_zeek",
    "dest_port_zeek",
    "conn_state",
    "proto",
    "service",
    "history",
    "local_orig",
    "local_resp",
]
PORT_FEATURES = {"src_port_zeek", "dest_port_zeek"}

# Conservative Flow-only observability assessment.  A/B candidates are the
# only ones eligible for the recommended core set; C/D labels remain useful for
# limitations, rejection, and auxiliary analysis.
OBSERVABILITY: dict[str, tuple[str, str]] = {
    "T1016": ("D", "System network configuration is host state, not established by conn Flow."),
    "T1018": ("B", "Remote-host fan-out is supported by deterministic multi-Flow context."),
    "T1046": ("B", "Service/port fan-out is observable across related Flows."),
    "T1048": ("C", "Alternative-protocol transfer is visible, but exfiltration intent/content is not."),
    "T1059": ("D", "Command execution is not observable from conn Flow."),
    "T1071": ("C", "Application-protocol traffic is visible; C2 intent is not."),
    "T1078": ("D", "Valid-account use requires authentication or host evidence."),
    "T1110": ("B", "Repeated authentication-like connections can support brute-force evidence."),
    "T1112": ("D", "Registry modification is host-only evidence."),
    "T1133": ("C", "Remote-service access is visible; legitimacy and authentication are not."),
    "T1136": ("D", "Account creation is not established by conn Flow."),
    "T1190": ("C", "Public-service interaction is visible; successful exploitation is not."),
    "T1203": ("D", "Client execution exploitation requires endpoint/content evidence."),
    "T1204": ("D", "User execution is not observable from conn Flow."),
    "T1210": ("C", "Remote-service interaction is visible; exploitation success is not."),
    "T1505": ("D", "Server software component persistence needs host/application evidence."),
    "T1546": ("D", "Event-triggered execution requires host evidence."),
    "T1547": ("D", "Boot/logon autostart requires host evidence."),
    "T1548": ("D", "Privilege escalation mechanism is not established by conn Flow."),
    "T1557": ("B", "Adversary-in-the-middle can have network-level evidence, but needs context."),
    "T1566": ("C", "Delivery traffic may be visible; phishing semantics/content are absent."),
    "T1571": ("C", "Non-standard port/protocol use is visible; malicious intent is not."),
    "T1587": ("D", "Capability development is pre-compromise activity outside conn-Flow proof."),
    "T1589": ("D", "Identity-information gathering is not established by conn Flow."),
    "T1590": ("C", "Network-information gathering may leave scan-like evidence but intent is weak."),
    "T1592": ("D", "Host-information gathering requires content/host semantics."),
    "T1595": ("B", "Active scanning fan-out is observable in causal Flow context."),
}


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean_label(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.casefold() in {"", "none", "nan", "null", "<na>"} else text


def dominant(counter: Counter[str]) -> tuple[str, int, float]:
    total = sum(counter.values())
    if not counter or total == 0:
        return "", 0, 0.0
    item, count = counter.most_common(1)[0]
    return item, int(count), float(count / total)


def split_version_and_week(path: Path) -> tuple[str, str]:
    match = FILE_RE.match(path.name)
    if not match:
        raise ValueError(f"unexpected UWF filename: {path.name}")
    return VERSION_NAMES[match.group(1)], match.group(2)


def load_attack_mapping(path: Path) -> dict[str, dict[str, Any]]:
    bundle = json.loads(path.read_text(encoding="utf-8"))
    patterns: dict[str, dict[str, Any]] = {}
    stix_to_external: dict[str, str] = {}
    relationships = []
    for obj in bundle.get("objects", []):
        if obj.get("type") == "attack-pattern":
            external_id = ""
            for ref in obj.get("external_references", []):
                if ref.get("source_name") == "mitre-attack" and ref.get("external_id"):
                    external_id = str(ref["external_id"])
                    break
            if not external_id:
                continue
            stix_to_external[str(obj["id"])] = external_id
            patterns[external_id] = {
                "name": obj.get("name", ""),
                "stix_id": obj.get("id", ""),
                "is_subtechnique": bool(obj.get("x_mitre_is_subtechnique", False)),
                "revoked": bool(obj.get("revoked", False)),
                "deprecated": bool(obj.get("x_mitre_deprecated", False)),
                "parent": "",
            }
        elif obj.get("type") == "relationship" and obj.get("relationship_type") == "subtechnique-of":
            relationships.append(obj)
    for rel in relationships:
        child = stix_to_external.get(str(rel.get("source_ref", "")), "")
        parent = stix_to_external.get(str(rel.get("target_ref", "")), "")
        if child in patterns:
            patterns[child]["parent"] = parent
    return patterns


@dataclass
class TechniqueStats:
    flow_count: int = 0
    versions: set[str] = field(default_factory=set)
    weeks: set[str] = field(default_factory=set)
    dates: set[str] = field(default_factory=set)
    files: set[str] = field(default_factory=set)
    week_flows: Counter[str] = field(default_factory=Counter)
    file_flows: Counter[str] = field(default_factory=Counter)
    sources: Counter[str] = field(default_factory=Counter)
    destinations: Counter[str] = field(default_factory=Counter)
    protocols: Counter[str] = field(default_factory=Counter)
    ports: Counter[str] = field(default_factory=Counter)
    source_date_groups: set[str] = field(default_factory=set)
    first_seen: str = ""
    last_seen: str = ""
    sampled_profiles: list[int] = field(default_factory=list)

    def update_time(self, values: pd.Series) -> None:
        valid = pd.to_datetime(values, errors="coerce", utc=True).dropna()
        if valid.empty:
            return
        first = valid.min().isoformat()
        last = valid.max().isoformat()
        if not self.first_seen or first < self.first_seen:
            self.first_seen = first
        if not self.last_seen or last > self.last_seen:
            self.last_seen = last


def safe_value_counts(series: pd.Series) -> Counter[str]:
    values = series.astype("string").fillna("<MISSING>").str.strip().replace("", "<MISSING>")
    return Counter({str(k): int(v) for k, v in values.value_counts(dropna=False).items()})


def profile_hashes(frame: pd.DataFrame) -> np.ndarray:
    columns = [
        c
        for c in [
            "src_ip_zeek",
            "dest_ip_zeek",
            "src_port_zeek",
            "dest_port_zeek",
            "proto",
            "duration",
            "orig_bytes",
            "resp_bytes",
            "orig_pkts",
            "resp_pkts",
        ]
        if c in frame.columns
    ]
    if not columns:
        return np.array([], dtype=np.uint64)
    return pd.util.hash_pandas_object(frame[columns].astype("string"), index=False).to_numpy(dtype=np.uint64)


def scan_files(files: list[Path], attack: dict[str, dict[str, Any]]) -> dict[str, Any]:
    inventory: list[dict[str, Any]] = []
    per_version_label: dict[tuple[str, str], TechniqueStats] = defaultdict(TechniqueStats)
    aggregate: dict[str, TechniqueStats] = defaultdict(TechniqueStats)
    tactic_counts: Counter[tuple[str, str]] = Counter()
    binary_counts: Counter[tuple[str, str]] = Counter()
    duplicate_rows: Counter[str] = Counter()
    rng = np.random.default_rng(AUDIT_SEED)

    for path in files:
        version, week = split_version_and_week(path)
        parquet = pq.ParquetFile(path)
        columns = parquet.schema_arrow.names
        schema_text = "|".join(f"{field.name}:{field.type}" for field in parquet.schema_arrow)
        inventory.append(
            {
                "dataset_version": version,
                "week_start": week,
                "file": path.name,
                "bytes": path.stat().st_size,
                "rows": parquet.metadata.num_rows,
                "column_count": len(columns),
                "schema_sha256": hashlib.sha256(schema_text.encode("utf-8")).hexdigest(),
                "has_binary_label": "label_binary" in columns,
                "has_tactic_label": "label_tactic" in columns,
                "has_technique_label": "label_technique" in columns,
                "has_subtechnique_label": False,
                "has_vlan": "vlan" in columns,
                "sha256": sha256(path),
            }
        )
        requested = [
            c
            for c in [
                "label_binary",
                "label_tactic",
                "label_technique",
                "datetime",
                "src_ip_zeek",
                "dest_ip_zeek",
                "dest_port_zeek",
                "proto",
                "src_port_zeek",
                "duration",
                "orig_bytes",
                "resp_bytes",
                "orig_pkts",
                "resp_pkts",
            ]
            if c in columns
        ]
        for batch in parquet.iter_batches(batch_size=250_000, columns=requested):
            frame = batch.to_pandas()
            tactics = frame.get("label_tactic", pd.Series("", index=frame.index)).map(clean_label)
            for key, count in tactics.value_counts(dropna=False).items():
                tactic_counts[(version, key or "none")] += int(count)
            if "label_binary" in frame:
                binary = frame["label_binary"].astype("string").fillna("<MISSING>")
                for key, count in binary.value_counts(dropna=False).items():
                    binary_counts[(version, str(key))] += int(count)
            else:
                inferred = np.where(tactics.eq(""), "False", "True")
                for key, count in pd.Series(inferred).value_counts().items():
                    binary_counts[(version, str(key))] += int(count)

            if "label_technique" not in frame:
                continue
            labels = frame["label_technique"].map(clean_label)
            duplicate_rows[version] += int(labels.eq("Duplicate").sum())
            valid_mask = labels.str.match(r"^T\d{4}(?:\.\d{3})?$")
            if not valid_mask.any():
                continue
            valid = frame.loc[valid_mask].copy()
            valid["_label"] = labels.loc[valid_mask].values
            valid["_dt"] = pd.to_datetime(valid.get("datetime"), errors="coerce", utc=True)
            valid["_date"] = valid["_dt"].dt.strftime("%Y-%m-%d").fillna("<MISSING>")
            for label, group in valid.groupby("_label", sort=False):
                mapping = attack.get(label, {})
                parent = mapping.get("parent") if mapping.get("is_subtechnique") else label
                parent = parent or label
                for stats in (per_version_label[(version, label)], aggregate[parent]):
                    stats.flow_count += len(group)
                    stats.versions.add(version)
                    stats.weeks.add(f"{version}|{week}")
                    stats.files.add(path.name)
                    stats.week_flows[f"{version}|{week}"] += len(group)
                    stats.file_flows[path.name] += len(group)
                    stats.dates.update(f"{version}|{d}" for d in group["_date"].unique())
                    stats.update_time(group["_dt"])
                    if "src_ip_zeek" in group:
                        stats.sources.update(safe_value_counts(group["src_ip_zeek"]))
                    if "dest_ip_zeek" in group:
                        stats.destinations.update(safe_value_counts(group["dest_ip_zeek"]))
                    if "proto" in group:
                        stats.protocols.update(safe_value_counts(group["proto"]))
                    if "dest_port_zeek" in group:
                        stats.ports.update(safe_value_counts(group["dest_port_zeek"]))
                    if "src_ip_zeek" in group:
                        pairs = (
                            version
                            + "|"
                            + group["_date"].astype(str)
                            + "|"
                            + group["src_ip_zeek"].astype("string").fillna("<MISSING>")
                        )
                        stats.source_date_groups.update(pairs.unique().tolist())
                hashes = profile_hashes(group)
                if len(hashes):
                    target = aggregate[parent].sampled_profiles
                    remaining = max(0, 200_000 - len(target))
                    if remaining:
                        if len(hashes) > remaining:
                            hashes = rng.choice(hashes, size=remaining, replace=False)
                        target.extend(int(x) for x in hashes)

    parent_rows: list[dict[str, Any]] = []
    for (version, original), stats in sorted(per_version_label.items()):
        mapping = attack.get(original, {})
        parent = mapping.get("parent") if mapping.get("is_subtechnique") else original
        parent = parent or original
        source, _, source_share = dominant(stats.sources)
        destination, _, destination_share = dominant(stats.destinations)
        protocol, _, protocol_share = dominant(stats.protocols)
        port, _, port_share = dominant(stats.ports)
        parent_rows.append(
            {
                "dataset_version": version,
                "original_label": original,
                "parent_technique": parent,
                "technique_name": attack.get(parent, {}).get("name", ""),
                "label_type": "subtechnique" if mapping.get("is_subtechnique") else "parent_technique",
                "flow_count": stats.flow_count,
                "clean_flow_count": stats.flow_count,
                "version_count": len(stats.versions),
                "week_count": len(stats.weeks),
                "date_count": len(stats.dates),
                "file_count": len(stats.files),
                "source_host_count": len(stats.sources),
                "destination_host_count": len(stats.destinations),
                "top_source": source,
                "top_source_share": round(source_share, 6),
                "top_destination": destination,
                "top_destination_share": round(destination_share, 6),
                "top_protocol": protocol,
                "top_protocol_share": round(protocol_share, 6),
                "top_destination_port": port,
                "top_destination_port_share": round(port_share, 6),
                "first_seen": stats.first_seen,
                "last_seen": stats.last_seen,
                "benign_or_malicious": "Malicious",
                "mapping_status": "EXACT_ACTIVE"
                if mapping and not mapping.get("revoked") and not mapping.get("deprecated")
                else ("EXACT_HISTORICAL" if mapping else "UNMAPPED"),
                "mapping_basis": "MITRE Enterprise ATT&CK v19.1 external_id and subtechnique-of relationship",
            }
        )

    aggregate_rows: list[dict[str, Any]] = []
    for parent, stats in sorted(aggregate.items()):
        top_version_counter = Counter()
        for (version, original), local in per_version_label.items():
            mapping = attack.get(original, {})
            mapped_parent = mapping.get("parent") if mapping.get("is_subtechnique") else original
            if (mapped_parent or original) == parent:
                top_version_counter[version] += local.flow_count
        top_version, _, version_share = dominant(top_version_counter)
        top_file, _, top_file_share = dominant(stats.file_flows)
        source, _, source_share = dominant(stats.sources)
        destination, _, destination_share = dominant(stats.destinations)
        protocol, _, protocol_share = dominant(stats.protocols)
        port, _, port_share = dominant(stats.ports)
        sample_n = len(stats.sampled_profiles)
        unique_profiles = len(set(stats.sampled_profiles)) if sample_n else 0
        aggregate_rows.append(
            {
                "dataset_version": "ALL_UWF_TECHNIQUE_LABELED",
                "original_label": parent,
                "parent_technique": parent,
                "technique_name": attack.get(parent, {}).get("name", ""),
                "label_type": "parent_aggregate",
                "flow_count": stats.flow_count,
                "clean_flow_count": stats.flow_count,
                "version_count": len(stats.versions),
                "week_count": len(stats.weeks),
                "date_count": len(stats.dates),
                "file_count": len(stats.files),
                "source_host_count": len(stats.sources),
                "destination_host_count": len(stats.destinations),
                "top_source": source,
                "top_source_share": round(source_share, 6),
                "top_destination": destination,
                "top_destination_share": round(destination_share, 6),
                "top_protocol": protocol,
                "top_protocol_share": round(protocol_share, 6),
                "top_destination_port": port,
                "top_destination_port_share": round(port_share, 6),
                "first_seen": stats.first_seen,
                "last_seen": stats.last_seen,
                "benign_or_malicious": "Malicious",
                "mapping_status": "EXACT_ACTIVE"
                if attack.get(parent) and not attack[parent].get("revoked") and not attack[parent].get("deprecated")
                else ("EXACT_HISTORICAL" if attack.get(parent) else "UNMAPPED"),
                "mapping_basis": "MITRE Enterprise ATT&CK v19.1 external_id and subtechnique-of relationship",
                "top_version": top_version,
                "top_version_share": round(version_share, 6),
                "top_file": top_file,
                "top_file_share": round(top_file_share, 6),
                "profile_sample_count": sample_n,
                "profile_sample_duplicate_share": round(1 - unique_profiles / sample_n, 6) if sample_n else 0.0,
            }
        )

    return {
        "inventory": inventory,
        "parent_rows": parent_rows + aggregate_rows,
        "aggregate_rows": aggregate_rows,
        "aggregate": aggregate,
        "per_version_label": per_version_label,
        "tactic_counts": tactic_counts,
        "binary_counts": binary_counts,
        "duplicate_rows": duplicate_rows,
    }


def build_group_rows(scan: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in scan["aggregate_rows"]:
        technique = row["parent_technique"]
        stats: TechniqueStats = scan["aggregate"][technique]
        rows.append(
            {
                "parent_technique": technique,
                "technique_name": row["technique_name"],
                "flow_count": stats.flow_count,
                "official_group_available": False,
                "official_group_count": 0,
                "file_derived_group_count": len(stats.files),
                "week_group_count": len(stats.weeks),
                "calendar_date_group_count": len(stats.dates),
                "source_date_proxy_group_count": len(stats.source_date_groups),
                "recommended_split_group": "version+week/file",
                "fewshot_proxy_group": "version+week; date+source only as sensitivity",
                "group_status": "PROXY_ONLY_NO_PUBLIC_ACTIVITY_ID",
                "caveat": "Week/file groups are reproducible but are not proven independent missions; heuristic groups cannot be called attacks.",
            }
        )
    return rows


def build_observability_rows(scan: dict[str, Any], attack: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for aggregate_row in scan["aggregate_rows"]:
        technique = aggregate_row["parent_technique"]
        level, reason = OBSERVABILITY.get(technique, ("D", "Not yet supported by a Flow-only evidence rationale."))
        stats: TechniqueStats = scan["aggregate"][technique]
        _, _, port_share = dominant(stats.ports)
        reliable = (
            level in {"A", "B"}
            and len(stats.weeks) >= 3
            and stats.flow_count >= 100
            and port_share < 0.95
        )
        rows.append(
            {
                "parent_technique": technique,
                "technique_name": attack.get(technique, {}).get("name", ""),
                "observability_level": level,
                "observability_reason": reason,
                "flow_count": stats.flow_count,
                "version_count": len(stats.versions),
                "week_group_count": len(stats.weeks),
                "date_group_count": len(stats.dates),
                "reliable_known_candidate": reliable,
                "unknown_candidate_priority": "HIGH"
                if reliable
                else ("SECONDARY" if level in {"B", "C"} and len(stats.weeks) >= 2 else "LOW"),
                "input_requirement": "single Flow + deterministic past-only context" if level == "B" else "single Flow",
            }
        )
    return rows


def build_fewshot_rows(scan: dict[str, Any], observability_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    obs = {row["parent_technique"]: row for row in observability_rows}
    rows = []
    for aggregate_row in scan["aggregate_rows"]:
        technique = aggregate_row["parent_technique"]
        stats: TechniqueStats = scan["aggregate"][technique]
        week_counts: Counter[str] = stats.week_flows.copy()
        sorted_groups = sorted(week_counts.items(), key=lambda item: (item[0].rsplit("|", 1)[-1], item[0]))
        eligible_query = [item for item in sorted_groups if item[1] >= 10]
        query_groups = eligible_query[-1:] if len(sorted_groups) >= 2 and eligible_query else []
        query_keys = {group for group, _ in query_groups}
        support_groups = [item for item in sorted_groups if item[0] not in query_keys] if query_groups else []
        support_flows = sum(count for _, count in support_groups)
        query_flows = sum(count for _, count in query_groups)

        def status(shots: int) -> str:
            if not support_groups or not query_groups:
                return "NO-GO"
            if support_flows >= shots and query_flows >= max(10, shots):
                return "GO" if obs[technique]["reliable_known_candidate"] else "PARTIAL"
            return "NO-GO"

        rows.append(
            {
                "parent_technique": technique,
                "technique_name": aggregate_row["technique_name"],
                "observability_level": obs[technique]["observability_level"],
                "support_group_definition": "version+week/file",
                "total_proxy_group_count": len(sorted_groups),
                "support_group_count": len(support_groups),
                "query_group_count": len(query_groups),
                "eligible_support_flow_count": support_flows,
                "eligible_query_flow_count": query_flows,
                "one_shot_status": status(1),
                "five_shot_status": status(5),
                "ten_shot_status": status(10),
                "limitation": "Shot is a labeled Flow/context, not an independent mission; support/query use non-overlapping week/file proxies.",
            }
        )
    return rows


def sample_frame(
    paths: Iterable[Path],
    target_labels: set[str] | None,
    per_label_file: int,
    binary: bool = False,
) -> pd.DataFrame:
    pieces = []
    for path in paths:
        version, week = split_version_and_week(path)
        parquet = pq.ParquetFile(path)
        columns = parquet.schema_arrow.names
        if binary and "label_tactic" not in columns:
            continue
        if not binary and "label_technique" not in columns:
            continue
        requested = [c for c in MODEL_FEATURES + ["label_binary", "label_tactic", "label_technique", "datetime", "src_ip_zeek", "dest_ip_zeek"] if c in columns]
        frame = pq.read_table(path, columns=requested).to_pandas()
        if binary:
            if "label_binary" in frame:
                frame = frame.loc[frame["label_binary"].astype("string").ne("Duplicate")].copy()
            labels = frame["label_tactic"].map(lambda value: 0 if clean_label(value) == "" else 1)
            frame["_target"] = labels
        else:
            labels = frame["label_technique"].map(clean_label)
            frame = frame.loc[labels.isin(target_labels or set())].copy()
            frame["_target"] = labels.loc[frame.index]
        frame["_version"] = version
        frame["_week"] = week
        frame["_file"] = path.name
        frame["_hour"] = pd.to_datetime(frame.get("datetime"), errors="coerce", utc=True).dt.hour.fillna(-1)
        for label, group in frame.groupby("_target", sort=False):
            n = min(per_label_file, len(group))
            pieces.append(group.sample(n=n, random_state=AUDIT_SEED) if len(group) > n else group)
    return pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()


def metrics_binary(y_true: pd.Series, pred: np.ndarray, prob: np.ndarray) -> dict[str, Any]:
    from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score, roc_auc_score

    return {
        "f1": float(f1_score(y_true, pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_true, prob)) if len(np.unique(y_true)) == 2 else None,
        "pr_auc": float(average_precision_score(y_true, prob)) if len(np.unique(y_true)) == 2 else None,
        "precision": float(precision_score(y_true, pred, zero_division=0)),
        "recall": float(recall_score(y_true, pred, zero_division=0)),
    }


def metrics_multiclass(y_true: pd.Series, pred: np.ndarray, labels: list[str]) -> dict[str, Any]:
    from sklearn.metrics import confusion_matrix, f1_score, recall_score

    return {
        "macro_f1": float(f1_score(y_true, pred, labels=labels, average="macro", zero_division=0)),
        "micro_f1": float(f1_score(y_true, pred, labels=labels, average="micro", zero_division=0)),
        "per_class_recall": {
            label: float(value)
            for label, value in zip(labels, recall_score(y_true, pred, labels=labels, average=None, zero_division=0))
        },
        "confusion_matrix_labels": labels,
        "confusion_matrix": confusion_matrix(y_true, pred, labels=labels).tolist(),
    }


def fit_probe(
    train: pd.DataFrame,
    test: pd.DataFrame,
    feature_columns: list[str],
    model_name: str,
    task: str,
    shuffled: bool = False,
) -> dict[str, Any]:
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    numeric = [c for c in feature_columns if c in train and pd.api.types.is_numeric_dtype(train[c])]
    categorical = [c for c in feature_columns if c in train and c not in numeric]
    preprocessing = ColumnTransformer(
        [
            ("num", Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), numeric),
            (
                "cat",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore", min_frequency=2)),
                    ]
                ),
                categorical,
            ),
        ],
        sparse_threshold=0.3,
    )
    if model_name == "logistic_regression":
        # Single-process execution avoids Windows joblib pipe creation, which
        # can be denied in restricted audit environments.
        model = LogisticRegression(max_iter=600, class_weight="balanced", n_jobs=1, random_state=AUDIT_SEED)
    elif model_name == "lightgbm":
        import lightgbm as lgb

        model = lgb.LGBMClassifier(
            n_estimators=160,
            learning_rate=0.06,
            num_leaves=31,
            max_depth=-1,
            class_weight="balanced",
            random_state=AUDIT_SEED,
            n_jobs=max(1, min(8, os.cpu_count() or 1)),
            verbosity=-1,
        )
    else:
        raise ValueError(model_name)
    pipeline = Pipeline([("preprocess", preprocessing), ("model", model)])
    y_train = train["_target"].copy()
    if shuffled:
        y_train = y_train.sample(frac=1.0, random_state=AUDIT_SEED).to_numpy()
    pipeline.fit(train[feature_columns], y_train)
    pred = pipeline.predict(test[feature_columns])
    result = {
        "model": model_name,
        "task": task,
        "train_rows": len(train),
        "test_rows": len(test),
        "features": feature_columns,
        "label_shuffle": shuffled,
    }
    if task.startswith("binary"):
        prob = pipeline.predict_proba(test[feature_columns])[:, list(pipeline.classes_).index(1)]
        result.update(metrics_binary(test["_target"], pred, prob))
    else:
        labels = sorted(set(train["_target"]) | set(test["_target"]))
        result.update(metrics_multiclass(test["_target"], pred, labels))
    return result


def run_cpu_probes(files: list[Path]) -> dict[str, Any]:
    from sklearn.model_selection import train_test_split

    by_version: dict[str, list[Path]] = defaultdict(list)
    for path in files:
        version, _ = split_version_and_week(path)
        by_version[version].append(path)

    results: list[dict[str, Any]] = []
    stable = [c for c in MODEL_FEATURES]
    no_port = [c for c in stable if c not in PORT_FEATURES]

    # Task 2: Data24 contains the same five parent Technique labels in each of
    # five attack weeks.  This is the cleanest available row-random vs weekly
    # grouped comparison, although its smallest class remains sparse.
    task2_labels = {"T1048", "T1078", "T1110", "T1190", "T1595"}
    data24_attack = [p for p in by_version["UWF-ZeekData24"] if split_version_and_week(p)[1] < "2024-04-01"]
    task2 = sample_frame(data24_attack, task2_labels, per_label_file=5000, binary=False)
    random_train, random_test = train_test_split(
        task2,
        test_size=0.25,
        random_state=AUDIT_SEED,
        stratify=task2["_target"],
    )
    grouped_train = task2.loc[task2["_week"].ne("2024-03-24")].copy()
    grouped_test = task2.loc[task2["_week"].eq("2024-03-24")].copy()
    for model in ("logistic_regression", "lightgbm"):
        results.append(fit_probe(random_train, random_test, stable, model, "technique_random_split"))
        results.append(fit_probe(grouped_train, grouped_test, stable, model, "technique_grouped_week_split"))
        results.append(fit_probe(grouped_train, grouped_test, no_port, model, "technique_grouped_no_port"))
    results.append(fit_probe(grouped_train, grouped_test, stable, "lightgbm", "technique_grouped_label_shuffle", shuffled=True))

    # Task 1: train on Data24 + Fall24-2 and test on the mixed benign/attack
    # Sum25-2 week beginning 2025-05-25.  This is a version/time holdout and is
    # intentionally harsher than a row-random split.
    binary_train_paths = by_version["UWF-ZeekData24"] + by_version["UWF-ZeekDataFall24-2"]
    binary_test_paths = [p for p in by_version["UWF-ZeekDataSum25-2"] if split_version_and_week(p)[1] == "2025-05-25"]
    task1_train = sample_frame(binary_train_paths, None, per_label_file=6000, binary=True)
    task1_test = sample_frame(binary_test_paths, None, per_label_file=20000, binary=True)
    combined = pd.concat([task1_train, task1_test], ignore_index=True)
    bin_random_train, bin_random_test = train_test_split(
        combined,
        test_size=0.25,
        random_state=AUDIT_SEED,
        stratify=combined["_target"],
    )
    for model in ("logistic_regression", "lightgbm"):
        results.append(fit_probe(bin_random_train, bin_random_test, stable, model, "binary_random_split"))
        results.append(fit_probe(task1_train, task1_test, stable, model, "binary_version_time_holdout"))
        results.append(fit_probe(task1_train, task1_test, no_port, model, "binary_version_time_holdout_no_port"))
    results.append(fit_probe(task1_train, task1_test, stable, "lightgbm", "binary_grouped_label_shuffle", shuffled=True))

    # Version-prediction leakage probe.  Absolute version is never a formal
    # model input; high predictability from stable Flow fields still diagnoses
    # collection-domain shortcuts.
    version_frames = []
    for version, paths in by_version.items():
        if version == "UWF-ZeekData22":
            continue
        sampled = sample_frame(paths, None, per_label_file=2500, binary=True)
        if not sampled.empty:
            sampled["_target"] = version
            version_frames.append(sampled)
    version_data = pd.concat(version_frames, ignore_index=True)
    version_train, version_test = train_test_split(
        version_data,
        test_size=0.25,
        random_state=AUDIT_SEED,
        stratify=version_data["_target"],
    )
    results.append(fit_probe(version_train, version_test, stable, "lightgbm", "version_prediction"))
    results.append(fit_probe(version_train, version_test, no_port, "lightgbm", "version_prediction_no_port"))

    return {
        "seed": AUDIT_SEED,
        "lightgbm_version": __import__("lightgbm").__version__,
        "sklearn_version": __import__("sklearn").__version__,
        "task2_probe_labels": sorted(task2_labels),
        "task2_grouped_train_weeks": sorted(grouped_train["_week"].unique().tolist()),
        "task2_grouped_test_weeks": sorted(grouped_test["_week"].unique().tolist()),
        "task1_train_versions": sorted(task1_train["_version"].unique().tolist()),
        "task1_test_versions": sorted(task1_test["_version"].unique().tolist()),
        "results": results,
    }


def overlap_pair(left: Path, right: Path) -> dict[str, Any]:
    columns = ["uid", "community_id", "src_ip_zeek", "src_port_zeek", "dest_ip_zeek", "dest_port_zeek", "proto", "ts"]
    left_schema = pq.ParquetFile(left).schema_arrow.names
    right_schema = pq.ParquetFile(right).schema_arrow.names
    columns = [c for c in columns if c in left_schema and c in right_schema]
    left_rows = pq.ParquetFile(left).metadata.num_rows
    right_rows = pq.ParquetFile(right).metadata.num_rows
    small, large = (left, right) if left_rows <= right_rows else (right, left)
    small_frame = pq.read_table(small, columns=columns).to_pandas()
    result = {
        "left": left.name,
        "right": right.name,
        "left_rows": left_rows,
        "right_rows": right_rows,
    }
    for identifier in [c for c in ["uid", "community_id"] if c in columns]:
        small_values = set(small_frame[identifier].dropna().astype(str))
        intersection: set[str] = set()
        for batch in pq.ParquetFile(large).iter_batches(batch_size=250_000, columns=[identifier]):
            values = set(batch.to_pandas()[identifier].dropna().astype(str))
            intersection.update(values & small_values)
        result[f"{identifier}_intersection"] = len(intersection)
    key_columns = [c for c in ["src_ip_zeek", "src_port_zeek", "dest_ip_zeek", "dest_port_zeek", "proto", "ts"] if c in columns]
    small_hashes = set(pd.util.hash_pandas_object(small_frame[key_columns].astype("string"), index=False).astype("uint64"))
    intersections: set[int] = set()
    for batch in pq.ParquetFile(large).iter_batches(batch_size=250_000, columns=key_columns):
        frame = batch.to_pandas()
        hashes = set(pd.util.hash_pandas_object(frame[key_columns].astype("string"), index=False).astype("uint64"))
        intersections.update(int(x) for x in hashes & small_hashes)
    result["exact_flow_key_intersection"] = len(intersections)
    return result


def run_overlap_audit(files: list[Path]) -> list[dict[str, Any]]:
    indexed = {path.name: path for path in files}
    pairs = []
    for week in ["2021-12-12", "2021-12-19", "2021-12-26", "2022-01-02"]:
        pairs.append((f"uwf_data22_{week}.parquet", f"uwf_fall22_{week}.parquet"))
    for week in ["2024-10-27", "2024-11-03"]:
        pairs.append((f"uwf_data24_{week}.parquet", f"uwf_fall24_2_{week}.parquet"))
    for week in ["2025-05-18", "2025-05-25", "2025-06-01", "2025-06-08"]:
        pairs.append((f"uwf_sum25_1_{week}.parquet", f"uwf_sum25_2_{week}.parquet"))
    return [overlap_pair(indexed[left], indexed[right]) for left, right in pairs]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, default=Path("../dataset_audit_cache"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/dataset_audit/2026-08-uwf-main-validation"),
    )
    parser.add_argument("--skip-probes", action="store_true")
    parser.add_argument("--probes-only", action="store_true")
    args = parser.parse_args()
    cache = args.cache.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    files = sorted((cache / "downloads").glob("uwf_*.parquet"))
    if len(files) != 50:
        raise SystemExit(f"expected 50 UWF weekly Parquet files, found {len(files)}")
    if args.probes_only:
        write_json(output / "cpu_probe_results.json", run_cpu_probes(files))
        print(json.dumps({"status": "ok", "mode": "probes-only", "output": str(output)}, ensure_ascii=False))
        return
    attack_path = cache / "metadata" / "enterprise-attack-19.1.json"
    attack = load_attack_mapping(attack_path)
    scan = scan_files(files, attack)
    group_rows = build_group_rows(scan)
    observability_rows = build_observability_rows(scan, attack)
    fewshot_rows = build_fewshot_rows(scan, observability_rows)
    columns_parent = [
        "dataset_version",
        "original_label",
        "parent_technique",
        "technique_name",
        "label_type",
        "flow_count",
        "clean_flow_count",
        "version_count",
        "week_count",
        "date_count",
        "file_count",
        "source_host_count",
        "destination_host_count",
        "top_source",
        "top_source_share",
        "top_destination",
        "top_destination_share",
        "top_protocol",
        "top_protocol_share",
        "top_destination_port",
        "top_destination_port_share",
        "first_seen",
        "last_seen",
        "benign_or_malicious",
        "mapping_status",
        "mapping_basis",
        "top_version",
        "top_version_share",
        "top_file",
        "top_file_share",
        "profile_sample_count",
        "profile_sample_duplicate_share",
    ]
    write_csv(output / "04_uwf_parent_technique_matrix.csv", scan["parent_rows"], columns_parent)
    sub_rows = [row for row in scan["parent_rows"] if row["label_type"] == "subtechnique"]
    write_csv(
        output / "05_uwf_subtechnique_matrix.csv",
        sub_rows,
        [
            "dataset_version",
            "original_label",
            "parent_technique",
            "technique_name",
            "flow_count",
            "week_count",
            "date_count",
            "file_count",
            "mapping_status",
            "mapping_basis",
        ],
    )
    write_csv(output / "06_uwf_group_matrix.csv", group_rows, list(group_rows[0]))
    write_csv(output / "07_uwf_flow_observability.csv", observability_rows, list(observability_rows[0]))
    write_csv(output / "10_uwf_fewshot_feasibility.csv", fewshot_rows, list(fewshot_rows[0]))
    write_csv(output / "uwf_file_inventory.csv", scan["inventory"], list(scan["inventory"][0]))
    overlap = run_overlap_audit(files)
    write_json(output / "overlap_results.json", overlap)
    evidence = {
        "seed": AUDIT_SEED,
        "file_count": len(files),
        "download_bytes": sum(path.stat().st_size for path in files),
        "inventory": scan["inventory"],
        "binary_counts": {f"{version}|{label}": count for (version, label), count in scan["binary_counts"].items()},
        "tactic_counts": {f"{version}|{label}": count for (version, label), count in scan["tactic_counts"].items()},
        "duplicate_rows": dict(scan["duplicate_rows"]),
        "observed_parent_technique_count": len(scan["aggregate_rows"]),
        "observed_subtechnique_count": len(sub_rows),
        "attack_bundle_sha256": sha256(attack_path),
        "overlap_results": overlap,
    }
    write_json(output / "uwf_validation_evidence.json", evidence)
    if not args.skip_probes:
        write_json(output / "cpu_probe_results.json", run_cpu_probes(files))
    print(json.dumps({"status": "ok", "files": len(files), "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
