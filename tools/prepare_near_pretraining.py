#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from flowsec.training.audit import audit_u_final_isolation
from flowsec.training.contracts import EvidenceSnapshot
from flowsec.training.corpus import build_snapshot_universe, finalize_sft_corpus
from flowsec.training.materialization import materialize_application_payload
from flowsec.training.rag import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_EMBEDDING_REVISION,
    TransformersDenseEmbedder,
    build_rag_index,
    load_rag_index,
)
from flowsec.training.teacher import (
    annotate_snapshots,
    deepseek_api_preflight,
    make_live_teacher_client,
    select_teacher_pilot,
)


def _roots() -> tuple[Path, Path]:
    configured = os.environ.get("ARTIFACT_ROOT")
    if not configured:
        raise RuntimeError("ARTIFACT_ROOT must identify the Git-external Production root")
    artifact_root = Path(configured)
    return artifact_root / "edge_split_revision_v2", artifact_root / "near_pretraining_v1"


def _embedder(model_path: Path) -> TransformersDenseEmbedder:
    return TransformersDenseEmbedder(
        model_path,
        model_id=DEFAULT_EMBEDDING_MODEL,
        revision=DEFAULT_EMBEDDING_REVISION,
    )


def main() -> int:
    production_root, output_root = _roots()
    parser = argparse.ArgumentParser(
        description="Prepare checkpointed Near pre-training artifacts without starting SFT or RL."
    )
    parser.add_argument(
        "phase",
        choices=(
            "application-payload",
            "rag",
            "corpus",
            "provider-status",
            "teacher-pilot",
            "teacher-bulk",
            "finalize-sft",
            "isolation-audit",
        ),
    )
    parser.add_argument("--production-root", type=Path, default=production_root)
    parser.add_argument("--output-root", type=Path, default=output_root)
    parser.add_argument(
        "--embedding-model-path",
        type=Path,
        default=Path(
            os.environ.get(
                "NEAR_EMBEDDING_MODEL_PATH",
                str(output_root.parent.parent / "models/all-MiniLM-L6-v2"),
            )
        ),
    )
    parser.add_argument(
        "--source-manifest",
        type=Path,
        default=Path("configs/rag/near_kb_sources_v1.json"),
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.phase == "application-payload":
        result = materialize_application_payload(
            args.production_root, args.output_root, force=args.force
        )
    elif args.phase == "rag":
        result = build_rag_index(
            args.source_manifest,
            args.output_root / "rag",
            embedder=_embedder(args.embedding_model_path),
            retrieved_at="2026-08-12",
        )
    elif args.phase == "corpus":
        index = load_rag_index(
            args.output_root / "rag", embedder=_embedder(args.embedding_model_path)
        )
        result = build_snapshot_universe(
            args.production_root,
            args.output_root,
            args.output_root,
            rag_index=index,
        )
    elif args.phase == "provider-status":
        result = deepseek_api_preflight()
        status_path = args.output_root / "manifests/deepseek_provider_status.json"
        status_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = status_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(status_path)
    elif args.phase in {"teacher-pilot", "teacher-bulk"}:
        snapshot_path = args.output_root / "sft_corpus/evidence_snapshot_universe_v1.jsonl"
        snapshots = [
            EvidenceSnapshot.model_validate_json(line)
            for line in snapshot_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        client = make_live_teacher_client()
        if args.phase == "teacher-pilot":
            snapshots = select_teacher_pilot(snapshots, target=250)
            destination = args.output_root / "teacher_annotations/pilot"
        else:
            pilot_manifest = args.output_root / "teacher_annotations/pilot/manifest.json"
            if not pilot_manifest.is_file():
                raise RuntimeError("Teacher bulk requires a completed pilot manifest")
            pilot = json.loads(pilot_manifest.read_text(encoding="utf-8"))
            if pilot.get("status") != "PASS":
                raise RuntimeError("Teacher bulk requires a zero-quarantine pilot PASS")
            destination = args.output_root / "teacher_annotations/bulk"
        result = annotate_snapshots(snapshots, destination, client=client, concurrency=4)
    elif args.phase == "finalize-sft":
        qwen_path = os.environ.get("QWEN_MODEL_PATH")
        if not qwen_path:
            raise RuntimeError("QWEN_MODEL_PATH is required to finalize token-audited SFT corpus")
        from transformers import AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(qwen_path, local_files_only=True)
        result = finalize_sft_corpus(
            args.output_root / "manifests/snapshot_corpus_rl_manifest.json",
            args.output_root / "teacher_annotations/bulk",
            args.output_root / "sft_corpus/final",
            args.production_root / "manifests/edge_known_unknown_presets.json",
            tokenize=lambda text: tokenizer(text, add_special_tokens=True)["input_ids"],
        )
    else:
        result = audit_u_final_isolation(args.production_root, args.output_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
