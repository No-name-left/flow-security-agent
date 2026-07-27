from __future__ import annotations

import argparse
from pathlib import Path

from flowsec.data.grouping import (
    collect_gap_profiles,
    evaluate_group_candidates,
    write_grouping_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze NF-ToN-IoT-v3 grouping candidates")
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument(
        "--gap-output",
        type=Path,
        default=Path("artifacts/data/nf_ton_iot_v3/group_gap_profiles.json"),
    )
    parser.add_argument(
        "--candidate-output",
        type=Path,
        default=Path("artifacts/data/nf_ton_iot_v3/group_candidates.json"),
    )
    parser.add_argument(
        "--threshold-ms",
        action="append",
        default=[],
        metavar="CANDIDATE=MS",
        help="Evaluate a candidate at a chosen inactivity threshold; repeat as needed",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    profiles = collect_gap_profiles(args.csv)
    write_grouping_json(args.gap_output, profiles)
    print(f"wrote {args.gap_output}")
    if args.threshold_ms:
        thresholds: dict[str, int] = {}
        for item in args.threshold_ms:
            name, raw_value = item.split("=", 1)
            thresholds[name] = int(raw_value)
        candidates = evaluate_group_candidates(args.csv, thresholds)
        write_grouping_json(args.candidate_output, candidates)
        print(f"wrote {args.candidate_output}")


if __name__ == "__main__":
    main()
