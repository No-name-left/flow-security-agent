from pathlib import Path

from flowsec.data.schema import FeatureRole, load_dataset_contract


def test_nf_ton_contract_matches_frozen_feature_roles() -> None:
    contract = load_dataset_contract(Path("configs/data/nf_ton_iot_v3.yaml"))

    assert len(contract.fields) == 55
    assert len(contract.model_feature_names) == 49
    assert contract.expected_extracted_feature_count == 53
    roles = {field.name: field.role for field in contract.fields}
    assert roles["IPV4_SRC_ADDR"] is FeatureRole.CONTEXT_ONLY
    assert roles["FLOW_START_MILLISECONDS"] is FeatureRole.CONTEXT_ONLY
    assert roles["Label"] is FeatureRole.LABEL
    assert roles["Attack"] is FeatureRole.LABEL
    assert "IPV4_SRC_ADDR" not in contract.model_feature_names
    assert "FLOW_START_MILLISECONDS" not in contract.model_feature_names
