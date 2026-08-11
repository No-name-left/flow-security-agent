from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .contracts import NearValidationRecordV1, SFTRecordV1, canonical_json
from .corpus import sha256_file
from .harness import POOL_MEAN, TrafficExpertTrainingHarness, attach_lora, load_near_class_map


LAUNCHER_VERSION = "FORMAL_NEAR_SFT_LAUNCHER_V1"


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


def resolve_formal_paths(config: dict[str, Any]) -> dict[str, Path]:
    artifact_root = os.environ.get(str(config["data"]["artifact_root_env"]))
    model_root = os.environ.get(str(config["model"]["local_path_env"]))
    if not artifact_root or not model_root:
        raise RuntimeError("ARTIFACT_ROOT and QWEN_MODEL_PATH must be configured")
    artifact = Path(artifact_root)
    pretraining = artifact / str(config["data"]["pretraining_asset_version"])
    return {
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


def formal_preflight(config_path: Path, *, repo_root: Path | None = None) -> dict[str, Any]:
    config_path = Path(config_path).resolve()
    config = _load_yaml(config_path)
    paths = resolve_formal_paths(config)
    repo_root = Path(repo_root or config_path.parents[2]).resolve()
    if config.get("status") != "FROZEN_READY" or config.get("formal_run_authorized") is not True:
        raise RuntimeError("formal SFT config is not frozen/authorized")
    for name in (
        "corpus", "corpus_manifest", "validation", "validation_manifest", "preset_manifest",
        "teacher_quality_manifest", "supervision_audit_manifest",
        "evidence_pair_audit_manifest", "manual_review_manifest",
    ):
        if not paths[name].is_file():
            raise FileNotFoundError(f"required formal SFT asset unavailable: {name}")
    if not paths["model_root"].is_dir():
        raise FileNotFoundError("Qwen model root is unavailable")

    corpus = _read_json(paths["corpus_manifest"])
    validation = _read_json(paths["validation_manifest"])
    audits = {
        name: _read_json(paths[name])
        for name in (
            "teacher_quality_manifest", "supervision_audit_manifest",
            "evidence_pair_audit_manifest", "manual_review_manifest",
        )
    }
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
    classes, _mapping = load_near_class_map(paths["preset_manifest"])
    if set(corpus["class_distribution"]) != set(classes):
        raise RuntimeError("formal corpus class map mismatch")
    if set(validation["class_distribution"]) != set(classes):
        raise RuntimeError("validation class map mismatch")
    expected_sessions = int(config["data"]["expected_unique_sessions"])
    corpus_gate = {
        "version": corpus.get("version") == "NEAR_SFT_CORPUS_V2",
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


def _encode_sft(tokenizer: Any, record: SFTRecordV1, max_length: int) -> dict[str, list[int]]:
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
    torch.save(
        {
            "torch": torch.get_rng_state(),
            "cuda": torch.cuda.get_rng_state_all(),
            "python": random.getstate(),
        },
        checkpoint / "rng_state.pt",
    )
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


def run_formal_training(config_path: Path, *, run_id: str | None, resume: Path | None) -> Path:
    import torch
    from peft import PeftModel
    from safetensors.torch import load_file
    from transformers import AutoModelForImageTextToText, AutoTokenizer, get_cosine_schedule_with_warmup

    config_path = Path(config_path).resolve()
    config = _load_yaml(config_path)
    paths = resolve_formal_paths(config)
    metadata = formal_preflight(config_path)
    run_id = run_id or (
        "near-sft-v1-"
        + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + metadata["corpus_sha256"][:8]
    )
    run_root = initialize_run_directory(
        paths["output_root"], run_id, metadata, config_path, resume=resume
    )
    classes, class_map = load_near_class_map(paths["preset_manifest"])
    records = _load_records(paths["corpus"], SFTRecordV1)
    validation = _load_records(paths["validation"], NearValidationRecordV1)
    tokenizer = AutoTokenizer.from_pretrained(paths["model_root"], local_files_only=True)
    torch.manual_seed(metadata["seed"])
    random.seed(metadata["seed"])

    base = AutoModelForImageTextToText.from_pretrained(
        paths["model_root"],
        dtype=torch.bfloat16,
        device_map={"": 0},
        local_files_only=True,
    )
    if resume:
        checkpoint = sorted(Path(resume).glob("checkpoint-step-*"))[-1]
        base = PeftModel.from_pretrained(base, checkpoint / "adapter", is_trainable=True)
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
        num_classes=len(classes),
        pooling_method=POOL_MEAN,
        classification_loss_weight=float(config["architecture"]["classification_loss_weight"]),
        evidence_loss_weight=float(config["architecture"]["evidence_lm_loss_weight"]),
    )
    harness.fine_head.to(device="cuda", dtype=torch.bfloat16)
    optimizer = torch.optim.AdamW(
        (parameter for parameter in harness.parameters() if parameter.requires_grad),
        lr=float(config["optimizer"]["learning_rate"]),
        weight_decay=float(config["optimizer"]["weight_decay"]),
    )
    accumulation = int(config["schedule"]["gradient_accumulation_steps"])
    epochs = int(config["schedule"]["epochs"])
    total_steps = (len(records) * epochs + accumulation - 1) // accumulation
    scheduler = get_cosine_schedule_with_warmup(
        optimizer,
        num_warmup_steps=int(total_steps * float(config["optimizer"]["warmup_ratio"])),
        num_training_steps=total_steps,
    )
    state = {"epoch": 0, "next_record_index": 0, "optimizer_step": 0, "best_macro_f1": -1.0}
    if resume:
        checkpoint = sorted(Path(resume).glob("checkpoint-step-*"))[-1]
        harness.fine_head.load_state_dict(load_file(checkpoint / "fine_head.safetensors"))
        optimizer.load_state_dict(torch.load(checkpoint / "optimizer.pt", map_location="cuda"))
        scheduler.load_state_dict(torch.load(checkpoint / "scheduler.pt", map_location="cuda"))
        saved_rng = torch.load(checkpoint / "rng_state.pt", map_location="cpu")
        torch.set_rng_state(saved_rng["torch"])
        torch.cuda.set_rng_state_all(saved_rng["cuda"])
        random.setstate(saved_rng["python"])
        state = _read_json(checkpoint / "trainer_state.json")

    max_length = int(config["schedule"]["max_sequence_length"])
    save_steps = int(config["schedule"]["save_steps"])
    harness.train()
    optimizer.zero_grad(set_to_none=True)
    for epoch in range(int(state["epoch"]), epochs):
        order = list(range(len(records)))
        random.Random(metadata["seed"] + epoch).shuffle(order)
        start = int(state["next_record_index"]) if epoch == int(state["epoch"]) else 0
        for position in range(start, len(order)):
            record = records[order[position]]
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
            (output["loss"] / accumulation).backward()
            if (position + 1) % accumulation == 0 or position + 1 == len(order):
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
        with torch.no_grad():
            for item in validation:
                ids = tokenizer(
                    item.serialized_model_input,
                    add_special_tokens=True,
                    return_tensors="pt",
                )
                input_ids = ids["input_ids"].to("cuda")
                attention = ids["attention_mask"].to("cuda")
                result = harness(input_ids=input_ids, attention_mask=attention)
                predictions.append(int(result["fine_logits"].argmax(dim=-1).item()))
                labels.append(item.class_index)
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
