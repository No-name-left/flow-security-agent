from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from flowsec.training.train_near_sft import (
    LAUNCHER_VERSION,
    initialize_run_directory,
    validate_resume_metadata,
)


def _metadata() -> dict[str, object]:
    return {
        "launcher_version": LAUNCHER_VERSION,
        "config_sha256": "a" * 64,
        "model_id": "Qwen/Qwen3.5-9B",
        "model_revision": "b" * 40,
        "tokenizer_revision": "b" * 40,
        "seed": 20260809,
        "corpus_sha256": "c" * 64,
        "corpus_manifest_digest": "d" * 64,
        "validation_sha256": "e" * 64,
        "validation_manifest_digest": "f" * 64,
        "supervision_contract": "CLASSIFICATION_SUFFICIENCY_DECOUPLED_V1",
        "audit_digests": {"teacher_quality_manifest": "1" * 64},
    }


def test_run_directory_refuses_overwrite_and_resume_is_digest_strict(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("version: fixture\n", encoding="utf-8")
    run = initialize_run_directory(
        tmp_path / "runs",
        "run-1",
        _metadata(),
        config,
        resume=None,
    )
    assert (run / "config.snapshot.yaml").is_file()
    assert (run / "run_manifest.json").is_file()
    with pytest.raises(FileExistsError):
        initialize_run_directory(tmp_path / "runs", "run-1", _metadata(), config, resume=None)
    assert initialize_run_directory(
        tmp_path / "unused", "ignored", _metadata(), config, resume=run
    ) == run
    changed = {**_metadata(), "corpus_sha256": "0" * 64}
    with pytest.raises(RuntimeError, match="incompatible"):
        validate_resume_metadata(changed, _metadata())
    changed_contract = {**_metadata(), "supervision_contract": "COUPLED"}
    with pytest.raises(RuntimeError, match="supervision_contract"):
        validate_resume_metadata(changed_contract, _metadata())
    changed_audit = {**_metadata(), "audit_digests": {"teacher_quality_manifest": "2" * 64}}
    with pytest.raises(RuntimeError, match="audit_digests"):
        validate_resume_metadata(changed_audit, _metadata())


def test_formal_config_declares_all_reproducibility_and_safety_fields() -> None:
    config = yaml.safe_load(Path("configs/training/near_sft_config_v1.yaml").read_text())
    assert config["model"]["revision"] == config["model"]["tokenizer_revision"]
    assert config["architecture"]["pooling"] == "ATTENTION_MASKED_MEAN_V1"
    assert config["architecture"]["traffic_expert_prompt"] == "TRAFFIC_EXPERT_PROMPT_V2"
    assert config["schedule"]["shuffle"] == "deterministic_per_epoch"
    assert config["schedule"]["save_steps"] > 0
    assert config["schedule"]["save_total_limit"] == 2
    assert config["validation"]["primary_checkpoint_metric"] == "known_validation_macro_f1"
    assert config["validation"]["test_usage"] == "final_results_only"
    assert config["validation"]["u_final_usage"] == "forbidden"
    assert config["resume"]["compatibility"].startswith("strict_")
