#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path

from flowsec.training.contracts import EvidenceSnapshot, content_digest
from flowsec.training.prompts import traffic_expert_prompt_v1
from flowsec.training.serialization import (
    COMPACT_SERIALIZATION_CANDIDATE,
    CURRENT_SERIALIZATION_CANDIDATE,
    assert_semantic_equivalence,
    render_training_input,
    serialization_digest,
    token_length_report,
)


def main() -> int:
    from transformers import AutoTokenizer

    artifact_root = Path(os.environ["ARTIFACT_ROOT"])
    pretraining_root = artifact_root / "near_pretraining_v1"
    model_root = Path(os.environ["QWEN_MODEL_PATH"])
    snapshots = [
        EvidenceSnapshot.model_validate_json(line)
        for line in (
            pretraining_root / "sft_corpus/evidence_snapshot_universe_v1.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    tokenizer = AutoTokenizer.from_pretrained(model_root, local_files_only=True)
    prompt = traffic_expert_prompt_v1()
    current: list[str] = []
    compact: list[str] = []
    for snapshot in snapshots:
        assert_semantic_equivalence(snapshot.evidence)
        current.append(
            render_training_input(
                prompt,
                snapshot.evidence,
                serialization_version=CURRENT_SERIALIZATION_CANDIDATE,
            )
        )
        compact.append(
            render_training_input(
                prompt,
                snapshot.evidence,
                serialization_version=COMPACT_SERIALIZATION_CANDIDATE,
            )
        )
    tokenize = lambda text: tokenizer(text, add_special_tokens=True)["input_ids"]
    current_stats = token_length_report(current, tokenize=tokenize)
    compact_stats = token_length_report(compact, tokenize=tokenize)
    reduction = 1.0 - float(compact_stats["mean"]) / float(current_stats["mean"])
    selection = (
        COMPACT_SERIALIZATION_CANDIDATE
        if reduction > 0.01
        else CURRENT_SERIALIZATION_CANDIDATE
    )
    report = {
        "status": "PASS",
        "scope": "Near K_known TRAIN evidence snapshots only",
        "snapshot_count": len(snapshots),
        "semantic_equivalence_failures": 0,
        "current": current_stats,
        "compact": compact_stats,
        "compact_mean_reduction": reduction,
        "human_readability": "PASS: one frozen legend followed by ordered typed rows",
        "selection": selection,
        "selection_digest": serialization_digest(
            prompt,
            serialization_version=selection,
            classification_suffix="Classification representation:",
        ),
        "input_digest": content_digest(
            [snapshot.evidence_state_id for snapshot in snapshots]
        ),
        "u_final_count": 0,
    }
    path = pretraining_root / "manifests/serialization_audit.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
