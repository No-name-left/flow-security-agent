#!/usr/bin/env python3
"""Real local-vLLM smoke through the typed Traffic Expert and Production Adapter boundaries."""

from __future__ import annotations

import argparse
import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

import httpx
from openai import OpenAI

from flowsec.integrations.llm.adapters import LLMTrafficExpertBackend
from flowsec.integrations.llm.contracts import LLMBackendConfig, ResponseMode, RetryPolicy
from flowsec.integrations.llm.parsing import RawSmokeTrafficExpertResponseParserV0
from flowsec.integrations.llm.prompting import TrafficExpertPromptRenderer, raw_smoke_traffic_expert_prompt, render_messages_as_tagged_text
from flowsec.integrations.llm.transport import OpenAICompatibleChatTransport
from flowsec.production.runtime_adapter import ProductionPacketExpansionTool, ProductionParquetEvidenceStore, ProductionSafeAdapter, ProductionSampleRequest, ProductionTemporalContextTool
from flowsec.runtime.contracts import AgentAction, EvidenceItem, GapDomain, GapType, RuntimePhase, ToolRequest, ToolStatus


MODEL_ID = "Qwen/Qwen3.5-9B"
CLASS_SAMPLES = {
    "Normal": "fs1_7374c279f7cd884e1be73f9e08e65191a24c13d4",
    "DDoS_TCP": "fs1_8633c2a117f328502b7583b2c2f5ce539d2c0fef",
    "Port_Scanning": "fs1_3f80712341f43d2e64dd81bcaf54e83f557e2eb1",
    "SQL_injection": "fs1_9e240e26cfbd7fab3343911f89c38d87b22eb409",
    "Backdoor": "fs1_9a1bb97f1b972213939c20c746e810d128d5ec33",
    "MITM": "fs1_b8726027cf36304449de416c85246a0590c92182",
}
HAS_PAST_SAMPLE = "fs1_c30c9ed71429e81384477f652064609f9bf43ff5"
T = TypeVar("T")


def _gpu_memory_mib() -> int:
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        check=True,
        capture_output=True,
        text=True,
    )
    return sum(int(line.strip()) for line in result.stdout.splitlines() if line.strip())


def _profile(call: Callable[[], T]) -> tuple[T, dict[str, Any]]:
    observations = [_gpu_memory_mib()]
    stop = threading.Event()

    def poll() -> None:
        while not stop.wait(0.05):
            try:
                observations.append(_gpu_memory_mib())
            except (OSError, subprocess.SubprocessError, ValueError):
                pass

    thread = threading.Thread(target=poll, daemon=True)
    thread.start()
    started = time.perf_counter()
    try:
        value = call()
    finally:
        elapsed = time.perf_counter() - started
        stop.set()
        thread.join(timeout=1.0)
        observations.append(_gpu_memory_mib())
    return value, {
        "latency_seconds": elapsed,
        "gpu_memory_before_mib": observations[0],
        "gpu_memory_after_mib": observations[-1],
        "gpu_memory_observed_peak_mib": max(observations),
    }


def _request(sample_id: str) -> ProductionSampleRequest:
    return ProductionSampleRequest(
        sample_id=sample_id,
        dataset="Edge-IIoTset",
        split="train",
        phase=RuntimePhase.TRAIN,
        preset="Near",
    )


def _result_projection(result: Any) -> dict[str, Any]:
    return {
        "fine_candidates": [item.model_dump(mode="json") for item in result.fine_candidates],
        "coarse_candidates": [item.model_dump(mode="json") for item in result.coarse_candidates],
        "evidence_sufficiency": result.evidence_sufficiency.value,
        "supporting_evidence_count": len(result.supporting_evidence),
        "missing_evidence_count": len(result.missing_evidence),
        "parse_status": "PASS",
    }


