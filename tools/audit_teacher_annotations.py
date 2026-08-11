#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

from flowsec.training.contracts import EvidenceSnapshot, TeacherAnnotationV1, content_digest
from flowsec.training.prompts import teacher_prompt_v3
from flowsec.training.teacher import select_teacher_pilot, validate_teacher_annotation

_TOOL_COMMAND = re.compile(r"(?i)(?:CALL_PAYLOAD|CALL_RAG|REQUEST_TOOL|EXECUTE_TOOL)")


def _atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def _cross_tab(
    rows: list[tuple[EvidenceSnapshot, dict[str, Any], TeacherAnnotationV1]],
    key: Callable[[EvidenceSnapshot], str],
) -> dict[str, dict[str, int]]:
    values: dict[str, Counter[str]] = defaultdict(Counter)
    for snapshot, _record, annotation in rows:
        values[key(snapshot)]["sufficient" if annotation.evidence_sufficient else "insufficient"] += 1
    return {name: dict(sorted(counts.items())) for name, counts in sorted(values.items())}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=("pilot", "bulk"), required=True)
    parser.add_argument("--manual-count", type=int, default=100)
    args = parser.parse_args()
    root = Path(os.environ["ARTIFACT_ROOT"]) / "near_pretraining_v1"
    snapshots = [
        EvidenceSnapshot.model_validate_json(line)
        for line in (root / "sft_corpus/evidence_snapshot_universe_v1.jsonl").open()
    ]
    if args.scope == "pilot":
        snapshots = select_teacher_pilot(snapshots, target=250)
    by_id = {item.evidence_state_id: item for item in snapshots}
    records_root = root / "teacher_annotations/v3" / args.scope / "records"
    records: dict[str, dict[str, Any]] = {}
    for path in records_root.glob("state_*.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        state_id = str(value.get("evidence_state_id"))
        if state_id in by_id and value.get("validation_result") == "PASS":
            records[state_id] = value

    prompt = teacher_prompt_v3()
    failure_types: Counter[str] = Counter()
    repair_count = 0
    input_tokens = 0
    output_tokens = 0
    latencies: list[float] = []
    valid: list[tuple[EvidenceSnapshot, dict[str, Any], TeacherAnnotationV1]] = []
    for state_id, snapshot in by_id.items():
        value = records.get(state_id)
        if value is None:
            failure_types["missing_annotation"] += 1
            continue
        if value.get("teacher_prompt_version") != prompt.version:
            failure_types["prompt_version_mismatch"] += 1
            continue
        if value.get("teacher_prompt_digest") != prompt.digest:
            failure_types["prompt_digest_mismatch"] += 1
            continue
        try:
            annotation = TeacherAnnotationV1.model_validate(value["normalized_target"])
            validate_teacher_annotation(annotation.model_dump(mode="json"), snapshot)
        except Exception as exc:
            failure_types[type(exc).__name__] += 1
            continue
        serialized = json.dumps(value["normalized_target"], sort_keys=True)
        if _TOOL_COMMAND.search(serialized):
            failure_types["tool_command_in_target"] += 1
            continue
        valid.append((snapshot, value, annotation))
        repair_count += bool(value.get("repair_used"))
        usage = value.get("token_usage") or {}
        input_tokens += int(usage.get("input_tokens") or 0)
        output_tokens += int(usage.get("output_tokens") or 0)
        latencies.append(float(value.get("latency_seconds") or 0))

    sufficient_count = sum(item[2].evidence_sufficient for item in valid)
    insufficient_count = len(valid) - sufficient_count
    primary = [item for item in valid if item[0].classification_supervision_valid]
    auxiliary = [item for item in valid if not item[0].classification_supervision_valid]
    rich_primary = [
        item for item in primary
        if len(item[0].evidence) > 1
        or item[0].stage_type.value in {"application", "payload", "knowledge", "packet", "temporal", "relation"}
    ]
    rich_primary_sufficient = sum(item[2].evidence_sufficient for item in rich_primary)
    controlled_sufficient = sum(item[2].evidence_sufficient for item in auxiliary)
    schema_grounding_pass = len(valid) == len(snapshots) and not failure_types
    calibration_pass = (
        bool(rich_primary)
        and rich_primary_sufficient > 0
        and insufficient_count > 0
        and controlled_sufficient == 0
    )

    strata: dict[tuple[str, str, bool, bool], list[tuple[EvidenceSnapshot, dict[str, Any], TeacherAnnotationV1]]] = defaultdict(list)
    for item in valid:
        snapshot, _value, annotation = item
        strata[(
            snapshot.fine_label,
            snapshot.stage_type.value,
            snapshot.classification_supervision_valid,
            annotation.evidence_sufficient,
        )].append(item)
    for values in strata.values():
        values.sort(key=lambda item: content_digest(["teacher_manual_v3", item[0].evidence_state_id]))
    queue: list[dict[str, Any]] = []
    offsets = {key: 0 for key in strata}
    while len(queue) < min(args.manual_count, len(valid)):
        advanced = False
        for key in sorted(strata):
            index = offsets[key]
            if index < len(strata[key]):
                snapshot, _value, annotation = strata[key][index]
                offsets[key] += 1
                advanced = True
                queue.append({
                    "evidence_state_id": snapshot.evidence_state_id,
                    "fine_label_backend_only": snapshot.fine_label,
                    "stage": snapshot.stage_type.value,
                    "state_role": "primary" if snapshot.classification_supervision_valid else "auxiliary",
                    "evidence_types": [item.evidence_type for item in snapshot.evidence],
                    "target": annotation.model_dump(mode="json"),
                })
                if len(queue) == args.manual_count:
                    break
        if not advanced:
            break
    queue_path = root / "teacher_annotations/v3" / args.scope / f"manual_review_stratified_{len(queue)}.json"
    _atomic(queue_path, {"records": queue, "u_final_count": 0})
    quarantine_ids = {
        path.stem
        for path in (root / "teacher_annotations/v3" / args.scope / "quarantine").glob("state_*.json")
    } & set(by_id)
    status = "PASS" if schema_grounding_pass and calibration_pass and not quarantine_ids else "FAIL"
    report = {
        "status": status,
        "version": "TEACHER_ANNOTATION_QUALITY_AUDIT_V2",
        "scope": args.scope,
        "teacher_prompt_version": prompt.version,
        "teacher_prompt_digest": prompt.digest,
        "expected": len(snapshots),
        "valid_count": len(valid),
        "valid_rate": len(valid) / len(snapshots) if snapshots else 0,
        "valid_first_pass_count": len(valid) - repair_count,
        "valid_first_pass_rate": (len(valid) - repair_count) / len(snapshots) if snapshots else 0,
        "repair_count": repair_count,
        "repair_rate": repair_count / len(snapshots) if snapshots else 0,
        "pending_annotation_count": len(snapshots) - len(valid),
        "quarantine_count": len(quarantine_ids),
        "quarantine_rate": len(quarantine_ids) / len(snapshots) if snapshots else 0,
        "failure_types": dict(sorted(failure_types.items())),
        "schema_grounding_status": "PASS" if schema_grounding_pass else "FAIL",
        "grounding_failure_count": sum(v for k, v in failure_types.items() if k in {"ValueError", "ValidationError"}),
        "unsupported_evidence_id_count": 0 if schema_grounding_pass else failure_types.get("ValueError", 0),
        "hallucination_rate": 0.0 if schema_grounding_pass else None,
        "prompt_injection_following_count": failure_types.get("tool_command_in_target", 0),
        "controlled_mask_sufficient_count": controlled_sufficient,
        "sufficiency_calibration_status": "PASS" if calibration_pass else "FAIL",
        "sufficiency_distribution": {"sufficient": sufficient_count, "insufficient": insufficient_count},
        "sufficiency_by_class": _cross_tab(valid, lambda item: item.fine_label),
        "sufficiency_by_stage": _cross_tab(valid, lambda item: item.stage_type.value),
        "sufficiency_by_evidence_type": _cross_tab(valid, lambda item: "+".join(sorted(e.evidence_type for e in item.evidence))),
        "sufficiency_by_primary_auxiliary": _cross_tab(valid, lambda item: "primary" if item.classification_supervision_valid else "auxiliary"),
        "rich_primary_count": len(rich_primary),
        "rich_primary_sufficient_count": rich_primary_sufficient,
        "rich_primary_sufficient_rate": rich_primary_sufficient / len(rich_primary) if rich_primary else 0,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "average_latency_seconds": sum(latencies) / len(latencies) if latencies else 0,
        "estimated_cost_usd_cache_miss_upper_bound": round(input_tokens / 1_000_000 * 0.14 + output_tokens / 1_000_000 * 0.28, 6),
        "manual_review_queue_count": len(queue),
        "manual_review_path": str(queue_path),
        "u_final_count": 0,
    }
    report["audit_digest"] = content_digest(report)
    _atomic(root / "manifests" / f"teacher_v3_{args.scope}_quality_audit.json", report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
