#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flowsec.production.config import load_production_config
from flowsec.production.freeze import _edge_presets, _support_manifests, _training_manifests
from flowsec.production.manifests import ku_counts
from flowsec.production.readiness import (
    build_class_role_support_gate,
    validate_current_run_identity,
)
from flowsec.production.schema import content_hash
from flowsec.production.storage import ProductionCatalog, write_json


def _load(root: Path, name: str) -> dict[str, Any]:
    return json.loads((root / name).read_text(encoding="utf-8"))


def _prefix_failure_matrix(
    *,
    old_gate: dict[str, Any],
    old_edge_support: dict[str, Any],
) -> list[dict[str, Any]]:
    matrix: list[dict[str, Any]] = []
    for failure in old_gate.get("failures", []):
        dataset = str(failure.get("dataset", ""))
        preset = str(failure.get("preset", ""))
        if failure.get("code") == "PRESET_CLASS_SUPPORT_FAIL":
            for item in failure.get("K_known", []):
                for split in item.get("missing_splits", []):
                    matrix.append({
                        "dataset": dataset,
                        "preset": preset,
                        "label_space": "fine_label" if dataset == "Edge-IIoTset" else "coarse_label",
                        "class": item["class"],
                        "role": "K_known",
                        "physical_split": split,
                        "logical_partition": f"sft_{split}" if split != "test" else "closed_test",
                        "expected_minimum": 1,
                        "observed_count": 0,
                        "source_manifest": "production catalog + training asset manifest",
                        "gate_rule": "PREFIX implementation required every K_known class in every physical train/validation/test split",
                    })
        elif failure.get("code") == "U_FINAL_SUPPORT_QUERY_FAIL":
            classes = (
                old_edge_support.get("presets", {})
                .get(preset, {})
                .get("classes", {})
            )
            for label in failure.get("classes", []):
                entry = classes.get(label, {})
                for shot in entry.get("shots_requested", [1, 5, 10]):
                    shot_entry = entry.get(f"{shot}_shot", {})
                    if shot_entry.get("status") != "READY":
                        matrix.append({
                            "dataset": dataset,
                            "preset": preset,
                            "label_space": "fine_label",
                            "class": label,
                            "role": "U_final",
                            "physical_split": "test",
                            "logical_partition": f"final_unknown/{shot}_shot",
                            "expected_minimum": int(shot),
                            "observed_count": int(shot_entry.get("support_count", 0)),
                            "source_manifest": "edge_support_query_manifest.json",
                            "gate_rule": "PREFIX implementation coupled every registered shot variant to BASE readiness",
                        })
                if int(entry.get("query_count", 0)) == 0:
                    matrix.append({
                        "dataset": dataset,
                        "preset": preset,
                        "label_space": "fine_label",
                        "class": label,
                        "role": "U_final",
                        "physical_split": "test",
                        "logical_partition": "final_unknown/support_query",
                        "expected_minimum": 1,
                        "observed_count": 0,
                        "source_manifest": "edge_support_query_manifest.json",
                        "gate_rule": "PREFIX implementation coupled a non-empty few-shot query to BASE readiness",
                    })
    return matrix