def _build_backend(base_url: str, timeout: float) -> tuple[LLMTrafficExpertBackend, OpenAICompatibleChatTransport, TrafficExpertPromptRenderer]:
    profile = raw_smoke_traffic_expert_prompt()
    renderer = TrafficExpertPromptRenderer(profile)
    transport = OpenAICompatibleChatTransport(
        api_key="EMPTY",
        max_input_tokens=7424,
        max_output_tokens=768,
        max_latency_seconds=timeout,
        trust_env=False,
    )
    config = LLMBackendConfig(
        provider="local_vllm",
        base_url=base_url,
        model_id=MODEL_ID,
        timeout_seconds=timeout,
        retry_policy=RetryPolicy(max_attempts=1, retryable_failures=frozenset()),
        response_mode=ResponseMode.TEXT,
        generation_options={
            "temperature": 0.0,
            "seed": 7,
            "max_tokens": 768,
            "response_format": {"type": "json_object"},
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
        },
        prompt_profile_id=profile.prompt_id,
        request_metadata={"purpose": "raw_smoke_only"},
    )
    backend = LLMTrafficExpertBackend(
        transport=transport,
        config=config,
        renderer=renderer,
        parser=RawSmokeTrafficExpertResponseParserV0(),
    )
    return backend, transport, renderer


def _call_backend(backend: LLMTrafficExpertBackend, transport: OpenAICompatibleChatTransport, evidence: tuple[EvidenceItem, ...]) -> dict[str, Any]:
    result, resources = _profile(lambda: backend.evaluate(evidence))
    return {
        "result": _result_projection(result),
        "provider": dict(transport.last_response_metadata),
        "resources": resources,
        "repair_type": backend.last_call_audit.attempts[-1].repair_type.value if backend.last_call_audit else None,
    }


