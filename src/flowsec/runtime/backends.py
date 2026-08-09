from __future__ import annotations

from collections import deque
from typing import Any, Protocol

from .contracts import (
    CallMetrics,
    EvidenceItem,
    SupervisorDecision,
    SupervisorView,
    TrafficExpertResult,
    UnknownDecision,
    UnknownState,
)


class TrafficExpertBackend(Protocol):
    """Provider-neutral traffic expert boundary."""

    def estimate(self, evidence: tuple[EvidenceItem, ...]) -> CallMetrics:
        ...

    def evaluate(self, evidence: tuple[EvidenceItem, ...]) -> TrafficExpertResult:
        ...


class UnknownScorer(Protocol):
    """Independent unknown-scoring boundary; the final algorithm is deferred."""

    def score(
        self,
        result: TrafficExpertResult,
        context: dict[str, Any],
    ) -> UnknownDecision:
        ...


class SupervisorBackend(Protocol):
    """Policy backend that proposes, but never executes, a runtime action."""

    def estimate(self, state: SupervisorView) -> CallMetrics:
        ...

    def decide(self, state: SupervisorView) -> SupervisorDecision:
        ...


class MockTrafficExpertBackend:
    def __init__(
        self,
        responses: list[TrafficExpertResult | Exception],
        *,
        estimate_metrics: CallMetrics | None = None,
    ):
        self.responses = deque(responses)
        self.calls: list[tuple[EvidenceItem, ...]] = []
        self.estimate_metrics = estimate_metrics or CallMetrics()

    def estimate(self, evidence: tuple[EvidenceItem, ...]) -> CallMetrics:
        return self.estimate_metrics

    def evaluate(self, evidence: tuple[EvidenceItem, ...]) -> TrafficExpertResult:
        self.calls.append(evidence)
        if not self.responses:
            raise RuntimeError("no mock Traffic Expert response remains")
        response = self.responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response


class MockUnknownScorer:
    def __init__(self, responses: list[UnknownDecision | Exception]):
        self.responses = deque(responses)
        self.calls: list[TrafficExpertResult] = []

    def score(
        self,
        result: TrafficExpertResult,
        context: dict[str, Any],
    ) -> UnknownDecision:
        self.calls.append(result)
        if not self.responses:
            raise RuntimeError("no mock Unknown Scorer response remains")
        response = self.responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response


class DeterministicTestUnknownScorer:
    """Test-only scorer over an opaque signal; not a scientific algorithm choice."""

    def __init__(self, *, known_max: float, unknown_min: float):
        self.known_max = known_max
        self.unknown_min = unknown_min
        self.calls = 0

    def score(
        self,
        result: TrafficExpertResult,
        context: dict[str, Any],
    ) -> UnknownDecision:
        self.calls += 1
        value = float(result.model_signals.get("synthetic_open_set_signal", 0.5))
        if value <= self.known_max:
            state = UnknownState.KNOWN_LIKELY
        elif value >= self.unknown_min:
            state = UnknownState.UNKNOWN_LIKELY
        else:
            state = UnknownState.UNCERTAIN
        return UnknownDecision(score=value, state=state, metadata={"test_only": True})


class MockSupervisorBackend:
    def __init__(
        self,
        decisions: list[SupervisorDecision | Exception | object],
        *,
        estimate_metrics: CallMetrics | None = None,
    ):
        self.decisions = deque(decisions)
        self.states: list[SupervisorView] = []
        self.estimate_metrics = estimate_metrics or CallMetrics()

    def estimate(self, state: SupervisorView) -> CallMetrics:
        return self.estimate_metrics

    def decide(self, state: SupervisorView) -> SupervisorDecision:
        self.states.append(state.model_copy(deep=True))
        if not self.decisions:
            raise RuntimeError("no mock Supervisor response remains")
        decision = self.decisions.popleft()
        if isinstance(decision, Exception):
            raise decision
        return decision  # type: ignore[return-value]
