#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from flowsec.production.split_revision import (
    Boundary,
    SPLIT_POLICY_ID,
    audit_phase_a_split_candidates,
)
from flowsec.production.storage import ProductionCatalog, write_json


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Read-only Phase A comparison for Edge split candidates."
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
        "--selected-split-manifest",
        type=Path,
        default=Path(
            "/root/autodl-tmp/processed/edge_split_revision_v2/manifests/"
            "edge_split_manifest.json"
        ),
    )
    value.add_argument(
        "--output",
        type=Path,
        default=Path(
            "/root/autodl-tmp/experiments/edge_split_revision_v2/"
            "phase_a_split_candidate_comparison.json"
        ),
    )
    value.add_argument("--dataset", default="Edge-IIoTset")
    return value


def main() -> int:
    args = parser().parse_args()
    if not args.source_catalog.is_file():
        raise SystemExit(f"missing source catalog: {args.source_catalog}")
    manifest = _load(args.selected_split_manifest)
    if manifest.get("policy") != SPLIT_POLICY_ID:
        raise SystemExit("selected split manifest does not use the v2 policy")
    selected_boundaries = {
        str(capture_id): Boundary(**value["boundary"])
        for capture_id, value in manifest["captures"].items()
    }
    catalog = ProductionCatalog(args.source_catalog)
    try:
        catalog.connection.execute("PRAGMA query_only=ON")
        report = audit_phase_a_split_candidates(
            catalog=catalog,
            dataset=args.dataset,
            selected_boundaries=selected_boundaries,
            local_embargo_seconds=5.0,
        )
    finally:
        catalog.close()

    current = report["candidates"]["CURRENT_WALL_CLOCK_SPAN_CHRONOLOGICAL"]
    selected = report["candidates"][SPLIT_POLICY_ID]
    exact_delta = int(selected["exact_model_view_cross_split_collision_groups"]) - int(
        current["exact_model_view_cross_split_collision_groups"]
    )
    near_delta = int(selected["near_signature_cross_split_collision_groups"]) - int(
        current["near_signature_cross_split_collision_groups"]
    )
    report["selected_vs_current"] = {
        "zero_class_delta": int(selected["zero_class_count"])
        - int(current["zero_class_count"]),
        "critical_low_class_delta": int(selected["critical_low_class_count"])
        - int(current["critical_low_class_count"]),
        "exact_cross_split_collision_group_delta": exact_delta,
        "near_cross_split_collision_group_delta": near_delta,
        "interpretation": (
            "Model-view equality is not backend identity. Collision changes are disclosed "
            "and evaluated with train-unchanged EXACT_EVAL_CLEAN/NEAR_EVAL_CLEAN sensitivity."
        ),
    }
    report["SPLIT_REVISION_DESIGN"] = (
        "PASS_FOR_REBUILD"
        if int(selected["identity_cross_split_leakage"]) == 0
        and int(selected["zero_class_count"]) == 0
        and int(selected["critical_low_class_count"]) == 0
        and int(selected["zero_class_count"]) < int(current["zero_class_count"])
        and int(selected["critical_low_class_count"])
        < int(current["critical_low_class_count"])
        else "NEEDS_USER_DECISION"
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, report)
    print(json.dumps({
        "SPLIT_REVISION_DESIGN": report["SPLIT_REVISION_DESIGN"],
        "output": str(args.output),
        "source_rows": report["source_rows"],
        "selected_vs_current": report["selected_vs_current"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
