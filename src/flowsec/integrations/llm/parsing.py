from __future__ import annotations

import json
import re
from typing import Any, Protocol

from pydantic import ConfigDict, Field, ValidationError

from flowsec.runtime.contracts import (
    AgentAction,
    EvidenceSufficiency,
    FrozenRuntimeModel,
    MissingEvidence,
    PredictionCandidate,
    SupportingEvidence,
    SupervisorDecision,
    ToolRequest,
    TrafficExpertResult,
)

from .contracts import (
    LLMFailureKind,
    LLMResponseError,
    ParseAudit,
    RawLLMResponse,
    RepairType,
)


FIXTURE_TRAFFIC_EXPERT_SCHEMA_V0 = "SYNTHETIC_TRAFFIC_EXPERT_SCHEMA_V0_EXAMPLE"
FIXTURE_SUPERVISOR_SCHEMA_V0 = "SYNTHETIC_SUPERVISOR_SCHEMA_V0_EXAMPLE"
RAW_SMOKE_TRAFFIC_EXPERT_SCHEMA_V0 = "RAW_SMOKE_TRAFFIC_EXPERT_SCHEMA_V0"


class TrafficExpertResponseParser(Protocol):
    profile_id: str

    def parse(self, response: RawLLMResponse) -> tuple[TrafficExpertResult, ParseAudit]:
        ...


class SupervisorResponseParser(Protocol):
    profile_id: str

    def parse(self, response: RawLLMResponse) -> tuple[SupervisorDecision, ParseAudit]:
        ...


class _FixtureTrafficExpertPayloadV0(FrozenRuntimeModel):
    fine_candidates: tuple[PredictionCandidate, ...]
    coarse_candidates: tuple[PredictionCandidate, ...]
    short_analysis: str = Field(max_length=4000)
    supporting_evidence: tuple[SupportingEvidence, ...]
    missing_evidence: tuple[MissingEvidence, ...]
    evidence_sufficiency: EvidenceSufficiency
    model_signals: dict[str, Any]


class _FixtureSupervisorPayloadV0(FrozenRuntimeModel):
    action: AgentAction
    request_parameters: dict[str, Any] | None = None
    short_reason: str = Field(min_length=1, max_length=1000)
    priority: int | None = None
    expected_value: float | None = Field(default=None, allow_inf_nan=False)


