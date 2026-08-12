#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import random
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from flowsec.training.contracts import NearValidationRecordV1
from flowsec.training.harness import per_record_causal_lm_loss
from flowsec.training.runtime_preflight import (
    RUNTIME_PREFLIGHT_VERSION,
    exact_parameter_snapshot_match,
    gradient_parameter_audit,
    instantiated_parameter_audit,
    optimizer_parameter_audit,
    select_runtime_smoke_records,
    snapshot_named_parameters,
)
from flowsec.training.train_near_sft import (
    _atomic_json,
    _configured_sft_record_model,
    _load_records,
    _load_yaml,
    _macro_f1,
    _save_checkpoint,
    build_training_runtime,
    formal_preflight,
    forward_training_record,
    initialize_run_directory,
    resolve_formal_paths,
    validation_classification_forward,
)
from flowsec.training.harness import load_near_class_map


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_status(repo_root: Path) -> list[str]:
    output = subprocess.run(
        ["git", "status", "--short"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return output.splitlines()


def _tensor_finite(value: Any) -> bool:
    import torch

    return bool(torch.isfinite(value.detach()).all())


def _optimizer_step(harness: Any, optimizer: Any, scheduler: Any, max_grad_norm: float) -> None:
    import torch

    torch.nn.utils.clip_grad_norm_(
        [parameter for parameter in harness.parameters() if parameter.requires_grad],
        max_grad_norm,
    )
    optimizer.step()
    scheduler.step()
    optimizer.zero_grad(set_to_none=True)


def _loss_record(
    output: dict[str, Any],
    encoded: dict[str, list[int]],
    *,
    record_weight: float,
    classification_loss_weight: float,
    evidence_loss_weight: float,
) -> dict[str, Any]:
    import torch

    labels = torch.tensor([encoded["lm_labels"]], device="cuda")
    unweighted, valid = per_record_causal_lm_loss(output["lm_logits"], labels)
    if not bool(valid.item()):
        raise RuntimeError("formal record has no Evidence-State target tokens")
    expected_weighted = unweighted[0] * record_weight
    if not torch.allclose(
        output["evidence_lm_loss"].detach(),
        expected_weighted.detach(),
        rtol=2e-2,
        atol=2e-2,
    ):
        raise RuntimeError("runtime Evidence loss did not apply session_weight")
    for key in ("loss", "classification_loss", "evidence_lm_loss"):
        if not _tensor_finite(output[key]):
            raise RuntimeError(f"non-finite runtime loss: {key}")
    expected_total = (
        classification_loss_weight * output["classification_loss"].detach()
        + evidence_loss_weight * output["evidence_lm_loss"].detach()
    )
    if not torch.allclose(
        output["loss"].detach(), expected_total, rtol=1e-5, atol=1e-5
    ):
        raise RuntimeError("runtime total loss does not match configured multi-task loss")
    return {
        "total_loss": float(output["loss"].detach().float().cpu()),
        "classification_loss": float(
            output["classification_loss"].detach().float().cpu()
        ),
        "evidence_loss": float(output["evidence_lm_loss"].detach().float().cpu()),
        "raw_evidence_loss": float(unweighted[0].detach().float().cpu()),
        "record_weight": record_weight,
        "classification_supervised_count": int(
            output["classification_supervised_count"].detach().cpu()
        ),
    }


def _expected_rng_draws() -> dict[str, Any]:
    import torch

    return {
        "python": random.random(),
        "numpy": float(np.random.random()),
        "torch": torch.rand(4),
        "cuda": torch.rand(4, device="cuda").cpu(),
    }


def _rng_matches(expected: dict[str, Any]) -> bool:
    import torch

    observed = _expected_rng_draws()
    return bool(
        observed["python"] == expected["python"]
        and observed["numpy"] == expected["numpy"]
        and torch.equal(observed["torch"], expected["torch"])
        and torch.equal(observed["cuda"], expected["cuda"])
    )


def _select_validation(
    validation: list[NearValidationRecordV1], classes: tuple[str, ...]
) -> list[NearValidationRecordV1]:
    output = []
    for fine_label in classes:
        output.append(next(item for item in validation if item.fine_label == fine_label))
    return output


def run(args: argparse.Namespace) -> dict[str, Any]:
    import peft
    import torch
    import transformers

    repo_root = Path(args.repo_root).resolve()
    config_path = Path(args.config).resolve()
    smoke_root = Path(args.smoke_output_root).resolve()
    if smoke_root.exists():
        raise FileExistsError(f"disposable smoke output already exists: {smoke_root}")

    config = _load_yaml(config_path)
    paths = resolve_formal_paths(config)
    metadata = formal_preflight(config_path, repo_root=repo_root)
    if metadata["corpus_sha256"] != args.expected_corpus_sha256:
        raise RuntimeError("accepted formal corpus SHA256 changed")
    if paths["output_root"].exists() and any(paths["output_root"].iterdir()):
        raise RuntimeError("formal SFT output root is not idle")
    formal_output_initially_absent = not paths["output_root"].exists()

    classes, class_map = load_near_class_map(paths["preset_manifest"])
    if tuple(classes) != (
        "Normal",
        "DDoS_HTTP",
        "DDoS_TCP",
        "Password",
        "SQL_injection",
        "Vulnerability_scanner",
    ):
        raise RuntimeError("formal six-class order changed")
    records = _load_records(paths["corpus"], _configured_sft_record_model(config))
    validation = _load_records(paths["validation"], NearValidationRecordV1)
    selected, coverage = select_runtime_smoke_records(
        records,
        limit=int(args.record_limit),
        seed=int(config["schedule"]["seed"]),
    )
    selected_validation = _select_validation(validation, classes)

    accumulation = int(config["schedule"]["gradient_accumulation_steps"])
    if len(selected) < int(args.optimizer_steps) * accumulation:
        raise RuntimeError("smoke subset cannot provide the requested optimizer steps")
    formal_total_steps = math.ceil(
        len(records)
        * int(config["schedule"]["epochs"])
        / accumulation
    )
    run_metadata = {
        **metadata,
        "purpose": "DISPOSABLE_RUNTIME_PREFLIGHT_NOT_FORMAL_SFT",
        "runtime_preflight_version": RUNTIME_PREFLIGHT_VERSION,
        "formal_sft_run": False,
        "sft_runtime_smoke": True,
        "smoke_record_limit": len(selected),
        "smoke_optimizer_steps": int(args.optimizer_steps),
        "source_worktree_status": _git_status(repo_root),
    }
    run_root = initialize_run_directory(
        smoke_root.parent,
        smoke_root.name,
        run_metadata,
        config_path,
        resume=None,
    )
    _atomic_json(
        run_root / "DISPOSABLE_NOT_FORMAL.json",
        {
            "disposable": True,
            "formal_sft_run": False,
            "must_not_resume_as_formal": True,
            "formal_base_initialization_required": True,
        },
    )

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    runtime = build_training_runtime(
        config,
        paths,
        class_count=len(classes),
        total_steps=formal_total_steps,
    )
    tokenizer = runtime["tokenizer"]
    harness = runtime["harness"]
    optimizer = runtime["optimizer"]
    scheduler = runtime["scheduler"]
    parameter_audit = instantiated_parameter_audit(harness)
    optimizer_audit = optimizer_parameter_audit(harness, optimizer)
    if parameter_audit["fine_head_dimension"] != 6:
        raise RuntimeError("Fine Head output dimension is not six")
    optimizer.zero_grad(set_to_none=True)
    harness.train()

    max_length = int(config["schedule"]["max_sequence_length"])
    classification_loss_weight = float(
        config["architecture"]["classification_loss_weight"]
    )
    evidence_loss_weight = float(config["architecture"]["evidence_lm_loss_weight"])
    losses: list[dict[str, Any]] = []
    sequence_lengths: list[int] = []
    gradient_audit: dict[str, Any] | None = None
    primary_insufficient_ce_seen = False
    auxiliary_mask_seen = False
    weighted_runtime_checks = 0
    pre_resume_steps = int(args.optimizer_steps) - 1
    pre_resume_records = pre_resume_steps * accumulation
    state = runtime["state"]
    for position, record in enumerate(selected[:pre_resume_records]):
        output, encoded = forward_training_record(
            harness,
            tokenizer,
            record,
            class_map,
            max_length=max_length,
            loss_divisor=accumulation,
        )
        audit = _loss_record(
            output,
            encoded,
            record_weight=record.session_weight,
            classification_loss_weight=classification_loss_weight,
            evidence_loss_weight=evidence_loss_weight,
        )
        audit.update(
            {
                "position": position,
                "fine_label": record.fine_label,
                "state_role": record.state_role,
                "evidence_sufficient": record.evidence_state_target.evidence_sufficient,
                "gap_count": len(record.evidence_state_target.missing_evidence),
                "sequence_length": len(encoded["input_ids"]),
            }
        )
        losses.append(audit)
        sequence_lengths.append(len(encoded["input_ids"]))
        weighted_runtime_checks += 1
        if record.state_role == "primary" and not record.evidence_state_target.evidence_sufficient:
            primary_insufficient_ce_seen |= audit["classification_supervised_count"] == 1
        if record.state_role == "auxiliary":
            auxiliary_mask_seen |= (
                audit["classification_supervised_count"] == 0
                and audit["classification_loss"] == 0.0
            )
        if position == 0:
            gradient_audit = gradient_parameter_audit(harness)
        if (position + 1) % accumulation == 0:
            _optimizer_step(
                harness,
                optimizer,
                scheduler,
                float(config["optimizer"]["max_grad_norm"]),
            )
            state.update(
                {
                    "epoch": 0,
                    "next_record_index": position + 1,
                    "optimizer_step": (position + 1) // accumulation,
                    "best_macro_f1": -1.0,
                }
            )
            print(
                f"RUNTIME_SMOKE_STEP={state['optimizer_step']} "
                f"records={position + 1} sequence_max={max(sequence_lengths)}",
                flush=True,
            )

    if gradient_audit is None or not primary_insufficient_ce_seen or not auxiliary_mask_seen:
        raise RuntimeError("runtime loss/mask/gradient coverage is incomplete")
    paired_weights = Counter()
    paired_primary = Counter()
    selected_session_counts = Counter(item.sample_id for item in selected)
    multi_session_ids = {
        sample_id for sample_id, count in selected_session_counts.items() if count >= 2
    }
    for record in records:
        if record.sample_id in multi_session_ids:
            paired_weights[record.sample_id] += record.session_weight
            paired_primary[record.sample_id] += int(record.classification_ce_eligible)
    if not paired_weights or any(abs(value - 1.0) > 1e-9 for value in paired_weights.values()):
        raise RuntimeError("selected runtime session weights do not sum to one")
    if any(value != 1 for value in paired_primary.values()):
        raise RuntimeError("selected runtime trajectory does not have exactly one CE primary")

    fine_before_save = snapshot_named_parameters(harness, groups=("fine_head",))
    lora_before_save = snapshot_named_parameters(harness, groups=("lora",))
    trainable_after_steps = snapshot_named_parameters(
        harness, groups=("fine_head", "lora")
    )
    checkpoint = _save_checkpoint(
        run_root,
        harness,
        optimizer,
        scheduler,
        state,
        run_metadata,
        save_total_limit=int(config["schedule"]["save_total_limit"]),
    )
    expected_rng = _expected_rng_draws()
    checkpoint_size = sum(
        path.stat().st_size for path in checkpoint.rglob("*") if path.is_file()
    )

    del runtime, tokenizer, harness, optimizer, scheduler
    gc.collect()
    torch.cuda.empty_cache()

    resumed = build_training_runtime(
        config,
        paths,
        class_count=len(classes),
        total_steps=formal_total_steps,
        checkpoint=checkpoint,
    )
    tokenizer = resumed["tokenizer"]
    harness = resumed["harness"]
    optimizer = resumed["optimizer"]
    scheduler = resumed["scheduler"]
    resumed_state = resumed["state"]
    rng_restored = _rng_matches(expected_rng)
    fine_head_restored = exact_parameter_snapshot_match(fine_before_save, harness)
    lora_restored = exact_parameter_snapshot_match(lora_before_save, harness)
    if not rng_restored or not fine_head_restored or not lora_restored:
        raise RuntimeError("checkpoint model/RNG state did not restore exactly")
    if int(resumed_state["optimizer_step"]) != pre_resume_steps:
        raise RuntimeError("trainer step did not restore")
    if not optimizer.state or scheduler.last_epoch != pre_resume_steps:
        raise RuntimeError("optimizer or scheduler state did not restore")
    optimizer_parameter_audit(harness, optimizer)
    harness.train()
    optimizer.zero_grad(set_to_none=True)

    resumed_start = pre_resume_records
    resumed_end = int(args.optimizer_steps) * accumulation
    for position, record in enumerate(
        selected[resumed_start:resumed_end], start=resumed_start
    ):
        output, encoded = forward_training_record(
            harness,
            tokenizer,
            record,
            class_map,
            max_length=max_length,
            loss_divisor=accumulation,
        )
        audit = _loss_record(
            output,
            encoded,
            record_weight=record.session_weight,
            classification_loss_weight=classification_loss_weight,
            evidence_loss_weight=evidence_loss_weight,
        )
        audit.update(
            {
                "position": position,
                "fine_label": record.fine_label,
                "state_role": record.state_role,
                "evidence_sufficient": record.evidence_state_target.evidence_sufficient,
                "gap_count": len(record.evidence_state_target.missing_evidence),
                "sequence_length": len(encoded["input_ids"]),
                "resumed": True,
            }
        )
        losses.append(audit)
        sequence_lengths.append(len(encoded["input_ids"]))
        weighted_runtime_checks += 1
    _optimizer_step(
        harness,
        optimizer,
        scheduler,
        float(config["optimizer"]["max_grad_norm"]),
    )
    resumed_state.update(
        {
            "next_record_index": resumed_end,
            "optimizer_step": int(args.optimizer_steps),
        }
    )
    resumed_checkpoint = _save_checkpoint(
        run_root,
        harness,
        optimizer,
        scheduler,
        resumed_state,
        run_metadata,
        save_total_limit=int(config["schedule"]["save_total_limit"]),
    )
    print(
        f"RUNTIME_SMOKE_RESUMED_STEP={resumed_state['optimizer_step']} "
        f"records={resumed_end}",
        flush=True,
    )

    # Prove that optimizer updates changed both trainable components while the
    # checkpoint equality checks above prove save/reload fidelity.
    import torch as _torch

    current = dict(harness.named_parameters())
    changed_lora = any(
        not _torch.equal(value, current[name].detach().cpu())
        for name, value in trainable_after_steps.items()
        if "lora_" in name
    )
    changed_head = any(
        not _torch.equal(value, current[name].detach().cpu())
        for name, value in trainable_after_steps.items()
        if name.startswith("fine_head.")
    )
    if not changed_lora or not changed_head:
        raise RuntimeError("resumed optimizer step did not update LoRA and Fine Head")

    harness.eval()
    predictions: list[int] = []
    labels: list[int] = []
    validation_lengths: list[int] = []
    for item in selected_validation:
        prediction, label, length = validation_classification_forward(
            harness, tokenizer, item, class_map
        )
        predictions.append(prediction)
        labels.append(label)
        validation_lengths.append(length)
    smoke_macro_f1 = _macro_f1(predictions, labels, len(classes))
    if not math.isfinite(smoke_macro_f1):
        raise RuntimeError("validation metric code returned a non-finite value")
    generation_item = selected_validation[0]
    generation_inputs = tokenizer(
        generation_item.serialized_model_input,
        add_special_tokens=True,
        return_tensors="pt",
    ).to("cuda")
    with torch.no_grad():
        generated = harness.language_model.generate(
            **generation_inputs,
            do_sample=False,
            max_new_tokens=int(args.generation_tokens),
            use_cache=True,
        )
    generated_token_count = int(
        generated.shape[1] - generation_inputs["input_ids"].shape[1]
    )
    if generated_token_count <= 0:
        raise RuntimeError("validation Evidence-State generation emitted no tokens")

    peak_memory = int(torch.cuda.max_memory_allocated())
    elapsed = time.perf_counter() - started
    formal_output_still_absent = not paths["output_root"].exists()
    if formal_output_initially_absent and not formal_output_still_absent:
        raise RuntimeError("disposable smoke polluted the formal output root")
    loss_summary = {
        "classification_min": min(item["classification_loss"] for item in losses),
        "classification_max": max(item["classification_loss"] for item in losses),
        "evidence_min": min(item["evidence_loss"] for item in losses),
        "evidence_max": max(item["evidence_loss"] for item in losses),
        "total_min": min(item["total_loss"] for item in losses),
        "total_max": max(item["total_loss"] for item in losses),
    }
    report = {
        "version": RUNTIME_PREFLIGHT_VERSION,
        "status": "PASS",
        "purpose": "DISPOSABLE_TINY_SFT_RUNTIME_SMOKE_NOT_A_FORMAL_RESULT",
        "formal_sft_started": False,
        "sft_runtime_smoke": True,
        "entrypoint": "python -m flowsec.training.train_near_sft",
        "config_path": str(config_path),
        "resolved_paths": {name: str(value) for name, value in sorted(paths.items())},
        "formal_preflight": metadata,
        "model": {
            "model_id_or_path": str(paths["model_root"]),
            "model_id": config["model"]["model_id"],
            "revision": config["model"]["revision"],
            "tokenizer_revision": config["model"]["tokenizer_revision"],
            "dtype": "bfloat16",
            "bf16_supported": bool(torch.cuda.is_bf16_supported()),
        },
        "environment": {
            "gpu_model": torch.cuda.get_device_name(0),
            "gpu_memory_total_bytes": int(
                torch.cuda.get_device_properties(0).total_memory
            ),
            "peak_gpu_memory_bytes": peak_memory,
            "torch_version": torch.__version__,
            "cuda_version": torch.version.cuda,
            "transformers_version": transformers.__version__,
            "peft_version": peft.__version__,
        },
        "parameter_audit": parameter_audit,
        "optimizer_audit": optimizer_audit,
        "gradient_audit": gradient_audit,
        "corpus": {
            "path": str(paths["corpus"]),
            "sha256": _sha256(paths["corpus"]),
            "sha256_status": "PASS",
            "record_count": len(records),
            "selected": coverage,
        },
        "runtime_contract": {
            "session_weight_runtime_status": "PASS",
            "weighted_evidence_loss_checks": weighted_runtime_checks,
            "selected_multi_session_weight_sums": dict(sorted(paired_weights.items())),
            "selected_multi_session_primary_counts": dict(sorted(paired_primary.items())),
            "primary_insufficient_classification_ce_seen": primary_insufficient_ce_seen,
            "auxiliary_classification_mask_seen": auxiliary_mask_seen,
            "max_runtime_batch_sequence_length": max(sequence_lengths),
            "max_sequence_length": max_length,
            "loss_summary": loss_summary,
        },
        "smoke": {
            "status": "PASS",
            "optimizer_steps": int(args.optimizer_steps),
            "micro_batch_size": int(config["schedule"]["micro_batch_size"]),
            "gradient_accumulation_steps": accumulation,
            "effective_batch_size": int(config["schedule"]["micro_batch_size"])
            * accumulation,
            "formal_scheduler_total_steps": formal_total_steps,
            "elapsed_seconds": elapsed,
            "checkpoint_before_resume": str(checkpoint),
            "checkpoint_after_resume": str(resumed_checkpoint),
            "checkpoint_size_bytes": checkpoint_size,
            "checkpoint_save_status": "PASS",
            "checkpoint_resume_status": "PASS",
            "fine_head_checkpoint_status": "PASS",
            "lora_checkpoint_status": "PASS",
            "optimizer_resume_status": "PASS",
            "scheduler_resume_status": "PASS",
            "rng_resume_status": "PASS",
            "lora_updated_after_resume": changed_lora,
            "fine_head_updated_after_resume": changed_head,
            "disposable": True,
            "not_formal": True,
        },
        "validation": {
            "status": "PASS",
            "view": "EXACT_EVAL_CLEAN",
            "record_count": len(selected_validation),
            "class_count": len(set(item.fine_label for item in selected_validation)),
            "fine_logits_dimension": 6,
            "max_input_length": max(validation_lengths),
            "evidence_generation_executed": True,
            "generated_token_count": generated_token_count,
            "metric_code_executed": True,
            "metric_value_persisted": False,
            "result_semantics": "NOT_A_FORMAL_RESULT",
        },
        "output_isolation": {
            "smoke_root": str(run_root),
            "formal_output_root": str(paths["output_root"]),
            "formal_output_initially_absent": formal_output_initially_absent,
            "formal_output_still_absent": formal_output_still_absent,
            "status": "PASS",
        },
        "reproducibility": {
            "seed": int(config["schedule"]["seed"]),
            "python_seeded": True,
            "numpy_seeded": True,
            "torch_seeded": True,
            "cuda_seeded": True,
            "dataloader_workers": int(config["schedule"]["dataloader_workers"]),
            "data_order": config["schedule"]["shuffle"],
            "gpu_determinism_limitation": (
                "Exact cross-run GPU determinism is not guaranteed for all CUDA kernels; "
                "checkpoint RNG and deterministic record ordering are preserved."
            ),
        },
        "formal_config": {
            "status": "PASS",
            "config_sha256": _sha256(config_path),
            "snapshot_path": str(run_root / "config.snapshot.yaml"),
            "formal_output_root": str(paths["output_root"]),
            "formal_command": args.formal_command,
            "do_not_execute_in_preflight": True,
        },
        "ready_to_start_formal_sft": True,
        "next_action": "START_FORMAL_NEAR_MULTI_TASK_SFT",
    }
    _atomic_json(run_root / "runtime_preflight_manifest.json", report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--config", type=Path, default=Path("configs/training/near_sft_config_v2.yaml")
    )
    parser.add_argument(
        "--smoke-output-root",
        type=Path,
        default=Path(
            "/root/autodl-tmp/processed/sft_runtime_smoke/"
            "formal_near_multitask_sft_preflight_v1"
        ),
    )
    parser.add_argument("--record-limit", type=int, default=64)
    parser.add_argument("--optimizer-steps", type=int, default=4)
    parser.add_argument("--generation-tokens", type=int, default=32)
    parser.add_argument(
        "--expected-corpus-sha256",
        default="d93789de29b746d923660bb2e4ccad501412e75303ddf95f7087c85f6c67d6ca",
    )
    parser.add_argument(
        "--formal-command",
        default=(
            "ARTIFACT_ROOT=/root/autodl-tmp/processed "
            "QWEN_MODEL_PATH=/root/autodl-tmp/models/Qwen3.5-9B "
            "PYTHONPATH=src /root/autodl-tmp/conda/qwen35-runtime/bin/python "
            "-m flowsec.training.train_near_sft --config "
            "configs/training/near_sft_config_v2.yaml --execute"
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
