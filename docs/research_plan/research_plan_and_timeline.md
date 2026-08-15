# Open-World Continually Evolving LLM Traffic Agent：执行计划与时间表

> Derived from DEC-0024 and the canonical `research_plan_detailed.md`; updated 2026-08-15.
>
> 本文件只总结顺序、依赖、Gate与状态，不授权下载、训练、API调用、RL或U_final访问。

## 1. 当前路线

```text
Phase 0  Freeze Model A [COMPLETE]
→ Phase 1  Source Compatibility Preflight
→ Phase 2  Evidence Utility Pilot
→ Phase 3  Dataset-v4 Static + Continual Build
→ Phase 4  Static Model B0 + Unknown/LLM-value baselines
→ Phase 5  Open-world continual baseline with verified feedback/replay
→ Phase 6  RL-1 low-cost policy vs Heuristic
→ Phase 7  gated Evidence/RAG/RL-2 enhancements
→ Phase 8  sealed evaluation, ablation and writing
```

Active Evidence、Model A warm start、最终Dataset-v4组成、Evidence Decision Head、Unknown detector、clustering与RL算法均为`PROVISIONAL`，不得跳过对应cheap Gate。

## 2. Phase 0 — Model A freeze

| Item | Frozen result |
| --- | --- |
| Model A role | `LEGACY_CONTROLLED_DOMAIN + MODEL_A_BASELINE + OPTIONAL_REPLAY_SOURCE` |
| Formal classification | Macro-F1 `0.9984831208`; accuracy/micro-F1 `0.9984524915` |
| Raw Qwen | Macro-F1 `0.5617499100` |
| Frozen-Qwen limited probe | 3,600 balanced TRAIN records; Macro-F1 `0.9815630113` |
| Basic-sufficient classification | 2,694 records; Macro-F1 `0.9988867952` |
| Basic-insufficient classification | 537 records; Macro-F1 `0.9973544974` |
| Evidence-State | **FAIL**: Basic-insufficient sufficiency F1 `0`; gap micro-F1 `0`; 532/537 false sufficient |
| Formal checkpoint | immutable; no further Model A training authorized here |

Exit decision: closed-set classification is not the primary innovation; current LM Evidence State cannot control runtime acquisition; Teacher semantic sufficiency is not operational utility.

## 3. Phase 1 — Dataset Source Preflight

| Source role | Datasets | Scope |
| --- | --- | --- |
| Primary compatibility candidates | CICIDS2017, CSE-CIC-IDS2018, ToN-IoT | small metadata/assets, few captures/runs, hundreds of sessions |
| Legacy controlled source | Edge-IIoTset-clean | Model A baseline, regression, optional replay |
| Fallback/gap filling | Bot-IoT, UNSW-NB15, DoHBrw, USTC-TFC2016 | only if primary coverage/gates justify |

For each source, freeze:

```text
RAW / OFFICIAL_GT / GT_UNIT / SESSION_MAPPING
OBSERVABILITY / LEAKAGE / GROUP_SPLIT
TAXONOMY(EXACT|FAMILY_ONLY|AMBIGUOUS|UNSUPPORTED)
EVIDENCE_CAPABILITY / RESOURCE_BUDGET
```

Exit is an individual `PASS | PASS_WITH_LIMITATIONS | FAIL` matrix and a provisional final-source recommendation. No full download or PCAP processing occurs in this phase. A capture/file-level label that cannot support session GT is an immediate hard fail.

## 4. Phase 2 — Evidence Utility Pilot

Use hundreds of sessions from compatible sources. For each session, compare Basic with Basic plus one legal Evidence family. Extract frozen representations once; produce operational utility only with stratified 5-fold OOF/cross-fitting so no evaluated sample trained its own probe.

Report by class/subset:

- accuracy and Macro-F1 delta;
- cross-entropy delta;
- incorrect→correct and correct→incorrect flips;
- confidence change;
- bootstrap interval and second seed/reference-model direction.

Exit:

- `GO`: at least one Evidence family has stable, repeatable operational gain on a meaningful difficult subset;
- `NO_GO`: Basic is saturated and additional Evidence has negligible or unstable gain.

Only `GO` permits an Evidence Decision Head, Evidence-action expansion or Evidence RL. Teacher semantic relevance is not the target.

## 5. Phase 3 — Dataset-v4 full build

This phase starts only after Phase 1 and the resource decision.

```text
Raw PCAP / Logs / Official GT
→ dataset-specific GT Adapter / private SourceAttackEvent
→ Common Sessionizer
→ CanonicalSession + CanonicalLabel + CanonicalEvidenceBundle
→ grouped/chronological static split
→ K0 / U_dev / sealed U_final / U_inc stages
→ continual stream with hidden future GT
```

