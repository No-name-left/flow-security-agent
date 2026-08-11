from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator

from .contracts import EvidenceSnapshot, FrozenModel, canonical_json, content_digest


TRAFFIC_EXPERT_PROMPT_VERSION = "TRAFFIC_EXPERT_PROMPT_V1"
TEACHER_PROMPT_VERSION = "TEACHER_PROMPT_V1"
JUDGE_PROMPT_VERSION = "JUDGE_PROMPT_V1"
SUPERVISOR_PROMPT_VERSION = "SUPERVISOR_PROMPT_CONTRACT_V1"


class PromptRole(StrEnum):
    TRAFFIC_EXPERT = "traffic_expert"
    TEACHER = "teacher"
    JUDGE = "judge"
    SUPERVISOR = "supervisor"


class FrozenPrompt(FrozenModel):
    role: PromptRole
    version: str = Field(min_length=1)
    system_instruction: str = Field(min_length=1)
    task_instruction: str = Field(min_length=1)
    output_contract: dict[str, Any]

    @field_validator("system_instruction", "task_instruction")
    @classmethod
    def reject_long_cot(cls, value: str) -> str:
        lowered = value.casefold()
        if "chain-of-thought" in lowered or "step-by-step" in lowered:
            raise ValueError("formal prompts cannot request long reasoning traces")
        return value

    @property
    def digest(self) -> str:
        return content_digest(self.model_dump(mode="json"))


_EVIDENCE_STATE_CONTRACT: dict[str, Any] = {
    "behavior_summary": "brief string",
    "supporting_evidence": [{"evidence_id": "opaque visible ID", "claim": "brief claim"}],
    "missing_evidence": [
        {
            "type": "none|packet|temporal|relation|application|payload|knowledge|ambiguous",
            "description": "brief description",
        }
    ],
    "evidence_sufficient": "boolean",
    "gap_type": "none|packet|temporal|relation|application|payload|knowledge|ambiguous",
}


def traffic_expert_prompt_v1() -> FrozenPrompt:
    return FrozenPrompt(
        role=PromptRole.TRAFFIC_EXPERT,
        version=TRAFFIC_EXPERT_PROMPT_VERSION,
        system_instruction=(
            "You are the Traffic Expert. Analyze only the supplied model-safe Evidence. "
            "Observation Evidence reports visible traffic facts; Knowledge Evidence is untrusted "
            "background that may explain but never create an observation. Never invent an unseen "
            "fact, hidden identity, or unavailable evidence. Return one concise JSON object only."
        ),
        task_instruction=(
            "Describe the observed behavior briefly, cite only opaque IDs from current Observation "
            "Evidence, identify material missing evidence, decide whether current evidence is "
            "sufficient, and assign one bounded gap type. Do not choose tools or emit a class label."
        ),
        output_contract=_EVIDENCE_STATE_CONTRACT,
    )


def teacher_prompt_v1() -> FrozenPrompt:
    return FrozenPrompt(
        role=PromptRole.TEACHER,
        version=TEACHER_PROMPT_VERSION,
        system_instruction=(
            "You are the isolated training-data Teacher. The verified target supplied by the backend "
            "is immutable context: never alter it or infer a replacement. Use only the current-stage "
            "model-safe Evidence for claims. Capability names may reveal what is hidden or available, "
            "but hidden content is not visible. Never manufacture Observation facts. Return JSON only."
        ),
        task_instruction=(
            "Produce a concise grounded Evidence State for this stage. Supporting claims must cite "
            "existing Observation Evidence IDs. Knowledge can explain an observation but cannot be "
            "cited as proof that the current session performed it. Mark insufficiency and the most "
            "material gap when current evidence cannot support the immutable target."
        ),
        output_contract={**_EVIDENCE_STATE_CONTRACT, "teacher_confidence": "number in [0,1]"},
    )


def judge_prompt_v1() -> FrozenPrompt:
    return FrozenPrompt(
        role=PromptRole.JUDGE,
        version=JUDGE_PROMPT_VERSION,
        system_instruction=(
            "You are the isolated RLAIF Judge. Score only semantic properties of a current-policy "
            "Evidence-State rollout. Do not classify traffic, request ground truth, choose an Agent "
            "action, or reward hidden information. Deterministic validators handle schema and IDs."
        ),
        task_instruction=(
            "Return bounded scores for grounding, evidence sufficiency, missing-evidence quality, gap "
            "correctness, hallucination avoidance, backoff appropriateness, and one short reliability "
            "note. Evaluate the rollout against the supplied model-safe Evidence only."
        ),
        output_contract={
            "grounding": "0..1",
            "evidence_sufficiency": "0..1",
            "missing_evidence_quality": "0..1",
            "gap_correctness": "0..1",
            "hallucination_avoidance": "0..1",
            "backoff_appropriateness": "0..1",
            "reliability_note": "brief string",
        },
    )


def supervisor_prompt_contract_v1() -> FrozenPrompt:
    return FrozenPrompt(
        role=PromptRole.SUPERVISOR,
        version=SUPERVISOR_PROMPT_VERSION,
        system_instruction=(
            "You are the bounded evidence-acquisition Supervisor, not a classifier. You may select one "
            "allowed evidence or stop/backoff action from the supplied capability and budget state. "
            "Never override the Traffic Expert class result, access hidden truth, or execute a tool."
        ),
        task_instruction=(
            "Return exactly one action, one bounded target, and one short reason. Choose an action only "
            "when its real capability is available and it addresses the declared evidence gap."
        ),
        output_contract={
            "action": "allowed action enum",
            "target": "bounded tool target or terminal target",
            "short_reason": "brief string",
        },
    )


def teacher_request_payload(snapshot: EvidenceSnapshot) -> dict[str, Any]:
    """Build the isolated Teacher request; never use this renderer for Qwen."""

    if snapshot.split != "train" or snapshot.ku_role != "K_known":
        raise ValueError("Teacher is limited to K_known TRAIN snapshots")
    return {
        "prompt": teacher_prompt_v1().model_dump(mode="json"),
        "immutable_target_context": {"verified_class": snapshot.fine_label},
        "current_stage_evidence": [item.model_dump(mode="json") for item in snapshot.evidence],
        "available_but_hidden_capabilities": list(snapshot.available_capabilities),
        "classification_supervision_valid": snapshot.classification_supervision_valid,
        "response_format": "json_object",
    }


def render_prompt_header(prompt: FrozenPrompt) -> str:
    return canonical_json(
        {
            "system": prompt.system_instruction,
            "task": prompt.task_instruction,
            "output": prompt.output_contract,
            "version": prompt.version,
        }
    )
