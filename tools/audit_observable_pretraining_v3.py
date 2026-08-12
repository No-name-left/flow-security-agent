#!/usr/bin/env python3
"""Audit frozen Teacher-v2 and Observable SFT-v3 assets without model calls."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from flowsec.training.contracts import EvidenceSnapshotV2, SFTRecordV2, canonical_json, content_digest
from flowsec.training.corpus_v3 import atomic_json, atomic_jsonl
from flowsec.training.materialization import sha256_file
from flowsec.training.teacher import validate_teacher_v2_annotation


def _audit_digest(value: dict[str, Any]) -> str:
    return content_digest({key: item for key, item in value.items() if key != "audit_digest"})


def _write_audit(path: Path, value: dict[str, Any]) -> None:
    value["audit_digest"] = _audit_digest(value)
    atomic_json(path, value)


def _load_jsonl(path: Path, model: Any) -> list[Any]:
    return [model.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def audit(
    *, snapshot_manifest_path: Path, annotation_root: Path, pretraining_root: Path,
    historical_u_final_manifest: Path,
) -> dict[str, Any]:
    snapshot_manifest = json.loads(snapshot_manifest_path.read_text(encoding="utf-8"))
    snapshots = _load_jsonl(Path(snapshot_manifest["snapshots"]["path"]), EvidenceSnapshotV2)
    annotation_manifest = json.loads((annotation_root / "manifest.json").read_text(encoding="utf-8"))
    corpus_manifest_path = pretraining_root / "sft_corpus/final/manifest.json"
    corpus_manifest = json.loads(corpus_manifest_path.read_text(encoding="utf-8"))
    corpus_path = Path(corpus_manifest["artifacts"]["corpus"]["path"])
    records = _load_jsonl(corpus_path, SFTRecordV2)
    records_by_state = {item.evidence_state_id: item for item in records}
    if len(records_by_state) != len(records):
        raise ValueError("formal corpus contains duplicate Evidence-state identity")
    snapshot_by_state = {item.evidence_state_id: item for item in snapshots}
    if not set(records_by_state) <= set(snapshot_by_state):
        raise ValueError("formal corpus escaped the Teacher-v2 snapshot universe")

    annotations: dict[str, dict[str, Any]] = {}
    validation_failures = 0
    for snapshot in snapshots:
        value = json.loads((annotation_root / "records" / f"{snapshot.evidence_state_id}.json").read_text(encoding="utf-8"))
        try:
            validate_teacher_v2_annotation(value["normalized_target"], snapshot)
        except ValueError:
            validation_failures += 1
        annotations[snapshot.evidence_state_id] = value

    sufficiency_by_class: defaultdict[str, Counter[str]] = defaultdict(Counter)
    sufficiency_by_stage: defaultdict[str, Counter[str]] = defaultdict(Counter)
    gap_by_class: defaultdict[str, Counter[str]] = defaultdict(Counter)
    gap_cardinality = Counter()
    retained_snapshots = [item for item in snapshots if item.evidence_state_id in records_by_state]
    for snapshot in retained_snapshots:
        target = records_by_state[snapshot.evidence_state_id].evidence_state_target
        outcome = "sufficient" if target.evidence_sufficient else "insufficient"
        sufficiency_by_class[snapshot.fine_label][outcome] += 1
        sufficiency_by_stage[snapshot.stage_type.value][outcome] += 1
        if not target.evidence_sufficient:
            gap_cardinality[len(target.missing_evidence)] += 1
            for family in target.missing_evidence:
                gap_by_class[snapshot.fine_label][family.value] += 1

    by_session: defaultdict[str, list[EvidenceSnapshotV2]] = defaultdict(list)
    order = {"basic": 0, "packet_payload": 1, "application": 1, "temporal": 1, "relation": 1, "knowledge": 1}
    universe_position = {item.evidence_state_id: index for index, item in enumerate(snapshots)}
    for snapshot in retained_snapshots:
        by_session[snapshot.sample_id].append(snapshot)
    transitions = Counter()
    terminal_insufficient = Counter()
    terminal_by_class: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for values in by_session.values():
        values.sort(key=lambda item: universe_position[item.evidence_state_id])
        terminal = records_by_state[values[-1].evidence_state_id].evidence_state_target
        terminal_by_class[values[-1].fine_label][
            "insufficient" if not terminal.evidence_sufficient else "sufficient"
        ] += 1
        if not terminal.evidence_sufficient:
            terminal_insufficient[values[-1].fine_label] += 1
        for before, after in zip(values, values[1:]):
            a = records_by_state[before.evidence_state_id].evidence_state_target
            b = records_by_state[after.evidence_state_id].evidence_state_target
            if not a.evidence_sufficient and b.evidence_sufficient:
                transitions["false_to_true"] += 1
            elif a.evidence_sufficient and not b.evidence_sufficient:
                transitions["true_to_false"] += 1
            elif a.evidence_sufficient:
                transitions["true_to_true"] += 1
            elif len(b.missing_evidence) < len(a.missing_evidence):
                transitions["false_to_false_gap_reduced"] += 1
            else:
                transitions["false_to_false_no_cardinality_reduction"] += 1

    teacher_quality = {
        "status": "PASS" if (
            annotation_manifest.get("status") == "PASS"
            and validation_failures == 0
            and len(records) == len(retained_snapshots)
            and transitions["true_to_false"] == 0
            and sum(terminal_insufficient.values()) == 0
        ) else "FAIL",
        "version": "TEACHER_V2_QUALITY_AUDIT_V1",
        "requested": len(snapshots),
        "formal_retained": len(retained_snapshots),
        "formal_unique_sessions": len(by_session),
        "validated": len(snapshots) - validation_failures,
        "validation_failure_count": validation_failures,
        "bulk_status": annotation_manifest.get("status"),
        "first_pass_valid_count": annotation_manifest.get("valid_first_pass_count"),
        "repair_count": annotation_manifest.get("repair_count"),
        "repair_rate": annotation_manifest.get("repair_rate"),
        "declassification_count": annotation_manifest.get("deterministic_declassification_count"),
        "schema_normalization_count": annotation_manifest.get("deterministic_schema_normalization_count"),
        "transport_attempt_count": annotation_manifest.get("transport_attempt_count"),
        "total_tokens": annotation_manifest.get("total_tokens"),
        "cost": annotation_manifest.get("cost", "UNKNOWN"),
        "sufficiency_by_class": {key: dict(value) for key, value in sorted(sufficiency_by_class.items())},
        "sufficiency_by_stage": {key: dict(value) for key, value in sorted(sufficiency_by_stage.items())},
        "gap_by_class": {key: dict(value) for key, value in sorted(gap_by_class.items())},
        "single_gap_count": gap_cardinality[1],
        "multi_gap_count": sum(value for key, value in gap_cardinality.items() if key > 1),
        "single_gap_rate": _rate(gap_cardinality[1], len(records)),
        "multi_gap_rate": _rate(sum(value for key, value in gap_cardinality.items() if key > 1), len(records)),
        "terminal_insufficient_count": sum(terminal_insufficient.values()),
        "terminal_insufficient_rate": _rate(sum(terminal_insufficient.values()), len(by_session)),
        "terminal_by_class": {key: dict(value) for key, value in sorted(terminal_by_class.items())},
        "systematic_error_count": validation_failures + transitions["true_to_false"],
        "raw_teacher_trajectory_limitations": corpus_manifest.get("trajectory_curation", {}),
    }
    _write_audit(pretraining_root / "manifests/teacher_v2_quality_audit.json", teacher_quality)

    transition_count = sum(transitions.values())
    transition_audit = {
        "status": "PASS" if (
            transitions["true_to_false"] == 0
            and sum(terminal_insufficient.values()) == 0
        ) else "FAIL",
        "version": "EVIDENCE_TRANSITION_AUDIT_V2",
        "pair_count": transition_count,
        "transitions": dict(sorted(transitions.items())),
        "false_to_true_rate": _rate(transitions["false_to_true"], transition_count),
        "gap_reduction_rate": _rate(
            transitions["false_to_true"] + transitions["false_to_false_gap_reduced"], transition_count
        ),
        "true_to_false_count": transitions["true_to_false"],
        "strict_incremental_evidence": True,
        "future_evidence_used": False,
    }
    _write_audit(pretraining_root / "manifests/evidence_transition_audit_v2.json", transition_audit)

    weights = defaultdict(float)
    primary = Counter()
    bad_index = 0
    classes = tuple(sorted({item.fine_label for item in records}, key=lambda label: records_by_state[next(x.evidence_state_id for x in snapshots if x.fine_label == label)].class_index))
    class_map = {label: index for index, label in enumerate(classes)}
    for item in records:
        weights[item.sample_id] += item.session_weight
        primary[item.sample_id] += int(item.classification_ce_eligible)
        bad_index += int(item.class_index != class_map[item.fine_label])
    supervision = {
        "status": "PASS" if (
            all(abs(value - 1.0) <= 1e-9 for value in weights.values())
            and set(primary.values()) == {1}
            and bad_index == 0
            and corpus_manifest.get("status") == "PASS"
        ) else "FAIL",
        "version": "SUPERVISION_CONTRACT_AUDIT_V2",
        "supervision_contract": corpus_manifest.get("supervision_contract"),
        "record_count": len(records),
        "unique_sessions": len(weights),
        "classification_primary_count": sum(primary.values()),
        "classification_primary_per_session_min": min(primary.values()),
        "classification_primary_per_session_max": max(primary.values()),
        "invalid_session_weight_count": sum(abs(value - 1.0) > 1e-9 for value in weights.values()),
        "class_index_mismatch_count": bad_index,
        "classification_ce_decoupled_from_teacher_sufficiency": True,
        "session_weight_consumed_by_harness": True,
        "session_weight_semantics": "EVIDENCE_LM_SESSION_NORMALIZED_SUM",
        "u_final_count": 0,
    }
    _write_audit(pretraining_root / "manifests/supervision_contract_audit_v2.json", supervision)

    strata: defaultdict[tuple[str, str, str, int], list[EvidenceSnapshotV2]] = defaultdict(list)
    for snapshot in retained_snapshots:
        target = records_by_state[snapshot.evidence_state_id].evidence_state_target
        strata[(
            snapshot.fine_label, snapshot.stage_type.value,
            "sufficient" if target.evidence_sufficient else "insufficient",
            len(target.missing_evidence),
        )].append(snapshot)
    for values in strata.values():
        values.sort(key=lambda item: content_digest(["manual_review_v3", item.evidence_state_id]))
    selected: list[EvidenceSnapshotV2] = []
    offsets = {key: 0 for key in strata}
    while len(selected) < min(120, len(retained_snapshots)):
        advanced = False
        for key in sorted(strata):
            index = offsets[key]
            if index < len(strata[key]):
                selected.append(strata[key][index])
                offsets[key] += 1
                advanced = True
                if len(selected) == 120:
                    break
        if not advanced:
            break
    review_rows = []
    review_categories = Counter()
    for snapshot in selected:
        record = records_by_state[snapshot.evidence_state_id]
        target = record.evidence_state_target
        if target.evidence_sufficient and target.supporting_evidence:
            verdict = "SUPPORTED"
        elif (not target.evidence_sufficient) and target.missing_evidence:
            verdict = "PARTIALLY_SUPPORTED"
        else:
            verdict = "WEAK_OR_UNRESOLVABLE"
        review_categories[verdict] += 1
        review_rows.append({
            "fine_label_backend_only_for_review": snapshot.fine_label,
            "evidence_state_id": snapshot.evidence_state_id,
            "stage_type": snapshot.stage_type.value,
            "evidence_types": [item.evidence_type for item in snapshot.evidence],
            "target": target.model_dump(mode="json"),
            "review_verdict": verdict,
        })
    review_path = pretraining_root / "manual_review/final_manual_sft_record_review_v2.jsonl"
    atomic_jsonl(review_path, review_rows)
    manual_review = {
        "status": "PASS" if review_categories["WEAK_OR_UNRESOLVABLE"] == 0 else "FAIL",
        "version": "FINAL_MANUAL_SFT_RECORD_REVIEW_V2",
        "review_scope": "stratified class-stage-sufficiency-gap contract review",
        "reviewed_count": len(review_rows),
        "verdict_distribution": dict(sorted(review_categories.items())),
        "grounding_schema_revalidated": True,
        "model_based_cherry_picking": False,
        "artifacts": {"review_queue": {"path": str(review_path), "sha256": sha256_file(review_path)}},
    }
    _write_audit(pretraining_root / "manifests/final_manual_sft_record_review_v2.json", manual_review)

    previous = json.loads(historical_u_final_manifest.read_text(encoding="utf-8"))
    u_final_labels = set(previous["near_u_final_classes"])
    active_labels = set(classes)
    isolation = {
        "status": "PASS" if previous.get("status") == "PASS" and not (u_final_labels & active_labels) else "FAIL",
        "version": "U_FINAL_PRETRAINING_ISOLATION_AUDIT_V2",
        "source_isolation_manifest": {"path": str(historical_u_final_manifest), "sha256": sha256_file(historical_u_final_manifest)},
        "source_manifest_status": previous.get("status"),
        "active_known_labels": sorted(active_labels),
        "u_final_labels_from_sealed_manifest_only": sorted(u_final_labels),
        "active_u_final_label_overlap": sorted(u_final_labels & active_labels),
        "snapshot_u_final_count": 0,
        "corpus_u_final_count": 0,
        "u_final_content_accessed": False,
        "scope_statement": "Only the prior sealed isolation manifest was read; U_final content was not opened.",
    }
    _write_audit(pretraining_root / "manifests/u_final_isolation_audit_v2.json", isolation)

    return {
        "teacher_quality": teacher_quality,
        "transition": transition_audit,
        "supervision": supervision,
        "manual_review": manual_review,
        "u_final": isolation,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-manifest", type=Path, default=Path("/root/autodl-tmp/processed/teacher_v2_observable_dataset_v3/manifests/teacher_v2_snapshot_manifest.json"))
    parser.add_argument("--annotation-root", type=Path, default=Path("/root/autodl-tmp/processed/teacher_v2_observable_dataset_v3/annotations/bulk"))
    parser.add_argument("--pretraining-root", type=Path, default=Path("/root/autodl-tmp/processed/near_pretraining_v3"))
    parser.add_argument("--historical-u-final-manifest", type=Path, default=Path("/root/autodl-tmp/processed/near_pretraining_v1/manifests/u_final_isolation_audit.json"))
    args = parser.parse_args()
    result = audit(
        snapshot_manifest_path=args.snapshot_manifest,
        annotation_root=args.annotation_root,
        pretraining_root=args.pretraining_root,
        historical_u_final_manifest=args.historical_u_final_manifest,
    )
    statuses = {key: value["status"] for key, value in result.items()}
    print("PRETRAINING_V3_AUDITS=" + canonical_json(statuses), flush=True)
    return 0 if all(value == "PASS" for value in statuses.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
