from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

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

    @model_validator(mode="after")
    def validate_budget_alignment(self) -> "ExperimentVariantConfig":
        if self.max_rounds != self.budget.max_rounds:
            raise ValueError("variant max_rounds must match its budget contract")
        return self


def build_variant_configs(
    common_budget: BudgetLimits,
) -> dict[ExperimentVariant, ExperimentVariantConfig]:
    """Build budget-matched variants from an explicitly supplied experiment budget."""

    terminals = {
        AgentAction.ACCEPT_FINE,
        AgentAction.BACKOFF_COARSE,
        AgentAction.REJECT_UNKNOWN,
        AgentAction.ABSTAIN,
    }
    all_actions = frozenset(AgentAction)
    return {
        ExperimentVariant.BASIC: ExperimentVariantConfig(
            variant=ExperimentVariant.BASIC,
            allowed_information_domains=frozenset(),
            allowed_actions=frozenset(terminals),
            budget=common_budget.model_copy(
                update={"max_rounds": 0, "max_tool_calls": 0, "max_rag_calls": 0}
            ),
            max_rounds=0,
        ),
        ExperimentVariant.FIXED_FULL: ExperimentVariantConfig(
            variant=ExperimentVariant.FIXED_FULL,
            allowed_information_domains=frozenset(GapDomain),
            allowed_actions=all_actions,
            budget=common_budget,
            max_rounds=common_budget.max_rounds,
        ),
        ExperimentVariant.RULE_POLICY: ExperimentVariantConfig(
            variant=ExperimentVariant.RULE_POLICY,
            allowed_information_domains=frozenset(GapDomain),
            allowed_actions=all_actions,
            budget=common_budget,
            max_rounds=common_budget.max_rounds,
        ),
        ExperimentVariant.LLM_SUPERVISOR: ExperimentVariantConfig(
            variant=ExperimentVariant.LLM_SUPERVISOR,
            allowed_information_domains=frozenset(GapDomain),
            allowed_actions=all_actions,
            budget=common_budget,
            max_rounds=common_budget.max_rounds,
        ),
        ExperimentVariant.LEARNABLE_POLICY: ExperimentVariantConfig(
            variant=ExperimentVariant.LEARNABLE_POLICY,
            allowed_information_domains=frozenset(GapDomain),
            allowed_actions=all_actions,
            budget=common_budget,
            max_rounds=common_budget.max_rounds,
            implementation_status="placeholder_only",
        ),
    }
