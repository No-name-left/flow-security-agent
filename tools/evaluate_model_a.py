#!/usr/bin/env python3
"""Resumable, read-only formal evaluation for the frozen Near Model A run."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import os
import random
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from flowsec.integrations.llm.prompting import render_messages_as_tagged_text  # noqa: E402
from flowsec.training.blind_audit import build_blind_classifier_request  # noqa: E402
from flowsec.training.contracts import NearValidationRecordV1, SFTRecordV2  # noqa: E402
from flowsec.training.harness import (  # noqa: E402
    FineClassificationHead,
    POOL_MEAN,
    pool_hidden_state,
)
from flowsec.training.model_a_evaluation import (  # noqa: E402
    MODEL_A_EVALUATION_VERSION,
    append_jsonl,
    atomic_csv,
    atomic_json,
    classification_metrics,
    compact_evidence_from_input,
    completed_sample_ids,
    confusion_csv_rows,
    evidence_metrics_flat,
    parse_evidence_output,
    parse_raw_blind_output,
    read_jsonl,
    safe_validation_reference,
    sha256_file,
    supported_classification_metrics,
    validate_checkpoint_files,
)


DEFAULT_RUN = Path(
    "/root/autodl-tmp/processed/training_runs/near_sft_v3/"
    "near-sft-v3-20260812T230311Z-d93789de"
)
DEFAULT_CHECKPOINT = DEFAULT_RUN / "checkpoint-step-00001794"
DEFAULT_MODEL = Path("/root/autodl-tmp/models/Qwen3.5-9B")
DEFAULT_PRETRAINING = Path("/root/autodl-tmp/processed/near_pretraining_v3")
DEFAULT_FREEZE = Path("/root/autodl-tmp/processed/observable_dataset_v3_freeze")
DEFAULT_ELIGIBILITY = Path("/root/autodl-tmp/processed/observable_dataset_v3/eligibility")
DEFAULT_OUTPUT = Path("/root/autodl-tmp/processed/evaluation/model_a_formal_v1")
EXPECTED_FORMAL_MACRO_F1 = 0.9984831207613943
SEED = 20260809


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _records(path: Path, model: Any) -> list[Any]:
    return [
        model.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _classes(class_map_path: Path) -> tuple[tuple[str, ...], dict[str, int]]:
    value = _json(class_map_path)
    labels = tuple(value["Near"]["K_known"])
    mapping = {str(key): int(index) for key, index in value["class_index"].items()}
    if mapping != {label: index for index, label in enumerate(labels)}:
        raise ValueError("frozen class order and class_index disagree")
    return labels, mapping


def _eligibility_reference(
    validation: Sequence[NearValidationRecordV1], eligibility_root: Path
) -> dict[str, dict[str, Any]]:
    paths = sorted(eligibility_root.glob("*.parquet"))
    if not paths:
        raise FileNotFoundError(f"no Observable-v3 eligibility Parquet under {eligibility_root}")
    return safe_validation_reference({item.sample_id for item in validation}, paths)


def _load_language_model(model_root: Path, adapter: Path | None) -> tuple[Any, Any]:
    import torch
    from peft import PeftModel
    from transformers import AutoModelForImageTextToText, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_root, local_files_only=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    # Decoder-only batched generation requires left padding. Attention-masked
    # mean pooling is invariant to the padding side, so one setting is safe for
    # both the classifier and generation paths.
    tokenizer.padding_side = "left"
    model = AutoModelForImageTextToText.from_pretrained(
        model_root,
        dtype=torch.bfloat16,
        device_map={"": 0},
        local_files_only=True,
    )
    if adapter is not None:
        model = PeftModel.from_pretrained(model, adapter, is_trainable=False)
    model.eval()
    return tokenizer, model


def _clear_cuda() -> None:
    import torch

    gc.collect()
    torch.cuda.empty_cache()


def _underlying_hidden(model: Any, input_ids: Any, attention_mask: Any) -> Any:
    core = model.get_base_model() if hasattr(model, "get_base_model") else model
    output = core.model(
        input_ids=input_ids,
        attention_mask=attention_mask,
        use_cache=False,
        return_dict=True,
    )
    return output.last_hidden_state if hasattr(output, "last_hidden_state") else output[0]


def _batches(items: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _encode(tokenizer: Any, texts: Sequence[str]) -> dict[str, Any]:
    return tokenizer(
        list(texts), add_special_tokens=True, padding=True, return_tensors="pt"
    )


def _generate_texts(
    model: Any,
    tokenizer: Any,
    prompts: Sequence[str],
    *,
    max_new_tokens: int,
) -> list[str]:
    import torch

    encoded = _encode(tokenizer, prompts)
    encoded = {key: value.to("cuda") for key, value in encoded.items()}
    prompt_width = int(encoded["input_ids"].shape[1])
    with torch.inference_mode():
        generated = model.generate(
            **encoded,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            use_cache=True,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )
    return [
        tokenizer.decode(row[prompt_width:], skip_special_tokens=True).strip()
        for row in generated
    ]


def _classification_summary(
    path: Path,
    classes: tuple[str, ...],
    output: Path,
    *,
    prefix: str,
) -> dict[str, Any]:
    rows = read_jsonl(path)
    mapping = {label: index for index, label in enumerate(classes)}
    targets = [mapping[str(row["gt_fine_label"])] for row in rows]
    predictions = [mapping.get(str(row.get("predicted_fine_label")), -1) for row in rows]
    metrics = classification_metrics(targets, predictions, classes)
    atomic_json(output / f"{prefix}_metrics.json", metrics)
    return metrics


def run_final_classification(args: argparse.Namespace) -> dict[str, Any]:
    import torch
    from safetensors.torch import load_file

    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    checkpoint_status = validate_checkpoint_files(args.checkpoint)
    validation = _records(args.validation, NearValidationRecordV1)
    classes, class_map = _classes(args.class_map)
    reference = _eligibility_reference(validation, args.eligibility_root)
    prediction_path = output / "known_validation_predictions.jsonl"
    complete = completed_sample_ids(prediction_path)
    pending = [item for item in validation if item.sample_id not in complete]
    tokenizer, model = _load_language_model(args.model_root, args.checkpoint / "adapter")
    head = FineClassificationHead(4096, len(classes)).to(device="cuda", dtype=torch.bfloat16)
    head.load_state_dict(load_file(args.checkpoint / "fine_head.safetensors"))
    head.eval()
    with torch.inference_mode():
        for number, batch in enumerate(_batches(pending, args.batch_size), start=1):
            encoded = _encode(tokenizer, [item.serialized_model_input for item in batch])
            input_ids = encoded["input_ids"].to("cuda")
            attention = encoded["attention_mask"].to("cuda")
            hidden = _underlying_hidden(model, input_ids, attention)
            representation = pool_hidden_state(hidden, attention, method=POOL_MEAN)
            logits = head(representation).float()
            probabilities = torch.softmax(logits, dim=-1)
            predicted = logits.argmax(dim=-1).tolist()
            rows = []
            for index, item in enumerate(batch):
                expected_index = class_map[item.fine_label]
                if item.class_index != expected_index:
                    raise ValueError(f"validation class index mismatch: {item.sample_id}")
                rows.append(
                    {
                        "sample_id": item.sample_id,
                        "gt_fine_label": item.fine_label,
                        "predicted_fine_label": classes[predicted[index]],
                        "logits": logits[index].tolist(),
                        "probabilities": probabilities[index].tolist(),
                        "correct": predicted[index] == expected_index,
                        "basic_sufficient": reference[item.sample_id]["basic_sufficient"],
                        "reference_version": reference[item.sample_id]["reference_version"],
                    }
                )
            append_jsonl(prediction_path, rows)
            if number % 25 == 0:
                print(f"final classification {min(number * args.batch_size, len(pending))}/{len(pending)}", flush=True)
    del model, head
    _clear_cuda()
    rows = read_jsonl(prediction_path)
    if len(rows) != len(validation):
        raise ValueError("final classification prediction count is incomplete")
    targets = [class_map[str(row["gt_fine_label"])] for row in rows]
    predictions = [class_map[str(row["predicted_fine_label"])] for row in rows]
    overall = classification_metrics(targets, predictions, classes)
    subsets: dict[str, Any] = {}
    for name, flag in (("basic_sufficient", True), ("basic_insufficient", False)):
        selected = [row for row in rows if bool(row["basic_sufficient"]) is flag]
        subsets[name] = supported_classification_metrics(
            [class_map[str(row["gt_fine_label"])] for row in selected],
            [class_map[str(row["predicted_fine_label"])] for row in selected],
            classes,
        )
    metrics = {
        "version": MODEL_A_EVALUATION_VERSION,
        "checkpoint": checkpoint_status,
        "overall": overall,
        "subsets": subsets,
        "formal_macro_f1_expected": EXPECTED_FORMAL_MACRO_F1,
        "formal_macro_f1_absolute_difference": abs(overall["macro_f1"] - EXPECTED_FORMAL_MACRO_F1),
        "formal_macro_f1_reproduced": abs(overall["macro_f1"] - EXPECTED_FORMAL_MACRO_F1) <= 1e-12,
    }
    atomic_json(output / "classification_metrics.json", metrics)
    atomic_json(output / "per_class_metrics.json", overall["per_class"])
    atomic_json(output / "confusion_matrix.json", {
        "class_order": list(classes), "matrix": overall["confusion_matrix"]
    })
    atomic_csv(output / "confusion_matrix.csv", confusion_csv_rows(overall))
    return metrics


def run_evidence_generation(args: argparse.Namespace) -> dict[str, Any]:
    output = args.output
    validation = _records(args.validation, NearValidationRecordV1)
    reference = _eligibility_reference(validation, args.eligibility_root)
    path = output / "evidence_state_predictions.jsonl"
    complete = completed_sample_ids(path)
    pending = [item for item in validation if item.sample_id not in complete]
    tokenizer, model = _load_language_model(args.model_root, args.checkpoint / "adapter")
    for number, batch in enumerate(_batches(pending, args.generation_batch_size), start=1):
        texts = _generate_texts(
            model,
            tokenizer,
            [item.serialized_model_input for item in batch],
            max_new_tokens=args.evidence_max_new_tokens,
        )
        rows = []
        for item, text in zip(batch, texts, strict=True):
            evidence = compact_evidence_from_input(item.serialized_model_input)
            target = reference[item.sample_id]
            row: dict[str, Any] = {
                "sample_id": item.sample_id,
                "gt_fine_label": item.fine_label,
                "target_basic_sufficient": target["basic_sufficient"],
                "target_missing_evidence": target["missing_evidence"],
                "reference_version": target["reference_version"],
                "raw_output": text,
                "schema_valid": False,
                "predicted_evidence_sufficient": None,
                "predicted_missing_evidence": [],
                "missing_support_reference_count": 0,
                "knowledge_cited_as_observation_count": 0,
                "severe_hallucination_count": 0,
            }
            try:
                state, grounding = parse_evidence_output(text, evidence)
                row.update(
                    {
                        "schema_valid": True,
                        "predicted_evidence_sufficient": state.evidence_sufficient,
                        "predicted_missing_evidence": sorted(value.value for value in state.missing_evidence),
                        "predicted_state": state.model_dump(mode="json"),
                        **grounding,
                    }
                )
            except (ValueError, TypeError) as error:
                row["parse_error"] = f"{type(error).__name__}: {error}"
            rows.append(row)
        append_jsonl(path, rows)
        if number % 10 == 0:
            print(f"evidence generation {min(number * args.generation_batch_size, len(pending))}/{len(pending)}", flush=True)
    del model
    _clear_cuda()
    rows = read_jsonl(path)
    if len(rows) != len(validation):
        raise ValueError("Evidence-State prediction count is incomplete")
    metrics = {"overall": evidence_metrics_flat(rows)}
    for name, flag in (("basic_sufficient", True), ("basic_insufficient", False)):
        metrics[name] = evidence_metrics_flat(
            [row for row in rows if bool(row["target_basic_sufficient"]) is flag]
        )
    atomic_json(output / "evidence_state_metrics.json", metrics)
    return metrics


def run_raw_qwen(args: argparse.Namespace, tokenizer: Any, model: Any) -> dict[str, Any]:
    output = args.output
    validation = _records(args.validation, NearValidationRecordV1)
    classes, _ = _classes(args.class_map)
    path = output / "baseline_raw_qwen_predictions.jsonl"
    complete = completed_sample_ids(path)
    pending = [item for item in validation if item.sample_id not in complete]
    for number, batch in enumerate(_batches(pending, args.generation_batch_size), start=1):
        evidence = [compact_evidence_from_input(item.serialized_model_input) for item in batch]
        prompts = []
        for current in evidence:
            request = build_blind_classifier_request(
                current,
                classes,
                provider="local_qwen",
                base_url="local://transformers",
                model_id="Qwen/Qwen3.5-9B",
                # The transport contract requires a positive timeout even
                # though this request is rendered and executed in-process.
                timeout_seconds=1.0,
                local_qwen=True,
            )
            tagged_messages = list(render_messages_as_tagged_text(request.messages))
            prompts.append(
                tokenizer.apply_chat_template(
                    tagged_messages,
                    tokenize=False,
                    add_generation_prompt=True,
                    enable_thinking=False,
                )
            )
        texts = _generate_texts(
            model,
            tokenizer,
            prompts,
            max_new_tokens=args.raw_max_new_tokens,
        )
        rows = []
        for item, current, text in zip(batch, evidence, texts, strict=True):
            row: dict[str, Any] = {
                "sample_id": item.sample_id,
                "gt_fine_label": item.fine_label,
                "predicted_fine_label": None,
                "parse_valid": False,
                "raw_output": text,
            }
            try:
                parsed = parse_raw_blind_output(
                    text, candidate_labels=classes, evidence=current
                )
                row.update(
                    {
                        "parse_valid": True,
                        "predicted_fine_label": parsed.top1,
                        "top2": parsed.top2,
                        "confidence": parsed.confidence.value,
                        "supporting_evidence_ids": list(parsed.supporting_evidence_ids),
                    }
                )
            except (ValueError, TypeError) as error:
                row["parse_error"] = f"{type(error).__name__}: {error}"
            rows.append(row)
        append_jsonl(path, rows)
        if number % 10 == 0:
            print(f"raw Qwen {min(number * args.generation_batch_size, len(pending))}/{len(pending)}", flush=True)
    rows = read_jsonl(path)
    metrics = _classification_summary(
        path, classes, output, prefix="baseline_raw_qwen"
    )
    metrics["parse_valid_count"] = sum(bool(row["parse_valid"]) for row in rows)
    metrics["parse_valid_rate"] = metrics["parse_valid_count"] / len(rows)
    atomic_json(output / "baseline_raw_qwen_metrics.json", metrics)
    return metrics


def _extract_features(
    records: Sequence[Any],
    *,
    tokenizer: Any,
    model: Any,
    class_map: dict[str, int],
    output_features: Path,
    output_labels: Path,
    batch_size: int,
) -> None:
    import torch

    if output_features.is_file() and output_labels.is_file():
        features = np.load(output_features, mmap_mode="r")
        labels = np.load(output_labels, mmap_mode="r")
        if features.shape == (len(records), 4096) and labels.shape == (len(records),):
            return
        raise ValueError(f"existing feature cache has incompatible shape: {output_features}")
    output_features.parent.mkdir(parents=True, exist_ok=True)
    temporary_features = output_features.with_suffix(".tmp.npy")
    temporary_labels = output_labels.with_suffix(".tmp.npy")
    features = np.lib.format.open_memmap(
        temporary_features, mode="w+", dtype=np.float16, shape=(len(records), 4096)
    )
    labels = np.lib.format.open_memmap(
        temporary_labels, mode="w+", dtype=np.int64, shape=(len(records),)
    )
    offset = 0
    with torch.inference_mode():
        for number, batch in enumerate(_batches(records, batch_size), start=1):
            encoded = _encode(tokenizer, [item.serialized_model_input for item in batch])
            ids = encoded["input_ids"].to("cuda")
            attention = encoded["attention_mask"].to("cuda")
            hidden = _underlying_hidden(model, ids, attention)
            pooled = pool_hidden_state(hidden, attention, method=POOL_MEAN)
            end = offset + len(batch)
            features[offset:end] = pooled.float().cpu().numpy().astype(np.float16)
            labels[offset:end] = [class_map[item.fine_label] for item in batch]
            offset = end
            if number % 25 == 0:
                print(f"base features {offset}/{len(records)}", flush=True)
    features.flush()
    labels.flush()
    os.replace(temporary_features, output_features)
    os.replace(temporary_labels, output_labels)


def _stratified_training_subset(
    records: Sequence[SFTRecordV2],
    classes: Sequence[str],
    *,
    per_class: int,
) -> list[SFTRecordV2]:
    """Select a deterministic class-balanced diagnostic subset."""

    selected: list[SFTRecordV2] = []
    for label in classes:
        candidates = [item for item in records if item.fine_label == label]
        candidates.sort(
            key=lambda item: hashlib.sha256(
                f"{SEED}:{item.sample_id}".encode("utf-8")
            ).hexdigest()
        )
        if len(candidates) < per_class:
            raise ValueError(
                f"linear-probe class {label} has only {len(candidates)} records"
            )
        selected.extend(candidates[:per_class])
    return selected


def _extract_limited_training_features(
    selected: Sequence[SFTRecordV2],
    all_primary: Sequence[SFTRecordV2],
    *,
    tokenizer: Any,
    model: Any,
    class_map: dict[str, int],
    feature_root: Path,
    batch_size: int,
) -> tuple[Path, Path, dict[str, Any]]:
    """Build a resumable limited subset while reusing an interrupted full scan."""

    import torch

    output_features = feature_root / "limited_train_features.float16.npy"
    output_labels = feature_root / "limited_train_labels.npy"
    selection_path = feature_root / "limited_train_selection.json"
    selection = {
        "version": "MODEL_A_LIMITED_STRATIFIED_PROBE_V1",
        "seed": SEED,
        "selection": "SHA256(seed:sample_id)_LOWEST_PER_CLASS",
        "record_count": len(selected),
        "sample_ids": [item.sample_id for item in selected],
    }
    if selection_path.is_file() and _json(selection_path) != selection:
        raise ValueError("existing limited-probe selection is incompatible")
    atomic_json(selection_path, selection)
    if output_features.is_file() and output_labels.is_file():
        features = np.load(output_features, mmap_mode="r")
        labels = np.load(output_labels, mmap_mode="r")
        if features.shape == (len(selected), 4096) and labels.shape == (len(selected),):
            return output_features, output_labels, {"reused_from_interrupted_scan": 0}
        raise ValueError("existing limited feature cache has incompatible shape")

    temporary_features = output_features.with_suffix(".tmp.npy")
    temporary_labels = output_labels.with_suffix(".tmp.npy")
    if temporary_features.is_file() and temporary_labels.is_file():
        features = np.lib.format.open_memmap(temporary_features, mode="r+")
        labels = np.lib.format.open_memmap(temporary_labels, mode="r+")
        if features.shape != (len(selected), 4096) or labels.shape != (len(selected),):
            raise ValueError("partial limited feature cache has incompatible shape")
    else:
        features = np.lib.format.open_memmap(
            temporary_features,
            mode="w+",
            dtype=np.float16,
            shape=(len(selected), 4096),
        )
        labels = np.lib.format.open_memmap(
            temporary_labels, mode="w+", dtype=np.int64, shape=(len(selected),)
        )

    by_id = {item.sample_id: index for index, item in enumerate(all_primary)}
    interrupted_path = feature_root / "train_features.float16.tmp.npy"
    interrupted = (
        np.load(interrupted_path, mmap_mode="r") if interrupted_path.is_file() else None
    )
    reused = 0
    for position, item in enumerate(selected):
        if bool(np.any(features[position] != 0)):
            continue
        source_index = by_id[item.sample_id]
        if interrupted is not None and bool(np.any(interrupted[source_index] != 0)):
            features[position] = interrupted[source_index]
            labels[position] = class_map[item.fine_label]
            reused += 1
    features.flush()
    labels.flush()

    pending = [
        (position, item)
        for position, item in enumerate(selected)
        if not bool(np.any(features[position] != 0))
    ]
    with torch.inference_mode():
        for number, batch in enumerate(_batches(pending, batch_size), start=1):
            positions = [position for position, _item in batch]
            items = [item for _position, item in batch]
            encoded = _encode(tokenizer, [item.serialized_model_input for item in items])
            ids = encoded["input_ids"].to("cuda")
            attention = encoded["attention_mask"].to("cuda")
            hidden = _underlying_hidden(model, ids, attention)
            pooled = pool_hidden_state(hidden, attention, method=POOL_MEAN)
            values = pooled.float().cpu().numpy().astype(np.float16)
            for row, position, item in zip(values, positions, items, strict=True):
                features[position] = row
                labels[position] = class_map[item.fine_label]
            features.flush()
            labels.flush()
            if number % 25 == 0:
                completed = len(selected) - len(pending) + min(
                    number * batch_size, len(pending)
                )
                print(f"limited base features {completed}/{len(selected)}", flush=True)
    if not bool(np.all(np.any(features != 0, axis=1))):
        raise ValueError("limited feature extraction is incomplete")
    features.flush()
    labels.flush()
    os.replace(temporary_features, output_features)
    os.replace(temporary_labels, output_labels)
    return output_features, output_labels, {"reused_from_interrupted_scan": reused}


def run_base_controls(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    import torch
    from safetensors.torch import load_file, save_file

    output = args.output
    classes, class_map = _classes(args.class_map)
    validation = _records(args.validation, NearValidationRecordV1)
    all_training = _records(args.training_corpus, SFTRecordV2)
    all_primary = [item for item in all_training if item.state_role == "primary"]
    if len(all_primary) != len({item.sample_id for item in all_primary}):
        raise ValueError("linear probe training primary records are not one per session")
    if any(item.source_split != "train" for item in all_primary):
        raise ValueError("linear probe escaped the formal training split")
    training = _stratified_training_subset(
        all_primary, classes, per_class=args.probe_per_class
    )
    tokenizer, model = _load_language_model(args.model_root, None)
    raw_metrics = run_raw_qwen(args, tokenizer, model)
    feature_root = output / "model_a_linear_probe"
    validation_features = feature_root / "validation_features.float16.npy"
    validation_labels = feature_root / "validation_labels.npy"
    train_features, train_labels, extraction = _extract_limited_training_features(
        training,
        all_primary,
        tokenizer=tokenizer,
        model=model,
        class_map=class_map,
        feature_root=feature_root,
        batch_size=args.batch_size,
    )
    _extract_features(
        validation,
        tokenizer=tokenizer,
        model=model,
        class_map=class_map,
        output_features=validation_features,
        output_labels=validation_labels,
        batch_size=args.batch_size,
    )
    del model
    _clear_cuda()

    x_train = np.load(train_features, mmap_mode="r")
    y_train = np.load(train_labels, mmap_mode="r")
    x_validation = np.load(validation_features, mmap_mode="r")
    y_validation = np.load(validation_labels, mmap_mode="r")
    head = FineClassificationHead(4096, len(classes)).to("cuda")
    optimizer = torch.optim.AdamW(head.parameters(), lr=2e-4, weight_decay=0.01)
    batch_size = 16
    total_steps = math.ceil(len(training) / batch_size) * 2
    warmup_steps = int(total_steps * 0.03)
    from transformers import get_cosine_schedule_with_warmup

    scheduler = get_cosine_schedule_with_warmup(
        optimizer, num_warmup_steps=warmup_steps, num_training_steps=total_steps
    )
    generator = random.Random(SEED)
    history = []
    for epoch in range(2):
        indices = list(range(len(training)))
        generator.shuffle(indices)
        head.train()
        losses = []
        for batch_indices in _batches(indices, batch_size):
            x = torch.from_numpy(np.asarray(x_train[list(batch_indices)], dtype=np.float32)).to("cuda")
            y = torch.from_numpy(np.asarray(y_train[list(batch_indices)], dtype=np.int64)).to("cuda")
            optimizer.zero_grad(set_to_none=True)
            loss = torch.nn.functional.cross_entropy(head(x), y)
            loss.backward()
            optimizer.step()
            scheduler.step()
            losses.append(float(loss.item()))
        history.append({"epoch": epoch + 1, "mean_loss": sum(losses) / len(losses)})
    save_file({key: value.detach().cpu() for key, value in head.state_dict().items()}, feature_root / "linear_probe_head.safetensors")
    head.eval()
    predictions: list[int] = []
    with torch.inference_mode():
        for start in range(0, len(validation), 256):
            x = torch.from_numpy(np.asarray(x_validation[start : start + 256], dtype=np.float32)).to("cuda")
            predictions.extend(head(x).argmax(dim=-1).cpu().tolist())
    targets = np.asarray(y_validation).tolist()
    probe_metrics = classification_metrics(targets, predictions, classes)
    probe_metrics.update(
        {
            "training_record_count": len(training),
            "available_full_training_record_count": len(all_primary),
            "training_class_counts": {
                label: sum(item.fine_label == label for item in training)
                for label in classes
            },
            "training_split": "train",
            "limited_data_diagnostic": True,
            "selection": "DETERMINISTIC_SHA256_STRATIFIED",
            **extraction,
            "validation_record_count": len(validation),
            "base_parameters_trainable": 0,
            "head_only": True,
            "epochs": 2,
            "batch_size": batch_size,
            "seed": SEED,
            "history": history,
        }
    )
    atomic_json(output / "baseline_linear_probe_metrics.json", probe_metrics)

    formal_head = FineClassificationHead(4096, len(classes)).to("cuda")
    formal_head.load_state_dict(load_file(args.checkpoint / "fine_head.safetensors"))
    formal_head.eval()
    base_head_predictions: list[int] = []
    with torch.inference_mode():
        for start in range(0, len(validation), 256):
            x = torch.from_numpy(np.asarray(x_validation[start : start + 256], dtype=np.float32)).to("cuda")
            base_head_predictions.extend(formal_head(x).argmax(dim=-1).cpu().tolist())
    diagnostic = classification_metrics(targets, base_head_predictions, classes)
    diagnostic["role"] = "REPRESENTATION_DEPENDENCY_DIAGNOSTIC_NOT_FAIR_BASELINE"
    atomic_json(output / "final_head_base_representation_diagnostic.json", diagnostic)
    del head, formal_head
    _clear_cuda()
    return raw_metrics, probe_metrics


def build_manifest(args: argparse.Namespace) -> dict[str, Any]:
    output = args.output
    classification = _json(output / "classification_metrics.json")
    evidence = _json(output / "evidence_state_metrics.json")
    raw = _json(output / "baseline_raw_qwen_metrics.json")
    probe = _json(output / "baseline_linear_probe_metrics.json")
    diagnostic = _json(output / "final_head_base_representation_diagnostic.json")
    final_f1 = float(classification["overall"]["macro_f1"])
    probe_f1 = float(probe["macro_f1"])
    raw_f1 = float(raw["macro_f1"])
    delta_probe = final_f1 - probe_f1
    delta_raw = final_f1 - raw_f1
    uplift = (
        "STRONG" if delta_probe >= 0.10 else
        "MODERATE" if delta_probe >= 0.03 else
        "WEAK" if delta_probe > 0.005 else
        "NONE" if delta_probe >= -0.005 else "NEGATIVE"
    )
    linear_explains = "false" if delta_probe >= 0.03 else "partially" if delta_probe > 0.005 else "true"
    overall_evidence = evidence["overall"]
    evidence_contract_gate = (
        overall_evidence["schema_valid_rate"] >= 0.95
        and overall_evidence["severe_hallucination_count"] == 0
    )
    insufficient_evidence = evidence["basic_insufficient"]
    evidence_capability_gate = (
        evidence_contract_gate
        and insufficient_evidence["sufficiency"]["f1"] >= 0.70
        and insufficient_evidence["missing_evidence"]["micro_f1"] >= 0.50
    )
    classification_gate = bool(classification["formal_macro_f1_reproduced"])
    artifacts = {}
    for path in sorted(output.rglob("*")):
        if (
            path.is_file()
            and "quarantine" not in path.name
            and ".tmp." not in path.name
            and path.name != "evaluation_manifest.json"
        ):
            artifacts[str(path.relative_to(output))] = {
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
    training_ids = {
        item.sample_id for item in _records(args.training_corpus, SFTRecordV2)
    }
    validation_ids = {
        item.sample_id for item in _records(args.validation, NearValidationRecordV1)
    }
    identity_overlap = len(training_ids & validation_ids)
    classification_value = delta_probe > 0.005 and delta_raw > 0.10
    accepted = classification_gate and evidence_contract_gate and identity_overlap == 0 and (
        classification_value or evidence_capability_gate
    )
    manifest = {
        "version": MODEL_A_EVALUATION_VERSION,
        "status": "PASS" if accepted else "BLOCKED",
        "formal_run_id": args.run_root.name,
        "formal_checkpoint": str(args.checkpoint),
        "checkpoint_immutable": True,
        "validation_path": str(args.validation),
        "validation_sha256": sha256_file(args.validation),
        "training_validation_identity_overlap": identity_overlap,
        "formal_macro_f1_reproduced": classification_gate,
        "evidence_state_contract_gate_pass": evidence_contract_gate,
        "evidence_state_capability_gate_pass": evidence_capability_gate,
        "evidence_state_status": "PASS" if evidence_capability_gate else "FAIL",
        "classification_value_detected": classification_value,
        "sft_classification_uplift_status": uplift,
        "linear_head_only_explains_result": linear_explains,
        "model_a_accepted_for_warm_start": accepted,
        "base_representation_already_highly_separable": probe_f1 >= 0.99,
        "limited_data_probe_below_sft": probe_f1 < final_f1,
        "limited_probe_gap_is_exact_lora_uplift": False,
        "deltas": {"formal_minus_linear_probe_macro_f1": delta_probe, "formal_minus_raw_qwen_macro_f1": delta_raw},
        "formal": classification["overall"],
        "raw_qwen": raw,
        "linear_probe": probe,
        "final_head_without_lora_diagnostic": diagnostic,
        "evidence_state": evidence,
        "artifacts": artifacts,
    }
    atomic_json(output / "evaluation_manifest.json", manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("classification", "evidence", "controls", "manifest", "all"))
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--model-root", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--pretraining-root", type=Path, default=DEFAULT_PRETRAINING)
    parser.add_argument("--freeze-root", type=Path, default=DEFAULT_FREEZE)
    parser.add_argument("--eligibility-root", type=Path, default=DEFAULT_ELIGIBILITY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--generation-batch-size", type=int, default=4)
    parser.add_argument("--evidence-max-new-tokens", type=int, default=256)
    parser.add_argument("--raw-max-new-tokens", type=int, default=192)
    parser.add_argument("--probe-per-class", type=int, default=600)
    args = parser.parse_args()
    args.validation = args.pretraining_root / "validation/near_known_validation_v3.jsonl"
    args.training_corpus = args.pretraining_root / "sft_corpus/final/observable_sft_corpus_v3.jsonl"
    args.class_map = args.freeze_root / "manifests/main_class_map.json"
    if args.batch_size <= 0 or args.generation_batch_size <= 0:
        parser.error("batch sizes must be positive")
    return args


def main() -> None:
    args = parse_args()
    if args.phase in {"classification", "all"}:
        run_final_classification(args)
    if args.phase in {"evidence", "all"}:
        run_evidence_generation(args)
    if args.phase in {"controls", "all"}:
        run_base_controls(args)
    if args.phase in {"manifest", "all"}:
        manifest = build_manifest(args)
        print(json.dumps({
            "status": manifest["status"],
            "model_a_accepted_for_warm_start": manifest["model_a_accepted_for_warm_start"],
            "formal_macro_f1": manifest["formal"]["macro_f1"],
        }, sort_keys=True))


if __name__ == "__main__":
    main()
