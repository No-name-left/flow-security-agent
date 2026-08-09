from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from flowsec.production.config import load_production_config
from flowsec.production.freeze import IntentionalInterruption, run_freeze


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Build schema-versioned production sessions and formal frozen manifests."
    )
    value.add_argument(
        "--config",
        type=Path,
        default=Path("configs/data/production_freeze_v1.yaml"),
    )
    value.add_argument(
        "--edge-root",
        type=Path,
        default=Path(
            "/root/autodl-tmp/datasets/edge_iiotset/raw/Edge-IIoTset dataset"
        ),
    )
    value.add_argument(
        "--edge-archive",
        type=Path,
        default=Path(
            "/root/autodl-tmp/datasets/edge_iiotset/archive/"
            "edgeiiotset-cyber-security-dataset-of-iot-iiot.zip"
        ),
    )
    value.add_argument(
        "--iot23-root",
        type=Path,
        default=Path("/root/autodl-tmp/datasets/iot23"),
    )
    value.add_argument(
        "--output-root",
        type=Path,
        default=Path("/root/autodl-tmp/processed/production_data_freeze_v1"),
    )
    value.add_argument(
        "--report-dir",
        type=Path,
        default=Path(
            "/root/autodl-tmp/experiments/production_data_freeze_20260809"
        ),
    )
    value.add_argument("--tshark-bin", default=shutil.which("tshark") or "tshark")
    value.add_argument("--mode", choices=("dry-run", "sample", "full"), default="full")
    value.add_argument("--sample-sessions", type=int, default=5000)
    value.add_argument("--dataset", choices=("all", "edge", "iot23"), default="all")
    value.add_argument("--capture", action="append", default=[])
    value.add_argument("--stop-after-captures", type=int)
    value.add_argument("--force", action="store_true")
    access = value.add_mutually_exclusive_group()
    access.add_argument(
        "--exclude-final-unknown",
        action="store_true",
        default=True,
        help="Default: keep U_final unavailable to normal training/development paths.",
    )
    access.add_argument(
        "--include-final-unknown",
        action="store_true",
        help="Reserved for separately authorized final-evaluation/support paths; freeze still writes it separately.",
    )
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.include_final_unknown and args.mode != "dry-run":
        raise SystemExit(
            "--include-final-unknown is not valid for production generation; use the "
            "separate final-evaluation/support loader after freeze"
        )
    selected = {"edge", "iot23"} if args.dataset == "all" else {args.dataset}
    try:
        result = run_freeze(
            config=load_production_config(args.config),
            edge_root=args.edge_root,
            edge_archive=args.edge_archive,
            iot_root=args.iot23_root,
            output_root=args.output_root,
            report_dir=args.report_dir,
            tshark_bin=args.tshark_bin,
            mode=args.mode,
            sample_sessions=args.sample_sessions,
            only_datasets=selected,
            only_captures=set(args.capture) or None,
            stop_after_captures=args.stop_after_captures,
            force=args.force,
        )
    except IntentionalInterruption as error:
        print(json.dumps({"status": "INTERRUPTED_FOR_RESUME_TEST", "reason": str(error)}))
        return 75
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
