from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


try:  # Keep the base/data CI install importable without the training stack.
    import torch
    import torch.nn.functional as F
    from torch import Tensor, nn
except ImportError:  # pragma: no cover - exercised by minimal CI environments
    torch = None
    F = None
    Tensor = Any
    nn = None


POOL_LAST_PROMPT_TOKEN = "LAST_MODEL_VISIBLE_PROMPT_POSITION_V1"
POOL_EXPLICIT_PROMPT_END = "EXPLICIT_CLASSIFICATION_PROMPT_END_V1"
POOL_MEAN = "ATTENTION_MASKED_MEAN_V1"

LORA_TARGET_MODULES_V1 = (
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "in_proj_qkv",
    "in_proj_z",
    "in_proj_a",
    "in_proj_b",
    "out_proj",
    "gate_proj",
    "up_proj",
    "down_proj",
)

_TARGET_FAMILIES = {
    "gated_attention": frozenset({"q_proj", "k_proj", "v_proj", "o_proj"}),
    "gated_deltanet": frozenset(
        {"in_proj_qkv", "in_proj_z", "in_proj_a", "in_proj_b", "out_proj"}
    ),
    "ffn": frozenset({"gate_proj", "up_proj", "down_proj"}),
}


def require_torch() -> None:
    if torch is None or nn is None or F is None:
        raise RuntimeError("TrafficExpertTrainingHarness requires the optional PyTorch stack")


def load_near_class_map(preset_manifest: Path) -> tuple[tuple[str, ...], dict[str, int]]:
    data = json.loads(Path(preset_manifest).read_text(encoding="utf-8"))
    labels = data.get("Near", {}).get("K_known")
    if not isinstance(labels, list) or not labels or any(not isinstance(item, str) for item in labels):
        raise ValueError("Near K_known is unavailable in the frozen preset manifest")
    if len(labels) != len(set(labels)):
        raise ValueError("Near K_known labels are not unique")
    ordered = tuple(labels)
    return ordered, {label: index for index, label in enumerate(ordered)}


def inventory_lora_targets(
    named_modules: Iterable[tuple[str, Any]],
    targets: tuple[str, ...] = LORA_TARGET_MODULES_V1,
) -> dict[str, Any]:
    matched: dict[str, list[str]] = {name: [] for name in targets}
    for module_name, _module in named_modules:
        suffix = module_name.rsplit(".", 1)[-1]
        if suffix in matched:
            matched[suffix].append(module_name)
    family_counts = {
        family: sum(len(matched[name]) for name in suffixes)
        for family, suffixes in _TARGET_FAMILIES.items()
    }
    missing_families = sorted(name for name, count in family_counts.items() if count == 0)
    if missing_families:
        raise ValueError(f"LoRA inventory missed required module families: {missing_families}")
    return {
        "target_modules": list(targets),
        "target_counts": {name: len(values) for name, values in matched.items()},
        "family_counts": family_counts,
        "matched_module_count": sum(len(values) for values in matched.values()),
        "matched_modules": {name: sorted(values) for name, values in matched.items()},
    }


def pool_hidden_state(
    hidden_state: Tensor,
    attention_mask: Tensor,
    *,
    method: str,
) -> Tensor:
    require_torch()
    if hidden_state.ndim != 3 or attention_mask.ndim != 2:
        raise ValueError("pooling expects [batch, sequence, hidden] and [batch, sequence]")
    if hidden_state.shape[:2] != attention_mask.shape:
        raise ValueError("hidden state and attention mask shapes disagree")
    mask = attention_mask.to(dtype=torch.bool)
    if not bool(mask.any(dim=1).all()):
        raise ValueError("every pooling row requires at least one model-visible token")
    if method in {POOL_LAST_PROMPT_TOKEN, POOL_EXPLICIT_PROMPT_END}:
        positions = torch.arange(mask.shape[1], device=mask.device).expand_as(mask)
        indices = positions.masked_fill(~mask, -1).max(dim=1).values
        return hidden_state[torch.arange(hidden_state.shape[0], device=hidden_state.device), indices]
    if method == POOL_MEAN:
        weights = mask.unsqueeze(-1).to(dtype=hidden_state.dtype)
        return (hidden_state * weights).sum(dim=1) / weights.sum(dim=1).clamp_min(1.0)
    raise ValueError(f"unsupported classification pooling method: {method}")


