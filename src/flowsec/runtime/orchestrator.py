from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .backends import SupervisorBackend, TrafficExpertBackend, UnknownScorer
from .contracts import (
    ACTION_CAPABILITY,
    EVIDENCE_ACTIONS,
    TERMINAL_ACTIONS,
    AgentAction,
    BudgetLimits,
    BudgetState,
    Capability,
    CapabilityStatus,
    EvidenceState,
    FailureCode,
    FinalDecision,
    FinalDecisionType,
    GapDomain,
    GapType,
    RuntimeInput,
    RuntimePhase,
    RuntimeResult,
    SupervisorDecision,
    ToolResult,
    ToolStatus,
    TraceEvent,
    TraceEventType,
    TrafficExpertResult,
    UnknownDecision,
    UnknownState,
    ExperienceRecord,
)
from .memory import ExperienceMemory
from .tools import EvidenceTool


ACTION_GAP: dict[AgentAction, GapType] = {
    AgentAction.EXPAND_PACKETS: GapType.PACKET,
    AgentAction.EXPAND_TEMPORAL_CONTEXT: GapType.TEMPORAL,
    AgentAction.EXPAND_GRAPH_CONTEXT: GapType.GRAPH,
    AgentAction.REQUEST_APPLICATION_EVIDENCE: GapType.APPLICATION,
    AgentAction.RETRIEVE_KNOWLEDGE: GapType.KNOWLEDGE,
}


