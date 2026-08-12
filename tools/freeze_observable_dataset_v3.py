#!/usr/bin/env python3
"""Freeze the eligible six-class Observable Dataset v3 and SFT candidates."""

from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import os
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from flowsec.training.contracts import canonical_json, content_digest
from flowsec.training.materialization import sha256_file
from flowsec.training.observable_v3 import (
    ELIGIBILITY_POLICY_VERSION,
    OBSERVABLE_DATASET_VERSION,
)


FREEZE_VERSION = "OBSERVABLE_DATASET_V3_FREEZE_V1"
SELECTION_VERSION = "CLASS_BALANCED_DIVERSITY_AWARE_SFT_SELECTION_V2"
FINAL_MAIN_CLASSES = (
    "Normal",
    "DDoS_HTTP",
    "DDoS_TCP",
    "Password",
    "SQL_injection",
    "Vulnerability_scanner",
)
EXCLUDED_CANDIDATE_ROLES = {
    "MITM": "OBSERVABILITY_LIMITED_WRONG_GRANULARITY",
    "Port_Scanning": "OBSERVABILITY_LIMITED_CAPTURE_SEMANTICS_MISMATCH",
}
FORMAL_SPLITS = ("train", "validation", "test")
SPLIT_BITS = {"train": 1, "validation": 2, "test": 4}


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _atomic_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"refusing empty parquet: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
        pq.write_table(pa.Table.from_pylist(rows), temporary, compression="zstd")
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _artifact(path: Path) -> dict[str, Any]:
    return {"path": str(path), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}


def _rank(sample_id: str, seed: int) -> bytes:
    return hashlib.sha256(f"{seed}:{sample_id}".encode()).digest()


def select_diversity_aware(
    rows: list[dict[str, Any]],
    *,
    budget: int,
    maximum_per_exact: int,
    seed: int,
) -> list[dict[str, Any]]:
    """Near-first deterministic selection with bounded exact multiplicity."""

    exact_heaps: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    near_best: dict[str, tuple[bytes, str, str]] = {}
    by_id = {str(row["sample_id"]): row for row in rows}
    if len(by_id) != len(rows):
        raise ValueError("candidate input contains duplicate sample IDs")
    for row in rows:
        sample = str(row["sample_id"])
        exact, near = str(row["exact_signature"]), str(row["near_signature"])
        rank = _rank(sample, seed)
        previous = near_best.get(near)
        if previous is None or rank < previous[0]:
            near_best[near] = (rank, sample, exact)
        integer_rank = int.from_bytes(rank, "big")
        heap = exact_heaps[exact]
        candidate = (-integer_rank, sample, near)
        if len(heap) < maximum_per_exact:
            heapq.heappush(heap, candidate)
        elif integer_rank < -heap[0][0]:
            heapq.heapreplace(heap, candidate)

    exact_items = {
        exact: sorted((sample, near) for _, sample, near in heap)
        for exact, heap in exact_heaps.items()
    }
    chosen: dict[str, tuple[str, str, str]] = {}
    chosen_exact_counts: Counter[str] = Counter()
    for near, (_, sample, exact) in sorted(near_best.items()):
        if chosen_exact_counts[exact] >= maximum_per_exact:
            continue
        chosen.setdefault(sample, (exact, near, "NEAR_GROUP_FIRST"))
        chosen_exact_counts[exact] += 1
        if len(chosen) >= budget:
            break
    if len(chosen) < budget:
        for exact, items in sorted(exact_items.items()):
            if chosen_exact_counts[exact] >= maximum_per_exact:
                continue
            for sample, near in items:
                if sample not in chosen:
                    chosen[sample] = (exact, near, "EXACT_GROUP_SECOND")
                    chosen_exact_counts[exact] += 1
                    break
            if len(chosen) >= budget:
                break
    for depth in range(1, maximum_per_exact):
        if len(chosen) >= budget:
            break
        for exact, items in sorted(exact_items.items()):
            if chosen_exact_counts[exact] >= maximum_per_exact:
                continue
            if depth < len(items):
                sample, near = items[depth]
                if sample not in chosen:
                    chosen[sample] = (exact, near, "BOUNDED_MULTIPLICITY")
                    chosen_exact_counts[exact] += 1
            if len(chosen) >= budget:
                break
    selected = []
    for sample_id, (exact, near, stage) in sorted(chosen.items()):
        selected.append(
            {
                **by_id[sample_id],
                "selection_version": SELECTION_VERSION,
                "selection_stage": stage,
                "exact_signature": exact,
                "near_signature": near,
            }
        )
    exact_counts = Counter(str(row["exact_signature"]) for row in selected)
    if max(exact_counts.values(), default=0) > maximum_per_exact:
        raise ValueError("exact signature multiplicity gate failed")
    return selected


