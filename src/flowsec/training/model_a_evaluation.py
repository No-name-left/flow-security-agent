from __future__ import annotations

import csv
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Sequence

from flowsec.llm.structured_output import extract_json_value

from .blind_audit import BlindClassificationOutputV1, validate_blind_output
from .contracts import (
    EvidenceDomain,
    EvidenceEnvelope,
    EvidenceFamilyV2,
    EvidenceStateV2,
    EvidenceTrustV1,
)
from .serialization import decode_compact


MODEL_A_EVALUATION_VERSION = "MODEL_A_FORMAL_EVALUATION_V1"
REFERENCE_VERSION = "OBSERVABLE_V3_PREMODEL_BASIC_SUFFICIENCY_REFERENCE_V1"
MODEL_SAFE_MARKER = "\nMODEL_SAFE_EVIDENCE:\n"
CLASSIFICATION_SUFFIX = "\nClassification representation:"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def atomic_csv(path: Path, rows: Sequence[Sequence[Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)
    os.replace(temporary, path)


def append_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(
                json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False)
                + "\n"
            )
        handle.flush()
        os.fsync(handle.fileno())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not Path(path).is_file():
        return []
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def completed_sample_ids(path: Path) -> set[str]:
    rows = read_jsonl(path)
    identifiers = [str(row["sample_id"]) for row in rows]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"prediction artifact contains duplicate sample IDs: {path}")
    return set(identifiers)


def confusion_matrix(
    targets: Sequence[int], predictions: Sequence[int], class_count: int
) -> list[list[int]]:
    if len(targets) != len(predictions):
        raise ValueError("classification targets and predictions differ in length")
    if class_count <= 0:
        raise ValueError("classification metrics require at least one class")
    matrix = [[0 for _ in range(class_count)] for _ in range(class_count)]
    for target, prediction in zip(targets, predictions, strict=True):
        if target < 0 or target >= class_count:
            raise ValueError(f"target class index is invalid: {target}")
        if 0 <= prediction < class_count:
            matrix[target][prediction] += 1
    return matrix


def classification_metrics(
    targets: Sequence[int],
    predictions: Sequence[int],
    classes: Sequence[str],
) -> dict[str, Any]:
    if len(targets) != len(predictions) or not targets:
        raise ValueError("classification metrics require equal nonempty vectors")
    class_count = len(classes)
    matrix = confusion_matrix(targets, predictions, class_count)
    invalid = sum(not (0 <= value < class_count) for value in predictions)
    per_class: dict[str, dict[str, float | int]] = {}
    precisions: list[float] = []
    recalls: list[float] = []
    f1s: list[float] = []
    total_tp = total_fp = total_fn = 0
    for index, label in enumerate(classes):
        tp = matrix[index][index]
        fp = sum(matrix[row][index] for row in range(class_count) if row != index)
        fn = sum(matrix[index][column] for column in range(class_count) if column != index)
        fn += sum(
            target == index and not (0 <= prediction < class_count)
            for target, prediction in zip(targets, predictions, strict=True)
        )
        support = sum(target == index for target in targets)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
        }
        precisions.append(precision)
        recalls.append(recall)
        f1s.append(f1)
        total_tp += tp
        total_fp += fp
        total_fn += fn
    accuracy = sum(t == p for t, p in zip(targets, predictions, strict=True)) / len(targets)
    micro_precision = total_tp / (total_tp + total_fp) if total_tp + total_fp else 0.0
    micro_recall = total_tp / (total_tp + total_fn) if total_tp + total_fn else 0.0
    micro_f1 = (
        2 * micro_precision * micro_recall / (micro_precision + micro_recall)
        if micro_precision + micro_recall
        else 0.0
    )
    return {
        "record_count": len(targets),
        "invalid_prediction_count": invalid,
        "accuracy": accuracy,
        "macro_precision": sum(precisions) / class_count,
        "macro_recall": sum(recalls) / class_count,
        "macro_f1": sum(f1s) / class_count,
        "micro_precision": micro_precision,
        "micro_recall": micro_recall,
        "micro_f1": micro_f1,
        "per_class": per_class,
        "confusion_matrix": matrix,
        "class_order": list(classes),
    }


def supported_classification_metrics(
    targets: Sequence[int], predictions: Sequence[int], classes: Sequence[str]
) -> dict[str, Any]:
    support = sorted(set(targets))
    if not support:
        raise ValueError("subset classification metrics require records")
    remap = {old: new for new, old in enumerate(support)}
    subset_classes = [classes[index] for index in support]
    remapped_targets = [remap[value] for value in targets]
    remapped_predictions = [remap.get(value, -1) for value in predictions]
    result = classification_metrics(remapped_targets, remapped_predictions, subset_classes)
    result["macro_scope"] = "classes_with_subset_support"
    return result


