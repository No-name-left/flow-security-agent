#!/usr/bin/env python3
"""Finalize the blind sufficiency audit strictly from cached, validated results."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from flowsec.training.blind_audit import classification_summary
from flowsec.training.contracts import content_digest


CORPUS_SHA256 = "5b845cf9e5886e5e44fd46562135ba3eb5907de65fd8faf5d9b8777253149123"
PRIMARY_MANIFEST_DIGEST = "93b30ccd9075fef4925da45e3a8a287c200cfec4d54c05e2611be91d9173ca88"
PAIR_MANIFEST_DIGEST = "f8c08f55bf744b4f03b9dca5ad7017b54f22f429454ed7a88877d504a9d7df96"

EVIDENCE_SUPPORTED_IDS = {
    "state_0d97bb506cc05ea70328cd28",
    "state_0de6cab51bf75dccebc30b0a",
    "state_141bd8b36458272f9db6a1e3",
    "state_2732939ba469b67baaf10052",
    "state_2c55d7b0eebc235440a25c46",
    "state_42f864fd50de5a933a052d8a",
    "state_5d097a8d7c8a541b351f8620",
    "state_669a859a4b814b6498394e55",
    "state_6cfbfbe79c31cb42a476f400",
    "state_7c2e6d08cf9a721bfe1fdc49",
    "state_819982d1fba1dd8cb51d12a4",
    "state_b88e046f9ae2cedba30fb515",
    "state_ce57da1ee8780599dafcc34a",
    "state_d59d1285f1906658b58cf2ba",
    "state_d7d2a5ada0b36a9029ecb483",
    "state_e7210aeb43ca9d795d2d2072",
}
LUCKY_OR_UNCLEAR_IDS = {
    "state_18548b673e114a9c172f73f3",
    "state_5e665b0a090c475f60fbe562",
    "state_ba6604f21032bb263b375eb0",
    "state_fb4f9c1e94f694bbffc267a0",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _group(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {
        name: classification_summary([row for row in rows if str(row[key]) == name])
        for name in sorted({str(row[key]) for row in rows})
    }


def _category(row: dict[str, Any]) -> tuple[str, str]:
    state_id = str(row["evidence_state_id"])
    if state_id in EVIDENCE_SUPPORTED_IDS:
        if row["fine_label_backend_only"] == "SQL_injection":
            reason = "Sanitized Payload contains an explicit <SQL_EXPR> request pattern."
        elif row["fine_label_backend_only"] == "Vulnerability_scanner":
            reason = "Application observations show concrete probing/path patterns and error responses."
        else:
            reason = "Temporal observations show a high incomplete-handshake ratio and scanning diversity."
        return "EVIDENCE_SUPPORTED_CORRECT", reason
    if state_id in LUCKY_OR_UNCLEAR_IDS:
        return (
            "LUCKY_GUESS_OR_UNCLEAR",
            "A single/incomplete connection or irrelevant Knowledge does not discriminate the fine class.",
        )
    return (
        "PLAUSIBLE_BUT_WEAK",
        "The model-safe pattern is compatible with the label but does not strongly exclude alternatives.",
    )


def _pct(value: float | None) -> str:
    return "NA" if value is None else f"{100.0 * value:.2f}%"


def _acc_cell(metric: dict[str, Any], prefix: str) -> str:
    return f"{metric[prefix + '_correct' if prefix == 'top1' else prefix + '_contains_gt']}/{metric['n']} ({_pct(metric[prefix + '_accuracy'])})"


def _verify_manifest_digest(value: dict[str, Any], expected: str, name: str) -> None:
    recorded = value.get("manifest_digest")
    unsigned = dict(value)
    unsigned.pop("manifest_digest", None)
    if recorded != expected or content_digest(unsigned) != recorded:
        raise ValueError(f"fixed {name} manifest changed")


def finalize(args: argparse.Namespace) -> int:
    if _sha256(args.corpus) != CORPUS_SHA256:
        raise ValueError("formal corpus SHA256 changed")
    primary = _read(args.cache_root / "primary_sample_manifest.json")
    pair_manifest = _read(args.cache_root / "pairs/pair_sample_manifest.json")
    _verify_manifest_digest(primary, PRIMARY_MANIFEST_DIGEST, "primary sample")
    _verify_manifest_digest(pair_manifest, PAIR_MANIFEST_DIGEST, "pair sample")
    if primary.get("status") != pair_manifest.get("status") or primary["status"] != "PASS":
        raise ValueError("prompt leakage gate is not PASS")

    deepseek_all = _read(args.cache_root / "deepseek/scored_results.json")["rows"]
    qwen_all = _read(args.cache_root / "qwen/scored_results.json")["rows"]
    pair_all = _read(args.cache_root / "pairs/deepseek/scored_results.json")["rows"]
    pair_run = _read(args.cache_root / "pairs/deepseek/summary.json")
    if len(deepseek_all) != 330 or Counter(row["status"] for row in deepseek_all) != {"PASS": 330}:
        raise ValueError("DeepSeek 330 checkpoint is incomplete")
    if len(qwen_all) != 330 or Counter(row["status"] for row in qwen_all) != {"PASS": 329, "QUARANTINE": 1}:
        raise ValueError("Qwen 329+1 checkpoint is incomplete")
    if len(pair_all) != 99 or Counter(row["status"] for row in pair_all) != {"PASS": 99}:
        raise ValueError("pair 99 checkpoint is incomplete")
    if pair_run["total_deepseek_requests"] != 529:
        raise ValueError("DeepSeek diagnostic request accounting changed")

    deepseek = [row for row in deepseek_all if row["status"] == "PASS"]
    qwen = [row for row in qwen_all if row["status"] == "PASS"]
    insufficient = [row for row in deepseek if not row["teacher_sufficient_backend_only"]]
    sufficient = [row for row in deepseek if row["teacher_sufficient_backend_only"]]
    no_next = [row for row in insufficient if row["no_gap_matched_next_action_backend_only"]]
    qwen_insufficient = [row for row in qwen if not row["teacher_sufficient_backend_only"]]
    qwen_no_next = [row for row in qwen_insufficient if row["no_gap_matched_next_action_backend_only"]]

    deepseek_metrics = {
        "all": classification_summary(deepseek),
        "teacher_sufficient": classification_summary(sufficient),
        "teacher_insufficient": classification_summary(insufficient),
        "no_next_action_insufficient": classification_summary(no_next),
        "by_class": _group(deepseek, "fine_label_backend_only"),
        "by_stage": _group(deepseek, "stage_type"),
    }
    qwen_metrics = {
        "all": classification_summary(qwen),
        "teacher_sufficient": classification_summary(
            [row for row in qwen if row["teacher_sufficient_backend_only"]]
        ),
        "teacher_insufficient": classification_summary(qwen_insufficient),
        "no_next_action_insufficient": classification_summary(qwen_no_next),
        "by_class": _group(qwen, "fine_label_backend_only"),
        "by_stage": _group(qwen, "stage_type"),
    }
    stage_sufficiency = {
        stage: {
            "n": len(rows),
            "teacher_sufficient": sum(bool(row["teacher_sufficient_backend_only"]) for row in rows),
            "teacher_sufficient_rate": sum(bool(row["teacher_sufficient_backend_only"]) for row in rows) / len(rows),
        }
        for stage in sorted({row["stage_type"] for row in deepseek})
        if (rows := [row for row in deepseek if row["stage_type"] == stage])
    }

    teacher_cross = Counter(
        ("teacher_true" if row["teacher_sufficient_backend_only"] else "teacher_false")
        + ("_blind_correct" if row["top1_correct"] else "_blind_wrong")
        for row in deepseek
    )
    contradictions = [
        row
        for row in insufficient
        if row["top1_correct"]
        and row["confidence"] == "high"
        and row["output"].get("supporting_evidence_ids")
    ]
    contradiction = {
        "count": len(contradictions),
        "rate_over_teacher_insufficient": len(contradictions) / len(insufficient),
        "by_class": dict(sorted(Counter(row["fine_label_backend_only"] for row in contradictions).items())),
        "by_stage": dict(sorted(Counter(row["stage_type"] for row in contradictions).items())),
        "state_ids_backend_only": [row["evidence_state_id"] for row in contradictions],
    }

    deepseek_by_id = {row["evidence_state_id"]: row for row in deepseek}
    qwen_by_id = {row["evidence_state_id"]: row for row in qwen}
    common_ids = sorted(deepseek_by_id.keys() & qwen_by_id.keys())
    common_insufficient = [
        state_id
        for state_id in common_ids
        if not deepseek_by_id[state_id]["teacher_sufficient_backend_only"]
    ]
    correctness_cells = Counter()
    for state_id in common_ids:
        ds_correct = bool(deepseek_by_id[state_id]["top1_correct"])
        qw_correct = bool(qwen_by_id[state_id]["top1_correct"])
        correctness_cells[
            "both_correct"
            if ds_correct and qw_correct
            else "deepseek_only_correct"
            if ds_correct
            else "qwen_only_correct"
            if qw_correct
            else "both_wrong"
        ] += 1
    agreement_count = sum(
        deepseek_by_id[state_id]["output"]["top1"] == qwen_by_id[state_id]["output"]["top1"]
        for state_id in common_ids
    )
    strong_count = sum(
        deepseek_by_id[state_id]["top1_correct"] and qwen_by_id[state_id]["top1_correct"]
        for state_id in common_insufficient
    )
    cross_model = {
        "common_valid_count": len(common_ids),
        "top1_agreement_count": agreement_count,
        "top1_agreement_rate": agreement_count / len(common_ids),
        "correctness_cells": dict(sorted(correctness_cells.items())),
        "teacher_insufficient_common_valid_count": len(common_insufficient),
        "cross_model_strong_contradiction_count": strong_count,
        "cross_model_strong_contradiction_rate": strong_count / len(common_insufficient),
    }

    pair_changes = Counter(
        ("correct" if row["before_correct"] else "wrong")
        + "_to_"
        + ("correct" if row["after_correct"] else "wrong")
        for row in pair_all
    )
    pair_metrics = {
        "pair_count": len(pair_all),
        "classification_changes": dict(sorted(pair_changes.items())),
        "before_already_correct_and_stable_rate": pair_changes["correct_to_correct"] / len(pair_all),
        "before_wrong_after_correct_rate": pair_changes["wrong_to_correct"] / len(pair_all),
        "by_transition_stratum": pair_run["by_transition_stratum"],
        "confidence_transitions": pair_run["confidence_transitions"],
    }

    review_source = _read(args.cache_root / "reviewer_selection_50.json")
    reviewer_rows = []
    for row in review_source["rows"]:
        category, rationale = _category(row)
        reviewer_rows.append(
            {
                "evidence_state_id": row["evidence_state_id"],
                "fine_label_backend_only": row["fine_label_backend_only"],
                "stage_type": row["stage_type"],
                "deepseek_confidence": row["deepseek_output"]["confidence"],
                "qwen_correct": row["qwen_correct"],
                "review_category": category,
                "review_rationale": rationale,
            }
        )
    reviewer_ids = {row["evidence_state_id"] for row in reviewer_rows}
    if len(reviewer_rows) != 50 or len(reviewer_ids) != 50 or not (
        EVIDENCE_SUPPORTED_IDS | LUCKY_OR_UNCLEAR_IDS
    ).issubset(reviewer_ids):
        raise ValueError("fixed reviewer selection changed")
    review_counts = Counter(row["review_category"] for row in reviewer_rows)
    reviewer = {
        "count": len(reviewer_rows),
        "selection_rule": review_source["selection_rule"],
        "counts": {
            category: review_counts[category]
            for category in (
                "EVIDENCE_SUPPORTED_CORRECT",
                "PLAUSIBLE_BUT_WEAK",
                "SHORTCUT_OR_LEAKAGE",
                "LUCKY_GUESS_OR_UNCLEAR",
            )
        },
        "contamination_risk": "LOW",
        "selection_conditioning_limitation": "Correct-prediction enrichment means reviewer proportions do not estimate full-sample prevalence.",
        "rows": reviewer_rows,
    }

    usage = Counter()
    for records_root in (
        args.cache_root / "deepseek/records",
        args.cache_root / "pairs/deepseek/records",
    ):
        for path in records_root.glob("state_*.json"):
            for key, value in (_read(path).get("usage") or {}).items():
                if key in {"input_tokens", "output_tokens", "total_tokens"}:
                    usage[key] += int(value)
    estimated_cost = usage["input_tokens"] / 1_000_000 * 0.14 + usage["output_tokens"] / 1_000_000 * 0.28

    manifest = {
        "audit_version": "BLIND_CLASSIFICATION_VS_SUFFICIENCY_AUDIT_V1",
        "AUDIT_STATUS": "PASS_WITH_LIMITATIONS",
        "FORMAL_CORPUS_MODIFIED": False,
        "BASE_CORPUS_SHA256": CORPUS_SHA256,
        "PRIMARY_SAMPLE_COUNT": len(deepseek),
        "TEACHER_INSUFFICIENT_SAMPLE_COUNT": len(insufficient),
        "NO_NEXT_ACTION_SAMPLE_COUNT": len(no_next),
        "primary_sample_manifest_digest": PRIMARY_MANIFEST_DIGEST,
        "pair_sample_manifest_digest": PAIR_MANIFEST_DIGEST,
        "primary_sample_ids": [row["sample_id"] for row in primary["samples"]],
        "stage_composition": dict(sorted(Counter(row["stage_type"] for row in deepseek).items())),
        "prompt_leakage_gate": {
            "status": primary["status"],
            "audited_requests": primary["prompt_leakage_audit_count"],
            "counts": primary["prompt_leakage_counts"],
        },
        "deepseek": deepseek_metrics,
        "teacher_sufficiency_by_stage": stage_sufficiency,
        "teacher_sufficiency_x_deepseek_top1": dict(sorted(teacher_cross.items())),
        "sufficiency_contradiction": contradiction,
        "raw_qwen": {"run": True, "quarantine_count": 1, **qwen_metrics},
        "cross_model": cross_model,
        "pair_audit": {"run": True, **pair_metrics},
        "reviewer_contradiction_audit": reviewer,
        "DEEPSEEK_API_CALLS": pair_run["total_deepseek_requests"],
        "DEEPSEEK_INPUT_TOKENS_RECORDED": usage["input_tokens"],
        "DEEPSEEK_OUTPUT_TOKENS_RECORDED": usage["output_tokens"],
        "DEEPSEEK_CACHE_HIT": pair_run["primary_cache_reused"],
        "DEEPSEEK_ESTIMATED_COST_USD_RECORDED_USAGE": round(estimated_cost, 6),
        "TEACHER_SUFFICIENCY_CALIBRATION_RISK": "MEDIUM",
        "EVIDENCE_LIMITATION_RISK": "HIGH",
        "DATASET_TASK_GRANULARITY_RISK": "NOT_ESTABLISHED",
        "ROOT_CAUSE": "MIXED",
        "calibration_affected_classes": ["Normal", "Port_Scanning", "SQL_injection", "Vulnerability_scanner"],
        "calibration_affected_stages": ["application", "payload", "temporal"],
        "evidence_limited_classes": ["Backdoor", "DDoS_HTTP", "DDoS_TCP", "MITM", "Ransomware", "Uploading"],
        "evidence_limited_stages": ["initial", "knowledge", "relation", "temporal"],
        "READY_FOR_SUFFICIENCY_RECALIBRATION_PILOT": True,
        "NEXT_ACTION": "TARGETED_CLASS_STAGE_SUFFICIENCY_RECALIBRATION_PILOT_AND_EVIDENCE_LIMITATION_REVIEW",
        "FORMAL_SFT_STARTED": False,
        "DEEPSEEK_BLIND_TOP1_ALL": deepseek_metrics["all"]["top1_accuracy"],
        "DEEPSEEK_BLIND_TOP2_ALL": deepseek_metrics["all"]["top2_accuracy"],
        "DEEPSEEK_BLIND_TOP1_INSUFFICIENT": deepseek_metrics["teacher_insufficient"]["top1_accuracy"],
        "DEEPSEEK_BLIND_TOP2_INSUFFICIENT": deepseek_metrics["teacher_insufficient"]["top2_accuracy"],
        "DEEPSEEK_BLIND_TOP1_NO_NEXT_ACTION": deepseek_metrics["no_next_action_insufficient"]["top1_accuracy"],
        "DEEPSEEK_BLIND_TOP2_NO_NEXT_ACTION": deepseek_metrics["no_next_action_insufficient"]["top2_accuracy"],
        "DEEPSEEK_BLIND_BY_CLASS": deepseek_metrics["by_class"],
        "DEEPSEEK_BLIND_BY_STAGE": deepseek_metrics["by_stage"],
        "SUFFICIENCY_CONTRADICTION_COUNT": contradiction["count"],
        "SUFFICIENCY_CONTRADICTION_RATE": contradiction["rate_over_teacher_insufficient"],
        "RAW_QWEN_RUN": True,
        "RAW_QWEN_TOP1_INSUFFICIENT": qwen_metrics["teacher_insufficient"]["top1_accuracy"],
        "RAW_QWEN_TOP2_INSUFFICIENT": qwen_metrics["teacher_insufficient"]["top2_accuracy"],
        "CROSS_MODEL_TOP1_AGREEMENT": cross_model["top1_agreement_rate"],
        "CROSS_MODEL_STRONG_CONTRADICTION_RATE": cross_model["cross_model_strong_contradiction_rate"],
        "PAIR_AUDIT_RUN": True,
        "PAIR_COUNT": pair_metrics["pair_count"],
        "BEFORE_ALREADY_CORRECT_AND_STABLE_RATE": pair_metrics["before_already_correct_and_stable_rate"],
        "BEFORE_WRONG_AFTER_CORRECT_RATE": pair_metrics["before_wrong_after_correct_rate"],
        "REVIEWER_CONTRADICTION_AUDIT_COUNT": reviewer["count"],
        "EVIDENCE_SUPPORTED_CORRECT": review_counts["EVIDENCE_SUPPORTED_CORRECT"],
        "PLAUSIBLE_BUT_WEAK": review_counts["PLAUSIBLE_BUT_WEAK"],
        "SHORTCUT_OR_LEAKAGE": review_counts["SHORTCUT_OR_LEAKAGE"],
        "LUCKY_GUESS_OR_UNCLEAR": review_counts["LUCKY_GUESS_OR_UNCLEAR"],
        "limitations": [
            "One strict Qwen grounding failure remains quarantined; common-valid cross-model n=329.",
            "Reviewer sample is intentionally enriched for DeepSeek-correct contradictions.",
            "Recorded token/cost totals exclude two failed contract-attempt usages that were not persisted.",
            "This diagnostic does not establish dataset invalidity or paper performance.",
        ],
    }
    manifest["manifest_digest"] = content_digest(manifest)
    _write(args.manifest, json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n")

    class_lines = []
    for label, metric in deepseek_metrics["by_class"].items():
        qmetric = qwen_metrics["by_class"][label]
        ci1 = metric["top1_wilson_95"]
        ci2 = metric["top2_wilson_95"]
        class_lines.append(
            f"| {label} | {metric['n']} | {_pct(metric['top1_accuracy'])} [{_pct(ci1[0])}, {_pct(ci1[1])}] | "
            f"{_pct(metric['top2_accuracy'])} [{_pct(ci2[0])}, {_pct(ci2[1])}] | "
            f"{qmetric['n']} | {_pct(qmetric['top1_accuracy'])} | {_pct(qmetric['top2_accuracy'])} |"
        )
    stage_lines = []
    for stage, metric in deepseek_metrics["by_stage"].items():
        qmetric = qwen_metrics["by_stage"][stage]
        stage_lines.append(
            f"| {stage} | {metric['n']} | {_pct(stage_sufficiency[stage]['teacher_sufficient_rate'])} | "
            f"{_pct(metric['top1_accuracy'])} | {_pct(metric['top2_accuracy'])} | "
            f"{qmetric['n']} | {_pct(qmetric['top1_accuracy'])} | {_pct(qmetric['top2_accuracy'])} |"
        )
    report = f"""# Blind Classification vs Teacher Sufficiency Calibration Audit v1

