import inspect

import numpy as np

from tools.run_nf3_feasibility_pilot import build_past_only_features
from tools.run_nf3_ton_openworld_pilot import (
    FORBIDDEN_SELECTOR_INPUTS,
    UTILITY_SELECTOR_FEATURE_CONTRACT,
    calibrate_known_confidence_threshold,
    iter_oof_masks,
    openworld_masks,
    ton_broad_label,
    utility_selector_matrix,
)
from tools import run_nf3_ton_openworld_pilot as ton_pilot


def test_ton_candidate_taxonomy_preserves_only_preregistered_classes() -> None:
    assert ton_broad_label("Backdoor") == "Backdoor"
    assert ton_broad_label("password") == "Credential"
    assert ton_broad_label("xss") == "Web_Injection"
    assert ton_broad_label("ransomware") is None
    assert ton_broad_label("mitm") is None


def test_oof_masks_never_train_on_an_evaluation_row_or_group() -> None:
    groups = np.array(["g0", "g0", "g1", "g2", "g2", "g3"], dtype=object)
    covered = np.zeros(len(groups), dtype=int)
    for _, train, evaluation in iter_oof_masks(groups, folds=3, seed=20260815):
        assert not np.any(train & evaluation)
        assert not (set(groups[train]) & set(groups[evaluation]))
        covered += evaluation.astype(int)
    assert covered.tolist() == [1, 1, 1, 1, 1, 1]


def test_whole_unknown_class_is_absent_from_train_and_calibration() -> None:
    labels = np.array(["Benign", "Credential", "DDoS", "Credential"])
    partitions = np.array(["train", "train", "calibration", "evaluation"])
    masks = openworld_masks(labels, partitions, holdout="Credential")
    assert "Credential" not in set(labels[masks["train"]])
    assert "Credential" not in set(labels[masks["calibration"]])
    assert labels[masks["unknown_evaluation"]].tolist() == ["Credential"]


def test_unknown_threshold_accepts_known_validation_scores_only() -> None:
    signature = inspect.signature(calibrate_known_confidence_threshold)
    assert list(signature.parameters) == ["known_confidence", "known_fpr"]
    known = np.array([0.3, 0.5, 0.8, 0.9])
    assert calibrate_known_confidence_threshold(known, known_fpr=0.25) == 0.5


def test_discrete_unknown_scores_do_not_exceed_known_fpr_through_ties() -> None:
    known_validation = np.array([0.0] * 90 + [0.2] * 10)
    novelty = np.array([0.0] * 90 + [0.2] * 10 + [0.9] * 5)
    unknown = np.array([False] * 100 + [True] * 5)
    metrics = ton_pilot._unknown_metrics(
        unknown, novelty, known_validation, known_fpr=0.05
    )
    assert metrics["known_fpr_observed"] <= 0.05
    assert metrics["threshold_operator"] == ">"


def test_past_only_evidence_excludes_equal_timestamp_and_future_rows() -> None:
    data = {
        "Attack": np.array(["Benign", "dos", "ddos"], dtype=object),
        "source_dataset": np.array(["ton", "ton", "ton"], dtype=object),
        "FLOW_START_MILLISECONDS": np.array([2_000, 1_000, 1_000]),
        "IPV4_SRC_ADDR": np.array(["s", "s", "s"], dtype=object),
        "IPV4_DST_ADDR": np.array(["future", "a", "b"], dtype=object),
        "L4_DST_PORT": np.array([80, 81, 82]),
        "IN_BYTES": np.array([10, 20, 30]),
        "OUT_BYTES": np.array([1, 2, 3]),
        "IN_PKTS": np.array([1, 1, 1]),
        "OUT_PKTS": np.array([1, 1, 1]),
    }
    features = build_past_only_features(data)
    assert features[1, 0] == 0
    assert features[2, 0] == 0
    assert features[0, 0] == 2


def test_masked_unknown_row_never_enters_known_training_history() -> None:
    data = {
        "Attack": np.array(["password", "Benign"], dtype=object),
        "source_dataset": np.array(["ton", "ton"], dtype=object),
        "FLOW_START_MILLISECONDS": np.array([1_000, 2_000]),
        "IPV4_SRC_ADDR": np.array(["s", "s"], dtype=object),
        "IPV4_DST_ADDR": np.array(["u", "k"], dtype=object),
        "L4_DST_PORT": np.array([80, 81]),
        "IN_BYTES": np.array([10, 20]),
        "OUT_BYTES": np.array([1, 2]),
        "IN_PKTS": np.array([1, 1]),
        "OUT_PKTS": np.array([1, 1]),
    }
    unmasked = build_past_only_features(data)
    masked = build_past_only_features(
        data, history_eligible=np.array([False, True])
    )
    assert unmasked[1, 0] == 1
    assert masked[1, 0] == 0


def test_utility_selector_contract_has_no_full_gt_future_or_identity_input() -> None:
    assert not set(UTILITY_SELECTOR_FEATURE_CONTRACT) & set(FORBIDDEN_SELECTOR_INPUTS)
    signature = inspect.signature(utility_selector_matrix)
    assert list(signature.parameters) == ["basic_matrix", "basic_probabilities"]
    basic = np.array([[1.0, 2.0], [3.0, 4.0]])
    probabilities = np.array([[0.8, 0.2], [0.4, 0.6]])
    output = utility_selector_matrix(basic, probabilities)
    assert output.shape == (2, 5)
