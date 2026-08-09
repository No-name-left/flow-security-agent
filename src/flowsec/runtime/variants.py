from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from .contracts import AgentAction, BudgetLimits, FrozenRuntimeModel, GapDomain


class ExperimentVariant(StrEnum):
    BASIC = "basic"
    FIXED_FULL = "fixed_full"
    RULE_POLICY = "rule_policy"
    LLM_SUPERVISOR = "llm_supervisor"
    LEARNABLE_POLICY = "learnable_policy"


class ExperimentVariantConfig(FrozenRuntimeModel):
    variant: ExperimentVariant
    allowed_information_domains: frozenset[GapDomain]
    allowed_actions: frozenset[AgentAction]
    budget: BudgetLimits
    max_rounds: int = Field(ge=0)
    implementation_status: str = "available"


def default_variants() -> dict[ExperimentVariant, ExperimentVariantConfig]:
    terminals = {
        AgentAction.ACCEPT_FINE,
        AgentAction.BACKOFF_COARSE,
        AgentAction.REJECT_UNKNOWN,
        AgentAction.ABSTAIN,
    }
    all_actions = frozenset(AgentAction)
    common_budget = BudgetLimits(max_rounds=3)
    return {
        ExperimentVariant.BASIC: ExperimentVariantConfig(
            variant=ExperimentVariant.BASIC,
            allowed_information_domains=frozenset(),
            allowed_actions=frozenset(terminals),
            budget=BudgetLimits(max_rounds=0, max_tool_calls=0, max_rag_calls=0),
            max_rounds=0,
        ),
        ExperimentVariant.FIXED_FULL: ExperimentVariantConfig(
            variant=ExperimentVariant.FIXED_FULL,
            allowed_information_domains=frozenset(GapDomain),
            allowed_actions=all_actions,
            budget=common_budget,
            max_rounds=3,
        ),
        ExperimentVariant.RULE_POLICY: ExperimentVariantConfig(
            variant=ExperimentVariant.RULE_POLICY,
            allowed_information_domains=frozenset(GapDomain),
            allowed_actions=all_actions,
            budget=common_budget,
            max_rounds=3,
        ),
        ExperimentVariant.LLM_SUPERVISOR: ExperimentVariantConfig(
            variant=ExperimentVariant.LLM_SUPERVISOR,
            allowed_information_domains=frozenset(GapDomain),
            allowed_actions=all_actions,
            budget=common_budget,
            max_rounds=3,
        ),
        ExperimentVariant.LEARNABLE_POLICY: ExperimentVariantConfig(
            variant=ExperimentVariant.LEARNABLE_POLICY,
            allowed_information_domains=frozenset(GapDomain),
            allowed_actions=all_actions,
            budget=common_budget,
            max_rounds=3,
            implementation_status="placeholder_only",
        ),
    }
