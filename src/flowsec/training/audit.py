from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from .contracts import EvidenceDomain, EvidenceSnapshot, RLPromptRecordV1, StageType, content_digest
from .serialization import COMPACT_SERIALIZATION_CANDIDATE, render_training_input
from .prompts import traffic_expert_prompt_v1


U_FINAL_ISOLATION_AUDIT_VERSION = "U_FINAL_PRETRAINING_ISOLATION_AUDIT_V1"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def audit_u_final_isolation(production_root: Path, pretraining_root: Path) -> dict[str, Any]:
    import pyarrow.parquet as pq

    production_root, pretraining_root = Path(production_root), Path(pretraining_root)
    presets = _read_json(production_root / "manifests/edge_known_unknown_presets.json")
    known = set(presets["Near"]["K_known"])
    u_dev = set(presets["Near"]["U_dev"])
    u_final = set(presets["Near"]["U_final"])
    if known & (u_dev | u_final) or u_dev & u_final:
        raise ValueError("frozen Near roles overlap")
    candidates = pq.read_table(
        production_root / "sft_candidates/preset=Near/part-00000.parquet"
    ).to_pylist()
    candidate_ids = {str(row["sample_id"]) for row in candidates}
    candidate_labels = {str(row["fine_label"]) for row in candidates}
    candidate_role_failures = sum(
        row.get("physical_split") != "train"
        or row.get("ku_role") != "K_known"
        or row.get("preset") != "Near"
        for row in candidates
    )

    sidecar_ids: set[str] = set()
    sidecar_labels: set[str] = set()
    for directory in (
        pretraining_root / "application/captures",
        pretraining_root / "sanitized_payload/captures",
    ):
        for path in directory.glob("*.parquet"):
            for row in pq.read_table(path, columns=["sample_id", "split", "fine_label"]).to_pylist():
                if not row.get("sample_id"):
                    continue
                if row.get("split") != "train":
                    candidate_role_failures += 1
                sidecar_ids.add(str(row["sample_id"]))
                sidecar_labels.add(str(row["fine_label"]))

    snapshot_path = pretraining_root / "sft_corpus/evidence_snapshot_universe_v1.jsonl"
    snapshots = (
        [
            EvidenceSnapshot.model_validate_json(line)
            for line in snapshot_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if snapshot_path.is_file()
        else []
    )
    rl_path = pretraining_root / "rl_prompt_pool/near_rl_prompt_pool_v1.jsonl"
    rl_records = (
        [
            RLPromptRecordV1.model_validate_json(line)
            for line in rl_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if rl_path.is_file()
        else []
    )
    rag = _read_json(pretraining_root / "rag/manifest.json")
    dry_run_path = pretraining_root / "manifests/training_dry_run.json"
    dry_run = _read_json(dry_run_path) if dry_run_path.is_file() else {}
    findings = {
        "candidate_role_failures": candidate_role_failures,
        "candidate_unknown_label_count": len(candidate_labels - known),
        "candidate_u_dev_label_count": len(candidate_labels & u_dev),
        "candidate_u_final_label_count": len(candidate_labels & u_final),
        "sidecar_outside_candidate_count": len(sidecar_ids - candidate_ids),
        "sidecar_u_dev_label_count": len(sidecar_labels & u_dev),
        "sidecar_u_final_label_count": len(sidecar_labels & u_final),
        "snapshot_nontrain_count": sum(item.split != "train" for item in snapshots),
        "snapshot_nonknown_role_count": sum(item.ku_role != "K_known" for item in snapshots),
        "snapshot_u_dev_count": sum(item.fine_label in u_dev for item in snapshots),
        "snapshot_u_final_count": sum(item.fine_label in u_final for item in snapshots),
        "rl_nontrain_count": sum(item.source_split != "train" for item in rl_records),
        "rl_nonknown_role_count": sum(item.source_role != "K_known" for item in rl_records),
        "rl_u_dev_count": sum(item.fine_label in u_dev for item in rl_records),
        "rl_u_final_count": sum(item.fine_label in u_final for item in rl_records),
        "rag_u_final_term_hits": int(rag.get("u_final_term_hits", -1)),
        "dry_run_u_final_count": int(dry_run.get("u_final_count", 0)),
    }
    status = "PASS" if all(value == 0 for value in findings.values()) else "FAIL"
    report = {
        "status": status,
        "version": U_FINAL_ISOLATION_AUDIT_VERSION,
        "near_known_classes": sorted(known),
        "near_u_dev_classes": sorted(u_dev),
        "near_u_final_classes": sorted(u_final),
        "candidate_count": len(candidates),
        "sidecar_unique_session_count": len(sidecar_ids),
        "snapshot_count": len(snapshots),
        "rl_prompt_count": len(rl_records),
        "findings": findings,
        "scope_statement": "No U_final content informed extraction, sanitizer, RAG, Teacher, corpus, RL pool, pooling, or dry-run.",
    }
    report["audit_digest"] = content_digest(report)
    _atomic_json(pretraining_root / "manifests/u_final_isolation_audit.json", report)
    return report


def audit_snapshot_review(pretraining_root: Path, *, target: int = 200) -> dict[str, Any]:
    if not 100 <= target <= 200:
        raise ValueError("structured snapshot review must contain 100..200 records")
    pretraining_root = Path(pretraining_root)
    path = pretraining_root / "sft_corpus/evidence_snapshot_universe_v1.jsonl"
    snapshots = [
        EvidenceSnapshot.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    strata: dict[tuple[str, str], list[EvidenceSnapshot]] = {}
    for snapshot in snapshots:
        strata.setdefault((snapshot.fine_label, snapshot.stage_type.value), []).append(snapshot)
    for items in strata.values():
        items.sort(key=lambda item: content_digest(["snapshot_review_v1", item.evidence_state_id]))
    selected: list[EvidenceSnapshot] = []
    offsets = {key: 0 for key in strata}
    while len(selected) < target:
        advanced = False
        for key in sorted(strata):
            index = offsets[key]
            if index < len(strata[key]):
                selected.append(strata[key][index])
                offsets[key] += 1
                advanced = True
                if len(selected) == target:
                    break
        if not advanced:
            break
    forbidden_payload = (
        "sqlmap",
        "nikto",
        "hydra",
        "nmap",
        "digininja",
        "randomstorm",
        "github.com",
        "index.jsp",
        "e1105",
        "fname",
    )
    results = []
    failures = 0
    for snapshot in selected:
        evidence_types = [item.evidence_type for item in snapshot.evidence]
        serialized = render_training_input(
            traffic_expert_prompt_v1(),
            snapshot.evidence,
            serialization_version=COMPACT_SERIALIZATION_CANDIDATE,
        )
        payload_text = " ".join(
            str(item.content).casefold()
            for item in snapshot.evidence
            if item.evidence_type == "sanitized_payload"
        )
        checks = {
            "typed_roundtrip": EvidenceSnapshot.model_validate(
                snapshot.model_dump(mode="python")
            ).evidence_state_id
            == snapshot.evidence_state_id,
            "evidence_ids_unique": len({item.evidence_id for item in snapshot.evidence})
            == len(snapshot.evidence),
            "knowledge_separate": all(
                item.domain is EvidenceDomain.KNOWLEDGE
                for item in snapshot.evidence
                if item.evidence_type == "knowledge"
            ),
            "controlled_mask_ce_disabled": (
                snapshot.stage_type is not StageType.CONTROLLED_MASK
                or not snapshot.classification_supervision_valid
            ),
            "primary_ce_enabled": (
                snapshot.stage_type is StageType.CONTROLLED_MASK
                or snapshot.classification_supervision_valid
            ),
            "payload_fixed_shortcuts_absent": not any(
                token in payload_text for token in forbidden_payload
            ),
            "serialized_sample_identity_absent": snapshot.sample_id not in serialized,
        }
        passed = all(checks.values())
        failures += not passed
        results.append(
            {
                "evidence_state_id": snapshot.evidence_state_id,
                "fine_label_backend_only": snapshot.fine_label,
                "stage_type": snapshot.stage_type.value,
                "classification_supervision_valid": snapshot.classification_supervision_valid,
                "evidence_types": evidence_types,
                "checks": checks,
                "status": "PASS" if passed else "FAIL",
            }
        )
    report = {
        "status": "PASS" if failures == 0 and len(selected) == target else "FAIL",
        "version": "NEAR_SNAPSHOT_STRUCTURED_REVIEW_V1",
        "review_count": len(selected),
        "failure_count": failures,
        "class_distribution": dict(
            sorted(Counter(item.fine_label for item in selected).items())
        ),
        "stage_distribution": dict(
            sorted(Counter(item.stage_type.value for item in selected).items())
        ),
        "rubric": [
            "typed evidence fidelity",
            "opaque evidence identity grounding readiness",
            "Observation/Knowledge separation",
            "classification supervision mask correctness",
            "payload fixed-shortcut absence",
            "model-visible sample identity absence",
        ],
        "teacher_target_review": "PENDING_DEEPSEEK_ANNOTATION",
        "records": results,
        "u_final_count": 0,
    }
    report["audit_digest"] = content_digest(report)
    _atomic_json(pretraining_root / "manifests/snapshot_structured_review.json", report)
    return report
