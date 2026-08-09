from __future__ import annotations

import pytest

from flowsec.runtime.backends import MockSupervisorBackend
from flowsec.runtime.contracts import (
    AgentAction,
    ClassMemoryRecord,
    ExperienceRecord,
    FeedbackSource,
    FailureCode,
    RuntimePhase,
    VerifiedFeedback,
)
from flowsec.runtime.memory import InMemoryClassMemory, InMemoryExperienceStore

from ._helpers import decision, expert_result, runtime, runtime_input


def record(*, verified: bool = True, positive: bool = True) -> ExperienceRecord:
    return ExperienceRecord(
        experience_id=f"experience-{verified}-{positive}",
        state_summary="packet gap",
        action=AgentAction.EXPAND_PACKETS,
        outcome="worked" if positive else "failed",
        feedback=VerifiedFeedback(
            verified=verified,
            source=FeedbackSource.HUMAN_LABEL,
            summary="checked",
            outcome_positive=positive,
        ),
        keywords=("packet",),
        positive=positive,
    )


def test_experience_store_retrieval_is_deterministic() -> None:
    store = InMemoryExperienceStore([record(), record(positive=False)])
    retrieved = store.retrieve("packet", limit=1)
    assert retrieved[0].experience_id == "experience-True-True"


def test_unverified_experience_cannot_be_stored() -> None:
    store = InMemoryExperienceStore()
    with pytest.raises(ValueError, match="unverified"):
        store.add(record(verified=False))


def test_unverified_experience_cannot_preload_memory() -> None:
    with pytest.raises(ValueError, match="unverified"):
        InMemoryExperienceStore([record(verified=False)])


def test_negative_experience_can_be_stored() -> None:
    store = InMemoryExperienceStore()
    store.add(record(positive=False))
    assert store.records[0].positive is False


def test_experience_and_class_memory_are_isolated() -> None:
    experiences = InMemoryExperienceStore([record()])
    classes = InMemoryClassMemory()
    classes.add(ClassMemoryRecord(class_id="new-1", label="new attack"))
    assert classes.get("new-1") is not None
    assert len(experiences.records) == 1
    assert not hasattr(classes, "retrieve")


@pytest.mark.parametrize(
    "phase",
    [RuntimePhase.VALIDATION, RuntimePhase.U_DEV, RuntimePhase.TEST, RuntimePhase.U_FINAL],
)
def test_non_train_phases_are_memory_read_only(phase: RuntimePhase) -> None:
    store = InMemoryExperienceStore()
    supervisor = MockSupervisorBackend([decision(AgentAction.ACCEPT_FINE)])
    orchestrator, _, _ = runtime([expert_result()], supervisor, experience_memory=store)
    result = orchestrator.run(
        runtime_input(
            phase=phase,
            verified_feedback=VerifiedFeedback(
                verified=True,
                source=FeedbackSource.HUMAN_LABEL,
                summary="right",
                outcome_positive=True,
            ),
        )
    )
    assert result.memory_written is False
    assert store.records == []


def test_train_verified_feedback_allows_memory_write() -> None:
    store = InMemoryExperienceStore()
    supervisor = MockSupervisorBackend([decision(AgentAction.ACCEPT_FINE)])
    orchestrator, _, _ = runtime([expert_result()], supervisor, experience_memory=store)
    result = orchestrator.run(
        runtime_input(
            phase=RuntimePhase.TRAIN,
            verified_feedback=VerifiedFeedback(
                verified=True,
                source=FeedbackSource.HUMAN_LABEL,
                summary="right",
                outcome_positive=True,
            ),
        )
    )
    assert result.memory_written is True
    assert len(store.records) == 1


def test_train_unverified_feedback_denies_memory_write() -> None:
    store = InMemoryExperienceStore()
    supervisor = MockSupervisorBackend([decision(AgentAction.ACCEPT_FINE)])
    orchestrator, _, _ = runtime([expert_result()], supervisor, experience_memory=store)
    result = orchestrator.run(
        runtime_input(
            phase=RuntimePhase.TRAIN,
            verified_feedback=VerifiedFeedback(
                verified=False,
                source=FeedbackSource.VERIFIED_TOOL,
                summary="unverified fixture",
                outcome_positive=False,
            ),
        )
    )
    assert result.memory_written is False
    assert store.records == []


def test_train_verified_negative_feedback_writes_negative_experience() -> None:
    store = InMemoryExperienceStore()
    supervisor = MockSupervisorBackend([decision(AgentAction.ACCEPT_FINE)])
    orchestrator, _, _ = runtime([expert_result()], supervisor, experience_memory=store)
    result = orchestrator.run(
        runtime_input(
            phase=RuntimePhase.TRAIN,
            verified_feedback=VerifiedFeedback(
                verified=True,
                source=FeedbackSource.GROUND_TRUTH,
                summary="prediction was incorrect",
                outcome_positive=False,
            ),
        )
    )
    assert result.memory_written is True
    assert store.records[0].positive is False


def test_memory_write_failure_does_not_destroy_final_decision() -> None:
    class FailingMemory(InMemoryExperienceStore):
        def add(self, item: ExperienceRecord) -> None:
            raise RuntimeError("fixture write failure")

    store = FailingMemory()
    supervisor = MockSupervisorBackend([decision(AgentAction.ACCEPT_FINE)])
    orchestrator, _, _ = runtime([expert_result()], supervisor, experience_memory=store)
    result = orchestrator.run(
        runtime_input(
            phase=RuntimePhase.TRAIN,
            verified_feedback=VerifiedFeedback(
                verified=True,
                source=FeedbackSource.HUMAN_LABEL,
                summary="checked",
                outcome_positive=True,
            ),
        )
    )
    assert result.final_decision.decision_type.value == "fine"
    assert result.memory_written is False
    assert FailureCode.MEMORY_WRITE_FAILURE in result.failures


def test_retrieved_experience_reaches_supervisor_state() -> None:
    store = InMemoryExperienceStore([record()])
    supervisor = MockSupervisorBackend([decision(AgentAction.ACCEPT_FINE)])
    orchestrator, _, _ = runtime([expert_result()], supervisor, experience_memory=store)
    orchestrator.run(runtime_input(memory_query="packet"))
    assert supervisor.states[0].retrieved_experiences[0].experience_id == "experience-True-True"
