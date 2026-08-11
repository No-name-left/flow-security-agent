from __future__ import annotations

import hashlib
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from flowsec.production.runtime_adapter import (
    ProductionGraphContextTool,
    ProductionPacketExpansionTool,
    ProductionParquetEvidenceStore,
    ProductionSafeAdapter,
    ProductionSampleRequest,
    ProductionTemporalContextTool,
)
from flowsec.runtime.contracts import AgentAction, RuntimePhase, ToolRequest, ToolStatus

from .contracts import (
    RL_PROMPT_POOL_VERSION,
    EvidenceDomain,
    EvidenceEnvelope,
    EvidenceSnapshot,
    EvidenceStateV1,
    EvidenceTrustV1,
    NearValidationRecordV1,
    RLPromptRecordV1,
    SFTRecordV1,
    StageType,
    canonical_json,
    content_digest,
)
from .evidence import (
    ApplicationEvidenceV1,
    SanitizedPayloadV1,
    application_envelope,
    payload_envelope,
)
from .prompts import (
    TRAFFIC_EXPERT_PROMPT_VERSION,
    TEACHER_PROMPT_VERSION,
    teacher_prompt_v3,
    traffic_expert_prompt_v2,
)
from .rag import HybridRagIndex, build_safe_query, rag_envelope
from .serialization import COMPACT_SERIALIZATION_CANDIDATE, render_training_input


SNAPSHOT_UNIVERSE_VERSION = "NEAR_EVIDENCE_SNAPSHOT_UNIVERSE_V1"
CORPUS_BUILDER_VERSION = "NEAR_MULTI_STAGE_CORPUS_BUILDER_V1"
RL_SAMPLING_SEED = 20260809
RL_PROMPT_TARGET = 6000


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(chunk_size):
            digest.update(block)
    return digest.hexdigest()


def _bucket(sample_id: str, purpose: str, modulo: int = 100) -> int:
    return int(content_digest([RL_SAMPLING_SEED, purpose, sample_id])[:16], 16) % modulo


def _runtime_envelope(item: Any, evidence_type: str) -> EvidenceEnvelope:
    return EvidenceEnvelope(
        evidence_id=item.evidence_id,
        evidence_type=evidence_type,
        domain=EvidenceDomain.OBSERVATION,
        trust=EvidenceTrustV1.TRUSTED_OBSERVATION,
        content=json.loads(item.content),
        provenance=item.provenance,
        metadata=item.metadata,
    )


def _sidecar_rows(paths: Iterable[Path], column: str) -> dict[str, dict[str, Any]]:
    import pyarrow.parquet as pq

    rows: dict[str, dict[str, Any]] = {}
    for path in sorted(paths):
        for row in pq.read_table(path).to_pylist():
            sample_id = str(row.get("sample_id") or "")
            if not sample_id:
                continue
            if sample_id in rows:
                raise ValueError(f"duplicate sidecar identity: {sample_id}")
            rows[sample_id] = json.loads(str(row[column]))
    return rows


