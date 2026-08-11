from __future__ import annotations

import json
import os
import re
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
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
    PromptRole,
    judge_prompt_v2,
    teacher_prompt_v3,
)
from .role_requests import build_teacher_request


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
                    kind=ContentKind.INSTRUCTION,
                    label="output_contract",
                    content=canonical_json(prompt.output_contract),
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
    response_mode: ResponseMode = ResponseMode.STRUCTURED,
    max_tokens: int | None = None,
) -> LLMTransportRequest:
    return LLMTransportRequest(
        provider="deepseek",
        base_url=settings.base_url,
        model_id=settings.model_id,
        messages=_messages(prompt, payload),
        timeout_seconds=settings.timeout_seconds,
        response_mode=response_mode,
        generation_options={
            "temperature": 0,
            "max_tokens": max_tokens or settings.max_output_tokens,
            "extra_body": {"thinking": {"type": "disabled"}},
            **(
                {"response_format": {"type": "json_object"}}
                if response_mode is ResponseMode.STRUCTURED
                else {}
            ),
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


def _teacher_validation_failure_kind(exc: Exception) -> str:
    """Return a model-safe repair code without echoing invalid response content."""

    if isinstance(exc, ValidationError):
        paths = sorted({
            ".".join(str(part) for part in item.get("loc", ())) + ":" + str(item.get("type", "invalid"))
            for item in exc.errors(include_input=False)
        })
        return "schema_validation[" + ",".join(paths[:8]) + "]"
    message = str(exc).casefold()
    if "support references unavailable evidence" in message:
        return "grounding_reference_invalid"
    if "knowledge evidence cannot be cited" in message:
        return "knowledge_cited_as_observation"
    if "controlled lower-evidence auxiliary" in message:
        return "controlled_auxiliary_must_be_insufficient"
    if "immutable class verdict" in message:
        return "class_verdict_disclosed"
    return "semantic_consistency_invalid"


_STRICT_IMMUTABLE_LABEL_ALIASES: dict[str, tuple[str, ...]] = {
    "backdoor": ("backdoor",),
    "ddos_http": ("ddos", "distributed denial-of-service", "distributed denial of service", "flood"),
    "ddos_tcp": ("ddos", "distributed denial-of-service", "distributed denial of service", "flood"),
    "mitm": ("mitm", "man-in-the-middle", "man in the middle"),
    "normal": ("benign session", "benign traffic", "benign behavior", "benign activity"),
    "port_scanning": ("port scanning", "port-scanning", "port scanner", "scan"),
    "ransomware": ("ransomware",),
    "sql_injection": ("sql injection", "sql-injection", "sqli"),
    "vulnerability_scanner": ("vulnerability scanner", "vulnerability scanning", "vulnerability-scanner", "vulnerability-scanning", "scan", "probing for vulnerabilities"),
}


def _strict_immutable_label_aliases(fine_label: str) -> tuple[str, ...]:
    return _STRICT_IMMUTABLE_LABEL_ALIASES.get(fine_label.casefold(), ())


def validate_teacher_annotation(
    payload: dict[str, Any],
    snapshot: Any,
) -> TeacherAnnotationV1:
    annotation = TeacherAnnotationV1.model_validate(payload)
    validate_evidence_grounding(annotation, snapshot.evidence)
    if not snapshot.classification_supervision_valid and annotation.evidence_sufficient:
        raise ValueError("controlled lower-evidence auxiliary cannot become evidence-sufficient")
    rendered = canonical_json(annotation.model_dump(mode="json")).casefold()
    label_variants = {
        str(snapshot.fine_label).casefold(),
        str(snapshot.fine_label).casefold().replace("_", " "),
        str(snapshot.fine_label).casefold().replace("_", "-"),
    }
    backend_label = str(snapshot.fine_label).casefold()
    strict_aliases = _strict_immutable_label_aliases(backend_label)
    if any(alias in rendered for alias in strict_aliases):
        raise ValueError("Teacher Evidence State disclosed an immutable class verdict")
    if "_" in backend_label and re.search(
        rf"(?<![a-z0-9]){re.escape(backend_label)}(?![a-z0-9])", rendered
    ):
        raise ValueError("Teacher Evidence State disclosed an immutable class verdict")
    for label in label_variants:
        token = rf"(?<![a-z0-9]){re.escape(label)}(?![a-z0-9])"
        conclusion_patterns = (
            rf"\b(?:distinguish|differentiate)\s+(?:the\s+)?{token}(?:\s+[a-z-]+){{0,4}}\s+from\b",
            rf"\b(?:confirm|confirms|confirmed|identify|identifies|identified|classify|classified|label|labeled)\s+(?:as\s+)?(?:an?\s+|the\s+)?{token}",
            rf"\b(?:consistent\s+with|indicative\s+of|suggests?|points?\s+to)\s+(?:an?\s+|the\s+)?{token}",
            rf"{token}\s+(?:class|classification|behavior|activity|traffic|pattern)\b",
            rf"\b(?:class|label|classification)\s+(?:is|as|of)?\s*{token}",
        )
        if any(re.search(pattern, rendered) for pattern in conclusion_patterns):
            raise ValueError("Teacher Evidence State disclosed an immutable class verdict")
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
        payload = build_teacher_request(snapshot).model_dump(mode="json")
        request = _request(teacher_prompt_v3(), payload, self.settings, role="teacher")
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
                    "latency_seconds": response.usage.abstract_latency,
                    "raw_structured_result": raw_payload,
                    "annotation_digest": content_digest(annotation.model_dump(mode="json")),
                }
            except (ValueError, ValidationError, json.JSONDecodeError) as exc:
                failure_kind = _teacher_validation_failure_kind(exc)
                failures.append(failure_kind)
                if attempt == 2:
                    break
                repair_payload = {
                    **payload,
                    "repair_instruction": (
                        "The first response failed deterministic validation. Return a fresh object "
                        "that exactly follows the schema and current Evidence IDs; do not add fields. "
                        "Cite only visible Observation IDs, never Knowledge as a session fact. Never "
                        "repeat the immutable class label or emit a classification verdict; refer "
                        "to it only as 'the target behavior' and compare only with 'plausible "
                        "alternatives'. Keep evidence_sufficient, gap_type, and missing_evidence "
                        "mutually consistent; a "
                        "controlled lower-evidence auxiliary must remain insufficient. Each "
                        "missing_evidence description must use exactly this neutral sentence: More "
                        "independent evidence is required to resolve the remaining ambiguity."
                        " Keep behavior_summary to one sentence of at most 180 characters. Every "
                        "supporting_evidence ID must be copied exactly from the allowlist; if no "
                        "allowlisted ID is certainly applicable, return an empty supporting list. Never mention the target "
                        "family in any text field, including when describing absent evidence or "
                        "plausible alternatives. Every prohibited_output_terms entry and its "
                        "hyphenated or reordered form is forbidden in every response string."
                    ),
                    "validation_failure_kind": failure_kind,
                    "allowed_supporting_evidence_ids": [
                        item.evidence_id
                        for item in snapshot.evidence
                        if item.domain.value == "observation"
                    ],
                    "supporting_evidence_policy": (
                        "Use only exact IDs from allowed_supporting_evidence_ids; otherwise return []"
                    ),
                    "prohibited_output_terms": sorted({
                        str(snapshot.fine_label),
                        str(snapshot.fine_label).replace("_", " "),
                        str(snapshot.fine_label).replace("_", "-"),
                        *_strict_immutable_label_aliases(str(snapshot.fine_label)),
                    }),
                    "field_character_limits": {
                        "behavior_summary": 180,
                        "supporting_evidence.claim": 320,
                        "missing_evidence.description": 160,
                    },
                }
                request = _request(
                    teacher_prompt_v3(), repair_payload, self.settings, role="teacher_repair"
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
    """Exercise discovery plus text/JSON calls through the formal project transport."""

    settings = settings or DeepSeekFlashSettings.from_environment()
    key = os.environ.get(DEEPSEEK_SECRET_ENV)
    if not key:
        return {"status": "BLOCKED", "reason": "NO_API_KEY", **provider_availability()}
    from openai import OpenAI

    discovery_started = time.perf_counter()
    discovery_client = OpenAI(
        base_url=settings.base_url,
        api_key=key,
        timeout=settings.timeout_seconds,
    )
    models = discovery_client.models.list()
    discovery_latency = time.perf_counter() - discovery_started
    model_ids = sorted(str(item.id) for item in models.data)
    if settings.model_id not in model_ids:
        raise RuntimeError(f"configured DeepSeek model is unavailable: {settings.model_id}")

    transport = OpenAICompatibleChatTransport(
        api_key=key,
        max_input_tokens=8192,
        max_output_tokens=settings.max_output_tokens,
        max_latency_seconds=settings.timeout_seconds,
        trust_env=True,
    )
    simple_prompt = FrozenPrompt(
        role=PromptRole.TEACHER,
        version="DEEPSEEK_PROVIDER_TEXT_PREFLIGHT_V1",
        system_instruction="This is a provider health check. Return only the requested short answer.",
        task_instruction="Return exactly OK.",
        output_contract={"text": "OK"},
    )
    simple = transport.send(
        _request(
            simple_prompt,
            {"healthcheck": True},
            settings,
            role="provider_preflight_text",
            response_mode=ResponseMode.TEXT,
            max_tokens=16,
        )
    )
    if not simple.raw_text or simple.raw_text.strip().casefold().rstrip(".") != "ok":
        raise RuntimeError("DeepSeek simple completion smoke failed")

    structured_prompt = FrozenPrompt(
        role=PromptRole.TEACHER,
        version="DEEPSEEK_PROVIDER_JSON_PREFLIGHT_V1",
        system_instruction="This is a provider health check. Return one compact JSON object only.",
        task_instruction='Return the semantic object {"status":"ok"}.',
        output_contract={"status": "ok"},
    )
    structured = transport.send(
        _request(
            structured_prompt,
            {"healthcheck": True},
            settings,
            role="provider_preflight_structured",
            max_tokens=32,
        )
    )
    if structured.structured_payload != {"status": "ok"}:
        raise RuntimeError("DeepSeek structured response smoke failed")

    result = {
        "status": "PASS",
        "provider_path": "OpenAICompatibleChatTransport",
        "reasoning_mode": "non_thinking_explicit",
        "model_list_pass": True,
        "simple_completion_pass": True,
        "structured_response_pass": True,
        "schema_validation_pass": True,
        "timeout_retry_error_mapping_contract": "COVERED_BY_PROJECT_TRANSPORT_TESTS",
        "model_id": settings.model_id,
        "model_list_request_id": getattr(models, "_request_id", None),
        "simple_request_id": simple.request_id,
        "structured_request_id": structured.request_id,
        "latency_seconds": {
            "model_list": round(discovery_latency, 4),
            "simple": round(simple.usage.abstract_latency, 4),
            "structured": round(structured.usage.abstract_latency, 4),
        },
        "usage": {
            "simple": simple.usage.model_dump(mode="json"),
            "structured": structured.usage.model_dump(mode="json"),
        },
        "secret_value_logged": False,
        "transport_repr_redacted": key not in repr(transport),
        "teacher_client_ready": isinstance(
            DeepSeekTeacherClient(transport, settings=settings), DeepSeekTeacherClient
        ),
    }
    if key in json.dumps(result, sort_keys=True):
        raise RuntimeError("provider preflight result leaked a runtime secret")
    return result


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
    seed_cache_roots: tuple[Path, ...] = (),
) -> dict[str, Any]:
    """Cacheable/resumable TRAIN-only annotation with bounded concurrency and metrics."""

    if concurrency < 1 or concurrency > 16:
        raise ValueError("Teacher concurrency must be in 1..16")
    if any(item.split != "train" or item.ku_role != "K_known" for item in snapshots):
        raise ValueError("Teacher bulk escaped K_known TRAIN")
    output_root = Path(output_root)
    cache_root = output_root / "cache"
    records_root = output_root / "records"
    cache_root.mkdir(parents=True, exist_ok=True)
    records_root.mkdir(parents=True, exist_ok=True)
    prompt = teacher_prompt_v3()

    def annotate_one(snapshot: Any) -> tuple[str, str, str | None]:
        cache_path = cache_root / f"{snapshot.evidence_state_id}.json"
        record_path = records_root / f"{snapshot.evidence_state_id}.json"
        cache_candidates = (
            cache_path,
            *(
                Path(root) / f"{snapshot.evidence_state_id}.json"
                for root in seed_cache_roots
            ),
        )
        for candidate in cache_candidates:
            if not candidate.is_file():
                continue
            cached = json.loads(candidate.read_text(encoding="utf-8"))
            expected = content_digest(
                [snapshot.source_digest, prompt.digest, client.settings.model_id]
            )
            if cached.get("cache_key") == expected and cached.get("validation_result") == "PASS":
                try:
                    validate_teacher_annotation(cached.get("normalized_target") or {}, snapshot)
                except (ValueError, ValidationError, json.JSONDecodeError):
                    if record_path.is_file():
                        record_path.unlink()
                    continue
                write_annotation_record(cache_path, cached)
                write_annotation_record(record_path, cached)
                stale = output_root / "quarantine" / f"{snapshot.evidence_state_id}.json"
                if stale.is_file():
                    stale.unlink()
                return snapshot.evidence_state_id, "CACHED", None
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
                    "latency_seconds": audit.get("latency_seconds"),
                    "attempts": audit.get("attempts"),
                    "repair_used": audit.get("repair_used"),
                    "cache_key": cache_key,
                    "provider_version": DEEPSEEK_PROVIDER_VERSION,
                }
                write_annotation_record(cache_path, record)
                write_annotation_record(record_path, record)
                stale = output_root / "quarantine" / f"{snapshot.evidence_state_id}.json"
                if stale.is_file():
                    stale.unlink()
                return snapshot.evidence_state_id, "PASS", None
            except TeacherAnnotationQuarantined as exc:
                last_error = exc
                break
            except Exception as exc:
                last_error = exc
                if attempt < client.settings.max_attempts:
                    time.sleep(min(2**attempt, 8))
        failure_type = type(last_error).__name__ if last_error else "Unknown"
        quarantine = {
            "sample_id": snapshot.sample_id,
            "evidence_state_id": snapshot.evidence_state_id,
            "validation_result": "QUARANTINE",
            "safe_failure_type": failure_type,
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "teacher_prompt_version": prompt.version,
            "model": client.settings.model_id,
        }
        write_annotation_record(
            output_root / "quarantine" / f"{snapshot.evidence_state_id}.json", quarantine
        )
        if record_path.is_file():
            record_path.unlink()
        return snapshot.evidence_state_id, "QUARANTINE", failure_type

    counts: dict[str, int] = {"PASS": 0, "CACHED": 0, "QUARANTINE": 0}
    failure_types: Counter[str] = Counter()
    completed = 0
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(annotate_one, snapshot): snapshot for snapshot in snapshots}
        for future in as_completed(futures):
            _state_id, status, failure_type = future.result()
            counts[status] += 1
            completed += 1
            if failure_type:
                failure_types[failure_type] += 1
            if completed % 100 == 0 or completed == len(snapshots):
                print(
                    f"TEACHER_PROGRESS={completed}/{len(snapshots)} quarantine={counts['QUARANTINE']}",
                    file=sys.stderr,
                    flush=True,
                )

    records = []
    for snapshot in snapshots:
        record_path = records_root / f"{snapshot.evidence_state_id}.json"
        if record_path.is_file():
            value = json.loads(record_path.read_text(encoding="utf-8"))
            if value.get("validation_result") == "PASS":
                try:
                    validate_teacher_annotation(value.get("normalized_target") or {}, snapshot)
                except (ValueError, ValidationError, json.JSONDecodeError):
                    continue
                records.append(value)
    repair_count = sum(bool(item.get("repair_used")) for item in records)
    token_totals = [
        int((item.get("token_usage") or {}).get("total_tokens") or 0) for item in records
    ]
    latencies = [
        float(item.get("latency_seconds") or 0.0) for item in records
    ]
    class_distribution = Counter(str(item.fine_label) for item in snapshots)
    stage_distribution = Counter(str(item.stage_type.value) for item in snapshots)
    classification_candidate_distribution = Counter(
        "candidate" if item.classification_supervision_valid else "masked"
        for item in snapshots
    )
    state_role_distribution = Counter(
        "primary" if item.classification_supervision_valid else "auxiliary"
        for item in snapshots
    )
    evidence_sufficiency_distribution = Counter(
        "sufficient"
        if bool((item.get("normalized_target") or {}).get("evidence_sufficient"))
        else "insufficient"
        for item in records
    )
    valid_count = len(records)
    manifest = {
        "status": "PASS" if counts["QUARANTINE"] == 0 and valid_count == len(snapshots)
        else "PASS_WITH_QUARANTINE",
        "provider_version": DEEPSEEK_PROVIDER_VERSION,
        "model": client.settings.model_id,
        "prompt_version": prompt.version,
        "prompt_digest": prompt.digest,
        "requested": len(snapshots),
        "valid_count": valid_count,
        "valid_rate": valid_count / len(snapshots) if snapshots else 0.0,
        "valid_first_pass_count": valid_count - repair_count,
        "valid_first_pass_rate": (valid_count - repair_count) / len(snapshots)
        if snapshots else 0.0,
        "repair_count": repair_count,
        "repair_rate": repair_count / len(snapshots) if snapshots else 0.0,
        "quarantine_rate": counts["QUARANTINE"] / len(snapshots) if snapshots else 0.0,
        "failure_types": dict(sorted(failure_types.items())),
        "average_total_tokens": sum(token_totals) / len(token_totals) if token_totals else 0.0,
        "total_tokens": sum(token_totals),
        "average_latency_seconds": sum(latencies) / len(latencies) if latencies else 0.0,
        "counts": counts,
        "class_distribution": dict(sorted(class_distribution.items())),
        "stage_distribution": dict(sorted(stage_distribution.items())),
        "classification_candidate_distribution": dict(
            sorted(classification_candidate_distribution.items())
        ),
        "state_role_distribution": dict(sorted(state_role_distribution.items())),
        "classification_ce_policy": "deterministic primary protocol; independent of Teacher sufficiency",
        "evidence_sufficiency_distribution": dict(
            sorted(evidence_sufficiency_distribution.items())
        ),
        "concurrency": concurrency,
        "cache_resume_enabled": True,
        "seed_cache_roots": len(seed_cache_roots),
        "u_final_count": 0,
    }
    write_annotation_record(output_root / "manifest.json", manifest)
    return manifest
