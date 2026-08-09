from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flowsec.production.storage import ProductionCatalog, write_json


REQUIRED_BOOLEAN_GATES = (
    "EDGE_DEDUP_POLICY_SAFE",
    "EDGE_LABEL_PROVENANCE_SAFE",
    "EDGE_SESSIONIZATION_SAFE",
    "EDGE_SPLIT_SAFE",
    "EDGE_KU_SEMANTICS_SAFE",
    "IOT23_SPLIT_SAFE",
    "IOT23_KU_SAFE",
    "IOT23_SUPPORT_LABEL_SAFE",
    "U_FINAL_ISOLATION_PASS",
    "LEAKAGE_GATE_PASS",
    "DETERMINISM_GATE_PASS",
    "EXACT_EVAL_CLEAN_REGISTERED",
    "NEAR_EVAL_CLEAN_REGISTERED",
)


def _load(root: Path, name: str) -> dict[str, Any]:
    return json.loads((root / name).read_text(encoding="utf-8"))


def _split_counts(catalog: ProductionCatalog, dataset: str, label: str) -> dict[str, int]:
    return {
        str(split): int(count)
        for split, count in catalog.query(
            """
            SELECT base_split,COUNT(*)
            FROM records
            WHERE dataset=? AND fine_label=? AND retained=1
            GROUP BY base_split
            ORDER BY base_split
            """,
            (dataset, label),
        )
    }


def build_postfix_audit(
    *,
    report_dir: Path,
    catalog: ProductionCatalog,
) -> dict[str, Any]:
    readiness = _load(report_dir, "production_readiness.json")
    edge = _load(report_dir, "edge_dataset_manifest.json")
    iot = _load(report_dir, "iot23_dataset_manifest.json")
    retention = _load(report_dir, "edge_retention_audit.json")
    dedup = edge["deduplication"]
    leakage = _load(report_dir, "leakage_audit.json")
    sensitivity = _load(report_dir, "evaluation_clean_sensitivity_manifest.json")
    support = _load(report_dir, "class_role_support_gate.json")
    edge_ku = _load(report_dir, "edge_known_unknown_presets.json")
    iot_ku = _load(report_dir, "iot23_known_unknown_presets.json")
    iot_support = _load(report_dir, "iot23_support_query_manifest.json")
    statistics = _load(report_dir, "production_statistics.json")
    label_provenance = _load(report_dir, "edge_label_provenance_manifest.json")

    gates = {key: bool(readiness.get(key)) for key in REQUIRED_BOOLEAN_GATES}
    gates["IDENTITY_CROSS_SPLIT_LEAKAGE_ZERO"] = (
        int(readiness.get("IDENTITY_CROSS_SPLIT_LEAKAGE", -1)) == 0
    )
    gates["CLASS_ROLE_SUPPORT_GATE_PASS"] = (
        readiness.get("CLASS_ROLE_SUPPORT_GATE") == "PASS"
    )
    gate_pass = all(gates.values())
    status = "PASS_WITH_LIMITATIONS" if gate_pass else "BLOCKED"
    exact_variant = sensitivity["variants"]["EXACT_EVAL_CLEAN"]
    near_variant = sensitivity["variants"]["NEAR_EVAL_CLEAN"]
    iot_support_labels = sorted(
        label
        for preset in iot_support.get("presets", {}).values()
        for label in preset.get("classes", {})
    )
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "POSTFIX_PRECOMMIT_AUDIT": status,
        "status": status,
        "gate_pass": gate_pass,
        "gates": gates,
        "failed_gates": [key for key, value in gates.items() if not value],
        "deduplication": {
            "definition": dedup["policy"],
            "backend_identity_field": dedup["backend_identity_field"],
            "identity_duplicate_groups": dedup["identity_duplicate_groups"],
            "identity_duplicate_count": dedup["identity_duplicate_count"],
            "identity_label_conflict_groups": dedup["identity_label_conflict_groups"],
            "identity_label_conflict_count": dedup["identity_label_conflict_count"],
            "exact_model_view_collision_groups": dedup["exact_model_view_collision_groups"],
            "exact_model_view_collision_records": dedup["exact_model_view_collision_records"],
            "view_label_collision_groups": dedup["view_label_collision_groups"],
            "view_label_collision_count": dedup["view_label_collision_count"],
        },
        "edge": {
            "constructed": retention["constructed"],
            "retained": retention["retained"],
            "excluded": int(edge["counts_after_deduplication"]["excluded"]),
            "class_retention": retention["classes"],
            "DDoS_UDP_splits": _split_counts(catalog, edge["dataset"], "DDoS_UDP"),
            "retained_class_distribution": edge["counts_after_deduplication"]["fine_labels"],
            "label_provenance": {
                "CAPTURE_PROVENANCE_GATE": label_provenance["CAPTURE_PROVENANCE_GATE"],
                "LABEL_PROVENANCE_AUDIT_POSTFIX": label_provenance[
                    "LABEL_PROVENANCE_AUDIT_POSTFIX"
                ],
                "totals": label_provenance["totals"],
            },
        },
        "iot23": {
            "retained": int(iot["counts_after_deduplication"]["retained"]),
            "support_task_label_level": iot_support.get("task_label_level"),
            "support_labels": iot_support_labels,
            "exploitation_support_fixed": (
                iot_support.get("task_label_level") == "coarse_label"
                and iot_support_labels == ["Exploitation"]
            ),
        },
        "leakage": {
            "status": leakage["status"],
            "identity_cross_split_overlap": leakage["IDENTITY_CROSS_SPLIT_LEAKAGE"],
            "exact_view_cross_split_collision": leakage["EXACT_VIEW_CROSS_SPLIT_COLLISION"],
            "near_view_cross_split_collision": leakage["NEAR_VIEW_CROSS_SPLIT_COLLISION"],
            "future_context_violation": next(item["evidence"]["violations"] for item in leakage["items"] if item["id"] == 11),
            "cross_split_temporal_context_status": next(item["status"] for item in leakage["items"] if item["id"] == 12),
            "prohibited_model_fields_status": next(item["status"] for item in leakage["items"] if item["id"] == 6),
            "u_final_isolation_pass": bool(readiness["U_FINAL_ISOLATION_PASS"]),
        },
        "sensitivity": {
            "EXACT_EVAL_CLEAN": exact_variant,
            "NEAR_EVAL_CLEAN": near_variant,
            "SUPERSEDED_BEFORE_ANY_MODEL_RUN": sensitivity["superseded_variant"]["SUPERSEDED_BEFORE_ANY_MODEL_RUN"],
        },
        "readiness_support_gate": support,
        "role_freeze": {
            "edge_presets": {
                name: {key: preset[key] for key in ("K_known", "U_dev", "U_final")}
                for name, preset in edge_ku.items()
            },
            "iot23": {key: iot_ku[key] for key in ("k_known", "u_dev", "u_final")},
            "unchanged": True,
        },
        "determinism": _load(report_dir, "determinism_audit.json"),
        "resources": {
            "processed_bytes": int(statistics["final_output_bytes"]),
            "disk_remaining_bytes": int(statistics["disk_remaining_bytes"]),
        },
        "limitations": [
            "Exact and near Initial Model View collisions remain in Primary by design and are quantified by evaluation-clean sensitivity variants.",
            "Primary class imbalance and legitimate repeated attack behavior are retained; future training-size control belongs to a separate reproducible sampler.",
            "Edge attack classes are mostly single-capture, so no cross-attack-run generalization is claimed.",
        ],
        "QWEN_DOWNLOADED": False,
        "TRAINING_STARTED": False,
    }
    return result