def freeze(
    *,
    source_root: Path,
    output_root: Path,
    tracked_manifest: Path,
    class_budget: int = 2048,
    max_per_exact: int = 16,
    seed: int = 20260813,
) -> dict[str, Any]:
    preflight_path = source_root / "manifests/observable_dataset_v3_preflight.json"
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    if preflight.get("OBSERVABLE_DATASET_V3_PREFLIGHT") != "PASS":
        raise ValueError("Observable Dataset v3 preflight is not PASS")
    if preflight.get("dataset_version") != OBSERVABLE_DATASET_VERSION:
        raise ValueError("Observable Dataset v3 version mismatch")

    checkpoint_paths = sorted((source_root / "checkpoints").glob("*.json"))
    if len(checkpoint_paths) != 17:
        raise ValueError("freeze requires exactly 17 capture checkpoints")
    for checkpoint_path in checkpoint_paths:
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if checkpoint.get("status") != "PASS" or checkpoint.get("packet_limit") is not None:
            raise ValueError(f"invalid capture checkpoint: {checkpoint_path}")
        for artifact in (checkpoint.get("artifacts") or {}).values():
            path = Path(artifact["path"])
            if not path.is_file() or sha256_file(path) != artifact["sha256"]:
                raise ValueError(f"capture artifact identity mismatch: {path}")

    assignments: list[dict[str, Any]] = []
    selected_input: dict[str, list[dict[str, Any]]] = defaultdict(list)
    per_class: dict[str, Counter[str]] = defaultdict(Counter)
    exact_masks: dict[str, int] = defaultdict(int)
    near_masks: dict[str, int] = defaultdict(int)
    formal_ids: dict[str, set[str]] = {split: set() for split in FORMAL_SPLITS}
    for eligibility_path in sorted((source_root / "eligibility").glob("*.parquet")):
        capture = eligibility_path.stem
        eligibility_rows = pq.read_table(eligibility_path).to_pylist()
        basic_rows = {
            str(row["session_id_backend_only"]): row
            for row in pq.read_table(source_root / "basic_views" / f"{capture}.parquet").to_pylist()
        }
        if set(basic_rows) != {str(row["session_id"]) for row in eligibility_rows}:
            raise ValueError(f"Basic-v2 coverage mismatch: {capture}")
        for row in eligibility_rows:
            sample_id = str(row["session_id"])
            label, split = str(row["fine_label"]), str(row["split"])
            final_eligible = bool(
                label in FINAL_MAIN_CLASSES
                and split in FORMAL_SPLITS
                and row["full_observational_sufficient"]
                and row["classification_ce_eligible"]
            )
            exclusion = ""
            if not final_eligible:
                if label in EXCLUDED_CANDIDATE_ROLES:
                    exclusion = EXCLUDED_CANDIDATE_ROLES[label]
                elif split not in FORMAL_SPLITS:
                    exclusion = "SOURCE_SPLIT_QUARANTINE"
                else:
                    exclusion = str(row["exclusion_reason"] or row["eligibility_class"])
            assignment = {
                "freeze_version": FREEZE_VERSION,
                "eligibility_policy_version": ELIGIBILITY_POLICY_VERSION,
                "session_id": sample_id,
                "capture_id_backend_only": str(row["capture_id_backend_only"]),
                "fine_label": label,
                "source_split": split,
                "final_split": split if final_eligible else "excluded",
                "classification_ce_eligible": final_eligible,
                "full_observational_sufficient": bool(
                    row["full_observational_sufficient"]
                ),
                "eligibility_class": str(row["eligibility_class"]),
                "exclusion_reason": exclusion,
            }
            assignments.append(assignment)
            per_class[label]["original"] += 1
            if final_eligible:
                per_class[label][split] += 1
                formal_ids[split].add(sample_id)
                basic = basic_rows[sample_id]
                exact, near = str(basic["exact_signature"]), str(basic["near_signature"])
                exact_masks[exact] |= SPLIT_BITS[split]
                near_masks[near] |= SPLIT_BITS[split]
                if split == "train":
                    selected_input[label].append(
                        {
                            "sample_id": sample_id,
                            "fine_label": label,
                            "capture_id_backend_only": str(row["capture_id_backend_only"]),
                            "physical_split": "train",
                            "basic_view_sha256": str(basic["view_sha256"]),
                            "exact_signature": exact,
                            "near_signature": near,
                            "basic_sufficient": bool(row["basic_sufficient"]),
                            "supporting_evidence_families_json": str(
                                row["supporting_evidence_families_json"]
                            ),
                        }
                    )
            else:
                per_class[label]["excluded"] += 1

    overlap = {
        "train_validation": len(formal_ids["train"] & formal_ids["validation"]),
        "train_test": len(formal_ids["train"] & formal_ids["test"]),
        "validation_test": len(formal_ids["validation"] & formal_ids["test"]),
    }
    if any(overlap.values()):
        raise ValueError(f"formal sample identity overlap: {overlap}")

    candidate_rows: list[dict[str, Any]] = []
    selection_stats: dict[str, Any] = {}
    for label in FINAL_MAIN_CLASSES:
        source = selected_input[label]
        selected = select_diversity_aware(
            source,
            budget=class_budget,
            maximum_per_exact=max_per_exact,
            seed=seed,
        )
        exact_source_counts = Counter(row["exact_signature"] for row in source)
        bounded_capacity = sum(
            min(max_per_exact, count) for count in exact_source_counts.values()
        )
        expected = min(class_budget, bounded_capacity)
        if len(selected) != expected:
            raise ValueError(f"selection underfilled for {label}")
        candidate_rows.extend(selected)
        selection_stats[label] = {
            "eligible_train": len(source),
            "selected": len(selected),
            "bounded_selection_capacity": bounded_capacity,
            "budget_underfill_reason": (
                "EXACT_MULTIPLICITY_CAP" if expected < class_budget else None
            ),
            "exact_groups_available": len({row["exact_signature"] for row in source}),
            "exact_groups_selected": len({row["exact_signature"] for row in selected}),
            "near_groups_available": len({row["near_signature"] for row in source}),
            "near_groups_selected": len({row["near_signature"] for row in selected}),
            "maximum_selected_per_exact": max(
                Counter(row["exact_signature"] for row in selected).values(), default=0
            ),
        }

    assignment_path = output_root / "assignments/observable_dataset_v3_assignments.parquet"
    candidate_path = output_root / "sft_candidates/plan_b_2048_per_class.parquet"
    _atomic_parquet(assignment_path, assignments)
    _atomic_parquet(candidate_path, candidate_rows)
    current_counts = {
        label: {
            "original_n": preflight["per_class"][label]["original_n"],
            "eligible_n": preflight["per_class"][label]["eligible_n"],
            "train_n": per_class[label]["train"],
            "validation_n": per_class[label]["validation"],
            "test_n": per_class[label]["test"],
            "excluded_n": per_class[label]["excluded"],
            "retain_main_class": label in FINAL_MAIN_CLASSES,
        }
        for label in sorted(per_class)
    }
    manifest = {
        "DATASET_V3_FREEZE_STATUS": "PASS",
        "freeze_version": FREEZE_VERSION,
        "dataset_version": OBSERVABLE_DATASET_VERSION,
        "eligibility_policy_version": ELIGIBILITY_POLICY_VERSION,
        "final_main_classes": list(FINAL_MAIN_CLASSES),
        "final_main_class_count": len(FINAL_MAIN_CLASSES),
        "excluded_candidate_roles": EXCLUDED_CANDIDATE_ROLES,
        "split_protocol": "CONSTRAINED_CHRONOLOGICAL_BOUNDARY_V2_PER_SPLIT_ELIGIBILITY_FILTERED",
        "formal_counts": {
            split: sum(per_class[label][split] for label in FINAL_MAIN_CLASSES)
            for split in FORMAL_SPLITS
        },
        "per_class": current_counts,
        "generic_main": {split: 0 for split in FORMAL_SPLITS},
        "unobservable_main": {split: 0 for split in FORMAL_SPLITS},
        "sample_identity_overlap": overlap,
        "exact_model_view_cross_split_collision_groups": sum(
            bool(mask & (mask - 1)) for mask in exact_masks.values()
        ),
        "near_signature_cross_split_collision_groups": sum(
            bool(mask & (mask - 1)) for mask in near_masks.values()
        ),
        "sft_candidate_selection": {
            "version": SELECTION_VERSION,
            "seed": seed,
            "class_budget": class_budget,
            "max_per_exact_group": max_per_exact,
            "total": len(candidate_rows),
            "classes": selection_stats,
        },
        "source_preflight": _artifact(preflight_path),
        "external_artifacts": {
            "assignments": _artifact(assignment_path),
            "sft_candidates": _artifact(candidate_path),
        },
    }
    manifest["manifest_content_digest"] = content_digest(
        canonical_json({key: value for key, value in manifest.items() if key != "manifest_content_digest"})
    )
    external_manifest = output_root / "manifests/observable_dataset_v3_freeze.json"
    _atomic_json(external_manifest, manifest)
    tracked = json.loads(canonical_json(manifest))
    for artifact in tracked["external_artifacts"].values():
        artifact["path"] = "GIT_EXTERNAL"
    tracked["source_preflight"]["path"] = "GIT_EXTERNAL"
    _atomic_json(tracked_manifest, tracked)
    print(
        f"DATASET_V3_FREEZE_STATUS=PASS classes={len(FINAL_MAIN_CLASSES)} "
        f"candidates={len(candidate_rows)}",
        flush=True,
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("/root/autodl-tmp/processed/observable_dataset_v3"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("/root/autodl-tmp/processed/observable_dataset_v3_freeze"),
    )
    parser.add_argument(
        "--tracked-manifest",
        type=Path,
        default=Path("reports/training_readiness/observable_dataset_v3_freeze_manifest.json"),
    )
    parser.add_argument("--class-budget", type=int, default=2048)
    parser.add_argument("--max-per-exact", type=int, default=16)
    args = parser.parse_args()
    freeze(
        source_root=args.source_root.resolve(),
        output_root=args.output_root.resolve(),
        tracked_manifest=args.tracked_manifest.resolve(),
        class_budget=args.class_budget,
        max_per_exact=args.max_per_exact,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
