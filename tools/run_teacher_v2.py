#!/usr/bin/env python3
"""Run the resumable Teacher-v2 connectivity, pilot, or frozen bulk stage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from flowsec.training.contracts import EvidenceSnapshotV2
from flowsec.training.materialization import sha256_file
from flowsec.training.teacher import (
    annotate_snapshots_v2,
    deepseek_api_preflight,
    make_live_teacher_v2_client,
    select_teacher_v2_pilot,
    write_annotation_record,
)


DEFAULT_ROOT = Path("/root/autodl-tmp/processed/teacher_v2_observable_dataset_v3")


def _load_snapshots(root: Path) -> list[EvidenceSnapshotV2]:
    manifest = json.loads(
        (root / "manifests/teacher_v2_snapshot_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    if manifest.get("TEACHER_V2_SNAPSHOT_STATUS") != "PASS":
        raise ValueError("Teacher-v2 snapshot universe is not PASS")
    path = Path(manifest["snapshots"]["path"])
    if sha256_file(path) != manifest["snapshots"]["sha256"]:
        raise ValueError("Teacher-v2 snapshot universe digest mismatch")
    snapshots = [
        EvidenceSnapshotV2.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(snapshots) != int(manifest["snapshot_count"]):
        raise ValueError("Teacher-v2 snapshot universe count mismatch")
    return snapshots


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("connectivity", "pilot", "bulk"))
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--pilot-size", type=int, default=40)
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.mode == "connectivity":
        result = deepseek_api_preflight()
        write_annotation_record(root / "annotations/connectivity.json", result)
        print(f"TEACHER_V2_CONNECTIVITY={result['status']}")
        return 0 if result["status"] == "PASS" else 1

    snapshots = _load_snapshots(root)
    client = make_live_teacher_v2_client()
    pilot_root = root / "annotations/pilot"
    if args.mode == "pilot":
        selected = select_teacher_v2_pilot(snapshots, target=args.pilot_size)
        manifest = annotate_snapshots_v2(
            selected,
            pilot_root,
            client=client,
            concurrency=args.concurrency,
        )
        print(
            f"TEACHER_V2_PILOT={manifest['status']} "
            f"valid={manifest['valid_count']}/{manifest['requested']}"
        )
        return 0 if manifest["status"] == "PASS" else 1

    pilot_manifest_path = pilot_root / "manifest.json"
    if not pilot_manifest_path.is_file():
        raise ValueError("Teacher-v2 bulk requires a completed pilot manifest")
    pilot_manifest = json.loads(pilot_manifest_path.read_text(encoding="utf-8"))
    if pilot_manifest.get("status") != "PASS" or int(pilot_manifest.get("requested", 0)) < 20:
        raise ValueError("Teacher-v2 pilot gate is not PASS")
    manifest = annotate_snapshots_v2(
        snapshots,
        root / "annotations/bulk",
        client=client,
        concurrency=args.concurrency,
        seed_cache_roots=(pilot_root / "records",),
    )
    print(
        f"TEACHER_V2_BULK={manifest['status']} "
        f"valid={manifest['valid_count']}/{manifest['requested']}"
    )
    return 0 if manifest["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
