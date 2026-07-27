from pathlib import Path

from flowsec.data.grouping import collect_gap_profiles, evaluate_group_candidates


def test_grouping_profiles_and_episode_boundaries(tmp_path: Path) -> None:
    csv_path = tmp_path / "fixture.csv"
    csv_path.write_text(
        "FLOW_START_MILLISECONDS,IPV4_SRC_ADDR,IPV4_DST_ADDR,Attack\n"
        "0,10.0.0.1,10.0.0.2,Benign\n"
        "1000,10.0.0.1,10.0.0.2,Benign\n"
        "12000,10.0.0.1,10.0.0.2,Scanning\n"
        "13000,10.0.0.2,10.0.0.1,Scanning\n",
        encoding="utf-8",
    )

    profile = collect_gap_profiles(
        csv_path,
        candidate_names=("directed_pair_episode",),
        sample_every=1,
    )
    assert profile["global_timestamp_order_violations"] == 0
    assert profile["candidates"]["directed_pair_episode"]["key_count"] == 2

    result = evaluate_group_candidates(
        csv_path,
        {"directed_pair_episode": 5000, "unordered_pair_episode": 5000},
    )
    directed = result["candidates"]["directed_pair_episode"]
    unordered = result["candidates"]["unordered_pair_episode"]
    assert directed["group_count"] == 3
    assert unordered["group_count"] == 2
    assert directed["per_label_group_count"] == {"Benign": 1, "Scanning": 2}
