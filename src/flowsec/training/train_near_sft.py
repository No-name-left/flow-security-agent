from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .contracts import (
    EVIDENCE_STATE_SCHEMA_V2,
    NearValidationRecordV1,
    SFTRecordV1,
    SFTRecordV2,
    canonical_json,
)
from .corpus import sha256_file
from .harness import POOL_MEAN, TrafficExpertTrainingHarness, attach_lora, load_near_class_map


LAUNCHER_VERSION = "FORMAL_NEAR_SFT_LAUNCHER_V3"


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("formal SFT config must be a mapping")
    return value


def _git_head(repo_root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _validated_class_index(
    record: SFTRecordV1 | NearValidationRecordV1,
    class_map: dict[str, int],
    *,
    asset_name: str,
) -> int:
    expected = class_map.get(record.fine_label)
    if expected is None:
        raise RuntimeError(
            f"{asset_name} record has a fine label outside the active class map: "
            f"{record.fine_label}"
        )
    if record.class_index != expected:
        raise RuntimeError(
            f"{asset_name} record class_index disagrees with active class map: "
            f"{record.fine_label} has {record.class_index}, expected {expected}"
        )
    return expected


def _validated_jsonl_records(path: Path, model: Any, *, asset_name: str) -> list[Any]:
    records: list[Any] = []
    for line_number, line in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            records.append(model.model_validate_json(line))
        except ValueError as exc:
            raise RuntimeError(
                f"{asset_name} record failed schema validation at line {line_number}"
            ) from exc
    return records


def validate_formal_record_contract(
    corpus_path: Path,
    validation_path: Path,
    class_map: dict[str, int],
    *,
    expected_unique_sessions: int,
    max_states_per_session: int,
    record_model: Any = SFTRecordV1,
) -> dict[str, Any]:
    """Validate actual JSONL rows rather than trusting summary manifests."""

    if expected_unique_sessions <= 0:
        raise RuntimeError("expected_unique_sessions must be positive")
    if max_states_per_session <= 0:
        raise RuntimeError("max_states_per_session must be positive")

    corpus = _validated_jsonl_records(corpus_path, record_model, asset_name="SFT corpus")
    validation = _validated_jsonl_records(
        validation_path,
        NearValidationRecordV1,
        asset_name="validation corpus",
    )
    state_counts: Counter[str] = Counter()
    weight_totals: defaultdict[str, float] = defaultdict(float)
    corpus_classes: Counter[str] = Counter()
    validation_classes: Counter[str] = Counter()
    validation_sessions: set[str] = set()

    for record in corpus:
        _validated_class_index(record, class_map, asset_name="SFT corpus")
        state_counts[record.sample_id] += 1
        if state_counts[record.sample_id] > max_states_per_session:
            raise RuntimeError(
                "SFT corpus exceeds configured max_states_per_session for "
                f"{record.sample_id}"
            )
        weight_totals[record.sample_id] += record.session_weight
        corpus_classes[record.fine_label] += 1

    if len(state_counts) != expected_unique_sessions:
        raise RuntimeError(
            "SFT corpus unique-session count disagrees with configured "
            f"expected_unique_sessions: {len(state_counts)} != {expected_unique_sessions}"
        )
    invalid_weight_sessions = [
        sample_id
        for sample_id, total in weight_totals.items()
        if abs(total - 1.0) > 1e-9
    ]
    if invalid_weight_sessions:
        raise RuntimeError(
            "SFT corpus session weights do not sum to one; first invalid session: "
            f"{invalid_weight_sessions[0]}"
        )

    for record in validation:
        _validated_class_index(record, class_map, asset_name="validation corpus")
        if record.sample_id in validation_sessions:
            raise RuntimeError(
                f"validation corpus contains duplicate sample identity: {record.sample_id}"
            )
        validation_sessions.add(record.sample_id)
        validation_classes[record.fine_label] += 1

    overlap = set(state_counts) & validation_sessions
    if overlap:
        raise RuntimeError(
            "formal SFT and validation corpora overlap sample identity; first overlap: "
            f"{sorted(overlap)[0]}"
        )

    return {
        "corpus_record_count": len(corpus),
        "corpus_unique_sessions": len(state_counts),
        "corpus_class_distribution": dict(sorted(corpus_classes.items())),
        "validation_record_count": len(validation),
        "train_validation_identity_overlap": 0,
        "validation_class_distribution": dict(sorted(validation_classes.items())),
        "max_states_per_session_observed": max(state_counts.values(), default=0),
        "invalid_session_weight_count": 0,
    }


def _configured_sft_record_model(config: dict[str, Any]) -> Any:
    schema_version = str(
        config.get("data", {}).get("evidence_state_schema_version") or ""
    )
    if schema_version == EVIDENCE_STATE_SCHEMA_V2:
        return SFTRecordV2
    if not schema_version or schema_version == "EVIDENCE_STATE_SCHEMA_V1":
        return SFTRecordV1
    raise RuntimeError(f"unsupported formal corpus schema: {schema_version}")


def resolve_formal_paths(config: dict[str, Any]) -> dict[str, Path]:
    artifact_root = os.environ.get(str(config["data"]["artifact_root_env"]))
    model_root = os.environ.get(str(config["model"]["local_path_env"]))
    if not artifact_root or not model_root:
        raise RuntimeError("ARTIFACT_ROOT and QWEN_MODEL_PATH must be configured")
    artifact = Path(artifact_root)
    pretraining = artifact / str(config["data"]["pretraining_asset_version"])
    paths = {
        "artifact_root": artifact,
        "pretraining_root": pretraining,
        "corpus": pretraining / str(config["data"]["corpus_path"]),
        "corpus_manifest": pretraining / str(config["data"]["corpus_manifest"]),
        "validation": pretraining / str(config["validation"]["corpus_path"]),
        "validation_manifest": pretraining / str(config["validation"]["manifest_path"]),
        "teacher_quality_manifest": pretraining / str(config["data"]["teacher_quality_manifest"]),
        "supervision_audit_manifest": pretraining / str(config["data"]["supervision_audit_manifest"]),
        "evidence_pair_audit_manifest": pretraining / str(config["data"]["evidence_pair_audit_manifest"]),
        "manual_review_manifest": pretraining / str(config["data"]["manual_review_manifest"]),
        "preset_manifest": artifact
        / str(config["data"]["production_asset_version"])
        / str(config["data"]["preset_manifest"]),
        "model_root": Path(model_root),
        "output_root": artifact / str(config["output"]["relative_root"]),
    }
    if config["data"].get("u_final_isolation_manifest"):
        paths["u_final_isolation_manifest"] = pretraining / str(
            config["data"]["u_final_isolation_manifest"]
        )
    return paths


def formal_preflight(config_path: Path, *, repo_root: Path | None = None) -> dict[str, Any]:
    config_path = Path(config_path).resolve()
    config = _load_yaml(config_path)
    paths = resolve_formal_paths(config)
    repo_root = Path(repo_root or config_path.parents[2]).resolve()
    if config.get("status") != "FROZEN_READY" or config.get("formal_run_authorized") is not True:
        raise RuntimeError("formal SFT config is not frozen/authorized")
    required_assets = [
        "corpus", "corpus_manifest", "validation", "validation_manifest", "preset_manifest",
        "teacher_quality_manifest", "supervision_audit_manifest",
        "evidence_pair_audit_manifest", "manual_review_manifest",
    ]
    if "u_final_isolation_manifest" in paths:
        required_assets.append("u_final_isolation_manifest")
    for name in required_assets:
        if not paths[name].is_file():
            raise FileNotFoundError(f"required formal SFT asset unavailable: {name}")
    if not paths["model_root"].is_dir():
        raise FileNotFoundError("Qwen model root is unavailable")

    corpus = _read_json(paths["corpus_manifest"])
    validation = _read_json(paths["validation_manifest"])
    audit_names = [
        "teacher_quality_manifest", "supervision_audit_manifest",
        "evidence_pair_audit_manifest", "manual_review_manifest",
    ]
    if "u_final_isolation_manifest" in paths:
        audit_names.append("u_final_isolation_manifest")
    audits = {name: _read_json(paths[name]) for name in audit_names}
    if corpus.get("status") != "PASS" or validation.get("status") != "PASS":
        raise RuntimeError("formal corpus or validation Gate is not PASS")
    if any(value.get("status") != "PASS" for value in audits.values()):
        raise RuntimeError("one or more final pre-training audits are not PASS")
    if any(int(corpus.get(key, -1)) != 0 for key in ("test_count", "u_dev_count", "u_final_count")):
        raise RuntimeError("formal corpus escaped TRAIN-only scope")
    if any(int(validation.get(key, -1)) != 0 for key in ("test_count", "u_dev_count", "u_final_count")):
        raise RuntimeError("formal validation asset escaped K-known validation scope")
    if sha256_file(paths["corpus"]) != corpus["artifacts"]["corpus"]["sha256"]:
        raise RuntimeError("formal corpus digest mismatch")
    if sha256_file(paths["validation"]) != validation["artifacts"]["validation_corpus"]["sha256"]:
        raise RuntimeError("formal validation digest mismatch")
    classes, class_map = load_near_class_map(paths["preset_manifest"])
    if set(corpus["class_distribution"]) != set(classes):
        raise RuntimeError("formal corpus class map mismatch")
    if set(validation["class_distribution"]) != set(classes):
        raise RuntimeError("validation class map mismatch")
    expected_sessions = int(config["data"]["expected_unique_sessions"])
    record_model = _configured_sft_record_model(config)
    record_contract = validate_formal_record_contract(
        paths["corpus"],
        paths["validation"],
        class_map,
        expected_unique_sessions=expected_sessions,
        max_states_per_session=int(config["quality_gates"]["max_states_per_session"]),
        record_model=record_model,
    )
    if record_contract["corpus_record_count"] != int(corpus.get("record_count", -1)):
        raise RuntimeError("formal corpus manifest record count disagrees with JSONL")
    if record_contract["validation_record_count"] != int(validation.get("record_count", -1)):
        raise RuntimeError("validation manifest record count disagrees with JSONL")
    if record_contract["corpus_class_distribution"] != corpus.get("class_distribution"):
        raise RuntimeError("formal corpus manifest class distribution disagrees with JSONL")
    if record_contract["validation_class_distribution"] != validation.get("class_distribution"):
        raise RuntimeError("validation manifest class distribution disagrees with JSONL")
    corpus_gate = {
        "version": corpus.get("version")
        == str(config["data"].get("corpus_version", "NEAR_SFT_CORPUS_V2")),
        "supervision_contract": corpus.get("supervision_contract") == config.get("supervision_contract"),
        "record_count": int(corpus.get("record_count", -1)) >= expected_sessions,
        "unique_sessions": int(corpus.get("unique_sessions", -1)) == expected_sessions,
        "classification_supervised_count": int(corpus.get("classification_supervised_count", -1)) == expected_sessions,
        "classification_supervised_unique_sessions": int(corpus.get("classification_supervised_unique_sessions", -1)) == expected_sessions,
        "classification_supervised_class_coverage": int(corpus.get("classification_supervised_class_coverage", -1)) == len(classes),
        "classification_supervised_class_map": set(corpus.get("classification_supervised_class_distribution", {})) == set(classes),
        "one_supervised_state_per_session": int(corpus.get("classification_supervised_states_per_session_max", -1)) == 1,
        "teacher_quarantine_zero": int(corpus.get("teacher_quarantine_count", -1)) == 0,
        "sequence_overflow_zero": int(corpus.get("token_lengths", {}).get("overflow_count", -1)) == 0,
        "label_collision_zero": int(corpus.get("label_collision_count", -1)) == 0,
        "invalid_weight_zero": int(corpus.get("invalid_session_weight_count", -1)) == 0,
        "model_input_identity_zero": int(corpus.get("model_input_backend_identity_count", -1)) == 0,
        "prohibited_model_input_key_zero": int(corpus.get("prohibited_model_input_key_count", -1)) == 0,
        "target_class_verdict_zero": int(corpus.get("target_class_verdict_count", -1)) == 0,
        "both_sufficiency_states_present": set(corpus.get("evidence_sufficiency_distribution", {})) == {"sufficient", "insufficient"},
    }
    failed_corpus_gates = sorted(key for key, value in corpus_gate.items() if not value)
    if failed_corpus_gates:
        raise RuntimeError(f"formal corpus scientific Gate failed: {failed_corpus_gates}")

    return {
        "status": "PASS",
        "launcher_version": LAUNCHER_VERSION,
        "config_path": str(config_path),
        "config_sha256": sha256_file(config_path),
        "git_commit": _git_head(repo_root),
        "model_id": config["model"]["model_id"],
        "model_revision": config["model"]["revision"],
        "tokenizer_revision": config["model"]["tokenizer_revision"],
        "seed": int(config["schedule"]["seed"]),
        "corpus_sha256": corpus["artifacts"]["corpus"]["sha256"],
        "corpus_manifest_digest": corpus["artifact_digest"],
        "corpus_records": int(corpus["record_count"]),
        "validation_sha256": validation["artifacts"]["validation_corpus"]["sha256"],
        "validation_manifest_digest": validation["artifact_digest"],
        "validation_records": int(validation["record_count"]),
        "max_states_per_session": record_contract["max_states_per_session_observed"],
        "supervision_contract": config["supervision_contract"],
        "audit_digests": {
            name: value.get("audit_digest") for name, value in sorted(audits.items())
        },
        "u_final_count": 0,
        "formal_sft_run": False,
    }


def validate_resume_metadata(current: dict[str, Any], saved: dict[str, Any]) -> None:
    immutable = (
        "launcher_version",
        "config_sha256",
        "model_id",
        "model_revision",
        "tokenizer_revision",
        "seed",
        "corpus_sha256",
        "corpus_manifest_digest",
        "validation_sha256",
        "validation_manifest_digest",
        "supervision_contract",
        "audit_digests",
    )
    mismatches = [key for key in immutable if current.get(key) != saved.get(key)]
    if mismatches:
        raise RuntimeError(f"resume checkpoint is incompatible: {mismatches}")


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def seed_training_runtime(seed: int) -> None:
    """Seed every RNG used by the formal manual data/optimization loop."""

    import numpy as np
    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def capture_runtime_rng_state() -> dict[str, Any]:
    import numpy as np
    import torch

    return {
        "torch": torch.get_rng_state(),
        "cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else [],
        "python": random.getstate(),
        "numpy": np.random.get_state(),
    }


def restore_runtime_rng_state(value: dict[str, Any]) -> None:
    import numpy as np
    import torch

    required = {"torch", "cuda", "python", "numpy"}
    if set(value) != required:
        raise RuntimeError(f"checkpoint RNG state is incomplete: {sorted(set(value))}")
    torch.set_rng_state(value["torch"])
    if torch.cuda.is_available():
        torch.cuda.set_rng_state_all(value["cuda"])
    random.setstate(value["python"])
    np.random.set_state(value["numpy"])


def initialize_run_directory(
    output_root: Path,
    run_id: str,
    metadata: dict[str, Any],
    config_path: Path,
    *,
    resume: Path | None,
) -> Path:
    run_root = Path(output_root) / run_id
    if resume is None:
        if run_root.exists():
            raise FileExistsError(f"formal run output already exists: {run_root}")
        run_root.mkdir(parents=True)
        shutil.copy2(config_path, run_root / "config.snapshot.yaml")
        _atomic_json(run_root / "run_manifest.json", {**metadata, "run_id": run_id})
    else:
        run_root = Path(resume).resolve()
        saved = _read_json(run_root / "run_manifest.json")
        validate_resume_metadata(metadata, saved)
    return run_root


def _encode_sft(
    tokenizer: Any, record: SFTRecordV1 | SFTRecordV2, max_length: int
) -> dict[str, list[int]]:
    target = canonical_json(record.evidence_state_target.model_dump(mode="json"))
    prompt_ids = tokenizer(record.serialized_model_input, add_special_tokens=True)["input_ids"]
    target_ids = tokenizer(target + tokenizer.eos_token, add_special_tokens=False)["input_ids"]
    if len(prompt_ids) + len(target_ids) > max_length:
        raise ValueError(f"frozen SFT record exceeds max sequence length: {record.evidence_state_id}")
    return {
        "input_ids": prompt_ids + target_ids,
        "lm_labels": [-100] * len(prompt_ids) + target_ids,
        "classification_mask": [1] * len(prompt_ids) + [0] * len(target_ids),
    }


def _macro_f1(predictions: list[int], labels: list[int], class_count: int) -> float:
    scores = []
    for klass in range(class_count):
        tp = sum(p == klass and y == klass for p, y in zip(predictions, labels, strict=True))
        fp = sum(p == klass and y != klass for p, y in zip(predictions, labels, strict=True))
        fn = sum(p != klass and y == klass for p, y in zip(predictions, labels, strict=True))
        denom = 2 * tp + fp + fn
        scores.append((2 * tp / denom) if denom else 0.0)
    return sum(scores) / len(scores)


def build_optimizer_step_log(
    *,
    run_id: str,
    epoch: int,
    epochs: int,
    record_index: int,
    records_per_epoch: int,
    optimizer_step: int,
    total_loss: float,
    classification_loss: float,
    evidence_loss: float,
    learning_rate: float,
) -> dict[str, Any]:
    """Build the machine-readable heartbeat emitted by the formal loop."""

    numeric = {
        "total_loss": total_loss,
        "classification_loss": classification_loss,
        "evidence_loss": evidence_loss,
        "learning_rate": learning_rate,
    }
    if not all(value == value and abs(value) != float("inf") for value in numeric.values()):
        raise FloatingPointError(f"non-finite formal training metric: {numeric}")
    return {
        "event": "formal_sft_optimizer_step",
        "run_id": run_id,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "epoch": epoch,
        "epochs": epochs,
        "record_index": record_index,
        "records_per_epoch": records_per_epoch,
        "optimizer_step": optimizer_step,
        **numeric,
    }


def _save_checkpoint(
    run_root: Path,
    harness: Any,
    optimizer: Any,
    scheduler: Any,
    trainer_state: dict[str, Any],
    metadata: dict[str, Any],
    *,
    save_total_limit: int,
) -> Path:
    import torch
    from safetensors.torch import save_file

    checkpoint = run_root / f"checkpoint-step-{int(trainer_state['optimizer_step']):08d}"
    if checkpoint.exists():
        raise FileExistsError(f"checkpoint already exists: {checkpoint}")
    checkpoint.mkdir(parents=True)
    harness.language_model.save_pretrained(checkpoint / "adapter", safe_serialization=True)
    save_file(
        {
            key: value.detach().cpu().contiguous()
            for key, value in harness.fine_head.state_dict().items()
        },
        checkpoint / "fine_head.safetensors",
    )
    torch.save(optimizer.state_dict(), checkpoint / "optimizer.pt")
    torch.save(scheduler.state_dict(), checkpoint / "scheduler.pt")
    torch.save(capture_runtime_rng_state(), checkpoint / "rng_state.pt")
    _atomic_json(checkpoint / "trainer_state.json", trainer_state)
    _atomic_json(checkpoint / "checkpoint_manifest.json", {**metadata, **trainer_state})
    checkpoints = sorted(run_root.glob("checkpoint-step-*"))
    for old in checkpoints[:-save_total_limit]:
        shutil.rmtree(old)
    return checkpoint


def _load_records(path: Path, model: Any) -> list[Any]:
    return [
        model.model_validate_json(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def build_training_runtime(
    config: dict[str, Any],
    paths: dict[str, Path],
    *,
    class_count: int,
    total_steps: int,
    checkpoint: Path | None = None,
) -> dict[str, Any]:
    """Instantiate the one formal BF16 LoRA + Fine Head training runtime."""

    import torch
    from peft import PeftModel
    from safetensors.torch import load_file
    from transformers import (
        AutoModelForImageTextToText,
        AutoTokenizer,
        get_cosine_schedule_with_warmup,
    )

    if class_count <= 1 or total_steps <= 0:
        raise ValueError("formal training runtime requires classes and optimizer steps")
    seed_training_runtime(int(config["schedule"]["seed"]))
    tokenizer = AutoTokenizer.from_pretrained(paths["model_root"], local_files_only=True)
    base = AutoModelForImageTextToText.from_pretrained(
        paths["model_root"],
        dtype=torch.bfloat16,
        device_map={"": 0},
        local_files_only=True,
    )
    if checkpoint is not None:
        base = PeftModel.from_pretrained(
            base, Path(checkpoint) / "adapter", is_trainable=True
        )
    else:
        base = attach_lora(
            base,
            rank=int(config["lora"]["rank"]),
            alpha=int(config["lora"]["alpha"]),
            dropout=float(config["lora"]["dropout"]),
            target_modules=tuple(config["lora"]["target_modules"]),
        )
    base.enable_input_require_grads()
    if config["schedule"]["gradient_checkpointing"]:
        base.gradient_checkpointing_enable()
    harness = TrafficExpertTrainingHarness(
        base,
        hidden_size=int(config["architecture"]["hidden_size"]),
        num_classes=class_count,
        pooling_method=POOL_MEAN,
        classification_loss_weight=float(
            config["architecture"]["classification_loss_weight"]
        ),
        evidence_loss_weight=float(config["architecture"]["evidence_lm_loss_weight"]),
    )
    harness.fine_head.to(device="cuda", dtype=torch.bfloat16)
    optimizer = torch.optim.AdamW(
        (parameter for parameter in harness.parameters() if parameter.requires_grad),
        lr=float(config["optimizer"]["learning_rate"]),
        weight_decay=float(config["optimizer"]["weight_decay"]),
    )
    scheduler = get_cosine_schedule_with_warmup(
        optimizer,
        num_warmup_steps=int(total_steps * float(config["optimizer"]["warmup_ratio"])),
        num_training_steps=total_steps,
    )
    state = {
        "epoch": 0,
        "next_record_index": 0,
        "optimizer_step": 0,
        "best_macro_f1": -1.0,
    }
    if checkpoint is not None:
        checkpoint = Path(checkpoint)
        harness.fine_head.load_state_dict(load_file(checkpoint / "fine_head.safetensors"))
        optimizer.load_state_dict(
            torch.load(
                checkpoint / "optimizer.pt",
                map_location="cuda",
                weights_only=False,
            )
        )
        scheduler.load_state_dict(
            torch.load(
                checkpoint / "scheduler.pt",
                map_location="cuda",
                weights_only=False,
            )
        )
        saved_rng = torch.load(
            checkpoint / "rng_state.pt", map_location="cpu", weights_only=False
        )
        restore_runtime_rng_state(saved_rng)
        state = _read_json(checkpoint / "trainer_state.json")
    return {
        "tokenizer": tokenizer,
        "harness": harness,
        "optimizer": optimizer,
        "scheduler": scheduler,
        "state": state,
    }


def forward_training_record(
    harness: Any,
    tokenizer: Any,
    record: SFTRecordV1 | SFTRecordV2,
    class_map: dict[str, int],
    *,
    max_length: int,
    loss_divisor: int,
) -> tuple[dict[str, Any], dict[str, list[int]]]:
    """Run the exact formal encode/forward/backward micro-step."""

    import torch

    if loss_divisor <= 0:
        raise ValueError("loss divisor must be positive")
    encoded = _encode_sft(tokenizer, record, max_length)
    input_ids = torch.tensor([encoded["input_ids"]], device="cuda")
    attention = torch.ones_like(input_ids)
    output = harness(
        input_ids=input_ids,
        attention_mask=attention,
        classification_attention_mask=torch.tensor(
            [encoded["classification_mask"]], device="cuda"
        ),
        lm_labels=torch.tensor([encoded["lm_labels"]], device="cuda"),
        fine_labels=torch.tensor([class_map[record.fine_label]], device="cuda"),
        classification_ce_eligible=torch.tensor(
            [record.classification_ce_eligible], device="cuda"
        ),
        record_weights=torch.tensor([record.session_weight], device="cuda"),
    )
    (output["loss"] / loss_divisor).backward()
    return output, encoded


def validation_classification_forward(
    harness: Any,
    tokenizer: Any,
    item: NearValidationRecordV1,
    class_map: dict[str, int],
) -> tuple[int, int, int]:
    import torch

    ids = tokenizer(
        item.serialized_model_input,
        add_special_tokens=True,
        return_tensors="pt",
    )
    input_ids = ids["input_ids"].to("cuda")
    attention = ids["attention_mask"].to("cuda")
    with torch.no_grad():
        result = harness(input_ids=input_ids, attention_mask=attention)
    return (
        int(result["fine_logits"].argmax(dim=-1).item()),
        _validated_class_index(item, class_map, asset_name="validation corpus"),
        int(input_ids.shape[1]),
    )


def run_formal_training(config_path: Path, *, run_id: str | None, resume: Path | None) -> Path:
    import torch

    config_path = Path(config_path).resolve()
    config = _load_yaml(config_path)
    paths = resolve_formal_paths(config)
    metadata = {**formal_preflight(config_path), "formal_sft_run": True}
    run_id = run_id or (
        "near-sft-v3-"
        + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + metadata["corpus_sha256"][:8]
    )
    run_root = initialize_run_directory(
        paths["output_root"], run_id, metadata, config_path, resume=resume
    )
    print(
        json.dumps(
            {
                "event": "formal_sft_start",
                "run_id": run_id,
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "config_path": str(config_path),
                "corpus_sha256": metadata["corpus_sha256"],
                "formal_sft_run": True,
                "resume": resume is not None,
                "run_root": str(run_root),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    classes, class_map = load_near_class_map(paths["preset_manifest"])
    records = _load_records(paths["corpus"], _configured_sft_record_model(config))
    validation = _load_records(paths["validation"], NearValidationRecordV1)
    accumulation = int(config["schedule"]["gradient_accumulation_steps"])
    epochs = int(config["schedule"]["epochs"])
    total_steps = (len(records) * epochs + accumulation - 1) // accumulation
    checkpoint = sorted(Path(resume).glob("checkpoint-step-*"))[-1] if resume else None
    runtime = build_training_runtime(
        config,
        paths,
        class_count=len(classes),
        total_steps=total_steps,
        checkpoint=checkpoint,
    )
    tokenizer = runtime["tokenizer"]
    harness = runtime["harness"]
    optimizer = runtime["optimizer"]
    scheduler = runtime["scheduler"]
    state = runtime["state"]

    max_length = int(config["schedule"]["max_sequence_length"])
    save_steps = int(config["schedule"]["save_steps"])
    harness.train()
    optimizer.zero_grad(set_to_none=True)
    step_loss_sums: dict[str, Any] = {}
    step_record_count = 0
    for epoch in range(int(state["epoch"]), epochs):
        order = list(range(len(records)))
        random.Random(metadata["seed"] + epoch).shuffle(order)
        start = int(state["next_record_index"]) if epoch == int(state["epoch"]) else 0
        for position in range(start, len(order)):
            record = records[order[position]]
            output, _encoded = forward_training_record(
                harness,
                tokenizer,
                record,
                class_map,
                max_length=max_length,
                loss_divisor=accumulation,
            )
            for name, value in (
                ("total_loss", output["loss"]),
                ("classification_loss", output["classification_loss"]),
                ("evidence_loss", output["evidence_lm_loss"]),
            ):
                detached = value.detach().float()
                step_loss_sums[name] = step_loss_sums.get(name, 0.0) + detached
            step_record_count += 1
            if (position + 1) % accumulation == 0 or position + 1 == len(order):
                step_loss_averages = {
                    name: value / step_record_count
                    for name, value in step_loss_sums.items()
                }
                if not all(
                    bool(torch.isfinite(value).item())
                    for value in step_loss_averages.values()
                ):
                    raise FloatingPointError(
                        "non-finite formal training loss before optimizer step"
                    )
                torch.nn.utils.clip_grad_norm_(
                    [parameter for parameter in harness.parameters() if parameter.requires_grad],
                    float(config["optimizer"]["max_grad_norm"]),
                )
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad(set_to_none=True)
                state.update(
                    {
                        "epoch": epoch,
                        "next_record_index": position + 1,
                        "optimizer_step": int(state["optimizer_step"]) + 1,
                    }
                )
                step_log = build_optimizer_step_log(
                    run_id=run_id,
                    epoch=epoch + 1,
                    epochs=epochs,
                    record_index=position + 1,
                    records_per_epoch=len(order),
                    optimizer_step=int(state["optimizer_step"]),
                    total_loss=float(step_loss_averages["total_loss"].cpu()),
                    classification_loss=float(
                        step_loss_averages["classification_loss"].cpu()
                    ),
                    evidence_loss=float(step_loss_averages["evidence_loss"].cpu()),
                    learning_rate=float(optimizer.param_groups[0]["lr"]),
                )
                print(json.dumps(step_log, sort_keys=True), flush=True)
                _atomic_json(run_root / "training_status.json", step_log)
                step_loss_sums = {}
                step_record_count = 0
                if int(state["optimizer_step"]) % save_steps == 0:
                    _save_checkpoint(
                        run_root,
                        harness,
                        optimizer,
                        scheduler,
                        state,
                        metadata,
                        save_total_limit=int(config["schedule"]["save_total_limit"]),
                    )

        harness.eval()
        predictions: list[int] = []
        labels: list[int] = []
        for item in validation:
            prediction, label, _length = validation_classification_forward(
                harness, tokenizer, item, class_map
            )
            predictions.append(prediction)
            labels.append(label)
        macro_f1 = _macro_f1(predictions, labels, len(classes))
        state.update(
            {
                "epoch": epoch + 1,
                "next_record_index": 0,
                "best_macro_f1": max(float(state["best_macro_f1"]), macro_f1),
                "last_validation_macro_f1": macro_f1,
            }
        )
        _atomic_json(run_root / f"metrics-epoch-{epoch + 1}.json", {
            "epoch": epoch + 1,
            "known_validation_macro_f1": macro_f1,
            "primary_checkpoint_metric": "known_validation_macro_f1",
            "evidence_state_quality_gate": config["validation"]["evidence_state_quality_gate"],
        })
        _save_checkpoint(
            run_root,
            harness,
            optimizer,
            scheduler,
            state,
            metadata,
            save_total_limit=int(config["schedule"]["save_total_limit"]),
        )
        harness.train()
    _atomic_json(run_root / "completion.json", {**state, "status": "COMPLETE"})
    return run_root


def main() -> int:
    parser = argparse.ArgumentParser(description="Frozen formal Near multi-task SFT launcher.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--run-id")
    parser.add_argument("--resume", type=Path)
    args = parser.parse_args()
    if args.preflight_only or not args.execute:
        print(json.dumps(formal_preflight(args.config), indent=2, sort_keys=True))
        return 0
    run_root = run_formal_training(args.config, run_id=args.run_id, resume=args.resume)
    print(json.dumps({"status": "COMPLETE", "run_root": str(run_root)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
