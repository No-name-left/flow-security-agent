#!/usr/bin/env python3
"""Reproduce the August 2026 formal dataset-selection statistics.

The script consumes only cached official metadata and small samples.  It does
not download data, train a model, or modify project data.  CSV/JSON artifacts
are written to the requested audit report directory.
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import glob
import hashlib
import ipaddress
import json
import math
import os
import re
import struct
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


AUDIT_SEED = 20260803
PREFERRED_INSTANCE_SUPPORT = 20
MINIMUM_INSTANCE_SUPPORT = 15

# A: directly represented by single-Flow fields; B: requires causal Flow
# aggregation; C: partially observable but not provable from Flow alone; D:
# requires payload/host/cloud/user context absent from the audited Flow schema.
OBSERVABILITY: dict[str, tuple[str, str]] = {
    "T1018": ("B", "Remote-host fan-out can be supported by causal Flow context."),
    "T1046": ("B", "Port/service fan-out is observable only across multiple Flows."),
    "T1110": ("B", "Repeated authentication attempts may be inferred from connection patterns, not success semantics."),
    "T1572": ("B", "Persistent or unusual tunnel-like channels are pattern-level evidence, not payload proof."),
    "T1595": ("B", "Active scan fan-out is observable in causal Flow context."),
    "T1011": ("C", "Alternative-medium exfiltration needs semantics not present in basic Flow fields."),
    "T1021": ("C", "Remote-service use is visible; malicious intent and account context are not."),
    "T1041": ("C", "Outbound transfer is visible; C2/exfiltration intent is not directly observable."),
    "T1048": ("C", "Protocol/volume can support a hypothesis, but exfiltration semantics require more evidence."),
    "T1102": ("C", "Web-service traffic is visible; C2 use is not provable without endpoint/content context."),
    "T1105": ("C", "Transfer direction and volume are visible; tool identity and intent are not."),
    "T1133": ("C", "External remote-service traffic is visible; authentication and intent are not."),
    "T1190": ("C", "Connections to a public-facing service are visible; successful exploitation is not."),
    "T1210": ("C", "Remote-service interaction is visible; successful exploitation is not."),
    "T1219": ("C", "Remote-access endpoints may be recognized, but legitimate/malicious use needs context."),
    "T1567": ("C", "Web transfer is visible; exfiltration intent and content are not."),
    "T1570": ("C", "Lateral transfer pattern is partly visible; transferred tool identity is absent."),
}


DATASET_ROWS = [
    {
        "dataset": "CasinoLimit",
        "release": "Zenodo 17256954 (2025-10-03)",
        "official_source": "https://zenodo.org/records/17256954",
        "license": "CC BY 4.0",
        "flow_available": "yes",
        "benign_available": "continuous background present; row labels not direct",
        "attack_ground_truth": "system_labels + relations + instance",
        "activity_unit": "114 system-label instances; 140 Flow CSVs",
        "attack_label_granularity": "ATT&CK technique event labels, indirect Flow join",
        "schema_status": "verified on three extracted CSV members",
        "leakage_risk": "high if rows split; instance grouping required",
        "formal_role": "conditional primary episode/attribution candidate",
        "decision": "CONDITIONAL GO",
        "blocking_condition": "validate relation-window joins and freeze observable K sets",
    },
    {
        "dataset": "UWF-ZeekData24",
        "release": "2024 capture / 2025 paper",
        "official_source": "https://datasets.uwf.edu/data/UWF-ZeekData24/parquet/",
        "license": "CC BY 4.0 (site statement)",
        "flow_available": "yes (Zeek conn parquet)",
        "benign_available": "yes, but sampled weeks are temporally separated from attack weeks",
        "attack_ground_truth": "per-row label_technique",
        "activity_unit": "capture week; no explicit attack_activity_id",
        "attack_label_granularity": "ATT&CK technique",
        "schema_status": "verified 26 columns",
        "leakage_risk": "high temporal/class shortcut if randomly mixed",
        "formal_role": "source-domain/external technique evidence, not sole main split",
        "decision": "CONDITIONAL GO",
        "blocking_condition": "freeze week/activity grouping and avoid benign-vs-attack time shortcut",
    },
    {
        "dataset": "UWF-ZeekDataFall24-2",
        "release": "Fall 2024",
        "official_source": "https://datasets.uwf.edu/data/UWF-ZeekDataFall24-2/parquet/",
        "license": "CC BY 4.0 (site statement)",
        "flow_available": "yes (Zeek conn parquet)",
        "benign_available": "not in audited overlap samples",
        "attack_ground_truth": "per-row label_technique",
        "activity_unit": "capture week; no explicit attack_activity_id",
        "attack_label_granularity": "ATT&CK technique",
        "schema_status": "verified 27 columns including vlan",
        "leakage_risk": "same network/calendar as Data24 for two weeks",
        "formal_role": "attack-only companion/external evaluation",
        "decision": "CONDITIONAL GO",
        "blocking_condition": "group overlapping weeks and never treat as independent environment",
    },
    {
        "dataset": "UWF-ZeekDataSum25-1",
        "release": "Summer 2025",
        "official_source": "https://datasets.uwf.edu/data/UWF-ZeekDataSum25-1/parquet/",
        "license": "CC BY 4.0 (site statement)",
        "flow_available": "yes",
        "benign_available": "yes in early weeks; later weeks attack-only",
        "attack_ground_truth": "per-row label_technique",
        "activity_unit": "capture week; no explicit attack_activity_id",
        "attack_label_granularity": "ATT&CK technique",
        "schema_status": "verified 26 columns on one full week",
        "leakage_risk": "time and label composition are strongly coupled",
        "formal_role": "later-period temporal external evaluation",
        "decision": "CONDITIONAL GO",
        "blocking_condition": "report supported techniques only and preserve week boundaries",
    },
    {
        "dataset": "UWF-ZeekDataSum25-2",
        "release": "Summer 2025",
        "official_source": "https://datasets.uwf.edu/data/UWF-ZeekDataSum25-2/parquet/",
        "license": "CC BY 4.0 (site statement)",
        "flow_available": "yes",
        "benign_available": "yes in early weeks",
        "attack_ground_truth": "per-row label_technique",
        "activity_unit": "capture week; no explicit attack_activity_id",
        "attack_label_granularity": "T1046/T1595 in published metrics",
        "schema_status": "verified 27 columns on one full week",
        "leakage_risk": "shares four calendar weeks/environment with Sum25-1",
        "formal_role": "companion overlap audit; not an independent external domain",
        "decision": "CONDITIONAL GO",
        "blocking_condition": "group shared weeks and avoid double counting",
    },
    {
        "dataset": "CAM-LDS",
        "release": "Zenodo 18390561 (2026)",
        "official_source": "https://zenodo.org/records/18390561",
        "license": "CC BY 4.0",
        "flow_available": "not verified in filtered data; scenario has Suricata/network logs",
        "benign_available": "no normal simulation runs",
        "attack_ground_truth": "attackmate.json per run with ATT&CK metadata",
        "activity_unit": "34 independent simulation runs across 7 scenarios",
        "attack_label_granularity": "ATT&CK techniques/sub-techniques at scripted steps",
        "schema_status": "attackmate sample verified; NetFlow schema not verified",
        "leakage_risk": "very high if log rows instead of runs are split",
        "formal_role": "optional activity-level case study only",
        "decision": "NO-GO for main Flow training",
        "blocking_condition": "no benign runs and no verified direct Flow-label join",
    },
    {
        "dataset": "NF-ToN-IoT-v3",
        "release": "existing local archive",
        "official_source": "local project audit",
        "license": "refer to original dataset terms",
        "flow_available": "yes",
        "benign_available": "yes",
        "attack_ground_truth": "family labels, no audited ATT&CK activity IDs",
        "activity_unit": "not recoverable from NF-v3 rows in existing Phase 0 audit",
        "attack_label_granularity": "dataset attack families, not ATT&CK",
        "schema_status": "audited in existing project artifacts",
        "leakage_risk": "group key not frozen",
        "formal_role": "binary/engineering smoke only",
        "decision": "NO-GO for formal ATT&CK open recognition",
        "blocking_condition": "cannot provide required technique/activity ground truth",
    },
    {
        "dataset": "Multi-Source Cybersecurity Logs",
        "release": "arXiv:2606.18190",
        "official_source": "https://arxiv.org/abs/2606.18190",
        "license": "not established from paper",
        "flow_available": "network events exist, public archive not located",
        "benign_available": "800 benign sessions reported",
        "attack_ground_truth": "per-entry ATT&CK labels reported",
        "activity_unit": "870 sessions",
        "attack_label_granularity": "53 techniques reported",
        "schema_status": "paper only; downloadable data not verified",
        "leakage_risk": "paper uses random chunk splits within simulated sessions",
        "formal_role": "watch list / paper-method comparison",
        "decision": "NO-GO now",
        "blocking_condition": "no verified public data package/license and split needs session grouping",
    },
    {
        "dataset": "COMISET / Windows-APT 2025",
        "release": "2025-2026 discovery candidates",
        "official_source": "publisher data articles",
        "license": "dataset-specific; not audited",
        "flow_available": "host-focused, not verified Flow-only",
        "benign_available": "not audited",
        "attack_ground_truth": "ATT&CK-oriented host/scenario labels",
        "activity_unit": "system events/scenarios",
        "attack_label_granularity": "ATT&CK",
        "schema_status": "metadata discovery only",
        "leakage_risk": "out of current Flow-only scope",
        "formal_role": "bounded supplementary discovery",
        "decision": "NO-GO for current Flow-only study",
        "blocking_condition": "modality mismatch",
    },
]


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if columns is None:
        columns = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_stix(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    objects = data["objects"]
    by_stix = {obj["id"]: obj for obj in objects if "id" in obj}
    by_external: dict[str, dict[str, Any]] = {}
    for obj in objects:
        if obj.get("type") != "attack-pattern":
            continue
        for ref in obj.get("external_references", []):
            if ref.get("source_name") == "mitre-attack" and ref.get("external_id"):
                by_external[ref["external_id"]] = obj
    parent_rel = {
        obj["source_ref"]: obj["target_ref"]
        for obj in objects
        if obj.get("type") == "relationship" and obj.get("relationship_type") == "subtechnique-of"
    }
    return {"bundle": data, "by_stix": by_stix, "by_external": by_external, "parent_rel": parent_rel}


def attack_external_id(obj: dict[str, Any] | None) -> str | None:
    if not obj:
        return None
    for ref in obj.get("external_references", []):
        if ref.get("source_name") == "mitre-attack":
            return ref.get("external_id")
    return None


def map_attack_id(raw_id: str, stix: dict[str, Any]) -> dict[str, Any]:
    obj = stix["by_external"].get(raw_id)
    if obj is None:
        return {
            "normalized_id": raw_id,
            "technique_name_v19_1": "",
            "parent_id_v19_1": "",
            "parent_name_v19_1": "",
            "is_subtechnique": "",
            "deprecated": "",
            "revoked": "",
            "mapping_status": "UNRESOLVED",
            "mapping_note": "No exact external_id in frozen Enterprise ATT&CK v19.1 STIX; manual review required.",
        }
    parent_obj = stix["by_stix"].get(stix["parent_rel"].get(obj["id"]))
    parent_id = attack_external_id(parent_obj) or raw_id
    revoked = bool(obj.get("revoked"))
    deprecated = bool(obj.get("x_mitre_deprecated"))
    status = "EXACT_ACTIVE"
    note = "Exact external_id match."
    if revoked or deprecated:
        status = "EXACT_HISTORICAL_REVIEW"
        note = "Exact ID exists but is revoked/deprecated in v19.1; do not silently relabel."
    return {
        "normalized_id": raw_id,
        "technique_name_v19_1": obj.get("name", ""),
        "parent_id_v19_1": parent_id,
        "parent_name_v19_1": (parent_obj or obj).get("name", ""),
        "is_subtechnique": bool(obj.get("x_mitre_is_subtechnique")),
        "deprecated": deprecated,
        "revoked": revoked,
        "mapping_status": status,
        "mapping_note": note,
    }


def parse_casino(cache: Path, stix: dict[str, Any]) -> dict[str, Any]:
    base = cache / "downloads" / "casinolimit_output" / "output"
    system_paths = sorted((base / "system_labels").glob("*.json"))
    relation_paths = sorted((base / "relations").glob("*_relations.json"))
    relation_by_instance = {p.stem.removesuffix("_relations"): p for p in relation_paths}
    support: dict[str, set[str]] = defaultdict(set)
    reliable_support: dict[str, set[str]] = defaultdict(set)
    doubtful_support: dict[str, set[str]] = defaultdict(set)
    linkable_support: dict[str, set[str]] = defaultdict(set)
    reliable_linkable_support: dict[str, set[str]] = defaultdict(set)
    record_count: Counter[str] = Counter()
    doubtful_record_count: Counter[str] = Counter()
    linked_record_count: Counter[str] = Counter()
    instance_rows: list[dict[str, Any]] = []
    instance_label_sets: dict[str, set[str]] = {}
    label_record_total = 0
    for path in system_paths:
        instance = path.stem
        labels = json.loads(path.read_text(encoding="utf-8"))
        rel_path = relation_by_instance.get(instance)
        relations = json.loads(rel_path.read_text(encoding="utf-8")) if rel_path else {}
        relation_uids = {uid for rel in relations.values() for uid in rel.get("event_uids", [])}
        per_instance: dict[str, dict[str, int]] = defaultdict(lambda: {"records": 0, "doubt_records": 0, "linked_records": 0})
        for label in labels.values():
            raw_id = label["technique"].split(":", 1)[0].strip()
            label_record_total += 1
            record_count[raw_id] += 1
            support[raw_id].add(instance)
            per_instance[raw_id]["records"] += 1
            if label.get("doubt"):
                doubtful_record_count[raw_id] += 1
                doubtful_support[raw_id].add(instance)
                per_instance[raw_id]["doubt_records"] += 1
            else:
                reliable_support[raw_id].add(instance)
            linked = bool(set(label.get("event_uids", [])) & relation_uids)
            if linked:
                linked_record_count[raw_id] += 1
                linkable_support[raw_id].add(instance)
                per_instance[raw_id]["linked_records"] += 1
                if not label.get("doubt"):
                    reliable_linkable_support[raw_id].add(instance)
        instance_label_sets[instance] = {
            tech for tech, stats in per_instance.items() if stats["records"] > stats["doubt_records"]
        }
        for raw_id, stats in sorted(per_instance.items()):
            instance_rows.append(
                {
                    "instance": instance,
                    "raw_technique_id": raw_id,
                    "parent_technique_id_v19_1": map_attack_id(raw_id, stix)["parent_id_v19_1"],
                    "label_record_count": stats["records"],
                    "doubt_record_count": stats["doubt_records"],
                    "relation_linked_record_count": stats["linked_records"],
                    "has_relation_file": bool(rel_path),
                }
            )

    all_techniques = sorted(support)
    observability_rows: list[dict[str, Any]] = []
    mapping_rows: list[dict[str, Any]] = []
    for raw_id in all_techniques:
        mapped = map_attack_id(raw_id, stix)
        category, reason = OBSERVABILITY.get(
            mapped["parent_id_v19_1"] or raw_id,
            ("D", "The audited Flow schema cannot independently establish this host/content/identity action."),
        )
        raw_n = len(support[raw_id])
        reliable_n = len(reliable_support[raw_id])
        link_n = len(linkable_support[raw_id])
        reliable_link_n = len(reliable_linkable_support[raw_id])
        if (
            reliable_n >= PREFERRED_INSTANCE_SUPPORT
            and reliable_link_n >= PREFERRED_INSTANCE_SUPPORT
            and category in {"A", "B", "C"}
            and mapped["mapping_status"] == "EXACT_ACTIVE"
        ):
            k_set = "K_core"
        elif (
            reliable_n >= MINIMUM_INSTANCE_SUPPORT
            and reliable_link_n >= 5
            and category in {"A", "B", "C"}
            and mapped["mapping_status"] == "EXACT_ACTIVE"
        ):
            k_set = "K_fewshot"
        elif reliable_n >= MINIMUM_INSTANCE_SUPPORT and mapped["mapping_status"] == "EXACT_ACTIVE":
            k_set = "K_attribution_only"
        else:
            k_set = "K_excluded"
        mapping_rows.append(
            {
                "source_dataset": "CasinoLimit",
                "raw_label": raw_id,
                **mapped,
                "auto_confirmed": mapped["mapping_status"] == "EXACT_ACTIVE",
            }
        )
        observability_rows.append(
            {
                "source_dataset": "CasinoLimit",
                "raw_technique_id": raw_id,
                "parent_technique_id_v19_1": mapped["parent_id_v19_1"],
                "technique_name_v19_1": mapped["parent_name_v19_1"],
                "observability_category": category,
                "observability_reason": reason,
                "raw_instance_support": raw_n,
                "reliable_instance_support": reliable_n,
                "relation_linkable_instance_support": link_n,
                "reliable_relation_linkable_instance_support": reliable_link_n,
                "label_record_count": record_count[raw_id],
                "doubt_record_count": doubtful_record_count[raw_id],
                "relation_linked_record_count": linked_record_count[raw_id],
                "provisional_k_set": k_set,
                "mapping_status": mapped["mapping_status"],
            }
        )

    split = find_group_split(sorted(instance_label_sets), instance_label_sets, reliable_support)
    dry_run = casino_dry_run(cache, stix)
    thresholds = {
        str(threshold): sum(len(instances) >= threshold for instances in support.values())
        for threshold in [1, 5, 8, 10, 15, 20]
    }
    reliable_thresholds = {
        str(threshold): sum(len(instances) >= threshold for instances in reliable_support.values())
        for threshold in [1, 5, 8, 10, 15, 20]
    }
    return {
        "instances": len(system_paths),
        "flow_csv_members_official": 140,
        "system_label_records": label_record_total,
        "distinct_raw_techniques": len(all_techniques),
        "relation_files": len(relation_paths),
        "threshold_counts": thresholds,
        "reliable_threshold_counts": reliable_thresholds,
        "instance_rows": instance_rows,
        "mapping_rows": mapping_rows,
        "observability_rows": observability_rows,
        "split": split,
        "dry_run": dry_run,
        "k_sets": {
            name: sorted(row["parent_technique_id_v19_1"] for row in observability_rows if row["provisional_k_set"] == name)
            for name in ["K_core", "K_fewshot", "K_attribution_only", "K_excluded"]
        },
    }


def find_group_split(
    instances: list[str],
    instance_label_sets: dict[str, set[str]],
    reliable_support: dict[str, set[str]],
) -> dict[str, Any]:
    core = sorted(tech for tech, groups in reliable_support.items() if len(groups) >= PREFERRED_INSTANCE_SUPPORT)
    matrix = np.array([[tech in instance_label_sets[instance] for tech in core] for instance in instances], dtype=np.int16)
    rng = np.random.default_rng(AUDIT_SEED)
    sizes = (80, 17, len(instances) - 97)
    minima = np.array([[8], [3], [4]], dtype=np.int16)
    best: tuple[Any, ...] | None = None
    for trial in range(200_000):
        permutation = rng.permutation(len(instances))
        counts = np.vstack(
            [
                matrix[permutation[: sizes[0]]].sum(axis=0),
                matrix[permutation[sizes[0] : sizes[0] + sizes[1]]].sum(axis=0),
                matrix[permutation[sizes[0] + sizes[1] :]].sum(axis=0),
            ]
        )
        violation = int(np.maximum(minima - counts, 0).sum())
        score = (violation, -int(counts.min()), -int(counts[1:].min()))
        if best is None or score < best[0]:
            best = (score, trial, permutation, counts)
        if violation == 0:
            break
    assert best is not None
    _, trial, permutation, counts = best
    split_names = {
        "train": [instances[i] for i in permutation[: sizes[0]]],
        "validation": [instances[i] for i in permutation[sizes[0] : sizes[0] + sizes[1]]],
        "test": [instances[i] for i in permutation[sizes[0] + sizes[1] :]],
    }
    technique_counts = {
        tech: {"train": int(counts[0, j]), "validation": int(counts[1, j]), "test": int(counts[2, j])}
        for j, tech in enumerate(core)
    }
    return {
        "status": "FEASIBLE_ON_INSTANCE_LABEL_PRESENCE" if best[0][0] == 0 else "NOT_FEASIBLE_WITH_SEARCH_BUDGET",
        "seed": AUDIT_SEED,
        "trial": int(trial),
        "split_sizes": dict(zip(["train", "validation", "test"], sizes)),
        "minimum_per_technique": {"train": 8, "validation": 3, "test": 4},
        "techniques_checked": core,
        "technique_counts": technique_counts,
        "groups": split_names,
        "caveat": (
            "This proves only an instance-level label-presence split for non-doubt techniques with >=20 instances. "
            "It does not prove that each technique has enough correctly joined, Flow-observable samples."
        ),
    }


def ip_match(series: pd.Series, pattern: str) -> pd.Series:
    if not pattern:
        return pd.Series(True, index=series.index)
    if "/" in pattern:
        network = ipaddress.ip_network(pattern, strict=False)
        return series.map(lambda value: ipaddress.ip_address(str(value)) in network)
    return series.map(lambda value: fnmatch.fnmatch(str(value), pattern))


def port_match(series: pd.Series, pattern: str) -> pd.Series:
    if not pattern:
        return pd.Series(True, index=series.index)
    return series.astype(str) == str(pattern)


def casino_dry_run(cache: Path, stix: dict[str, Any]) -> dict[str, Any]:
    instance = "ravissant"
    base = cache / "downloads" / "casinolimit_output" / "output"
    flow_path = cache / "downloads" / "casinolimit_ravissant.csv"
    physical_rows = flow_path.read_bytes().count(b"\n") - 1
    frame = pd.read_csv(flow_path, skipinitialspace=True, engine="python", on_bad_lines="skip")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    labels = json.loads((base / "system_labels" / f"{instance}.json").read_text(encoding="utf-8"))
    relations = json.loads((base / "relations" / f"{instance}_relations.json").read_text(encoding="utf-8"))
    uid_to_techniques: dict[str, set[str]] = defaultdict(set)
    for label in labels.values():
        for uid in label.get("event_uids", []):
            uid_to_techniques[uid].add(label["technique"].split(":", 1)[0])
    relation_results: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    for relation in relations.values():
        data = relation["data"]
        time_mask = (frame["timestamp"] >= pd.Timestamp(data["start_time"])) & (
            frame["timestamp"] <= pd.Timestamp(data["end_time"])
        )
        direct = (
            time_mask
            & ip_match(frame["src_ip"], data.get("src_ip", ""))
            & ip_match(frame["dst_ip"], data.get("dst_ip", ""))
            & port_match(frame["src_port"], data.get("src_port", ""))
            & port_match(frame["dst_port"], data.get("dst_port", ""))
        )
        reverse = (
            time_mask
            & ip_match(frame["dst_ip"], data.get("src_ip", ""))
            & ip_match(frame["src_ip"], data.get("dst_ip", ""))
            & port_match(frame["dst_port"], data.get("src_port", ""))
            & port_match(frame["src_port"], data.get("dst_port", ""))
        )
        matched = direct | reverse
        raw_ids = sorted({tech for uid in relation.get("event_uids", []) for tech in uid_to_techniques.get(uid, set())})
        mapped = [map_attack_id(raw_id, stix) for raw_id in raw_ids]
        relation_results.append(
            {
                "event_uids": relation.get("event_uids", []),
                "raw_techniques": raw_ids,
                "parent_techniques_v19_1": sorted({item["parent_id_v19_1"] for item in mapped}),
                "time_window_candidate_count": int(time_mask.sum()),
                "strict_directed_match_count": int(direct.sum()),
                "direction_normalized_match_count": int(matched.sum()),
                "relation_data": data,
            }
        )
        for _, row in frame.loc[matched].head(2).iterrows():
            samples.append(
                {
                    "instance": instance,
                    "event_uids": relation.get("event_uids", []),
                    "raw_techniques": raw_ids,
                    "parent_techniques_v19_1": sorted({item["parent_id_v19_1"] for item in mapped}),
                    "timestamp": row["timestamp"].isoformat(),
                    "src_ip": row["src_ip"],
                    "dst_ip": row["dst_ip"],
                    "src_port": int(row["src_port"]),
                    "dst_port": int(row["dst_port"]),
                    "protocol": row["protocol"],
                    "bytes": float(row["bytes"]),
                    "packets": int(row["packets"]),
                    "join_mode": "time + relation endpoints/ports, accepting reverse Flow direction",
                }
            )
    return {
        "status": "PARTIAL_PASS_WITH_JOIN_WARNINGS",
        "formal_training_started": False,
        "instance": instance,
        "raw_flow_file": str(flow_path),
        "physical_data_rows": int(physical_rows),
        "parsed_rows": int(len(frame)),
        "malformed_or_skipped_rows": int(physical_rows - len(frame)),
        "system_label_records": len(labels),
        "relation_records": len(relations),
        "pipeline_stages": [
            "raw Flow CSV",
            "event_uid join to relation",
            "exact ATT&CK v19.1 external_id mapping",
            "time-window candidates",
            "directed and direction-normalized endpoint/port match",
            "candidate evidence sample",
        ],
        "relations": relation_results,
        "candidate_samples": samples,
        "warning": (
            "Two of three relations yielded candidates only after deterministic direction normalization; "
            "one relation yielded no endpoint/port match. The adapter must be validated on more instances "
            "before CasinoLimit can supply formal supervised Flow labels."
        ),
    }


def uwf_overlap(cache: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pairs = [
        (
            "Data24",
            "Fall24-2",
            "2024-10-27 - 2024-11-03",
            cache / "downloads" / "uwf_data24_2024-10-27.parquet",
            cache / "downloads" / "uwf_fall24_2_2024-10-27.parquet",
        ),
        (
            "Data24",
            "Fall24-2",
            "2024-11-03 - 2024-11-10",
            cache / "downloads" / "uwf_data24_2024-11-03.parquet",
            cache / "downloads" / "uwf_fall24_2_2024-11-03.parquet",
        ),
        (
            "Sum25-1",
            "Sum25-2",
            "2025-06-08 - 2025-06-15",
            cache / "downloads" / "uwf_sum25_1_2025-06-08.parquet",
            cache / "downloads" / "uwf_sum25_2_2025-06-08.parquet",
        ),
    ]
    rows: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    for left_name, right_name, week, left_path, right_path in pairs:
        left = pd.read_parquet(left_path)
        right = pd.read_parquet(right_path)
        key_cols = ["ts", "src_ip_zeek", "src_port_zeek", "dest_ip_zeek", "dest_port_zeek", "proto"]
        left_keys = set(map(tuple, left[key_cols].itertuples(index=False, name=None)))
        right_keys = set(map(tuple, right[key_cols].itertuples(index=False, name=None)))
        uid_intersection = len(set(left["uid"].astype(str)) & set(right["uid"].astype(str)))
        community_intersection = len(
            set(left["community_id"].dropna().astype(str)) & set(right["community_id"].dropna().astype(str))
        )
        flow_intersection = len(left_keys & right_keys)
        row = {
            "left_dataset": left_name,
            "right_dataset": right_name,
            "calendar_week": week,
            "left_rows": len(left),
            "right_rows": len(right),
            "left_labels": "|".join(sorted(left["label_technique"].astype(str).unique())),
            "right_labels": "|".join(sorted(right["label_technique"].astype(str).unique())),
            "time_ranges_overlap": max(left["ts"].min(), right["ts"].min()) <= min(left["ts"].max(), right["ts"].max()),
            "uid_intersection": uid_intersection,
            "community_id_intersection": community_intersection,
            "exact_flow_key_intersection": flow_intersection,
            "common_columns": len(set(left.columns) & set(right.columns)),
            "left_only_columns": "|".join(sorted(set(left.columns) - set(right.columns))),
            "right_only_columns": "|".join(sorted(set(right.columns) - set(left.columns))),
            "interpretation": "shared calendar/environment; no exact sampled record overlap",
        }
        rows.append(row)
        details[f"{left_name}__{right_name}__{week}"] = row

    # Published official metrics show four Sum25 shared calendar weeks. Only
    # the final pair was downloaded because it is tiny and sufficient to test
    # exact-record overlap mechanics.
    for week, left_rows, right_rows in [
        ("2025-05-18 - 2025-05-25", 49_893, 244_377),
        ("2025-05-25 - 2025-06-01", 179_308, 1_146_127),
        ("2025-06-01 - 2025-06-08", 302_746, 478_173),
    ]:
        rows.append(
            {
                "left_dataset": "Sum25-1",
                "right_dataset": "Sum25-2",
                "calendar_week": week,
                "left_rows": left_rows,
                "right_rows": right_rows,
                "left_labels": "from official technique metrics",
                "right_labels": "from official technique metrics",
                "time_ranges_overlap": True,
                "uid_intersection": "not sampled",
                "community_id_intersection": "not sampled",
                "exact_flow_key_intersection": "not sampled",
                "common_columns": 26,
                "left_only_columns": "",
                "right_only_columns": "vlan",
                "interpretation": "shared calendar/environment; exact-record overlap not tested",
            }
        )
    return rows, details


def schema_rows(cache: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    datasets = {
        "CasinoLimit": cache / "downloads" / "casinolimit_robotique.csv",
        "UWF Data24": cache / "downloads" / "uwf_data24_2024-10-27.parquet",
        "UWF Fall24-2": cache / "downloads" / "uwf_fall24_2_2024-10-27.parquet",
        "UWF Sum25-1": cache / "downloads" / "uwf_sum25_1_2025-06-08.parquet",
        "UWF Sum25-2": cache / "downloads" / "uwf_sum25_2_2025-06-08.parquet",
    }
    canonical = {
        "timestamp": {"CasinoLimit": "timestamp", "UWF": "ts|datetime"},
        "src_ip": {"CasinoLimit": "src_ip", "UWF": "src_ip_zeek"},
        "dst_ip": {"CasinoLimit": "dst_ip", "UWF": "dest_ip_zeek"},
        "src_port": {"CasinoLimit": "src_port", "UWF": "src_port_zeek"},
        "dst_port": {"CasinoLimit": "dst_port", "UWF": "dest_port_zeek"},
        "protocol": {"CasinoLimit": "protocol", "UWF": "proto"},
        "duration": {"CasinoLimit": "duration", "UWF": "duration"},
        "forward_reverse_bytes": {"CasinoLimit": "bytes (one recorded direction/row)", "UWF": "orig_bytes|resp_bytes"},
        "forward_reverse_packets": {"CasinoLimit": "packets (one recorded direction/row)", "UWF": "orig_pkts|resp_pkts"},
        "tcp_state_or_history": {"CasinoLimit": "missing", "UWF": "conn_state|history"},
        "service": {"CasinoLimit": "missing", "UWF": "service"},
        "attack_technique": {"CasinoLimit": "indirect system_labels+relations", "UWF": "label_technique"},
        "activity_group": {"CasinoLimit": "instance_name", "UWF": "missing; derive capture-week/activity group"},
    }
    for dataset, path in datasets.items():
        if path.suffix == ".csv":
            columns = [column.strip() for column in pd.read_csv(path, nrows=0).columns]
            family = "CasinoLimit"
        else:
            columns = list(pd.read_parquet(path).columns)
            family = "UWF"
        for field, mapping in canonical.items():
            source = mapping[family]
            available = source not in {"missing", ""}
            rows.append(
                {
                    "dataset": dataset,
                    "canonical_field": field,
                    "source_field_or_rule": source,
                    "availability": "yes" if available else "no",
                    "verified_sample_path": str(path),
                    "notes": "adapter required" if "|" in source or "indirect" in source or "derive" in source else "",
                }
            )
    for field in canonical:
        rows.append(
            {
                "dataset": "CAM-LDS",
                "canonical_field": field,
                "source_field_or_rule": "not verified from a NetFlow sample",
                "availability": "unknown",
                "verified_sample_path": str(cache / "downloads" / "cam_scenario7_attackmate.json"),
                "notes": "attackmate ground truth is verified, direct Flow schema/join is not",
            }
        )
    return rows


def add_non_casino_mappings(cache: Path, stix: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    source_labels: dict[str, set[str]] = defaultdict(set)
    for filename, source in [
        ("uwf_data24_technique_metrics.csv", "UWF Data24"),
        ("uwf_sum25_1_technique_metrics.csv", "UWF Sum25-1"),
        ("uwf_sum25_2_technique_metrics.csv", "UWF Sum25-2"),
    ]:
        frame = pd.read_csv(cache / "metadata" / filename)
        for value in frame["label_technique"].astype(str):
            if re.fullmatch(r"T\d{4}(?:\.\d{3})?", value):
                source_labels[source].add(value)
    for path in (cache / "downloads").glob("uwf_fall24_2_*.parquet"):
        for value in pd.read_parquet(path, columns=["label_technique"])["label_technique"].astype(str).unique():
            if re.fullmatch(r"T\d{4}(?:\.\d{3})?", value):
                source_labels["UWF Fall24-2"].add(value)
    attackmate = cache / "downloads" / "cam_scenario7_attackmate.json"
    for line in attackmate.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        parameters = event.get("parameters") or {}
        metadata = parameters.get("metadata") or {}
        technique_text = metadata.get("techniques", "")
        for value in technique_text.split(","):
            value = value.strip()
            if re.fullmatch(r"T\d{4}(?:\.\d{3})?", value):
                source_labels["CAM-LDS scenario_7 sample"].add(value)
    for source, labels in sorted(source_labels.items()):
        for raw_id in sorted(labels):
            mapped = map_attack_id(raw_id, stix)
            rows.append(
                {
                    "source_dataset": source,
                    "raw_label": raw_id,
                    **mapped,
                    "auto_confirmed": mapped["mapping_status"] == "EXACT_ACTIVE",
                }
            )


def download_manifest(cache: Path) -> list[dict[str, Any]]:
    source_map = {
        "zenodo_17256954.json": "https://zenodo.org/api/records/17256954",
        "zenodo_18390561.json": "https://zenodo.org/api/records/18390561",
        "enterprise-attack-19.1.json": "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/v19.1/enterprise-attack/enterprise-attack-19.1.json",
        "qwen35_9b_base_config.json": "https://huggingface.co/Qwen/Qwen3.5-9B-Base/raw/main/config.json",
        "qwen35_9b_config.json": "https://huggingface.co/Qwen/Qwen3.5-9B/raw/main/config.json",
        "modeling_qwen3_5.py": "https://raw.githubusercontent.com/huggingface/transformers/main/src/transformers/models/qwen3_5/modeling_qwen3_5.py",
        "configuration_qwen3_5.py": "https://raw.githubusercontent.com/huggingface/transformers/main/src/transformers/models/qwen3_5/configuration_qwen3_5.py",
        "dollm_2405.07638.pdf": "https://arxiv.org/pdf/2405.07638",
        "trafficllm_2504.04222.pdf": "https://arxiv.org/pdf/2504.04222",
        "multisource_2606.18190.pdf": "https://arxiv.org/pdf/2606.18190",
        "uwf_zeekdata24.pdf": "https://www.mdpi.com/2306-5729/10/5/59/pdf",
        "casinolimit_output.zip": "https://zenodo.org/api/records/17256954/files/output.zip/content",
        "casinolimit_syslogs_labels.zip": "https://zenodo.org/api/records/17256954/files/syslogs_labels.zip/content",
        "casinolimit_labelled_flows_tail.bin": "https://zenodo.org/api/records/17256954/files/labelled_flows.zip/content#range-tail",
        "casinolimit_minnie_member.bin": "https://zenodo.org/api/records/17256954/files/labelled_flows.zip/content#member-minnie",
        "casinolimit_robotique_member.bin": "https://zenodo.org/api/records/17256954/files/labelled_flows.zip/content#member-robotique",
        "casinolimit_ravissant_member.bin": "https://zenodo.org/api/records/17256954/files/labelled_flows.zip/content#member-ravissant",
        "cam_scenario7_tail.bin": "https://zenodo.org/api/records/18390561/files/scenario_7.zip/content#range-tail",
        "cam_scenario7_attackmate_member.bin": "https://zenodo.org/api/records/18390561/files/scenario_7.zip/content#member-attackmate.json",
        "cam_manifestations_filtered_tail.bin": "https://zenodo.org/api/records/18390561/files/manifestations_filtered.zip/content#range-tail",
    }
    partial = {"casinolimit_syslogs_labels.zip", "casinolimit_flow_probe.bin"}
    range_only = {
        "casinolimit_labelled_flows_tail.bin",
        "casinolimit_minnie_member.bin",
        "casinolimit_robotique_member.bin",
        "casinolimit_ravissant_member.bin",
        "cam_scenario7_tail.bin",
        "cam_scenario7_attackmate_member.bin",
        "cam_manifestations_filtered_tail.bin",
        "casinolimit_flow_probe.bin",
    }
    rows = []
    for path in sorted(p for p in cache.rglob("*") if p.is_file() and "casinolimit_output\\output" not in str(p)):
        name = path.name
        if name.startswith("uwf_") and path.suffix == ".parquet":
            source = "https://datasets.uwf.edu/data/ (official dated parquet directory; cached filename normalized)"
        elif name.startswith("uwf_") and name.endswith("metrics.csv"):
            source = "https://datasets.uwf.edu/data/ (official _parquet_technique_metrics_ directory)"
        else:
            source = source_map.get(name, "derived locally from an official cached archive/sample")
        complete = "partial" if name in partial else ("range/member complete" if name in range_only else "complete")
        stat = path.stat()
        rows.append(
            {
                "local_path": str(path),
                "source_url": source,
                "acquired_or_derived_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "size_bytes": stat.st_size,
                "sha256": file_sha256(path),
                "completeness": complete,
                "version_or_record": "ATT&CK v19.1" if name == "enterprise-attack-19.1.json" else "see source metadata",
                "license": (
                    "CC BY 4.0" if any(token in name for token in ["casino", "cam_", "uwf_"]) else "source-specific"
                ),
            }
        )
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
    casino = parse_casino(cache, stix)
    mapping_rows = casino["mapping_rows"]
    add_non_casino_mappings(cache, stix, mapping_rows)
    overlap_rows, overlap_details = uwf_overlap(cache)
    schemas = schema_rows(cache)

    write_csv(report / "03_candidate_dataset_matrix.csv", DATASET_ROWS)
    write_csv(report / "06_casinolimit_instance_technique_matrix.csv", casino["instance_rows"])
    write_csv(report / "08_uwf_overlap_matrix.csv", overlap_rows)
    write_csv(report / "09_attack_v19_1_mapping.csv", mapping_rows)
    write_csv(report / "10_flow_observability_audit.csv", casino["observability_rows"])
    write_csv(report / "11_schema_compatibility.csv", schemas)
    write_json(report / "13_split_feasibility.json", casino["split"])
    write_json(report / "16_download_manifest.json", download_manifest(cache))
    write_json(report / "dry_run_evidence.json", casino["dry_run"])

    summary = {
        "audit_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "audit_seed": AUDIT_SEED,
        "attack_version": "Enterprise ATT&CK v19.1",
        "attack_stix_sha256": file_sha256(stix_path),
        "cache_bytes_touched": sum(path.stat().st_size for path in cache.rglob("*") if path.is_file()),
        "casino": {key: value for key, value in casino.items() if key not in {"instance_rows", "mapping_rows", "observability_rows"}},
        "uwf_overlap": overlap_details,
        "dataset_decisions": {row["dataset"]: row["decision"] for row in DATASET_ROWS},
        "formal_selection": {
            "main": "CasinoLimit only as a conditional episode-level candidate; not approved for row-level supervised labels",
            "source_or_external": "UWF datasets under capture-week grouping and label-support restrictions",
            "optional": "CAM-LDS activity-level case study after a direct Flow join is verified",
            "no_go": "NF-ToN-IoT-v3 for ATT&CK task; host-only supplementary datasets; unavailable multi-source archive",
        },
        "no_gpu_training_performed": True,
    }
    write_json(report / "audit_summary.json", summary)
    print(json.dumps({"status": "ok", "report_dir": str(report), "casino": summary["casino"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
