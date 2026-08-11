#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from flowsec.training.contracts import (
    EvidenceGapType,
    EvidenceSnapshot,
    EvidenceStateV1,
    MissingEvidenceV1,
    SupportingEvidenceV1,
    canonical_json,
)
from flowsec.training.harness import (
    POOL_MEAN,
    TrafficExpertTrainingHarness,
    attach_lora,
    changed_trainable_parameters,
    load_near_class_map,
    sampled_frozen_parameter_digest,
    snapshot_trainable_parameters,
    trainable_parameter_audit,
)
from flowsec.training.serialization import COMPACT_SERIALIZATION_CANDIDATE, render_training_input
from flowsec.training.prompts import traffic_expert_prompt_v1


def _fixture_target(snapshot: EvidenceSnapshot) -> EvidenceStateV1:
    observation = next(item for item in snapshot.evidence if item.domain.value == "OBSERVATION")
    if snapshot.classification_supervision_valid:
        return EvidenceStateV1(
            behavior_summary="The bounded current-stage network observations support a provisional traffic interpretation.",
            supporting_evidence=(
                SupportingEvidenceV1(
                    evidence_id=observation.evidence_id,
                    claim="The cited current-stage observation is available to the model.",
                ),
            ),
            evidence_sufficient=True,
            gap_type=EvidenceGapType.NONE,
        )
    return EvidenceStateV1(
        behavior_summary="The controlled lower-evidence state is not sufficient for a fine traffic interpretation.",
        supporting_evidence=(),
        missing_evidence=(
            MissingEvidenceV1(
                type=EvidenceGapType.AMBIGUOUS,
                description="Ordered packet observations are intentionally unavailable in this dry-run state.",
            ),
        ),
        evidence_sufficient=False,
        gap_type=EvidenceGapType.AMBIGUOUS,
    )


def _encode_record(tokenizer, snapshot: EvidenceSnapshot, *, max_length: int):
    prompt = render_training_input(
        traffic_expert_prompt_v1(),
        snapshot.evidence,
        serialization_version=COMPACT_SERIALIZATION_CANDIDATE,
    )
    target = canonical_json(_fixture_target(snapshot).model_dump(mode="json"))
    prompt_ids = tokenizer(prompt, add_special_tokens=True)["input_ids"]
    target_ids = tokenizer(target + tokenizer.eos_token, add_special_tokens=False)["input_ids"]
    if len(prompt_ids) + len(target_ids) > max_length:
        raise ValueError("dry-run record exceeds the frozen sequence bound; do not truncate evidence")
    input_ids = prompt_ids + target_ids
    labels = [-100] * len(prompt_ids) + target_ids
    classification_mask = [1] * len(prompt_ids) + [0] * len(target_ids)
    return input_ids, labels, classification_mask


