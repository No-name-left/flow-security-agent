from __future__ import annotations

import json
from pathlib import Path

import pytest

from flowsec.training.contracts import (
    EvidenceDomain,
    EvidenceEnvelope,
    EvidenceSnapshot,
    EvidenceTrustV1,
    SFTRecordV1,
    StageType,
)
from flowsec.training.corpus import finalize_sft_corpus
from flowsec.training.harness import POOL_MEAN, TrafficExpertTrainingHarness
from flowsec.training.prompts import teacher_prompt_v3


SAMPLE_ID = "fs1_" + "1" * 40


def _snapshot(state_suffix: str, *, primary: bool) -> EvidenceSnapshot:
    stage = StageType.INITIAL if primary else StageType.CONTROLLED_MASK
    evidence_type = "initial" if primary else "controlled_mask"
    return EvidenceSnapshot(
        sample_id=SAMPLE_ID,
        evidence_state_id="state_" + state_suffix * 24,
        fine_label="Normal",
        coarse_label="Benign",
        split="train",
        ku_role="K_known",
        stage_type=stage,
        classification_supervision_valid=primary,
        available_capabilities=("packet_expansion",),
        evidence=(
            EvidenceEnvelope(
                evidence_id="ev_" + evidence_type + "_12345678",
                evidence_type=evidence_type,
                domain=EvidenceDomain.OBSERVATION,
                trust=EvidenceTrustV1.TRUSTED_OBSERVATION,
                content={"evidence_type": evidence_type, "bounded": True},
                provenance="fixture",
            ),
        ),
        source_digest=("a" if primary else "b") * 64,
    )


def _annotation(snapshot: EvidenceSnapshot) -> dict[str, object]:
    prompt = teacher_prompt_v3()
    target = {
        "behavior_summary": "Only bounded current evidence is visible.",
        "supporting_evidence": [],
        "missing_evidence": [
            {"type": "packet", "description": "More packet interaction is material."}
        ],
        "evidence_sufficient": False,
        "gap_type": "packet",
        "teacher_confidence": 0.8,
    }
    return {
        "evidence_state_id": snapshot.evidence_state_id,
        "validation_result": "PASS",
        "teacher_prompt_version": prompt.version,
        "teacher_prompt_digest": prompt.digest,
        "normalized_target": target,
        "request_id": "fixture-request",
        "model": "fixture-teacher",
    }


def test_final_corpus_keeps_primary_ce_when_teacher_says_insufficient(tmp_path: Path) -> None:
    primary = _snapshot("1", primary=True)
    auxiliary = _snapshot("2", primary=False)
    snapshot_path = tmp_path / "snapshots.jsonl"
    snapshot_path.write_text(
        "\n".join(item.model_dump_json() for item in (primary, auxiliary)) + "\n",
        encoding="utf-8",
    )
    snapshot_manifest = tmp_path / "snapshot-manifest.json"
    snapshot_manifest.write_text(
        json.dumps(
            {
                "dataset_digest": "c" * 64,
                "artifacts": {"snapshot_universe": {"path": str(snapshot_path)}},
            }
        ),
        encoding="utf-8",
    )
    annotation_root = tmp_path / "annotations"
    records = annotation_root / "records"
    records.mkdir(parents=True)
    for item in (primary, auxiliary):
        (records / f"{item.evidence_state_id}.json").write_text(
            json.dumps(_annotation(item)), encoding="utf-8"
        )
    preset = tmp_path / "preset.json"
    preset.write_text(json.dumps({"Near": {"K_known": ["Normal"]}}), encoding="utf-8")

    manifest = finalize_sft_corpus(
        snapshot_manifest,
        annotation_root,
        tmp_path / "final",
        preset,
        tokenize=lambda text: text.split(),
    )
    corpus_path = Path(manifest["artifacts"]["corpus"]["path"])
    corpus = [SFTRecordV1.model_validate_json(line) for line in corpus_path.read_text().splitlines()]
    by_stage = {item.stage_type: item for item in corpus}

    assert by_stage[StageType.INITIAL].evidence_state_target.evidence_sufficient is False
    assert by_stage[StageType.INITIAL].classification_ce_eligible is True
    assert by_stage[StageType.CONTROLLED_MASK].classification_ce_eligible is False
    assert manifest["classification_supervised_count"] == 1
    assert manifest["classification_masked_count"] == 1
    assert manifest["classification_supervised_states_per_session_max"] == 1
    assert manifest["prohibited_model_input_key_count"] == 0
    assert manifest["target_class_verdict_count"] == 0



def test_teacher_rejects_immutable_class_verdict_in_evidence_state() -> None:
    from flowsec.training.teacher import validate_teacher_annotation

    snapshot = _snapshot("3", primary=True)
    payload = {
        "behavior_summary": "The label is Normal.",
        "supporting_evidence": [],
        "missing_evidence": [],
        "evidence_sufficient": True,
        "gap_type": "none",
        "teacher_confidence": 0.9,
    }
    with pytest.raises(ValueError, match="class verdict"):
        validate_teacher_annotation(payload, snapshot)


