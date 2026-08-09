from __future__ import annotations

from typing import Any, Iterable

from flowsec.production.schema import content_hash
from flowsec.production.storage import ProductionCatalog


def _label_split_counts(
    catalog: ProductionCatalog,
    *,
    dataset: str,
    label_column: str,
    labels: Iterable[str],
    splits: Iterable[str],
) -> dict[str, dict[str, int]]:
    if label_column not in {"fine_label", "coarse_label"}:
        raise ValueError(label_column)
    output: dict[str, dict[str, int]] = {}
    for label in labels:
        output[str(label)] = {
            str(split): int(
                catalog.scalar(
                    f"""
                    SELECT COUNT(*) FROM records
                    WHERE dataset=? AND {label_column}=? AND base_split=? AND retained=1
                    """,
                    (dataset, label, split),
                )
                or 0
            )
            for split in splits
        }
    return output


def validate_current_run_identity(
    *,
    catalog: ProductionCatalog,
    config_hash: str,
    source_manifest: dict[str, Any],
    statistics: dict[str, Any],
    completion: dict[str, Any],
) -> dict[str, Any]:
    """Reject small-manifest refreshes against stale or mismatched run assets."""
    backend_records = int(catalog.scalar("SELECT COUNT(*) FROM records") or 0)
    canonical_sessions = int(
        catalog.scalar(
            "SELECT COUNT(*) FROM records WHERE retained=1 AND base_split!='quarantine'"
        )
        or 0
    )
    expected_source_hash = content_hash(source_manifest.get("files", []))
    asset_counts = statistics.get("asset_counts", {})
    checks = {
        "source_config_hash": source_manifest.get("config_hash") == config_hash,
        "completion_config_hash": completion.get("config_hash") == config_hash,
        "completion_source_manifest_hash": (
            completion.get("source_manifest_hash") == expected_source_hash
        ),
        "statistics_mode_full": statistics.get("mode") == "full",
        "completion_mode_full": completion.get("mode") == "full",
        "completion_selected_all": completion.get("selected_all") is True,
        "backend_record_count": int(asset_counts.get("backend_records", -1))
        == backend_records,
        "canonical_session_count": int(asset_counts.get("canonical_sessions", -1))
        == canonical_sessions,
    }
    failures = sorted(key for key, passed in checks.items() if not passed)
    if failures:
        raise ValueError("STALE_RUN_MANIFEST: " + ", ".join(failures))
    return {
        "status": "PASS",
        "config_hash": config_hash,
        "source_manifest_hash": expected_source_hash,
        "backend_records": backend_records,
        "canonical_sessions": canonical_sessions,
        "checks": checks,
    }


def _support_protocol(
    entry: dict[str, Any],
    *,
    registered_shots: Iterable[int],
) -> dict[str, Any]:
    registered = tuple(sorted(set(int(value) for value in registered_shots)))
    query_ids = [str(sample_id) for sample_id in entry.get("query_sample_ids", [])]
    query_unique = len(query_ids) == len(set(query_ids))
    hard_overlap_free = (
        int(entry.get("support_query_overlap", 0)) == 0
        and int(entry.get("support_query_exact_duplicate", 0)) == 0
        and int(entry.get("support_query_reverse_duplicate", 0)) == 0
    )
    variants: dict[str, Any] = {}
    all_registered_ready = bool(registered)
    for shot in (1, 5, 10):
        key = f"{shot}_shot"
        if shot not in registered:
            variants[key] = {
                "status": "NOT_REGISTERED",
                "support_count": 0,
                "expected_support_count": shot,
                "query_count": len(query_ids),
            }
            continue
        value = entry.get(key, {})
        support_ids = [str(sample_id) for sample_id in value.get("support_sample_ids", [])]
        unique_support = len(support_ids) == len(set(support_ids))
        sample_disjoint = not set(support_ids) & set(query_ids)
        ready = (
            value.get("status") == "READY"
            and len(support_ids) == shot
            and unique_support
            and sample_disjoint
            and query_unique
            and len(query_ids) > 0
            and hard_overlap_free
        )
        all_registered_ready = all_registered_ready and ready
        variants[key] = {
            "status": "READY" if ready else "NOT_READY",
            "manifest_status": value.get("status", "MISSING"),
            "support_count": len(support_ids),
            "expected_support_count": shot,
            "query_count": len(query_ids),
            "unique_support": unique_support,
            "support_query_disjoint": sample_disjoint,
        }
    requested_query = int(entry.get("query_cap_requested", len(query_ids)))
    warnings = []
    if len(query_ids) < requested_query:
        warnings.append(
            f"query capacity is {len(query_ids)}/{requested_query}; registered variants "
            "must still have a non-empty structurally disjoint query"
        )
    return {
        "status": "PASS" if all_registered_ready else "FAIL",
        "registered_shots": list(registered),
        "variants": variants,
        "query_unique": query_unique,
        "hard_signature_overlap_free": hard_overlap_free,
        "query_count": len(query_ids),
        "warnings": warnings,
    }