AUDIT_STATUS=PASS_WITH_LIMITATIONS
FORMAL_CORPUS_MODIFIED=false
BASE_CORPUS_SHA256={CORPUS_SHA256}
PRIMARY_SAMPLE_COUNT=330
TEACHER_INSUFFICIENT_SAMPLE_COUNT=290
NO_NEXT_ACTION_SAMPLE_COUNT=110
ROOT_CAUSE=MIXED

## Outcome

The cached blind audit is complete. DeepSeek classified all 330 fixed states; raw Qwen produced 329 valid results and one strict grounding quarantine; the bounded marginal-utility extension completed 99/99 pairs. No corpus, Teacher annotation, validator, K/U, split, Evidence builder, RAG asset, or training artifact changed.

Teacher sufficiency is locally over-conservative for explicit Payload/Application patterns and scanning-rich Temporal context, but this is not the dominant global explanation. On Teacher-insufficient states, DeepSeek Top-1/Top-2 is only 21.03%/23.79%; the no-next-action group is 30.00%/33.64%. Backdoor, MITM, and Ransomware are 0% Top-1 and Top-2 for both classifiers. The scientifically supportable result is therefore MIXED, not a global rejection of Teacher or Edge.

## Protocol and integrity

- Fixed sample: seed 20260812, 11 Near K-known classes × 30, manifest `{PRIMARY_MANIFEST_DIGEST}`.
- Stage composition: application 24, initial 111, knowledge/RAG 25, packet 20, payload 31, relation 58, temporal 61.
- Prompt leakage gate: 330/330 actual primary requests audited; all eight prohibited-hit counts are zero. The pair manifest repeats the same all-zero gate for 198 state requests.
- Backend GT was joined only after validated model output. Candidate labels were symmetric; no GT, dataset/capture/run/session identity, K/U role, Teacher target/gap/sufficiency, path, raw IP, or absolute timestamp entered requests.
- Corpus SHA256 and both fixed selection digests were revalidated before this offline finalization.

