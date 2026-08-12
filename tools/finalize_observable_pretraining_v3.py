#!/usr/bin/env python3
"""Materialize the frozen Dataset-v3 SFT and known-validation assets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from flowsec.training.corpus_v3 import (
    build_sft_corpus,
    build_validation,
    update_token_audit,
    write_class_map,
)


DEFAULT_FREEZE = Path(
    "/root/autodl-tmp/processed/observable_dataset_v3_freeze/manifests/observable_dataset_v3_freeze.json"
)
DEFAULT_SNAPSHOTS = Path(
    "/root/autodl-tmp/processed/teacher_v2_observable_dataset_v3/manifests/teacher_v2_snapshot_manifest.json"
)
DEFAULT_ANNOTATIONS = Path(
    "/root/autodl-tmp/processed/teacher_v2_observable_dataset_v3/annotations/bulk"
)
DEFAULT_EVIDENCE = Path("/root/autodl-tmp/processed/observable_dataset_v3")
DEFAULT_OUTPUT = Path("/root/autodl-tmp/processed/near_pretraining_v3")
DEFAULT_CLASS_MAP = Path(
    "/root/autodl-tmp/processed/observable_dataset_v3_freeze/manifests/main_class_map.json"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("build", "token-audit"))
    parser.add_argument("--freeze-manifest", type=Path, default=DEFAULT_FREEZE)
    parser.add_argument("--snapshot-manifest", type=Path, default=DEFAULT_SNAPSHOTS)
    parser.add_argument("--annotation-root", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--class-map", type=Path, default=DEFAULT_CLASS_MAP)
    parser.add_argument("--tokenizer-path", type=Path)
    parser.add_argument("--max-sequence-length", type=int, default=8192)
    args = parser.parse_args()
    freeze = json.loads(args.freeze_manifest.read_text(encoding="utf-8"))
    classes = tuple(freeze["final_main_classes"])
    if args.mode == "build":
        write_class_map(args.class_map, classes)
        corpus = build_sft_corpus(
            snapshot_manifest_path=args.snapshot_manifest,
            annotation_root=args.annotation_root,
            freeze_manifest_path=args.freeze_manifest,
            output_root=args.output_root,
            classes=classes,
        )
        validation = build_validation(
            freeze_manifest_path=args.freeze_manifest,
            evidence_root=args.evidence_root,
            output_root=args.output_root,
            classes=classes,
        )
        print(
            "SFT_CORPUS_V3_BUILD=" + corpus["status"]
            + f" records={corpus['record_count']} sessions={corpus['unique_sessions']}"
            + f" validation={validation['record_count']}",
            flush=True,
        )
        return 0 if corpus["status"] == validation["status"] == "PASS" else 1

    if args.tokenizer_path is None:
        raise ValueError("token-audit requires --tokenizer-path")
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        args.tokenizer_path, local_files_only=True, trust_remote_code=True
    )
    audit = update_token_audit(
        corpus_manifest_path=args.output_root / "sft_corpus/final/manifest.json",
        validation_manifest_path=args.output_root / "validation/manifest.json",
        tokenize=lambda value: tokenizer(value, add_special_tokens=True)["input_ids"],
        max_sequence_length=args.max_sequence_length,
    )
    print(
        f"TOKENIZER_LENGTH_AUDIT={audit['status']} max={audit['corpus_max']} "
        f"overflow={audit['overflow_count']}",
        flush=True,
    )
    return 0 if audit["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
