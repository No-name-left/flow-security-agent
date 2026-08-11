from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from flowsec.integrations.llm.contracts import (
    ContentKind,
    EvidenceTrust,
    LLMMessage,
    LLMTransportRequest,
    MessageContent,
    MessageRole,
    PromptIdentity,
    RawLLMResponse,
    ResponseMode,
)
from flowsec.integrations.llm.transport import LLMTransport, OpenAICompatibleChatTransport

from .contracts import (
    JudgeRewardV1,
    TeacherAnnotationV1,
    canonical_json,
    content_digest,
    validate_evidence_grounding,
)
from .prompts import (
    FrozenPrompt,
    judge_prompt_v1,
    teacher_prompt_v1,
    teacher_request_payload,
)


DEEPSEEK_PROVIDER_VERSION = "DEEPSEEK_FLASH_PROVIDER_V1"
DEEPSEEK_MODEL_DEFAULT = "deepseek-v4-flash"
DEEPSEEK_BASE_URL_DEFAULT = "https://api.deepseek.com"
DEEPSEEK_SECRET_ENV = "DEEPSEEK_API_KEY"


class TeacherAnnotationQuarantined(ValueError):
    """A schema/grounding failure that already consumed the single repair attempt."""


@dataclass(frozen=True, slots=True)
class DeepSeekFlashSettings:
    model_id: str = DEEPSEEK_MODEL_DEFAULT
    base_url: str = DEEPSEEK_BASE_URL_DEFAULT
    timeout_seconds: float = 90.0
    max_output_tokens: int = 900
    max_attempts: int = 3

    @classmethod
    def from_environment(cls) -> "DeepSeekFlashSettings":
        return cls(
            model_id=os.environ.get("DEEPSEEK_MODEL", DEEPSEEK_MODEL_DEFAULT),
            base_url=os.environ.get("DEEPSEEK_BASE_URL", DEEPSEEK_BASE_URL_DEFAULT),
        )


def provider_availability(environ: dict[str, str] | None = None) -> dict[str, Any]:
    environment = os.environ if environ is None else environ
    return {
        "provider_version": DEEPSEEK_PROVIDER_VERSION,
        "model_id": environment.get("DEEPSEEK_MODEL", DEEPSEEK_MODEL_DEFAULT),
        "base_url": environment.get("DEEPSEEK_BASE_URL", DEEPSEEK_BASE_URL_DEFAULT),
        "secret_reference": DEEPSEEK_SECRET_ENV,
        "api_key_available": bool(environment.get(DEEPSEEK_SECRET_ENV)),
        "secret_value_logged": False,
    }


def _prompt_identity(prompt: FrozenPrompt) -> PromptIdentity:
    return PromptIdentity(
        prompt_id=prompt.version,
        prompt_version=prompt.version,
        prompt_hash=prompt.digest,
        renderer_version="TRAINING_STRUCTURED_RENDERER_V1",
    )


def _messages(prompt: FrozenPrompt, payload: dict[str, Any]) -> tuple[LLMMessage, ...]:
    return (
        LLMMessage(
            role=MessageRole.SYSTEM,
            content=(
                MessageContent(
                    kind=ContentKind.INSTRUCTION,
                    label="system_instruction",
                    content=prompt.system_instruction,
                ),
            ),
        ),
        LLMMessage(
            role=MessageRole.USER,
            content=(
                MessageContent(
                    kind=ContentKind.INSTRUCTION,
                    label="task_instruction",
                    content=prompt.task_instruction,
                ),
                MessageContent(
                    kind=ContentKind.DATA,
                    trust=EvidenceTrust.UNTRUSTED_EVIDENCE,
                    label="structured_task_data",
                    content=canonical_json(payload),
                ),
            ),
        ),
    )