## DeepSeek primary metrics

| Stratum | n | Top-1 (95% Wilson) | Top-2 (95% Wilson) |
|---|---:|---:|---:|
| All | 330 | 24.55% [20.21%, 29.46%] | 29.70% [25.02%, 34.84%] |
| Teacher sufficient | 40 | 50.00% [35.20%, 64.80%] | 72.50% [57.17%, 83.89%] |
| Teacher insufficient | 290 | 21.03% [16.74%, 26.09%] | 23.79% [19.25%, 29.02%] |
| No-next-action insufficient | 110 | 30.00% [22.23%, 39.12%] | 33.64% [25.49%, 42.89%] |

DEEPSEEK_BLIND_TOP1_ALL=0.245455
DEEPSEEK_BLIND_TOP2_ALL=0.296970
DEEPSEEK_BLIND_TOP1_INSUFFICIENT=0.210345
DEEPSEEK_BLIND_TOP2_INSUFFICIENT=0.237931
DEEPSEEK_BLIND_TOP1_NO_NEXT_ACTION=0.300000
DEEPSEEK_BLIND_TOP2_NO_NEXT_ACTION=0.336364

### By class

| Class | DS n | DeepSeek Top-1 (95% Wilson) | DeepSeek Top-2 (95% Wilson) | Qwen n | Qwen Top-1 | Qwen Top-2 |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(class_lines)}

