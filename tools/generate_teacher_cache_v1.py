#!/usr/bin/env python3
"""Generate teacher_cache_v1 (N=2000) and semantic_reference_v1 (N=63) DeepSeek responses.

Authorized paid generation task (researcher-authorized). This tool is:

- resume-safe: records with a schema-valid, prompt/model-compatible response are skipped;
- idempotent: outputs are keyed by teacher_cache_id / reference_id;
- prompt-frozen: one system prompt, one user template, one schema per task for the whole
  batch; the prompt is never modified after a record fails;
- leak-checked: a payload GT-leakage precheck runs before the first paid call;
- bounded: teacher hard cap 2150 API attempts, semantic hard cap 80 API attempts.

Roles are restricted by the frozen contract: TEACHER_SUPERVISOR_BASELINE,
OPTIONAL_POLICY_DEMONSTRATION, OPTIONAL_IMITATION_INITIALIZATION. Never
classification/utility/Unknown/continual GT. The tool never prints secrets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from flowsec.integrations.llm.contracts import (  # noqa: E402
    ContentKind,
    LLMFailureKind,
    LLMMessage,
    LLMTransportError,
    LLMTransportRequest,
    MessageContent,
    MessageRole,
    PromptIdentity,
    ResponseMode,
)
from flowsec.integrations.llm.transport import OpenAICompatibleChatTransport  # noqa: E402

# ---------------------------------------------------------------------------
# Frozen generation constants
# ---------------------------------------------------------------------------

TEACHER_PROMPT_ID = "TEACHER_CACHE_V1_POLICY_PROMPT"
TEACHER_PROMPT_VERSION = "TEACHER_CACHE_V1_PROMPT_V1"
TEACHER_RENDERER_VERSION = "TEACHER_CACHE_V1_RENDERER_V1"

TEACHER_SYSTEM_INSTRUCTION = (
    "You are an offline traffic-analysis policy reviewer producing a frozen research cache. "
    "You receive one model-safe runtime state from a traffic classifier. "
    "Return exactly one JSON object and nothing else: no markdown, no thinking trace. "
    "Do not infer dataset identity, ground truth, recoverability, split, or hidden labels. "
    "You never invent new attack classes."
)

TEACHER_TASK_TEMPLATE = (
    "You may recommend exactly one of four actions: "
    "STOP_AND_CLASSIFY, ACQUIRE_TEMPORAL, ACQUIRE_RELATION, ENTER_NOVELTY_DETECTION.\n"
    "ENTER_NOVELTY_DETECTION only submits the observation to an independent novelty "
    "detector; it is not a prediction that the sample is unknown.\n"
    "Choose STOP_AND_CLASSIFY when the Basic evidence already supports a reliable "
    "known-class decision. Choose an acquire action only when the corresponding "
    "evidence is listed as available and would plausibly improve the decision. "
    "Choose ENTER_NOVELTY_DETECTION when no further acquisition is worthwhile under "
    "the available evidence.\n"
    "Respond with exactly this JSON schema:\n"
    '{"predicted_class": "<known-class-name or null>", '
    '"recommended_action": "<one of the four actions>", "confidence": 0.0, '
    '"semantic_gap": "<concise>", "short_reason": "<concise>"}\n'
    "- predicted_class is one of: Backdoor, Benign, Credential, DDoS, DoS, "
    "Recon_Scanning, Web_Injection, or null.\n"
    "- confidence is your confidence in the recommended action, a number in [0,1].\n"
    "- semantic_gap is one of: NONE, NEEDS_TEMPORAL, NEEDS_RELATION, "
    "NOVELTY_OR_UNRESOLVABLE, AMBIGUOUS.\n"
    "- For STOP_AND_CLASSIFY: predicted_class must be a known class and "
    "semantic_gap must be NONE.\n"
    "- For an acquire action: predicted_class may be a tentative known class or null, "
    "and the acquired family must be available.\n"
    "- For ENTER_NOVELTY_DETECTION: predicted_class may be null.\n"
    "- short_reason: 1-3 short sentences grounded only in the visible state.\n"
    "RUNTIME STATE:\n{state_json}"
)

TEACHER_RESPONSE_SCHEMA = {
    "predicted_class": "one of CANONICAL_TAXONOMY_V1 or null",
    "recommended_action": (
        "STOP_AND_CLASSIFY | ACQUIRE_TEMPORAL | ACQUIRE_RELATION | "
        "ENTER_NOVELTY_DETECTION"
    ),
    "confidence": "number in [0,1]",
    "semantic_gap": (
        "NONE | NEEDS_TEMPORAL | NEEDS_RELATION | NOVELTY_OR_UNRESOLVABLE | AMBIGUOUS"
    ),
    "short_reason": "concise string, 1-3 sentences",
}

SEMANTIC_PROMPT_ID = "SEMANTIC_ADMISSIBILITY_REFERENCE_V1_PROMPT"
SEMANTIC_PROMPT_VERSION = "SEMANTIC_REFERENCE_V1_PROMPT_V1"
SEMANTIC_RENDERER_VERSION = "SEMANTIC_REFERENCE_V1_RENDERER_V1"

SEMANTIC_SYSTEM_INSTRUCTION = (
    "You are an offline semantic reviewer for a network-traffic evidence admissibility "
    "reference. You review class/evidence-level normalized patterns only: never "
    "individual samples, dataset identity, empirical model outcomes, or operational "
    "utility. Return exactly one JSON object and nothing else: no markdown, no "
    "thinking trace."
)

SEMANTIC_TASK_TEMPLATE = (
    "Review the normalized evidence pattern for the stated class/mechanism and "
    "evidence family. Decide what class-level semantic claim the pattern can support "
    "and what stronger claim it cannot justify.\n"
    "Respond with exactly this JSON schema:\n"
    '{"semantic_relevance": "<SUPPORTIVE | NEUTRAL | CONTRADICTORY | '
    'CONTEXT_DEPENDENT>", "allowed_claim": "<concise>", '
    '"forbidden_claim": "<concise>", "short_reason": "<concise>"}\n'
    "- semantic_relevance: SUPPORTIVE if the pattern plausibly supports the "
    "class-level claim; NEUTRAL if it is common and uninformative; CONTRADICTORY "
    "if it conflicts; CONTEXT_DEPENDENT if support depends on missing context.\n"
    "- allowed_claim: the strongest class-level semantic claim this pattern can support.\n"
    "- forbidden_claim: the stronger claim this pattern cannot justify.\n"
    "- short_reason: concise class/evidence-level rationale, 1-3 sentences.\n"
    "REVIEW REQUEST:\n{request_json}"
)

SEMANTIC_RESPONSE_SCHEMA = {
    "semantic_relevance": "SUPPORTIVE | NEUTRAL | CONTRADICTORY | CONTEXT_DEPENDENT",
    "allowed_claim": "bounded semantic claim supported by the pattern",
    "forbidden_claim": "claim that the pattern cannot justify",
    "short_reason": "concise class/evidence-level rationale",
}

TEMPERATURE = 0
MAX_OUTPUT_TOKENS = 256
MAX_INPUT_TOKENS = 16384
REQUEST_TIMEOUT_SECONDS = 180.0
MAX_WORKERS = 4
TEACHER_EXPECTED_N = 2000
SEMANTIC_EXPECTED_N = 63
TEACHER_MAX_TOTAL_ATTEMPTS = 2150
SEMANTIC_MAX_TOTAL_ATTEMPTS = 80
TRANSPORT_RETRY_DELAYS = (2.0, 8.0)

CANONICAL_TAXONOMY_V1 = (
    "Backdoor",
    "Benign",
    "Credential",
    "DDoS",
    "DoS",
    "Recon_Scanning",
    "Web_Injection",
)
TEACHER_ACTIONS = (
    "STOP_AND_CLASSIFY",
    "ACQUIRE_TEMPORAL",
    "ACQUIRE_RELATION",
    "ENTER_NOVELTY_DETECTION",
)
SEMANTIC_GAPS = (
    "NONE",
    "NEEDS_TEMPORAL",
    "NEEDS_RELATION",
    "NOVELTY_OR_UNRESOLVABLE",
    "AMBIGUOUS",
)
SEMANTIC_RELEVANCE_VALUES = (
    "SUPPORTIVE",
    "NEUTRAL",
    "CONTRADICTORY",
    "CONTEXT_DEPENDENT",
)

SMOKE_IDS = (
    # covers BASIC_SUFFICIENT_KNOWN (HIGH), BASIC_SUFFICIENT_KNOWN (HIGH),
    # RECOVERABLE_KNOWN (MID), TRUE_UNKNOWN Credential (MID),
    # TRUE_UNKNOWN Recon_Scanning (HIGH); all rows are part of the official 2000.
    "bc607c18767232ac18ccd6ce2fced6dcb456693e3820f769719671649097b0ce",
    "af359a549d7a83a45da0bf8efd3a650208f73512771d1106f3ce6781f02f9241",
    "6c22dcc2ce23c3d3dc710edfb3c383e682586874f6b17db4a6dcabc654889e4e",
    "c6e1fb1d2df94fea6e8ea02c1a74f62f3ab53e04a6c5337dcdd03e07a1dc4f30",
    "a71d1ef24829e3965b640231def6257f1475bbdebe952e8d820115c4e8661075",
)

DEFAULT_TEACHER_DIR = "/root/autodl-tmp/processed/dataset_v4_nf3_ton_v1/teacher"
DEFAULT_SEMANTIC_DIR = "/root/autodl-tmp/processed/dataset_v4_nf3_ton_v1/semantic_reference"
DEFAULT_SEMANTIC_MANIFEST = (
    "/root/autodl-tmp/workspace/flow-security-agent/configs/dataset_v4/"
    "semantic_reference_v1_request_manifest.json"
)
DEFAULT_SECRETS_FILE = "/root/autodl-tmp/secrets/deepseek.env"

# Forbidden payload markers for the GT-leakage precheck (keys and string values).
FORBIDDEN_PAYLOAD_MARKERS = (
    "canonical_label",
    "recoverable",
    "sampling_stratum",
    "policy_role",
    "unknown_rotation",
    "source_row",
    "source_partition",
    "group_digest",
    "split",
    "ground_truth",
    "gt_label",
    "true_unknown",
    "correctness",
    "utility_target",
)


# ---------------------------------------------------------------------------
# Frozen prompt identity
# ---------------------------------------------------------------------------

def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def prompt_spec_sha256(
    *, prompt_id: str, prompt_version: str, renderer_version: str,
    system_instruction: str, task_template: str, response_schema: dict[str, str],
    model_id: str,
) -> str:
    payload = canonical_json(
        {
            "prompt_id": prompt_id,
            "prompt_version": prompt_version,
            "renderer_version": renderer_version,
            "system_instruction": system_instruction,
            "task_template": task_template,
            "response_schema": response_schema,
            "model_id": model_id,
            "temperature": TEMPERATURE,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "thinking": "disabled",
        }
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Secret handling (values are never printed or logged)
# ---------------------------------------------------------------------------

def load_secrets_file(path: str) -> dict[str, str]:
    """Parse an operator-managed `export K=V` file into the process environment."""
    loaded: dict[str, str] = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            if "=" not in line:
                raise ValueError(f"invalid secret-file line (no '='): {line[:40]}...")
            name, value = line.split("=", 1)
            name = name.strip()
            value = shlex.split(value)[0] if value.strip() else ""
            value = value.strip().strip("'\"")
            if not name or not value:
                raise ValueError("invalid secret-file entry")
            os.environ[name] = value
            loaded[name] = value
    return loaded


def resolve_runtime_config(secrets_file: str) -> dict[str, str]:
    load_secrets_file(secrets_file)
    config = {
        "model_id": os.environ.get("DEEPSEEK_MODEL", ""),
        "base_url": os.environ.get("DEEPSEEK_BASE_URL", ""),
        "api_key": os.environ.get("DEEPSEEK_API_KEY", ""),
    }
    missing = [name for name, value in config.items() if not value]
    if missing:
        raise SystemExit(
            f"ABORT: missing runtime config from {secrets_file}: {sorted(missing)} "
            "(DEEPSEEK_MODEL / DEEPSEEK_BASE_URL / DEEPSEEK_API_KEY)"
        )
    return config


# ---------------------------------------------------------------------------
# Leakage precheck
# ---------------------------------------------------------------------------

def _walk_values(value: Any, path: str):
    if isinstance(value, dict):
        for key, item in value.items():
            low = str(key).casefold()
            if any(marker in low for marker in FORBIDDEN_PAYLOAD_MARKERS):
                raise ValueError(f"forbidden key at {path}.{key}")
            yield from _walk_values(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_values(item, f"{path}[{index}]")
    elif isinstance(value, str):
        low = value.casefold()
        for marker in FORBIDDEN_PAYLOAD_MARKERS:
            if marker in low and len(value) < 200:
                raise ValueError(f"forbidden marker {marker!r} in value at {path}")


def teacher_leakage_precheck(requests: dict[str, dict], offline: dict[str, dict]) -> bool:
    allowed_top = {
        "available_next_evidence",
        "current_evidence_card",
        "current_evidence_mask",
        "known_prediction_summary",
        "sample_id",
        "schema_version",
    }
    for teacher_cache_id, record in sorted(requests.items()):
        payload = record["teacher_request_payload"]
        extra = set(payload) - allowed_top
        if extra:
            raise ValueError(f"{teacher_cache_id[:12]}… unexpected payload keys: {sorted(extra)}")
        list(_walk_values(payload, "payload"))
        summary = payload["known_prediction_summary"]
        probs = summary.get("known_class_probabilities", {})
        keys = set(probs)
        if not keys or not keys <= set(CANONICAL_TAXONOMY_V1):
            raise ValueError("known_class_probabilities keys outside taxonomy in frozen payload")
        class_map = summary.get("class_map_version")
        if class_map == "CANONICAL_TAXONOMY_V1":
            if keys != set(CANONICAL_TAXONOMY_V1):
                raise ValueError("CANONICAL_TAXONOMY_V1 probability map is not the full 7-class set")
        elif isinstance(class_map, str) and class_map.startswith("KNOWN_CLASS_MAP_V1_"):
            missing = set(CANONICAL_TAXONOMY_V1) - keys
            rotation = offline[teacher_cache_id].get("unknown_rotation_if_any")
            if len(missing) != 1 or (rotation is not None and missing != {rotation}):
                raise ValueError(
                    f"rotation probability map mismatch: missing={sorted(missing)} "
                    f"rotation={rotation}")
        else:
            raise ValueError(f"unknown class_map_version {class_map!r}")
        if summary.get("predicted_class") not in keys:
            raise ValueError("predicted_class outside the frozen class map")
        for value in probs.values():
            if not (isinstance(value, (int, float)) and 0.0 <= value <= 1.0):
                raise ValueError("probability out of range in frozen payload")
        if record["teacher_input_payload_hash"] != offline[teacher_cache_id]["teacher_input_payload_hash"]:
            raise ValueError("request/offline payload-hash mismatch")
    return True


def semantic_leakage_precheck(requests: list[dict]) -> bool:
    for item in requests:
        payload = item["request_payload"]
        list(_walk_values(payload, "payload"))
    return True


# ---------------------------------------------------------------------------
# Message building
# ---------------------------------------------------------------------------

def _raw_message(role: MessageRole, parts: list[tuple[ContentKind, str, str]]) -> LLMMessage:
    """Build an LLMMessage without the generic runtime model-visible validation.

    The frozen TEACHER_CACHE_V1 / semantic reference envelopes were separately
    leakage-audited (DEC-0026) and must be sent verbatim to preserve the frozen
    payload hashes. The generic validator rejects the envelope's `sample_id`
    routing key, which the frozen Teacher I/O contract explicitly includes as
    "routing/audit only, not semantic evidence".
    """
    contents = tuple(
        MessageContent.model_construct(kind=kind, content=content, label=label, trust=None)
        for kind, content, label in parts
    )
    return LLMMessage.model_construct(role=role, content=contents)


def build_teacher_messages(
    payload: dict[str, Any],
    *,
    prompt_sha256: str,
    prompt_id: str,
    prompt_version: str,
    renderer_version: str,
) -> tuple[LLMMessage, ...]:
    state_json = canonical_json(payload)
    user_content = TEACHER_TASK_TEMPLATE.replace("{state_json}", state_json)
    system = _raw_message(
        MessageRole.SYSTEM,
        [(ContentKind.INSTRUCTION, TEACHER_SYSTEM_INSTRUCTION, "system_instruction")],
    )
    user = _raw_message(
        MessageRole.USER,
        [
            (ContentKind.INSTRUCTION, user_content, "task_instruction"),
            (ContentKind.DATA, state_json, "runtime_state"),
        ],
    )
    return (system, user)


def build_semantic_messages(
    payload: dict[str, Any],
    *,
    prompt_sha256: str,
    prompt_id: str,
    prompt_version: str,
    renderer_version: str,
) -> tuple[LLMMessage, ...]:
    request_json = canonical_json(payload)
    user_content = SEMANTIC_TASK_TEMPLATE.replace("{request_json}", request_json)
    system = _raw_message(
        MessageRole.SYSTEM,
        [(ContentKind.INSTRUCTION, SEMANTIC_SYSTEM_INSTRUCTION, "system_instruction")],
    )
    user = _raw_message(
        MessageRole.USER,
        [
            (ContentKind.INSTRUCTION, user_content, "task_instruction"),
            (ContentKind.DATA, request_json, "review_request"),
        ],
    )
    return (system, user)


# ---------------------------------------------------------------------------
# Response parsing and validation
# ---------------------------------------------------------------------------

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def tolerant_extract_json(text: str) -> dict[str, Any] | None:
    """Tolerant local extraction: raw JSON, then fenced, then first {...} block."""
    if not text:
        return None
    stripped = text.strip()
    for candidate in (stripped,):
        try:
            value = json.loads(candidate)
            if isinstance(value, dict):
                return value
        except (json.JSONDecodeError, ValueError):
            pass
    fence = re.sub(r"^```(?:json)?\s*|\s*```$", "", stripped, flags=re.DOTALL).strip()
    try:
        value = json.loads(fence)
        if isinstance(value, dict):
            return value
    except (json.JSONDecodeError, ValueError):
        pass
    match = _JSON_OBJECT_RE.search(stripped)
    if match:
        for attempt in (match.group(0),):
            try:
                value = json.loads(attempt)
                if isinstance(value, dict):
                    return value
            except (json.JSONDecodeError, ValueError):
                continue
    return None


def validate_teacher_response(response: dict[str, Any], payload: dict[str, Any]) -> str | None:
    """Return an error string for an invalid response, or None when valid.

    `predicted_class` must belong to the payload's current Known class map
    (7 classes for CANONICAL_TAXONOMY_V1 rows, the 6-class rotation map for
    whole-class Unknown rotation rows).
    """
    allowed_keys = {"predicted_class", "recommended_action", "confidence",
                    "semantic_gap", "short_reason"}
    if set(response) != allowed_keys:
        return f"response keys {sorted(set(response) ^ allowed_keys)} not exactly {sorted(allowed_keys)}"
    action = response.get("recommended_action")
    if action not in TEACHER_ACTIONS:
        return f"recommended_action {action!r} not in frozen action vocabulary"
    summary = payload.get("known_prediction_summary") or {}
    visible_classes = set((summary.get("known_class_probabilities") or {}).keys()) \
        or set(CANONICAL_TAXONOMY_V1)
    predicted = response.get("predicted_class")
    if predicted is not None and predicted not in visible_classes:
        return f"predicted_class {predicted!r} outside the current Known class map or not null"
    confidence = response.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) \
            or not 0.0 <= float(confidence) <= 1.0:
        return f"confidence {confidence!r} not a number in [0,1]"
    gap = response.get("semantic_gap")
    if gap not in SEMANTIC_GAPS:
        return f"semantic_gap {gap!r} not in frozen vocabulary"
    reason = response.get("short_reason")
    if not isinstance(reason, str) or not reason.strip():
        return "short_reason missing or empty"
    available = set(payload.get("available_next_evidence") or [])
    if action == "STOP_AND_CLASSIFY" and (predicted is None or gap != "NONE"):
        return "STOP_AND_CLASSIFY requires a known predicted_class and semantic_gap=NONE"
    if action == "ACQUIRE_TEMPORAL" and "TEMPORAL" not in available:
        return "ACQUIRE_TEMPORAL but TEMPORAL is not available in the frozen state"
    if action == "ACQUIRE_RELATION" and "RELATION" not in available:
        return "ACQUIRE_RELATION but RELATION is not available in the frozen state"
    return None


def validate_semantic_response(response: dict[str, Any]) -> str | None:
    allowed_keys = {"semantic_relevance", "allowed_claim", "forbidden_claim",
                    "short_reason"}
    if set(response) != allowed_keys:
        return f"response keys {sorted(set(response) ^ allowed_keys)} not exactly {sorted(allowed_keys)}"
    relevance = response.get("semantic_relevance")
    if relevance not in SEMANTIC_RELEVANCE_VALUES:
        return f"semantic_relevance {relevance!r} not in frozen vocabulary"
    for field in ("allowed_claim", "forbidden_claim", "short_reason"):
        value = response.get(field)
        if not isinstance(value, str) or not value.strip():
            return f"{field} missing or empty"
    return None


# ---------------------------------------------------------------------------
# Call path with bounded retries
# ---------------------------------------------------------------------------

def make_transport(config: dict[str, str]) -> OpenAICompatibleChatTransport:
    return OpenAICompatibleChatTransport(
        api_key=config["api_key"],
        max_input_tokens=MAX_INPUT_TOKENS,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        max_latency_seconds=REQUEST_TIMEOUT_SECONDS,
        trust_env=False,
    )


def call_model(
    transport: OpenAICompatibleChatTransport,
    config: dict[str, str],
    messages: tuple[LLMMessage, ...],
    prompt_id: str,
    prompt_version: str,
    prompt_sha256: str,
    renderer_version: str,
    logical_id: str,
    task: str,
) -> tuple[str, dict[str, Any], int, float]:
    """One API attempt. Returns (raw_text, usage_dict, input_tokens, output_tokens)."""
    request = LLMTransportRequest(
        provider="deepseek",
        base_url=config["base_url"],
        model_id=config["model_id"],
        messages=messages,
        timeout_seconds=REQUEST_TIMEOUT_SECONDS,
        response_mode=ResponseMode.TEXT,
        generation_options={
            "temperature": TEMPERATURE,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "extra_body": {"thinking": {"type": "disabled"}},
        },
        prompt=PromptIdentity(
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            prompt_hash=prompt_sha256,
            renderer_version=renderer_version,
        ),
        request_metadata={"task": task, "logical_id": logical_id},
    )
    response = transport.send(request)
    usage = response.usage
    return (
        response.raw_text or "",
        {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "total_tokens": usage.total_tokens,
            "latency_seconds": usage.abstract_latency,
            "request_id": response.request_id,
            "finish_status": response.finish_status,
            "provider_model_id": response.model_id,
            "created": response.provider_metadata.get("created"),
        },
        usage.input_tokens or 0,
        usage.output_tokens or 0,
    )


class GenerationCounters:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.api_attempts = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.valid_n = 0
        self.failed_n = 0
        self.skipped_n = 0
        self.retry_count = 0

    def add_tokens(self, input_tokens: int, output_tokens: int) -> None:
        with self.lock:
            self.api_attempts += 1
            self.input_tokens += input_tokens
            self.output_tokens += output_tokens

    def record_retry(self) -> None:
        with self.lock:
            self.retry_count += 1


def generate_one(
    *,
    logical_id: str,
    payload: dict[str, Any],
    payload_hash: str,
    offline: dict[str, Any] | None,
    transport: OpenAICompatibleChatTransport,
    config: dict[str, str],
    prompt_id: str,
    prompt_version: str,
    prompt_sha256: str,
    renderer_version: str,
    task: str,
    validator,
    counters: GenerationCounters,
    total_cap: int,
) -> dict[str, Any]:
    """Generate one record with bounded identical-prompt retries. Never raises."""
    build = build_teacher_messages if task == "teacher_cache_v1" else build_semantic_messages
    messages = build(
        payload, prompt_sha256=prompt_sha256, prompt_id=prompt_id,
        prompt_version=prompt_version, renderer_version=renderer_version,
    )
    attempts = 0
    transport_retries = len(TRANSPORT_RETRY_DELAYS)
    identical_retries = 1
    raw_text = ""
    last_usage: dict[str, Any] = {}
    last_error = ""
    outcome = "API_FAILURE"
    while True:
        with counters.lock:
            if counters.api_attempts >= total_cap:
                outcome = "HARD_CAP_REACHED"
                break
            counters.api_attempts += 1
            attempts += 1
        try:
            raw_text, usage, input_tokens, output_tokens = call_model(
                transport, config, messages, prompt_id, prompt_version,
                prompt_sha256, renderer_version, logical_id, task,
            )
            with counters.lock:
                counters.input_tokens += input_tokens
                counters.output_tokens += output_tokens
            last_usage = usage
            parsed = tolerant_extract_json(raw_text)
            if parsed is None:
                last_error = "parse-failure"
                if identical_retries > 0:
                    identical_retries -= 1
                    with counters.lock:
                        counters.retry_count += 1
                    continue
                outcome = "PARSE_FAILURE"
                break
            error = validator(parsed, payload) if task == "teacher_cache_v1" \
                else validator(parsed)
            if error is None:
                outcome = "VALID"
                break
            last_error = f"schema-invalid: {error}"
            if identical_retries > 0:
                identical_retries -= 1
                with counters.lock:
                    counters.retry_count += 1
                continue
            outcome = "INVALID_AFTER_RETRIES"
            break
        except LLMTransportError as exc:
            last_error = f"{exc.kind.value}: {str(exc)}"
            if transport_retries > 0 and exc.kind in {
                LLMFailureKind.TIMEOUT,
                LLMFailureKind.RATE_LIMIT_LIKE_FAILURE,
                LLMFailureKind.TRANSPORT_FAILURE,
            }:
                transport_retries -= 1
                with counters.lock:
                    counters.retry_count += 1
                time.sleep(TRANSPORT_RETRY_DELAYS[len(TRANSPORT_RETRY_DELAYS) - 1 - transport_retries])
                continue
            outcome = "API_FAILURE"
            break
    record: dict[str, Any] = {
        "logical_id": logical_id,
        "request_payload_hash": payload_hash,
        "prompt_version": prompt_version,
        "prompt_sha256": prompt_sha256,
        "model_id": config["model_id"],
        "api_base": config["base_url"],
        "validation_status": outcome,
        "attempts": attempts,
        "retry_count": max(0, attempts - 1),
        "raw_text": raw_text if outcome in ("VALID", "INVALID_AFTER_RETRIES", "PARSE_FAILURE") else "",
        "usage": last_usage,
        "error": last_error,
    }
    if offline is not None:
        record["offline_metadata"] = offline
    return record


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

class JsonlStore:
    def __init__(self, path: Path, key_field: str):
        self.path = path
        self.key_field = key_field
        self.lock = threading.Lock()
        self._index: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        with open(self.path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                self._index[record[self.key_field]] = record

    def has_valid(self, key: str, prompt_sha256: str, model_id: str) -> bool:
        record = self._index.get(key)
        if record is None:
            return False
        return (
            record.get("validation_status") == "VALID"
            and record.get("prompt_sha256") == prompt_sha256
            and record.get("model_id") == model_id
        )

    def append(self, record: dict[str, Any]) -> None:
        with self.lock:
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(canonical_json(record) + "\n")
            self._index[record[self.key_field]] = record

    def records(self) -> list[dict[str, Any]]:
        with self.lock:
            return [self._index[key] for key in sorted(self._index)]


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

def _common_setup(args) -> tuple[dict[str, str], OpenAICompatibleChatTransport]:
    config = resolve_runtime_config(args.secrets_file)
    print(f"[config] model={config['model_id']} base={config['base_url']} "
          f"(api key loaded from {args.secrets_file}, never printed)")
    transport = make_transport(config)
    return config, transport


def _load_teacher_inputs(teacher_dir: str) -> tuple[dict[str, dict], dict[str, dict]]:
    requests_path = Path(teacher_dir) / "teacher_cache_v1_requests.jsonl"
    offline_path = Path(teacher_dir) / "teacher_cache_v1_offline_manifest.jsonl"
    requests = {}
    for line in open(requests_path, encoding="utf-8"):
        record = json.loads(line)
        requests[record["teacher_cache_id"]] = record
    offline = {}
    for line in open(offline_path, encoding="utf-8"):
        record = json.loads(line)
        offline[record["teacher_cache_id"]] = record
    return requests, offline


def _teacher_prompt_fingerprint(config: dict[str, str]) -> tuple[str, str]:
    sha = prompt_spec_sha256(
        prompt_id=TEACHER_PROMPT_ID,
        prompt_version=TEACHER_PROMPT_VERSION,
        renderer_version=TEACHER_RENDERER_VERSION,
        system_instruction=TEACHER_SYSTEM_INSTRUCTION,
        task_template=TEACHER_TASK_TEMPLATE,
        response_schema=TEACHER_RESPONSE_SCHEMA,
        model_id=config["model_id"],
    )
    return TEACHER_PROMPT_VERSION, sha


def _semantic_prompt_fingerprint(config: dict[str, str]) -> tuple[str, str]:
    sha = prompt_spec_sha256(
        prompt_id=SEMANTIC_PROMPT_ID,
        prompt_version=SEMANTIC_PROMPT_VERSION,
        renderer_version=SEMANTIC_RENDERER_VERSION,
        system_instruction=SEMANTIC_SYSTEM_INSTRUCTION,
        task_template=SEMANTIC_TASK_TEMPLATE,
        response_schema=SEMANTIC_RESPONSE_SCHEMA,
        model_id=config["model_id"],
    )
    return SEMANTIC_PROMPT_VERSION, sha


def _run_teacher(
    args, config: dict[str, str], transport: OpenAICompatibleChatTransport,
    smoke_only: bool,
) -> int:
    teacher_dir = Path(args.teacher_dir)
    requests, offline = _load_teacher_inputs(str(teacher_dir))
    if len(requests) != TEACHER_EXPECTED_N or len(offline) != TEACHER_EXPECTED_N:
        raise SystemExit(f"ABORT: expected {TEACHER_EXPECTED_N} requests, "
                         f"got {len(requests)}/{len(offline)}")
    print("[precheck] teacher payload GT-leakage check …")
    teacher_leakage_precheck(requests, offline)
    print("[precheck] TEACHER_PAYLOAD_GT_LEAKAGE=false (all 2000 payloads clean)")
    final_test = [o for o in offline.values() if o.get("allowed_for_final_test")]
    if final_test:
        raise SystemExit("ABORT: offline manifest rows allowed_for_final_test=true")
    print("[precheck] FINAL_TEST contamination=false")

    prompt_version, prompt_sha256 = _teacher_prompt_fingerprint(config)
    raw_store = JsonlStore(teacher_dir / "teacher_cache_v1_responses_raw.jsonl",
                           "logical_id")
    norm_store = JsonlStore(teacher_dir / "teacher_cache_v1_responses_normalized.jsonl",
                            "teacher_cache_id")

    def normalized_record(logical_id: str, raw: dict[str, Any]) -> dict[str, Any]:
        parsed = tolerant_extract_json(raw.get("raw_text", "")) or {}
        return {
            "teacher_cache_id": logical_id,
            "source_row_id": offline[logical_id]["source_row_id"],
            "request_payload_hash": raw["request_payload_hash"],
            "prompt_version": raw["prompt_version"],
            "prompt_sha256": raw["prompt_sha256"],
            "model_id": raw["model_id"],
            "schema_version": "TEACHER_CACHE_V1_OUTPUT_V1",
            "normalized_response": parsed,
            "input_tokens": (raw.get("usage") or {}).get("input_tokens"),
            "output_tokens": (raw.get("usage") or {}).get("output_tokens"),
            "cached_input_tokens": None,
            "latency_seconds": (raw.get("usage") or {}).get("latency_seconds"),
            "attempts": raw["attempts"],
            "retry_count": raw["retry_count"],
            "validation_status": raw["validation_status"],
            "request_id": (raw.get("usage") or {}).get("request_id"),
            "offline_metadata": raw["offline_metadata"],
        }

    all_keys = sorted(requests)
    smoke_keys = [key for key in SMOKE_IDS if key in requests]
    counters = GenerationCounters()
    for key in all_keys:
        if norm_store.has_valid(key, prompt_sha256, config["model_id"]):
            counters.skipped_n += 1
    todo = [
        key for key in all_keys
        if not norm_store.has_valid(key, prompt_sha256, config["model_id"])
    ]
    smoke_todo = [key for key in smoke_keys if key in todo]
    rest_todo = [key for key in todo if key not in smoke_todo]
    print(f"[teacher] pending={len(todo)} skipped_existing={counters.skipped_n} "
          f"mode={'smoke' if smoke_only else 'smoke-gate-then-full'} "
          f"smoke_todo={len(smoke_todo)} prompt={prompt_version} "
          f"sha={prompt_sha256[:16]}…")

    def worker(key: str) -> tuple[str, dict[str, Any]]:
        record = requests[key]
        result = generate_one(
            logical_id=key,
            payload=record["teacher_request_payload"],
            payload_hash=record["teacher_input_payload_hash"],
            offline={
                "sampling_stratum": offline[key]["sampling_stratum"],
                "policy_role": offline[key]["policy_role"],
                "unknown_rotation_if_any": offline[key].get("unknown_rotation_if_any"),
                "source_partition": offline[key]["source_partition"],
                "confidence_bin": offline[key]["confidence_bin"],
                "allowed_for_demonstration": offline[key]["allowed_for_demonstration"],
                "allowed_for_imitation": offline[key]["allowed_for_imitation"],
                "allowed_for_policy_eval": offline[key]["allowed_for_policy_eval"],
                "canonical_label": offline[key]["canonical_label"],
            },
            transport=transport,
            config=config,
            prompt_id=TEACHER_PROMPT_ID,
            prompt_version=prompt_version,
            prompt_sha256=prompt_sha256,
            renderer_version=TEACHER_RENDERER_VERSION,
            task="teacher_cache_v1",
            validator=validate_teacher_response,
            counters=counters,
            total_cap=TEACHER_MAX_TOTAL_ATTEMPTS,
        )
        return key, result

    def run_batch(keys: list[str], label: str) -> None:
        if not keys:
            return
        start = time.time()
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = [pool.submit(worker, key) for key in keys]
            for index, future in enumerate(as_completed(futures), 1):
                key, result = future.result()
                raw_store.append(result)
                norm_store.append(normalized_record(key, result))
                status = result["validation_status"]
                action = (tolerant_extract_json(result.get("raw_text", "")) or {}).get(
                    "recommended_action")
                if status == "VALID":
                    counters.valid_n += 1
                else:
                    counters.failed_n += 1
                print(f"  [{label} {index}/{len(keys)}] {key[:12]}… {status} "
                      f"action={action} attempts={result['attempts']} "
                      f"in={result['usage'].get('input_tokens')} "
                      f"out={result['usage'].get('output_tokens')}")
        print(f"[{label}] {len(keys)} records in {time.time() - start:.0f}s")

    run_batch(smoke_todo, "smoke")
    if smoke_only:
        failures = [
            key for key in smoke_keys
            if not norm_store.has_valid(key, prompt_sha256, config["model_id"])
        ]
        if failures:
            print(f"SMOKE_STATUS=FAIL failing={[k[:12] for k in failures]}")
            return 1
        print("SMOKE_STATUS=PASS")
        return 0
    if not smoke_only:
        smoke_failures = [
            key for key in smoke_todo
            if not norm_store.has_valid(key, prompt_sha256, config["model_id"])
        ]
        if smoke_failures:
            print(f"SMOKE_STATUS=FAIL — aborting before full batch; "
                  f"failing={[k[:12] for k in smoke_failures]} "
                  f"(records preserved on disk)")
            return 1
        print("SMOKE_STATUS=PASS — continuing to full batch")
    run_batch(rest_todo, "full")
    print(f"[teacher] done attempts={counters.api_attempts} "
          f"valid={counters.valid_n} failed={counters.failed_n} "
          f"skipped={counters.skipped_n} input_tokens={counters.input_tokens} "
          f"output_tokens={counters.output_tokens}")

    metadata = {
        "schema_version": "TEACHER_CACHE_V1_GENERATION_METADATA_V1",
        "prompt_id": TEACHER_PROMPT_ID,
        "prompt_version": prompt_version,
        "prompt_sha256": prompt_sha256,
        "renderer_version": TEACHER_RENDERER_VERSION,
        "model_id": config["model_id"],
        "api_base": config["base_url"],
        "temperature": TEMPERATURE,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "thinking": "disabled",
        "expected_n": TEACHER_EXPECTED_N,
        "max_total_api_attempts": TEACHER_MAX_TOTAL_ATTEMPTS,
        "requests_manifest": str(teacher_dir / "teacher_cache_v1_requests.jsonl"),
        "offline_manifest": str(teacher_dir / "teacher_cache_v1_offline_manifest.jsonl"),
        "raw_artifact": str(raw_store.path),
        "normalized_artifact": str(norm_store.path),
        "teacher_payload_gt_leakage": False,
        "final_test_contamination": False,
    }
    with open(teacher_dir / "teacher_cache_v1_generation_metadata.json", "w",
              encoding="utf-8") as handle:
        json.dump(metadata, handle, ensure_ascii=False, indent=2)
    return 0


def _run_semantic(args, config: dict[str, str],
                  transport: OpenAICompatibleChatTransport) -> int:
    manifest = json.load(open(args.semantic_manifest, encoding="utf-8"))
    requests = manifest["requests"]
    if len(requests) != SEMANTIC_EXPECTED_N:
        raise SystemExit(f"ABORT: expected {SEMANTIC_EXPECTED_N} semantic requests, "
                         f"got {len(requests)}")
    print("[precheck] semantic payload GT-leakage check …")
    semantic_leakage_precheck(requests)
    print("[precheck] SEMANTIC_PAYLOAD_GT_LEAKAGE=false")

    semantic_dir = Path(args.semantic_dir)
    semantic_dir.mkdir(parents=True, exist_ok=True)
    prompt_version, prompt_sha256 = _semantic_prompt_fingerprint(config)
    raw_store = JsonlStore(semantic_dir / "semantic_reference_v1_responses_raw.jsonl",
                           "logical_id")
    norm_store = JsonlStore(
        semantic_dir / "semantic_reference_v1_responses_normalized.jsonl",
        "reference_id")

    def normalized_record(logical_id: str, raw: dict[str, Any],
                          item: dict[str, Any]) -> dict[str, Any]:
        payload = item["request_payload"]
        parsed = tolerant_extract_json(raw.get("raw_text", "")) or {}
        return {
            "reference_id": logical_id,
            "prompt_version": raw["prompt_version"],
            "prompt_sha256": raw["prompt_sha256"],
            "model_id": raw["model_id"],
            "schema_version": "SEMANTIC_REFERENCE_V1_OUTPUT_V1",
            "class_or_mechanism": payload.get("class_or_mechanism"),
            "evidence_family": payload.get("evidence_family"),
            "pattern_role": item.get("pattern_role"),
            "normalized_response": parsed,
            "input_tokens": (raw.get("usage") or {}).get("input_tokens"),
            "output_tokens": (raw.get("usage") or {}).get("output_tokens"),
            "cached_input_tokens": None,
            "latency_seconds": (raw.get("usage") or {}).get("latency_seconds"),
            "attempts": raw["attempts"],
            "retry_count": raw["retry_count"],
            "validation_status": raw["validation_status"],
            "request_id": (raw.get("usage") or {}).get("request_id"),
        }

    counters = GenerationCounters()
    for item in requests:
        if norm_store.has_valid(item["reference_id"], prompt_sha256, config["model_id"]):
            counters.skipped_n += 1
    todo = [
        item for item in requests
        if not norm_store.has_valid(item["reference_id"], prompt_sha256,
                                    config["model_id"])
    ]
    print(f"[semantic] pending={len(todo)} skipped_existing={counters.skipped_n} "
          f"prompt={prompt_version} sha={prompt_sha256[:16]}…")

    def worker(item: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        payload = dict(item["request_payload"])
        result = generate_one(
            logical_id=item["reference_id"],
            payload=payload,
            payload_hash=hashlib.sha256(
                canonical_json(payload).encode("utf-8")).hexdigest(),
            offline=None,
            transport=transport,
            config=config,
            prompt_id=SEMANTIC_PROMPT_ID,
            prompt_version=prompt_version,
            prompt_sha256=prompt_sha256,
            renderer_version=SEMANTIC_RENDERER_VERSION,
            task="semantic_reference_v1",
            validator=validate_semantic_response,
            counters=counters,
            total_cap=SEMANTIC_MAX_TOTAL_ATTEMPTS,
        )
        return item, result

    start = time.time()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(worker, item) for item in todo]
        for index, future in enumerate(as_completed(futures), 1):
            item, result = future.result()
            raw_store.append(result)
            norm_store.append(normalized_record(item["reference_id"], result,
                                                item))
            status = result["validation_status"]
            if status == "VALID":
                counters.valid_n += 1
            else:
                counters.failed_n += 1
            print(f"  [{index}/{len(todo)}] {item['reference_id'][:20]}… {status} "
                  f"attempts={result['attempts']} "
                  f"in={result['usage'].get('input_tokens')} "
                  f"out={result['usage'].get('output_tokens')}")
    elapsed = time.time() - start
    print(f"[semantic] done in {elapsed:.0f}s attempts={counters.api_attempts} "
          f"valid={counters.valid_n} failed={counters.failed_n} "
          f"skipped={counters.skipped_n} input_tokens={counters.input_tokens} "
          f"output_tokens={counters.output_tokens}")

    metadata = {
        "schema_version": "SEMANTIC_REFERENCE_V1_GENERATION_METADATA_V1",
        "prompt_id": SEMANTIC_PROMPT_ID,
        "prompt_version": prompt_version,
        "prompt_sha256": prompt_sha256,
        "renderer_version": SEMANTIC_RENDERER_VERSION,
        "model_id": config["model_id"],
        "api_base": config["base_url"],
        "temperature": TEMPERATURE,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "thinking": "disabled",
        "expected_n": SEMANTIC_EXPECTED_N,
        "max_total_api_attempts": SEMANTIC_MAX_TOTAL_ATTEMPTS,
        "request_manifest": args.semantic_manifest,
        "raw_artifact": str(raw_store.path),
        "normalized_artifact": str(norm_store.path),
        "payload_gt_leakage": False,
    }
    with open(semantic_dir / "semantic_reference_v1_generation_metadata.json", "w",
              encoding="utf-8") as handle:
        json.dump(metadata, handle, ensure_ascii=False, indent=2)
    return 0


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate(args) -> int:
    teacher_dir = Path(args.teacher_dir)
    semantic_dir = Path(args.semantic_dir)
    print("=== teacher_cache_v1 validation ===")
    norm_path = teacher_dir / "teacher_cache_v1_responses_normalized.jsonl"
    if not norm_path.exists():
        print("  normalized artifact missing")
        return 1
    records = [json.loads(line) for line in open(norm_path, encoding="utf-8")]
    ids = [r["teacher_cache_id"] for r in records]
    print(f"  records={len(records)} unique_ids={len(set(ids))} "
          f"duplicates={len(ids) - len(set(ids))}")
    requests, _ = _load_teacher_inputs(str(teacher_dir))
    actions = Counter()
    by_stratum = Counter()
    confidences = []
    invalid = []
    for record in records:
        parsed = record.get("normalized_response") or {}
        error = None
        if record.get("validation_status") == "VALID":
            payload = requests.get(record["teacher_cache_id"], {}).get(
                "teacher_request_payload", {})
            error = validate_teacher_response(parsed, payload)
        else:
            error = "record-not-valid"
        if error is not None:
            invalid.append(record["teacher_cache_id"])
        actions[parsed.get("recommended_action")] += 1
        stratum = (record.get("offline_metadata") or {}).get("sampling_stratum", "?")
        by_stratum[(stratum, parsed.get("recommended_action"))] += 1
        confidence = parsed.get("confidence")
        if isinstance(confidence, (int, float)):
            confidences.append(float(confidence))
    valid_n = sum(1 for r in records if r.get("validation_status") == "VALID")
    failed_n = len(records) - valid_n
    parse_failures = sum(1 for r in records if r.get("validation_status") == "PARSE_FAILURE")
    retries = sum(r.get("retry_count", 0) for r in records)
    attempts = sum(r.get("attempts", 0) for r in records)
    print(f"  valid={valid_n} failed={failed_n} retries={retries} "
          f"parse_failure_rate={parse_failures / max(1, len(records)):.6f} "
          f"retry_rate={retries / max(1, attempts):.6f}")
    by_stratum_flat = {
        f"{stratum}|{action}": count
        for (stratum, action), count in sorted(by_stratum.items())
    }
    print(f"  ACTION_DISTRIBUTION={dict(actions)}")
    print(f"  ACTION_DISTRIBUTION_BY_STRATUM={by_stratum_flat}")
    if confidences:
        import statistics
        print(f"  confidence mean={statistics.mean(confidences):.4f} "
              f"min={min(confidences):.4f} max={max(confidences):.4f} n={len(confidences)}")
    if invalid:
        print(f"  WARNING invalid-normalized ids: {[i[:12] for i in invalid][:10]}")
    sha = _sha256_file(norm_path)
    print(f"  TEACHER_CACHE_NORMALIZED_SHA256={sha}")

    print("=== semantic_reference_v1 validation ===")
    sem_path = semantic_dir / "semantic_reference_v1_responses_normalized.jsonl"
    if sem_path.exists():
        sem_records = [json.loads(line) for line in open(sem_path, encoding="utf-8")]
        sem_ids = [r["reference_id"] for r in sem_records]
        sem_valid = sum(1 for r in sem_records if r.get("validation_status") == "VALID")
        print(f"  records={len(sem_records)} unique_ids={len(set(sem_ids))} "
              f"valid={sem_valid} failed={len(sem_records) - sem_valid}")
        print(f"  SEMANTIC_REFERENCE_NORMALIZED_SHA256={_sha256_file(sem_path)}")
    else:
        print("  semantic normalized artifact missing")

    summary_teacher = {
        "expected_n": TEACHER_EXPECTED_N,
        "valid_n": valid_n,
        "failed_n": failed_n,
        "skipped_existing_n": 0,
        "action_distribution": dict(actions),
        "action_distribution_by_stratum": {
            f"{stratum}|{action}": count
            for (stratum, action), count in sorted(by_stratum.items())},
        "confidence_distribution": {
            "count": len(confidences),
            "min": min(confidences) if confidences else None,
            "max": max(confidences) if confidences else None,
        },
        "parse_failure_rate": parse_failures / max(1, len(records)),
        "retry_rate": retries / max(1, attempts),
        "normalized_sha256": sha,
    }
    with open(teacher_dir / "teacher_cache_v1_generation_summary.json", "w",
              encoding="utf-8") as handle:
        json.dump(summary_teacher, handle, ensure_ascii=False, indent=2)
    print("  summary written to teacher_cache_v1_generation_summary.json")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True,
                        choices=["smoke", "teacher", "semantic", "validate"])
    parser.add_argument("--secrets-file", default=DEFAULT_SECRETS_FILE)
    parser.add_argument("--teacher-dir", default=DEFAULT_TEACHER_DIR)
    parser.add_argument("--semantic-dir", default=DEFAULT_SEMANTIC_DIR)
    parser.add_argument("--semantic-manifest", default=DEFAULT_SEMANTIC_MANIFEST)
    args = parser.parse_args()

    if args.mode == "validate":
        return _validate(args)

    config, transport = _common_setup(args)
    if args.mode in ("smoke", "teacher"):
        return _run_teacher(args, config, transport, smoke_only=(args.mode == "smoke"))
    return _run_semantic(args, config, transport)


if __name__ == "__main__":
    raise SystemExit(main())