def render_postfix_markdown(audit: dict[str, Any]) -> str:
    dedup = audit["deduplication"]
    edge = audit["edge"]
    leakage = audit["leakage"]
    lines = [
        "# Post-fix Pre-Commit Scientific Audit",
        "",
        f"- Verdict: **{audit['POSTFIX_PRECOMMIT_AUDIT']}**",
        f"- Backend identity duplicates removed: {dedup['identity_duplicate_count']}",
        f"- Backend identity label-conflict rows quarantined: {dedup['identity_label_conflict_count']}",
        f"- Exact model-view collision groups retained/audited: {dedup['exact_model_view_collision_groups']}",
        f"- Edge constructed / retained / excluded: {edge['constructed']} / {edge['retained']} / {edge['excluded']}",
        f"- Identity cross-split overlap: {leakage['identity_cross_split_overlap']}",
        f"- Exact / near view cross-split collisions: {leakage['exact_view_cross_split_collision']} / {leakage['near_view_cross_split_collision']}",
        f"- Class-role support gate: {audit['readiness_support_gate']['CLASS_ROLE_SUPPORT_GATE']}",
        f"- Determinism: {audit['determinism']['status']}",
        "",
        "## Failed gates",
        "",
    ]
    lines.extend(
        [f"- {gate}" for gate in audit["failed_gates"]]
        or ["- None"]
    )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in audit["limitations"])
    lines.append("")
    return "\n".join(lines)