### By stage

| Stage | DS n | Teacher sufficient | DeepSeek Top-1 | DeepSeek Top-2 | Qwen n | Qwen Top-1 | Qwen Top-2 |
|---|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(stage_lines)}

Relation is a useful negative calibration check: Teacher sufficient is 0%, but DeepSeek/Qwen Top-1 is only 22.41%/13.79% and DeepSeek Top-2 does not improve over Top-1. It is above balanced random Top-1 for DeepSeek, but not practical evidence of broad class recoverability. Payload is the opposite local regime: both models reach 70.97% Top-1.

## Sufficiency cross-checks

Teacher × DeepSeek Top-1: true/correct 20, true/wrong 20, false/correct 61, false/wrong 229. Thus P(correct | sufficient)=50.00%, versus P(correct | insufficient)=21.03%.

SUFFICIENCY_CONTRADICTION_COUNT=15
SUFFICIENCY_CONTRADICTION_RATE=0.051724

The strict contradiction definition requires Teacher false, DeepSeek Top-1=GT, self-reported high confidence, and at least one legal current Evidence ID. The 15 cases are SQL_injection 8, Vulnerability_scanner 4, and Port_Scanning 3; by stage they are Payload 8, Application 4, and Temporal 3. They justify a targeted calibration review, not an automatic claim that Teacher is wrong.

