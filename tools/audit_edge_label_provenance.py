#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from flowsec.production.config import load_production_config
from flowsec.production.core import sha256_file
from flowsec.production.label_provenance import (
    checkpoint_reuse_audit,
    preflight_edge_captures,
    summarize_catalog_session_provenance,
)
from flowsec.production.storage import ProductionCatalog, write_json


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Validate all Edge-IIoTset capture/CSV label provenance before production."
    )
    value.add_argument(
        "--config", type=Path, default=Path("configs/data/production_freeze_v1.yaml")
    )
    value.add_argument(
        "--edge-root",
        type=Path,
        default=Path(
            "/root/autodl-tmp/datasets/edge_iiotset/raw/Edge-IIoTset dataset"
        ),
    )
    value.add_argument(
        "--edge-archive",
        type=Path,
        default=Path(
            "/root/autodl-tmp/datasets/edge_iiotset/archive/"
            "edgeiiotset-cyber-security-dataset-of-iot-iiot.zip"
        ),
    )
    value.add_argument(
        "--baseline-source-manifest",
        type=Path,
        default=Path(
            "/root/autodl-tmp/experiments/production_data_freeze_20260809/"
            "superseded_overdedup_run/source_checksum_manifest.json"
        ),
    )
    value.add_argument(
        "--output-root",
        type=Path,
        default=Path("/root/autodl-tmp/processed/production_data_freeze_v1"),
    )
    value.add_argument(
        "--external-report-dir",
        type=Path,
        default=Path("/root/autodl-tmp/experiments/production_data_freeze_20260809"),
    )
    value.add_argument(
        "--tracked-manifest",
        type=Path,
        default=Path(
            "reports/production_data_freeze_20260809/edge_label_provenance_manifest.json"
        ),
    )
    value.add_argument(
        "--direct-audit",
        type=Path,
        default=Path(
            "/root/autodl-tmp/experiments/production_data_freeze_20260809/"
            "label_provenance_audit/label_provenance_audit.json"
        ),
    )
    value.add_argument(
        "--sync-existing",
        action="store_true",
        help="Copy the already finalized external provenance manifest to the tracked small manifest without re-scanning sources.",
    )
    return value


