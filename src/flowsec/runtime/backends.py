from __future__ import annotations

from collections import deque
from typing import Any, Protocol

from .contracts import (
    EvidenceItem,
    EvidenceState,
    SupervisorDecision,
    TrafficExpertResult,
    UnknownDecision,
    UnknownState,
)


class TrafficExpertBackend(Protocol):
    """Provider-neutral traffic expert boundary."""

    def evaluate(
        self,
        evidence: tuple[EvidenceItem, ...],
        previous_state: EvidenceState | None = None,
    ) -> TrafficExpertResult:
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

    def decide(self, state: EvidenceState) -> SupervisorDecision:
        ...


class MockTrafficExpertBackend:
    def __init__(self, responses: list[TrafficExpertResult | Exception]):
        self.responses = deque(responses)
        self.calls: list[tuple[EvidenceItem, ...]] = []

    def evaluate(
        self,
        evidence: tuple[EvidenceItem, ...],
        previous_state: EvidenceState | None = None,
    ) -> TrafficExpertResult:
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

    def __init__(self, *, known_max: float = 0.3, unknown_min: float = 0.7):
        self.known_max = known_max
        self.unknown_min = unknown_min
        self.calls = 0

    def score(
        self,
        result: TrafficExpertResult,
        context: dict[str, Any],
    ) -> UnknownDecision:
        self.calls += 1
        value = float(result.model_signals.get("unknown_score", 0.5))
        if value <= self.known_max:
            state = UnknownState.KNOWN_LIKELY
        elif value >= self.unknown_min:
            state = UnknownState.UNKNOWN_LIKELY
        else:
            state = UnknownState.UNCERTAIN
        return UnknownDecision(score=value, state=state, metadata={"test_only": True})


class MockSupervisorBackend:
    def __init__(self, decisions: list[SupervisorDecision | Exception | object]):
        self.decisions = deque(decisions)
        self.states: list[EvidenceState] = []

    def decide(self, state: EvidenceState) -> SupervisorDecision:
        self.states.append(state.model_copy(deep=True))
        if not self.decisions:
            raise RuntimeError("no mock Supervisor response remains")
        decision = self.decisions.popleft()
        if isinstance(decision, Exception):
            raise decision
        return decision  # type: ignore[return-value]
