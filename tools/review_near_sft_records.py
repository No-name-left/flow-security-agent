#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from flowsec.training.contracts import (
    EvidenceSnapshot,
    SFTRecordV1,
    content_digest,
    validate_evidence_grounding,
)

_TOOL_COMMAND = re.compile(r"(?i)(?:CALL_PAYLOAD|CALL_RAG|REQUEST_TOOL|EXECUTE_TOOL)")


def _atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--accept-manual", action="store_true")
    args = parser.parse_args()
    root = Path(os.environ["ARTIFACT_ROOT"]) / "near_pretraining_v1"
    corpus_root = root / "sft_corpus/final"
    manifest = json.loads((corpus_root / "manifest.json").read_text())
    corpus = [
        SFTRecordV1.model_validate_json(line)
        for line in Path(manifest["artifacts"]["corpus"]["path"]).open()
    ]
    snapshots = {
        item.evidence_state_id: item
        for item in (
            EvidenceSnapshot.model_validate_json(line)
            for line in (root / "sft_corpus/evidence_snapshot_universe_v1.jsonl").open()
        )
    }
    strata: dict[tuple[str, str, bool, str], list[SFTRecordV1]] = defaultdict(list)
    for item in corpus:
        strata[(
            item.fine_label,
            item.state_role,
            item.evidence_state_target.evidence_sufficient,
            item.stage_type.value,
        )].append(item)
    for values in strata.values():
        values.sort(key=lambda item: content_digest(["final_manual_review_v1", item.evidence_state_id]))
    selected: list[SFTRecordV1] = []
    offsets = {key: 0 for key in strata}
    while len(selected) < min(100, len(corpus)):
        advanced = False
        for key in sorted(strata):
            index = offsets[key]
            if index < len(strata[key]):
                selected.append(strata[key][index])
                offsets[key] += 1
                advanced = True
                if len(selected) == 100:
                    break
        if not advanced:
            break

    failures: Counter[str] = Counter()
    queue: list[dict[str, Any]] = []
    evidence_presence: Counter[str] = Counter()
    for item in selected:
        snapshot = snapshots[item.evidence_state_id]
        try:
            validate_evidence_grounding(item.evidence_state_target, snapshot.evidence)
        except ValueError:
            failures["grounding"] += 1
        target_text = json.dumps(item.evidence_state_target.model_dump(mode="json"), sort_keys=True)
        if _TOOL_COMMAND.search(target_text):
            failures["tool_command"] += 1
        lowered = item.serialized_model_input.casefold()
        if any(token in lowered for token in (
            '"fine_label"', '"coarse_label"', '"sample_id"', '"split"',
            '"ku_role"', '"dataset_name"', '"capture_id"', '"source_path"'
        )):
            failures["model_input_backend_or_gt_key"] += 1
        if item.sample_id in item.serialized_model_input:
            failures["sample_identity"] += 1
        if item.classification_ce_eligible != (item.state_role == "primary"):
            failures["classification_gate"] += 1
        if item.state_role == "auxiliary" and item.evidence_state_target.evidence_sufficient:
            failures["auxiliary_sufficient"] += 1
        types = sorted({e.evidence_type for e in snapshot.evidence})
        evidence_presence.update(types)
        queue.append({
            "evidence_state_id": item.evidence_state_id,
            "fine_label_backend_only": item.fine_label,
            "class_index_backend_only": item.class_index,
            "state_role": item.state_role,
            "classification_ce_eligible": item.classification_ce_eligible,
            "stage": item.stage_type.value,
            "evidence_types": types,
            "input_preview": item.serialized_model_input[:500],
            "target": item.evidence_state_target.model_dump(mode="json"),
            "session_weight": item.session_weight,
        })
    coverage = {
        "known_class_count": len({item.fine_label for item in selected}),
        "state_roles": sorted({item.state_role for item in selected}),
        "sufficiency_values": sorted({item.evidence_state_target.evidence_sufficient for item in selected}),
        "stages": sorted({item.stage_type.value for item in selected}),
        "evidence_types": dict(sorted(evidence_presence.items())),
        "insufficient_primary_count": sum(
            item.state_role == "primary" and not item.evidence_state_target.evidence_sufficient
            for item in selected
        ),
        "auxiliary_masked_count": sum(
            item.state_role == "auxiliary" and not item.classification_ce_eligible
            for item in selected
        ),
    }
    coverage_pass = (
        coverage["known_class_count"] == 11
        and coverage["state_roles"] == ["auxiliary", "primary"]
        and coverage["sufficiency_values"] == [False, True]
        and all(name in coverage["evidence_types"] for name in ("application", "sanitized_payload", "knowledge"))
    )
    deterministic_pass = not failures and coverage_pass
    status = "PASS" if deterministic_pass and args.accept_manual else "PENDING_MANUAL_REVIEW" if deterministic_pass else "FAIL"
    queue_path = corpus_root / "manual_sft_record_review_queue_100.json"
    _atomic(queue_path, {"records": queue, "coverage": coverage, "u_final_count": 0})
    report = {
        "status": status,
        "version": "FINAL_MANUAL_SFT_RECORD_REVIEW_V1",
        "review_count": len(selected),
        "reviewer": "Codex scientific record review" if args.accept_manual else "PENDING",
        "review_questions": [
            "classification target is legal backend supervision",
            "GT/backend identity is absent from model input",
            "insufficient primary may retain classification CE",
            "controlled auxiliary masks classification CE",
            "Evidence State is grounded and gap is not a tool command",
            "Payload and Knowledge preserve Observation boundary",
            "target is scientifically coherent for visible evidence",
            "sequence remains within frozen bound",
        ],
        "deterministic_checks": "PASS" if deterministic_pass else "FAIL",
        "failure_counts": dict(sorted(failures.items())),
        "coverage": coverage,
        "sequence_overflow_count": manifest["token_lengths"]["overflow_count"],
        "queue_path": str(queue_path),
        "manual_acceptance_recorded": bool(args.accept_manual),
        "u_final_count": 0,
    }
    report["audit_digest"] = content_digest(report)
    _atomic(root / "manifests/final_manual_sft_record_review.json", report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if status == "PASS" else 2 if status == "PENDING_MANUAL_REVIEW" else 1


if __name__ == "__main__":
    raise SystemExit(main())