def _assert_no_backend_leakage(renderer: TrafficExpertPromptRenderer, evidence: tuple[EvidenceItem, ...], prohibited: tuple[str, ...]) -> None:
    payload = json.dumps(render_messages_as_tagged_text(renderer.render(evidence)), sort_keys=True)
    leaked = [value for value in prohibited if value and value in payload]
    if leaked:
        raise RuntimeError("backend-only value appeared in the model request")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--production-root", type=Path, default=Path("/root/autodl-tmp/processed/edge_split_revision_v2"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()
    started = time.time()
    payload: dict[str, Any] = {
        "schema_version": "qwen35_9b_real_runtime_smoke_v1",
        "model_id": MODEL_ID,
        "base_url": args.base_url,
        "temperature": 0.0,
        "seed": 7,
        "thinking_enabled": False,
        "max_model_len": 8192,
        "sft_run": False,
        "rl_run": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        client = OpenAI(
            base_url=args.base_url,
            api_key="EMPTY",
            timeout=args.timeout,
            http_client=httpx.Client(timeout=args.timeout, trust_env=False),
        )
        models, models_profile = _profile(lambda: client.models.list())
        served = sorted(item.id for item in models.data)
        if MODEL_ID not in served:
            raise RuntimeError(f"served model list does not contain {MODEL_ID}")
        raw, raw_profile = _profile(
            lambda: client.chat.completions.create(
                model=MODEL_ID,
                messages=[
                    {"role": "system", "content": "Return one direct JSON object. Do not emit a reasoning trace."},
                    {"role": "user", "content": "Return {\"status\":\"ok\"}."},
                ],
                temperature=0.0,
                seed=7,
                max_tokens=128,
                response_format={"type": "json_object"},
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
        )
        raw_content = raw.choices[0].message.content or ""
        raw_json = json.loads(raw_content)
        raw_reasoning = getattr(raw.choices[0].message, "reasoning_content", None)
        payload["provider_connectivity"] = {
            "status": "PASS",
            "served_models": served,
            "models_request": models_profile,
            "chat_request": raw_profile,
            "response_json": raw_json,
            "reasoning_content_present": bool(raw_reasoning),
            "input_tokens": getattr(raw.usage, "prompt_tokens", None),
            "output_tokens": getattr(raw.usage, "completion_tokens", None),
        }
        if raw_reasoning or not isinstance(raw_json, dict):
            raise RuntimeError("direct-response provider smoke returned visible reasoning or non-JSON")

        backend, transport, renderer = _build_backend(args.base_url, args.timeout)
        synthetic = EvidenceItem(
            evidence_id="ev_synthetic_raw_smoke",
            gap_type=GapType.OTHER,
            domain=GapDomain.OBSERVATIONAL,
            content=json.dumps(
                {
                    "evidence_type": "initial_session_evidence",
                    "packet_sequence": [
                        {"direction": "initiator_to_responder", "packet_length": 60, "relative_iat": 0.0, "l3_protocol": "IPv4", "l4_protocol": "TCP", "tcp_flags": 2},
                        {"direction": "responder_to_initiator", "packet_length": 60, "relative_iat": 0.001, "l3_protocol": "IPv4", "l4_protocol": "TCP", "tcp_flags": 18},
                    ],
                    "session_summary": {"duration": 0.001, "initiator_packets": 1, "responder_packets": 1, "initiator_bytes": 60, "responder_bytes": 60},
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            provenance="synthetic_model_safe_smoke",
            metadata={"smoke_only": True},
        )
        payload["fake_safe_backend"] = _call_backend(backend, transport, (synthetic,))
        if payload["fake_safe_backend"]["provider"].get("reasoning_content_present"):
            raise RuntimeError("fake-safe backend emitted visible reasoning content")

        store = ProductionParquetEvidenceStore(args.production_root)
        adapter = ProductionSafeAdapter(store)
        requests = [_request(sample_id) for sample_id in CLASS_SAMPLES.values()] + [_request(HAS_PAST_SAMPLE)]
        adapter.prefetch(requests)
        real_results: dict[str, Any] = {}
        adapted: dict[str, Any] = {}
        for ground_truth, sample_id in CLASS_SAMPLES.items():
            sample = adapter.adapt(_request(sample_id))
            adapted[sample_id] = sample
            index = store.row("sample_id_index", dataset="Edge-IIoTset", split="train", sample_id=sample_id, required=True)
            assert index is not None
            prohibited = (
                sample_id,
                str(index["fine_label"]), str(index["coarse_label"]), str(index["capture_ref_hash"]), str(index["source_sha256"]),
            )
            _assert_no_backend_leakage(renderer, sample.runtime_input.initial_evidence, prohibited)
            call = _call_backend(backend, transport, sample.runtime_input.initial_evidence)
            call["post_response_control_plane_ground_truth"] = ground_truth
            call["ground_truth_was_model_visible"] = False
            real_results[ground_truth] = call
        payload["real_production"] = real_results

        packet_sample = adapted[CLASS_SAMPLES["Backdoor"]]
        packet_initial = _call_backend(backend, transport, packet_sample.runtime_input.initial_evidence)
        packet_tool = next(tool for tool in packet_sample.tools if isinstance(tool, ProductionPacketExpansionTool))
        packet_result = packet_tool.execute(
            ToolRequest(action=AgentAction.EXPAND_PACKETS, parameters={"start_packet": 9, "end_packet": 16}),
            packet_sample.runtime_input.initial_evidence,
        )
        if packet_result.status is not ToolStatus.SUCCESS:
            raise RuntimeError("packet 9-16 evidence was not available")
        packet_expanded = _call_backend(backend, transport, packet_sample.runtime_input.initial_evidence + packet_result.evidence)
        payload["packet_expansion"] = {
            "status": "PASS",
            "round_1_initial": packet_initial,
            "round_2_initial_plus_packets_9_16": packet_expanded,
            "runtime_tool_status": packet_result.status.value,
        }

        temporal_sample = adapter.adapt(_request(HAS_PAST_SAMPLE))
        temporal_initial = _call_backend(backend, transport, temporal_sample.runtime_input.initial_evidence)
        temporal_tool = next(tool for tool in temporal_sample.tools if isinstance(tool, ProductionTemporalContextTool))
        temporal_result = temporal_tool.execute(
            ToolRequest(action=AgentAction.EXPAND_TEMPORAL_CONTEXT, parameters={"past_only": True, "window_seconds": 60.0}),
            temporal_sample.runtime_input.initial_evidence,
        )
        if temporal_result.status is not ToolStatus.SUCCESS:
            raise RuntimeError("past-only temporal evidence was not available")
        temporal_row = store.row("temporal_index", dataset="Edge-IIoTset", split="train", sample_id=HAS_PAST_SAMPLE, required=True)
        assert temporal_row is not None
        _assert_no_backend_leakage(
            renderer,
            temporal_sample.runtime_input.initial_evidence + temporal_result.evidence,
            (HAS_PAST_SAMPLE, str(temporal_row["source_identity_hash"]), str(temporal_row["destination_identity_hash"]), str(temporal_row["communication_pair_hash"])),
        )
        temporal_context = _call_backend(backend, transport, temporal_sample.runtime_input.initial_evidence + temporal_result.evidence)
        payload["temporal_context"] = {
            "status": "PASS",
            "initial_only": temporal_initial,
            "initial_plus_past_only_context": temporal_context,
            "runtime_tool_status": temporal_result.status.value,
            "strictly_past_only": float(temporal_row["context_latest_timestamp"]) < float(temporal_row["timestamp"]),
        }

        repeat_sample = adapted[CLASS_SAMPLES["Normal"]]
        repeat_a = _call_backend(backend, transport, repeat_sample.runtime_input.initial_evidence)
        repeat_b = _call_backend(backend, transport, repeat_sample.runtime_input.initial_evidence)
        labels_a = ([item["label"] for item in repeat_a["result"]["fine_candidates"]], [item["label"] for item in repeat_a["result"]["coarse_candidates"]])
        labels_b = ([item["label"] for item in repeat_b["result"]["fine_candidates"]], [item["label"] for item in repeat_b["result"]["coarse_candidates"]])
        payload["determinism"] = {
            "schema_stability": repeat_a["result"]["parse_status"] == repeat_b["result"]["parse_status"] == "PASS",
            "classification_stability": labels_a == labels_b,
            "parse_stability": True,
            "labels_equal": labels_a == labels_b,
        }
        if not payload["determinism"]["schema_stability"]:
            raise RuntimeError("deterministic repeat schema stability failed")

        all_calls = [payload["fake_safe_backend"], *real_results.values(), packet_initial, packet_expanded, temporal_initial, temporal_context, repeat_a, repeat_b]
        payload["resource_summary"] = {
            "idle_loaded_gpu_memory_mib": models_profile["gpu_memory_before_mib"],
            "observed_peak_gpu_memory_mib": max(item["resources"]["gpu_memory_observed_peak_mib"] for item in all_calls),
            "ttft": "UNAVAILABLE_NON_STREAMING_API",
        }
        payload.update({
            "MODEL_SERVICE_STATUS": "PASS",
            "LOCAL_QWEN_RAW_SMOKE": "PASS",
            "RUNTIME_TO_QWEN_REAL_SMOKE": "PASS",
            "completed_at_unix": time.time(),
            "elapsed_seconds": time.time() - started,
        })
    except Exception as exc:
        payload.update({
            "MODEL_SERVICE_STATUS": "FAIL",
            "LOCAL_QWEN_RAW_SMOKE": "FAIL",
            "RUNTIME_TO_QWEN_REAL_SMOKE": "FAIL",
            "failure_type": type(exc).__name__,
            "failure": str(exc),
            "completed_at_unix": time.time(),
            "elapsed_seconds": time.time() - started,
        })
        args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        raise
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("MODEL_SERVICE_STATUS", "LOCAL_QWEN_RAW_SMOKE", "RUNTIME_TO_QWEN_REAL_SMOKE")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
