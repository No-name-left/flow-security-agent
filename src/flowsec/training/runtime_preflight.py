from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from typing import Any, Iterable, Sequence

from .contracts import SFTRecordV2
from .harness import require_torch


RUNTIME_PREFLIGHT_VERSION = "FORMAL_NEAR_SFT_RUNTIME_PREFLIGHT_V1"


def _stable_order(record: SFTRecordV2, seed: int) -> str:
    return hashlib.sha256(
        f"{seed}:{record.evidence_state_id}".encode("utf-8")
    ).hexdigest()


def select_runtime_smoke_records(
    records: Sequence[SFTRecordV2],
    *,
    limit: int,
    seed: int,
) -> tuple[list[SFTRecordV2], dict[str, Any]]:
    """Select a deterministic, coverage-constrained subset of the formal corpus."""

    if not 32 <= limit <= 128:
        raise ValueError("runtime smoke subset must contain 32..128 records")
    if len(records) < limit:
        raise ValueError("formal corpus is smaller than the smoke subset")
    if len({item.evidence_state_id for item in records}) != len(records):
        raise ValueError("formal corpus contains duplicate Evidence state IDs")

    ordered = sorted(records, key=lambda item: _stable_order(item, seed))
    by_session: dict[str, list[SFTRecordV2]] = defaultdict(list)
    for item in records:
        by_session[item.sample_id].append(item)

    selected: list[SFTRecordV2] = []
    selected_ids: set[str] = set()

    def add(item: SFTRecordV2) -> None:
        if len(selected) < limit and item.evidence_state_id not in selected_ids:
            selected.append(item)
            selected_ids.add(item.evidence_state_id)

    # Put a real insufficient Basic primary first so the first backward proves
    # classification/sufficiency decoupling and both losses at once.
    witness = next(
        item
        for item in ordered
        if item.state_role == "primary"
        and not item.evidence_state_target.evidence_sufficient
        and len(item.evidence_state_target.missing_evidence) >= 2
    )
    add(witness)

    # Preserve all states of one maximum-depth trajectory for the runtime
    # session-weight check.
    paired_session = min(
        (values for values in by_session.values() if len(values) >= 2),
        key=lambda values: _stable_order(values[0], seed),
    )
    for item in sorted(paired_session, key=lambda value: value.stage_type.value):
        add(item)

    classes = sorted({item.fine_label for item in records})
    for fine_label in classes:
        class_records = [item for item in ordered if item.fine_label == fine_label]
        for predicate in (
            lambda item: item.state_role == "primary"
            and item.evidence_state_target.evidence_sufficient,
            lambda item: item.state_role == "primary"
            and not item.evidence_state_target.evidence_sufficient,
            lambda item: item.state_role == "auxiliary",
        ):
            match = next((item for item in class_records if predicate(item)), None)
            if match is not None:
                add(match)

    for cardinality in (1, 2):
        match = next(
            (
                item
                for item in ordered
                if len(item.evidence_state_target.missing_evidence)
                == (cardinality if cardinality == 1 else 2)
            ),
            None,
        )
        if match is not None:
            add(match)
    for item in ordered:
        add(item)
        if len(selected) == limit:
            break

    coverage = {
        "record_count": len(selected),
        "unique_sessions": len({item.sample_id for item in selected}),
        "fine_classes": sorted({item.fine_label for item in selected}),
        "class_distribution": dict(sorted(Counter(item.fine_label for item in selected).items())),
        "state_role_distribution": dict(
            sorted(Counter(item.state_role for item in selected).items())
        ),
        "sufficiency_distribution": dict(
            sorted(
                Counter(
                    "sufficient"
                    if item.evidence_state_target.evidence_sufficient
                    else "insufficient"
                    for item in selected
                ).items()
            )
        ),
        "gap_cardinality_distribution": dict(
            sorted(
                Counter(
                    str(len(item.evidence_state_target.missing_evidence))
                    for item in selected
                ).items()
            )
        ),
        "stage_distribution": dict(
            sorted(Counter(item.stage_type.value for item in selected).items())
        ),
        "multi_state_session_count": sum(
            count >= 2 for count in Counter(item.sample_id for item in selected).values()
        ),
        "classification_sufficiency_decoupling_witness": witness.evidence_state_id,
    }
    required_roles = {"primary", "auxiliary"}
    required_sufficiency = {"sufficient", "insufficient"}
    if set(coverage["state_role_distribution"]) != required_roles:
        raise ValueError("smoke subset lacks primary or auxiliary states")
    if set(coverage["sufficiency_distribution"]) != required_sufficiency:
        raise ValueError("smoke subset lacks sufficient or insufficient states")
    if "1" not in coverage["gap_cardinality_distribution"] or not any(
        int(value) >= 2 for value in coverage["gap_cardinality_distribution"]
    ):
        raise ValueError("smoke subset lacks single- or multi-gap states")
    if coverage["multi_state_session_count"] < 1:
        raise ValueError("smoke subset lacks a session-weight trajectory")
    return selected, coverage


