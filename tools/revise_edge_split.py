#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import resource
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flowsec.production.audits import build_leakage_audit
from flowsec.production.config import load_production_config
from flowsec.production.freeze import (
    _aggregate_counts,
    _edge_presets,
    _retention_breakdown,
    _support_manifests,
    _training_manifests,
)
from flowsec.production.label_provenance import (
    preflight_edge_captures,
    provenance_by_capture,
)
from flowsec.production.manifests import write_logical_assets
from flowsec.production.readiness import build_class_role_support_gate
from flowsec.production.sensitivity import build_evaluation_clean_variants
from flowsec.production.split_revision import (
    LOW_RESOURCE_STRESS_STATUS,
    SPLIT_POLICY_ID,
    build_low_resource_analysis,
    build_paper_readiness,
    build_revision_boundaries,
    build_sft_candidate_manifests,
    install_revision_overlay,
)
from flowsec.production.storage import ProductionCatalog, write_json


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _identity_digest(catalog: ProductionCatalog, dataset: str) -> dict[str, Any]:
    digest = hashlib.sha256()
    count = 0
    for (sample_id,) in catalog.connection.execute(
        "SELECT sample_id FROM records WHERE dataset=? ORDER BY sample_id", (dataset,)
    ):
        digest.update(str(sample_id).encode("utf-8"))
        digest.update(b"\n")
        count += 1
    distinct = int(
        catalog.scalar(
            "SELECT COUNT(DISTINCT sample_id) FROM records WHERE dataset=?", (dataset,)
        )
        or 0
    )
    return {
        "count": count,
        "distinct_sample_ids": distinct,
        "ordered_sample_id_sha256": digest.hexdigest(),
    }


def _copy_static_manifests(source: Path, destination: Path) -> list[str]:
    names = [
        "canonical_schema_v1.json",
        "edge_label_schema.json",
        "iot23_label_schema.json",
        "iot23_dataset_manifest.json",
        "iot23_split_manifest.json",
        "iot23_retention_audit.json",
        "model_feature_whitelist.json",
        "prohibited_model_fields.json",
        "anomaly_policy.json",
        "anomaly_manifest.json",
        "source_checksum_manifest.json",
        "edge_checkpoint_reuse_audit.json",
    ]
    copied: list[str] = []
    destination.mkdir(parents=True, exist_ok=True)
    for name in names:
        path = source / name
        if path.is_file():
            shutil.copy2(path, destination / name)
            copied.append(name)
    return copied


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Reassign Edge physical splits without packet/session reconstruction."
    )
    value.add_argument(
        "--config",
        type=Path,
        default=Path("configs/data/production_freeze_v1.yaml"),
    )
    value.add_argument(
        "--source-catalog",
        type=Path,
        default=Path(
            "/root/autodl-tmp/processed/production_data_freeze_v1/_state/"
            "production_catalog.sqlite"
        ),
    )
    value.add_argument(
        "--source-manifest-dir",
        type=Path,
        default=Path("/root/autodl-tmp/processed/production_data_freeze_v1/manifests"),
    )
    value.add_argument(
        "--edge-root",
        type=Path,
        default=Path(
            "/root/autodl-tmp/datasets/edge_iiotset/raw/Edge-IIoTset dataset"
        ),
    )
    value.add_argument(
        "--output-root",
        type=Path,
        default=Path("/root/autodl-tmp/processed/edge_split_revision_v2"),
    )
    value.add_argument(
        "--report-dir",
        type=Path,
        default=Path("/root/autodl-tmp/experiments/edge_split_revision_v2"),
    )
    value.add_argument("--selected-sft-plan", choices=("PLAN_A", "PLAN_B", "PLAN_C"), default="PLAN_B")
    value.add_argument("--force-empty-output", action="store_true")
    return value