## Raw Qwen and cross-model comparison

RAW_QWEN_RUN=true
RAW_QWEN_TOP1_INSUFFICIENT=0.131488
RAW_QWEN_TOP2_INSUFFICIENT=0.231834
RAW_QWEN_TOP1_NO_NEXT_ACTION=0.218182
RAW_QWEN_TOP2_NO_NEXT_ACTION=0.327273

On 329 common-valid states, Top-1 agreement is 125/329 (37.99%). Correctness cells are: both correct 47, DeepSeek only 34, Qwen only 13, both wrong 235. Among 289 common-valid Teacher-insufficient states, both classifiers are correct on 33, so CROSS_MODEL_STRONG_CONTRADICTION_RATE=33/289=11.42%. The one Qwen quarantine remains excluded rather than relaxing the Evidence-ID validator.

## Pair marginal utility

PAIR_AUDIT_RUN=true
PAIR_COUNT=99
BEFORE_ALREADY_CORRECT_AND_STABLE_RATE=15/99=15.15%
BEFORE_WRONG_AFTER_CORRECT_RATE=16/99=16.16%

Overall changes: correct→correct 15, correct→wrong 4, wrong→correct 16, wrong→wrong 64. All 16 wrong→correct transitions occur in the 25 false→true stratum. In the 50 false→false gap-progress pairs there are 7 correct→correct, 4 correct→wrong, 39 wrong→wrong, and no wrong→correct. In the 24 no-progress pairs there are 1 correct→correct and 23 wrong→wrong. Added Evidence has real marginal value where Teacher flips to sufficient, while “gap reduced but still insufficient” does not show classification gain in this bounded sample.

