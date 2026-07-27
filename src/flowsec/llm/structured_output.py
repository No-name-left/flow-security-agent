from __future__ import annotations

import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError


class JsonExtractionError(ValueError):
    """No unambiguous JSON value could be extracted."""


class StructuredOutputValidationError(ValueError):
    """Extracted JSON did not satisfy the declared schema."""


SchemaT = TypeVar("SchemaT", bound=BaseModel)


def strip_markdown_fence(text: str) -> str:
    cleaned = text.strip()
    full = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if full:
        return full.group(1).strip()
    return cleaned


def strip_thinking_blocks(text: str) -> str:
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    if "</think>" in cleaned.lower():
        cleaned = re.split(r"</think>", cleaned, flags=re.IGNORECASE)[-1]
    return cleaned.strip()


def _embedded_json_values(text: str) -> list[Any]:
    decoder = json.JSONDecoder()
    values: list[Any] = []
    index = 0
    while index < len(text):
        starts = [position for position in (text.find("{", index), text.find("[", index)) if position >= 0]
        if not starts:
            break
        start = min(starts)
        try:
            value, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            index = start + 1
            continue
        values.append(value)
        index = end
    return values


def extract_json_value(text: str, *, require_single: bool = True) -> Any:
    cleaned = strip_markdown_fence(strip_thinking_blocks(text))
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        values = _embedded_json_values(cleaned)
    if not values:
        raise JsonExtractionError("no JSON object or array found in model output")
    if require_single and len(values) != 1:
        raise JsonExtractionError(f"expected one JSON value, found {len(values)}")
    return values[0] if require_single else values


def validate_structured_output(text: str, schema: type[SchemaT]) -> SchemaT:
    value = extract_json_value(text)
    try:
        return schema.model_validate(value)
    except ValidationError as exc:
        raise StructuredOutputValidationError(str(exc)) from exc