def main() -> int:
    args = parser().parse_args()
    if not args.source_catalog.is_file():
        raise SystemExit(f"missing source catalog: {args.source_catalog}")
    for target in (args.output_root, args.report_dir):
        if target.exists() and any(target.iterdir()):
            if not args.force_empty_output:
                raise SystemExit(f"refusing non-empty output directory: {target}")
            raise SystemExit(
                "--force-empty-output never deletes files; provide fresh empty paths"
            )
        target.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    config = load_production_config(args.config)
    edge_dataset = str(config.edge["dataset_name"])
    source_manifest = _load(args.source_manifest_dir / "source_checksum_manifest.json")
    frozen_provenance = _load(
        args.source_manifest_dir / "edge_label_provenance_manifest.json"
    )
    expected_hashes = {
        str(item["capture_id"]): {
            "pcap_sha256": str(item["pcap_sha256"]),
            "companion_csv_sha256": str(item["companion_csv_sha256"]),
        }
        for item in frozen_provenance["captures"]
    }
    provenance_preflight = preflight_edge_captures(
        edge_config=config.edge,
        edge_root=args.edge_root,
        official_archive_verified=True,
        expected_hashes=expected_hashes,
    )
    if provenance_preflight["CAPTURE_PROVENANCE_GATE"] != "PASS":
        raise SystemExit("LABEL_PROVENANCE_FINAL_GATE=BLOCKED")
    provenance_totals = frozen_provenance.get("totals", {})
    provenance_safe = (
        frozen_provenance.get("CAPTURE_PROVENANCE_GATE") == "PASS"
        and int(provenance_totals.get("conflict_sessions", 0)) == 0
        and int(provenance_totals.get("unmatched_quarantine_sessions", 0)) == 0
    )
    if not provenance_safe:
        raise SystemExit("LABEL_PROVENANCE_FINAL_GATE=BLOCKED")

    catalog = ProductionCatalog(args.source_catalog)
    try:
        source_identity = _identity_digest(catalog, edge_dataset)
        current_presets = _edge_presets(config, catalog)
        current_paper = build_paper_readiness(
            catalog=catalog,
            dataset=edge_dataset,
            edge_presets=current_presets,
        )
        boundaries = build_revision_boundaries(
            catalog,
            dataset=edge_dataset,
            local_embargo_seconds=float(config.processing["fixed_gap_safety_seconds"]),
        )
        split_manifest = install_revision_overlay(
            catalog,
            dataset=edge_dataset,
            boundaries=boundaries,
            assignment_root=args.output_root / "split_assignments" / "Edge-IIoTset",
            compression=str(config.processing["parquet_compression"]),
            max_rows=int(config.processing["parquet_shard_rows"]),
        )
        revised_identity = _identity_digest(catalog, edge_dataset)
        identity_unchanged = source_identity == revised_identity
        if not identity_unchanged:
            raise RuntimeError("canonical session identity universe changed")

        edge_presets = _edge_presets(config, catalog)
        paper = build_paper_readiness(
            catalog=catalog,
            dataset=edge_dataset,
            edge_presets=edge_presets,
        )
        zero_improved = int(paper["zero_class_count"]) < int(
            current_paper["zero_class_count"]
        )
        critical_improved = int(paper["critical_low_class_count"]) < int(
            current_paper["critical_low_class_count"]
        )
        if (
            paper["PAPER_EVALUATION_READINESS_GATE"] != "PASS_WITH_LIMITATIONS"
            or not zero_improved
            or not critical_improved
        ):
            raise RuntimeError("PAPER_EVALUATION_READINESS_GATE=FAIL")

        asset_metadata, asset_counts = write_logical_assets(
            catalog=catalog,
            output_root=args.output_root,
            processing=config.processing,
            label_schema_ids={
                config.edge["dataset_name"]: config.edge["label_schema_id"],
                config.iot23["dataset_name"]: config.iot23["label_schema_id"],
            },
            edge_label_provenance=provenance_by_capture(frozen_provenance),
        )
        sensitivity = build_evaluation_clean_variants(
            catalog=catalog,
            output_root=args.output_root,
            processing=config.processing,
        )
        for variant_name, variant in sensitivity["variants"].items():
            key = f"sensitivity_{variant_name.lower()}_exclusion_ids"
            asset_metadata[key] = variant["exclusion_id_asset"]
            asset_counts[key] = int(variant["exclusion_id_asset"]["rows"])

        edge_support, iot_support = _support_manifests(config, catalog, edge_presets)
        edge_training, iot_training = _training_manifests(
            config=config,
            source_manifest=source_manifest,
            edge_presets=edge_presets,
        )
        iot_preset = {
            **config.iot23["known_unknown_preset"],
            "selection_rule": "unchanged frozen IoT-23 native taxonomy protocol",
        }
        class_role = build_class_role_support_gate(
            catalog=catalog,
            edge_dataset=edge_dataset,
            edge_presets=edge_presets,
            edge_support=edge_support,
            edge_training=edge_training,
            iot_dataset=str(config.iot23["dataset_name"]),
            iot_preset=iot_preset,
            iot_support=iot_support,
            iot_training=iot_training,
        )
        if class_role["CLASS_ROLE_SUPPORT_GATE"] != "PASS":
            raise RuntimeError("CLASS_ROLE_SUPPORT_GATE=FAIL")

        sft = build_sft_candidate_manifests(
            catalog=catalog,
            dataset=edge_dataset,
            edge_presets=edge_presets,
            output_root=args.output_root / "sft_candidates",
            selected_plan=args.selected_sft_plan,
            compression=str(config.processing["parquet_compression"]),
            max_rows=int(config.processing["parquet_shard_rows"]),
        )
        edge_counts = _aggregate_counts(catalog, edge_dataset)
        total_counts = {
            str(label): int(count)
            for label, count in catalog.query(
                "SELECT fine_label,COUNT(*) FROM records WHERE dataset=? GROUP BY fine_label",
                (edge_dataset,),
            )
        }
        low_resource = build_low_resource_analysis(
            paper_readiness=paper,
            coarse_mapping=dict(config.edge["coarse_mapping"]),
            total_counts=total_counts,
        )
        leakage = build_leakage_audit(
            catalog=catalog,
            projection_violations=asset_metadata.pop("_projection_violations"),
            edge_presets=edge_presets,
            iot_preset=iot_preset,
            support_manifests=[edge_support, iot_support],
            training_manifests=[edge_training, iot_training],
            source_manifest=source_manifest,
        )
        if not leakage["LEAKAGE_AUDIT_OK"]:
            raise RuntimeError("LEAKAGE_AUDIT=FAIL")

        elapsed = time.monotonic() - started
        report_values: dict[str, Any] = {
            "edge_split_manifest.json": {
                **split_manifest,
                "policy": SPLIT_POLICY_ID,
                "target_ratios": {"train": 0.70, "validation": 0.15, "test": 0.15},
                "safety": (
                    "complete-session crossing quarantine plus capture-local 5-second embargo"
                ),
                "context_scope": config.processing["context_scope"],
                "session_timeout_seconds": config.processing["session_timeout_seconds"],
            },
            "split_revision_comparison.json": {
                "old": current_paper,
                "new": paper,
                "zero_improved": zero_improved,
                "critical_low_improved": critical_improved,
            },
            "paper_evaluation_readiness.json": paper,
            "sft_candidate_manifest.json": sft,
            "low_resource_analysis.json": low_resource,
            "edge_known_unknown_presets.json": edge_presets,
            "edge_support_query_manifest.json": edge_support,
            "iot23_support_query_manifest.json": iot_support,
            "training_asset_manifest_edge.json": edge_training,
            "training_asset_manifest_iot23.json": iot_training,
            "class_role_support_gate.json": class_role,
            "evaluation_clean_sensitivity_manifest.json": sensitivity,
            "leakage_audit.json": leakage,
            "edge_retention_audit.json": _retention_breakdown(catalog, edge_dataset),
            "edge_label_provenance_manifest.json": frozen_provenance,
            "edge_label_provenance_final_gate.json": {
                "LABEL_PROVENANCE_FINAL_GATE": "PASS",
                "capture_gate": provenance_preflight,
                "session_assignment_methods": {
                    "DIRECT_EVIDENCE_UNANIMOUS_ONLY": int(
                        provenance_totals.get("direct_evidence_sessions", 0)
                    ),
                    "VERIFIED_CAPTURE_FALLBACK": int(
                        provenance_totals.get("verified_capture_fallback_sessions", 0)
                    ),
                    "LABEL_CONFLICT_QUARANTINE": int(
                        provenance_totals.get("conflict_sessions", 0)
                    ),
                    "UNMATCHED_PROVENANCE_QUARANTINE": int(
                        provenance_totals.get("unmatched_quarantine_sessions", 0)
                    ),
                },
            },
            "canonical_identity_universe.json": {
                "before": source_identity,
                "after": revised_identity,
                "unchanged": identity_unchanged,
                "source_catalog": str(args.source_catalog),
                "sessionization_reexecuted": False,
                "tshark_reexecuted": False,
            },
            "production_statistics.json": {
                "mode": "split_revision_only",
                "elapsed_seconds": elapsed,
                "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                "asset_counts": asset_counts,
                "asset_metadata": asset_metadata,
                "edge_counts": edge_counts,
            },
            "split_revision_completion.json": {
                "generated_at": _now(),
                "SPLIT_REVISION_STATUS": "PASS_WITH_LIMITATIONS",
                "SPLIT_REVISION_DESIGN": "PASS_FOR_REBUILD",
                "LABEL_PROVENANCE_FINAL_GATE": "PASS",
                "PAPER_EVALUATION_READINESS_GATE": paper[
                    "PAPER_EVALUATION_READINESS_GATE"
                ],
                "CLASS_ROLE_SUPPORT_GATE": class_role["CLASS_ROLE_SUPPORT_GATE"],
                "IDENTITY_CROSS_SPLIT_LEAKAGE": leakage[
                    "IDENTITY_CROSS_SPLIT_LEAKAGE"
                ],
                "U_FINAL_ISOLATION": (
                    "PASS"
                    if all(
                        item["status"] == "PASS"
                        for item in leakage["items"]
                        if item["id"] in {15, 16, 17}
                    )
                    else "FAIL"
                ),
                "selected_sft_plan": args.selected_sft_plan,
                "LOW_RESOURCE_STRESS_TEST_STATUS": LOW_RESOURCE_STRESS_STATUS,
                "QWEN_RUN": False,
                "SFT_RUN": False,
                "tshark_reexecuted": False,
                "canonical_reconstructed": False,
            },
        }
        args.report_dir.mkdir(parents=True, exist_ok=True)
        for name, value in report_values.items():
            write_json(args.report_dir / name, value)
        copied = _copy_static_manifests(
            args.source_manifest_dir, args.report_dir
        )
        output_manifests = args.output_root / "manifests"
        output_manifests.mkdir(parents=True, exist_ok=True)
        for path in args.report_dir.iterdir():
            if path.is_file():
                shutil.copy2(path, output_manifests / path.name)
        write_json(
            args.report_dir / "source_catalog_reference.json",
            {
                "source_catalog": str(args.source_catalog),
                "read_only_split_overlay": True,
                "static_manifests_copied": copied,
            },
        )
        shutil.copy2(
            args.report_dir / "source_catalog_reference.json",
            output_manifests / "source_catalog_reference.json",
        )
        print(json.dumps(report_values["split_revision_completion.json"], indent=2))
    finally:
        catalog.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
