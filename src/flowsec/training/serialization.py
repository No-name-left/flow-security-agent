from __future__ import annotations

import statistics
from collections.abc import Callable, Iterable
from typing import Any

from .contracts import EvidenceEnvelope, canonical_json, content_digest
from .prompts import FrozenPrompt, render_prompt_header


CURRENT_SERIALIZATION_CANDIDATE = "CURRENT_SAFE_JSON_V1"
COMPACT_SERIALIZATION_CANDIDATE = "COMPACT_SAFE_EVIDENCE_V1"


def _semantic_item(item: EvidenceEnvelope) -> dict[str, Any]:
    return item.model_dump(mode="json")


def serialize_current(evidence: tuple[EvidenceEnvelope, ...]) -> str:
    return canonical_json(
        {
            "evidence": [_semantic_item(item) for item in evidence],
            "evidence_count": len(evidence),
        }
    )


def serialize_compact(evidence: tuple[EvidenceEnvelope, ...]) -> str:
    """Lossless compact rendering with a single stable key legend."""

    rows = []
    for item in evidence:
        rows.append(
            [
                item.evidence_id,
                item.evidence_type,
                item.domain.value,
                item.trust.value,
                item.provenance,
                item.metadata,
                item.content,
            ]
        )
    return canonical_json(
        {
            "format": "i,type,domain,trust,provenance,metadata,content",
            "items": rows,
        }
    )


def decode_compact(text: str) -> list[dict[str, Any]]:
    import json

    value = json.loads(text)
    if value.get("format") != "i,type,domain,trust,provenance,metadata,content":
        raise ValueError("unexpected compact evidence format")
    output: list[dict[str, Any]] = []
    for row in value.get("items", []):
        if not isinstance(row, list) or len(row) != 7:
            raise ValueError("invalid compact evidence row")
        output.append(
            {
                "evidence_id": row[0],
                "evidence_type": row[1],
                "domain": row[2],
                "trust": row[3],
                "provenance": row[4],
                "metadata": row[5],
                "content": row[6],
            }
        )
    return output


def assert_semantic_equivalence(evidence: tuple[EvidenceEnvelope, ...]) -> None:
    import json

    current = json.loads(serialize_current(evidence))["evidence"]
    compact = decode_compact(serialize_compact(evidence))
    if current != compact:
        raise ValueError("compact serialization is not semantically lossless")


def render_training_input(
    prompt: FrozenPrompt,
    evidence: tuple[EvidenceEnvelope, ...],
    *,
    serialization_version: str,
    classification_suffix: str = "Classification representation:",
) -> str:
    if serialization_version == CURRENT_SERIALIZATION_CANDIDATE:
        serialized = serialize_current(evidence)
    elif serialization_version == COMPACT_SERIALIZATION_CANDIDATE:
        assert_semantic_equivalence(evidence)
        serialized = serialize_compact(evidence)
    else:
        raise ValueError(f"unsupported serialization version: {serialization_version}")
    return "\n".join(
        (
            render_prompt_header(prompt),
            "MODEL_SAFE_EVIDENCE:",
            serialized,
            classification_suffix,
        )
    )


def serialization_digest(
    prompt: FrozenPrompt,
    *,
    serialization_version: str,
    classification_suffix: str,
) -> str:
    return content_digest(
        {
            "prompt_digest": prompt.digest,
            "serialization_version": serialization_version,
            "classification_suffix": classification_suffix,
        }
    )


def percentile(values: list[int], quantile: float) -> int:
    if not values:
        raise ValueError("cannot compute a percentile of an empty set")
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * quantile))
    return ordered[index]


def token_length_report(
    texts: Iterable[str],
    *,
    tokenize: Callable[[str], list[int]],
) -> dict[str, float | int]:
    lengths = [len(tokenize(text)) for text in texts]
    if not lengths:
        raise ValueError("token audit requires at least one input")
    return {
        "count": len(lengths),
        "mean": round(statistics.fmean(lengths), 3),
        "p50": percentile(lengths, 0.50),
        "p90": percentile(lengths, 0.90),
        "p95": percentile(lengths, 0.95),
        "p99": percentile(lengths, 0.99),
        "max": max(lengths),
    }
