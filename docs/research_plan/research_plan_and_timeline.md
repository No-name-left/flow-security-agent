# 网络流量开放识别与自适应取证智能体：Near-first执行计划与时间表

> Derived from the canonical `research_plan_detailed.md`; updated 2026-08-13.
>
> Research meaning follows the canonical plan. Training/Open-world execution follows `docs/training/near_mainline_training_protocol_v1.md`. This file only summarizes order, dependencies, Gates and status.

## 1. ONE_MAINLINE_FIRST

The only first end-to-end route is Edge-IIoTset **Near**:

```text
Phase A/B reusable infrastructure (complete)
→ Task Definition v2 + Evidence-v2
→ Observable Dataset v3 eligibility across train/validation/test
→ Teacher-v2 + SFT corpus v3 acceptance
→ Raw/Traditional baselines
→ Multi-task SFT
→ RLAIF-GRPO + classification CE
→ Independent Unknown
→ Application/Payload/RAG + Agent
→ Experience Memory
→ 1/5/10-shot Class Memory
→ NEAR_MAINLINE_COMPLETE
```

Far, Mixed, IoT-23 and optional ablations remain in the plan but are `DEFERRED_UNTIL_NEAR_MAINLINE_COMPLETE`. They are not parallel first-development tracks.

## 2. Task Definition v2 inputs

| Item | Value |
| --- | --- |
| Seed | Dataset selection `20260813`; formal training `20260809` |
| Main classes | Normal, DDoS_HTTP, DDoS_TCP, Password, SQL_injection, Vulnerability_scanner（6）；MITM/Port_Scanning排除 |
| U_dev | DDoS_ICMP, OS_Fingerprinting |
| U_final | DDoS_UDP, XSS |
| Physical split | `CONSTRAINED_CHRONOLOGICAL_BOUNDARY_V2` |
| Dataset v3 split policy | final=`CONSTRAINED_CHRONOLOGICAL_BOUNDARY_V2_PER_SPLIT_ELIGIBILITY_FILTERED`；没有重分split |
| Excluded main roles | Backdoor→Long-Horizon Temporal Case Study; Uploading/Ransomware→Observability-Limited/Abstain |

旧11类PLAN_B、Teacher V3和22,957-record corpus为superseded historical，不能进入formal SFT。不得依据模型结果修改final classes或eligibility；validation、test、U_dev和U_final不能进入Teacher-v2/SFT。

## 3. Current infrastructure status

| Component | Status |
| --- | --- |
| Production Data Freeze | `PRODUCTION_DATA_READY=true`; PASS_WITH_LIMITATIONS |
| Edge v2 split | train 5,294,777; validation 1,073,539; test 1,110,343; quarantine 140,373 |
| Identity leakage / U_final isolation | 0 / PASS |
| Runtime Adapter | `production_runtime_adapter_v1`; READY=true |
| Evidence schema | `production_runtime_evidence_v1` |
| Evidence Fidelity | PASS |
| v1 Initial / packets 9–16 / Temporal / Relation | REUSABLE FOUNDATION；不等于Evidence-v2完成 |
| Basic-v2 / packet-aligned payload / Temporal-v2 / Relation-v2 / Application-v2 | **IMPLEMENTED / PASS**；17 captures Evidence-only scan |
| Qwen raw deployment | official revision `c202236...`; local/runtime smoke PASS |
| Full deployment-audit pytest | 261 passed; latest repository regression after CI portability fix: 264 passed |
| Dataset v3 / Teacher-v2 / corpus v3 | **PASS / PASS / PASS**；1,318,688/270,851/279,057；20,807 annotations；14,350 records |
| SFT / RL / Unknown / formal benchmark | READY_NOT_STARTED / NOT RUN / NOT FROZEN / NOT RUN |

The raw service is vLLM BF16 text-only, 8192 context, non-thinking/direct-response. It does not expose hidden states and therefore does not replace the training-side Fine Head harness.

## 4. Model/training dependency chain

```text
Official frozen Qwen base
→ LoRA + Linear Fine Classification Head + LM Evidence State
→ Checkpoint A: Near Multi-task SFT
→ clone/reference A
→ RLAIF-GRPO + Fine Head classification CE
→ Checkpoint B
→ freeze primary Qwen
→ Independent Unknown using K validation + U_dev
→ freeze all final-route development settings
→ first U_final evaluation
```

The Fine Head is the sole trained fine-class source; coarse uses deterministic mapping. `CLASSIFICATION_SUFFICIENCY_DECOUPLED_V1` makes one legal primary per TRAIN K-known session CE-eligible independently of Teacher sufficiency; controlled lower-evidence auxiliaries mask CE. GT stays backend-only. GRPO optimizes Evidence behavior, not Fine Head correctness as a group-relative reward; Fine classification remains a separate CE term.

## 5. Phase schedule