def _training_asset_contract(
    training: dict[str, Any],
    *,
    dataset: str,
    preset: str | None,
    role: str,
    split: str,
    label_key: str,
    labels: Iterable[str],
    ku_role: str,
    development_visible: bool,
    allowed_labels: Iterable[str],
) -> dict[str, Any]:
    matches = [
        asset
        for asset in training.get("assets", [])
        if asset.get("role") == role
        and (preset is None or asset.get("preset") == preset)
    ]
    expected_labels = sorted(str(label) for label in labels)
    errors: list[str] = []
    if training.get("dataset") != dataset:
        errors.append("dataset")
    if len(matches) != 1:
        errors.append("asset_cardinality")
        asset: dict[str, Any] = {}
    else:
        asset = matches[0]
    sample_ids = asset.get("sample_ids", {})
    filter_value = sample_ids.get("filter", {})
    if sample_ids.get("dataset") != dataset:
        errors.append("sample_id_dataset")
    if asset.get("split") != split or filter_value.get("split") != split:
        errors.append("split")
    if set(filter_value) != {"split", label_key}:
        errors.append("label_space")
    if sorted(str(value) for value in filter_value.get(label_key, [])) != expected_labels:
        errors.append("filter_labels")
    if sorted(str(value) for value in asset.get("allowed_labels", [])) != sorted(
        str(value) for value in allowed_labels
    ):
        errors.append("allowed_labels")
    if asset.get("ku_role") != ku_role:
        errors.append("ku_role")
    if asset.get("development_visible") is not development_visible:
        errors.append("development_visibility")
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": sorted(set(errors)),
        "role": role,
        "split": split,
        "label_key": label_key,
        "labels": expected_labels,
    }


def _development_leaks(
    training: dict[str, Any],
    *,
    preset: str | None,
    label_key: str,
    forbidden_labels: Iterable[str],
) -> list[dict[str, Any]]:
    forbidden = set(str(label) for label in forbidden_labels)
    leaks: list[dict[str, Any]] = []
    for asset in training.get("assets", []):
        if preset is not None and asset.get("preset") != preset:
            continue
        if asset.get("development_visible") is not True:
            continue
        filter_labels = set(
            str(label)
            for label in asset.get("sample_ids", {}).get("filter", {}).get(label_key, [])
        )
        allowed_labels = set(str(label) for label in asset.get("allowed_labels", []))
        overlap = sorted(forbidden & (filter_labels | allowed_labels))
        if overlap:
            leaks.append({"role": asset.get("role"), "labels": overlap})
    return leaks


def _matrix_row(
    *,
    dataset: str,
    preset: str,
    label_space: str,
    label: str,
    role: str,
    physical_split: str,
    logical_partition: str,
    expected_minimum: int,
    observed_count: int,
    source_manifest: str,
    gate_rule: str,
    hard_for_base: bool,
    logical_status: str,
) -> dict[str, Any]:
    count_ok = observed_count >= expected_minimum
    passed = count_ok and logical_status == "PASS"
    status = "PASS" if passed else ("FAIL" if hard_for_base else "LIMITATION")
    return {
        "dataset": dataset,
        "preset": preset,
        "label_space": label_space,
        "class": label,
        "role": role,
        "physical_split": physical_split,
        "logical_partition": logical_partition,
        "expected_minimum": expected_minimum,
        "observed_count": observed_count,
        "source_manifest": source_manifest,
        "gate_rule": gate_rule,
        "hard_for_base": hard_for_base,
        "logical_manifest_status": logical_status,
        "status": status,
    }


