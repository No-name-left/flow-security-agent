#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from flowsec.training.contracts import EvidenceSnapshot, TeacherAnnotationV1, content_digest


def _atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def _annotation(path: Path) -> TeacherAnnotationV1:
    value = json.loads(path.read_text(encoding="utf-8"))
    return TeacherAnnotationV1.model_validate(value["normalized_target"])


def main() -> int:
    root = Path(os.environ["ARTIFACT_ROOT"]) / "near_pretraining_v1"
    snapshots = [
        EvidenceSnapshot.model_validate_json(line)
        for line in (root / "sft_corpus/evidence_snapshot_universe_v1.jsonl").open()
    ]
    by_session: dict[str, list[EvidenceSnapshot]] = defaultdict(list)
    for item in snapshots:
        by_session[item.sample_id].append(item)
    record_root = root / "teacher_annotations/v3/bulk/records"
    evidence_audit = json.loads((root / "manifests/final_evidence_spotcheck.json").read_text())

    pairs: dict[str, list[dict[str, Any]]] = {"payload": [], "rag": []}
    knowledge_cited_as_observation = 0
    for values in by_session.values():
        primary = next((item for item in values if item.classification_supervision_valid), None)
        auxiliary = next((item for item in values if not item.classification_supervision_valid), None)
        if primary is None or auxiliary is None:
            continue
        types = {item.evidence_type for item in primary.evidence}
        kind = "payload" if "sanitized_payload" in types else "rag" if "knowledge" in types else None
        if kind is None:
            continue
        before_path = record_root / f"{auxiliary.evidence_state_id}.json"
        after_path = record_root / f"{primary.evidence_state_id}.json"
        if not before_path.is_file() or not after_path.is_file():
            continue
        before = _annotation(before_path)
        after = _annotation(after_path)
        new_ids = {
            item.evidence_id
            for item in primary.evidence
            if item.evidence_type in ({"sanitized_payload"} if kind == "payload" else {"knowledge"})
        }
        cited = {item.evidence_id for item in after.supporting_evidence}
        if kind == "rag":
            knowledge_cited_as_observation += len(new_ids & cited)
        before_gaps = {item.type.value for item in before.missing_evidence}
        after_gaps = {item.type.value for item in after.missing_evidence}
        marginal_value = (
            (not before.evidence_sufficient and after.evidence_sufficient)
            or after.gap_type != before.gap_type
            or after_gaps != before_gaps
            or bool(new_ids & cited)
            or after.behavior_summary != before.behavior_summary
        )
        pairs[kind].append({
            "sample_id_backend_only": primary.sample_id,
            "fine_label_backend_only": primary.fine_label,
            "before_state_id": auxiliary.evidence_state_id,
            "after_state_id": primary.evidence_state_id,
            "before_sufficient": before.evidence_sufficient,
            "after_sufficient": after.evidence_sufficient,
            "before_gap": before.gap_type.value,
            "after_gap": after.gap_type.value,
            "before_missing": sorted(before_gaps),
            "after_missing": sorted(after_gaps),
            "new_evidence_cited": bool(new_ids & cited),
            "marginal_value": marginal_value,
            "before_summary": before.behavior_summary,
            "after_summary": after.behavior_summary,
        })

    summary: dict[str, Any] = {}
    representatives: dict[str, list[dict[str, Any]]] = {}
    for kind, values in pairs.items():
        transitions = Counter(
            f"{str(item['before_sufficient']).lower()}->{str(item['after_sufficient']).lower()}"
            for item in values
        )
        marginal = sum(item["marginal_value"] for item in values)
        summary[kind] = {
            "pair_count": len(values),
            "sufficiency_transitions": dict(sorted(transitions.items())),
            "marginal_value_count": marginal,
            "marginal_value_rate": marginal / len(values) if values else 0,
            "new_evidence_cited_count": sum(item["new_evidence_cited"] for item in values),
        }
        ordered = sorted(values, key=lambda item: content_digest(["pair_review_v1", item["after_state_id"]]))
        representatives[kind] = ordered[:25]

    checks = {
        "payload_pairs_present": summary["payload"]["pair_count"] > 0,
        "rag_pairs_present": summary["rag"]["pair_count"] > 0,
        "payload_has_explainable_marginal_value": summary["payload"]["marginal_value_count"] > 0,
        "rag_has_explainable_marginal_value": summary["rag"]["marginal_value_count"] > 0,
        "knowledge_never_cited_as_observation": knowledge_cited_as_observation == 0,
        "rag_query_shortcut_audit_pass": evidence_audit.get("status") == "PASS",
        "rag_u_final_term_hits_zero": evidence_audit.get("checks", {}).get("rag_u_final_term_hits_zero") is True,
    }
    report = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "version": "PAYLOAD_RAG_GAP_PAIR_AUDIT_V1",
        "checks": checks,
        "summary": summary,
        "knowledge_cited_as_observation_count": knowledge_cited_as_observation,
        "representative_pairs": representatives,
        "u_final_count": 0,
    }
    report["audit_digest"] = content_digest(report)
    _atomic(root / "manifests/payload_rag_gap_pair_audit.json", report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
