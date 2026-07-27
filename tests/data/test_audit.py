from pathlib import Path

from flowsec.data.audit import audit_csv
from flowsec.data.schema import DatasetContract, FeatureRole, FieldContract


def _contract() -> DatasetContract:
    return DatasetContract(
        dataset="fixture",
        version="1",
        doi="fixture-doi",
        expected_extracted_feature_count=3,
        binary_label_field="Label",
        multiclass_label_field="Attack",
        expected_binary_values=(0, 1),
        expected_multiclass_values=("Benign", "Scanning"),
        categorical_fields=("Label", "Attack"),
        fields=(
            FieldContract(name="FLOW_START_MILLISECONDS", dtype="int64", role=FeatureRole.CONTEXT_ONLY),
            FieldContract(name="FLOW_END_MILLISECONDS", dtype="int64", role=FeatureRole.CONTEXT_ONLY),
            FieldContract(name="VALUE", dtype="int64", role=FeatureRole.MODEL_FEATURE),
            FieldContract(name="Label", dtype="int64", role=FeatureRole.LABEL),
            FieldContract(name="Attack", dtype="string", role=FeatureRole.LABEL),
        ),
    )


def test_audit_counts_labels_quality_and_exact_duplicates(tmp_path: Path) -> None:
    csv_path = tmp_path / "fixture.csv"
    csv_path.write_text(
        "FLOW_START_MILLISECONDS,FLOW_END_MILLISECONDS,VALUE,Label,Attack\n"
        "1000,1001,0,0,Benign\n"
        "2000,2001,2,1,Scanning\n"
        "2000,2001,2,1,Scanning\n",
        encoding="utf-8",
    )

    result = audit_csv(csv_path, _contract(), duplicate_temp_parent=tmp_path)

    assert result["row_count"] == 3
    assert result["binary_distribution"] == {"0": 1, "1": 2}
    assert result["multiclass_distribution"] == {"Benign": 1, "Scanning": 2}
    assert result["timestamp_order_violations"] == 0
    assert result["binary_attack_mismatch_rows"] == 0
    assert result["duplicates"]["duplicate_rows_beyond_first"] == 1
    assert result["duplicates"]["duplicate_groups"] == 1