def build_class_role_support_gate(
    *,
    catalog: ProductionCatalog,
    edge_dataset: str,
    edge_presets: dict[str, Any],
    edge_support: dict[str, Any],
    edge_training: dict[str, Any],
    iot_dataset: str,
    iot_preset: dict[str, Any],
    iot_support: dict[str, Any],
    iot_training: dict[str, Any],
    run_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    variant_failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    matrix: list[dict[str, Any]] = []
    edge_results: dict[str, Any] = {}
    edge_support_presets = edge_support.get("presets", {})

    for preset_name, preset in edge_presets.items():
        known = _label_split_counts(
            catalog,
            dataset=edge_dataset,
            label_column="fine_label",
            labels=preset["K_known"],
            splits=("train", "validation", "test"),
        )
        udev = _label_split_counts(
            catalog,
            dataset=edge_dataset,
            label_column="fine_label",
            labels=preset["U_dev"],
            splits=("validation",),
        )
        ufinal_counts = _label_split_counts(
            catalog,
            dataset=edge_dataset,
            label_column="fine_label",
            labels=preset["U_final"],
            splits=("test",),
        )
        contracts = {
            "sft_train": _training_asset_contract(
                edge_training, dataset=edge_dataset, preset=preset_name,
                role="sft_train", split="train", label_key="fine_label_in",
                labels=preset["K_known"], ku_role="K_known",
                development_visible=True, allowed_labels=preset["K_known"],
            ),
            "sft_validation": _training_asset_contract(
                edge_training, dataset=edge_dataset, preset=preset_name,
                role="sft_validation", split="validation", label_key="fine_label_in",
                labels=preset["K_known"], ku_role="K_known",
                development_visible=True, allowed_labels=preset["K_known"],
            ),
            "closed_test": _training_asset_contract(
                edge_training, dataset=edge_dataset, preset=preset_name,
                role="closed_test", split="test", label_key="fine_label_in",
                labels=preset["K_known"], ku_role="K_known",
                development_visible=False, allowed_labels=preset["K_known"],
            ),
            "unknown_development": _training_asset_contract(
                edge_training, dataset=edge_dataset, preset=preset_name,
                role="unknown_development", split="validation", label_key="fine_label_in",
                labels=preset["U_dev"], ku_role="U_dev",
                development_visible=True, allowed_labels=[],
            ),
            "final_unknown": _training_asset_contract(
                edge_training, dataset=edge_dataset, preset=preset_name,
                role="final_unknown", split="test", label_key="fine_label_in",
                labels=preset["U_final"], ku_role="U_final",
                development_visible=False, allowed_labels=[],
            ),
        }
        for role, contract in contracts.items():
            if contract["status"] != "PASS":
                failures.append({
                    "code": "LOGICAL_MANIFEST_ROLE_FAIL",
                    "dataset": edge_dataset,
                    "preset": preset_name,
                    "logical_partition": role,
                    "errors": contract["errors"],
                })
        leaks = _development_leaks(
            edge_training,
            preset=preset_name,
            label_key="fine_label_in",
            forbidden_labels=preset["U_final"],
        )
        if leaks:
            failures.append({
                "code": "U_FINAL_DEVELOPMENT_LEAK",
                "dataset": edge_dataset,
                "preset": preset_name,
                "leaks": leaks,
            })

        for label, counts in known.items():
            for split, logical, minimum, hard, rule in (
                ("train", "sft_train", 1, True, "BASE: each K_known class has legal training support"),
                ("validation", "sft_validation", 1, False, "VARIANT: per-class validation support; not a BASE hard constraint"),
                ("test", "closed_test", 1, True, "BASE: each K_known class has closed-evaluation support"),
            ):
                row = _matrix_row(
                    dataset=edge_dataset, preset=preset_name, label_space="fine_label",
                    label=label, role="K_known", physical_split=split,
                    logical_partition=logical, expected_minimum=minimum,
                    observed_count=counts[split],
                    source_manifest="production catalog + training_asset_manifest_edge.json",
                    gate_rule=rule, hard_for_base=hard,
                    logical_status=contracts[logical]["status"],
                )
                matrix.append(row)
                if row["status"] == "FAIL":
                    failures.append({"code": "K_KNOWN_SUPPORT_FAIL", **row})
                elif row["status"] == "LIMITATION":
                    warnings.append({"code": "K_KNOWN_VALIDATION_LIMITATION", **row})

        for label, counts in udev.items():
            row = _matrix_row(
                dataset=edge_dataset, preset=preset_name, label_space="fine_label",
                label=label, role="U_dev", physical_split="validation",
                logical_partition="unknown_development", expected_minimum=1,
                observed_count=counts["validation"],
                source_manifest="production catalog + training_asset_manifest_edge.json",
                gate_rule="BASE: each U_dev class has development evidence and is not K supervision",
                hard_for_base=True,
                logical_status=contracts["unknown_development"]["status"],
            )
            matrix.append(row)
            if row["status"] == "FAIL":
                failures.append({"code": "U_DEV_SUPPORT_FAIL", **row})

        support_classes = edge_support_presets.get(preset_name, {}).get("classes", {})
        ufinal: dict[str, Any] = {}
        for label, counts in ufinal_counts.items():
            isolation_status = "PASS" if not leaks else "FAIL"
            logical_status = (
                "PASS"
                if contracts["final_unknown"]["status"] == "PASS"
                and isolation_status == "PASS"
                else "FAIL"
            )
            row = _matrix_row(
                dataset=edge_dataset, preset=preset_name, label_space="fine_label",
                label=label, role="U_final", physical_split="test",
                logical_partition="final_unknown", expected_minimum=1,
                observed_count=counts["test"],
                source_manifest=(
                    "production catalog + training_asset_manifest_edge.json + "
                    "edge_support_query_manifest.json"
                ),
                gate_rule="BASE: final-evaluation evidence exists and development visibility is excluded",
                hard_for_base=True, logical_status=logical_status,
            )
            matrix.append(row)
            if row["status"] == "FAIL":
                failures.append({"code": "U_FINAL_EVALUATION_SUPPORT_FAIL", **row})
            protocol = _support_protocol(
                support_classes.get(label, {}), registered_shots=(1, 5, 10)
            )
            protocol["physical_test_count"] = counts["test"]
            protocol["development_isolation"] = isolation_status
            ufinal[label] = protocol
            if protocol["status"] != "PASS":
                variant_failures.append({
                    "code": "FEW_SHOT_VARIANT_NOT_READY",
                    "dataset": edge_dataset,
                    "preset": preset_name,
                    "class": label,
                    "variants": protocol["variants"],
                })
            for warning in protocol["warnings"]:
                warnings.append({
                    "dataset": edge_dataset, "preset": preset_name,
                    "class": label, "warning": warning,
                })
        preset_failures = [
            item for item in failures
            if item.get("dataset") == edge_dataset and item.get("preset") == preset_name
        ]
        preset_variant_failures = [
            item for item in variant_failures
            if item.get("dataset") == edge_dataset and item.get("preset") == preset_name
        ]
        edge_results[preset_name] = {
            "K_known": known,
            "U_dev": udev,
            "U_final": ufinal,
            "development_isolation": "PASS" if not leaks else "FAIL",
            "status": "PASS" if not preset_failures else "FAIL",
            "base_production_ready": not preset_failures,
            "few_shot_variant_ready": not preset_variant_failures,
        }

    iot_preset_id = str(iot_preset["id"])
    iot_known = _label_split_counts(
        catalog, dataset=iot_dataset, label_column="coarse_label",
        labels=iot_preset["k_known"], splits=("train", "validation", "test"),
    )
    iot_udev = _label_split_counts(
        catalog, dataset=iot_dataset, label_column="coarse_label",
        labels=iot_preset["u_dev"], splits=("unknown_dev",),
    )
    iot_ufinal_counts = _label_split_counts(
        catalog, dataset=iot_dataset, label_column="coarse_label",
        labels=iot_preset["u_final"], splits=("unknown_final",),
    )
    iot_contracts = {
        "sft_train": _training_asset_contract(
            iot_training, dataset=iot_dataset, preset=None, role="sft_train",
            split="train", label_key="coarse_label_in", labels=iot_preset["k_known"],
            ku_role="K_known", development_visible=True,
            allowed_labels=iot_preset["k_known"],
        ),
        "sft_validation": _training_asset_contract(
            iot_training, dataset=iot_dataset, preset=None, role="sft_validation",
            split="validation", label_key="coarse_label_in", labels=iot_preset["k_known"],
            ku_role="K_known", development_visible=True,
            allowed_labels=iot_preset["k_known"],
        ),
        "scenario_held_closed_test": _training_asset_contract(
            iot_training, dataset=iot_dataset, preset=None,
            role="scenario_held_closed_test", split="test",
            label_key="coarse_label_in", labels=iot_preset["k_known"],
            ku_role="K_known", development_visible=False,
            allowed_labels=iot_preset["k_known"],
        ),
        "unknown_development": _training_asset_contract(
            iot_training, dataset=iot_dataset, preset=None,
            role="unknown_development", split="unknown_dev",
            label_key="coarse_label_in", labels=iot_preset["u_dev"],
            ku_role="U_dev", development_visible=True, allowed_labels=[],
        ),
        "final_unknown": _training_asset_contract(
            iot_training, dataset=iot_dataset, preset=None, role="final_unknown",
            split="unknown_final", label_key="coarse_label_in",
            labels=iot_preset["u_final"], ku_role="U_final",
            development_visible=False, allowed_labels=[],
        ),
    }
    for role, contract in iot_contracts.items():
        if contract["status"] != "PASS":
            failures.append({
                "code": "LOGICAL_MANIFEST_ROLE_FAIL", "dataset": iot_dataset,
                "preset": iot_preset_id, "logical_partition": role,
                "errors": contract["errors"],
            })
    iot_leaks = _development_leaks(
        iot_training, preset=None, label_key="coarse_label_in",
        forbidden_labels=iot_preset["u_final"],
    )
    if iot_leaks:
        failures.append({
            "code": "U_FINAL_DEVELOPMENT_LEAK", "dataset": iot_dataset,
            "preset": iot_preset_id, "leaks": iot_leaks,
        })
    if iot_training.get("task_label_level") != "coarse_label":
        failures.append({
            "code": "CANONICAL_LABEL_SPACE_FAIL", "dataset": iot_dataset,
            "preset": iot_preset_id, "expected": "coarse_label",
            "observed": iot_training.get("task_label_level"),
        })
    if iot_support.get("task_label_level") != "coarse_label":
        failures.append({
            "code": "CANONICAL_LABEL_SPACE_FAIL", "dataset": iot_dataset,
            "preset": iot_preset_id, "source_manifest": "iot23_support_query_manifest.json",
            "expected": "coarse_label", "observed": iot_support.get("task_label_level"),
        })

    for label, counts in iot_known.items():
        for split, logical in (
            ("train", "sft_train"),
            ("validation", "sft_validation"),
            ("test", "scenario_held_closed_test"),
        ):
            row = _matrix_row(
                dataset=iot_dataset, preset=iot_preset_id, label_space="coarse_label",
                label=label, role="K_known", physical_split=split,
                logical_partition=logical, expected_minimum=1,
                observed_count=counts[split],
                source_manifest="production catalog + training_asset_manifest_iot23.json",
                gate_rule="BASE: scenario-held K_known partition has legal coarse-label support",
                hard_for_base=True, logical_status=iot_contracts[logical]["status"],
            )
            matrix.append(row)
            if row["status"] == "FAIL":
                failures.append({"code": "K_KNOWN_SUPPORT_FAIL", **row})
    for label, counts in iot_udev.items():
        row = _matrix_row(
            dataset=iot_dataset, preset=iot_preset_id, label_space="coarse_label",
            label=label, role="U_dev", physical_split="unknown_dev",
            logical_partition="unknown_development", expected_minimum=1,
            observed_count=counts["unknown_dev"],
            source_manifest="production catalog + training_asset_manifest_iot23.json",
            gate_rule="BASE: formal coarse U_dev has unknown-development support",
            hard_for_base=True,
            logical_status=iot_contracts["unknown_development"]["status"],
        )
        matrix.append(row)
        if row["status"] == "FAIL":
            failures.append({"code": "U_DEV_SUPPORT_FAIL", **row})

    iot_support_classes = (
        iot_support.get("presets", {}).get(iot_preset_id, {}).get("classes", {})
    )
    iot_ufinal: dict[str, Any] = {}
    for label, counts in iot_ufinal_counts.items():
        isolation_status = "PASS" if not iot_leaks else "FAIL"
        logical_status = (
            "PASS"
            if iot_contracts["final_unknown"]["status"] == "PASS"
            and isolation_status == "PASS"
            else "FAIL"
        )
        row = _matrix_row(
            dataset=iot_dataset, preset=iot_preset_id, label_space="coarse_label",
            label=label, role="U_final", physical_split="unknown_final",
            logical_partition="final_unknown", expected_minimum=1,
            observed_count=counts["unknown_final"],
            source_manifest=(
                "production catalog + training_asset_manifest_iot23.json + "
                "iot23_support_query_manifest.json"
            ),
            gate_rule="BASE: formal coarse U_final evaluation exists and is development-isolated",
            hard_for_base=True, logical_status=logical_status,
        )
        matrix.append(row)
        if row["status"] == "FAIL":
            failures.append({"code": "U_FINAL_EVALUATION_SUPPORT_FAIL", **row})
        protocol = _support_protocol(
            iot_support_classes.get(label, {}), registered_shots=(1, 5)
        )
        protocol["physical_unknown_final_count"] = counts["unknown_final"]
        protocol["development_isolation"] = isolation_status
        iot_ufinal[label] = protocol
        if protocol["status"] != "PASS":
            variant_failures.append({
                "code": "FEW_SHOT_VARIANT_NOT_READY", "dataset": iot_dataset,
                "preset": iot_preset_id, "class": label,
                "variants": protocol["variants"],
            })
        for warning in protocol["warnings"]:
            warnings.append({
                "dataset": iot_dataset, "preset": iot_preset_id,
                "class": label, "warning": warning,
            })

    iot_failures = [item for item in failures if item.get("dataset") == iot_dataset]
    iot_variant_failures = [
        item for item in variant_failures if item.get("dataset") == iot_dataset
    ]
    base_ready = not failures
    few_shot_ready = not variant_failures
    return {
        "status": "PASS" if base_ready else "FAIL",
        "CLASS_ROLE_SUPPORT_GATE": "PASS" if base_ready else "FAIL",
        "BASE_PRODUCTION_READY": base_ready,
        "FEW_SHOT_VARIANT_READY": few_shot_ready,
        "minimum_rules": {
            "Edge.K_known.train": {"minimum": 1, "hard_for_base": True},
            "Edge.K_known.validation": {"minimum": 1, "hard_for_base": False},
            "Edge.K_known.test": {"minimum": 1, "hard_for_base": True},
            "Edge.U_dev.validation": {"minimum": 1, "hard_for_base": True},
            "Edge.U_final.test": {"minimum": 1, "hard_for_base": True},
            "IoT23.K_known.train_validation_test": {"minimum_each": 1, "hard_for_base": True},
            "IoT23.U_dev.unknown_dev": {"minimum": 1, "hard_for_base": True},
            "IoT23.U_final.unknown_final": {"minimum": 1, "hard_for_base": True},
            "few_shot": {
                "Edge_registered": [1, 5, 10], "IoT23_registered": [1, 5],
                "query_minimum": 1, "hard_for_base": False,
                "source": "frozen Phase-C support/query protocol",
            },
        },
        "run_identity": run_identity,
        "class_role_matrix": matrix,
        "edge": edge_results,
        "iot23": {
            "preset": iot_preset_id,
            "K_known": iot_known,
            "U_dev": iot_udev,
            "U_final": iot_ufinal,
            "development_isolation": "PASS" if not iot_leaks else "FAIL",
            "status": "PASS" if not iot_failures else "FAIL",
            "base_production_ready": not iot_failures,
            "few_shot_variant_ready": not iot_variant_failures,
        },
        "failures": failures,
        "variant_failures": variant_failures,
        "low_sample_warnings": warnings,
    }