def per_record_causal_lm_loss(logits: Tensor, labels: Tensor) -> tuple[Tensor, Tensor]:
    """Return target-token mean loss per record and its valid-target mask."""

    require_torch()
    if logits.ndim != 3 or labels.ndim != 2 or logits.shape[:2] != labels.shape:
        raise ValueError("causal LM loss expects [batch, sequence, vocab] logits and labels")
    shifted_logits = logits[:, :-1, :].contiguous()
    shifted_labels = labels[:, 1:].contiguous()
    token_losses = F.cross_entropy(
        shifted_logits.view(-1, shifted_logits.shape[-1]),
        shifted_labels.view(-1),
        reduction="none",
        ignore_index=-100,
    ).view(shifted_labels.shape)
    valid = shifted_labels.ne(-100)
    counts = valid.sum(dim=1)
    per_record = (token_losses * valid).sum(dim=1) / counts.clamp_min(1)
    return per_record, counts.gt(0)


if nn is not None:

    class FineClassificationHead(nn.Module):
        def __init__(self, hidden_size: int, num_classes: int):
            super().__init__()
            if hidden_size <= 0 or num_classes <= 1:
                raise ValueError("Fine Head requires positive hidden size and at least two classes")
            self.projection = nn.Linear(hidden_size, num_classes)

        def forward(self, representation: Tensor) -> Tensor:
            return self.projection(representation)


    class TrafficExpertTrainingHarness(nn.Module):
        """Transformers-compatible Qwen LM + one Fine Head multi-task harness."""

        def __init__(
            self,
            language_model: nn.Module,
            *,
            hidden_size: int,
            num_classes: int,
            pooling_method: str,
            classification_loss_weight: float = 1.0,
            evidence_loss_weight: float = 0.35,
        ):
            super().__init__()
            if classification_loss_weight <= 0 or evidence_loss_weight < 0:
                raise ValueError("invalid multi-task loss weights")
            self.language_model = language_model
            self.fine_head = FineClassificationHead(hidden_size, num_classes)
            self.pooling_method = pooling_method
            self.classification_loss_weight = float(classification_loss_weight)
            self.evidence_loss_weight = float(evidence_loss_weight)

        def forward(
            self,
            *,
            input_ids: Tensor,
            attention_mask: Tensor,
            classification_attention_mask: Tensor | None = None,
            lm_labels: Tensor | None = None,
            fine_labels: Tensor | None = None,
            classification_ce_eligible: Tensor | None = None,
            record_weights: Tensor | None = None,
        ) -> dict[str, Tensor | Any]:
            outputs = self.language_model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                labels=lm_labels,
                output_hidden_states=True,
                return_dict=True,
                use_cache=False,
            )
            hidden_states = getattr(outputs, "hidden_states", None)
            if not hidden_states:
                raise RuntimeError("language model did not expose hidden states")
            if classification_attention_mask is None:
                if lm_labels is not None:
                    raise ValueError(
                        "LM-supervised training requires an explicit prompt-only classification mask"
                    )
                classification_attention_mask = attention_mask
            representation = pool_hidden_state(
                hidden_states[-1],
                classification_attention_mask,
                method=self.pooling_method,
            )
            fine_logits = self.fine_head(representation)

            classification_loss = fine_logits.sum() * 0.0
            supervised_count = torch.zeros((), device=fine_logits.device, dtype=torch.long)
            if fine_labels is not None:
                if classification_ce_eligible is None:
                    raise ValueError("classification labels require an explicit supervision mask")
                mask = classification_ce_eligible.to(
                    device=fine_logits.device, dtype=torch.bool
                )
                if mask.ndim != 1 or mask.shape[0] != fine_logits.shape[0]:
                    raise ValueError("classification supervision mask shape is invalid")
                per_record = F.cross_entropy(fine_logits, fine_labels, reduction="none")
                supervised_count = mask.sum()
                if int(supervised_count.item()) > 0:
                    classification_loss = per_record[mask].mean()

            lm_loss = fine_logits.sum() * 0.0
            if lm_labels is not None:
                per_record_lm, lm_valid = per_record_causal_lm_loss(outputs.logits, lm_labels)
                if record_weights is None:
                    raise ValueError("LM-supervised training requires explicit session record weights")
                weights = record_weights.to(device=fine_logits.device, dtype=per_record_lm.dtype)
                if weights.ndim != 1 or weights.shape[0] != fine_logits.shape[0]:
                    raise ValueError("record weight shape is invalid")
                if not bool(torch.isfinite(weights).all()) or bool((weights <= 0).any()):
                    raise ValueError("record weights must be finite and positive")
                if bool(lm_valid.any()):
                    lm_loss = (per_record_lm[lm_valid] * weights[lm_valid]).sum() / lm_valid.sum()
            combined_loss = (
                self.classification_loss_weight * classification_loss
                + self.evidence_loss_weight * lm_loss
            )
            return {
                "loss": combined_loss,
                "classification_loss": classification_loss,
                "evidence_lm_loss": lm_loss,
                "fine_logits": fine_logits,
                "lm_logits": outputs.logits,
                "session_representation": representation,
                "classification_supervised_count": supervised_count,
                "language_model_output": outputs,
            }