def _copy_small_manifests(
    *,
    report_dir: Path,
    destinations: list[Path],
    names: list[str],
) -> None:
    for destination in destinations:
        destination.mkdir(parents=True, exist_ok=True)
        for name in names:
            shutil.copy2(report_dir / name, destination / name)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh class-role/support/readiness small manifests without rebuilding canonical data."
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--tracked-report-dir", type=Path)
    args = parser.parse_args()

    config = load_production_config(args.config)
    report_dir = args.report_dir.resolve()
    output_root = args.output_root.resolve()
    catalog = ProductionCatalog(output_root / "_state" / "production_catalog.sqlite")
    try:
        source_manifest = _load(report_dir, "source_checksum_manifest.json")
        statistics = _load(report_dir, "production_statistics.json")
        completion = json.loads(
            (output_root / "_state" / "completion.json").read_text(encoding="utf-8")
        )
        run_identity = validate_current_run_identity(
            catalog=catalog,
            config_hash=config.config_hash,
            source_manifest=source_manifest,
            statistics=statistics,
            completion=completion,
        )

        prefix_gate_path = report_dir / "class_role_support_gate_prefix_failure.json"
        prefix_matrix_path = report_dir / "class_role_support_failure_matrix_prefix.json"
        if prefix_gate_path.is_file() and prefix_matrix_path.is_file():
            prefix_matrix = json.loads(
                prefix_matrix_path.read_text(encoding="utf-8")
            ).get("matrix", [])
        else:
            old_gate = _load(report_dir, "class_role_support_gate.json")
            old_edge_support = _load(report_dir, "edge_support_query_manifest.json")
            prefix_matrix = _prefix_failure_matrix(
                old_gate=old_gate, old_edge_support=old_edge_support
            )
            write_json(prefix_gate_path, old_gate)
            write_json(
                prefix_matrix_path,
                {
                    "status": "PREFIX_FAILURE_CAPTURED",
                    "root_cause_classes": ["GATE_LOGIC_BUG", "MANIFEST_GENERATION_BUG"],
                    "matrix": prefix_matrix,
                },
            )

        edge_presets = _edge_presets(config, catalog)
        edge_support, iot_support = _support_manifests(config, catalog, edge_presets)
        edge_support_second, iot_support_second = _support_manifests(
            config, catalog, edge_presets
        )
        support_deterministic = (
            content_hash(edge_support) == content_hash(edge_support_second)
            and content_hash(iot_support) == content_hash(iot_support_second)
        )
        if not support_deterministic:
            raise ValueError("SMALL_MANIFEST_DETERMINISM_FAIL")
        run_identity["small_manifest_determinism"] = {
            "status": "PASS",
            "edge_support_hash": content_hash(edge_support),
            "iot23_support_hash": content_hash(iot_support),
            "method": "two independent in-memory generations from the validated current catalog",
        }
        training_edge, training_iot = _training_manifests(
            config=config,
            source_manifest=source_manifest,
            edge_presets=edge_presets,
        )
        iot_preset = {
            **config.iot23["known_unknown_preset"],
            "counts": {
                "K_known": ku_counts(
                    catalog=catalog, dataset=config.iot23["dataset_name"],
                    label_column="coarse_label",
                    labels=config.iot23["known_unknown_preset"]["k_known"],
                ),
                "U_dev": ku_counts(
                    catalog=catalog, dataset=config.iot23["dataset_name"],
                    label_column="coarse_label",
                    labels=config.iot23["known_unknown_preset"]["u_dev"],
                ),
                "U_final": ku_counts(
                    catalog=catalog, dataset=config.iot23["dataset_name"],
                    label_column="coarse_label",
                    labels=config.iot23["known_unknown_preset"]["u_final"],
                ),
            },
            "selection_rule": "native coarse hierarchy and official scenario metadata; no model outputs",
        }
        gate = build_class_role_support_gate(
            catalog=catalog,
            edge_dataset=config.edge["dataset_name"],
            edge_presets=edge_presets,
            edge_support=edge_support,
            edge_training=training_edge,
            iot_dataset=config.iot23["dataset_name"],
            iot_preset=iot_preset,
            iot_support=iot_support,
            iot_training=training_iot,
            run_identity=run_identity,
        )
    finally:
        catalog.close()

    gate["generated_at"] = datetime.now(timezone.utc).isoformat()
    values = {
        "edge_known_unknown_presets.json": edge_presets,
        "iot23_known_unknown_presets.json": iot_preset,
        "edge_support_query_manifest.json": edge_support,
        "iot23_support_query_manifest.json": iot_support,
        "training_asset_manifest_edge.json": training_edge,
        "training_asset_manifest_iot23.json": training_iot,
        "class_role_support_gate.json": gate,
    }
    for name, value in values.items():
        write_json(report_dir / name, value)

    readiness = _load(report_dir, "production_readiness.json")
    edge_base_ready = bool(gate["edge"]) and all(
        bool(value["base_production_ready"]) for value in gate["edge"].values()
    )
    iot_base_ready = bool(gate["iot23"]["base_production_ready"])
    readiness.update(
        {
            "SUPPORT_QUERY_FROZEN": bool(gate["FEW_SHOT_VARIANT_READY"]),
            "BASE_PRODUCTION_READY": bool(gate["BASE_PRODUCTION_READY"]),
            "FEW_SHOT_VARIANT_READY": bool(gate["FEW_SHOT_VARIANT_READY"]),
            "EDGE_SPLIT_SAFE": edge_base_ready,
            "IOT23_SPLIT_SAFE": iot_base_ready,
            "CLASS_ROLE_SUPPORT_GATE": gate["CLASS_ROLE_SUPPORT_GATE"],
            "POSTFIX_PRECOMMIT_AUDIT": "NOT_RUN",
            "PRODUCTION_DATA_READY": False,
            "DECISION_REQUIRED": True,
            "status": "INCOMPLETE",
            "QWEN_DOWNLOADED": False,
            "TRAINING_STARTED": False,
        }
    )
    write_json(report_dir / "production_readiness.json", readiness)
    completion["production_ready"] = False
    completion["readiness"] = {
        key: value
        for key, value in readiness.items()
        if key not in {"generated_at", "status", "limitations", "exact_next_action"}
    }
    write_json(output_root / "_state" / "completion.json", completion)

    names = list(values) + [
        "class_role_support_gate_prefix_failure.json",
        "class_role_support_failure_matrix_prefix.json",
        "production_readiness.json",
    ]
    destinations = [output_root / "manifests"]
    if args.tracked_report_dir is not None:
        destinations.append(args.tracked_report_dir.resolve())
    _copy_small_manifests(
        report_dir=report_dir, destinations=destinations, names=names
    )
    print(
        json.dumps(
            {
                "CLASS_ROLE_SUPPORT_GATE": gate["CLASS_ROLE_SUPPORT_GATE"],
                "BASE_PRODUCTION_READY": gate["BASE_PRODUCTION_READY"],
                "FEW_SHOT_VARIANT_READY": gate["FEW_SHOT_VARIANT_READY"],
                "prefix_failure_matrix": prefix_matrix,
                "run_identity": run_identity,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if gate["CLASS_ROLE_SUPPORT_GATE"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
