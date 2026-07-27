from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from flowsec.llm.fingerprint import sha256_json


class FeatureRole(StrEnum):
    MODEL_FEATURE = "model_feature"
    GROUPING_ONLY = "grouping_only"
    CONTEXT_ONLY = "context_only"
    LABEL = "label"
    IDENTIFIER = "identifier"
    METADATA = "metadata"
    EXCLUDED = "excluded"


class FieldContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    dtype: str = Field(min_length=1)
    role: FeatureRole
    description: str = ""
    allowed_uses: tuple[str, ...] = ()


class DatasetContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset: str = Field(min_length=1)
    version: str = Field(min_length=1)
    doi: str = Field(min_length=1)
    expected_extracted_feature_count: int = Field(gt=0)
    binary_label_field: str
    multiclass_label_field: str
    expected_binary_values: tuple[int, ...]
    expected_multiclass_values: tuple[str, ...]
    canonical_multiclass_mapping: dict[str, str] = Field(default_factory=dict)
    fields: tuple[FieldContract, ...]
    categorical_fields: tuple[str, ...] = ()
    near_constant_threshold: float = Field(default=0.999, gt=0, le=1)

    @model_validator(mode="after")
    def validate_contract(self) -> "DatasetContract":
        names = [field.name for field in self.fields]
        if len(names) != len(set(names)):
            raise ValueError("field names must be unique")
        known = set(names)
        for required in (self.binary_label_field, self.multiclass_label_field):
            if required not in known:
                raise ValueError(f"label field is not declared: {required}")
        unknown_categorical = set(self.categorical_fields) - known
        if unknown_categorical:
            raise ValueError(f"unknown categorical fields: {sorted(unknown_categorical)}")
        unknown_mapping_keys = set(self.canonical_multiclass_mapping) - set(
            self.expected_multiclass_values
        )
        if unknown_mapping_keys:
            raise ValueError(
                f"canonical mapping contains unknown raw labels: {sorted(unknown_mapping_keys)}"
            )
        feature_count = sum(field.role not in {FeatureRole.LABEL, FeatureRole.METADATA} for field in self.fields)
        if feature_count != self.expected_extracted_feature_count:
            raise ValueError(
                "declared extracted-feature count mismatch: "
                f"{feature_count} != {self.expected_extracted_feature_count}"
            )
        return self

    @property
    def field_names(self) -> tuple[str, ...]:
        return tuple(field.name for field in self.fields)

    @property
    def model_feature_names(self) -> tuple[str, ...]:
        return tuple(field.name for field in self.fields if field.role is FeatureRole.MODEL_FEATURE)

    @property
    def fingerprint(self) -> str:
        return sha256_json(self.model_dump(mode="json"))

    def validate_actual_schema(self, actual: list[tuple[str, str]]) -> None:
        expected = [(field.name, field.dtype) for field in self.fields]
        if actual != expected:
            raise ValueError({"expected": expected, "actual": actual})

    def validate_no_model_leakage(self) -> None:
        forbidden_names = {
            self.binary_label_field,
            self.multiclass_label_field,
            "sample_id",
            "group_id",
            "capture_id",
            "dataset_id",
            "source_file",
            "source_row",
        }
        forbidden = forbidden_names.intersection(self.model_feature_names)
        if forbidden:
            raise ValueError(f"forbidden model features: {sorted(forbidden)}")
        raw_identity = {
            "IPV4_SRC_ADDR",
            "IPV4_DST_ADDR",
            "FLOW_START_MILLISECONDS",
            "FLOW_END_MILLISECONDS",
        }
        leaked_identity = raw_identity.intersection(self.model_feature_names)
        if leaked_identity:
            raise ValueError(f"raw identity/time fields leaked into model features: {sorted(leaked_identity)}")


def load_dataset_contract(path: Path) -> DatasetContract:
    document: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    contract = DatasetContract.model_validate(document)
    contract.validate_no_model_leakage()
    return contract
