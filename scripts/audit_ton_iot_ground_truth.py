from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from flowsec.data.fingerprint import file_digest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inventory locally downloaded ToN-IoT Ground Truth")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/data/ton_iot_ground_truth.yaml"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    raw_directory = Path(config["local_raw_directory"])
    files = sorted(path for path in raw_directory.rglob("*") if path.is_file()) if raw_directory.exists() else []
    if not files:
        raise SystemExit(
            "No official Ground Truth files are present. Download only the official "
            "SecuityEvents_GroundTruth_datasets folder into "
            f"{raw_directory} and rerun; no schema or matching result has been inferred."
        )
    inventory = [
        {
            "path": path.relative_to(raw_directory).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": file_digest(path),
        }
        for path in files
    ]
    print(json.dumps(inventory, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