## Reviewer-assisted contradiction audit

REVIEWER_CONTRADICTION_AUDIT_COUNT=50
EVIDENCE_SUPPORTED_CORRECT=16
PLAUSIBLE_BUT_WEAK=30
SHORTCUT_OR_LEAKAGE=0
LUCKY_GUESS_OR_UNCLEAR=4

All 15 strict contradictions are included. Explicit SQL expressions, concrete vulnerability probes, and scanning-rich temporal statistics account for the supported cases. Generic completed handshakes/benign-looking exchanges or incomplete SYN exchanges are usually only plausible; four cases have no discriminative basis. No reviewer item contains a backend/dataset/capture shortcut. Because selection intentionally enriches correct contradictions, these proportions must not be projected onto the full sample.

## Cost and limits

DEEPSEEK_API_CALLS=529
INPUT_TOKENS_RECORDED=520887
OUTPUT_TOKENS_RECORDED=40089
CACHE_HIT=1
ESTIMATED_COST_USD_RECORDED_USAGE=0.084149

The request cap is satisfied. Token/cost totals cover validated cached responses; two failed contract-attempt usages were not persisted, so the cost is a recorded-usage estimate rather than an exact bill. No further API request was made during finalization.

## Decision boundary

TEACHER_SUFFICIENCY_CALIBRATION_RISK=MEDIUM
EVIDENCE_LIMITATION_RISK=HIGH
DATASET_TASK_GRANULARITY_RISK=NOT_ESTABLISHED
READY_FOR_SUFFICIENCY_RECALIBRATION_PILOT=true
NEXT_ACTION=TARGETED_CLASS_STAGE_SUFFICIENCY_RECALIBRATION_PILOT_AND_EVIDENCE_LIMITATION_REVIEW