def binary_metrics(targets: Sequence[bool], predictions: Sequence[bool]) -> dict[str, Any]:
    if len(targets) != len(predictions) or not targets:
        raise ValueError("binary metrics require equal nonempty vectors")
    tp = sum(target and prediction for target, prediction in zip(targets, predictions, strict=True))
    tn = sum(not target and not prediction for target, prediction in zip(targets, predictions, strict=True))
    fp = sum(not target and prediction for target, prediction in zip(targets, predictions, strict=True))
    fn = sum(target and not prediction for target, prediction in zip(targets, predictions, strict=True))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "accuracy": (tp + tn) / len(targets),
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "confusion_matrix": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
    }


def multilabel_metrics(
    targets: Sequence[set[str]],
    predictions: Sequence[set[str]],
    families: Sequence[str],
) -> dict[str, Any]:
    if len(targets) != len(predictions) or not targets:
        raise ValueError("multi-label metrics require equal nonempty vectors")
    exact = sum(target == prediction for target, prediction in zip(targets, predictions, strict=True))
    per_family: dict[str, dict[str, float | int]] = {}
    macro_f1: list[float] = []
    total_tp = total_fp = total_fn = 0
    for family in families:
        tp = sum(family in t and family in p for t, p in zip(targets, predictions, strict=True))
        fp = sum(family not in t and family in p for t, p in zip(targets, predictions, strict=True))
        fn = sum(family in t and family not in p for t, p in zip(targets, predictions, strict=True))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_family[family] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": tp + fn,
        }
        macro_f1.append(f1)
        total_tp += tp
        total_fp += fp
        total_fn += fn
    micro_precision = total_tp / (total_tp + total_fp) if total_tp + total_fp else 0.0
    micro_recall = total_tp / (total_tp + total_fn) if total_tp + total_fn else 0.0
    return {
        "exact_match": exact / len(targets),
        "micro_precision": micro_precision,
        "micro_recall": micro_recall,
        "micro_f1": (
            2 * micro_precision * micro_recall / (micro_precision + micro_recall)
            if micro_precision + micro_recall
            else 0.0
        ),
        "macro_f1": sum(macro_f1) / len(families),
        "per_family": per_family,
    }


def compact_evidence_from_input(serialized_model_input: str) -> tuple[EvidenceEnvelope, ...]:
    if MODEL_SAFE_MARKER not in serialized_model_input:
        raise ValueError("formal input has no MODEL_SAFE_EVIDENCE marker")
    value = serialized_model_input.split(MODEL_SAFE_MARKER, 1)[1]
    if value.endswith(CLASSIFICATION_SUFFIX):
        value = value[: -len(CLASSIFICATION_SUFFIX)]
    decoded = decode_compact(value)
    return tuple(
        EvidenceEnvelope(
            evidence_id=str(item["evidence_id"]),
            evidence_type=str(item["evidence_type"]),
            domain=EvidenceDomain(str(item["domain"])),
            trust=EvidenceTrustV1(str(item["trust"])),
            provenance=str(item["provenance"]),
            metadata=dict(item["metadata"]),
            content=dict(item["content"]),
        )
        for item in decoded
    )


def parse_raw_blind_output(
    text: str,
    *,
    candidate_labels: tuple[str, ...],
    evidence: tuple[EvidenceEnvelope, ...],
) -> BlindClassificationOutputV1:
    payload = extract_json_value(text)
    if not isinstance(payload, dict):
        raise ValueError("raw blind classification output is not an object")
    return validate_blind_output(
        payload,
        candidate_labels=candidate_labels,
        evidence=evidence,
    )


def parse_evidence_output(
    text: str, evidence: tuple[EvidenceEnvelope, ...]
) -> tuple[EvidenceStateV2, dict[str, int]]:
    payload = extract_json_value(text)
    if not isinstance(payload, dict):
        raise ValueError("Evidence-State output is not an object")
    state = EvidenceStateV2.model_validate(payload)
    available = {item.evidence_id: item for item in evidence}
    missing_reference = 0
    knowledge_as_observation = 0
    for support in state.supporting_evidence:
        item = available.get(support.evidence_id)
        if item is None:
            missing_reference += 1
        elif item.domain is EvidenceDomain.KNOWLEDGE:
            knowledge_as_observation += 1
    return state, {
        "missing_support_reference_count": missing_reference,
        "knowledge_cited_as_observation_count": knowledge_as_observation,
        "severe_hallucination_count": missing_reference + knowledge_as_observation,
    }


