from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import Field, field_validator

from flowsec.runtime.contracts import (
    AgentAction,
    EvidenceItem,
    FrozenRuntimeModel,
    SupervisorView,
    validate_model_visible_value,
)

from .contracts import (
    ContentKind,
    LLMMessage,
    MessageContent,
    MessageRole,
    PromptIdentity,
)


FIXTURE_RENDERER_VERSION = "SYNTHETIC_FIXTURE_RENDERER_V0"
FIXTURE_TRAFFIC_EXPERT_PROMPT_V0 = "FIXTURE_TRAFFIC_EXPERT_PROMPT_V0"
FIXTURE_SUPERVISOR_PROMPT_V0 = "FIXTURE_SUPERVISOR_PROMPT_V0"


class PromptProfile(FrozenRuntimeModel):
    """Replaceable prompt fixture; the current text is not a research prompt."""

    prompt_id: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    renderer_version: str = Field(min_length=1)
    system_instruction: str = Field(min_length=1, repr=False)
    task_instruction: str = Field(min_length=1, repr=False)

    @field_validator("system_instruction", "task_instruction")
    @classmethod
    def validate_instruction(cls, value: str) -> str:
        validate_model_visible_value(value, location="fixture_prompt")
        return value

    @property
    def identity(self) -> PromptIdentity:
        payload = json.dumps(
            {
                "prompt_id": self.prompt_id,
                "prompt_version": self.prompt_version,
                "renderer_version": self.renderer_version,
                "system_instruction": self.system_instruction,
                "task_instruction": self.task_instruction,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return PromptIdentity(
            prompt_id=self.prompt_id,
            prompt_version=self.prompt_version,
            prompt_hash=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            renderer_version=self.renderer_version,
        )


class ToolSpecification(FrozenRuntimeModel):
    allowed_actions: tuple[AgentAction, ...]
    parameter_contracts: dict[str, Any] = Field(default_factory=dict)

    @field_validator("parameter_contracts")
    @classmethod
    def validate_contracts(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_model_visible_value(value, location="tool_specification")
        try:
            json.dumps(value, sort_keys=True, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("tool specifications must be finite JSON data") from exc
        return value


def fixture_traffic_expert_prompt() -> PromptProfile:
    return PromptProfile(
        prompt_id=FIXTURE_TRAFFIC_EXPERT_PROMPT_V0,
        prompt_version="V0_EXAMPLE",
        renderer_version=FIXTURE_RENDERER_VERSION,
        system_instruction=(
            "Synthetic test instruction: analyze only the delimited evidence data and return "
            "one fixture-compatible structured response."
        ),
        task_instruction=(
            "Produce candidate classes, a short analysis, supporting and missing evidence, "
            "evidence sufficiency, and opaque model signals."
        ),
    )


def fixture_supervisor_prompt() -> PromptProfile:
    return PromptProfile(
        prompt_id=FIXTURE_SUPERVISOR_PROMPT_V0,
        prompt_version="V0_EXAMPLE",
        renderer_version=FIXTURE_RENDERER_VERSION,
        system_instruction=(
            "Synthetic test instruction: propose exactly one allowed action; do not execute tools, "
            "create a class, write memory, or alter the runtime state."
        ),
        task_instruction=(
            "Use the state data and tool specification to return one action and a short reason."
        ),
    )


def _json_data(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _evidence_block(item: EvidenceItem) -> MessageContent:
    return MessageContent(
        kind=ContentKind.DATA,
        trust=item.trust,
        label=f"evidence:{item.evidence_id}",
        content=_json_data(item.model_dump(mode="json")),
    )


class TrafficExpertPromptRenderer:
    def __init__(self, profile: PromptProfile):
        self.profile = profile

    @property
    def identity(self) -> PromptIdentity:
        return self.profile.identity

    def render(self, evidence: tuple[EvidenceItem, ...]) -> tuple[LLMMessage, ...]:
        messages = (
            LLMMessage(
                role=MessageRole.SYSTEM,
                content=(
                    MessageContent(
                        kind=ContentKind.INSTRUCTION,
                        label="system_instruction",
                        content=self.profile.system_instruction,
                    ),
                ),
            ),
            LLMMessage(
                role=MessageRole.USER,
                content=(
                    MessageContent(
                        kind=ContentKind.INSTRUCTION,
                        label="task_instruction",
                        content=self.profile.task_instruction,
                    ),
                    *(_evidence_block(item) for item in evidence),
                ),
            ),
        )
        return tuple(message.model_copy(deep=True) for message in messages)


class SupervisorPromptRenderer:
    def __init__(self, profile: PromptProfile, tool_specification: ToolSpecification):
        self.profile = profile
        self.tool_specification = tool_specification

    @property
    def identity(self) -> PromptIdentity:
        return self.profile.identity

    def render(self, state: SupervisorView) -> tuple[LLMMessage, ...]:
        state_payload = state.model_dump(mode="json", exclude={"evidence"})
        tool_payload = {
            "allowed_actions": [item.value for item in self.tool_specification.allowed_actions],
            "parameter_contracts": self.tool_specification.parameter_contracts,
        }
        user_parts = [
            MessageContent(
                kind=ContentKind.INSTRUCTION,
                label="task_instruction",
                content=self.profile.task_instruction,
            ),
            MessageContent(
                kind=ContentKind.INSTRUCTION,
                label="tool_specification",
                content=_json_data(tool_payload),
            ),
            MessageContent(
                kind=ContentKind.DATA,
                label="supervisor_state",
                content=_json_data(state_payload),
            ),
        ]
        user_parts.extend(_evidence_block(item) for item in state.evidence)
        return (
            LLMMessage(
                role=MessageRole.SYSTEM,
                content=(
                    MessageContent(
                        kind=ContentKind.INSTRUCTION,
                        label="system_instruction",
                        content=self.profile.system_instruction,
                    ),
                ),
            ),
            LLMMessage(role=MessageRole.USER, content=tuple(user_parts)),
        )


def render_messages_as_tagged_text(messages: tuple[LLMMessage, ...]) -> tuple[dict[str, str], ...]:
    """Provider adapter helper that preserves instruction/data delimiters in text APIs."""

    rendered: list[dict[str, str]] = []
    for message in messages:
        parts: list[str] = []
        for part in message.content:
            if part.kind is ContentKind.INSTRUCTION:
                parts.append(f"<INSTRUCTION name={json.dumps(part.label)}>\n{part.content}\n</INSTRUCTION>")
            else:
                trust = part.trust.value if part.trust is not None else "data"
                parts.append(
                    f"<DATA name={json.dumps(part.label)} trust={json.dumps(trust)}>\n"
                    f"{part.content}\n</DATA>"
                )
        rendered.append({"role": message.role.value, "content": "\n".join(parts)})
    return tuple(rendered)
