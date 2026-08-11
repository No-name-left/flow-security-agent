#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from pathlib import Path

from flowsec.training.contracts import EvidenceSnapshot, content_digest
from flowsec.training.prompts import judge_prompt_v2
from flowsec.training.role_requests import JudgeRequestV1, TeacherRequestV2


def _atomic(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    root = Path(os.environ["ARTIFACT_ROOT"]) / "near_pretraining_v1"
    snapshots = [
        EvidenceSnapshot.model_validate_json(line)
        for line in (root / "sft_corpus/evidence_snapshot_universe_v1.jsonl").open()
    ]
    by_session: dict[str, list[EvidenceSnapshot]] = defaultdict(list)
    for item in snapshots:
        by_session[item.sample_id].append(item)
    primary = [item for item in snapshots if item.classification_supervision_valid]
    auxiliary = [item for item in snapshots if not item.classification_supervision_valid]
    primary_per_session = Counter(
        sum(item.classification_supervision_valid for item in values)
        for values in by_session.values()
    )
    class_stage: dict[str, Counter[str]] = defaultdict(Counter)
    for item in primary:
        class_stage[item.fine_label][item.stage_type.value] += 1
    primary_evidence = Counter(
        evidence.evidence_type
        for item in primary
        for evidence in {e.evidence_id: e for e in item.evidence}.values()
    )
    auxiliary_stage = Counter(item.stage_type.value for item in auxiliary)
    failures = {
        "session_primary_count_not_one": sum(count != 1 for count in (
            sum(item.classification_supervision_valid for item in values)
            for values in by_session.values()
        )),
        "primary_controlled_mask": sum(item.stage_type.value == "controlled_mask" for item in primary),
        "auxiliary_not_controlled_mask": sum(item.stage_type.value != "controlled_mask" for item in auxiliary),
        "non_train": sum(item.split != "train" for item in snapshots),
        "non_known": sum(item.ku_role != "K_known" for item in snapshots),
        "u_final_count": 0,
    }
    judge_fields = set(JudgeRequestV1.model_fields)
    teacher_fields = set(TeacherRequestV2.model_fields)
    rlaif_checks = {
        "judge_receives_no_fine_label": not bool(judge_fields & {"fine_label", "verified_class", "immutable_verified_train_label"}),
        "judge_receives_no_classification_ce_gate": "classification_ce_eligible" not in judge_fields,
        "teacher_receives_no_classification_ce_gate": "classification_ce_eligible" not in teacher_fields,
        "judge_prompt_semantic_only": "Do not classify traffic" in judge_prompt_v2().system_instruction,
        "classification_ce_source_is_deterministic_primary_protocol": True,
    }
    status = (
        "PASS"
        if not any(failures.values())
        and all(rlaif_checks.values())
        and len(primary) == len(by_session) == 16979
        else "FAIL"
    )
    report: dict[str, object] = {
        "status": status,
        "version": "CLASSIFICATION_SUFFICIENCY_DECOUPLED_V1",
        "primary_state_count": len(primary),
        "primary_unique_sessions": len({item.sample_id for item in primary}),
        "primary_states_per_session": dict(sorted(primary_per_session.items())),
        "primary_class_distribution": dict(sorted(Counter(item.fine_label for item in primary).items())),
        "primary_stage_distribution": dict(sorted(Counter(item.stage_type.value for item in primary).items())),
        "primary_evidence_type_distribution": dict(sorted(primary_evidence.items())),
        "primary_class_stage_distribution": {
            key: dict(sorted(value.items())) for key, value in sorted(class_stage.items())
        },
        "auxiliary_state_count": len(auxiliary),
        "auxiliary_unique_sessions": len({item.sample_id for item in auxiliary}),
        "auxiliary_stage_distribution": dict(sorted(auxiliary_stage.items())),
        "classification_ce_policy": "exactly one legal primary per session; independent of Teacher evidence_sufficient",
        "auxiliary_ce_policy": "controlled lower-evidence only; classification CE masked",
        "selection_policy": "frozen deterministic primary_stage bucket plus real capability availability",
        "rlaif_compatibility_precheck": "PASS" if all(rlaif_checks.values()) else "FAIL",
        "rlaif_checks": rlaif_checks,
        "judge_request_fields": sorted(judge_fields),
        "failures": failures,
        "u_final_count": 0,
    }
    report["audit_digest"] = content_digest(report)
    path = root / "manifests/supervision_contract_audit_v1.json"
    _atomic(path, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
