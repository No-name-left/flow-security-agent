#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from flowsec.production.determinism import compare_runs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean-a", type=Path, required=True)
    parser.add_argument("--clean-b", type=Path, required=True)
    parser.add_argument("--resumed", type=Path, required=True)
    parser.add_argument("--clean-a-manifests", type=Path)
    parser.add_argument("--clean-b-manifests", type=Path)
    parser.add_argument("--resumed-manifests", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare_runs(
        clean_a=args.clean_a,
        clean_b=args.clean_b,
        resumed=args.resumed,
        output=args.output,
        clean_a_manifests=args.clean_a_manifests,
        clean_b_manifests=args.clean_b_manifests,
        resumed_manifests=args.resumed_manifests,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["DETERMINISM_AUDIT_OK"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