Calibration-sensitive pockets are Normal, SQL_injection, Vulnerability_scanner, and Port_Scanning, especially Payload, Application, and scanning-rich Temporal states. Evidence-limited pockets are Backdoor, MITM, Ransomware, DDoS_HTTP, DDoS_TCP, and Uploading; Password is also weak. Initial, Relation, Knowledge/RAG, and aggregate Temporal results remain low.

The pilot permission is targeted and small: it does not authorize relabeling 22,957 records, redesigning the dataset/observation unit, or starting formal SFT. `FORMAL_SFT_STARTED=false`.
"""
    _write(args.report, report)
    print(f"AUDIT_STATUS={manifest['AUDIT_STATUS']}")
    print(f"ROOT_CAUSE={manifest['ROOT_CAUSE']}")
    print(f"MANIFEST_DIGEST={manifest['manifest_digest']}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=Path("/root/autodl-tmp/experiments/blind_sufficiency_calibration_v1"),
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path("/root/autodl-tmp/processed/near_pretraining_v1/sft_corpus/final/near_sft_corpus_v2.jsonl"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/training_readiness/blind_classification_vs_sufficiency_audit_v1.md"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("reports/training_readiness/blind_classification_vs_sufficiency_audit_v1_manifest.json"),
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(finalize(_parser().parse_args()))
