import numpy as np

from tools.run_nf3_feasibility_pilot import (
    RollingWindow,
    broad_label,
    build_past_only_features,
    stable_fold,
)


def test_broad_label_preserves_unmapped_and_maps_supported() -> None:
    assert broad_label("ton", "password") == "Credential"
    assert broad_label("cse", "Bot") == "Bot_C2"
    assert broad_label("unsw", "Backdoor") is None
    assert broad_label("bot", "Theft") is None


def test_stable_fold_is_deterministic() -> None:
    group = "ton|123|a|b"
    assert stable_fold(group) == stable_fold(group)


def test_rolling_window_expires_and_tracks_unique_relations() -> None:
    window = RollingWindow(10_000)
    window.add(1_000, "s", "d1", 80, 100, 2)
    window.add(2_000, "s", "d2", 443, 200, 3)
    values = window.features("s", "d1", 80)
    assert values[:5] == [2.0, 2.0, 2.0, 1.0, 1.0]
    assert values[8:] == [1.0, 1.0, 2.0]
    window.expire(12_000)
    values = window.features("s", "d1", 80)
    assert values[:5] == [1.0, 1.0, 1.0, 0.0, 0.0]


def test_past_only_features_exclude_equal_timestamp_rows() -> None:
    data = {
        "Attack": np.array(["Benign", "DoS", "DoS"], dtype=object),
        "source_dataset": np.array(["x", "x", "x"], dtype=object),
        "FLOW_START_MILLISECONDS": np.array([1_000, 1_000, 2_000]),
        "IPV4_SRC_ADDR": np.array(["s", "s", "s"], dtype=object),
        "IPV4_DST_ADDR": np.array(["d1", "d2", "d3"], dtype=object),
        "L4_DST_PORT": np.array([80, 443, 53]),
        "IN_BYTES": np.array([10, 20, 30]),
        "OUT_BYTES": np.array([1, 2, 3]),
        "IN_PKTS": np.array([1, 1, 1]),
        "OUT_PKTS": np.array([1, 1, 1]),
    }
    features = build_past_only_features(data)
    assert features[0, 0] == 0
    assert features[1, 0] == 0
    assert features[2, 0] == 2