else:  # pragma: no cover - used only to produce an actionable optional-dependency error

    class FineClassificationHead:  # type: ignore[no-redef]
        def __init__(self, *_args: Any, **_kwargs: Any):
            require_torch()


    class TrafficExpertTrainingHarness:  # type: ignore[no-redef]
        def __init__(self, *_args: Any, **_kwargs: Any):
            require_torch()


def attach_lora(
    model: Any,
    *,
    rank: int,
    alpha: int,
    dropout: float,
    target_modules: tuple[str, ...] = LORA_TARGET_MODULES_V1,
) -> Any:
    require_torch()
    try:
        from peft import LoraConfig, TaskType, get_peft_model
    except ImportError as exc:  # pragma: no cover - training environment preflight
        raise RuntimeError("PEFT is required to attach Near LoRA adapters") from exc
    inventory_lora_targets(model.named_modules(), target_modules)
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    config = LoraConfig(
        r=rank,
        lora_alpha=alpha,
        lora_dropout=dropout,
        target_modules=list(target_modules),
        task_type=TaskType.CAUSAL_LM,
        bias="none",
    )
    return get_peft_model(model, config)


def trainable_parameter_audit(module: Any) -> dict[str, Any]:
    require_torch()
    total = 0
    trainable = 0
    groups: dict[str, int] = {"lora": 0, "fine_head": 0, "other": 0}
    names: list[str] = []
    for name, parameter in module.named_parameters():
        count = parameter.numel()
        total += count
        if not parameter.requires_grad:
            continue
        trainable += count
        names.append(name)
        if "lora_" in name:
            groups["lora"] += count
        elif name.startswith("fine_head."):
            groups["fine_head"] += count
        else:
            groups["other"] += count
    if groups["lora"] == 0 or groups["fine_head"] == 0 or groups["other"] != 0:
        raise ValueError(f"unexpected trainable parameter boundary: {groups}")
    return {
        "total_parameters": total,
        "trainable_parameters": trainable,
        "trainable_ratio": trainable / total,
        "groups": groups,
        "trainable_names": sorted(names),
    }


def sampled_frozen_parameter_digest(module: Any) -> str:
    """Audit every frozen tensor via shape/dtype and deterministic sampled values."""

    require_torch()
    digest = hashlib.sha256()
    frozen_count = 0
    with torch.no_grad():
        for name, parameter in sorted(module.named_parameters()):
            if parameter.requires_grad:
                continue
            frozen_count += 1
            flat = parameter.detach().reshape(-1)
            indices = sorted({0, max(0, flat.numel() // 2), max(0, flat.numel() - 1)})
            values = flat[indices].float().cpu().numpy().tobytes() if flat.numel() else b""
            digest.update(name.encode("utf-8"))
            digest.update(str(tuple(parameter.shape)).encode("ascii"))
            digest.update(str(parameter.dtype).encode("ascii"))
            digest.update(values)
    if frozen_count == 0:
        raise ValueError("frozen-parameter audit found no frozen tensors")
    return digest.hexdigest()


def changed_trainable_parameters(
    before: dict[str, Tensor],
    module: Any,
) -> dict[str, bool]:
    require_torch()
    result: dict[str, bool] = {}
    current = dict(module.named_parameters())
    for name, value in before.items():
        result[name] = not torch.equal(value, current[name].detach().cpu())
    return result


def snapshot_trainable_parameters(module: Any) -> dict[str, Tensor]:
    require_torch()
    return {
        name: parameter.detach().cpu().clone()
        for name, parameter in module.named_parameters()
        if parameter.requires_grad
    }
