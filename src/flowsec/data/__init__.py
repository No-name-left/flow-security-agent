"""Flow dataset audit, event matching, and split-contract utilities."""

from .event_matching import EventIndex, FlowIdentity, MatchResult, MatchStatus, duplicate_signature
from .ground_truth import GroundTruthEvent, GroundTruthSchema, GroundTruthSchemaError
from .schema import DatasetContract, FeatureRole, load_dataset_contract

__all__ = [
    "DatasetContract",
    "EventIndex",
    "FeatureRole",
    "FlowIdentity",
    "GroundTruthEvent",
    "GroundTruthSchema",
    "GroundTruthSchemaError",
    "MatchResult",
    "MatchStatus",
    "duplicate_signature",
    "load_dataset_contract",
]
