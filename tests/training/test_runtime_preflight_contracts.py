from __future__ import annotations

import pytest

from flowsec.training.contracts import (
    EvidenceFamilyV2,
    EvidenceStageV2,
    EvidenceStateV2,
    GapDomainV2,
    RecoverabilityV2,
    SFTRecordV2,
)
from flowsec.training.runtime_preflight import (
    gradient_parameter_audit,
    instantiated_parameter_audit,
    optimizer_parameter_audit,
    select_runtime_smoke_records,
)


def _record(
    index: int,
    *,
    label: str,
    primary: bool,
    sufficient: bool,
    gaps: tuple[EvidenceFamilyV2, ...] = (),
    sample_index: int | None = None,
    weight: float = 1.0,
) -> SFTRecordV2:
    if sufficient:
        state = EvidenceStateV2(
            evidence_sufficient=True,
            missing_evidence=(),
            primary_gap=None,
            gap_type=GapDomainV2.NONE,
            recoverability=RecoverabilityV2.ALREADY_SUFFICIENT,
        )
    else:
        state = EvidenceStateV2(
            evidence_sufficient=False,
            missing_evidence=gaps,
            primary_gap=gaps[0],
            gap_type=GapDomainV2.OBSERVATIONAL,
            recoverability=RecoverabilityV2.RECOVERABLE_WITH_AVAILABLE_TOOLS,
        )
    sample = sample_index if sample_index is not None else index
    return SFTRecordV2(
        sample_id="fs1_" + f"{sample:040x}",
        evidence_state_id="state_" + f"{index:024x}",
        fine_label=label,
        class_index=0,
        classification_ce_eligible=primary,
        state_role="primary" if primary else "auxiliary",
        serialized_model_input=f"bounded evidence {index}",
        evidence_state_target=state,
        stage_type=EvidenceStageV2.BASIC if primary else EvidenceStageV2.TEMPORAL,
        available_capability_mask=(),
        prompt_version="fixture",
        serialization_version="fixture",
        teacher_annotation_digest="a" * 64,
        teacher_model="fixture",
        teacher_prompt_digest="b" * 64,
        teacher_request_id=f"request-{index}",
        dataset_digest="c" * 64,
        session_weight=weight,
    )


def test_runtime_smoke_selection_is_deterministic_and_covers_real_contract_states() -> None:
    labels = (
        "Normal",
        "DDoS_HTTP",
        "DDoS_TCP",
        "Password",
        "SQL_injection",
        "Vulnerability_scanner",
    )
    records: list[SFTRecordV2] = []
    for index in range(72):
        sufficient = index % 4 == 0
        gaps = () if sufficient else (
            (EvidenceFamilyV2.TEMPORAL, EvidenceFamilyV2.APPLICATION)
            if index % 5 == 0
            else (EvidenceFamilyV2.TEMPORAL,)
        )
        records.append(
            _record(
                index,
                label=labels[index % len(labels)],
                primary=True,
                sufficient=sufficient,
                gaps=gaps,
            )
        )
    records.extend(
        [
            _record(
                100,
                label="DDoS_HTTP",
                primary=True,
                sufficient=False,
                gaps=(EvidenceFamilyV2.TEMPORAL,),
                sample_index=100,
                weight=0.5,
            ),
            _record(
                101,
                label="DDoS_HTTP",
                primary=False,
                sufficient=True,
                sample_index=100,
                weight=0.5,
            ),
        ]
    )
    first, coverage = select_runtime_smoke_records(records, limit=64, seed=20260809)
    second, _ = select_runtime_smoke_records(records, limit=64, seed=20260809)
    assert [item.evidence_state_id for item in first] == [
        item.evidence_state_id for item in second
    ]
    assert coverage["record_count"] == 64
    assert coverage["fine_classes"] == sorted(labels)
    assert set(coverage["state_role_distribution"]) == {"primary", "auxiliary"}
    assert set(coverage["sufficiency_distribution"]) == {
        "sufficient",
        "insufficient",
    }
    assert coverage["multi_state_session_count"] >= 1


def test_parameter_gradient_and_optimizer_audits_reject_non_lora_base_training() -> None:
    torch = pytest.importorskip("torch")
    nn = torch.nn

    class FineHead(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.projection = nn.Linear(4, 6)

    class TinyHarness(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.base_weight = nn.Parameter(torch.ones(4), requires_grad=False)
            self.lm_head = nn.Linear(4, 8, bias=False)
            self.lm_head.requires_grad_(False)
            self.lora_A = nn.Parameter(torch.ones(4))
            self.fine_head = FineHead()

    harness = TinyHarness()
    optimizer = torch.optim.AdamW(
        (parameter for parameter in harness.parameters() if parameter.requires_grad),
        lr=1e-3,
    )
    parameters = instantiated_parameter_audit(harness)
    assert parameters["fine_head_dimension"] == 6
    assert parameters["trainable_by_group"]["base"] == 0
    assert parameters["trainable_by_group"]["lm_head"] == 0
    assert optimizer_parameter_audit(harness, optimizer)["status"] == "PASS"
    (harness.lora_A.sum() + harness.fine_head.projection.weight.sum()).backward()
    assert gradient_parameter_audit(harness)["status"] == "PASS"

    harness.base_weight.requires_grad_(True)
    with pytest.raises(RuntimeError, match="base or original LM Head"):
        instantiated_parameter_audit(harness)