class _DuplicateKeyError(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _json_decoder() -> json.JSONDecoder:
    def reject_non_finite(value: str) -> None:
        raise ValueError(f"non-finite JSON constant: {value}")

    return json.JSONDecoder(
        object_pairs_hook=_unique_object,
        parse_constant=reject_non_finite,
    )


def _ensure_finite_json(value: dict[str, Any]) -> None:
    try:
        json.dumps(value, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise LLMResponseError(
            LLMFailureKind.MALFORMED_RESPONSE,
            "response payload is not finite JSON data",
        ) from exc


def _extract_payload(response: RawLLMResponse) -> tuple[dict[str, Any], ParseAudit]:
    if response.failure is not None:
        raise LLMResponseError(response.failure.kind, response.failure.safe_message)
    if response.finish_status is not None and response.finish_status.casefold() in {
        "length",
        "truncated",
        "max_tokens",
        "incomplete",
    }:
        raise LLMResponseError(LLMFailureKind.TRUNCATED_RESPONSE, "response was truncated")
    if response.structured_payload is not None:
        _ensure_finite_json(response.structured_payload)
        return response.structured_payload, ParseAudit(parser_profile_id="pending")

    text = response.raw_text
    if text is None or not text.strip():
        raise LLMResponseError(LLMFailureKind.EMPTY_RESPONSE, "response body is empty")
    cleaned = text.strip()
    repair_type = RepairType.NONE
    fence = re.fullmatch(
        r"```(?:json)?\s*(.*?)\s*```",
        cleaned,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if fence:
        cleaned = fence.group(1).strip()
        repair_type = RepairType.STRIP_MARKDOWN_FENCE

    decoder = _json_decoder()
    try:
        value = decoder.decode(cleaned)
    except _DuplicateKeyError as exc:
        raise LLMResponseError(LLMFailureKind.MALFORMED_RESPONSE, str(exc)) from exc
    except json.JSONDecodeError:
        values: list[dict[str, Any]] = []
        index = 0
        try:
            while index < len(cleaned):
                start = cleaned.find("{", index)
                if start < 0:
                    break
                try:
                    candidate, end = decoder.raw_decode(cleaned, start)
                except json.JSONDecodeError:
                    index = start + 1
                    continue
                if isinstance(candidate, dict):
                    values.append(candidate)
                index = end
        except (_DuplicateKeyError, ValueError) as exc:
            raise LLMResponseError(LLMFailureKind.MALFORMED_RESPONSE, str(exc)) from exc
        if len(values) != 1:
            raise LLMResponseError(
                LLMFailureKind.MALFORMED_RESPONSE,
                f"expected one unambiguous JSON object, found {len(values)}",
            )
        value = values[0]
        repair_type = RepairType.EXTRACT_UNIQUE_JSON_OBJECT
    except ValueError as exc:
        raise LLMResponseError(LLMFailureKind.MALFORMED_RESPONSE, str(exc)) from exc
    if not isinstance(value, dict):
        raise LLMResponseError(
            LLMFailureKind.SCHEMA_VALIDATION_FAILURE,
            "the response payload must be a JSON object",
            repair_applied=repair_type is not RepairType.NONE,
            repair_type=repair_type,
        )
    _ensure_finite_json(value)
    return value, ParseAudit(
        parser_profile_id="pending",
        repair_applied=repair_type is not RepairType.NONE,
        repair_type=repair_type,
    )


class FixtureTrafficExpertResponseParserV0:
    profile_id = FIXTURE_TRAFFIC_EXPERT_SCHEMA_V0

    def parse(self, response: RawLLMResponse) -> tuple[TrafficExpertResult, ParseAudit]:
        payload, audit = _extract_payload(response)
        try:
            parsed = _FixtureTrafficExpertPayloadV0.model_validate(payload)
            result = TrafficExpertResult(
                **parsed.model_dump(mode="python"),
                metrics=response.usage.to_metrics(),
            )
        except (ValidationError, ValueError, TypeError) as exc:
            raise LLMResponseError(
                LLMFailureKind.SCHEMA_VALIDATION_FAILURE,
                "Traffic Expert response failed the synthetic parser profile",
                repair_applied=audit.repair_applied,
                repair_type=audit.repair_type,
            ) from exc
        return result, audit.model_copy(update={"parser_profile_id": self.profile_id})


class RawSmokeTrafficExpertResponseParserV0(FixtureTrafficExpertResponseParserV0):
    # Deliberately reuses the strict provisional payload shape without freezing it.

    profile_id = RAW_SMOKE_TRAFFIC_EXPERT_SCHEMA_V0


class FixtureSupervisorResponseParserV0:
    profile_id = FIXTURE_SUPERVISOR_SCHEMA_V0

    def parse(self, response: RawLLMResponse) -> tuple[SupervisorDecision, ParseAudit]:
        payload, audit = _extract_payload(response)
        try:
            parsed = _FixtureSupervisorPayloadV0.model_validate(payload)
            request = None
            if parsed.request_parameters is not None:
                request = ToolRequest(
                    action=parsed.action,
                    parameters=parsed.request_parameters,
                )
            result = SupervisorDecision(
                action=parsed.action,
                request=request,
                short_reason=parsed.short_reason,
                priority=parsed.priority,
                expected_value=parsed.expected_value,
                metrics=response.usage.to_metrics(),
            )
        except (ValidationError, ValueError, TypeError) as exc:
            raise LLMResponseError(
                LLMFailureKind.SCHEMA_VALIDATION_FAILURE,
                "Supervisor response failed the synthetic parser profile",
                repair_applied=audit.repair_applied,
                repair_type=audit.repair_type,
            ) from exc
        return result, audit.model_copy(update={"parser_profile_id": self.profile_id})
