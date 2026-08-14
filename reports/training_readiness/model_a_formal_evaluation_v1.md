# Model A Formal Evaluation v1

> Status: **PASS_WITH_MAJOR_EVIDENCE_STATE_LIMITATION**
>
> Formal run: `near-sft-v3-20260812T230311Z-d93789de`
>
> Final checkpoint: `checkpoint-step-00001794`
>
> Evaluation contract: `MODEL_A_FORMAL_EVALUATION_V1`

## Executive decision

The final checkpoint is reproducible and useful as a controlled Edge-IIoTset classifier and a guarded Model B warm start. It is **not** accepted as a successful Evidence-State model. Known-class Macro-F1 reproduces the training artifact exactly, while actual deterministic Evidence-State generation reveals a near-total `evidence_sufficient=true` collapse on the pre-model Basic-insufficient subset.

```text
MODEL_A_FORMAL_EVAL_STATUS=PASS_WITH_MAJOR_EVIDENCE_STATE_LIMITATION
KNOWN_CLASSIFICATION_STATUS=PASS
EVIDENCE_STATE_STATUS=FAIL
SFT_EFFECT_STATUS=WEAK_CLASSIFICATION_UPLIFT_LIMITED_PROBE
MODEL_A_ACCEPTED_FOR_WARM_START=true
```

Warm-start acceptance means that Model A may initialize Model B under replay and regression gates. It does not authorize treating Model A's Evidence-State behavior as a passing baseline, starting RLAIF, or carrying the current Evidence-State supervision forward unchanged.

## Frozen inputs and integrity

- Base/tokenizer revision: `c202236235762e1c871ad0ccb60c8ee5ba337b9a`.
- LoRA and Fine Head (`Linear(4096, 6)`, weight shape `6 x 4096`) loaded from step 1794; no fallback checkpoint was used. The PEFT adapter declares `modules_to_save=null`, so the original LM Head is not replaced by checkpoint modules.
- Known label order: Normal, DDoS_HTTP, DDoS_TCP, Password, SQL_injection, Vulnerability_scanner.
- Validation: 3,231 `EXACT_EVAL_CLEAN` records, SHA256 `d03228c3062028316786b1483dd7086c199bc03d142c5b9bfbc4ff6e9f352fe7`.
- Train/validation opaque sample-ID overlap: 0.
- Basic-sufficiency references are a one-to-one join to the pre-model Observable-v3 eligibility assessment. They are not derived from Model A predictions and are not Teacher annotations retrofitted after evaluation.
- The formal run and checkpoint remained read-only.

## Known classification

| Metric | Final Model A |
| --- | ---: |
| Records | 3,231 |
| Accuracy | 0.9984524915 |
| Macro precision | 0.9988932407 |
| Macro recall | 0.9980789474 |
| Macro F1 | 0.9984831208 |
| Micro F1 | 0.9984524915 |

`FORMAL_MACRO_F1_REPRODUCED=true`: the recomputed Macro-F1 exactly equals the epoch-2/completion value `0.9984831207613943`.

| Class | Precision | Recall | F1 | Support |
| --- | ---: | ---: | ---: | ---: |
| Normal | 0.996012 | 0.999000 | 0.997504 | 1,000 |
| DDoS_HTTP | 1.000000 | 1.000000 | 1.000000 | 156 |
| DDoS_TCP | 1.000000 | 1.000000 | 1.000000 | 127 |
| Password | 1.000000 | 1.000000 | 1.000000 | 1,000 |
| SQL_injection | 1.000000 | 1.000000 | 1.000000 | 568 |
| Vulnerability_scanner | 0.997347 | 0.989474 | 0.993395 | 380 |

The 2,694 Basic-sufficient records reach Macro-F1 `0.9988867952`; the 537 Basic-insufficient records reach `0.9973544974`. Basic-insufficient classification is slightly harder, but the difference is small. Closed-set classification performance therefore does not validate the active-evidence hypothesis by itself.

## Actual Evidence-State generation

The final LoRA LM generated one deterministic response for every formal validation input using the exact `TRAFFIC_EXPERT_PROMPT_V3`, compact serialization, strict `EvidenceStateV2` parser, and current grounding checks.

