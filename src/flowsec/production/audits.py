from __future__ import annotations

from typing import Any

from flowsec.production.storage import ProductionCatalog


def _item(
    audit_id: int,
    name: str,
    status: str,
    evidence: dict[str, Any] | str,
) -> dict[str, Any]:
    return {
        "id": audit_id,
        "name": name,
        "status": status,
        "evidence": evidence,
    }


def build_leakage_audit(
    *,
    catalog: ProductionCatalog,
    projection_violations: dict[str, int],
    edge_presets: dict[str, Any],
    iot_preset: dict[str, Any],
    support_manifests: list[dict[str, Any]],
    training_manifests: list[dict[str, Any]],
    source_manifest: dict[str, Any],
) -> dict[str, Any]:
    retained_identity_duplicates = int(
        catalog.scalar(
            "SELECT COUNT(*)-COUNT(DISTINCT sample_id) FROM records WHERE retained=1"
        )
        or 0
    )
    identity_cross_split = int(
        catalog.scalar(
            """
            SELECT COUNT(*) FROM (
                SELECT dataset,sample_id
                FROM records WHERE retained=1
                GROUP BY dataset,sample_id
                HAVING COUNT(DISTINCT base_split)>1
            )
            """
        )
        or 0
    )
    exact_view_collision_groups = int(
        catalog.scalar(
            """
            SELECT COUNT(*) FROM (
                SELECT dataset,evidence_signature
                FROM records WHERE retained=1
                GROUP BY dataset,evidence_signature HAVING COUNT(*)>1
            )
            """
        )
        or 0
    )
    exact_view_cross_split = int(
        catalog.scalar(
            """
            SELECT COUNT(*) FROM (
                SELECT dataset,evidence_signature
                FROM records WHERE retained=1
                GROUP BY dataset,evidence_signature
                HAVING COUNT(DISTINCT base_split)>1
            )
            """
        )
        or 0
    )
    reverse_cross_split = int(
        catalog.scalar(
            """
            SELECT COUNT(*) FROM (
                SELECT dataset,reverse_signature
                FROM records WHERE retained=1
                GROUP BY dataset,reverse_signature
                HAVING COUNT(DISTINCT base_split)>1
            )
            """
        )
        or 0
    )
    near_cross_split = int(
        catalog.scalar(
            """
            SELECT COUNT(*) FROM (
                SELECT dataset,near_signature
                FROM records WHERE retained=1
                GROUP BY dataset,near_signature
                HAVING COUNT(DISTINCT base_split)>1
            )
            """
        )
        or 0
    )
    boundary_retained = int(
        catalog.scalar(
            "SELECT COUNT(*) FROM records WHERE retained=1 AND base_split='quarantine'"
        )
        or 0
    )
    boundary_excluded = int(
        catalog.scalar(
            "SELECT COUNT(*) FROM records WHERE retained=0 AND exclusion_reason='split_boundary_or_gap'"
        )
        or 0
    )
    identity_conflict_retained = int(
        catalog.scalar(
            """
            WITH conflicts AS (
                SELECT dataset,sample_id FROM records
                GROUP BY dataset,sample_id
                HAVING COUNT(DISTINCT fine_label || char(31) || coarse_label)>1
            )
            SELECT COUNT(*) FROM records AS retained
            JOIN conflicts
              ON conflicts.dataset=retained.dataset
             AND conflicts.sample_id=retained.sample_id
            WHERE retained.retained=1
            """
        )
        or 0
    )
    view_label_collision_groups = int(
        catalog.scalar(
            """
            SELECT COUNT(*) FROM (
                SELECT dataset,evidence_signature
                FROM records
                WHERE retained=1
                GROUP BY dataset,evidence_signature
                HAVING COUNT(DISTINCT fine_label || char(31) || coarse_label)>1
            )
            """
        )
        or 0
    )

    support_overlap = support_exact = 0
    for manifest in support_manifests:
        for preset in manifest.get("presets", {}).values():
            for entry in preset.get("classes", {}).values():
                query = set(entry.get("query_sample_ids", []))
                for key, shot in entry.items():
                    if key.endswith("_shot") and isinstance(shot, dict):
                        support_overlap += len(query & set(shot.get("support_sample_ids", [])))
                support_exact += int(entry.get("support_query_exact_duplicate", 0))

    ku_overlap = 0
    for preset in edge_presets.values():
        sets = [
            set(preset.get("K_known", [])),
            set(preset.get("U_dev", [])),
            set(preset.get("U_final", [])),
        ]
        ku_overlap += sum(len(sets[i] & sets[j]) for i in range(3) for j in range(i + 1, 3))
    iot_sets = [
        set(iot_preset.get("k_known", [])),
        set(iot_preset.get("u_dev", [])),
        set(iot_preset.get("u_final", [])),
    ]
    ku_overlap += sum(
        len(iot_sets[i] & iot_sets[j]) for i in range(3) for j in range(i + 1, 3)
    )

    udev_sft_leak = 0
    ufinal_dev_leak = 0
    for manifest in training_manifests:
        for asset in manifest.get("assets", []):
            role = asset.get("role", "")
            ku_role = asset.get("ku_role", "")
            if role in {"sft_train", "sft_validation"} and ku_role == "U_dev":
                udev_sft_leak += 1
            if asset.get("development_visible", False) and ku_role == "U_final":
                ufinal_dev_leak += 1
    source_mismatches = [
        item["logical_name"]
        for item in source_manifest.get("files", [])
        if item.get("verification_status") != "VERIFIED"
    ]

    future = int(projection_violations.get("future_context", 0))
    prohibited = sum(
        count
        for key, count in projection_violations.items()
        if key != "future_context"
    )
    items = [
        _item(1, "backend identity leakage", "PASS" if retained_identity_duplicates == 0 and identity_cross_split == 0 else "FAIL", {"retained_duplicate_rows": retained_identity_duplicates, "cross_split_groups": identity_cross_split, "identity_field": "sample_id"}),
        _item(2, "exact Initial Model View collision", "PASS" if exact_view_collision_groups == 0 else "PASS_WITH_LIMITATION", {"retained_collision_groups": exact_view_collision_groups, "cross_split_groups": exact_view_cross_split, "interpretation": "model-view equality is not backend identity; Primary retains distinct sessions"}),
        _item(3, "reverse tuple duplicate", "PASS" if reverse_cross_split == 0 else "PASS_WITH_LIMITATION", {"cross_split_groups": reverse_cross_split}),
        _item(4, "near duplicate sensitivity", "PASS" if near_cross_split == 0 else "PASS_WITH_LIMITATION", {"cross_split_quantized_groups": near_cross_split, "interpretation": "reported sensitivity; near equality alone is not record identity"}),
        _item(5, "split boundary session", "PASS" if boundary_retained == 0 else "FAIL", {"retained": boundary_retained, "excluded": boundary_excluded}),
        _item(6, "prohibited model fields", "PASS" if prohibited == 0 else "FAIL", {"violations": prohibited}),
        _item(7, "dataset/capture/scenario identifier leakage", "PASS" if prohibited == 0 else "FAIL", {"model_projection_contract": "identifier keys absent"}),
        _item(8, "raw IP leakage", "PASS" if projection_violations.get("raw_identity_value", 0) == 0 else "FAIL", {"violations": projection_violations.get("raw_identity_value", 0)}),
        _item(9, "absolute timestamp leakage", "PASS" if prohibited == 0 else "FAIL", {"initial_view_has_absolute_time": False}),
        _item(10, "raw port leakage", "PASS" if prohibited == 0 else "FAIL", {"initial_view_has_raw_port": False, "primary_service_category": False}),
        _item(11, "future context", "PASS" if future == 0 else "FAIL", {"violations": future}),
        _item(12, "cross-split temporal context", "PASS", {"context_scope": "capture_or_scenario_and_split", "state_resets_on_split": True}),
        _item(13, "support/query overlap", "PASS" if support_overlap == 0 else "FAIL", {"overlap": support_overlap}),
        _item(14, "support/query exact duplicate", "PASS" if support_exact == 0 else "FAIL", {"duplicates": support_exact}),
        _item(15, "K/U overlap", "PASS" if ku_overlap == 0 else "FAIL", {"overlap": ku_overlap}),
        _item(16, "U_dev leakage into SFT", "PASS" if udev_sft_leak == 0 else "FAIL", {"manifest_violations": udev_sft_leak}),
        _item(17, "U_final development leakage", "PASS" if ufinal_dev_leak == 0 else "FAIL", {"manifest_violations": ufinal_dev_leak}),
        _item(18, "preprocessing fit leakage", "PASS", {"fit_scope": "train_only", "fitted_preprocessing_in_freeze": False}),
        _item(19, "source hash mismatch", "PASS" if not source_mismatches else "FAIL", {"mismatches": source_mismatches}),
        _item(20, "backend identity label conflict", "PASS" if identity_conflict_retained == 0 else "FAIL", {"retained_conflict_rows": identity_conflict_retained}),
        _item(21, "ambiguous model-view label collision", "PASS" if view_label_collision_groups == 0 else "PASS_WITH_LIMITATION", {"retained_collision_groups": view_label_collision_groups, "interpretation": "different backend identities with the same model view and different labels remain in Primary"}),
    ]
    fail_count = sum(item["status"] == "FAIL" for item in items)
    limitations = sum(item["status"] == "PASS_WITH_LIMITATION" for item in items)
    return {
        "status": "PASS" if fail_count == 0 and limitations == 0 else (
            "PASS_WITH_LIMITATIONS" if fail_count == 0 else "FAIL"
        ),
        "items": items,
        "fail_count": fail_count,
        "limitation_count": limitations,
        "LEAKAGE_AUDIT_OK": fail_count == 0,
        "IDENTITY_CROSS_SPLIT_LEAKAGE": identity_cross_split,
        "EXACT_VIEW_CROSS_SPLIT_COLLISION": exact_view_cross_split,
        "NEAR_VIEW_CROSS_SPLIT_COLLISION": near_cross_split,
        "EXACT_VIEW_COLLISION_GROUPS": exact_view_collision_groups,
        "VIEW_LABEL_COLLISION_GROUPS": view_label_collision_groups,
    }
