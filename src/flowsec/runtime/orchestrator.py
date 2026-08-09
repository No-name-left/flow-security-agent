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
    BudgetView,
    CallMetrics,
    Capability,
    CapabilityStatus,
    EvidenceItem,
    EvidenceState,
    EvidenceSufficiency,
    EvidenceTrust,
    FailureCode,
    FinalDecision,
    FinalDecisionType,
    GapDomain,
    GapType,
    RuntimeInput,
    RuntimePhase,
    RuntimeResult,
    SupervisorDecision,
    ToolRequest,
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
        budget_limits: BudgetLimits,
        tools: Iterable[EvidenceTool] = (),
        allowed_actions: frozenset[AgentAction] | None = None,
        allowed_information_domains: frozenset[GapDomain] | None = None,
        allowed_request_parameters: dict[
            AgentAction, tuple[dict[str, Any], ...]
        ] | None = None,
        experience_memory: ExperienceMemory | None = None,
        memory_retrieval_limit: int,
        max_invalid_retries: int = 1,
    ):
        tool_list = list(tools)
        if len({tool.action for tool in tool_list}) != len(tool_list):
            raise ValueError("tool actions must be unique")
        if any(tool.action not in EVIDENCE_ACTIONS for tool in tool_list):
            raise ValueError("only evidence actions may be registered as tools")
        if any(tool.capability is not ACTION_CAPABILITY[tool.action] for tool in tool_list):
            raise ValueError("tool capability does not match its registered action")
        self.traffic_expert = traffic_expert
        self.unknown_scorer = unknown_scorer
        self.supervisor = supervisor
        self.tools = {tool.action: tool for tool in tool_list}
        if memory_retrieval_limit < 0:
            raise ValueError("memory_retrieval_limit cannot be negative")
        if max_invalid_retries < 0:
            raise ValueError("max_invalid_retries cannot be negative")
        self.budget_limits = budget_limits
        self.allowed_actions = (
            frozenset(AgentAction) if allowed_actions is None else allowed_actions
        )
        self.allowed_information_domains = (
            frozenset(GapDomain)
            if allowed_information_domains is None
            else allowed_information_domains
        )
        self.allowed_request_signatures = {
            action: frozenset(
                ToolRequest(action=action, parameters=parameters).signature
                for parameters in parameter_options
            )
            for action, parameter_options in (allowed_request_parameters or {}).items()
        }
        self.experience_memory = experience_memory
        self.memory_retrieval_limit = memory_retrieval_limit
        self.max_invalid_retries = max_invalid_retries

    def run(self, runtime_input: RuntimeInput) -> RuntimeResult:
        trace: list[TraceEvent] = []
        failures: list[FailureCode] = []
        budget = BudgetState(limits=self.budget_limits)
        step = 0
        initial_evidence = tuple(runtime_input.initial_evidence)
        initial_capabilities = tuple(runtime_input.capabilities)

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

        try:
            initial_evidence = tuple(
                EvidenceItem.model_validate(item.model_dump(mode="python"))
                for item in initial_evidence
            )
            initial_capabilities = tuple(
                CapabilityStatus.model_validate(item.model_dump(mode="python"))
                for item in initial_capabilities
            )
        except Exception as exc:
            failures.append(FailureCode.UNSAFE_EVIDENCE)
            emit(
                TraceEventType.FAILURE,
                round_index=0,
                summary={"error_type": type(exc).__name__, "stage": "initial_projection"},
                failure=FailureCode.UNSAFE_EVIDENCE,
            )
            return self._finish_without_state(
                runtime_input,
                budget,
                trace,
                failures,
                "initial evidence projection failed validation",
                emit,
            )

        unsafe = [item.evidence_id for item in initial_evidence if not item.model_safe]
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
            try:
                retrieved = self.experience_memory.retrieve(
                    runtime_input.memory_query,
                    limit=self.memory_retrieval_limit,
                )
                if any(
                    not isinstance(item, ExperienceRecord) or not item.feedback.verified
                    for item in retrieved
                ):
                    raise ValueError("memory returned an unvalidated experience")
                experiences = tuple(
                    ExperienceRecord.model_validate(item.model_dump(mode="python"))
                    for item in retrieved
                )
                emit(
                    TraceEventType.MEMORY,
                    round_index=0,
                    summary={
                        "retrieved_experience_ids": [item.experience_id for item in experiences]
                    },
                )
            except Exception as exc:
                failures.append(FailureCode.MEMORY_ACCESS_FAILURE)
                emit(
                    TraceEventType.FAILURE,
                    round_index=0,
                    summary={"error_type": type(exc).__name__},
                    failure=FailureCode.MEMORY_ACCESS_FAILURE,
                )

        evaluated = self._evaluate(
            evidence=initial_evidence,
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
            evidence=initial_evidence,
            traffic_expert_result=expert_result,
            traffic_expert_history=(expert_result,),
            unknown_decision=unknown,
            capabilities=initial_capabilities,
            budget=budget,
            retrieved_experiences=experiences,
        )

        consecutive_rejections = 0
        while True:
            before = budget.snapshot()
            supervisor_view = state.to_supervisor_view()
            try:
                supervisor_estimate = self.supervisor.estimate(
                    supervisor_view.model_copy(deep=True)
                )
                if not isinstance(supervisor_estimate, CallMetrics):
                    raise TypeError("Supervisor estimate must be CallMetrics")
                supervisor_estimate = supervisor_estimate.model_copy(deep=True)
            except Exception as exc:
                failures.append(FailureCode.SUPERVISOR_OUTPUT_FAILURE)
                consecutive_rejections += 1
                emit(
                    TraceEventType.FAILURE,
                    round_index=state.round_index,
                    summary={"error_type": type(exc).__name__, "stage": "estimate"},
                    before=before,
                    failure=FailureCode.SUPERVISOR_OUTPUT_FAILURE,
                )
                if consecutive_rejections > self.max_invalid_retries:
                    return self._finish(runtime_input, state, trace, failures, emit)
                continue
            if not budget.can_consume(kind="supervisor", metrics=supervisor_estimate):
                failures.append(FailureCode.BUDGET_EXHAUSTED)
                emit(
                    TraceEventType.FAILURE,
                    round_index=state.round_index,
                    failure=FailureCode.BUDGET_EXHAUSTED,
                    stop_reason="supervisor budget exhausted",
                )
                return self._finish(runtime_input, state, trace, failures, emit)
            budget.consume(kind="supervisor", metrics=supervisor_estimate)
            try:
                decision = self.supervisor.decide(supervisor_view.model_copy(deep=True))
            except Exception as exc:
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

            try:
                decision = SupervisorDecision.model_validate(
                    decision.model_dump(mode="python")
                )
            except Exception as exc:
                failures.append(FailureCode.SUPERVISOR_OUTPUT_FAILURE)
                consecutive_rejections += 1
                emit(
                    TraceEventType.FAILURE,
                    round_index=state.round_index,
                    summary={"error_type": type(exc).__name__, "stage": "validation"},
                    failure=FailureCode.SUPERVISOR_OUTPUT_FAILURE,
                )
                if consecutive_rejections > self.max_invalid_retries:
                    return self._finish(runtime_input, state, trace, failures, emit)
                continue
            if not self._metrics_within_estimate(decision.metrics, supervisor_estimate):
                failures.append(FailureCode.SUPERVISOR_OUTPUT_FAILURE)
                emit(
                    TraceEventType.FAILURE,
                    round_index=state.round_index,
                    summary={"stage": "metrics", "reason": "estimate_exceeded"},
                    failure=FailureCode.SUPERVISOR_OUTPUT_FAILURE,
                )
                return self._finish(runtime_input, state, trace, failures, emit)
            budget.reconcile_metrics(
                reserved=supervisor_estimate,
                actual=decision.metrics,
            )
            emit(
                TraceEventType.SUPERVISOR,
                round_index=state.round_index,
                summary={
                    "action": decision.action.value,
                    "short_reason": decision.short_reason,
                    "request_signature": decision.request.signature if decision.request else None,
                    "planned_action_count": len(decision.planned_actions),
                    "estimated_metrics": supervisor_estimate.model_dump(mode="json"),
                    "actual_metrics": decision.metrics.model_dump(mode="json"),
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
            tool = self.tools[decision.action]
            try:
                tool_estimate = tool.estimate(decision.request.model_copy(deep=True))
                if not isinstance(tool_estimate, CallMetrics):
                    raise TypeError("Tool estimate must be CallMetrics")
                tool_estimate = tool_estimate.model_copy(deep=True)
            except Exception as exc:
                failures.append(FailureCode.TOOL_FAILURE)
                emit(
                    TraceEventType.FAILURE,
                    round_index=state.round_index,
                    summary={"error_type": type(exc).__name__, "stage": "estimate"},
                    before=before,
                    failure=FailureCode.TOOL_FAILURE,
                )
                return self._finish(runtime_input, state, trace, failures, emit)
            if not budget.can_consume(kind="tool", metrics=tool_estimate) or (
                is_rag and not budget.can_consume(kind="rag")
            ):
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
            budget.consume(kind="tool", metrics=tool_estimate)
            if is_rag:
                budget.consume(kind="rag")

            try:
                tool_result = tool.execute(
                    decision.request.model_copy(deep=True),
                    tuple(item.model_copy(deep=True) for item in state.evidence),
                )
                tool_result = ToolResult.model_validate(
                    tool_result.model_dump(mode="python")
                )
                tool_raised = False
            except Exception as exc:
                tool_result = ToolResult(
                    status=ToolStatus.FAILURE,
                    request_signature=decision.request.signature,
                    error=type(exc).__name__,
                )
                tool_raised = True
            if not self._metrics_within_estimate(tool_result.metrics, tool_estimate):
                failures.append(FailureCode.TOOL_FAILURE)
                emit(
                    TraceEventType.FAILURE,
                    round_index=state.round_index,
                    summary={"action": decision.action.value, "reason": "estimate_exceeded"},
                    before=before,
                    failure=FailureCode.TOOL_FAILURE,
                    stop_reason="tool violated preflight cost estimate",
                )
                return self._finish(runtime_input, state, trace, failures, emit)
            if not tool_raised:
                budget.reconcile_metrics(
                    reserved=tool_estimate,
                    actual=tool_result.metrics,
                )
            emit(
                TraceEventType.TOOL,
                round_index=state.round_index,
                summary={
                    "action": decision.action.value,
                    "request_signature": decision.request.signature,
                    "status": tool_result.status.value,
                    "evidence_ids": [item.evidence_id for item in tool_result.evidence],
                    "provenance": [item.provenance for item in tool_result.evidence],
                    "estimated_metrics": tool_estimate.model_dump(mode="json"),
                    "actual_metrics": tool_result.metrics.model_dump(mode="json"),
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
                    item.model_copy(
                        update={"available": False, "reason": "tool reported unavailable"}
                    )
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
                item.domain is not GapDomain.KNOWLEDGE
                or item.gap_type is not GapType.KNOWLEDGE
                or item.trust is not EvidenceTrust.UNTRUSTED_EVIDENCE
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

            merged_evidence, merge_failure = self._merge_evidence(
                state.evidence,
                tool_result.evidence,
            )
            if merge_failure is not None:
                failures.append(merge_failure)
                state.tool_failures = (*state.tool_failures, merge_failure)
                emit(
                    TraceEventType.FAILURE,
                    round_index=state.round_index,
                    summary={"action": decision.action.value, "reason": "evidence_not_new"},
                    failure=merge_failure,
                )
                consecutive_rejections += 1
                if consecutive_rejections > self.max_invalid_retries:
                    return self._finish(runtime_input, state, trace, failures, emit)
                continue

            consecutive_rejections = 0
            budget.rounds += 1
            state.round_index += 1
            state.evidence = merged_evidence
            evaluated = self._evaluate(
                evidence=state.evidence,
                budget=budget,
                trace_emit=emit,
                failures=failures,
                round_index=state.round_index,
            )
            if evaluated is None:
                return self._finish(runtime_input, state, trace, failures, emit)
            next_expert_result, state.unknown_decision = evaluated
            state.traffic_expert_result = next_expert_result
            state.traffic_expert_history = (
                *state.traffic_expert_history,
                next_expert_result,
            )

    def _validate_decision(
        self,
        decision: SupervisorDecision,
        state: EvidenceState,
    ) -> FailureCode | None:
        if decision.action not in self.allowed_actions:
            return FailureCode.INVALID_ACTION
        if decision.action in TERMINAL_ACTIONS:
            if decision.request is not None:
                return FailureCode.INVALID_ACTION
            result = state.traffic_expert_result
            if decision.action is AgentAction.ACCEPT_FINE:
                if (
                    result.evidence_sufficiency is not EvidenceSufficiency.SUFFICIENT
                    or not result.fine_candidates
                    or state.unknown_decision.state is not UnknownState.KNOWN_LIKELY
                ):
                    return FailureCode.INVALID_ACTION
            elif decision.action is AgentAction.BACKOFF_COARSE:
                if (
                    result.evidence_sufficiency is EvidenceSufficiency.INSUFFICIENT
                    or not result.coarse_candidates
                    or state.unknown_decision.state is UnknownState.UNKNOWN_LIKELY
                ):
                    return FailureCode.INVALID_ACTION
            elif (
                decision.action is AgentAction.REJECT_UNKNOWN
                and state.unknown_decision.state is not UnknownState.UNKNOWN_LIKELY
            ):
                return FailureCode.INVALID_ACTION
            return None
        if decision.action not in EVIDENCE_ACTIONS or decision.request is None:
            return FailureCode.INVALID_ACTION
        if decision.request.action is not decision.action:
            return FailureCode.INVALID_ACTION
        if not self._request_parameters_are_safe(decision.request):
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
        evidence: tuple[EvidenceItem, ...],
        budget: BudgetState,
        trace_emit: Any,
        failures: list[FailureCode],
        round_index: int,
    ) -> tuple[TrafficExpertResult, UnknownDecision] | None:
        before = budget.snapshot()
        try:
            expert_input = tuple(item.model_copy(deep=True) for item in evidence)
            expert_estimate = self.traffic_expert.estimate(
                tuple(item.model_copy(deep=True) for item in expert_input)
            )
            if not isinstance(expert_estimate, CallMetrics):
                raise TypeError("Traffic Expert estimate must be CallMetrics")
            expert_estimate = expert_estimate.model_copy(deep=True)
        except Exception as exc:
            failures.append(FailureCode.TRAFFIC_EXPERT_OUTPUT_FAILURE)
            trace_emit(
                TraceEventType.FAILURE,
                round_index=round_index,
                summary={"error_type": type(exc).__name__, "stage": "estimate"},
                before=before,
                failure=FailureCode.TRAFFIC_EXPERT_OUTPUT_FAILURE,
            )
            return None
        if not budget.can_consume(kind="traffic_expert", metrics=expert_estimate):
            failures.append(FailureCode.BUDGET_EXHAUSTED)
            trace_emit(
                TraceEventType.FAILURE,
                round_index=round_index,
                failure=FailureCode.BUDGET_EXHAUSTED,
                stop_reason="Traffic Expert budget exhausted",
            )
            return None
        budget.consume(kind="traffic_expert", metrics=expert_estimate)
        try:
            result = self.traffic_expert.evaluate(
                tuple(item.model_copy(deep=True) for item in expert_input)
            )
            if not isinstance(result, TrafficExpertResult):
                raise TypeError("Traffic Expert output must be TrafficExpertResult")
            result = TrafficExpertResult.model_validate(
                result.model_dump(mode="python")
            )
        except Exception as exc:
            failures.append(FailureCode.TRAFFIC_EXPERT_OUTPUT_FAILURE)
            trace_emit(
                TraceEventType.FAILURE,
                round_index=round_index,
                summary={"error_type": type(exc).__name__},
                before=before,
                failure=FailureCode.TRAFFIC_EXPERT_OUTPUT_FAILURE,
            )
            return None
        if not self._metrics_within_estimate(result.metrics, expert_estimate):
            failures.append(FailureCode.TRAFFIC_EXPERT_OUTPUT_FAILURE)
            trace_emit(
                TraceEventType.FAILURE,
                round_index=round_index,
                summary={"stage": "metrics", "reason": "estimate_exceeded"},
                before=before,
                failure=FailureCode.TRAFFIC_EXPERT_OUTPUT_FAILURE,
                stop_reason="Traffic Expert violated preflight cost estimate",
            )
            return None
        budget.reconcile_metrics(reserved=expert_estimate, actual=result.metrics)
        trace_emit(
            TraceEventType.TRAFFIC_EXPERT,
            round_index=round_index,
            summary={
                "fine_labels": [item.label for item in result.fine_candidates],
                "coarse_labels": [item.label for item in result.coarse_candidates],
                "sufficiency": result.evidence_sufficiency.value,
                "supporting_evidence_ids": [item.evidence_id for item in result.supporting_evidence],
                "missing_gap_types": [item.gap_type.value for item in result.missing_evidence],
                "estimated_metrics": expert_estimate.model_dump(mode="json"),
                "actual_metrics": result.metrics.model_dump(mode="json"),
            },
            before=before,
        )
        try:
            unknown = self.unknown_scorer.score(
                result.model_copy(deep=True),
                {"round_index": round_index, "evidence_count": len(evidence)},
            )
            if not isinstance(unknown, UnknownDecision):
                raise TypeError("Unknown Scorer output must be UnknownDecision")
            unknown = UnknownDecision.model_validate(
                unknown.model_dump(mode="python")
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
    def _metrics_within_estimate(actual: CallMetrics, estimate: CallMetrics) -> bool:
        return (
            actual.abstract_tokens <= estimate.abstract_tokens
            and actual.abstract_cost <= estimate.abstract_cost
            and actual.abstract_latency <= estimate.abstract_latency
        )

    def _request_parameters_are_safe(self, request: ToolRequest) -> bool:
        normalized = {str(key).casefold().replace("-", "_"): value for key, value in request.parameters.items()}
        future_markers = {
            "future",
            "include_future",
            "lookahead",
            "future_window",
            "end_timestamp",
            "absolute_end_time",
        }
        if any(
            key in future_markers
            and not (value is False or value is None or value == 0 or value == "")
            for key, value in normalized.items()
        ):
            return False
        if request.action is AgentAction.EXPAND_TEMPORAL_CONTEXT:
            if normalized.get("past_only") is not True:
                return False
        allowed = self.allowed_request_signatures.get(request.action)
        return allowed is None or request.signature in allowed

    @staticmethod
    def _merge_evidence(
        current: tuple[EvidenceItem, ...],
        incoming: tuple[EvidenceItem, ...],
    ) -> tuple[tuple[EvidenceItem, ...], FailureCode | None]:
        by_id = {item.evidence_id: item for item in current}
        fingerprints = {
            item.model_dump_json(exclude={"evidence_id"})
            for item in current
        }
        additions: list[EvidenceItem] = []
        for item in incoming:
            existing = by_id.get(item.evidence_id)
            if existing is not None:
                if existing != item:
                    return current, FailureCode.UNSAFE_EVIDENCE
                continue
            fingerprint = item.model_dump_json(exclude={"evidence_id"})
            if fingerprint in fingerprints:
                continue
            by_id[item.evidence_id] = item
            fingerprints.add(fingerprint)
            additions.append(item)
        if not additions:
            return current, FailureCode.NO_STATE_CHANGE
        return (*current, *additions), None

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
            budget=BudgetView.from_state(budget),
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
                outcome=(
                    f"verified positive terminal outcome: {final.decision_type.value}"
                    if runtime_input.verified_feedback.outcome_positive
                    else f"verified negative terminal outcome: {final.decision_type.value}"
                ),
                feedback=runtime_input.verified_feedback,
                keywords=tuple(runtime_input.memory_query.split()),
                positive=runtime_input.verified_feedback.outcome_positive,
            )
            try:
                self.experience_memory.add(record)
                memory_written = True
                emit(
                    TraceEventType.MEMORY,
                    round_index=state.round_index,
                    summary={"write": True, "experience_id": record.experience_id},
                )
            except Exception as exc:
                failures.append(FailureCode.MEMORY_WRITE_FAILURE)
                emit(
                    TraceEventType.FAILURE,
                    round_index=state.round_index,
                    summary={"error_type": type(exc).__name__},
                    failure=FailureCode.MEMORY_WRITE_FAILURE,
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
            final_state=state.model_copy(deep=True),
            trace=tuple(trace),
            budget=BudgetView.from_state(state.budget),
            failures=tuple(failures),
            memory_written=memory_written,
        )
