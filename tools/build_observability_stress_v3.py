#!/usr/bin/env python3
"""Build a bounded CE-masked index of excluded Observable Dataset-v3 states."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from flowsec.training.contracts import content_digest
from flowsec.training.corpus_v3 import atomic_json
from flowsec.training.materialization import sha256_file


STRESS_VERSION = "OBSERVABILITY_STRESS_SET_V3_INDEX_V1"


def build(*, freeze_manifest: Path, output_root: Path, per_stratum: int = 1000) -> dict:
    freeze = json.loads(freeze_manifest.read_text(encoding="utf-8"))
    source = Path(freeze["external_artifacts"]["assignments"]["path"])
    if sha256_file(source) != freeze["external_artifacts"]["assignments"]["sha256"]:
        raise ValueError("Dataset-v3 assignment digest mismatch")
    strata = defaultdict(list)
    for row in pq.read_table(source).to_pylist():
        if bool(row["classification_ce_eligible"]) or row["final_split"] != "excluded":
            continue
        reason = str(row["exclusion_reason"] or "UNSPECIFIED")
        if reason == "SOURCE_SPLIT_QUARANTINE":
            continue
        key = (str(row["fine_label"]), reason)
        strata[key].append(row)
    selected = []
    for key, rows in sorted(strata.items()):
        rows.sort(key=lambda item: content_digest([STRESS_VERSION, item["session_id"]]))
        for row in rows[:per_stratum]:
            selected.append(
                {
                    "version": STRESS_VERSION,
                    "sample_id_backend_only": row["session_id"],
                    "fine_label_backend_only": row["fine_label"],
                    "source_split_backend_only": row["source_split"],
                    "eligibility_class": row["eligibility_class"],
                    "exclusion_reason": row["exclusion_reason"],
                    "classification_ce_eligible": False,
                    "intended_supervision": "ABSTAIN_OR_NOT_RECOVERABLE",
                    "unknown_semantics": False,
                }
            )
    path = output_root / "observability_stress_index_v3.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(selected), path, compression="zstd")
    manifest = {
        "status": "PASS",
        "version": STRESS_VERSION,
        "record_count": len(selected),
        "per_stratum_limit": per_stratum,
        "classification_ce_eligible_count": 0,
        "unknown_equated_with_unobservable": False,
        "distribution": dict(sorted(Counter(row["fine_label_backend_only"] for row in selected).items())),
        "reason_distribution": dict(sorted(Counter(row["exclusion_reason"] for row in selected).items())),
        "roles": {
            "Backdoor": "LONG_HORIZON_CASE_STUDY_NOT_MATERIALIZED_HERE",
            "Uploading": "OBSERVABILITY_LIMITED_DECLARED_NOT_IN_17_CAPTURE_V3_SCAN",
            "Ransomware": "OBSERVABILITY_LIMITED_DECLARED_NOT_IN_17_CAPTURE_V3_SCAN",
        },
        "limitation": "This bounded v1 index covers exclusions from the eight-candidate Evidence-v2 scan. Uploading and Ransomware remain preserved external sources for a separate non-CE stress materialization.",
        "artifact": {"path": str(path), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)},
        "u_final_count": 0,
    }
    atomic_json(output_root / "manifest.json", manifest)
    print(f"OBSERVABILITY_STRESS_SET={manifest['status']} records={len(selected)}")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-manifest", type=Path, default=Path("/root/autodl-tmp/processed/observable_dataset_v3_freeze/manifests/observable_dataset_v3_freeze.json"))
    parser.add_argument("--output-root", type=Path, default=Path("/root/autodl-tmp/processed/observability_stress_v3"))
    parser.add_argument("--per-stratum", type=int, default=1000)
    args = parser.parse_args()
    result = build(freeze_manifest=args.freeze_manifest, output_root=args.output_root, per_stratum=args.per_stratum)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
