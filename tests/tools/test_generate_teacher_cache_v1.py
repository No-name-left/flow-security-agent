"""Targeted tests for the teacher_cache_v1 generation tool (pure functions only, no network)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import generate_teacher_cache_v1 as g  # noqa: E402
from flowsec.integrations.llm.contracts import (  # noqa: E402
    LLMFailureKind,
    RawLLMResponse,
    RawUsage,
)
from flowsec.integrations.llm.transport import FakeFailure, FakeLLMTransport  # noqa: E402

TEACHER_DIR = Path("/root/autodl-tmp/processed/dataset_v4_nf3_ton_v1/teacher")


def _payload(classes: list[str] | None = None) -> dict:
    classes = classes or list(g.CANONICAL_TAXONOMY_V1)
    return {
        "available_next_evidence": ["TEMPORAL", "RELATION"],
        "known_prediction_summary": {
            "class_map_version": "CANONICAL_TAXONOMY_V1",
            "known_class_probabilities": {name: 1.0 / len(classes) for name in classes},
            "predicted_class": classes[0],
        },
    }


def test_tolerant_extract_json_variants():
    assert g.tolerant_extract_json('{"a": 1}') == {"a": 1}
    assert g.tolerant_extract_json('```json\n{"b": 2}\n```') == {"b": 2}
    assert g.tolerant_extract_json('noise before {"c": 3} tail') == {"c": 3}
    assert g.tolerant_extract_json("no json here at all") is None
    assert g.tolerant_extract_json("") is None


def test_validate_teacher_response_accepts_valid_stop():
    response = {
        "predicted_class": "DDoS",
        "recommended_action": "STOP_AND_CLASSIFY",
        "confidence": 0.9,
        "semantic_gap": "NONE",
        "short_reason": "basic supports it",
    }
    assert g.validate_teacher_response(response, _payload()) is None


@pytest.mark.parametrize(
    "patch",
    [
        {"semantic_gap": "AMBIGUOUS"},  # STOP requires NONE
        {"predicted_class": None},  # STOP requires a known class
        {"confidence": 1.5},  # out of range
        {"confidence": "high"},  # not a number
        {"recommended_action": "STOP"},  # not in the frozen vocabulary
        {"semantic_gap": "NONE", "recommended_action": "ACQUIRE_TEMPORAL",
         "available_none": None},  # unknown extra key rejected below
    ],
)
def test_validate_teacher_response_rejects_invalid(patch):
    response = {
        "predicted_class": "DDoS",
        "recommended_action": "STOP_AND_CLASSIFY",
        "confidence": 0.9,
        "semantic_gap": "NONE",
        "short_reason": "x",
    }
    if "available_none" in patch:
        patch.pop("available_none")
        response["extra_key"] = True
    response.update(patch)
    assert g.validate_teacher_response(response, _payload()) is not None


def test_validate_teacher_response_rotation_map():
    payload = _payload(classes=["Backdoor", "Benign", "Credential", "DDoS", "DoS",
                                "Web_Injection"])
    response = {
        "predicted_class": "Recon_Scanning",
        "recommended_action": "STOP_AND_CLASSIFY",
        "confidence": 0.9,
        "semantic_gap": "NONE",
        "short_reason": "x",
    }
    # Recon_Scanning is held out of this rotation map and must be rejected.
    assert g.validate_teacher_response(response, payload) is not None
    response["predicted_class"] = "DDoS"
    assert g.validate_teacher_response(response, payload) is None


def test_validate_teacher_response_acquire_availability():
    payload = _payload()
    payload["available_next_evidence"] = ["RELATION"]
    response = {
        "predicted_class": None,
        "recommended_action": "ACQUIRE_TEMPORAL",
        "confidence": 0.7,
        "semantic_gap": "NEEDS_TEMPORAL",
        "short_reason": "x",
    }
    assert g.validate_teacher_response(response, payload) is not None
    response["recommended_action"] = "ACQUIRE_RELATION"
    response["semantic_gap"] = "NEEDS_RELATION"
    assert g.validate_teacher_response(response, payload) is None


def test_validate_semantic_response():
    good = {"semantic_relevance": "SUPPORTIVE", "allowed_claim": "a",
            "forbidden_claim": "b", "short_reason": "c"}
    assert g.validate_semantic_response(good) is None
    assert g.validate_semantic_response({**good, "semantic_relevance": "HIGH"}) is not None
    assert g.validate_semantic_response({**good, "short_reason": ""}) is not None
    assert g.validate_semantic_response({**good, "extra": 1}) is not None


def test_prompt_spec_sha256_stable():
    first = g.prompt_spec_sha256(
        prompt_id=g.TEACHER_PROMPT_ID,
        prompt_version=g.TEACHER_PROMPT_VERSION,
        renderer_version=g.TEACHER_RENDERER_VERSION,
        system_instruction=g.TEACHER_SYSTEM_INSTRUCTION,
        task_template=g.TEACHER_TASK_TEMPLATE,
        response_schema=g.TEACHER_RESPONSE_SCHEMA,
        model_id="deepseek-v4-flash",
    )
    second = g.prompt_spec_sha256(
        prompt_id=g.TEACHER_PROMPT_ID,
        prompt_version=g.TEACHER_PROMPT_VERSION,
        renderer_version=g.TEACHER_RENDERER_VERSION,
        system_instruction=g.TEACHER_SYSTEM_INSTRUCTION,
        task_template=g.TEACHER_TASK_TEMPLATE,
        response_schema=g.TEACHER_RESPONSE_SCHEMA,
        model_id="deepseek-v4-flash",
    )
    assert first == second and len(first) == 64
    changed = g.prompt_spec_sha256(
        prompt_id=g.TEACHER_PROMPT_ID,
        prompt_version=g.TEACHER_PROMPT_VERSION,
        renderer_version=g.TEACHER_RENDERER_VERSION,
        system_instruction=g.TEACHER_SYSTEM_INSTRUCTION + " changed",
        task_template=g.TEACHER_TASK_TEMPLATE,
        response_schema=g.TEACHER_RESPONSE_SCHEMA,
        model_id="deepseek-v4-flash",
    )
    assert changed != first


def test_teacher_leakage_precheck_real_manifest():
    requests, offline = g._load_teacher_inputs(str(TEACHER_DIR))
    assert g.teacher_leakage_precheck(requests, offline) is True
    # injecting GT into a payload must be rejected
    first_id = sorted(requests)[0]
    tampered = json.loads(json.dumps(requests))
    tampered[first_id]["teacher_request_payload"]["canonical_label"] = "DDoS"
    with pytest.raises(ValueError):
        g.teacher_leakage_precheck(tampered, offline)
    # rotation probability maps must match the offline rotation role
    rotation_rows = {
        key: value for key, value in requests.items()
        if offline[key].get("unknown_rotation_if_any")
    }
    assert len(rotation_rows) == 400


def test_generate_one_retry_bounds(monkeypatch):
    monkeypatch.setattr(g, "TRANSPORT_RETRY_DELAYS", (0.0, 0.0))
    events = [
        FakeFailure(LLMFailureKind.TIMEOUT, "timeout"),
        FakeFailure(LLMFailureKind.TIMEOUT, "timeout"),
        FakeFailure(LLMFailureKind.TIMEOUT, "timeout"),
    ]
    transport = FakeLLMTransport(
        profile=None, events=events,
        estimate_metrics=__import__("flowsec.runtime.contracts", fromlist=["CallMetrics"]).CallMetrics(
            abstract_tokens=100, abstract_latency=1.0),
        secret_values=(),
    )
    transport.profile = None  # unused: events are failures/RawLLMResponse only
    counters = g.GenerationCounters()
    result = g.generate_one(
        logical_id="x", payload=_payload(), payload_hash="h", offline=None,
        transport=transport,
        config={"model_id": "deepseek-v4-flash", "base_url": "https://api.deepseek.com",
                "api_key": "k"},
        prompt_id=g.TEACHER_PROMPT_ID, prompt_version=g.TEACHER_PROMPT_VERSION,
        prompt_sha256="a" * 64, renderer_version=g.TEACHER_RENDERER_VERSION,
        task="teacher_cache_v1", validator=g.validate_teacher_response,
        counters=counters, total_cap=2150,
    )
    # 1 initial + 2 transport retries = 3 attempts, then API_FAILURE
    assert result["validation_status"] == "API_FAILURE"
    assert result["attempts"] == 3
    assert result["retry_count"] == 2


def test_generate_one_valid_response(monkeypatch):
    monkeypatch.setattr(g, "TRANSPORT_RETRY_DELAYS", (0.0, 0.0))
    good_text = json.dumps({
        "predicted_class": "DDoS", "recommended_action": "STOP_AND_CLASSIFY",
        "confidence": 0.9, "semantic_gap": "NONE", "short_reason": "x",
    })
    response = RawLLMResponse(
        provider="deepseek", model_id="deepseek-v4-flash", raw_text=good_text,
        usage=RawUsage(input_tokens=12, output_tokens=8, total_tokens=20),
    )
    transport = FakeLLMTransport(
        profile=None, events=[response],
        estimate_metrics=__import__("flowsec.runtime.contracts", fromlist=["CallMetrics"]).CallMetrics(
            abstract_tokens=100, abstract_latency=1.0),
        secret_values=(),
    )
    counters = g.GenerationCounters()
    result = g.generate_one(
        logical_id="y", payload=_payload(), payload_hash="h", offline=None,
        transport=transport,
        config={"model_id": "deepseek-v4-flash", "base_url": "https://api.deepseek.com",
                "api_key": "k"},
        prompt_id=g.TEACHER_PROMPT_ID, prompt_version=g.TEACHER_PROMPT_VERSION,
        prompt_sha256="b" * 64, renderer_version=g.TEACHER_RENDERER_VERSION,
        task="teacher_cache_v1", validator=g.validate_teacher_response,
        counters=counters, total_cap=2150,
    )
    assert result["validation_status"] == "VALID"
    assert result["attempts"] == 1
    assert counters.input_tokens == 12
    assert counters.output_tokens == 8
