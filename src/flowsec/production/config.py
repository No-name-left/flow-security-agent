from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from flowsec.production.schema import canonical_json


@dataclass(frozen=True, slots=True)
class ProductionConfig:
    path: Path
    values: dict[str, Any]
    config_hash: str

    @property
    def schema_version(self) -> str:
        return str(self.values["schema_version"])

    @property
    def edge(self) -> dict[str, Any]:
        return self.values["edge"]

    @property
    def iot23(self) -> dict[str, Any]:
        return self.values["iot23"]

    @property
    def processing(self) -> dict[str, Any]:
        return self.values["processing"]


def load_production_config(path: Path) -> ProductionConfig:
    values = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(values, dict):
        raise ValueError(f"production config must be an object: {path}")
    required = {"schema_version", "processing", "edge", "iot23"}
    missing = sorted(required - set(values))
    if missing:
        raise ValueError(f"production config missing keys: {missing}")
    config_hash = hashlib.sha256(canonical_json(values).encode("utf-8")).hexdigest()
    return ProductionConfig(path=path.resolve(), values=values, config_hash=config_hash)