def _load_dry_run_snapshots(path: Path) -> list[EvidenceSnapshot]:
    snapshots = [
        EvidenceSnapshot.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not any(item.classification_supervision_valid for item in snapshots) or not any(
        not item.classification_supervision_valid for item in snapshots
    ):
        raise ValueError("dry-run requires supervised and masked legal snapshots")
    return snapshots


def main() -> int:
    import torch
    from safetensors.torch import load_file, save_file
    from transformers import AutoModelForImageTextToText, AutoTokenizer

    artifact_root = Path(os.environ["ARTIFACT_ROOT"])
    output_root = artifact_root / "near_pretraining_v1"
    production_root = artifact_root / "edge_split_revision_v2"
    model_root = Path(os.environ["QWEN_MODEL_PATH"])
    snapshot_path = output_root / "sft_corpus/evidence_snapshot_universe_v1.jsonl"
    universe = _load_dry_run_snapshots(snapshot_path)
    rendered_lengths = {
        item.evidence_state_id: len(
            render_training_input(
                traffic_expert_prompt_v1(),
                item.evidence,
                serialization_version=COMPACT_SERIALIZATION_CANDIDATE,
            )
        )
        for item in universe
    }
    snapshots = [
        max(
            (item for item in universe if item.classification_supervision_valid),
            key=lambda item: rendered_lengths[item.evidence_state_id],
        ),
        max(
            (item for item in universe if not item.classification_supervision_valid),
            key=lambda item: rendered_lengths[item.evidence_state_id],
        ),
    ]
    classes, class_map = load_near_class_map(
        production_root / "manifests/edge_known_unknown_presets.json"
    )
    tokenizer = AutoTokenizer.from_pretrained(model_root, local_files_only=True)
    torch.manual_seed(20260809)
    torch.cuda.reset_peak_memory_stats()
    model = AutoModelForImageTextToText.from_pretrained(
        model_root,
        dtype=torch.bfloat16,
        device_map={"": 0},
        local_files_only=True,
    )
    model = attach_lora(model, rank=8, alpha=16, dropout=0.05)
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
    parameter_audit = trainable_parameter_audit(harness)
    frozen_before = sampled_frozen_parameter_digest(harness)
    trainable_before = snapshot_trainable_parameters(harness)
    optimizer = torch.optim.AdamW(
        (parameter for parameter in harness.parameters() if parameter.requires_grad),
        lr=2e-4,
        weight_decay=0.01,
    )

    losses = []
    sequence_lengths = []
    token_count = 0
    started = time.perf_counter()
    for snapshot in snapshots:
        input_ids, labels, classification_mask = _encode_record(
            tokenizer, snapshot, max_length=3072
        )
        sequence_lengths.append(len(input_ids))
        token_count += len(input_ids)
        inputs = torch.tensor([input_ids], device="cuda", dtype=torch.long)
        attention = torch.ones_like(inputs)
        output = harness(
            input_ids=inputs,
            attention_mask=attention,
            classification_attention_mask=torch.tensor(
                [classification_mask], device="cuda", dtype=torch.long
            ),
            lm_labels=torch.tensor([labels], device="cuda", dtype=torch.long),
            fine_labels=torch.tensor([class_map[snapshot.fine_label]], device="cuda"),
            classification_supervision_valid=torch.tensor(
                [snapshot.classification_supervision_valid], device="cuda"
            ),
        )
        loss = output["loss"]
        if not bool(torch.isfinite(loss)):
            raise RuntimeError("dry-run loss is not finite")
        loss.backward()
        optimizer.step()
        optimizer.zero_grad(set_to_none=True)
        losses.append(
            {
                "combined": float(loss.detach()),
                "classification": float(output["classification_loss"].detach()),
                "evidence_lm": float(output["evidence_lm_loss"].detach()),
                "classification_supervised_count": int(
                    output["classification_supervised_count"].detach()
                ),
            }
        )
    elapsed = time.perf_counter() - started
    frozen_after = sampled_frozen_parameter_digest(harness)
    changes = changed_trainable_parameters(trainable_before, harness)
    lora_changed = any(changed for name, changed in changes.items() if "lora_" in name)
    head_changed = any(changed for name, changed in changes.items() if name.startswith("fine_head."))
    if frozen_before != frozen_after or not lora_changed or not head_changed:
        raise RuntimeError("frozen/trainable parameter boundary failed")

    checkpoint_root = output_root / "dry_run/TEMPORARY_qwen35_9b"
    adapter_root = checkpoint_root / "adapter"
    checkpoint_root.mkdir(parents=True, exist_ok=True)
    harness.language_model.save_pretrained(adapter_root, safe_serialization=True)
    head_path = checkpoint_root / "fine_head.safetensors"
    save_file(
        {key: value.detach().cpu().contiguous() for key, value in harness.fine_head.state_dict().items()},
        head_path,
    )
    loaded_head = load_file(head_path)
    if set(loaded_head) != set(harness.fine_head.state_dict()):
        raise RuntimeError("Fine Head checkpoint reload failed")
    adapter_files = sorted(path for path in adapter_root.rglob("*") if path.is_file())
    if not any(path.name == "adapter_config.json" for path in adapter_files):
        raise RuntimeError("PEFT adapter checkpoint reload contract is incomplete")
    checkpoint_size = sum(path.stat().st_size for path in checkpoint_root.rglob("*") if path.is_file())
    shutil.rmtree(checkpoint_root)

    report = {
        "status": "PASS",
        "purpose": "REAL_9B_TRAINING_SIDE_DRY_RUN_NOT_FORMAL_SFT",
        "target_source": "DETERMINISTIC_SCHEMA_FIXTURE_NOT_FORMAL_TEACHER",
        "optimizer_steps": len(snapshots),
        "formal_sft_run": False,
        "rl_run": False,
        "scope": "Near K_known TRAIN only",
        "u_final_count": 0,
        "sequence_lengths": sequence_lengths,
        "micro_batch_size": 1,
        "dtype": "bfloat16",
        "losses": losses,
        "elapsed_seconds": elapsed,
        "tokens_per_second": token_count / elapsed,
        "peak_vram_bytes": torch.cuda.max_memory_allocated(),
        "checkpoint_size_bytes": checkpoint_size,
        "checkpoint_reload_contract": "PASS",
        "temporary_checkpoint_deleted": True,
        "frozen_parameter_digest_unchanged": True,
        "lora_changed": lora_changed,
        "fine_head_changed": head_changed,
        "parameter_audit": parameter_audit,
    }
    report_path = output_root / "manifests/training_dry_run.json"
    temporary = report_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(report_path)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