def render_final_freeze_markdown(
    *,
    readiness: dict[str, Any],
    edge: dict[str, Any],
    iot: dict[str, Any],
    leakage: dict[str, Any],
    determinism: dict[str, Any],
    statistics: dict[str, Any],
) -> str:
    return "\n".join(
        [
            "# Production Data Freeze",
            "",
            f"- Status: **{readiness['status']}**",
            f"- PRODUCTION_DATA_READY: **{str(readiness['PRODUCTION_DATA_READY']).lower()}**",
            f"- CLASS_ROLE_SUPPORT_GATE: **{readiness['CLASS_ROLE_SUPPORT_GATE']}**",
            f"- Edge retained sessions: {edge['counts_after_deduplication']['retained']}",
            f"- IoT-23 retained sessions: {iot['counts_after_deduplication']['retained']}",
            f"- Leakage audit: {leakage['status']}",
            f"- Determinism audit: {determinism['status']}",
            f"- Elapsed: {statistics.get('cumulative_elapsed_seconds', statistics['elapsed_seconds']):.2f}s",
            f"- Peak RSS: {statistics.get('overall_peak_rss_kib', statistics['peak_rss_kib'])} KiB",
            f"- Output bytes: {statistics['final_output_bytes']}",
            "",
            "## Frozen decisions",
            "",
            "- CanonicalSessionRecord v1 with backend/model-safe/expandable layers.",
            "- PRIMARY_VIEW is the Gate-validated no-service view; derived service is diagnostic only.",
            "- Edge uses capture-internal chronological 70/15/15 blocks with data-derived gaps.",
            "- IoT-23 keeps scenario-held train/validation/test and one official Capture-3 class-held Unknown supplement.",
            "- U_final is excluded from normal loaders, SFT/development manifests, and known-only label-schema projection.",
            "- BASE class-role readiness is evaluated separately from registered few-shot variants.",
            "",
            "## Next action",
            "",
            readiness["exact_next_action"],
            "",
        ]
    )


def finalize_postfix_audit(
    *,
    report_dir: Path,
    output_root: Path,
    audit_dir: Path,
) -> dict[str, Any]:
    catalog = ProductionCatalog(output_root / "_state" / "production_catalog.sqlite")
    try:
        audit = build_postfix_audit(report_dir=report_dir, catalog=catalog)
    finally:
        catalog.close()
    audit_dir.mkdir(parents=True, exist_ok=True)
    write_json(audit_dir / "precommit_scientific_audit.json", audit)
    (audit_dir / "precommit_scientific_audit.md").write_text(
        render_postfix_markdown(audit), encoding="utf-8"
    )

    readiness_path = report_dir / "production_readiness.json"
    readiness = _load(report_dir, "production_readiness.json")
    ready = audit["POSTFIX_PRECOMMIT_AUDIT"] == "PASS_WITH_LIMITATIONS"
    readiness["POSTFIX_PRECOMMIT_AUDIT"] = audit["POSTFIX_PRECOMMIT_AUDIT"]
    readiness["PRODUCTION_DATA_READY"] = ready
    readiness["DECISION_REQUIRED"] = not ready
    readiness["status"] = "PASS_WITH_LIMITATIONS" if ready else "INCOMPLETE"
    readiness["QWEN_DOWNLOADED"] = False
    readiness["TRAINING_STARTED"] = False
    write_json(readiness_path, readiness)
    final_report_path = report_dir / "final_production_freeze_report.md"
    final_report_path.write_text(
        render_final_freeze_markdown(
            readiness=readiness,
            edge=_load(report_dir, "edge_dataset_manifest.json"),
            iot=_load(report_dir, "iot23_dataset_manifest.json"),
            leakage=_load(report_dir, "leakage_audit.json"),
            determinism=_load(report_dir, "determinism_audit.json"),
            statistics=_load(report_dir, "production_statistics.json"),
        ),
        encoding="utf-8",
    )

    current = {
        "status": "CURRENT" if ready else "NOT_READY",
        "output_root": str(output_root),
        "report_dir": str(report_dir),
        "postfix_audit": str(audit_dir),
        "supersedes": "superseded_overdedup_run",
        "PRODUCTION_DATA_READY": ready,
    }
    write_json(report_dir / "current_run.json", current)
    write_json(output_root / "_state" / "current_run.json", current)
    manifests = output_root / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    shutil.copy2(readiness_path, manifests / readiness_path.name)
    shutil.copy2(final_report_path, manifests / final_report_path.name)
    shutil.copy2(audit_dir / "precommit_scientific_audit.json", manifests / "postfix_precommit_scientific_audit.json")
    completion_path = output_root / "_state" / "completion.json"
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    completion["production_ready"] = ready
    completion["readiness"] = {
        key: value
        for key, value in readiness.items()
        if key not in {"generated_at", "status", "limitations", "exact_next_action"}
    }
    write_json(completion_path, completion)
    return audit