class RuntimeOrchestrator:
    """Deterministic executor around provider-neutral expert and policy backends."""

    def __init__(
        self,
        *,
        traffic_expert: TrafficExpertBackend,
        unknown_scorer: UnknownScorer,
        supervisor: SupervisorBackend,
        tools: Iterable[EvidenceTool] = (),
        budget_limits: BudgetLimits | None = None,
        allowed_actions: frozenset[AgentAction] | None = None,
        allowed_information_domains: frozenset[GapDomain] | None = None,
        experience_memory: ExperienceMemory | None = None,
        memory_retrieval_limit: int = 3,
        max_invalid_retries: int = 1,
    ):
        self.traffic_expert = traffic_expert
        self.unknown_scorer = unknown_scorer
        self.supervisor = supervisor
        self.tools = {tool.action: tool for tool in tools}
        self.budget_limits = budget_limits or BudgetLimits()
        self.allowed_actions = (
            frozenset(AgentAction) if allowed_actions is None else allowed_actions
        )
        self.allowed_information_domains = (
            frozenset(GapDomain)
            if allowed_information_domains is None
            else allowed_information_domains
        )
        self.experience_memory = experience_memory
        self.memory_retrieval_limit = memory_retrieval_limit
        self.max_invalid_retries = max_invalid_retries

    def run(self, runtime_input: RuntimeInput) -> RuntimeResult:
        trace: list[TraceEvent] = []
        failures: list[FailureCode] = []
        budget = BudgetState(limits=self.budget_limits)
        step = 0

        def emit(
            event_type: TraceEventType,
            *,
            round_index: int,
            summary: dict[str, Any] | None = None,
            before: dict[str, Any] | None = None,
            failure: FailureCode | None = None,
            stop_reason: str | None = None,
        ) -> None:
            nonlocal step
            trace.append(
                TraceEvent(
                    step=step,
                    round_index=round_index,
                    event_type=event_type,
                    summary=summary or {},
                    budget_before=before if before is not None else budget.snapshot(),
                    budget_after=budget.snapshot(),
                    failure=failure,
                    stop_reason=stop_reason,
                )
            )
            step += 1

        unsafe = [item.evidence_id for item in runtime_input.initial_evidence if not item.model_safe]
        if unsafe:
            failures.append(FailureCode.UNSAFE_EVIDENCE)
            emit(
                TraceEventType.FAILURE,
                round_index=0,
                summary={"unsafe_evidence_ids": unsafe},
                failure=FailureCode.UNSAFE_EVIDENCE,
            )
            return self._finish_without_state(
                runtime_input,
                budget,
                trace,
                failures,
                "initial evidence is not model-safe",
                emit,
            )

        experiences: tuple[ExperienceRecord, ...] = ()
        if self.experience_memory is not None:
            experiences = self.experience_memory.retrieve(
                runtime_input.memory_query,
                limit=self.memory_retrieval_limit,
            )
            emit(
                TraceEventType.MEMORY,
                round_index=0,
                summary={"retrieved_experience_ids": [item.experience_id for item in experiences]},
            )

        evaluated = self._evaluate(
            evidence=runtime_input.initial_evidence,
            previous_state=None,
            budget=budget,
            trace_emit=emit,
            failures=failures,
            round_index=0,
        )
        if evaluated is None:
            return self._finish_without_state(
                runtime_input,
                budget,
                trace,
                failures,
                "initial model evaluation failed",
                emit,
            )
        expert_result, unknown = evaluated
        state = EvidenceState(
            sample_id=runtime_input.sample_id,
            evidence=runtime_input.initial_evidence,
            traffic_expert_result=expert_result,
            unknown_decision=unknown,
            capabilities=runtime_input.capabilities,
            budget=budget,
            retrieved_experiences=experiences,
        )

        consecutive_rejections = 0
        while True:
            before = budget.snapshot()
            if not budget.can_consume(kind="supervisor"):
                failures.append(FailureCode.BUDGET_EXHAUSTED)
                emit(
                    TraceEventType.FAILURE,
                    round_index=state.round_index,
                    failure=FailureCode.BUDGET_EXHAUSTED,
                    stop_reason="supervisor budget exhausted",
                )
                return self._finish(runtime_input, state, trace, failures, emit)
            try:
                decision = self.supervisor.decide(state.model_copy(deep=True))
                budget.consume(kind="supervisor")
            except Exception as exc:
                budget.consume(kind="supervisor")
                failures.append(FailureCode.SUPERVISOR_OUTPUT_FAILURE)
                consecutive_rejections += 1
                emit(
                    TraceEventType.FAILURE,
                    round_index=state.round_index,
                    summary={"error_type": type(exc).__name__},
                    before=before,
                    failure=FailureCode.SUPERVISOR_OUTPUT_FAILURE,
                )
                if consecutive_rejections > self.max_invalid_retries:
                    return self._finish(runtime_input, state, trace, failures, emit)
                continue
            if not isinstance(decision, SupervisorDecision):
                failures.append(FailureCode.SUPERVISOR_OUTPUT_FAILURE)
                consecutive_rejections += 1
                emit(
                    TraceEventType.FAILURE,
                    round_index=state.round_index,
                    summary={"error_type": "invalid_decision_type"},
                    before=before,
                    failure=FailureCode.SUPERVISOR_OUTPUT_FAILURE,
                )
                if consecutive_rejections > self.max_invalid_retries:
                    return self._finish(runtime_input, state, trace, failures, emit)
                continue

            if decision.metrics.abstract_tokens or decision.metrics.abstract_cost or decision.metrics.abstract_latency:
                if not self._add_metrics(budget, decision.metrics):
                    failures.append(FailureCode.BUDGET_EXHAUSTED)
                    emit(
                        TraceEventType.FAILURE,
                        round_index=state.round_index,
                        failure=FailureCode.BUDGET_EXHAUSTED,
                        stop_reason="supervisor metrics exceeded budget",
                    )
                    return self._finish(runtime_input, state, trace, failures, emit)
            emit(
                TraceEventType.SUPERVISOR,
                round_index=state.round_index,
                summary={
                    "action": decision.action.value,
                    "request_signature": decision.request.signature if decision.request else None,
                    "planned_action_count": len(decision.planned_actions),
                    "evidence_state": {
                        "evidence_count": len(state.evidence),
                        "sufficiency": state.traffic_expert_result.evidence_sufficiency.value,
                        "unknown_state": state.unknown_decision.state.value,
                        "available_capabilities": sorted(
                            item.value for item in state.available_capabilities
                        ),
                        "request_count": len(state.request_history),
                        "tool_failure_count": len(state.tool_failures),
                        "retrieved_experience_ids": [
                            item.experience_id for item in state.retrieved_experiences
                        ],
                    },
                },
                before=before,
            )

            validation_failure = self._validate_decision(decision, state)
            if validation_failure is not None:
                failures.append(validation_failure)
                consecutive_rejections += 1
                emit(
                    TraceEventType.FAILURE,
                    round_index=state.round_index,
                    summary={"action": decision.action.value},
                    failure=validation_failure,
                )
                if consecutive_rejections > self.max_invalid_retries:
                    return self._finish(runtime_input, state, trace, failures, emit)
                continue

            if decision.action in TERMINAL_ACTIONS:
                return self._finish(
                    runtime_input,
                    state,
                    trace,
                    failures,
                    emit,
                    requested_action=decision.action,
                    reason=decision.short_reason,
                )

            if state.round_index >= self.budget_limits.max_rounds:
                failures.append(FailureCode.MAX_ROUNDS_REACHED)
                emit(
                    TraceEventType.FAILURE,
                    round_index=state.round_index,
                    summary={"action": decision.action.value},
                    failure=FailureCode.MAX_ROUNDS_REACHED,
                    stop_reason="maximum evidence rounds reached",
                )
                return self._finish(runtime_input, state, trace, failures, emit)

            assert decision.request is not None
            before = budget.snapshot()
            is_rag = decision.action is AgentAction.RETRIEVE_KNOWLEDGE
            if not budget.can_consume(kind="tool") or (is_rag and not budget.can_consume(kind="rag")):
                failures.append(FailureCode.BUDGET_EXHAUSTED)
                emit(
                    TraceEventType.FAILURE,
                    round_index=state.round_index,
                    summary={"action": decision.action.value},
                    before=before,
                    failure=FailureCode.BUDGET_EXHAUSTED,
                    stop_reason="tool budget exhausted",
                )
                return self._finish(runtime_input, state, trace, failures, emit)

            tool = self.tools[decision.action]
            try:
                tool_result = tool.execute(decision.request, state.evidence)
            except Exception as exc:
                tool_result = ToolResult(
                    status=ToolStatus.FAILURE,
                    request_signature=decision.request.signature,
                    error=type(exc).__name__,
                )
            if not budget.can_consume(kind="tool", metrics=tool_result.metrics):
                failures.append(FailureCode.BUDGET_EXHAUSTED)
                emit(
                    TraceEventType.FAILURE,
                    round_index=state.round_index,
                    summary={"action": decision.action.value},
                    before=before,
                    failure=FailureCode.BUDGET_EXHAUSTED,
                    stop_reason="tool metrics exceeded budget",
                )
                return self._finish(runtime_input, state, trace, failures, emit)
            budget.consume(kind="tool", metrics=tool_result.metrics)
            if is_rag:
                budget.consume(kind="rag")
            emit(
                TraceEventType.TOOL,
                round_index=state.round_index,
                summary={
                    "action": decision.action.value,
                    "request_signature": decision.request.signature,
                    "status": tool_result.status.value,
                    "evidence_ids": [item.evidence_id for item in tool_result.evidence],
                    "provenance": [item.provenance for item in tool_result.evidence],
                },
                before=before,
            )

            state.request_history = (*state.request_history, decision.request.signature)
            state.action_history = (*state.action_history, decision.action)
            if tool_result.request_signature != decision.request.signature:
                failures.append(FailureCode.TOOL_FAILURE)
                state.tool_failures = (*state.tool_failures, FailureCode.TOOL_FAILURE)
                emit(
                    TraceEventType.FAILURE,
                    round_index=state.round_index,
                    summary={"action": decision.action.value, "reason": "signature_mismatch"},
                    failure=FailureCode.TOOL_FAILURE,
                )
                return self._finish(runtime_input, state, trace, failures, emit)
            if tool_result.status is ToolStatus.UNAVAILABLE:
                failures.append(FailureCode.CAPABILITY_UNAVAILABLE)
                state.tool_failures = (*state.tool_failures, FailureCode.CAPABILITY_UNAVAILABLE)
                state.capabilities = tuple(
                    item.model_copy(update={"available": False, "reason": tool_result.error})
                    if item.capability is ACTION_CAPABILITY[decision.action]
                    else item
                    for item in state.capabilities
                )
                emit(
                    TraceEventType.FAILURE,
                    round_index=state.round_index,
                    summary={"action": decision.action.value},
                    failure=FailureCode.CAPABILITY_UNAVAILABLE,
                )
                consecutive_rejections += 1
                if consecutive_rejections > self.max_invalid_retries:
                    return self._finish(runtime_input, state, trace, failures, emit)
                continue
            if tool_result.status is ToolStatus.FAILURE:
                failures.append(FailureCode.TOOL_FAILURE)
                state.tool_failures = (*state.tool_failures, FailureCode.TOOL_FAILURE)
                emit(
                    TraceEventType.FAILURE,
                    round_index=state.round_index,
                    summary={"action": decision.action.value},
                    failure=FailureCode.TOOL_FAILURE,
                )
                consecutive_rejections += 1
                if consecutive_rejections > self.max_invalid_retries:
                    return self._finish(runtime_input, state, trace, failures, emit)
                continue

            if any(not item.model_safe for item in tool_result.evidence):
                failures.append(FailureCode.UNSAFE_EVIDENCE)
                emit(
                    TraceEventType.FAILURE,
                    round_index=state.round_index,
                    failure=FailureCode.UNSAFE_EVIDENCE,
                )
                return self._finish(runtime_input, state, trace, failures, emit)
            if is_rag and any(
                item.domain is not GapDomain.KNOWLEDGE or item.gap_type is not GapType.KNOWLEDGE
                for item in tool_result.evidence
            ):
                failures.append(FailureCode.UNSAFE_EVIDENCE)
                emit(
                    TraceEventType.FAILURE,
                    round_index=state.round_index,
                    summary={"action": decision.action.value, "reason": "rag_domain_mismatch"},
                    failure=FailureCode.UNSAFE_EVIDENCE,
                )
                return self._finish(runtime_input, state, trace, failures, emit)

            consecutive_rejections = 0
            budget.rounds += 1
            state.round_index += 1
            state.evidence = (*state.evidence, *tool_result.evidence)
            evaluated = self._evaluate(
                evidence=state.evidence,
                previous_state=state,
                budget=budget,
                trace_emit=emit,
                failures=failures,
                round_index=state.round_index,
            )
            if evaluated is None:
                return self._finish(runtime_input, state, trace, failures, emit)
            state.traffic_expert_result, state.unknown_decision = evaluated

    def _validate_decision(
        self,
        decision: SupervisorDecision,
        state: EvidenceState,
    ) -> FailureCode | None:
        if decision.action not in self.allowed_actions:
            return FailureCode.INVALID_ACTION
        if decision.action in TERMINAL_ACTIONS:
            return FailureCode.INVALID_ACTION if decision.request is not None else None
        if decision.action not in EVIDENCE_ACTIONS or decision.request is None:
            return FailureCode.INVALID_ACTION
        if decision.request.action is not decision.action:
            return FailureCode.INVALID_ACTION
        capability = ACTION_CAPABILITY[decision.action]
        if capability not in state.available_capabilities or decision.action not in self.tools:
            return FailureCode.CAPABILITY_UNAVAILABLE
        if decision.request.signature in state.request_history:
            return FailureCode.REPEATED_REQUEST
        required_gap = ACTION_GAP[decision.action]
        gaps = [item for item in state.traffic_expert_result.missing_evidence if item.valuable]
        matching = [item for item in gaps if item.gap_type is required_gap]
        if not matching:
            return FailureCode.INVALID_ACTION
        if any(item.domain not in self.allowed_information_domains for item in matching):
            return FailureCode.INVALID_ACTION
        if decision.action is AgentAction.RETRIEVE_KNOWLEDGE and any(
            item.domain is not GapDomain.KNOWLEDGE for item in matching
        ):
            return FailureCode.INVALID_ACTION
        return None

    def _evaluate(
        self,
        *,
        evidence: tuple[Any, ...],
        previous_state: EvidenceState | None,
        budget: BudgetState,
        trace_emit: Any,
        failures: list[FailureCode],
        round_index: int,
    ) -> tuple[TrafficExpertResult, UnknownDecision] | None:
        before = budget.snapshot()
        if not budget.can_consume(kind="traffic_expert"):
            failures.append(FailureCode.BUDGET_EXHAUSTED)
            trace_emit(
                TraceEventType.FAILURE,
                round_index=round_index,
                failure=FailureCode.BUDGET_EXHAUSTED,
                stop_reason="Traffic Expert budget exhausted",
            )
            return None
        try:
            result = self.traffic_expert.evaluate(evidence, previous_state)
        except Exception as exc:
            budget.consume(kind="traffic_expert")
            failures.append(FailureCode.TRAFFIC_EXPERT_OUTPUT_FAILURE)
            trace_emit(
                TraceEventType.FAILURE,
                round_index=round_index,
                summary={"error_type": type(exc).__name__},
                before=before,
                failure=FailureCode.TRAFFIC_EXPERT_OUTPUT_FAILURE,
            )
            return None
        if not budget.can_consume(kind="traffic_expert", metrics=result.metrics):
            failures.append(FailureCode.BUDGET_EXHAUSTED)
            trace_emit(
                TraceEventType.FAILURE,
                round_index=round_index,
                before=before,
                failure=FailureCode.BUDGET_EXHAUSTED,
                stop_reason="Traffic Expert metrics exceeded budget",
            )
            return None
        budget.consume(kind="traffic_expert", metrics=result.metrics)
        trace_emit(
            TraceEventType.TRAFFIC_EXPERT,
            round_index=round_index,
            summary={
                "fine_labels": [item.label for item in result.fine_candidates],
                "coarse_labels": [item.label for item in result.coarse_candidates],
                "sufficiency": result.evidence_sufficiency.value,
                "supporting_evidence_ids": [item.evidence_id for item in result.supporting_evidence],
                "missing_gap_types": [item.gap_type.value for item in result.missing_evidence],
            },
            before=before,
        )
        try:
            unknown = self.unknown_scorer.score(
                result,
                {"round_index": round_index, "evidence_count": len(evidence)},
            )
        except Exception as exc:
            failures.append(FailureCode.UNKNOWN_SCORER_FAILURE)
            trace_emit(
                TraceEventType.FAILURE,
                round_index=round_index,
                summary={"error_type": type(exc).__name__},
                failure=FailureCode.UNKNOWN_SCORER_FAILURE,
            )
            return None
        trace_emit(
            TraceEventType.UNKNOWN_SCORER,
            round_index=round_index,
            summary={"state": unknown.state.value, "score": unknown.score},
        )
        return result, unknown

    @staticmethod
    def _add_metrics(budget: BudgetState, metrics: Any) -> bool:
        if (
            budget.abstract_tokens + metrics.abstract_tokens > budget.limits.max_abstract_tokens
            or budget.abstract_cost + metrics.abstract_cost > budget.limits.max_abstract_cost
            or budget.abstract_latency + metrics.abstract_latency > budget.limits.max_abstract_latency
        ):
            return False
        budget.abstract_tokens += metrics.abstract_tokens
        budget.abstract_cost += metrics.abstract_cost
        budget.abstract_latency += metrics.abstract_latency
        return True

    def _finish_without_state(
        self,
        runtime_input: RuntimeInput,
        budget: BudgetState,
        trace: list[TraceEvent],
        failures: list[FailureCode],
        reason: str,
        emit: Any,
    ) -> RuntimeResult:
        final = FinalDecision(
            decision_type=FinalDecisionType.ABSTAIN,
            action=AgentAction.ABSTAIN,
            reason=reason,
            unknown_state=UnknownState.UNCERTAIN,
        )
        emit(
            TraceEventType.FINAL,
            round_index=budget.rounds,
            summary={"action": final.action.value, "decision_type": final.decision_type.value},
            stop_reason=reason,
        )
        return RuntimeResult(
            sample_id=runtime_input.sample_id,
            final_decision=final,
            final_state=None,
            trace=tuple(trace),
            budget=budget,
            failures=tuple(failures),
        )

    def _finish(
        self,
        runtime_input: RuntimeInput,
        state: EvidenceState,
        trace: list[TraceEvent],
        failures: list[FailureCode],
        emit: Any,
        *,
        requested_action: AgentAction = AgentAction.ABSTAIN,
        reason: str = "runtime safety stop",
    ) -> RuntimeResult:
        action = requested_action
        label: str | None = None
        if action is AgentAction.ACCEPT_FINE and state.traffic_expert_result.fine_candidates:
            decision_type = FinalDecisionType.FINE
            label = state.traffic_expert_result.fine_candidates[0].label
        elif action is AgentAction.BACKOFF_COARSE and state.traffic_expert_result.coarse_candidates:
            decision_type = FinalDecisionType.COARSE
            label = state.traffic_expert_result.coarse_candidates[0].label
        elif action is AgentAction.REJECT_UNKNOWN:
            decision_type = FinalDecisionType.UNKNOWN
        else:
            action = AgentAction.ABSTAIN
            decision_type = FinalDecisionType.ABSTAIN
        final = FinalDecision(
            decision_type=decision_type,
            action=action,
            label=label,
            reason=reason,
            unknown_state=state.unknown_decision.state,
        )
        memory_written = False
        if (
            self.experience_memory is not None
            and runtime_input.phase is RuntimePhase.TRAIN
            and runtime_input.verified_feedback is not None
            and runtime_input.verified_feedback.verified
        ):
            record = ExperienceRecord(
                experience_id=f"{runtime_input.sample_id}:{len(trace)}",
                state_summary=(
                    f"rounds={state.round_index}; unknown={state.unknown_decision.state.value}; "
                    f"evidence={len(state.evidence)}"
                ),
                action=final.action,
                outcome=runtime_input.verified_feedback.summary,
                feedback=runtime_input.verified_feedback,
                keywords=tuple(runtime_input.memory_query.split()),
                positive=final.decision_type is not FinalDecisionType.ABSTAIN,
            )
            self.experience_memory.add(record)
            memory_written = True
            emit(
                TraceEventType.MEMORY,
                round_index=state.round_index,
                summary={"write": True, "experience_id": record.experience_id},
            )
        emit(
            TraceEventType.FINAL,
            round_index=state.round_index,
            summary={
                "action": final.action.value,
                "decision_type": final.decision_type.value,
                "label": final.label,
            },
            stop_reason=reason,
        )
        return RuntimeResult(
            sample_id=runtime_input.sample_id,
            final_decision=final,
            final_state=state,
            trace=tuple(trace),
            budget=state.budget,
            failures=tuple(failures),
            memory_written=memory_written,
        )