def load_sidecars(sidecar_root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    root = Path(sidecar_root)
    application = _sidecar_rows((root / "application/captures").glob("*.parquet"), "application_json")
    payload = _sidecar_rows(
        (root / "sanitized_payload/captures").glob("*.parquet"), "payload_json"
    )
    return application, payload


def _query_summary(evidence: tuple[EvidenceEnvelope, ...]) -> str:
    allowed_keys = {
        "evidence_type",
        "l3_protocol",
        "l4_protocol",
        "handshake_state",
        "kind",
        "method",
        "status",
        "protocol",
        "parameter_count",
        "past_only",
        "node_roles",
        "repeated_relation",
    }
    tokens: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in allowed_keys:
                    if isinstance(item, list):
                        tokens.extend(str(entry) for entry in item[:4])
                    elif isinstance(item, (str, int, float, bool)):
                        tokens.append(str(item))
                visit(item)
        elif isinstance(value, list):
            for item in value[:16]:
                visit(item)

    semantic_payload_terms = {
        "sql": "sql database query",
        "union": "union select database query",
        "select": "select database query",
        "username": "credential authentication username",
        "password": "credential authentication password",
        "login": "credential authentication login",
        "multipart": "multipart file upload",
        "filename": "filename file upload",
        "content-disposition": "multipart file upload",
        "upload": "file upload",
        "command": "command execution",
        "shell": "shell command execution",
        "exec": "command execution",
        "post": "http post request body",
        "get": "http get request",
    }
    for item in evidence:
        tokens.append(item.evidence_type)
        visit(item.content)
        if item.evidence_type == "sanitized_payload":
            safe_text = canonical_json(item.content).casefold()
            for needle, interpretation in semantic_payload_terms.items():
                if needle in safe_text:
                    tokens.extend(interpretation.split())
    summary = " ".join(tokens[:80]) or "bounded network session observations"
    return summary[:360]


def _state_id(sample_id: str, stage: StageType, evidence: tuple[EvidenceEnvelope, ...]) -> str:
    return "state_" + content_digest(
        [SNAPSHOT_UNIVERSE_VERSION, sample_id, stage.value, [item.evidence_id for item in evidence]]
    )[:24]


def _controlled_lower_evidence(initial: EvidenceEnvelope, sample_id: str) -> EvidenceEnvelope:
    summary = initial.content.get("session_summary", {})
    return EvidenceEnvelope(
        evidence_id="ev_controlled_" + content_digest([sample_id, "packet_mask_v1"])[:20],
        evidence_type="controlled_mask",
        domain=EvidenceDomain.OBSERVATION,
        trust=EvidenceTrustV1.TRUSTED_OBSERVATION,
        content={
            "evidence_type": "controlled_lower_evidence",
            "whole_session_summary": summary,
            "mask_policy": "ordered_packet_observations_withheld",
        },
        provenance="offline_controlled_mask_v1",
        metadata={"synthetic_observation": False, "classification_target_masked": True},
    )


def _tool_evidence(adapted: Any, tool_type: type, request: ToolRequest, kind: str) -> EvidenceEnvelope | None:
    tool = next(item for item in adapted.tools if isinstance(item, tool_type))
    result = tool.execute(request, adapted.runtime_input.initial_evidence)
    if result.status is not ToolStatus.SUCCESS or not result.evidence:
        return None
    return _runtime_envelope(result.evidence[0], kind)


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def _write_jsonl(path: Path, values: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for value in values:
            handle.write(canonical_json(value) + chr(10))
    os.replace(temporary, path)


def _balanced_rl_selection(
    snapshots: list[EvidenceSnapshot], target: int
) -> list[EvidenceSnapshot]:
    strata: dict[tuple[str, str, bool], list[EvidenceSnapshot]] = defaultdict(list)
    for snapshot in snapshots:
        strata[(snapshot.fine_label, snapshot.stage_type.value, snapshot.classification_supervision_valid)].append(snapshot)
    for values in strata.values():
        values.sort(key=lambda item: content_digest([RL_SAMPLING_SEED, "rl", item.evidence_state_id]))
    keys = sorted(strata)
    selected: list[EvidenceSnapshot] = []
    offsets = Counter()
    while len(selected) < min(target, len(snapshots)):
        advanced = False
        for key in keys:
            index = offsets[key]
            if index < len(strata[key]):
                selected.append(strata[key][index])
                offsets[key] += 1
                advanced = True
                if len(selected) == target:
                    break
        if not advanced:
            break
    return selected


def build_snapshot_universe(
    production_root: Path,
    sidecar_root: Path,
    output_root: Path,
    *,
    rag_index: HybridRagIndex,
) -> dict[str, Any]:
    import pyarrow.parquet as pq

    production_root, output_root = Path(production_root), Path(output_root)
    candidate_path = production_root / "sft_candidates/preset=Near/part-00000.parquet"
    candidate_rows = pq.read_table(candidate_path).to_pylist()
    if len(candidate_rows) != 16979:
        raise ValueError("Near PLAN_B candidate count changed")
    for row in candidate_rows:
        if row.get("physical_split") != "train" or row.get("ku_role") != "K_known" or row.get("preset") != "Near":
            raise ValueError("candidate escaped Near K_known TRAIN")
    application_rows, payload_rows = load_sidecars(sidecar_root)
    candidate_ids = {str(row["sample_id"]) for row in candidate_rows}
    if not set(application_rows).issubset(candidate_ids) or not set(payload_rows).issubset(candidate_ids):
        raise ValueError("sidecar escaped the frozen candidate universe")

    store = ProductionParquetEvidenceStore(production_root)
    adapter = ProductionSafeAdapter(store)
    requests = [
        ProductionSampleRequest(
            sample_id=str(row["sample_id"]),
            dataset="Edge-IIoTset",
            split="train",
            phase=RuntimePhase.TRAIN,
            preset="Near",
        )
        for row in candidate_rows
    ]
    adapter.prefetch(requests)
    coarse_by_id = {
        request.sample_id: str(
            store.row(
                "sample_id_index",
                dataset="Edge-IIoTset",
                split="train",
                sample_id=request.sample_id,
                required=True,
            )["coarse_label"]
        )
        for request in requests
    }
    label_by_id = {str(row["sample_id"]): str(row["fine_label"]) for row in candidate_rows}
    source_dataset_digest = content_digest(
        [sha256_file(candidate_path), store.production_version, SNAPSHOT_UNIVERSE_VERSION]
    )

    primary_parts: list[dict[str, Any]] = []
    rag_queries: list[str] = []
    rag_positions: list[int] = []
    for request in requests:
        sample_id = request.sample_id
        adapted = adapter.adapt(request)
        initial_item = adapted.runtime_input.initial_evidence[0]
        initial = _runtime_envelope(initial_item, "initial")
        evidence: list[EvidenceEnvelope] = [initial]
        stage = StageType.INITIAL
        bucket = _bucket(sample_id, "primary_stage")
        if sample_id in payload_rows and bucket < 15:
            value = SanitizedPayloadV1.model_validate(payload_rows[sample_id])
            evidence.append(payload_envelope(sample_id, value))
            stage = StageType.PAYLOAD
        elif sample_id in application_rows and bucket < 30:
            value = ApplicationEvidenceV1.model_validate(application_rows[sample_id])
            evidence.append(application_envelope(sample_id, value))
            stage = StageType.APPLICATION
        elif bucket % 4 == 0:
            added = _tool_evidence(
                adapted,
                ProductionPacketExpansionTool,
                ToolRequest(action=AgentAction.EXPAND_PACKETS, parameters={"start_packet": 9, "end_packet": 16}),
                "packet",
            )
            if added:
                evidence.append(added)
                stage = StageType.PACKET
        elif bucket % 4 == 1:
            added = _tool_evidence(
                adapted,
                ProductionTemporalContextTool,
                ToolRequest(action=AgentAction.EXPAND_TEMPORAL_CONTEXT, parameters={"past_only": True, "window_seconds": 60.0}),
                "temporal",
            )
            if added:
                evidence.append(added)
                stage = StageType.TEMPORAL
        elif bucket % 4 == 2:
            added = _tool_evidence(
                adapted,
                ProductionGraphContextTool,
                ToolRequest(action=AgentAction.EXPAND_GRAPH_CONTEXT, parameters={"scope": "local"}),
                "relation",
            )
            if added:
                evidence.append(added)
                stage = StageType.RELATION

        available = tuple(
            sorted(item.capability.value for item in adapted.runtime_input.capabilities if item.available)
        )
        primary_parts.append(
            {
                "sample_id": sample_id,
                "fine_label": label_by_id[sample_id],
                "coarse_label": coarse_by_id[sample_id],
                "stage": stage,
                "available": available,
                "evidence": tuple(evidence),
            }
        )
        if _bucket(sample_id, "rag_exposure", 1000) < 70:
            rag_positions.append(len(primary_parts) - 1)
            rag_queries.append(
                build_safe_query(
                    visible_evidence_summary=_query_summary(tuple(evidence)),
                    evidence_gap="generic protocol and security behavior interpretation",
                )
            )

    retrievals = rag_index.retrieve_many(rag_queries, top_k=1)
    for position, result in zip(rag_positions, retrievals, strict=True):
        if result and result[0][1] > 0.0:
            chunk, score = result[0]
            primary_parts[position]["evidence"] = (
                *primary_parts[position]["evidence"],
                rag_envelope(chunk, score=score),
            )
            primary_parts[position]["stage"] = StageType.KNOWLEDGE

    snapshots: list[EvidenceSnapshot] = []
    primary_count = 0
    auxiliary_count = 0
    for part in primary_parts:
        evidence = tuple(part["evidence"])
        source_digest = content_digest([source_dataset_digest, [item.model_dump(mode="json") for item in evidence]])
        primary = EvidenceSnapshot(
            sample_id=part["sample_id"],
            evidence_state_id=_state_id(part["sample_id"], part["stage"], evidence),
            fine_label=part["fine_label"],
            coarse_label=part["coarse_label"],
            split="train",
            ku_role="K_known",
            stage_type=part["stage"],
            classification_supervision_valid=True,
            available_capabilities=part["available"],
            evidence=evidence,
            source_digest=source_digest,
        )
        snapshots.append(primary)
        primary_count += 1
        if _bucket(part["sample_id"], "auxiliary") < 35:
            controlled = (_controlled_lower_evidence(evidence[0], part["sample_id"]),)
            snapshots.append(
                EvidenceSnapshot(
                    sample_id=part["sample_id"],
                    evidence_state_id=_state_id(part["sample_id"], StageType.CONTROLLED_MASK, controlled),
                    fine_label=part["fine_label"],
                    coarse_label=part["coarse_label"],
                    split="train",
                    ku_role="K_known",
                    stage_type=StageType.CONTROLLED_MASK,
                    classification_supervision_valid=False,
                    available_capabilities=part["available"],
                    evidence=controlled,
                    source_digest=content_digest([source_dataset_digest, controlled[0].model_dump(mode="json")]),
                )
            )
            auxiliary_count += 1

    state_ids = [item.evidence_state_id for item in snapshots]
    if len(state_ids) != len(set(state_ids)):
        raise ValueError("snapshot state identities are not unique")
    snapshots_path = output_root / "sft_corpus/evidence_snapshot_universe_v1.jsonl"
    _write_jsonl(snapshots_path, (item.model_dump(mode="json") for item in snapshots))

    serialized_by_state = {
        item.evidence_state_id: render_training_input(
            traffic_expert_prompt_v2(),
            item.evidence,
            serialization_version=COMPACT_SERIALIZATION_CANDIDATE,
        )
        for item in snapshots
    }
    rl_snapshots = _balanced_rl_selection(snapshots, RL_PROMPT_TARGET)
    rl_records = [
        RLPromptRecordV1(
            prompt_id="rlp_" + content_digest([RL_PROMPT_POOL_VERSION, item.evidence_state_id])[:24],
            evidence_state_id=item.evidence_state_id,
            sample_id=item.sample_id,
            fine_label=item.fine_label,
            stage_type=item.stage_type,
            classification_supervision_valid=item.classification_supervision_valid,
            serialized_model_input=serialized_by_state[item.evidence_state_id],
        )
        for item in rl_snapshots
    ]
    rl_path = output_root / "rl_prompt_pool/near_rl_prompt_pool_v1.jsonl"
    _write_jsonl(rl_path, (item.model_dump(mode="json") for item in rl_records))

    class_counts = Counter(item.fine_label for item in snapshots)
    stage_counts = Counter(item.stage_type.value for item in snapshots)
    evidence_presence = Counter(
        evidence_type
        for item in snapshots
        for evidence_type in {evidence.evidence_type for evidence in item.evidence}
    )
    rl_class_counts = Counter(item.fine_label for item in rl_records)
    rl_stage_counts = Counter(item.stage_type.value for item in rl_records)
    input_digests = Counter(content_digest(value) for value in serialized_by_state.values())
    manifest = {
        "status": "PASS",
        "builder_version": CORPUS_BUILDER_VERSION,
        "snapshot_version": SNAPSHOT_UNIVERSE_VERSION,
        "scope": "Near PLAN_B K_known TRAIN only",
        "dataset_digest": source_dataset_digest,
        "candidate_sessions": len(candidate_rows),
        "unique_sessions": len({item.sample_id for item in snapshots}),
        "snapshot_count": len(snapshots),
        "primary_count": primary_count,
        "auxiliary_count": auxiliary_count,
        "classification_supervised_count": sum(item.classification_supervision_valid for item in snapshots),
        "classification_masked_count": sum(not item.classification_supervision_valid for item in snapshots),
        "states_per_session": dict(sorted(Counter(Counter(item.sample_id for item in snapshots).values()).items())),
        "class_distribution": dict(sorted(class_counts.items())),
        "stage_distribution": dict(sorted(stage_counts.items())),
        "application_state_count": evidence_presence["application"],
        "payload_state_count": evidence_presence["sanitized_payload"],
        "rag_state_count": evidence_presence["knowledge"],
        "evidence_presence_distribution": dict(sorted(evidence_presence.items())),
        "rag_exposure_rate": evidence_presence["knowledge"] / len(snapshots),
        "exact_serialized_input_duplicate_groups": sum(count > 1 for count in input_digests.values()),
        "teacher_status": "PENDING_EXTERNAL_ANNOTATION",
        "teacher_queue_count": len(snapshots),
        "formal_sft_record_count": 0,
        "rl_prompt_pool": {
            "version": RL_PROMPT_POOL_VERSION,
            "sampling_seed": RL_SAMPLING_SEED,
            "count": len(rl_records),
            "class_distribution": dict(sorted(rl_class_counts.items())),
            "stage_distribution": dict(sorted(rl_stage_counts.items())),
            "digest": sha256_file(rl_path),
        },
        "artifacts": {
            "snapshot_universe": {"path": str(snapshots_path), "sha256": sha256_file(snapshots_path)},
            "rl_prompt_pool": {"path": str(rl_path), "sha256": sha256_file(rl_path)},
        },
        "validation_count": 0,
        "test_count": 0,
        "u_dev_count": 0,
        "u_final_count": 0,
        "sft_run": False,
        "rl_run": False,
    }
    manifest["artifact_digest"] = content_digest(manifest["artifacts"])
    _atomic_json(output_root / "manifests/snapshot_corpus_rl_manifest.json", manifest)
    return manifest


def build_known_validation_corpus(
    production_root: Path,
    output_root: Path,
    preset_manifest: Path,
    *,
    per_class_limit: int = 100,
) -> dict[str, Any]:
    """Materialize a deterministic K-known validation-only classification asset."""

    import pyarrow.parquet as pq

    from .harness import load_near_class_map

    if per_class_limit < 1:
        raise ValueError("validation per-class limit must be positive")
    production_root = Path(production_root)
    classes, class_map = load_near_class_map(Path(preset_manifest))
    import pyarrow.dataset as ds

    index_root = (
        production_root
        / "sample_id_index/dataset=Edge-IIoTset/split=validation"
    )
    index_paths = sorted(index_root.glob("*.parquet"))
    if not index_paths:
        raise FileNotFoundError("Production validation index shards are unavailable")
    selected_by_class: dict[str, list[dict[str, Any]]] = {
        label: [] for label in classes
    }
    seen_exact: dict[str, set[str]] = {label: set() for label in classes}
    scanner = ds.dataset(index_root, format="parquet").scanner(
        columns=["sample_id", "fine_label", "exact_signature"],
        filter=ds.field("fine_label").isin(list(classes)),
    )
    for batch in scanner.to_batches():
        for row in batch.to_pylist():
            label = str(row["fine_label"])
            exact = str(row["exact_signature"])
            if len(selected_by_class[label]) >= per_class_limit or exact in seen_exact[label]:
                continue
            seen_exact[label].add(exact)
            selected_by_class[label].append(row)
    selected = [
        row
        for label in classes
        for row in selected_by_class[label]
    ]
    requests = [
        ProductionSampleRequest(
            sample_id=str(row["sample_id"]),
            dataset="Edge-IIoTset",
            split="validation",
            phase=RuntimePhase.VALIDATION,
            preset="Near",
        )
        for row in selected
    ]
    store = ProductionParquetEvidenceStore(production_root)
    adapter = ProductionSafeAdapter(store)
    adapter.prefetch(requests)
    row_by_id = {str(row["sample_id"]): row for row in selected}
    dataset_digest = content_digest(
        [
            [sha256_file(path) for path in index_paths],
            store.production_version,
            "NEAR_KNOWN_VALIDATION_V1",
        ]
    )
    records: list[NearValidationRecordV1] = []
    for request in requests:
        adapted = adapter.adapt(request)
        initial = _runtime_envelope(adapted.runtime_input.initial_evidence[0], "initial")
        label = str(row_by_id[request.sample_id]["fine_label"])
        records.append(
            NearValidationRecordV1(
                sample_id=request.sample_id,
                fine_label=label,
                class_index=class_map[label],
                serialized_model_input=render_training_input(
                    traffic_expert_prompt_v2(),
                    (initial,),
                    serialization_version=COMPACT_SERIALIZATION_CANDIDATE,
                ),
                prompt_version=TRAFFIC_EXPERT_PROMPT_VERSION,
                serialization_version=COMPACT_SERIALIZATION_CANDIDATE,
                dataset_digest=dataset_digest,
            )
        )
    output_root = Path(output_root)
    output_path = output_root / "near_known_validation_v1.jsonl"
    _write_jsonl(output_path, (item.model_dump(mode="json") for item in records))
    class_counts = Counter(item.fine_label for item in records)
    exact_diversity = Counter(
        str(row_by_id[item.sample_id]["exact_signature"]) for item in records
    )
    manifest = {
        "status": "PASS",
        "version": "NEAR_KNOWN_VALIDATION_V1",
        "scope": "Near K_known validation only; no test, U_dev, or U_final",
        "record_count": len(records),
        "class_distribution": dict(sorted(class_counts.items())),
        "class_count": len(class_counts),
        "exact_diversity": len(exact_diversity),
        "dataset_digest": dataset_digest,
        "u_dev_count": 0,
        "u_final_count": 0,
        "test_count": 0,
        "artifacts": {
            "validation_corpus": {
                "path": str(output_path),
                "sha256": sha256_file(output_path),
            }
        },
    }
    manifest["artifact_digest"] = content_digest(manifest["artifacts"])
    _atomic_json(output_root / "manifest.json", manifest)
    return manifest


def finalize_sft_corpus(
    snapshot_manifest: Path,
    annotation_root: Path,
    output_root: Path,
    preset_manifest: Path,
    *,
    tokenize: Any,
    max_sequence_length: int = 3072,
) -> dict[str, Any]:
    """Join validated Teacher records only; never invent or replace missing annotations."""

    from .harness import load_near_class_map
    from .serialization import token_length_report
    from .teacher import validate_teacher_annotation

    snapshot_manifest = Path(snapshot_manifest)
    snapshot_meta = json.loads(snapshot_manifest.read_text(encoding="utf-8"))
    snapshot_path = Path(snapshot_meta["artifacts"]["snapshot_universe"]["path"])
    snapshots = [
        EvidenceSnapshot.model_validate_json(line)
        for line in snapshot_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    snapshot_by_state = {item.evidence_state_id: item for item in snapshots}
    annotation_root = Path(annotation_root)
    annotations: dict[str, dict[str, Any]] = {}
    for path in sorted((annotation_root / "records").glob("state_*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("validation_result") != "PASS":
            continue
        state_id = str(value.get("evidence_state_id"))
        if state_id in annotations:
            raise ValueError("duplicate Teacher annotation state identity")
        annotations[state_id] = value
    if len(annotations) != len(snapshots):
        raise ValueError("formal SFT requires one validated Teacher annotation for every frozen state")
    primary_sessions = {
        item.sample_id for item in snapshots if item.classification_supervision_valid
    }
    annotated_primary = {
        item.sample_id
        for item in snapshots
        if item.classification_supervision_valid and item.evidence_state_id in annotations
    }
    if primary_sessions != annotated_primary:
        raise ValueError("formal SFT cannot omit a primary Teacher annotation for any session")

    classes, class_map = load_near_class_map(Path(preset_manifest))
    state_counts = Counter(
        item.sample_id for item in snapshots if item.evidence_state_id in annotations
    )
    supervised_state_counts = Counter(
        item.sample_id
        for item in snapshots
        if item.evidence_state_id in annotations and item.classification_supervision_valid
    )
    if supervised_state_counts and max(supervised_state_counts.values()) > 1:
        raise ValueError("a session cannot contribute multiple classification-supervised states")
    records: list[SFTRecordV1] = []
    for snapshot in snapshots:
        annotation_record = annotations.get(snapshot.evidence_state_id)
        if annotation_record is None:
            continue
        if (
            annotation_record.get("teacher_prompt_version") != TEACHER_PROMPT_VERSION
            or annotation_record.get("teacher_prompt_digest") != teacher_prompt_v3().digest
        ):
            raise ValueError("Teacher annotation does not match the frozen prompt")
        validated_annotation = validate_teacher_annotation(
            annotation_record["normalized_target"], snapshot
        )
        normalized = validated_annotation.model_dump(mode="json")
        normalized.pop("teacher_confidence", None)
        target = EvidenceStateV1.model_validate(normalized)
        serialized = render_training_input(
            traffic_expert_prompt_v2(),
            snapshot.evidence,
            serialization_version=COMPACT_SERIALIZATION_CANDIDATE,
        )
        request_id = annotation_record.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            raise ValueError("Teacher annotation provenance lacks request identity")
        records.append(
            SFTRecordV1(
                sample_id=snapshot.sample_id,
                evidence_state_id=snapshot.evidence_state_id,
                fine_label=snapshot.fine_label,
                class_index=class_map[snapshot.fine_label],
                classification_ce_eligible=snapshot.classification_supervision_valid,
                state_role=("primary" if snapshot.classification_supervision_valid else "auxiliary"),
                serialized_model_input=serialized,
                evidence_state_target=target,
                stage_type=snapshot.stage_type,
                available_capability_mask=snapshot.available_capabilities,
                prompt_version=TRAFFIC_EXPERT_PROMPT_VERSION,
                serialization_version=COMPACT_SERIALIZATION_CANDIDATE,
                teacher_annotation_digest=content_digest(annotation_record["normalized_target"]),
                teacher_model=str(annotation_record["model"]),
                teacher_prompt_digest=str(annotation_record["teacher_prompt_digest"]),
                teacher_request_id=request_id,
                dataset_digest=str(snapshot_meta["dataset_digest"]),
                session_weight=1.0 / state_counts[snapshot.sample_id],
            )
        )
    if {item.fine_label for item in records} != set(classes):
        raise ValueError("formal SFT corpus lost a frozen Near class")
    output_root = Path(output_root)
    corpus_path = output_root / "near_sft_corpus_v2.jsonl"
    _write_jsonl(corpus_path, (item.model_dump(mode="json") for item in records))
    target_texts = [
        canonical_json(item.evidence_state_target.model_dump(mode="json")) for item in records
    ]
    lengths = token_length_report(
        (item.serialized_model_input for item in records), tokenize=tokenize
    )
    target_lengths = token_length_report(target_texts, tokenize=tokenize)
    combined_lengths = token_length_report(
        (
            item.serialized_model_input + chr(10) + target
            for item, target in zip(records, target_texts, strict=True)
        ),
        tokenize=tokenize,
    )
    combined_raw_lengths = [
        len(tokenize(item.serialized_model_input)) + len(tokenize(target))
        for item, target in zip(records, target_texts, strict=True)
    ]
    sequence_overflow_count = sum(
        length > max_sequence_length for length in combined_raw_lengths
    )
    class_distribution = Counter(item.fine_label for item in records)
    stage_distribution = Counter(item.stage_type.value for item in records)
    duplicate_inputs = Counter(content_digest(item.serialized_model_input) for item in records)
    labels_by_input: dict[str, set[str]] = defaultdict(set)
    for item in records:
        labels_by_input[content_digest(item.serialized_model_input)].add(item.fine_label)
    label_collision_count = sum(len(labels) > 1 for labels in labels_by_input.values())
    weight_totals = Counter()
    for item in records:
        weight_totals[item.sample_id] += item.session_weight
    invalid_weight_session_count = sum(
        abs(total - 1.0) > 1e-9 for total in weight_totals.values()
    )
    model_input_backend_identity_count = sum(
        item.sample_id in item.serialized_model_input for item in records
    )
    evidence_presence = Counter(
        evidence_type
        for item in records
        for evidence_type in {
            evidence.evidence_type
            for evidence in snapshot_by_state[item.evidence_state_id].evidence
        }
    )
    classification_supervised_class_distribution = Counter(
        item.fine_label for item in records if item.classification_ce_eligible
    )
    state_role_distribution = Counter(item.state_role for item in records)
    sufficiency_distribution = Counter(
        "sufficient" if item.evidence_state_target.evidence_sufficient else "insufficient"
        for item in records
    )
    gap_type_distribution = Counter(item.evidence_state_target.gap_type.value for item in records)
    missing_evidence_distribution = Counter(
        missing.type.value
        for item in records
        for missing in item.evidence_state_target.missing_evidence
    )
    sufficiency_by_role: dict[str, Counter[str]] = defaultdict(Counter)
    sufficiency_by_stage: dict[str, Counter[str]] = defaultdict(Counter)
    sufficiency_by_class: dict[str, Counter[str]] = defaultdict(Counter)
    sufficiency_by_evidence_type: dict[str, Counter[str]] = defaultdict(Counter)
    for item in records:
        outcome = "sufficient" if item.evidence_state_target.evidence_sufficient else "insufficient"
        sufficiency_by_role[item.state_role][outcome] += 1
        sufficiency_by_stage[item.stage_type.value][outcome] += 1
        sufficiency_by_class[item.fine_label][outcome] += 1
        evidence_key = "+".join(
            sorted(e.evidence_type for e in snapshot_by_state[item.evidence_state_id].evidence)
        )
        sufficiency_by_evidence_type[evidence_key][outcome] += 1
    prohibited_input_key_count = sum(
        any(
            token in item.serialized_model_input.casefold()
            for token in (
                '"fine_label"', '"coarse_label"', '"sample_id"', '"split"',
                '"ku_role"', '"dataset_name"', '"capture_id"', '"source_path"'
            )
        )
        for item in records
    )
    target_class_verdict_count = sum(
        any(
            token in canonical_json(item.evidence_state_target.model_dump(mode="json")).casefold()
            for token in ("label is", "classified as", "classification as", '"fine_label"', '"coarse_label"')
        )
        for item in records
    )
    review_strata: dict[tuple[str, str, bool], list[SFTRecordV1]] = defaultdict(list)
    for item in records:
        review_strata[
            (item.fine_label, item.stage_type.value, item.classification_ce_eligible)
        ].append(item)
    for values in review_strata.values():
        values.sort(
            key=lambda item: content_digest(
                ["manual_audit_v1", item.fine_label, item.stage_type.value, item.evidence_state_id]
            )
        )
    review: list[SFTRecordV1] = []
    review_offsets = {key: 0 for key in review_strata}
    while len(review) < min(200, len(records)):
        advanced = False
        for key in sorted(review_strata):
            index = review_offsets[key]
            if index < len(review_strata[key]):
                review.append(review_strata[key][index])
                review_offsets[key] += 1
                advanced = True
                if len(review) == 200:
                    break
        if not advanced:
            break
    review_path = output_root / "manual_audit_stratified_200.jsonl"
    _write_jsonl(review_path, (item.model_dump(mode="json") for item in review))
    status = "PASS" if all(
        value == 0
        for value in (
            sequence_overflow_count,
            label_collision_count,
            invalid_weight_session_count,
            model_input_backend_identity_count,
            prohibited_input_key_count,
            target_class_verdict_count,
            len(records) - len(snapshots),
            len(primary_sessions) - 16979,
            sum(classification_supervised_class_distribution.values()) - 16979,
        )
    ) and set(classification_supervised_class_distribution) == set(classes) else "FAIL"
    manifest = {
        "status": status,
        "version": "NEAR_SFT_CORPUS_V2",
        "supervision_contract": "CLASSIFICATION_SUFFICIENCY_DECOUPLED_V1",
        "teacher_prompt_version": TEACHER_PROMPT_VERSION,
        "teacher_prompt_digest": teacher_prompt_v3().digest,
        "record_count": len(records),
        "unique_sessions": len({item.sample_id for item in records}),
        "states_per_session": dict(sorted(Counter(state_counts.values()).items())),
        "class_distribution": dict(sorted(class_distribution.items())),
        "stage_distribution": dict(sorted(stage_distribution.items())),
        "classification_supervised_count": sum(item.classification_ce_eligible for item in records),
        "classification_masked_count": sum(not item.classification_ce_eligible for item in records),
        "classification_supervised_unique_sessions": len({
            item.sample_id for item in records if item.classification_ce_eligible
        }),
        "classification_supervised_class_distribution": dict(
            sorted(classification_supervised_class_distribution.items())
        ),
        "classification_supervised_class_coverage": len(classification_supervised_class_distribution),
        "state_role_distribution": dict(sorted(state_role_distribution.items())),
        "evidence_sufficiency_distribution": dict(sorted(sufficiency_distribution.items())),
        "gap_type_distribution": dict(sorted(gap_type_distribution.items())),
        "missing_evidence_distribution": dict(sorted(missing_evidence_distribution.items())),
        "sufficiency_by_primary_auxiliary": {
            key: dict(sorted(value.items())) for key, value in sorted(sufficiency_by_role.items())
        },
        "sufficiency_by_stage": {
            key: dict(sorted(value.items())) for key, value in sorted(sufficiency_by_stage.items())
        },
        "sufficiency_by_class": {
            key: dict(sorted(value.items())) for key, value in sorted(sufficiency_by_class.items())
        },
        "sufficiency_by_evidence_type": {
            key: dict(sorted(value.items())) for key, value in sorted(sufficiency_by_evidence_type.items())
        },
        "application_count": evidence_presence["application"],
        "payload_count": evidence_presence["sanitized_payload"],
        "rag_count": evidence_presence["knowledge"],
        "rag_fraction": evidence_presence["knowledge"] / len(records),
        "teacher_pass_count": len(annotations),
        "teacher_quarantine_count": len(list((annotation_root / "quarantine").glob("*.json"))),
        "token_lengths": {
            "model_input": lengths,
            "evidence_state_target": target_lengths,
            "combined_sequence": combined_lengths,
            "max_sequence_length": max_sequence_length,
            "overflow_count": sequence_overflow_count,
        },
        "exact_serialized_input_duplicate_groups": sum(value > 1 for value in duplicate_inputs.values()),
        "duplicate_rate": sum(value - 1 for value in duplicate_inputs.values() if value > 1) / len(records),
        "label_collision_count": label_collision_count,
        "missing_field_count": 0,
        "missing_field_rate": 0.0,
        "model_input_backend_identity_count": model_input_backend_identity_count,
        "prohibited_model_input_key_count": prohibited_input_key_count,
        "target_class_verdict_count": target_class_verdict_count,
        "invalid_session_weight_count": invalid_weight_session_count,
        "classification_supervised_states_per_session_max": max(
            supervised_state_counts.values(), default=0
        ),
        "manual_audit_queue_count": len(review),
        "artifacts": {
            "corpus": {"path": str(corpus_path), "sha256": sha256_file(corpus_path)},
            "manual_audit": {"path": str(review_path), "sha256": sha256_file(review_path)},
        },
        "validation_count": 0,
        "test_count": 0,
        "u_dev_count": 0,
        "u_final_count": 0,
        "sft_run": False,
    }
    manifest["artifact_digest"] = content_digest(manifest["artifacts"])
    _atomic_json(output_root / "manifest.json", manifest)
    return manifest