def test_teacher_rejects_contextual_class_conclusions_but_allows_behavior_terms() -> None:
    from flowsec.training.teacher import validate_teacher_annotation

    snapshot = _snapshot("5", primary=True)
    base = {
        "behavior_summary": "Only bounded current evidence is visible.",
        "supporting_evidence": [],
        "missing_evidence": [
            {"type": "application", "description": "More application evidence is needed."}
        ],
        "evidence_sufficient": False,
        "gap_type": "application",
        "teacher_confidence": 0.8,
    }
    contextual = {**base, "missing_evidence": [
        {"type": "application", "description": "More evidence is needed to distinguish Normal traffic from alternatives."}
    ]}
    with pytest.raises(ValueError, match="class verdict"):
        validate_teacher_annotation(contextual, snapshot)
    backend_literal = {**base, "missing_evidence": [
        {"type": "application", "description": "Evidence is needed to distinguish DDoS_HTTP from alternatives."}
    ]}
    ddos_snapshot = snapshot.model_copy(update={"fine_label": "DDoS_HTTP"})
    with pytest.raises(ValueError, match="class verdict"):
        validate_teacher_annotation(backend_literal, ddos_snapshot)
    allowed = {**base, "behavior_summary": "The TCP exchange ended with a normal closure."}
    validate_teacher_annotation(allowed, snapshot)



def test_teacher_rejects_high_specificity_attack_family_aliases() -> None:
    from flowsec.training.teacher import validate_teacher_annotation

    snapshot = _snapshot("6", primary=True)
    base = {
        "behavior_summary": "Only bounded current evidence is visible.",
        "supporting_evidence": [],
        "missing_evidence": [
            {"type": "application", "description": "More application evidence is needed."}
        ],
        "evidence_sufficient": False,
        "gap_type": "application",
        "teacher_confidence": 0.8,
    }
    cases = (
        ("Backdoor", "Evidence of actual backdoor communication is absent."),
        ("DDoS_HTTP", "The exchange is consistent with an HTTP-based DDoS pattern."),
        ("DDoS_TCP", "The packets indicate a SYN flood."),
        ("MITM", "More evidence is needed to distinguish a man-in-the-middle."),
        ("Port_Scanning", "The timing is typical of port scanning."),
        ("Ransomware", "Ransomware command traffic is not yet visible."),
        ("SQL_injection", "More payload is required to confirm SQL injection."),
        ("Vulnerability_scanner", "This resembles a vulnerability scanner."),
        ("Vulnerability_scanner", "The exchange is consistent with automated scanning behavior."),
        ("Port_Scanning", "The handshake is consistent with a port scan attempt."),
        ("DDoS_HTTP", "The timing resembles a high-rate request flood."),
        ("Normal", "The exchange is consistent with benign traffic."),
    )
    for fine_label, disclosure in cases:
        target = {**base, "behavior_summary": disclosure}
        with pytest.raises(ValueError, match="class verdict"):
            validate_teacher_annotation(
                target, snapshot.model_copy(update={"fine_label": fine_label})
            )

    sql_like_observation = {
        **base,
        "behavior_summary": "The request contains SQL-like punctuation in one parameter.",
    }
    validate_teacher_annotation(
        sql_like_observation,
        snapshot.model_copy(update={"fine_label": "SQL_injection"}),
    )

def test_teacher_request_never_receives_classification_ce_gate() -> None:
    from flowsec.training.role_requests import build_teacher_request

    request = build_teacher_request(_snapshot("4", primary=True)).model_dump()
    assert "classification_ce_eligible" not in request
    assert "classification_supervision_valid" not in request
    assert request["controlled_lower_evidence_auxiliary"] is False

def test_harness_ce_gate_is_structurally_independent_of_sufficiency_target() -> None:
    torch = pytest.importorskip("torch")

    class Output:
        def __init__(self, logits, hidden_states):
            self.logits = logits
            self.hidden_states = hidden_states
            self.loss = None

    class TinyLM(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.embedding = torch.nn.Embedding(32, 4)
            self.lm_head = torch.nn.Linear(4, 32)

        def forward(self, input_ids, **_kwargs):
            state = self.embedding(input_ids)
            return Output(self.lm_head(state), (state,))

    harness = TrafficExpertTrainingHarness(
        TinyLM(), hidden_size=4, num_classes=3, pooling_method=POOL_MEAN
    )
    common = {
        "input_ids": torch.tensor([[1, 2, 3], [4, 5, 6]]),
        "attention_mask": torch.ones(2, 3, dtype=torch.long),
        "classification_attention_mask": torch.tensor([[1, 1, 0], [1, 1, 0]]),
        "fine_labels": torch.tensor([0, 1]),
        "classification_ce_eligible": torch.tensor([True, False]),
        "record_weights": torch.tensor([1.0, 1.0]),
    }
    insufficient_target = torch.tensor([[-100, 7, 8], [-100, 9, 10]])
    sufficient_target = torch.tensor([[-100, 11, 12], [-100, 13, 14]])
    a = harness(lm_labels=insufficient_target, **common)
    b = harness(lm_labels=sufficient_target, **common)

    assert a["classification_supervised_count"].item() == 1
    assert b["classification_supervised_count"].item() == 1
    assert a["classification_loss"].item() == pytest.approx(b["classification_loss"].item())
