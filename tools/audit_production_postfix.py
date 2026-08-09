#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from flowsec.production.postfix_audit import finalize_postfix_audit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--audit-dir", type=Path, required=True)
    parser.add_argument("--tracked-report-dir", type=Path)
    args = parser.parse_args()
    audit = finalize_postfix_audit(
        report_dir=args.report_dir,
        output_root=args.output_root,
        audit_dir=args.audit_dir,
    )
    if args.tracked_report_dir is not None:
        args.tracked_report_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            args.report_dir / "production_readiness.json",
            args.tracked_report_dir / "production_readiness.json",
        )
        shutil.copy2(
            args.audit_dir / "precommit_scientific_audit.json",
            args.tracked_report_dir / "postfix_precommit_scientific_audit.json",
        )
        shutil.copy2(
            args.audit_dir / "precommit_scientific_audit.md",
            args.tracked_report_dir / "postfix_precommit_scientific_audit.md",
        )
        shutil.copy2(
            args.report_dir / "final_production_freeze_report.md",
            args.tracked_report_dir / "final_production_freeze_report.md",
        )
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0 if audit["POSTFIX_PRECOMMIT_AUDIT"] == "PASS_WITH_LIMITATIONS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