def parameter_group(name: str) -> str:
    if name.startswith("fine_head."):
        return "fine_head"
    if "lora_" in name:
        return "lora"
    if name.startswith("lm_head.") or ".lm_head." in name or name.endswith(
        ".lm_head.weight"
    ) or name.endswith(".lm_head.bias"):
        return "lm_head"
    return "base"


def instantiated_parameter_audit(module: Any) -> dict[str, Any]:
    require_torch()
    total = trainable = 0
    totals: Counter[str] = Counter()
    trainable_groups: Counter[str] = Counter()
    trainable_names: list[str] = []
    for name, parameter in module.named_parameters():
        count = parameter.numel()
        group = parameter_group(name)
        total += count
        totals[group] += count
        if parameter.requires_grad:
            trainable += count
            trainable_groups[group] += count
            trainable_names.append(name)
    if trainable_groups["lora"] <= 0 or trainable_groups["fine_head"] <= 0:
        raise RuntimeError("LoRA and Fine Head must both be trainable")
    if trainable_groups["base"] or trainable_groups["lm_head"]:
        raise RuntimeError("base or original LM Head is unexpectedly trainable")
    fine_head = getattr(module, "fine_head", None)
    dimension = int(fine_head.projection.out_features)
    return {
        "total_parameters": total,
        "trainable_parameters": trainable,
        "trainable_percent": 100.0 * trainable / total,
        "total_by_group": dict(sorted(totals.items())),
        "trainable_by_group": {
            name: int(trainable_groups[name])
            for name in ("lora", "fine_head", "base", "lm_head")
        },
        "fine_head_dimension": dimension,
        "trainable_name_count": len(trainable_names),
        "trainable_name_sample": sorted(trainable_names)[:24],
    }


def optimizer_parameter_audit(module: Any, optimizer: Any) -> dict[str, Any]:
    require_torch()
    names_by_id = {id(parameter): name for name, parameter in module.named_parameters()}
    expected = {
        id(parameter)
        for parameter in module.parameters()
        if parameter.requires_grad
    }
    observed = {
        id(parameter)
        for group in optimizer.param_groups
        for parameter in group["params"]
    }
    if observed != expected:
        raise RuntimeError("optimizer parameters disagree with the trainable boundary")
    groups = Counter(parameter_group(names_by_id[value]) for value in observed)
    if set(groups) != {"lora", "fine_head"}:
        raise RuntimeError(f"optimizer contains unexpected parameter groups: {groups}")
    return {
        "status": "PASS",
        "parameter_tensor_count": len(observed),
        "tensor_distribution": dict(sorted(groups.items())),
    }


def gradient_parameter_audit(module: Any) -> dict[str, Any]:
    require_torch()
    non_null = Counter()
    nonzero = Counter()
    frozen_with_grad: list[str] = []
    for name, parameter in module.named_parameters():
        group = parameter_group(name)
        if not parameter.requires_grad:
            if parameter.grad is not None:
                frozen_with_grad.append(name)
            continue
        if parameter.grad is not None:
            non_null[group] += 1
            if bool(parameter.grad.detach().ne(0).any()):
                nonzero[group] += 1
    if frozen_with_grad:
        raise RuntimeError(f"frozen parameter received a gradient: {frozen_with_grad[0]}")
    if nonzero["lora"] <= 0 or nonzero["fine_head"] <= 0:
        raise RuntimeError("LoRA or Fine Head lacks a nonzero gradient")
    return {
        "status": "PASS",
        "non_null_gradient_tensors": dict(sorted(non_null.items())),
        "nonzero_gradient_tensors": dict(sorted(nonzero.items())),
        "frozen_gradient_tensor_count": 0,
    }


def snapshot_named_parameters(
    module: Any, *, groups: Iterable[str]
) -> dict[str, Any]:
    require_torch()
    accepted = set(groups)
    return {
        name: parameter.detach().cpu().clone()
        for name, parameter in module.named_parameters()
        if parameter_group(name) in accepted
    }


def exact_parameter_snapshot_match(expected: dict[str, Any], module: Any) -> bool:
    require_torch()
    import torch

    current = dict(module.named_parameters())
    return set(expected).issubset(current) and all(
        torch.equal(value, current[name].detach().cpu())
        for name, value in expected.items()
    )
