from __future__ import annotations

import pytest
from pydantic import ValidationError

from flowsec.runtime.contracts import (
    AgentAction,
    BudgetLimits,
    BudgetState,
    CallMetrics,
    EvidenceSufficiency,
    GapDomain,
    GapType,
    MissingEvidence,
    RuntimeInput,
    ToolRequest,
)
from flowsec.runtime.variants import ExperimentVariant, default_variants

from ._helpers import capabilities, evidence


def test_gap_contract_distinguishes_observational_and_knowledge() -> None:
    observational = MissingEvidence(
        description="need packets",
        gap_type=GapType.PACKET,
        domain=GapDomain.OBSERVATIONAL,
    )
    knowledge = MissingEvidence(
        description="need semantics",
        gap_type=GapType.KNOWLEDGE,
        domain=GapDomain.KNOWLEDGE,
    )
    assert observational.domain is GapDomain.OBSERVATIONAL
    assert knowledge.domain is GapDomain.KNOWLEDGE


def test_gap_contract_rejects_wrong_domain() -> None:
    with pytest.raises(ValidationError):
        MissingEvidence(
            description="bad",
            gap_type=GapType.PACKET,
            domain=GapDomain.KNOWLEDGE,
        )


def test_tool_request_signature_is_deterministic_and_parameter_sensitive() -> None:
    first = ToolRequest(action=AgentAction.EXPAND_TEMPORAL_CONTEXT, parameters={"window": 60})
    reordered = ToolRequest(action=AgentAction.EXPAND_TEMPORAL_CONTEXT, parameters={"window": 60})
    different = ToolRequest(action=AgentAction.EXPAND_TEMPORAL_CONTEXT, parameters={"window": 300})
    assert first.signature == reordered.signature
    assert first.signature != different.signature


def test_budget_tracks_abstract_resources_without_prices() -> None:
    state = BudgetState(limits=BudgetLimits(max_tool_calls=1, max_abstract_tokens=5))
    state.consume(kind="tool", metrics=CallMetrics(abstract_tokens=5, abstract_cost=0.25))
    assert state.tool_calls == 1
    assert state.abstract_tokens == 5
    assert state.abstract_cost == 0.25
    assert not state.can_consume(kind="tool")


def test_runtime_input_forbids_ground_truth_field() -> None:
    with pytest.raises(ValidationError):
        RuntimeInput.model_validate(
            {
                "sample_id": "sample",
                "initial_evidence": [evidence()],
                "capabilities": capabilities(),
                "ground_truth": "must-not-enter-state",
            }
        )


def test_variants_express_domains_tools_budgets_and_placeholder() -> None:
    variants = default_variants()
    assert variants[ExperimentVariant.BASIC].max_rounds == 0
    assert AgentAction.EXPAND_PACKETS not in variants[ExperimentVariant.BASIC].allowed_actions
    assert variants[ExperimentVariant.RULE_POLICY].allowed_information_domains
    assert variants[ExperimentVariant.LEARNABLE_POLICY].implementation_status == "placeholder_only"