def _request(
    prompt: FrozenPrompt,
    payload: dict[str, Any],
    settings: DeepSeekFlashSettings,
    *,
    role: str,
) -> LLMTransportRequest:
    return LLMTransportRequest(
        provider="deepseek",
        base_url=settings.base_url,
        model_id=settings.model_id,
        messages=_messages(prompt, payload),
        timeout_seconds=settings.timeout_seconds,
        response_mode=ResponseMode.STRUCTURED,
        generation_options={
            "temperature": 0,
            "max_tokens": settings.max_output_tokens,
            "response_format": {"type": "json_object"},
        },
        prompt=_prompt_identity(prompt),
        request_metadata={"backend_role": role, "provider_version": DEEPSEEK_PROVIDER_VERSION},
    )


def _response_payload(response: RawLLMResponse) -> dict[str, Any]:
    if response.failure is not None:
        raise ValueError(response.failure.safe_message)
    if response.structured_payload is not None:
        return response.structured_payload
    if not response.raw_text:
        raise ValueError("provider returned no structured payload")
    value = json.loads(response.raw_text)
    if not isinstance(value, dict):
        raise ValueError("provider response is not an object")
    return value


def validate_teacher_annotation(
    payload: dict[str, Any],
    snapshot: Any,
) -> TeacherAnnotationV1:
    annotation = TeacherAnnotationV1.model_validate(payload)
    validate_evidence_grounding(annotation, snapshot.evidence)
    present_types = {item.evidence_type for item in snapshot.evidence}
    aliases = {"relation": "relation", "application": "application", "payload": "sanitized_payload", "knowledge": "knowledge"}
    for missing in annotation.missing_evidence:
        if aliases.get(missing.type.value, missing.type.value) in present_types:
            raise ValueError(f"Teacher declared present evidence missing: {missing.type.value}")
    if annotation.evidence_sufficient != snapshot.classification_supervision_valid:
        raise ValueError("Teacher sufficiency disagrees with the frozen supervision decision")
    return annotation


class DeepSeekTeacherClient:
    def __init__(
        self,
        transport: LLMTransport,
        *,
        settings: DeepSeekFlashSettings,
    ):
        self.transport = transport
        self.settings = settings

    def annotate(self, snapshot: Any) -> tuple[TeacherAnnotationV1, dict[str, Any]]:
        payload = teacher_request_payload(snapshot)
        request = _request(teacher_prompt_v1(), payload, self.settings, role="teacher")
        failures: list[str] = []
        for attempt in (1, 2):
            response = self.transport.send(request)
            try:
                raw_payload = _response_payload(response)
                annotation = validate_teacher_annotation(raw_payload, snapshot)
                return annotation, {
                    "status": "PASS",
                    "attempts": attempt,
                    "repair_used": attempt == 2,
                    "request_id": response.request_id,
                    "model_id": response.model_id or self.settings.model_id,
                    "usage": response.usage.model_dump(mode="json"),
                    "raw_structured_result": raw_payload,
                    "annotation_digest": content_digest(annotation.model_dump(mode="json")),
                }
            except (ValueError, ValidationError, json.JSONDecodeError) as exc:
                failures.append(type(exc).__name__)
                if attempt == 2:
                    break
                repair_payload = {
                    **payload,
                    "repair_instruction": (
                        "The first response failed deterministic validation. Return a fresh object "
                        "that exactly follows the schema and current Evidence IDs; do not add fields."
                    ),
                    "validation_failure_kind": type(exc).__name__,
                }
                request = _request(
                    teacher_prompt_v1(), repair_payload, self.settings, role="teacher_repair"
                )
        raise TeacherAnnotationQuarantined(
            f"Teacher annotation quarantined after bounded repair: {failures}"
        )


def parse_judge_response(response: RawLLMResponse) -> JudgeRewardV1:
    return JudgeRewardV1.model_validate(_response_payload(response))