| Phase | Work | Status / Gate |
| --- | --- | --- |
| A | Production, v2 split, PLAN_B, Safe Adapter, Fidelity, raw Qwen deployment | **COMPLETE / PASS_WITH_LIMITATIONS** |
| B | Transformers/PEFT harness; pooling; LoRA inventory assertion; serialization v1; Prompt/schema v1; Application/Payload contracts; RAG Evidence Contract | **COMPLETE / PASS_WITH_LIMITATIONS** |
| C | Raw Near Qwen and LightGBM/XGBoost/RF strong baselines | NOT STARTED |
| C0 | Evidence-v2 + all-split eligibility + Observable Dataset v3 | **COMPLETE / PASS** |
| D | Build Basic-v2 primary + at most 1–2 meaningful auxiliary states from eligible TRAIN | **COMPLETE / PASS** |
| E | DeepSeek Teacher-v2 40-state smoke, resumable 20,807-state bulk, consistency and bounded review | **COMPLETE / PASS** |
| E2 | Corpus v3, session-weight/label-map/preflight/blind sanity acceptance | **COMPLETE / PASS**；11,958 sessions / 14,350 records |
| F | Training #1 classification-first Multi-task BF16 LoRA SFT | Checkpoint A |
| G | SFT validation/evaluation | no formal test/U_final tuning |
| H | Fixed reproducible RL Prompt Pool | K_known TRAIN only |
| I | Training #2 RLAIF-GRPO + classification CE | Checkpoint B |
| J | RL validation/evaluation | no U_final |
| K | Freeze final primary Qwen | immutable Checkpoint B |
| L | Compare margin/entropy/energy/prototype Unknown | K validation + U_dev only |
| M | Freeze Unknown | score/threshold immutable |
| N | First U_final open-set evaluation | one-way sealed evaluation |
| O | Complete/finalize Application, Payload, RAG | all contracts/assets frozen |
| P | Basic, Fixed Full, RulePolicy, DeepSeek Flash Supervisor | budget/information matched |
| Q | Experience Memory experiment | TRAIN verified writes; eval read-only |
| R | 1/5/10-shot Class Memory | no immediate continual LoRA |
| S | Near complete | `NEAR_MAINLINE_COMPLETE=true` |

Safety dependency: if O/P contains settings that can affect the evaluated U_final route, freeze them before N. Phase labels never permit U_final-driven sanitizer, RAG, Supervisor or Memory tuning.

## 6. DeepSeek execution roles

DeepSeek Flash is the current configurable default for three isolated roles:

- Teacher: Evidence-State corpus assistance, with verified GT only as immutable context;
- Judge: online/asynchronous semantic reward for current-policy GRPO rollouts;
- Supervisor: formal inference action choice, never GT and never direct fine reclassification.

Each role has independent Prompt, Schema, permissions, cache and logs. Codex implements and runs the orchestration but is not the formal Teacher/Judge.

## 7. Agent and evidence Gates

Final Near Agent tools are Initial, packets 9–16, Temporal, Graph, Application, Sanitized Payload and Knowledge RAG. Only real AVAILABLE evidence is legal. RAG is on-demand for knowledge gaps; Observation gaps require real traffic evidence.

Formal comparison includes Basic, Fixed Full, RulePolicy and DeepSeek Flash Supervisor with the same Qwen, tool domain and maximum budget. The first Agent experiment runs without Experience Memory; Memory is a later isolated experiment.

## 8. Evaluation isolation

No formal test or U_final may select:

- Prompt/serialization/pooling/LoRA/hyperparameters;
- Teacher/Judge rubric;
- Unknown algorithm/threshold;
- sanitizer, KB, retriever or RAG top-k;
- Supervisor prompt/budget/policy;
- Memory retrieval settings.

Temporal/Graph/Memory evaluation is chronological within capture/scenario. One reconstructed session remains one result.

## 9. Deferred after Near completion

- Pure Generative SFT ablation;
- DPO;
- Far and Mixed training/evaluation;
- IoT-23 external validation execution;
- tokenizer training/ablation;
- QLoRA main experiment and thinking-on;
- Low-Resource Unknown Stress Test;
- Learnable Agent Policy RL;
- continual LoRA and Agent Growth.

## 10. Current stop point

DEC-0022 records completion of DEC-0021 while retaining DEC-0020's classification/sufficiency decoupling. `SFT_RUN=false`, `RL_RUN=false`, `UNKNOWN_ALGORITHM_FROZEN=false`, and `READY_FOR_FORMAL_SFT=true`.

**NEXT ACTION: `START_FORMAL_NEAR_MULTI_TASK_SFT`.** Formal SFT is now authorized only through`NEAR_SFT_CONFIG_V2`; no optimizer run has started. GRPO, Unknown, U_final and Agent experiments remain unauthorized.
