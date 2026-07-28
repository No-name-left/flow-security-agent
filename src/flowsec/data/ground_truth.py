from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


class GroundTruthSchemaError(ValueError):
    """Raised when an official Ground Truth file cannot be normalized safely."""


@dataclass(frozen=True)
class GroundTruthSchema:
    start: str
    source_ip: str
    destination_ip: str
    label: str
    end: str | None = None
    protocol: str | None = None
    source_port: str | None = None
    destination_port: str | None = None
    event_id: str | None = None
    scenario_id: str | None = None
    timestamp_unit: str = "iso8601"
    timezone_name: str | None = None
    default_duration_ms: int | None = None

    def required_columns(self) -> set[str]:
        required = {self.start, self.source_ip, self.destination_ip, self.label}
        optional_mappings = (
            self.end,
            self.protocol,
            self.source_port,
            self.destination_port,
            self.event_id,
            self.scenario_id,
        )
        required.update(value for value in optional_mappings if value)
        return required


@dataclass(frozen=True)
class GroundTruthEvent:
    event_id: str
    start_ms: int
    end_ms: int
    source_ip: str
    destination_ip: str
    protocol: int | None
    source_port: int | None
    destination_port: int | None
    label: str
    scenario_id: str | None = None


def _parse_timestamp(value: str, schema: GroundTruthSchema) -> int:
    raw = value.strip()
    if not raw:
        raise GroundTruthSchemaError("Ground Truth timestamp is empty")
    if schema.timestamp_unit == "milliseconds":
        return int(raw)
    if schema.timestamp_unit == "seconds":
        return int(round(float(raw) * 1000))
    if schema.timestamp_unit != "iso8601":
        raise GroundTruthSchemaError(f"unsupported timestamp_unit: {schema.timestamp_unit}")
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        if schema.timezone_name != "UTC":
            raise GroundTruthSchemaError(
                "naive ISO timestamp requires an explicit supported timezone_name; only UTC is "
                "accepted until the official file documents another conversion"
            )
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(round(parsed.timestamp() * 1000))


def _parse_optional_int(value: str | None) -> int | None:
    if value is None:
        return None
    stripped = value.strip()
    if stripped in {"", "*", "any", "ANY", "-"}:
        return None
    return int(stripped)


def _parse_protocol(value: str | None) -> int | None:
    if value is None:
        return None
    stripped = value.strip().lower()
    if stripped in {"", "*", "any", "-"}:
        return None
    names = {"icmp": 1, "tcp": 6, "udp": 17, "ipv6-icmp": 58}
    if stripped in names:
        return names[stripped]
    if stripped.isdigit():
        return int(stripped)
    return _unsupported_protocol(stripped)


def _unsupported_protocol(value: str) -> int:
    raise GroundTruthSchemaError(f"unsupported protocol value: {value}")


def _stable_event_id(values: Mapping[str, Any]) -> str:
    payload = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "gt-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def normalize_ground_truth_rows(
    rows: Iterable[Mapping[str, str]],
    schema: GroundTruthSchema,
) -> list[GroundTruthEvent]:
    events: list[GroundTruthEvent] = []
    for row_number, row in enumerate(rows, start=2):
        missing = sorted(schema.required_columns() - set(row))
        if missing:
            raise GroundTruthSchemaError(
                f"Ground Truth row {row_number} is missing configured columns: {missing}"
            )
        start_ms = _parse_timestamp(row[schema.start], schema)
        if schema.end:
            end_ms = _parse_timestamp(row[schema.end], schema)
        elif schema.default_duration_ms is not None:
            end_ms = start_ms + schema.default_duration_ms
        else:
            raise GroundTruthSchemaError(
                "Ground Truth has no end column and no documented default_duration_ms"
            )
        if end_ms < start_ms:
            raise GroundTruthSchemaError(f"Ground Truth row {row_number} ends before it starts")

        normalized = {
            "start_ms": start_ms,
            "end_ms": end_ms,
            "source_ip": row[schema.source_ip].strip(),
            "destination_ip": row[schema.destination_ip].strip(),
            "protocol": _parse_protocol(row.get(schema.protocol) if schema.protocol else None),
            "source_port": _parse_optional_int(
                row.get(schema.source_port) if schema.source_port else None
            ),
            "destination_port": _parse_optional_int(
                row.get(schema.destination_port) if schema.destination_port else None
            ),
            "label": row[schema.label].strip(),
            "scenario_id": row.get(schema.scenario_id, "").strip() if schema.scenario_id else None,
        }
        explicit_id = row.get(schema.event_id, "").strip() if schema.event_id else ""
        events.append(
            GroundTruthEvent(
                event_id=explicit_id or _stable_event_id(normalized),
                **normalized,
            )
        )
    return events


def load_ground_truth_csv(path: Path, schema: GroundTruthSchema) -> list[GroundTruthEvent]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise GroundTruthSchemaError(f"Ground Truth file has no CSV header: {path}")
        missing = sorted(schema.required_columns() - set(reader.fieldnames))
        if missing:
            raise GroundTruthSchemaError(
                f"Ground Truth header is missing configured columns: {missing}; "
                f"observed={reader.fieldnames}"
            )
        return normalize_ground_truth_rows(reader, schema)