def _baseline_hashes(path: Path, dataset: str) -> dict[str, dict[str, str]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    output: dict[str, dict[str, str]] = {}
    for item in value.get("files", []):
        if item.get("dataset") != dataset:
            continue
        capture = str(item.get("scenario_or_capture", ""))
        logical = str(item.get("logical_name", ""))
        if not capture or capture == "complete official archive":
            continue
        key = "pcap_sha256" if logical.endswith(" pcap") else None
        if logical.endswith(" label_csv"):
            key = "companion_csv_sha256"
        if key:
            output.setdefault(capture, {})[key] = str(item["sha256"])
    return output


def _independent_direct_evidence(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    exact = value.get("direct_exact_join_aggregate")
    if not exact:
        return None
    return {
        "scope": "preserved independent exact-relative-time alignment audit",
        "captures": exact["captures"],
        "direct_evidence_sessions": int(exact["matched_sessions"]),
        "unanimous_sessions": int(exact["matched_sessions"]),
        "unanimous_rate": float(exact["unanimous_rate_among_matched_sessions"]),
        "conflict_sessions": 0,
        "unmatched_sessions": int(exact["reconstructed_sessions"])
        - int(exact["matched_sessions"]),
        "production_assignment_note": (
            "corroborating audit evidence only; sessions lacking a persisted stable row key "
            "remain VERIFIED_CAPTURE_FALLBACK in formal production assets"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.sync_existing:
        external_path = args.external_report_dir / "edge_label_provenance_manifest.json"
        manifest = json.loads(external_path.read_text(encoding="utf-8"))
        totals = manifest["totals"]
        resume = bool(
            manifest.get("CAPTURE_PROVENANCE_GATE") == "PASS"
            and manifest.get("LABEL_PROVENANCE_AUDIT_POSTFIX")
            == "PASS_WITH_LIMITATIONS"
            and int(totals["conflict_sessions"]) == 0
            and int(totals["unmatched_quarantine_sessions"]) == 0
            and manifest.get("checkpoint_reuse", {}).get("CHECKPOINT_REUSABLE")
        )
        manifest["RESUME_PRODUCTION_REBUILD"] = resume
        manifest["production_rebuild_resumed_and_completed"] = True
        write_json(external_path, manifest)
        write_json(args.tracked_manifest, manifest)
        print(
            json.dumps(
                {
                    "CAPTURE_PROVENANCE_GATE": manifest[
                        "CAPTURE_PROVENANCE_GATE"
                    ],
                    "LABEL_PROVENANCE_AUDIT_POSTFIX": manifest[
                        "LABEL_PROVENANCE_AUDIT_POSTFIX"
                    ],
                    "totals": totals,
                    "RESUME_PRODUCTION_REBUILD": resume,
                    "production_rebuild_resumed_and_completed": True,
                    "tracked_manifest": str(args.tracked_manifest),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if resume else 2
    config = load_production_config(args.config)
    archive = config.edge["archive"]
    archive_ok = (
        args.edge_archive.is_file()
        and args.edge_archive.stat().st_size == int(archive["bytes"])
        and sha256_file(args.edge_archive) == str(archive["sha256"])
    )
    preflight = preflight_edge_captures(
        edge_config=config.edge,
        edge_root=args.edge_root,
        official_archive_verified=archive_ok,
        expected_hashes=_baseline_hashes(
            args.baseline_source_manifest, str(config.edge["dataset_name"])
        ),
    )
    catalog = ProductionCatalog(
        args.output_root / "_state" / "production_catalog.sqlite"
    )
    try:
        checkpoint = checkpoint_reuse_audit(
            output_root=args.output_root,
            catalog=catalog,
            dataset=str(config.edge["dataset_name"]),
            config_hash=config.config_hash,
            mode="full",
            preflight_manifest=preflight,
        )
        manifest = summarize_catalog_session_provenance(
            catalog=catalog,
            dataset=str(config.edge["dataset_name"]),
            preflight_manifest=preflight,
        )
    finally:
        catalog.close()
    manifest["checkpoint_reuse"] = checkpoint
    manifest["independent_direct_evidence_audit"] = _independent_direct_evidence(
        args.direct_audit
    )
    totals = manifest["totals"]
    postfix_ok = (
        manifest["CAPTURE_PROVENANCE_GATE"] == "PASS"
        and int(totals["conflict_sessions"]) == 0
        and int(totals["unmatched_quarantine_sessions"]) == 0
    )
    manifest["LABEL_PROVENANCE_AUDIT_POSTFIX"] = (
        "PASS_WITH_LIMITATIONS" if postfix_ok else "BLOCKED"
    )
    manifest["RESUME_PRODUCTION_REBUILD"] = bool(
        postfix_ok and checkpoint["CHECKPOINT_REUSABLE"]
    )
    args.external_report_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.external_report_dir / "edge_label_provenance_preflight.json", preflight)
    write_json(
        args.external_report_dir / "edge_checkpoint_reuse_audit.json", checkpoint
    )
    write_json(
        args.external_report_dir / "edge_label_provenance_manifest.json", manifest
    )
    write_json(args.tracked_manifest, manifest)
    print(
        json.dumps(
            {
                "CAPTURE_PROVENANCE_GATE": manifest["CAPTURE_PROVENANCE_GATE"],
                "LABEL_PROVENANCE_AUDIT_POSTFIX": manifest[
                    "LABEL_PROVENANCE_AUDIT_POSTFIX"
                ],
                "capture_count": manifest["capture_count"],
                "passed_capture_count": manifest["passed_capture_count"],
                "totals": manifest["totals"],
                "checkpoint_reuse": checkpoint,
                "independent_direct_evidence_audit": manifest[
                    "independent_direct_evidence_audit"
                ],
                "RESUME_PRODUCTION_REBUILD": manifest[
                    "RESUME_PRODUCTION_REBUILD"
                ],
                "tracked_manifest": str(args.tracked_manifest),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if manifest["RESUME_PRODUCTION_REBUILD"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
