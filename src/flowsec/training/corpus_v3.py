from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable

import pyarrow.parquet as pq

from .contracts import (
    EvidenceDomain,
    EvidenceEnvelope,
    EvidenceSnapshotV2,
    EvidenceStateV2,
    EvidenceTrustV1,
    NearValidationRecordV1,
    SFT_CORPUS_VERSION_V3,
    SFTRecordV2,
    canonical_json,
    content_digest,
)
from .materialization import sha256_file
from .prompts import (
    TEACHER_V2_PROMPT_VERSION,
    TRAFFIC_EXPERT_PROMPT_VERSION_V3,
    teacher_v2_prompt_v2,
    traffic_expert_prompt_v3,
)
from .serialization import COMPACT_SERIALIZATION_CANDIDATE, render_training_input
from .teacher import validate_teacher_v2_annotation


CORPUS_BUILD_VERSION = "OBSERVABLE_SFT_CORPUS_V3_BUILDER_V1"
VALIDATION_VERSION = "OBSERVABLE_KNOWN_VALIDATION_V3"
CLASS_MAP_VERSION = "OBSERVABLE_MAIN_CLASS_MAP_V3"
SUPERVISION_CONTRACT = "CLASSIFICATION_SUFFICIENCY_DECOUPLED_MULTI_GAP_V2"


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def atomic_jsonl(path: Path, values: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for value in values:
            handle.write(canonical_json(value) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def basic_v2_envelopes(sample_id: str, view: dict[str, Any]) -> tuple[EvidenceEnvelope, ...]:
    """Project a Basic-v2 view without backend identity or split metadata."""

    def envelope(
        kind: str, content: dict[str, Any], *, payload: bool = False
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
            metadata={"bounded": True, "strictly_past_only": False},
        )

    metadata = {
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
        envelope("basic_metadata", metadata),
        envelope("sanitized_payload", payload, payload=True),
    )


def _load_snapshots(snapshot_manifest_path: Path) -> tuple[list[EvidenceSnapshotV2], dict[str, Any]]:
    manifest = json.loads(snapshot_manifest_path.read_text(encoding="utf-8"))
    if manifest.get("TEACHER_V2_SNAPSHOT_STATUS") != "PASS":
        raise ValueError("Teacher-v2 snapshot universe is not PASS")
    path = Path(manifest["snapshots"]["path"])
    if sha256_file(path) != manifest["snapshots"]["sha256"]:
        raise ValueError("Teacher-v2 snapshot digest mismatch")
    snapshots = [
        EvidenceSnapshotV2.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(snapshots) != int(manifest["snapshot_count"]):
        raise ValueError("Teacher-v2 snapshot count mismatch")
    return snapshots, manifest


def _load_annotations(
    snapshots: list[EvidenceSnapshotV2], annotation_root: Path
) -> dict[str, dict[str, Any]]:
    manifest = json.loads((annotation_root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "PASS":
        raise ValueError("Teacher-v2 bulk manifest is not PASS")
    if manifest.get("prompt_version") != TEACHER_V2_PROMPT_VERSION:
        raise ValueError("Teacher-v2 bulk prompt version mismatch")
    if manifest.get("prompt_digest") != teacher_v2_prompt_v2().digest:
        raise ValueError("Teacher-v2 bulk prompt digest mismatch")
    if int(manifest.get("valid_count", -1)) != len(snapshots):
        raise ValueError("Teacher-v2 bulk does not cover the frozen state universe")

    annotations: dict[str, dict[str, Any]] = {}
    for snapshot in snapshots:
        path = annotation_root / "records" / f"{snapshot.evidence_state_id}.json"
        if not path.is_file():
            raise ValueError(f"missing Teacher-v2 annotation: {snapshot.evidence_state_id}")
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("validation_result") != "PASS":
            raise ValueError("non-PASS Teacher-v2 record entered corpus join")
        if value.get("evidence_state_id") != snapshot.evidence_state_id:
            raise ValueError("Teacher-v2 state identity mismatch")
        if value.get("evidence_state_digest") != snapshot.source_digest:
            raise ValueError("Teacher-v2 source digest mismatch")
        if value.get("teacher_prompt_version") != TEACHER_V2_PROMPT_VERSION:
            raise ValueError("Teacher-v2 record prompt version mismatch")
        if value.get("teacher_prompt_digest") != teacher_v2_prompt_v2().digest:
            raise ValueError("Teacher-v2 record prompt digest mismatch")
        validate_teacher_v2_annotation(value["normalized_target"], snapshot)
        annotations[snapshot.evidence_state_id] = value
    return annotations


def _distribution(values: Iterable[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def build_sft_corpus(
    *,
    snapshot_manifest_path: Path,
    annotation_root: Path,
    freeze_manifest_path: Path,
    output_root: Path,
    classes: tuple[str, ...],
) -> dict[str, Any]:
    snapshots, snapshot_manifest = _load_snapshots(snapshot_manifest_path)
    annotations = _load_annotations(snapshots, annotation_root)
    freeze = json.loads(freeze_manifest_path.read_text(encoding="utf-8"))
    if freeze.get("DATASET_V3_FREEZE_STATUS") != "PASS":
        raise ValueError("Observable Dataset-v3 freeze is not PASS")
    if tuple(freeze.get("final_main_classes") or ()) != classes:
        raise ValueError("active class map disagrees with Dataset-v3 freeze")
    if snapshot_manifest.get("dataset_freeze_digest") != freeze.get("manifest_content_digest"):
        raise ValueError("snapshot universe and Dataset-v3 freeze disagree")
    class_map = {label: index for index, label in enumerate(classes)}

    raw_state_counts = Counter(item.sample_id for item in snapshots)
    snapshots_by_session: defaultdict[str, list[EvidenceSnapshotV2]] = defaultdict(list)
    for snapshot in snapshots:
        snapshots_by_session[snapshot.sample_id].append(snapshot)
    retained_snapshots: list[EvidenceSnapshotV2] = []
    dropped_terminal_sessions = Counter()
    dropped_post_sufficient_states = Counter()
    for session_snapshots in snapshots_by_session.values():
        targets = [
            validate_teacher_v2_annotation(
                annotations[item.evidence_state_id]["normalized_target"], item
            )
            for item in session_snapshots
        ]
        label = session_snapshots[0].fine_label
        # A controlled trajectory that remains insufficient after every
        # eligibility-required state cannot provide clean SFT supervision.
        # Preserve its raw Teacher record externally, but quarantine the whole
        # trajectory from the formal corpus rather than rewriting semantics.
        if not targets[-1].evidence_sufficient:
            dropped_terminal_sessions[label] += 1
            continue
        # Runtime must stop requesting Evidence once the current state is
        # sufficient.  Later states are counterfactual and may produce the
        # impossible true->false transition, so retain through first success.
        for index, (snapshot, target) in enumerate(zip(session_snapshots, targets, strict=True)):
            retained_snapshots.append(snapshot)
            if target.evidence_sufficient:
                dropped_post_sufficient_states[label] += len(session_snapshots) - index - 1
                break
    snapshots = retained_snapshots
    state_counts = Counter(item.sample_id for item in snapshots)
    primary_counts = Counter(
        item.sample_id for item in snapshots if item.classification_supervision_valid
    )
    if set(primary_counts.values()) != {1} or set(primary_counts) != set(state_counts):
        raise ValueError("every SFT session must have exactly one Basic-v2 primary")
    if max(state_counts.values(), default=0) > 3:
        raise ValueError("SFT state construction exceeds one primary plus two auxiliaries")

    records: list[SFTRecordV2] = []
    snapshot_by_state = {item.evidence_state_id: item for item in snapshots}
    for snapshot in snapshots:
        value = annotations[snapshot.evidence_state_id]
        annotation = validate_teacher_v2_annotation(value["normalized_target"], snapshot)
        target_value = annotation.model_dump(mode="json")
        target_value.pop("teacher_confidence", None)
        target = EvidenceStateV2.model_validate(target_value)
        request_id = value.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            raise ValueError("Teacher-v2 annotation lacks provider request identity")
        record = SFTRecordV2(
            sample_id=snapshot.sample_id,
            evidence_state_id=snapshot.evidence_state_id,
            fine_label=snapshot.fine_label,
            class_index=class_map[snapshot.fine_label],
            classification_ce_eligible=snapshot.classification_supervision_valid,
            state_role=("primary" if snapshot.classification_supervision_valid else "auxiliary"),
            serialized_model_input=render_training_input(
                traffic_expert_prompt_v3(),
                snapshot.evidence,
                serialization_version=COMPACT_SERIALIZATION_CANDIDATE,
            ),
            evidence_state_target=target,
            stage_type=snapshot.stage_type,
            available_capability_mask=snapshot.available_capabilities,
            prompt_version=TRAFFIC_EXPERT_PROMPT_VERSION_V3,
            serialization_version=COMPACT_SERIALIZATION_CANDIDATE,
            teacher_annotation_digest=content_digest(value["normalized_target"]),
            teacher_model=str(value["model"]),
            teacher_prompt_digest=str(value["teacher_prompt_digest"]),
            teacher_request_id=request_id,
            dataset_digest=str(freeze["manifest_content_digest"]),
            session_weight=1.0 / state_counts[snapshot.sample_id],
        )
        records.append(record)

    if len(records) != len(snapshots) or set(item.fine_label for item in records) != set(classes):
        raise ValueError("formal v3 corpus lost a state or active class")
    weights: defaultdict[str, float] = defaultdict(float)
    for item in records:
        weights[item.sample_id] += item.session_weight
    invalid_weights = sum(abs(value - 1.0) > 1e-9 for value in weights.values())
    if invalid_weights:
        raise ValueError("session-normalized SFT weights do not sum to one")

    corpus_path = output_root / "sft_corpus/final/observable_sft_corpus_v3.jsonl"
    atomic_jsonl(corpus_path, (item.model_dump(mode="json") for item in records))
    class_distribution = _distribution(item.fine_label for item in records)
    primary_distribution = _distribution(
        item.fine_label for item in records if item.classification_ce_eligible
    )
    sufficiency = _distribution(
        "sufficient" if item.evidence_state_target.evidence_sufficient else "insufficient"
        for item in records
    )
    gap_distribution = _distribution(
        family.value
        for item in records
        for family in item.evidence_state_target.missing_evidence
    )
    gap_cardinality = Counter(
        len(item.evidence_state_target.missing_evidence)
        for item in records
        if not item.evidence_state_target.evidence_sufficient
    )
    duplicate_inputs = Counter(content_digest(item.serialized_model_input) for item in records)
    labels_by_input: defaultdict[str, set[str]] = defaultdict(set)
    for item in records:
        labels_by_input[content_digest(item.serialized_model_input)].add(item.fine_label)
    prohibited = (
        '"fine_label"', '"coarse_label"', '"sample_id"', '"split"',
        '"ku_role"', '"dataset_name"', '"capture_id"', '"source_path"',
    )
    prohibited_count = sum(
        any(token in item.serialized_model_input.casefold() for token in prohibited)
        for item in records
    )
    target_verdict_count = sum(
        any(
            token in canonical_json(item.evidence_state_target.model_dump(mode="json")).casefold()
            for token in ('"fine_label"', '"coarse_label"', "label is", "classified as")
        )
        for item in records
    )
    primary_by_session = Counter(
        item.sample_id for item in records if item.classification_ce_eligible
    )
    manifest = {
        "status": "PASS",
        "version": SFT_CORPUS_VERSION_V3,
        "builder_version": CORPUS_BUILD_VERSION,
        "supervision_contract": SUPERVISION_CONTRACT,
        "teacher_prompt_version": TEACHER_V2_PROMPT_VERSION,
        "teacher_prompt_digest": teacher_v2_prompt_v2().digest,
        "traffic_expert_prompt_version": TRAFFIC_EXPERT_PROMPT_VERSION_V3,
        "record_count": len(records),
        "unique_sessions": len(state_counts),
        "states_per_session": dict(sorted(Counter(state_counts.values()).items())),
        "class_distribution": class_distribution,
        "stage_distribution": _distribution(item.stage_type.value for item in records),
        "classification_supervised_count": sum(item.classification_ce_eligible for item in records),
        "classification_masked_count": sum(not item.classification_ce_eligible for item in records),
        "classification_supervised_unique_sessions": len(primary_by_session),
        "classification_supervised_class_distribution": primary_distribution,
        "classification_supervised_class_coverage": len(primary_distribution),
        "classification_supervised_states_per_session_max": max(primary_by_session.values()),
        "state_role_distribution": _distribution(item.state_role for item in records),
        "evidence_sufficiency_distribution": sufficiency,
        "gap_type_distribution": _distribution(item.evidence_state_target.gap_type.value for item in records),
        "missing_evidence_distribution": gap_distribution,
        "missing_evidence_cardinality": dict(sorted(gap_cardinality.items())),
        "single_gap_rate": gap_cardinality[1] / len(records),
        "multi_gap_rate": sum(value for key, value in gap_cardinality.items() if key > 1) / len(records),
        "exact_serialized_input_duplicate_groups": sum(value > 1 for value in duplicate_inputs.values()),
        "label_collision_count": sum(len(value) > 1 for value in labels_by_input.values()),
        "model_input_backend_identity_count": sum(
            item.sample_id in item.serialized_model_input for item in records
        ),
        "prohibited_model_input_key_count": prohibited_count,
        "target_class_verdict_count": target_verdict_count,
        "invalid_session_weight_count": invalid_weights,
        "teacher_pass_count": len(annotations),
        "teacher_quarantine_count": 0,
        "raw_teacher_snapshot_count": sum(raw_state_counts.values()),
        "raw_teacher_unique_sessions": len(raw_state_counts),
        "trajectory_curation": {
            "policy": "TERMINAL_SUFFICIENT_AND_STOP_AFTER_FIRST_SUFFICIENT_V1",
            "dropped_terminal_insufficient_sessions": sum(dropped_terminal_sessions.values()),
            "dropped_terminal_insufficient_by_class": dict(sorted(dropped_terminal_sessions.items())),
            "dropped_post_sufficient_states": sum(dropped_post_sufficient_states.values()),
            "dropped_post_sufficient_by_class": dict(sorted(dropped_post_sufficient_states.items())),
            "raw_teacher_cache_modified": False,
            "semantic_target_rewritten": False,
        },
        "token_lengths": {"status": "PENDING_EXACT_TOKENIZER_AUDIT", "overflow_count": -1},
        "artifacts": {
            "corpus": {
                "path": str(corpus_path),
                "size_bytes": corpus_path.stat().st_size,
                "sha256": sha256_file(corpus_path),
            }
        },
        "validation_count": 0,
        "test_count": 0,
        "u_dev_count": 0,
        "u_final_count": 0,
        "sft_run": False,
    }
    zero_gates = (
        "label_collision_count", "model_input_backend_identity_count",
        "prohibited_model_input_key_count", "target_class_verdict_count",
        "invalid_session_weight_count", "teacher_quarantine_count",
    )
    if any(int(manifest[key]) != 0 for key in zero_gates):
        manifest["status"] = "FAIL"
    manifest["artifact_digest"] = content_digest(manifest["artifacts"])
    atomic_json(output_root / "sft_corpus/final/manifest.json", manifest)
    return manifest


def _select_diverse_validation(
    rows: list[dict[str, Any]], *, per_class_limit: int
) -> list[dict[str, Any]]:
    groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row["exact_signature"])].append(row)
    for values in groups.values():
        values.sort(key=lambda item: content_digest(["validation_v3", item["session_id"]]))
    ordered_groups = sorted(groups, key=lambda key: content_digest(["validation_v3_group", key]))
    selected: list[dict[str, Any]] = []
    offsets = {key: 0 for key in ordered_groups}
    while len(selected) < min(per_class_limit, len(rows)):
        advanced = False
        for key in ordered_groups:
            index = offsets[key]
            if index < len(groups[key]):
                selected.append(groups[key][index])
                offsets[key] += 1
                advanced = True
                if len(selected) == per_class_limit:
                    break
        if not advanced:
            break
    return selected


def build_validation(
    *,
    freeze_manifest_path: Path,
    evidence_root: Path,
    output_root: Path,
    classes: tuple[str, ...],
    per_class_limit: int = 1000,
) -> dict[str, Any]:
    freeze = json.loads(freeze_manifest_path.read_text(encoding="utf-8"))
    assignments_path = Path(freeze["external_artifacts"]["assignments"]["path"])
    if sha256_file(assignments_path) != freeze["external_artifacts"]["assignments"]["sha256"]:
        raise ValueError("Dataset-v3 assignment digest mismatch")
    candidate_path = Path(freeze["external_artifacts"]["sft_candidates"]["path"])
    if sha256_file(candidate_path) != freeze["external_artifacts"]["sft_candidates"]["sha256"]:
        raise ValueError("Dataset-v3 SFT candidate digest mismatch")
    training_signatures = pq.read_table(
        candidate_path, columns=["exact_signature", "near_signature"]
    ).to_pylist()
    training_exact = {str(row["exact_signature"]) for row in training_signatures}
    training_near = {str(row["near_signature"]) for row in training_signatures}
    wanted_by_capture: defaultdict[str, dict[str, str]] = defaultdict(dict)
    for row in pq.read_table(assignments_path).to_pylist():
        if (
            row["final_split"] == "validation"
            and bool(row["classification_ce_eligible"])
            and bool(row["full_observational_sufficient"])
            and str(row["fine_label"]) in classes
        ):
            wanted_by_capture[str(row["capture_id_backend_only"])][str(row["session_id"])] = str(row["fine_label"])

    candidates_by_class: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    view_by_id: dict[str, dict[str, Any]] = {}
    for capture, wanted in sorted(wanted_by_capture.items()):
        for row in pq.read_table(evidence_root / "basic_views" / f"{capture}.parquet").to_pylist():
            sample_id = str(row["session_id_backend_only"])
            if sample_id not in wanted:
                continue
            view_by_id[sample_id] = json.loads(row["view_json"])
            candidates_by_class[wanted[sample_id]].append(
                {
                    "session_id": sample_id,
                    "fine_label": wanted[sample_id],
                    "exact_signature": str(row["exact_signature"]),
                    "near_signature": str(row["near_signature"]),
                }
            )
    if set(candidates_by_class) != set(classes):
        raise ValueError("validation Evidence-v2 coverage lost an active class")

    exact_clean_by_class = {
        label: [
            row for row in candidates_by_class[label]
            if row["exact_signature"] not in training_exact
        ]
        for label in classes
    }
    if any(not rows for rows in exact_clean_by_class.values()):
        raise ValueError("exact-eval-clean validation lost an active class")

    selected = [
        row
        for label in classes
        for row in _select_diverse_validation(
            exact_clean_by_class[label], per_class_limit=per_class_limit
        )
    ]
    class_map = {label: index for index, label in enumerate(classes)}
    records = []
    for row in selected:
        sample_id = row["session_id"]
        evidence = basic_v2_envelopes(sample_id, view_by_id[sample_id])
        records.append(
            NearValidationRecordV1(
                sample_id=sample_id,
                fine_label=row["fine_label"],
                class_index=class_map[row["fine_label"]],
                serialized_model_input=render_training_input(
                    traffic_expert_prompt_v3(),
                    evidence,
                    serialization_version=COMPACT_SERIALIZATION_CANDIDATE,
                ),
                prompt_version=TRAFFIC_EXPERT_PROMPT_VERSION_V3,
                serialization_version=COMPACT_SERIALIZATION_CANDIDATE,
                dataset_digest=str(freeze["manifest_content_digest"]),
            )
        )
    validation_path = output_root / "validation/near_known_validation_v3.jsonl"
    atomic_jsonl(validation_path, (item.model_dump(mode="json") for item in records))
    distribution = _distribution(item.fine_label for item in records)
    manifest = {
        "status": "PASS",
        "version": VALIDATION_VERSION,
        "selection_policy": "CLASS_BALANCED_EXACT_DIVERSITY_DETERMINISTIC_V1",
        "evaluation_view": "EXACT_EVAL_CLEAN",
        "per_class_limit": per_class_limit,
        "record_count": len(records),
        "class_distribution": distribution,
        "class_coverage": len(distribution),
        "source_validation_distribution": {
            label: len(candidates_by_class[label]) for label in classes
        },
        "exact_clean_available_distribution": {
            label: len(exact_clean_by_class[label]) for label in classes
        },
        "near_clean_available_distribution": {
            label: sum(row["near_signature"] not in training_near for row in candidates_by_class[label])
            for label in classes
        },
        "exact_train_collision_excluded_count": sum(
            len(candidates_by_class[label]) - len(exact_clean_by_class[label])
            for label in classes
        ),
        "selected_exact_train_collision_count": 0,
        "source_split": "validation",
        "source_role": "K_known",
        "train_count": 0,
        "test_count": 0,
        "u_dev_count": 0,
        "u_final_count": 0,
        "artifacts": {
            "validation_corpus": {
                "path": str(validation_path),
                "size_bytes": validation_path.stat().st_size,
                "sha256": sha256_file(validation_path),
            }
        },
    }
    manifest["artifact_digest"] = content_digest(manifest["artifacts"])
    atomic_json(output_root / "validation/manifest.json", manifest)
    return manifest


def update_token_audit(
    *,
    corpus_manifest_path: Path,
    validation_manifest_path: Path,
    tokenize: Callable[[str], list[int]],
    max_sequence_length: int,
) -> dict[str, Any]:
    corpus_manifest = json.loads(corpus_manifest_path.read_text(encoding="utf-8"))
    validation_manifest = json.loads(validation_manifest_path.read_text(encoding="utf-8"))
    corpus_path = Path(corpus_manifest["artifacts"]["corpus"]["path"])
    validation_path = Path(validation_manifest["artifacts"]["validation_corpus"]["path"])
    lengths: list[int] = []
    for line in corpus_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = SFTRecordV2.model_validate_json(line)
        target = canonical_json(item.evidence_state_target.model_dump(mode="json"))
        lengths.append(len(tokenize(item.serialized_model_input)) + len(tokenize(target)))
    validation_lengths = [
        len(tokenize(NearValidationRecordV1.model_validate_json(line).serialized_model_input))
        for line in validation_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    ordered = sorted(lengths)
    def percentile(q: float) -> int:
        return ordered[int(round((len(ordered) - 1) * q))]
    audit = {
        "status": "PASS" if max(lengths) <= max_sequence_length else "FAIL",
        "tokenizer_mode": "LOCAL_TOKENIZER_ONLY_NO_MODEL_INFERENCE",
        "max_sequence_length": max_sequence_length,
        "corpus_count": len(lengths),
        "corpus_max": max(lengths),
        "corpus_p50": percentile(0.5),
        "corpus_p95": percentile(0.95),
        "corpus_p99": percentile(0.99),
        "validation_count": len(validation_lengths),
        "validation_max": max(validation_lengths),
        "overflow_count": sum(value > max_sequence_length for value in lengths),
    }
    corpus_manifest["token_lengths"] = audit
    if audit["status"] != "PASS":
        corpus_manifest["status"] = "FAIL"
    atomic_json(corpus_manifest_path, corpus_manifest)
    atomic_json(corpus_manifest_path.parent.parent.parent / "manifests/tokenizer_length_audit_v3.json", audit)
    return audit


def write_class_map(path: Path, classes: tuple[str, ...]) -> dict[str, Any]:
    value = {
        "version": CLASS_MAP_VERSION,
        "status": "PASS",
        "Near": {"K_known": list(classes)},
        "class_index": {label: index for index, label in enumerate(classes)},
        "u_final_content_accessed": False,
    }
    atomic_json(path, value)
    return value
