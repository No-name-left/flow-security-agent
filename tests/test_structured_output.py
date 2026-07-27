from __future__ import annotations

from typing import Literal

import pytest
from pydantic import BaseModel, ConfigDict, Field

from flowsec.llm.structured_output import (
    JsonExtractionError,
    StructuredOutputValidationError,
    extract_json_value,
    validate_structured_output,
)


class ExampleOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str
    label: Literal["benign", "malicious"]
    confidence: float = Field(ge=0, le=1)


def test_extracts_json_from_thinking_and_mixed_text() -> None:
    text = """
    <think>private reasoning that is not part of the result</think>
    Result:
    ```json
    {"record_id": "flow-1", "label": "malicious", "confidence": 0.8}
    ```
    """
    value = extract_json_value(text)
    assert value["record_id"] == "flow-1"
    parsed = validate_structured_output(text, ExampleOutput)
    assert parsed.label == "malicious"


def test_rejects_invalid_structured_output() -> None:
    with pytest.raises(StructuredOutputValidationError):
        validate_structured_output(
            '{"record_id":"flow-1","label":"unsupported","confidence":2}',
            ExampleOutput,
        )


def test_rejects_multiple_top_level_json_values() -> None:
    with pytest.raises(JsonExtractionError):
        extract_json_value('first {"a": 1} second {"b": 2}')
