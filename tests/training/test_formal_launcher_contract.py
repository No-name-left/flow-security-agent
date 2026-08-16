from __future__ import annotations

import json
import random
from pathlib import Path

import pytest
import yaml

from flowsec.training.train_near_sft import (
    LAUNCHER_VERSION,
    build_optimizer_step_log,
    capture_runtime_rng_state,
    formal_preflight,
    initialize_run_directory,
    restore_runtime_rng_state,
    seed_training_runtime,
    validate_formal_record_contract,
    validate_resume_metadata,
)


def _sft_record(*, sample: str, label: str, index: int, weight: float = 1.0) -> dict[str, object]:
    return {
        "sample_id": "fs1_" + sample * 40,
        "evidence_state_id": "state_" + sample * 24,
        "fine_label": label,
        "class_index": index,
        "classification_ce_eligible": True,
        "state_role": "primary",
        "serialized_model_input": "bounded traffic evidence",
        "evidence_state_target": {
            "behavior_summary": "One bounded traffic observation is visible.",
            "supporting_evidence": [],
            "missing_evidence": [],
            "evidence_sufficient": True,
            "gap_type": "none",
        },
        "stage_type": "initial",
        "available_capability_mask": [],
        "prompt_version": "fixture",
        "serialization_version": "fixture",
        "schema_version": "EVIDENCE_STATE_SCHEMA_V1",
        "teacher_annotation_digest": "a" * 64,
        "teacher_model": "fixture",
        "teacher_prompt_digest": "b" * 64,
        "teacher_request_id": "fixture-request",
        "source_split": "train",
        "source_role": "K_known",
        "dataset_digest": "c" * 64,
        "session_weight": weight,
    }


def _validation_record(*, sample: str, label: str, index: int) -> dict[str, object]:
    return {
        "sample_id": "fs1_" + sample * 40,
        "fine_label": label,
        "class_index": index,
        "serialized_model_input": "bounded validation evidence",
        "prompt_version": "fixture",
        "serialization_version": "fixture",
        "source_split": "validation",
        "source_role": "K_known",
        "dataset_digest": "d" * 64,
    }


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


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


def test_formal_runtime_rng_checkpoint_covers_python_numpy_and_torch() -> None:
    np = pytest.importorskip("numpy")
    torch = pytest.importorskip("torch")
    seed_training_runtime(20260809)
    state = capture_runtime_rng_state()
    assert set(state) == {"python", "numpy", "torch", "cuda"}
    expected = (
        random.random(),
        float(np.random.random()),
        torch.rand(4),
    )
    random.random()
    np.random.random()
    torch.rand(4)
    restore_runtime_rng_state(state)
    observed = (
        random.random(),
        float(np.random.random()),
        torch.rand(4),
    )
    assert observed[0] == expected[0]
    assert observed[1] == expected[1]
    assert torch.equal(observed[2], expected[2])


def test_optimizer_step_log_exposes_finite_formal_runtime_progress() -> None:
    value = build_optimizer_step_log(
        run_id="near-sft-v3-fixture",
        epoch=1,
        epochs=2,
        record_index=16,
        records_per_epoch=14350,
        optimizer_step=1,
        total_loss=2.5,
        classification_loss=1.75,
        evidence_loss=0.75,
        learning_rate=2e-4,
    )
    assert value["event"] == "formal_sft_optimizer_step"
    assert value["optimizer_step"] == 1
    assert value["total_loss"] == 2.5
    with pytest.raises(FloatingPointError, match="non-finite"):
        build_optimizer_step_log(
            run_id="near-sft-v3-fixture",
            epoch=1,
            epochs=2,
            record_index=16,
            records_per_epoch=14350,
            optimizer_step=1,
            total_loss=float("nan"),
            classification_loss=1.75,
            evidence_loss=0.75,
            learning_rate=2e-4,
        )


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


def test_superseded_formal_config_remains_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_root = tmp_path / "model"
    model_root.mkdir()
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path))
    monkeypatch.setenv("QWEN_MODEL_PATH", str(model_root))
    with pytest.raises(RuntimeError, match="not frozen/authorized"):
        formal_preflight(Path("configs/training/near_sft_config_v1.yaml"))


