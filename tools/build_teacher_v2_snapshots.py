#!/usr/bin/env python3
"""Build bounded Teacher-v2 states from frozen Observable Dataset v3 candidates."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from flowsec.training.contracts import (
    EvidenceDomain,
    EvidenceEnvelope,
    EvidenceSnapshotV2,
    EvidenceStageV2,
    EvidenceTrustV1,
    canonical_json,
    content_digest,
)
from flowsec.training.materialization import sha256_file


SNAPSHOT_VERSION = "OBSERVABLE_TEACHER_V2_SNAPSHOT_UNIVERSE_V1"
ALL_CAPABILITIES = (
    "PACKET_PAYLOAD",
    "APPLICATION",
    "TEMPORAL",
    "RELATION",
    "KNOWLEDGE",
)
FAMILY_STAGE = {
    "PACKET_PAYLOAD": EvidenceStageV2.PACKET_PAYLOAD,
    "APPLICATION": EvidenceStageV2.APPLICATION,
    "TEMPORAL": EvidenceStageV2.TEMPORAL,
    "RELATION": EvidenceStageV2.RELATION,
}
FAMILY_ORDER = ("PACKET_PAYLOAD", "APPLICATION", "TEMPORAL", "RELATION")


def _state_id(
    sample_id: str, stage: EvidenceStageV2, evidence: tuple[EvidenceEnvelope, ...]
) -> str:
    return "state_" + content_digest(
        [SNAPSHOT_VERSION, sample_id, stage.value, [item.evidence_id for item in evidence]]
    )[:24]


def _envelope(
    sample_id: str,
    kind: str,
    content: dict[str, Any],
    *,
    payload: bool = False,
) -> EvidenceEnvelope:
    return EvidenceEnvelope(
        evidence_id=f"ev_{kind}_{content_digest([sample_id, kind])[:24]}",
        evidence_type=kind,
        domain=EvidenceDomain.OBSERVATION,
        trust=(
            EvidenceTrustV1.UNTRUSTED_PAYLOAD
            if payload
            else EvidenceTrustV1.TRUSTED_OBSERVATION
        ),
        content=content,
        provenance=f"observable_dataset_v3_{kind}_v2",
        metadata={"bounded": True, "strictly_past_only": kind in {"temporal", "relation"}},
    )


def _basic_envelopes(sample_id: str, view: dict[str, Any]) -> tuple[EvidenceEnvelope, ...]:
    meta = {
        "schema_version": view["schema_version"],
        "session_summary": view["session_summary"],
        "first_eight_packets": view["first_eight_packets"],
        "cheap_application_metadata": view["cheap_application_metadata"],
    }
    payload = {
        "schema_version": "PACKET_ALIGNED_SANITIZED_PAYLOAD_V2",
        "packet_range": [1, len(view["packet_aligned_payload"])],
        "packet_aligned_payload": view["packet_aligned_payload"],
    }
    return (
        _envelope(sample_id, "basic_metadata", meta),
        _envelope(sample_id, "sanitized_payload", payload, payload=True),
    )


def _packet_expansion(
    sample_id: str, rows: list[dict[str, Any]]
) -> EvidenceEnvelope | None:
    expanded = [
        {key: value for key, value in row.items() if key not in {"session_id", "frame_number_backend_only"}}
        for row in sorted(rows, key=lambda item: int(item["packet_index"]))
        if 9 <= int(row["packet_index"]) <= 16
    ]
    if not expanded:
        return None
    return _envelope(
        sample_id,
        "packet_payload",
        {"schema_version": "PACKET_ALIGNED_SANITIZED_PAYLOAD_V2", "packet_range": [9, 16], "packets": expanded},
        payload=True,
    )


def _snapshot(
    *,
    sample_id: str,
    fine_label: str,
    coarse_label: str,
    stage: EvidenceStageV2,
    primary: bool,
    evidence: tuple[EvidenceEnvelope, ...],
    acquired: set[str],
    dataset_digest: str,
) -> EvidenceSnapshotV2:
    available = tuple(item for item in ALL_CAPABILITIES if item not in acquired)
    source_digest = content_digest(
        [
            SNAPSHOT_VERSION,
            dataset_digest,
            sample_id,
            stage.value,
            [item.model_dump(mode="json") for item in evidence],
            available,
        ]
    )
    return EvidenceSnapshotV2(
        sample_id=sample_id,
        evidence_state_id=_state_id(sample_id, stage, evidence),
        fine_label=fine_label,
        coarse_label=coarse_label,
        split="train",
        ku_role="K_known",
        stage_type=stage,
        classification_supervision_valid=primary,
        available_capabilities=available,
        evidence=evidence,
        source_digest=source_digest,
    )


def _write_jsonl(path: Path, snapshots: list[EvidenceSnapshotV2]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for snapshot in snapshots:
            handle.write(canonical_json(snapshot.model_dump(mode="json")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def build(*, evidence_root: Path, freeze_root: Path, output_root: Path) -> dict[str, Any]:
    freeze_manifest_path = freeze_root / "manifests/observable_dataset_v3_freeze.json"
    freeze_manifest = json.loads(freeze_manifest_path.read_text(encoding="utf-8"))
    if freeze_manifest.get("DATASET_V3_FREEZE_STATUS") != "PASS":
        raise ValueError("Dataset-v3 freeze is not PASS")
    candidate_artifact = freeze_manifest["external_artifacts"]["sft_candidates"]
    candidate_path = Path(candidate_artifact["path"])
    if sha256_file(candidate_path) != candidate_artifact["sha256"]:
        raise ValueError("frozen SFT candidate digest mismatch")
    candidates = pq.read_table(candidate_path).to_pylist()
    candidate_by_capture: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        candidate_by_capture[str(row["capture_id_backend_only"])].append(row)

    snapshots: list[EvidenceSnapshotV2] = []
    per_class = defaultdict(Counter)
    for capture, capture_candidates in sorted(candidate_by_capture.items()):
        wanted = {str(row["sample_id"]): row for row in capture_candidates}
        basic = {
            str(row["session_id_backend_only"]): json.loads(row["view_json"])
            for row in pq.read_table(evidence_root / "basic_views" / f"{capture}.parquet").to_pylist()
            if str(row["session_id_backend_only"]) in wanted
        }
        raw = {
            str(row["sample_id"]): row
            for row in pq.read_table(evidence_root / "raw_sessions" / f"{capture}.parquet").to_pylist()
            if str(row["sample_id"]) in wanted
        }
        application = {
            str(row["session_id"]): json.loads(row["application_json"])
            for row in pq.read_table(evidence_root / "application" / f"{capture}.parquet").to_pylist()
            if str(row["session_id"]) in wanted
        }
        temporal = {
            str(row["session_id"]): json.loads(row["contexts_json"])
            for row in pq.read_table(evidence_root / "temporal" / f"{capture}.parquet").to_pylist()
            if str(row["session_id"]) in wanted
        }
        relation = {
            str(row["session_id"]): {
                key: value
                for key, value in row.items()
                if key not in {"session_id", "contexts_json"}
            }
            | {"contexts": json.loads(row["contexts_json"])}
            for row in pq.read_table(evidence_root / "relation" / f"{capture}.parquet").to_pylist()
            if str(row["session_id"]) in wanted
        }
        payload_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in pq.read_table(evidence_root / "packet_payload" / f"{capture}.parquet").to_pylist():
            if str(row["session_id"]) in wanted:
                payload_rows[str(row["session_id"])].append(row)
        if not all(set(wanted) == set(values) for values in (basic, raw, application, temporal, relation)):
            raise ValueError(f"candidate Evidence-v2 coverage mismatch: {capture}")

        for sample_id, candidate in sorted(wanted.items()):
            label = str(candidate["fine_label"])
            coarse = str(raw[sample_id]["coarse_label_backend_only"])
            evidence = _basic_envelopes(sample_id, basic[sample_id])
            primary = _snapshot(
                sample_id=sample_id,
                fine_label=label,
                coarse_label=coarse,
                stage=EvidenceStageV2.BASIC,
                primary=True,
                evidence=evidence,
                acquired=set(),
                dataset_digest=freeze_manifest["manifest_content_digest"],
            )
            snapshots.append(primary)
            per_class[label]["primary"] += 1
            if bool(candidate["basic_sufficient"]):
                continue
            required = set(json.loads(candidate["supporting_evidence_families_json"]))
            acquired: set[str] = set()
            for family in [item for item in FAMILY_ORDER if item in required][:2]:
                added: EvidenceEnvelope | None
                if family == "PACKET_PAYLOAD":
                    added = _packet_expansion(sample_id, payload_rows[sample_id])
                elif family == "APPLICATION":
                    added = _envelope(sample_id, "application", application[sample_id])
                elif family == "TEMPORAL":
                    added = _envelope(
                        sample_id,
                        "temporal",
                        {
                            "schema_version": "TEMPORAL_EVIDENCE_V2",
                            "strictly_past_only": True,
                            "contexts": temporal[sample_id],
                        },
                    )
                else:
                    added = _envelope(
                        sample_id,
                        "relation",
                        {"schema_version": "RELATION_EVIDENCE_V2", **relation[sample_id]},
                    )
                if added is None:
                    continue
                evidence = (*evidence, added)
                acquired.add(family)
                snapshots.append(
                    _snapshot(
                        sample_id=sample_id,
                        fine_label=label,
                        coarse_label=coarse,
                        stage=FAMILY_STAGE[family],
                        primary=False,
                        evidence=evidence,
                        acquired=acquired,
                        dataset_digest=freeze_manifest["manifest_content_digest"],
                    )
                )
                per_class[label]["auxiliary"] += 1

    state_ids = [item.evidence_state_id for item in snapshots]
    if len(state_ids) != len(set(state_ids)):
        raise ValueError("Teacher-v2 state identity collision")
    per_session = Counter(item.sample_id for item in snapshots)
    if min(per_session.values(), default=0) != 1 or max(per_session.values(), default=0) > 3:
        raise ValueError("Teacher-v2 state count escaped 1 primary + at most 2 auxiliary")
    primary = Counter(item.sample_id for item in snapshots if item.classification_supervision_valid)
    if set(primary.values()) != {1} or set(primary) != set(per_session):
        raise ValueError("Teacher-v2 primary state gate failed")

    snapshots_path = output_root / "snapshots/teacher_v2_snapshot_universe.jsonl"
    _write_jsonl(snapshots_path, snapshots)
    manifest = {
        "TEACHER_V2_SNAPSHOT_STATUS": "PASS",
        "snapshot_version": SNAPSHOT_VERSION,
        "dataset_freeze_digest": freeze_manifest["manifest_content_digest"],
        "candidate_sha256": candidate_artifact["sha256"],
        "candidate_sessions": len(candidates),
        "snapshot_count": len(snapshots),
        "primary_count": sum(item.classification_supervision_valid for item in snapshots),
        "auxiliary_count": sum(not item.classification_supervision_valid for item in snapshots),
        "max_states_per_session": max(per_session.values()),
        "per_class": {key: dict(value) for key, value in sorted(per_class.items())},
        "stage_distribution": dict(sorted(Counter(item.stage_type.value for item in snapshots).items())),
        "snapshots": {
            "path": str(snapshots_path),
            "size_bytes": snapshots_path.stat().st_size,
            "sha256": sha256_file(snapshots_path),
        },
        "u_final_count": 0,
    }
    manifest_path = output_root / "manifests/teacher_v2_snapshot_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"TEACHER_V2_SNAPSHOT_STATUS=PASS sessions={len(candidates)} states={len(snapshots)}",
        flush=True,
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence-root", type=Path, default=Path("/root/autodl-tmp/processed/observable_dataset_v3")
    )
    parser.add_argument(
        "--freeze-root", type=Path, default=Path("/root/autodl-tmp/processed/observable_dataset_v3_freeze")
    )
    parser.add_argument(
        "--output-root", type=Path, default=Path("/root/autodl-tmp/processed/teacher_v2_observable_dataset_v3")
    )
    args = parser.parse_args()
    build(
        evidence_root=args.evidence_root.resolve(),
        freeze_root=args.freeze_root.resolve(),
        output_root=args.output_root.resolve(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
