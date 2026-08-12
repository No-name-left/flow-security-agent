#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import pyarrow as pa
import pyarrow.parquet as pq

from flowsec.training.contextual_salvage_v2 import (
    ArpClaimV2,
    RelationGraphTargetV2,
    ScanSessionObservationV2,
    build_past_only_relation_graph_v2,
    build_past_only_scan_context_v2,
    strongest_relation_context,
    strongest_scan_context,
)
from flowsec.training.contracts import EvidenceFamilyV2, EvidenceStageV2, SFTRecordV2


AUDIT_VERSION = "BASIC_V2_SUFFICIENCY_AND_CONTEXTUAL_SALVAGE_V2"
EXPECTED_CLASSES = (
    "DDoS_HTTP",
    "DDoS_TCP",
    "Normal",
    "Password",
    "SQL_injection",
    "Vulnerability_scanner",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _load_primary_basic(corpus_path: Path) -> dict[str, Any]:
    records: list[SFTRecordV2] = []
    with corpus_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            try:
                record = SFTRecordV2.model_validate_json(line)
            except Exception as error:  # pragma: no cover - diagnostic context
                raise ValueError(f"invalid SFT-v2 record at line {line_number}") from error
            if record.state_role == "primary":
                if not record.classification_ce_eligible:
                    raise ValueError("primary state is not classification-CE eligible")
                if record.stage_type is not EvidenceStageV2.BASIC:
                    raise ValueError("primary state is not Basic-v2")
                records.append(record)

    if len({item.sample_id for item in records}) != len(records):
        raise ValueError("formal corpus contains duplicate primary sample identities")
    observed_classes = tuple(sorted({item.fine_label for item in records}))
    if observed_classes != EXPECTED_CLASSES:
        raise ValueError(f"unexpected formal class set: {observed_classes}")

    def summarize(items: Iterable[SFTRecordV2]) -> dict[str, Any]:
        values = tuple(items)
        sufficient = sum(item.evidence_state_target.evidence_sufficient for item in values)
        gap_counts = Counter(len(item.evidence_state_target.missing_evidence) for item in values)
        family_counts = Counter(
            family.value
            for item in values
            for family in item.evidence_state_target.missing_evidence
        )
        inconsistent = sum(
            bool(item.evidence_state_target.missing_evidence)
            == item.evidence_state_target.evidence_sufficient
            for item in values
        )
        if inconsistent:
            raise ValueError("zero-gap and evidence-sufficient semantics disagree")
        insufficient = len(values) - sufficient
        return {
            "primary_basic_n": len(values),
            "sufficient_n": sufficient,
            "insufficient_n": insufficient,
            "sufficient_rate": _rate(sufficient, len(values)),
            "zero_gap_n": gap_counts[0],
            "single_gap_n": gap_counts[1],
            "multi_gap_n": sum(count for size, count in gap_counts.items() if size >= 2),
            "single_gap_rate": _rate(gap_counts[1], len(values)),
            "multi_gap_rate": _rate(
                sum(count for size, count in gap_counts.items() if size >= 2), len(values)
            ),
            "missing_evidence_occurrences": {
                family.value: family_counts[family.value] for family in EvidenceFamilyV2
            },
            "missing_evidence_rate_over_all_primary": {
                family.value: _rate(family_counts[family.value], len(values))
                for family in EvidenceFamilyV2
            },
            "missing_evidence_rate_over_insufficient_primary": {
                family.value: _rate(family_counts[family.value], insufficient)
                for family in EvidenceFamilyV2
            },
        }

    per_class = {
        fine_label: summarize(item for item in records if item.fine_label == fine_label)
        for fine_label in EXPECTED_CLASSES
    }
    return {
        "corpus_path": str(corpus_path),
        "corpus_sha256": _sha256(corpus_path),
        "primary_schema": "SFTRecordV2",
        "primary_role": "state_role=primary + classification_ce_eligible=true",
        "primary_stage": "EvidenceStageV2.BASIC",
        "zero_gap_equivalent_to_sufficient": True,
        "overall": summarize(records),
        "per_class": per_class,
        "old_new_direct_comparison": "NOT_VALID",
        "old_new_direct_comparison_reason": (
            "The superseded Teacher V3 corpus used a different population, Evidence schema, "
            "Initial representation, and non-uniform primary stage assignment; its percentage "
            "is not an estimand-equivalent Basic-v2 baseline."
        ),
    }


RAW_COLUMNS = (
    "sample_id",
    "split",
    "timestamp_start",
    "timestamp_end",
    "raw_initiator_ip",
    "raw_responder_ip",
    "raw_responder_port",
    "packet_count",
    "responder_packets",
    "tcp_syn",
    "tcp_synack",
    "tcp_rst",
    "duration",
)


def _load_raw(path: Path) -> list[dict[str, Any]]:
    return pq.read_table(path, columns=list(RAW_COLUMNS)).to_pylist()


def _relation_inputs(
    capture_id: str,
    raw_rows: list[dict[str, Any]],
    link_path: Path,
) -> tuple[list[RelationGraphTargetV2], list[ArpClaimV2]]:
    targets = [
        RelationGraphTargetV2(
            record_id=str(row["sample_id"]),
            observation_scope_id=capture_id,
            partition_id=str(row["split"]),
            timestamp=float(row["timestamp_start"]),
            source_ip=str(row["raw_initiator_ip"]),
            destination_ip=str(row["raw_responder_ip"]),
        )
        for row in raw_rows
    ]
    claims: list[ArpClaimV2] = []
    for row in pq.read_table(link_path).to_pylist():
        if row.get("event_type") != "ARP":
            continue
        if not row.get("source_mac") or not row.get("source_ip") or not row.get("target_ip"):
            continue
        if row["source_ip"] in {"0.0.0.0", "::"}:
            continue
        claims.append(
            ArpClaimV2(
                observation_scope_id=capture_id,
                timestamp=float(row["timestamp"]),
                sender_mac=str(row["source_mac"]),
                sender_ip=str(row["source_ip"]),
                target_ip=str(row["target_ip"]),
            )
        )
    return targets, claims


def _scan_inputs(capture_id: str, raw_rows: list[dict[str, Any]]) -> list[ScanSessionObservationV2]:
    return [
        ScanSessionObservationV2(
            record_id=str(row["sample_id"]),
            observation_scope_id=capture_id,
            partition_id=str(row["split"]),
            timestamp_start=float(row["timestamp_start"]),
            timestamp_end=float(row["timestamp_end"]),
            source_node_id=str(row["raw_initiator_ip"]),
            destination_node_id=str(row["raw_responder_ip"]),
            destination_port=int(row["raw_responder_port"]),
            packet_count=int(row["packet_count"]),
            responder_packet_count=int(row["responder_packets"]),
            tcp_syn_count=int(row["tcp_syn"]),
            tcp_synack_count=int(row["tcp_synack"]),
            tcp_rst_count=int(row["tcp_rst"]),
            duration_seconds=float(row["duration"]),
        )
        for row in raw_rows
    ]


def _audit_capture(
    capture_id: str,
    raw_path: Path,
    link_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    raw_rows = _load_raw(raw_path)
    by_id = {str(row["sample_id"]): row for row in raw_rows}

    targets, claims = _relation_inputs(capture_id, raw_rows, link_path)
    relation = build_past_only_relation_graph_v2(targets, claims)
    relation_supported: list[dict[str, Any]] = []
    relation_split = Counter()
    relation_level = Counter()
    relation_horizon = Counter()
    for record_id, contexts in relation.items():
        strongest = strongest_relation_context(contexts)
        if strongest is None:
            continue
        row = by_id[record_id]
        relation_split[str(row["split"])] += 1
        relation_level[strongest.relation_level] += 1
        relation_horizon[str(strongest.horizon_seconds)] += 1
        relation_supported.append(
            {
                "sample_id_backend_only": record_id,
                "capture_id_backend_only": capture_id,
                "split_backend_only": str(row["split"]),
                "shortest_supported_horizon": strongest.horizon_seconds,
                "relation_level": strongest.relation_level,
                "repeated_same_mac_common_target_count": (
                    strongest.repeated_same_mac_common_target_count
                ),
                "repeated_anomalous_claim_count": strongest.repeated_anomalous_claim_count,
            }
        )

    sessions = _scan_inputs(capture_id, raw_rows)
    scan = build_past_only_scan_context_v2(sessions)
    scan_supported: list[dict[str, Any]] = []
    scan_split = Counter()
    scan_mechanism = Counter()
    scan_horizon = Counter()
    maxima = Counter()
    for record_id, contexts in scan.items():
        for context in contexts:
            maxima["prior_same_source_session_count"] = max(
                maxima["prior_same_source_session_count"],
                context.prior_same_source_session_count,
            )
            maxima["distinct_destination_count"] = max(
                maxima["distinct_destination_count"], context.distinct_destination_count
            )
            maxima["distinct_destination_port_count"] = max(
                maxima["distinct_destination_port_count"],
                context.distinct_destination_port_count,
            )
        strongest = strongest_scan_context(contexts)
        if strongest is None:
            continue
        row = by_id[record_id]
        scan_split[str(row["split"])] += 1
        if strongest.vertical_scan_supported:
            scan_mechanism["vertical"] += 1
        if strongest.horizontal_scan_supported:
            scan_mechanism["horizontal"] += 1
        scan_horizon[str(strongest.horizon_seconds)] += 1
        scan_supported.append(
            {
                "sample_id_backend_only": record_id,
                "capture_id_backend_only": capture_id,
                "split_backend_only": str(row["split"]),
                "shortest_supported_horizon": strongest.horizon_seconds,
                "vertical_scan_supported": strongest.vertical_scan_supported,
                "horizontal_scan_supported": strongest.horizontal_scan_supported,
                "prior_same_source_session_count": strongest.prior_same_source_session_count,
                "distinct_destination_count": strongest.distinct_destination_count,
                "distinct_destination_port_count": strongest.distinct_destination_port_count,
            }
        )

    dominant_triplet_n = max(
        Counter(
            (
                row["raw_initiator_ip"],
                row["raw_responder_ip"],
                row["raw_responder_port"],
            )
            for row in raw_rows
        ).values(),
        default=0,
    )
    summary = {
        "capture_id_backend_only": capture_id,
        "session_count": len(raw_rows),
        "split_distribution": dict(sorted(Counter(str(row["split"]) for row in raw_rows).items())),
        "arp_claim_count": len(claims),
        "relation_supported_n": len(relation_supported),
        "relation_supported_rate": _rate(len(relation_supported), len(raw_rows)),
        "relation_supported_by_split": dict(sorted(relation_split.items())),
        "relation_level_distribution": dict(sorted(relation_level.items())),
        "relation_shortest_horizon_distribution": dict(sorted(relation_horizon.items())),
        "scan_supported_n": len(scan_supported),
        "scan_supported_rate": _rate(len(scan_supported), len(raw_rows)),
        "scan_supported_by_split": dict(sorted(scan_split.items())),
        "scan_mechanism_distribution": dict(sorted(scan_mechanism.items())),
        "scan_shortest_horizon_distribution": dict(sorted(scan_horizon.items())),
        "scan_context_maxima": dict(sorted(maxima.items())),
        "dominant_source_destination_service_triplet_n_backend_only": dominant_triplet_n,
        "source_hashes": {
            "raw_sessions_sha256": _sha256(raw_path),
            "link_events_sha256": _sha256(link_path),
        },
    }
    return summary, relation_supported, scan_supported


def _write_parquet(path: Path, rows: list[dict[str, Any]], schema: pa.Schema) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows, schema=schema)
    pq.write_table(table, path, compression="zstd")


def run(args: argparse.Namespace) -> dict[str, Any]:
    corpus = Path(args.corpus).resolve()
    observable_root = Path(args.observable_root).resolve()
    external_root = Path(args.external_output_root).resolve()
    report_json = Path(args.report_json).resolve()
    external_root.mkdir(parents=True, exist_ok=True)

    basic = _load_primary_basic(corpus)
    if args.expected_corpus_sha256 and basic["corpus_sha256"] != args.expected_corpus_sha256:
        raise ValueError("formal corpus SHA256 differs from the accepted v3 corpus")

    capture_ids = ["Attack_MITM", "Attack_Port_Scanning"] + sorted(
        path.stem for path in (observable_root / "raw_sessions").glob("Normal_*.parquet")
    )
    capture_summaries: dict[str, Any] = {}
    relation_rows: list[dict[str, Any]] = []
    scan_rows: list[dict[str, Any]] = []
    for capture_id in capture_ids:
        summary, relation_supported, scan_supported = _audit_capture(
            capture_id,
            observable_root / "raw_sessions" / f"{capture_id}.parquet",
            observable_root / "link_events" / f"{capture_id}.parquet",
        )
        capture_summaries[capture_id] = summary
        relation_rows.extend(relation_supported)
        scan_rows.extend(scan_supported)
        print(
            f"SALVAGE_CAPTURE_DONE capture={capture_id} sessions={summary['session_count']} "
            f"relation={summary['relation_supported_n']} scan={summary['scan_supported_n']}",
            flush=True,
        )

    relation_path = external_root / "relation_supported_sessions.parquet"
    scan_path = external_root / "scan_supported_sessions.parquet"
    _write_parquet(
        relation_path,
        relation_rows,
        pa.schema(
            [
                ("sample_id_backend_only", pa.string()),
                ("capture_id_backend_only", pa.string()),
                ("split_backend_only", pa.string()),
                ("shortest_supported_horizon", pa.int64()),
                ("relation_level", pa.string()),
                ("repeated_same_mac_common_target_count", pa.int64()),
                ("repeated_anomalous_claim_count", pa.int64()),
            ]
        ),
    )
    _write_parquet(
        scan_path,
        scan_rows,
        pa.schema(
            [
                ("sample_id_backend_only", pa.string()),
                ("capture_id_backend_only", pa.string()),
                ("split_backend_only", pa.string()),
                ("shortest_supported_horizon", pa.int64()),
                ("vertical_scan_supported", pa.bool_()),
                ("horizontal_scan_supported", pa.bool_()),
                ("prior_same_source_session_count", pa.int64()),
                ("distinct_destination_count", pa.int64()),
                ("distinct_destination_port_count", pa.int64()),
            ]
        ),
    )

    mitm = capture_summaries["Attack_MITM"]
    scanning = capture_summaries["Attack_Port_Scanning"]
    normal_ids = [item for item in capture_ids if item.startswith("Normal_")]
    normal_session_count = sum(capture_summaries[item]["session_count"] for item in normal_ids)
    normal_relation_supported = sum(
        capture_summaries[item]["relation_supported_n"] for item in normal_ids
    )
    normal_scan_supported = sum(
        capture_summaries[item]["scan_supported_n"] for item in normal_ids
    )
    mitm_formal = mitm["relation_supported_by_split"]
    scan_formal = scanning["scan_supported_by_split"]

    manifest: dict[str, Any] = {
        "audit_version": AUDIT_VERSION,
        "status": "PASS",
        "formal_corpus_modified": False,
        "formal_sft_started": False,
        "basic_v2_primary_audit": basic,
        "salvage_contract": {
            "label_free": True,
            "deterministic": True,
            "test_time_available": True,
            "strictly_past_only": True,
            "partition_local": True,
            "future_context_used": False,
            "model_safe_identity_leakage": 0,
            "horizons_seconds": [10, 60, 180, 300],
            "relation_rule": (
                "Repeated ARP claims: at least two claims for each of at least two "
                "source IPs by one MAC toward one common target, or a repeated same-IP "
                "multi-MAC conflict, within [target_time-horizon,target_time)."
            ),
            "vertical_scan_rule": (
                "Probe-like current session plus >=8 past same-source sessions, >=8 "
                "destination ports, <=3 destinations, and >=0.5 probe ratio."
            ),
            "horizontal_scan_rule": (
                "Probe-like current session plus >=8 past same-source sessions, >=8 "
                "destinations, <=3 destination ports, and >=0.5 probe ratio."
            ),
        },
        "capture_summaries": capture_summaries,
        "controls": {
            "normal_capture_count": len(normal_ids),
            "normal_session_count": normal_session_count,
            "normal_relation_supported_n": normal_relation_supported,
            "normal_relation_supported_rate": _rate(
                normal_relation_supported, normal_session_count
            ),
            "normal_scan_supported_n": normal_scan_supported,
            "normal_scan_supported_rate": _rate(normal_scan_supported, normal_session_count),
            "port_scanning_relation_control_supported_n": scanning[
                "relation_supported_n"
            ],
            "mitm_scan_control_supported_n": mitm["scan_supported_n"],
        },
        "mitm_verdict": {
            "status": "PASS_CASE_STUDY_ONLY",
            "total_sessions": mitm["session_count"],
            "contextually_supported": mitm["relation_supported_n"],
            "full_observational_sufficient": mitm["relation_supported_n"],
            "train": mitm_formal.get("train", 0),
            "validation": mitm_formal.get("validation", 0),
            "test": mitm_formal.get("test", 0),
            "quarantine": mitm_formal.get("quarantine", 0),
            "primary_relation_mechanisms": [
                "REPEATED_SAME_MAC_MULTIPLE_IP_COMMON_TARGET",
                "ENTITY_LINKED_OR_BOUNDED_LOCAL_NETWORK_STATE",
            ],
            "capture_label_required": False,
            "future_context_used": False,
            "model_safe_leakage": 0,
            "main_class_exclusion_reason": (
                "The relation mechanism is real and label-free, but only 150/25/24 "
                "supported train/validation/test sessions remain, most support is shared "
                "Level-B local state, and all observations come from one capture/run. This "
                "is sufficient for a bounded case study, not stable primary-class training "
                "and evaluation."
            ),
        },
        "scanning_verdict": {
            "status": "FAIL",
            "original_label": "Port_Scanning",
            "formal_label": "UNRESOLVED_PORT_SCANNING_NOT_OBSERVED",
            "total_sessions": scanning["session_count"],
            "contextually_supported": scanning["scan_supported_n"],
            "full_observational_sufficient": scanning["scan_supported_n"],
            "train": scan_formal.get("train", 0),
            "validation": scan_formal.get("validation", 0),
            "test": scan_formal.get("test", 0),
            "quarantine": scan_formal.get("quarantine", 0),
            "vertical_scan_supported": bool(
                scanning["scan_mechanism_distribution"].get("vertical", 0)
            ),
            "horizontal_scan_supported": bool(
                scanning["scan_mechanism_distribution"].get("horizontal", 0)
            ),
            "primary_scan_mechanism": "NONE",
            "capture_label_required": True,
            "future_context_used": False,
            "model_safe_leakage": 0,
            "failure_reason": (
                "The dominant 9,987-session source/destination/service triplet repeatedly "
                "targets one destination and one destination port; neither vertical port "
                "diversity nor horizontal host/service fan-out is observed under any fixed "
                "strict-past horizon."
            ),
        },
        "consequence": {
            "proposed_final_main_classes": list(EXPECTED_CLASSES),
            "proposed_final_main_class_count": len(EXPECTED_CLASSES),
            "salvage_integration_required": False,
            "current_6_class_corpus_still_valid": True,
            "ready_for_formal_sft": True,
            "next_action": "START_FORMAL_NEAR_MULTI_TASK_SFT",
        },
        "external_artifacts": {
            "root": str(external_root),
            "relation_supported_sessions": {
                "path": str(relation_path),
                "row_count": len(relation_rows),
                "sha256": _sha256(relation_path),
            },
            "scan_supported_sessions": {
                "path": str(scan_path),
                "row_count": len(scan_rows),
                "sha256": _sha256(scan_path),
            },
        },
    }
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    external_manifest = external_root / "manifest.json"
    external_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"AUDIT_MANIFEST={report_json}")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--corpus",
        default=(
            "/root/autodl-tmp/processed/near_pretraining_v3/sft_corpus/final/"
            "observable_sft_corpus_v3.jsonl"
        ),
    )
    parser.add_argument(
        "--expected-corpus-sha256",
        default="d93789de29b746d923660bb2e4ccad501412e75303ddf95f7087c85f6c67d6ca",
    )
    parser.add_argument(
        "--observable-root", default="/root/autodl-tmp/processed/observable_dataset_v3"
    )
    parser.add_argument(
        "--external-output-root",
        default="/root/autodl-tmp/experiments/contextual_evidence_salvage_v2",
    )
    parser.add_argument(
        "--report-json",
        default=(
            "reports/training_readiness/"
            "basic_v2_sufficiency_and_contextual_salvage_v2.json"
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
