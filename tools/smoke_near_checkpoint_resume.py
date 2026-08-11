#!/usr/bin/env python3
from __future__ import annotations

import gc
import hashlib
import json
import os
import random
import shutil
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    import torch
    from peft import PeftModel
    from safetensors.torch import load_file, save_file
    from transformers import AutoModelForImageTextToText, AutoTokenizer

    from flowsec.training.harness import (
        POOL_MEAN,
        TrafficExpertTrainingHarness,
        attach_lora,
        load_near_class_map,
        trainable_parameter_audit,
    )
    from dry_run_near_sft import _encode_record, _load_dry_run_snapshots

    artifact_root = Path(os.environ["ARTIFACT_ROOT"])
    output_root = artifact_root / "near_pretraining_v1"
    production_root = artifact_root / "edge_split_revision_v2"
    model_root = Path(os.environ["QWEN_MODEL_PATH"])
    snapshot_path = output_root / "sft_corpus/evidence_snapshot_universe_v1.jsonl"
    universe = _load_dry_run_snapshots(snapshot_path)
    primary = next(item for item in universe if item.classification_supervision_valid)
    auxiliary = next(item for item in universe if not item.classification_supervision_valid)
    classes, class_map = load_near_class_map(
        production_root / "manifests/edge_known_unknown_presets.json"
    )
    tokenizer = AutoTokenizer.from_pretrained(model_root, local_files_only=True)
    seed = 20260809
    torch.manual_seed(seed)
    random.seed(seed)

    def base_model() -> Any:
        return AutoModelForImageTextToText.from_pretrained(
            model_root,
            dtype=torch.bfloat16,
            device_map={"": 0},
            local_files_only=True,
        )

    def harness_for(model: Any) -> TrafficExpertTrainingHarness:
        model.enable_input_require_grads()
        model.gradient_checkpointing_enable()
        harness = TrafficExpertTrainingHarness(
            model,
            hidden_size=4096,
            num_classes=len(classes),
            pooling_method=POOL_MEAN,
            classification_loss_weight=1.0,
            evidence_loss_weight=0.35,
        )
        harness.fine_head.to(device="cuda", dtype=torch.bfloat16)
        harness.train()
        return harness

    def optimizer_for(harness: TrafficExpertTrainingHarness) -> Any:
        return torch.optim.AdamW(
            (parameter for parameter in harness.parameters() if parameter.requires_grad),
            lr=2e-4,
            weight_decay=0.01,
        )

    def step(harness: Any, optimizer: Any, scheduler: Any, snapshot: Any) -> dict[str, float | int]:
        input_ids, labels, classification_mask = _encode_record(
            tokenizer, snapshot, max_length=3072
        )
        inputs = torch.tensor([input_ids], device="cuda", dtype=torch.long)
        output = harness(
            input_ids=inputs,
            attention_mask=torch.ones_like(inputs),
            classification_attention_mask=torch.tensor(
                [classification_mask], device="cuda", dtype=torch.long
            ),
            lm_labels=torch.tensor([labels], device="cuda", dtype=torch.long),
            fine_labels=torch.tensor([class_map[snapshot.fine_label]], device="cuda"),
            classification_ce_eligible=torch.tensor(
                [snapshot.classification_supervision_valid], device="cuda"
            ),
            record_weights=torch.tensor([1.0], device="cuda"),
        )
        loss = output["loss"]
        if not bool(torch.isfinite(loss)):
            raise RuntimeError("resume smoke loss is not finite")
        loss.backward()
        optimizer.step()
        scheduler.step()
        optimizer.zero_grad(set_to_none=True)
        return {
            "combined": float(loss.detach()),
            "classification": float(output["classification_loss"].detach()),
            "evidence_lm": float(output["evidence_lm_loss"].detach()),
            "classification_supervised_count": int(output["classification_supervised_count"]),
        }

    model = attach_lora(base_model(), rank=8, alpha=16, dropout=0.05)
    harness = harness_for(model)
    parameter_audit = trainable_parameter_audit(harness)
    optimizer = optimizer_for(harness)
    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda=lambda _step: 1.0)
    losses = [step(harness, optimizer, scheduler, primary), step(harness, optimizer, scheduler, auxiliary)]

    checkpoint = output_root / "dry_run/TEMPORARY_qwen35_resume_smoke"
    if checkpoint.exists():
        raise FileExistsError(f"temporary resume-smoke checkpoint already exists: {checkpoint}")
    (checkpoint / "adapter").mkdir(parents=True)
    harness.language_model.save_pretrained(checkpoint / "adapter", safe_serialization=True)
    save_file(
        {key: value.detach().cpu().contiguous() for key, value in harness.fine_head.state_dict().items()},
        checkpoint / "fine_head.safetensors",
    )
    torch.save(optimizer.state_dict(), checkpoint / "optimizer.pt")
    torch.save(scheduler.state_dict(), checkpoint / "scheduler.pt")
    rng_state = {
        "torch": torch.get_rng_state(),
        "cuda": torch.cuda.get_rng_state_all(),
        "python": random.getstate(),
    }
    torch.save(rng_state, checkpoint / "rng_state.pt")
    metadata = {
        "status": "CHECKPOINTED",
        "optimizer_step": 2,
        "model_revision": "c202236235762e1c871ad0ccb60c8ee5ba337b9a",
        "seed": seed,
        "snapshot_sha256": _sha256(snapshot_path),
        "supervision_contract": "CLASSIFICATION_SUFFICIENCY_DECOUPLED_V1",
    }
    _atomic(checkpoint / "checkpoint_manifest.json", metadata)
    expected_torch = torch.rand(4)
    expected_cuda = torch.rand(4, device="cuda").cpu()
    expected_python = random.random()

    del optimizer, scheduler, harness, model
    gc.collect()
    torch.cuda.empty_cache()

    base = base_model()
    resumed_model = PeftModel.from_pretrained(
        base, checkpoint / "adapter", is_trainable=True
    )
    resumed = harness_for(resumed_model)
    resumed.fine_head.load_state_dict(load_file(checkpoint / "fine_head.safetensors"))
    resumed_optimizer = optimizer_for(resumed)
    resumed_scheduler = torch.optim.lr_scheduler.LambdaLR(
        resumed_optimizer, lr_lambda=lambda _step: 1.0
    )
    resumed_optimizer.load_state_dict(torch.load(checkpoint / "optimizer.pt", map_location="cuda"))
    resumed_scheduler.load_state_dict(torch.load(checkpoint / "scheduler.pt"))
    restored_rng = torch.load(checkpoint / "rng_state.pt", map_location="cpu", weights_only=False)
    torch.set_rng_state(restored_rng["torch"])
    torch.cuda.set_rng_state_all(restored_rng["cuda"])
    random.setstate(restored_rng["python"])
    rng_restored = (
        torch.equal(torch.rand(4), expected_torch)
        and torch.equal(torch.rand(4, device="cuda").cpu(), expected_cuda)
        and random.random() == expected_python
    )
    if not rng_restored:
        raise RuntimeError("RNG state did not restore deterministically")
    if not resumed_optimizer.state or resumed_scheduler.last_epoch != 2:
        raise RuntimeError("optimizer or scheduler state did not restore")
    saved = json.loads((checkpoint / "checkpoint_manifest.json").read_text())
    if saved != metadata:
        raise RuntimeError("resume metadata digest contract changed")

    losses.append(step(resumed, resumed_optimizer, resumed_scheduler, primary))
    if resumed_scheduler.last_epoch != 3:
        raise RuntimeError("resumed scheduler did not advance")
    checkpoint_size = sum(path.stat().st_size for path in checkpoint.rglob("*") if path.is_file())
    shutil.rmtree(checkpoint)
    report = {
        "status": "PASS",
        "purpose": "REAL_9B_SAVE_LOAD_RESUME_SMOKE_NOT_FORMAL_SFT",
        "optimizer_steps_before_reload": 2,
        "optimizer_steps_after_reload": 1,
        "optimizer_restored": True,
        "scheduler_restored": True,
        "rng_restored": rng_restored,
        "lora_restored": True,
        "fine_head_restored": True,
        "resume_metadata_contract": "PASS",
        "checkpoint_size_bytes": checkpoint_size,
        "temporary_checkpoint_deleted": True,
        "losses": losses,
        "parameter_audit": parameter_audit,
        "formal_sft_run": False,
        "rl_run": False,
        "u_final_count": 0,
    }
    _atomic(output_root / "manifests/training_resume_smoke.json", report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