def evidence_reference_from_eligibility(row: dict[str, Any]) -> dict[str, Any]:
    sufficient = bool(row["basic_sufficient"])
    families = [] if sufficient else json.loads(str(row["supporting_evidence_families_json"]))
    allowed = {item.value for item in EvidenceFamilyV2}
    if any(item not in allowed for item in families):
        raise ValueError(f"eligibility reference contains an unsupported family: {families}")
    return {
        "reference_version": REFERENCE_VERSION,
        "basic_sufficient": sufficient,
        "missing_evidence": sorted(set(families)),
        "reference_source": "pre-model Observable-v3 eligibility assessment",
    }


def evidence_metrics_flat(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Non-recursive Evidence metrics used for overall and explicit subsets."""

    if not rows:
        raise ValueError("Evidence-State metrics require predictions")
    families = tuple(item.value for item in EvidenceFamilyV2)
    targets: list[bool] = []
    predictions: list[bool] = []
    gap_targets: list[set[str]] = []
    gap_predictions: list[set[str]] = []
    for row in rows:
        target = bool(row["target_basic_sufficient"])
        target_gaps = set(row["target_missing_evidence"])
        if bool(row["schema_valid"]):
            predicted = bool(row["predicted_evidence_sufficient"])
            predicted_gaps = set(row["predicted_missing_evidence"])
        else:
            predicted = not target
            predicted_gaps = set() if target_gaps else set(families)
        targets.append(target)
        predictions.append(predicted)
        gap_targets.append(target_gaps)
        gap_predictions.append(predicted_gaps)
    valid = sum(bool(row["schema_valid"]) for row in rows)
    return {
        "record_count": len(rows),
        "schema_valid_count": valid,
        "schema_valid_rate": valid / len(rows),
        "invalid_structured_output_count": len(rows) - valid,
        "severe_hallucination_count": sum(
            int(row.get("severe_hallucination_count", 0)) for row in rows
        ),
        "sufficiency": binary_metrics(targets, predictions),
        "missing_evidence": multilabel_metrics(
            gap_targets, gap_predictions, families
        ),
    }


def confusion_csv_rows(metrics: dict[str, Any]) -> list[list[Any]]:
    classes = list(metrics["class_order"])
    rows: list[list[Any]] = [["gt\\predicted", *classes]]
    rows.extend(
        [label, *metrics["confusion_matrix"][index]]
        for index, label in enumerate(classes)
    )
    return rows


def validate_checkpoint_files(checkpoint: Path) -> dict[str, Any]:
    checkpoint = Path(checkpoint)
    required = (
        "adapter/adapter_model.safetensors",
        "adapter/adapter_config.json",
        "fine_head.safetensors",
        "optimizer.pt",
        "scheduler.pt",
        "rng_state.pt",
        "trainer_state.json",
        "checkpoint_manifest.json",
    )
    missing = [name for name in required if not (checkpoint / name).is_file()]
    if missing:
        raise FileNotFoundError(f"final checkpoint is incomplete: {missing}")
    manifest = json.loads((checkpoint / "checkpoint_manifest.json").read_text(encoding="utf-8"))
    state = json.loads((checkpoint / "trainer_state.json").read_text(encoding="utf-8"))
    if int(state.get("optimizer_step", -1)) != 1794 or int(state.get("epoch", -1)) != 2:
        raise ValueError(f"unexpected final checkpoint state: {state}")
    return {
        "status": "PASS",
        "checkpoint": str(checkpoint),
        "required_file_count": len(required),
        "optimizer_step": int(state["optimizer_step"]),
        "epoch": int(state["epoch"]),
        "model_id": manifest["model_id"],
        "model_revision": manifest["model_revision"],
        "tokenizer_revision": manifest["tokenizer_revision"],
    }


def safe_validation_reference(
    validation_ids: set[str], eligibility_paths: Sequence[Path]
) -> dict[str, dict[str, Any]]:
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    values = pa.array(sorted(validation_ids))
    result: dict[str, dict[str, Any]] = {}
    columns = (
        "session_id",
        "split",
        "fine_label",
        "basic_sufficient",
        "supporting_evidence_families_json",
        "classification_ce_eligible",
    )
    for path in eligibility_paths:
        table = pq.read_table(path, columns=list(columns))
        selected = table.filter(pc.is_in(table["session_id"], value_set=values))
        for row in selected.to_pylist():
            sample_id = str(row["session_id"])
            if sample_id in result:
                raise ValueError(f"duplicate validation eligibility row: {sample_id}")
            if row["split"] != "validation" or not row["classification_ce_eligible"]:
                raise ValueError(f"validation reference escaped eligible validation: {sample_id}")
            result[sample_id] = {
                "fine_label": str(row["fine_label"]),
                **evidence_reference_from_eligibility(row),
            }
    missing = sorted(validation_ids - set(result))
    extra = sorted(set(result) - validation_ids)
    if missing or extra:
        raise ValueError(
            f"validation eligibility join is not one-to-one: missing={missing[:3]} extra={extra[:3]}"
        )
    return result
