from __future__ import annotations

import argparse
from pathlib import Path

from flowsec.data.audit import audit_csv, write_json
from flowsec.data.fingerprint import file_digest
from flowsec.data.schema import load_dataset_contract


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit the official NF-ToN-IoT-v3 CSV")
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path("configs/data/nf_ton_iot_v3.yaml"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/data/nf_ton_iot_v3/phase0_audit.json"),
    )
    parser.add_argument(
        "--duplicate-temp",
        type=Path,
        default=Path("artifacts/data/nf_ton_iot_v3"),
    )
    parser.add_argument(
        "--skip-duplicates",
        action="store_true",
        help="Skip the expensive exact duplicate-line pass",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    contract = load_dataset_contract(args.contract)
    result = audit_csv(
        args.csv,
        contract,
        duplicate_temp_parent=None if args.skip_duplicates else args.duplicate_temp,
    )
    result["source_sha256"] = file_digest(args.csv)
    write_json(args.output, result)
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
