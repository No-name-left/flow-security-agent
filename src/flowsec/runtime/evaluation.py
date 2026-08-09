from __future__ import annotations

from collections import Counter
from typing import Any

from .contracts import FinalDecisionType, RuntimeResult, TraceEventType


def summarize_runtime_results(results: list[RuntimeResult]) -> dict[str, Any]:
    decisions = Counter(item.final_decision.decision_type.value for item in results)
    actions = Counter(
        event.summary.get("action")
        for item in results
        for event in item.trace
        if event.summary.get("action")
    )
    failures = Counter(code.value for item in results for code in item.failures)
    budgets = [item.budget for item in results]
    return {
        "sample_count": len(results),
        "final_decision_distribution": dict(decisions),
        "fine_count": decisions[FinalDecisionType.FINE.value],
        "coarse_count": decisions[FinalDecisionType.COARSE.value],
        "unknown_reject_count": decisions[FinalDecisionType.UNKNOWN.value],
        "abstain_count": decisions[FinalDecisionType.ABSTAIN.value],
        "rounds": sum(item.rounds for item in budgets),
        "traffic_expert_calls": sum(item.traffic_expert_calls for item in budgets),
        "supervisor_calls": sum(item.supervisor_calls for item in budgets),
        "tool_calls": sum(item.tool_calls for item in budgets),
        "rag_calls": sum(item.rag_calls for item in budgets),
        "tool_failures": failures.get("tool_failure", 0),
        "budget_exhaustion": failures.get("budget_exhausted", 0),
        "action_histogram": dict(actions),
        "abstract_tokens": sum(item.abstract_tokens for item in budgets),
        "abstract_cost": sum(item.abstract_cost for item in budgets),
        "abstract_latency": sum(item.abstract_latency for item in budgets),
        "trace_event_count": sum(
            event.event_type is not TraceEventType.FINAL
            for item in results
            for event in item.trace
        ),
    }