Fine supervision uses `EXACT` mappings only. `FAMILY_ONLY` enables Family loss and masks Fine loss. `AMBIGUOUS/UNSUPPORTED` are not main supervised samples. Canonical synonyms receive one semantic role across all datasets.

Exit requires GT/session assignment, identity/leakage, split, future-knowledge, evidence-capability and resource manifests to pass. U_final remains sealed.

## 6. Phase 4 — Static Model B0

Model B0:

```text
Qwen3.5-9B frozen base + LoRA → shared h
h → Linear Family Head
h → Linear Fine Head
h/logits → MSP / Energy / Prototype Unknown
LM Head → explanation/descriptive output only
```

Required cheap ablations:

1. base Qwen + fresh LoRA versus Model A LoRA warm start, matched data/steps/LR/heads;
2. LightGBM or equivalent legal structured baseline;
3. Frozen-Qwen + linear heads;
4. Qwen + LoRA Model B0;
5. optional compact traffic encoder if low cost.

Primary evaluation is cross-domain, open-set and robustness, not pooled IID alone. U_dev selects MSP/Energy/Prototype thresholds; U_final never does. Exit freezes B0, Unknown candidate/threshold, K0 and regression tolerances.

## 7. Phase 5 — Open-world continual baseline

Run the frozen stream with hidden GT:

```text
Known / drift / U_inc arrival
→ Known decision or Unknown Buffer
→ REQUEST_ANALYST_FEEDBACK
→ verified label
→ cluster review / new-class confirmation
→ episodic adaptation: verified new + balanced old replay
→ old/new/Unknown/cross-domain Release Gate
→ release B_{t+1} or rollback B_t
```

Start with simple density clustering and balanced replay. No per-sample gradient updates and no self-confirmation. Exit is a reproducible non-RL evolution loop with discovery delay, new/old performance and forgetting metrics.

## 8. Phase 6 — RL-1 policy

First implement `RL-0 HEURISTIC` using frozen thresholds, buffering, analyst-query and adaptation rules. Then, only if the continual environment has meaningful sequential decisions, train a small `RL-1` policy with Qwen frozen.

Compare long-term classification, Unknown detection, discovery delay, analyst queries, Evidence cost, adaptation count, forgetting and total compute. If RL does not reproducibly beat Heuristic, record No-Go and stop RL expansion.

## 9. Phase 7 — Conditional enhancements

These are not automatic milestones:

- Evidence Decision Head and Evidence actions: only after Utility Gate PASS;
- RAG enhancement: only with stage-aware `RAG_VERSION_t` and future-label exclusion;
- RL-2 Qwen policy LoRA/PPO/GRPO: only after RL-1 PASS, trustworthy delayed reward, adequate trajectories/GPU and advisor confirmation;
- complex continual methods: only if balanced replay exposes a material limitation.

DeepSeek may supply offline demonstrations/review and an optional Supervisor baseline. It is not the permanent online evolution authority.

## 10. Phase 8 — Final evaluation

After all route-affecting settings freeze, run sealed U_final and report:

- Known Accuracy/Macro-F1 and per-class results;
- AUROC/AUPR/FPR@95TPR, Unknown precision/recall/open-set F1 and optional OSCR;
- cross-domain and cross-run/capture results;
- new-class discovery delay, verified-query count and class registration accuracy;
- old-class forgetting and release/rollback outcomes;
- Agent action, Evidence, token, latency, compute and analyst costs;
- LLM value, warm-start, Unknown, replay, Evidence and policy ablations.

U_final never changes model, threshold, taxonomy, RAG, Evidence, policy or release settings.

## 11. Current status

```text
PHASE_0_MODEL_A_FREEZE=COMPLETE
PHASE_1_SOURCE_PREFLIGHT=NOT_STARTED
PHASE_2_EVIDENCE_UTILITY=NOT_STARTED
PHASE_3_DATASET_V4_BUILD=NOT_STARTED
PHASE_4_MODEL_B0=NOT_STARTED
PHASE_5_CONTINUAL_BASELINE=NOT_STARTED
PHASE_6_RL1=NOT_STARTED
PHASE_7_CONDITIONAL=NOT_AUTHORIZED
PHASE_8_FINAL_EVAL=NOT_STARTED

ACTIVE_EVIDENCE_STATUS=PROVISIONAL_PENDING_GATE
MODEL_A_WARM_START_STATUS=PROVISIONAL_PENDING_ABLATION
FEW_SHOT_STATUS=OUT_OF_SCOPE
RLAIF_OLD_STATUS=DOWNGRADED
ADVISOR_CONFIRMATION_REQUIRED=true
```

**NEXT ACTION:** separately authorize Source Compatibility Preflight and the bounded Evidence Utility Pilot design. Do not start bulk data work, Teacher labeling, Model B0 training, RL or U_final.