def make_live_teacher_client(
    settings: DeepSeekFlashSettings | None = None,
) -> DeepSeekTeacherClient:
    settings = settings or DeepSeekFlashSettings.from_environment()
    api_key = os.environ.get(DEEPSEEK_SECRET_ENV)
    if not api_key:
        raise RuntimeError("DEEPSEEK_PROVIDER_BLOCKED=NO_API_KEY")
    transport = OpenAICompatibleChatTransport(
        api_key=api_key,
        max_input_tokens=8192,
        max_output_tokens=settings.max_output_tokens,
        max_latency_seconds=settings.timeout_seconds,
        trust_env=True,
    )
    return DeepSeekTeacherClient(transport, settings=settings)


def deepseek_api_preflight(
    settings: DeepSeekFlashSettings | None = None,
) -> dict[str, Any]:
    """Run model discovery and one non-thinking structured smoke only with a runtime secret."""

    settings = settings or DeepSeekFlashSettings.from_environment()
    key = os.environ.get(DEEPSEEK_SECRET_ENV)
    if not key:
        return {"status": "BLOCKED", "reason": "NO_API_KEY", **provider_availability()}
    from openai import OpenAI

    started = time.perf_counter()
    client = OpenAI(base_url=settings.base_url, api_key=key, timeout=settings.timeout_seconds)
    models = client.models.list()
    model_ids = sorted(str(item.id) for item in models.data)
    if settings.model_id not in model_ids:
        raise RuntimeError(f"configured DeepSeek model is unavailable: {settings.model_id}")
    response = client.chat.completions.create(
        model=settings.model_id,
        messages=(
            {
                "role": "system",
                "content": "Return only a compact JSON object. Do not expose hidden reasoning.",
            },
            {
                "role": "user",
                "content": 'Return exactly the semantic object {"status":"ok"}.',
            },
        ),
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=32,
        stream=False,
    )
    content = response.choices[0].message.content
    if not isinstance(content, str) or json.loads(content) != {"status": "ok"}:
        raise RuntimeError("DeepSeek structured response smoke failed")
    usage = getattr(response, "usage", None)
    usage_summary = {
        name: int(getattr(usage, name, 0) or 0)
        for name in ("prompt_tokens", "completion_tokens", "total_tokens")
    }
    return {
        "status": "PASS",
        "model_list_pass": True,
        "structured_response_pass": True,
        "reasoning_mode": "non-thinking_direct_structured",
        "model_id": settings.model_id,
        "model_list_request_id": getattr(models, "_request_id", None),
        "structured_request_id": getattr(response, "_request_id", None)
        or getattr(response, "id", None),
        "latency_seconds": round(time.perf_counter() - started, 4),
        "usage": usage_summary,
        "secret_value_logged": False,
        "teacher_client_ready": isinstance(make_live_teacher_client(settings), DeepSeekTeacherClient),
    }


