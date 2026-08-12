# Blind Classification vs Teacher Sufficiency Calibration Audit v1

AUDIT_STATUS=PASS_WITH_LIMITATIONS
FORMAL_CORPUS_MODIFIED=false
BASE_CORPUS_SHA256=5b845cf9e5886e5e44fd46562135ba3eb5907de65fd8faf5d9b8777253149123
PRIMARY_SAMPLE_COUNT=330
TEACHER_INSUFFICIENT_SAMPLE_COUNT=290
NO_NEXT_ACTION_SAMPLE_COUNT=110
ROOT_CAUSE=MIXED

## Outcome

The cached blind audit is complete. DeepSeek classified all 330 fixed states; raw Qwen produced 329 valid results and one strict grounding quarantine; the bounded marginal-utility extension completed 99/99 pairs. No corpus, Teacher annotation, validator, K/U, split, Evidence builder, RAG asset, or training artifact changed.

Teacher sufficiency is locally over-conservative for explicit Payload/Application patterns and scanning-rich Temporal context, but this is not the dominant global explanation. On Teacher-insufficient states, DeepSeek Top-1/Top-2 is only 21.03%/23.79%; the no-next-action group is 30.00%/33.64%. Backdoor, MITM, and Ransomware are 0% Top-1 and Top-2 for both classifiers. The scientifically supportable result is therefore MIXED, not a global rejection of Teacher or Edge.

## Protocol and integrity

- Fixed sample: seed 20260812, 11 Near K-known classes × 30, manifest `93b30ccd9075fef4925da45e3a8a287c200cfec4d54c05e2611be91d9173ca88`.
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
| Backdoor | 30 | 0.00% [0.00%, 11.35%] | 0.00% [0.00%, 11.35%] | 30 | 0.00% | 0.00% |
| DDoS_HTTP | 30 | 0.00% [0.00%, 11.35%] | 3.33% [0.59%, 16.67%] | 30 | 13.33% | 13.33% |
| DDoS_TCP | 30 | 0.00% [0.00%, 11.35%] | 23.33% [11.79%, 40.93%] | 30 | 0.00% | 0.00% |
| MITM | 30 | 0.00% [0.00%, 11.35%] | 0.00% [0.00%, 11.35%] | 29 | 0.00% | 0.00% |
| Normal | 30 | 83.33% [66.44%, 92.66%] | 100.00% [88.65%, 100.00%] | 30 | 93.33% | 100.00% |
| Password | 30 | 16.67% [7.34%, 33.56%] | 16.67% [7.34%, 33.56%] | 30 | 13.33% | 13.33% |
| Port_Scanning | 30 | 100.00% [88.65%, 100.00%] | 100.00% [88.65%, 100.00%] | 30 | 0.00% | 100.00% |
| Ransomware | 30 | 0.00% [0.00%, 11.35%] | 0.00% [0.00%, 11.35%] | 30 | 0.00% | 0.00% |
| SQL_injection | 30 | 43.33% [27.38%, 60.80%] | 43.33% [27.38%, 60.80%] | 30 | 43.33% | 43.33% |
| Uploading | 30 | 3.33% [0.59%, 16.67%] | 3.33% [0.59%, 16.67%] | 30 | 6.67% | 6.67% |
| Vulnerability_scanner | 30 | 23.33% [11.79%, 40.93%] | 36.67% [21.87%, 54.49%] | 30 | 30.00% | 40.00% |

### By stage

| Stage | DS n | Teacher sufficient | DeepSeek Top-1 | DeepSeek Top-2 | Qwen n | Qwen Top-1 | Qwen Top-2 |
|---|---:|---:|---:|---:|---:|---:|---:|
| application | 24 | 37.50% | 29.17% | 37.50% | 24 | 45.83% | 54.17% |
| initial | 111 | 0.00% | 16.22% | 17.12% | 111 | 6.31% | 17.12% |
| knowledge | 25 | 16.00% | 20.00% | 24.00% | 25 | 12.00% | 24.00% |
| packet | 20 | 15.00% | 25.00% | 40.00% | 20 | 40.00% | 45.00% |
| payload | 31 | 41.94% | 70.97% | 77.42% | 31 | 70.97% | 74.19% |
| relation | 58 | 0.00% | 22.41% | 22.41% | 58 | 13.79% | 22.41% |
| temporal | 61 | 18.03% | 18.03% | 31.15% | 60 | 1.67% | 20.00% |

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