def test_completed_v3_model_a_config_is_preserved_but_fail_closed() -> None:
    config = yaml.safe_load(Path("configs/training/near_sft_config_v2.yaml").read_text())
    assert config["status"] == "COMPLETED_MODEL_A_LEGACY"
    assert config["formal_run_authorized"] is False
    assert config["research_role"] == "LEGACY_CONTROLLED_DOMAIN_BASELINE"
    assert config["do_not_execute_for_model_b"] is True
    assert config["superseded_for_model_b_by"] == "DATASET_V4_B1_RUNTIME_CONTRACT_V1"
    assert config["data"]["corpus_version"] == "OBSERVABLE_SFT_CORPUS_V3"
    assert config["data"]["evidence_state_schema_version"] == "EVIDENCE_STATE_SCHEMA_V2"
    assert config["data"]["expected_unique_sessions"] == 11958
    assert config["quality_gates"]["max_states_per_session"] == 3
    assert config["schedule"]["max_sequence_length"] == 8192


def test_completed_v3_model_a_config_rejects_relaunch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_root = tmp_path / "model"
    model_root.mkdir()
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path))
    monkeypatch.setenv("QWEN_MODEL_PATH", str(model_root))
    with pytest.raises(RuntimeError, match="not frozen/authorized"):
        formal_preflight(Path("configs/training/near_sft_config_v2.yaml"))


def test_record_preflight_uses_active_class_map_and_parameterized_session_count(
    tmp_path: Path,
) -> None:
    corpus = tmp_path / "corpus.jsonl"
    validation = tmp_path / "validation.jsonl"
    _write_jsonl(
        corpus,
        [
            _sft_record(sample="1", label="Normal", index=0),
            _sft_record(sample="2", label="DDoS_TCP", index=1),
        ],
    )
    _write_jsonl(
        validation,
        [_validation_record(sample="3", label="DDoS_TCP", index=1)],
    )
    result = validate_formal_record_contract(
        corpus,
        validation,
        {"Normal": 0, "DDoS_TCP": 1},
        expected_unique_sessions=2,
        max_states_per_session=2,
    )
    assert result["corpus_unique_sessions"] == 2
    assert result["max_states_per_session_observed"] == 1


@pytest.mark.parametrize("asset", ["corpus", "validation"])
def test_record_preflight_rejects_class_index_or_label_outside_active_map(
    tmp_path: Path,
    asset: str,
) -> None:
    corpus = tmp_path / "corpus.jsonl"
    validation = tmp_path / "validation.jsonl"
    corpus_row = _sft_record(sample="1", label="Normal", index=0)
    validation_row = _validation_record(sample="2", label="Normal", index=0)
    if asset == "corpus":
        corpus_row["class_index"] = 1
    else:
        validation_row["fine_label"] = "Removed_Class"
    _write_jsonl(corpus, [corpus_row])
    _write_jsonl(validation, [validation_row])
    with pytest.raises(RuntimeError, match="active class map"):
        validate_formal_record_contract(
            corpus,
            validation,
            {"Normal": 0},
            expected_unique_sessions=1,
            max_states_per_session=2,
        )


def test_record_preflight_enforces_state_cap_and_weight_sum(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.jsonl"
    validation = tmp_path / "validation.jsonl"
    first = _sft_record(sample="1", label="Normal", index=0, weight=0.4)
    second = _sft_record(sample="1", label="Normal", index=0, weight=0.4)
    second["evidence_state_id"] = "state_" + "2" * 24
    second["classification_ce_eligible"] = False
    second["state_role"] = "auxiliary"
    second["stage_type"] = "controlled_mask"
    _write_jsonl(corpus, [first, second])
    _write_jsonl(validation, [_validation_record(sample="3", label="Normal", index=0)])
    with pytest.raises(RuntimeError, match="weights do not sum to one"):
        validate_formal_record_contract(
            corpus,
            validation,
            {"Normal": 0},
            expected_unique_sessions=1,
            max_states_per_session=2,
        )
    with pytest.raises(RuntimeError, match="max_states_per_session"):
        validate_formal_record_contract(
            corpus,
            validation,
            {"Normal": 0},
            expected_unique_sessions=1,
            max_states_per_session=1,
        )


def test_record_preflight_rejects_train_validation_identity_overlap(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.jsonl"
    validation = tmp_path / "validation.jsonl"
    _write_jsonl(corpus, [_sft_record(sample="1", label="Normal", index=0)])
    _write_jsonl(
        validation, [_validation_record(sample="1", label="Normal", index=0)]
    )
    with pytest.raises(RuntimeError, match="overlap sample identity"):
        validate_formal_record_contract(
            corpus,
            validation,
            {"Normal": 0},
            expected_unique_sessions=1,
            max_states_per_session=1,
        )