| Subset | N | Schema valid | Severe hallucinations | Sufficiency accuracy | Sufficiency F1 | Gap micro F1 | Gap exact match |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Overall | 3,231 | 1.000000 | 0 | 0.835345 | 0.910135 | 0.000000 | 0.833798 |
| Basic-sufficient | 2,694 | 1.000000 | 0 | 1.000000 | 1.000000 | 0.000000 | 1.000000 |
| Basic-insufficient | 537 | 1.000000 | 0 | 0.009311 | 0.000000 | 0.000000 | 0.000000 |

The overall sufficiency F1 is misleading because `sufficient` is the majority positive class. Model A predicted 2,694/2,694 sufficient records correctly but only 5/537 insufficient records correctly; 532 insufficient records were false-positive sufficient. It did not recover the pre-model missing-family targets. This is a substantive capability failure, not a schema or hallucination failure.

## Classification controls

| System | Training supervision | Accuracy | Macro F1 | Interpretation |
| --- | --- | ---: | ---: | --- |
| Raw Qwen zero-shot | none | 0.848344 | 0.561750 | 3,230/3,231 valid; DDoS_HTTP and DDoS_TCP F1 are zero |
| Frozen-base limited linear probe | 600 TRAIN primary records/class; 3,600 total | 0.993810 | 0.981563 | High base separability, but below the 0.99 early-stop threshold |
| Formal multi-task SFT | 11,958 TRAIN primary sessions plus controlled Evidence states | 0.998452 | 0.998483 | Exact formal reproduction |
| Final head on base representation | diagnostic only | 0.117611 | 0.035078 | Formal head is strongly dependent on the adapted representation; not a fair baseline |

Limited-probe per-class F1: Normal `0.998999`, DDoS_HTTP `0.970297`, DDoS_TCP `0.933824`, Password `1.000000`, SQL_injection `0.998243`, Vulnerability_scanner `0.988016`.

The user-requested early-stop contract was followed. The initial interrupted prefix contained 2,256 legal TRAIN records but only DDoS_HTTP (2,014) and DDoS_TCP (242), so it was not a valid six-way training set. A deterministic SHA256-ranked subset of 600 records per class was used instead; 663 already extracted features were reused. No validation representation or label participated in optimization. The remaining 8,358 TRAIN primary features were not extracted.

```text
TRAIN_FEATURE_COUNT=3600
TRAIN_FEATURE_CLASS_COUNTS={Normal:600,DDoS_HTTP:600,DDoS_TCP:600,Password:600,SQL_injection:600,Vulnerability_scanner:600}
VALIDATION_COUNT=3231
BASE_REPRESENTATION_ALREADY_HIGHLY_SEPARABLE=false
LIMITED_DATA_PROBE_BELOW_SFT=true
LIMITED_PROBE_GAP_IS_EXACT_LORA_UPLIFT=false
```

Because limited-probe Macro-F1 is `0.981563 < 0.99`, the strict `BASE_REPRESENTATION_ALREADY_HIGHLY_SEPARABLE` flag remains false. The base representation is nevertheless already highly useful. The `0.016920` Macro-F1 difference is not an exact LoRA causal effect because the probe used 3,600 rather than 11,958 training sessions.

## Acceptance boundary

Model A is accepted for warm start because checkpoint loading, exact classification reproduction, split isolation, prompt/schema legality, and a classification value signal all pass. The signal is bounded: Formal is far above raw Qwen, above the limited balanced probe, and its Fine Head fails when applied to unadapted representations. `LINEAR_HEAD_ONLY_EXPLAINS_RESULT=partially`; the current experiment cannot isolate the exact gain from more supervised examples versus LoRA representation learning.

The Evidence-State failure is a mandatory Model B regression target. Model B planning must require a balanced sufficient/insufficient validation gate and must not proceed to RLAIF until insufficient-state and missing-family performance improve materially.

Large predictions, feature caches, matrices, and the authoritative evaluation manifest remain Git-external at `/root/autodl-tmp/processed/evaluation/model_a_formal_v1/`.