def write_annotation_record(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = dict(value)
    secret_names = {"api_key", "authorization", "bearer", "secret", "access_token", "private_key"}
    if any(str(key).casefold().replace("-", "_") in secret_names for key in safe):
        raise ValueError("annotation record contains a secret-like field")
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(safe, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def select_teacher_pilot(snapshots: list[Any], *, target: int = 250) -> list[Any]:
    if not 200 <= target <= 300:
        raise ValueError("Teacher pilot target must be in 200..300")
    strata: dict[tuple[str, str, bool], list[Any]] = {}
    for snapshot in snapshots:
        key = (
            str(snapshot.fine_label),
            str(snapshot.stage_type.value),
            bool(snapshot.classification_supervision_valid),
        )
        strata.setdefault(key, []).append(snapshot)
    for values in strata.values():
        values.sort(key=lambda item: content_digest(["teacher_pilot_v1", item.evidence_state_id]))
    selected: list[Any] = []
    offsets = {key: 0 for key in strata}
    while len(selected) < min(target, len(snapshots)):
        advanced = False
        for key in sorted(strata):
            index = offsets[key]
            if index < len(strata[key]):
                selected.append(strata[key][index])
                offsets[key] += 1
                advanced = True
                if len(selected) == target:
                    break
        if not advanced:
            break
    return selected


def annotate_snapshots(
    snapshots: list[Any],
    output_root: Path,
    *,
    client: DeepSeekTeacherClient,
    concurrency: int = 4,
) -> dict[str, Any]:
    """Cacheable bulk annotation. It never selects validation, test, or unknown roles."""

    if concurrency < 1 or concurrency > 16:
        raise ValueError("Teacher concurrency must be in 1..16")
    if any(item.split != "train" or item.ku_role != "K_known" for item in snapshots):
        raise ValueError("Teacher bulk escaped K_known TRAIN")
    output_root = Path(output_root)
    cache_root = output_root / "cache"
    records_root = output_root / "records"
    cache_root.mkdir(parents=True, exist_ok=True)
    records_root.mkdir(parents=True, exist_ok=True)
    prompt = teacher_prompt_v1()

    def annotate_one(snapshot: Any) -> tuple[str, str]:
        cache_path = cache_root / f"{snapshot.evidence_state_id}.json"
        if cache_path.is_file():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            expected = content_digest(
                [snapshot.source_digest, prompt.digest, client.settings.model_id]
            )
            if cached.get("cache_key") == expected and cached.get("validation_result") == "PASS":
                return snapshot.evidence_state_id, "CACHED"
        last_error: Exception | None = None
        for attempt in range(1, client.settings.max_attempts + 1):
            try:
                annotation, audit = client.annotate(snapshot)
                cache_key = content_digest(
                    [snapshot.source_digest, prompt.digest, client.settings.model_id]
                )
                record = {
                    "sample_id": snapshot.sample_id,
                    "evidence_state_id": snapshot.evidence_state_id,
                    "evidence_state_digest": snapshot.source_digest,
                    "teacher_prompt_version": prompt.version,
                    "teacher_prompt_digest": prompt.digest,
                    "model": client.settings.model_id,
                    "request_id": audit.get("request_id"),
                    "raw_structured_result": audit.get("raw_structured_result"),
                    "normalized_target": annotation.model_dump(mode="json"),
                    "validation_result": "PASS",
                    "timestamp_utc": datetime.now(UTC).isoformat(),
                    "token_usage": audit.get("usage"),
                    "repair_used": audit.get("repair_used"),
                    "cache_key": cache_key,
                    "provider_version": DEEPSEEK_PROVIDER_VERSION,
                }
                write_annotation_record(cache_path, record)
                write_annotation_record(
                    records_root / f"{snapshot.evidence_state_id}.json", record
                )
                return snapshot.evidence_state_id, "PASS"
            except TeacherAnnotationQuarantined as exc:
                last_error = exc
                break
            except Exception as exc:  # transport failures are retried within the fixed bound
                last_error = exc
                if attempt < client.settings.max_attempts:
                    time.sleep(min(2**attempt, 8))
        quarantine = {
            "sample_id": snapshot.sample_id,
            "evidence_state_id": snapshot.evidence_state_id,
            "validation_result": "QUARANTINE",
            "safe_failure_type": type(last_error).__name__ if last_error else "Unknown",
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "teacher_prompt_version": prompt.version,
            "model": client.settings.model_id,
        }
        write_annotation_record(
            output_root / "quarantine" / f"{snapshot.evidence_state_id}.json", quarantine
        )
        return snapshot.evidence_state_id, "QUARANTINE"

    counts: dict[str, int] = {"PASS": 0, "CACHED": 0, "QUARANTINE": 0}
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(annotate_one, snapshot): snapshot for snapshot in snapshots}
        for future in as_completed(futures):
            _state_id, status = future.result()
            counts[status] += 1
    manifest = {
        "status": "PASS" if counts["QUARANTINE"] == 0 else "PASS_WITH_QUARANTINE",
        "provider_version": DEEPSEEK_PROVIDER_VERSION,
        "model": client.settings.model_id,
        "prompt_version": prompt.version,
        "prompt_digest": prompt.digest,
        "requested": len(snapshots),
        "counts": counts,
        "concurrency": concurrency,
        "u_final_count": 0,
    }
    write_annotation_record(output_root / "manifest.json", manifest)
    return manifest
