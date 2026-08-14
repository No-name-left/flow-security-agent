# 成本感知主动证据获取：Model A→Model B执行计划与时间表

> Derived from the canonical `research_plan_detailed.md`; updated 2026-08-14.
>
> Research meaning follows the canonical plan. Training/Open-world execution follows `docs/training/near_mainline_training_protocol_v1.md`. This file only summarizes order, dependencies, Gates and status.

## 1. 当前正式路线

核心问题是`cost-aware active / sequential observation-evidence acquisition for LLM-based malicious traffic analysis`：Qwen先读取廉价Basic-v2，分别输出Fine Classification与Evidence State；若Observation不足，Supervisor选择一个bounded action，Runtime确定性执行并让Qwen重评；Evidence充分时停止。LLM traffic classification、Agent、RAG与few-shot本身都不是本文创新中心。

```text
Edge Dataset v3 + Teacher-v2 + corpus v3 (complete)
→ Model A Formal Multi-task SFT (in progress)
→ Model A validation/evaluation
→ CICIDS2017 + ToN-IoT compatibility
→ common label/session/evidence pipeline
→ Model B multi-domain continuation SFT
→ Basic / Full / Static / Rule / Agent experiments
→ mixed-domain RLAIF after baselines stabilize
→ final Unknown/OOD, ablation and writing
```

Model A不会因多数据集路线而废弃：它是single-domain controlled benchmark、Model B warm start与Edge replay安全锚点。Few-shot novel-class registration降为Future Work/Optional Extension，不进入关键路径。

## 2. Model A冻结输入与Model B目标

| Item | Value |
| --- | --- |
| Seed | Dataset selection `20260813`; formal training `20260809` |
| Main classes | Normal, DDoS_HTTP, DDoS_TCP, Password, SQL_injection, Vulnerability_scanner（6）；MITM/Port_Scanning排除 |
| U_dev | DDoS_ICMP, OS_Fingerprinting |
| U_final | DDoS_UDP, XSS |
| Physical split | `CONSTRAINED_CHRONOLOGICAL_BOUNDARY_V2` |
| Dataset v3 split policy | final=`CONSTRAINED_CHRONOLOGICAL_BOUNDARY_V2_PER_SPLIT_ELIGIBILITY_FILTERED`；没有重分split |
| Excluded main roles | Backdoor→Long-Horizon Temporal Case Study; Uploading/Ransomware→Observability-Limited/Abstain |

旧11类PLAN_B、Teacher V3和22,957-record corpus为superseded historical，不能进入formal SFT。不得依据模型结果修改Model A final classes或eligibility；validation、test、U_dev和U_final不能进入Teacher-v2/SFT。

Model B第一优先为CICIDS2017与ToN-IoT；兼容性和时间允许时增加CSE-CIC-IDS2018。统一的是session semantics、label semantics与Observation Evidence interface，而不是直接concat CSV。Canonical label保存`source_label / canonical_family / canonical_fine_label / mapping_quality(EXACT|FAMILY_ONLY|UNSUPPORTED)`；`FAMILY_ONLY`不得强行映射到DDoS_HTTP/DDoS_TCP等细类。

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
| Model A Formal SFT / RL / Unknown / formal Agent benchmark | **IN PROGRESS** / NOT RUN / NOT FROZEN / NOT RUN |

The raw service is vLLM BF16 text-only, 8192 context, non-thinking/direct-response. It does not expose hidden states and therefore does not replace the training-side Fine Head harness.

## 4. Model/training dependency chain

```text
Official frozen Qwen base
→ LoRA + Linear Fine Classification Head + LM Evidence State
→ Model A: Edge Formal Multi-task SFT + validation
→ CICIDS2017/ToN-IoT common data contract
→ expand Fine Head 6→K; copy mapped rows
→ Model B: Edge replay + external balanced continuation SFT
→ Basic/Full/Static/Rule/Agent baselines
→ optional mixed-domain RLAIF + Fine Head classification CE
→ freeze primary Qwen/Agent route
→ Independent Unknown using K validation + U_dev
→ freeze all final-route development settings
→ first U_final evaluation
```

The Fine Head is the sole trained fine-class source; coarse uses deterministic mapping. `CLASSIFICATION_SUFFICIENCY_DECOUPLED_V1` makes one legal primary per TRAIN K-known session CE-eligible independently of Teacher sufficiency; controlled lower-evidence auxiliaries mask CE. GT stays backend-only. Model B warm-starts Model A, replays Edge and uses dataset/class-aware sampling; large external domains must not erase Model A. GRPO optimizes Evidence behavior, not Fine Head correctness as a group-relative reward; Fine classification remains a separate CE term.

## 5. Phase schedule

| Phase | Work | Status / Gate |
| --- | --- | --- |
| 1A | Production、v2 split、Safe Adapter、Task Definition v2、Dataset/Evidence/Teacher/corpus v3 | **COMPLETE / PASS**；Model A输入冻结 |
| 1B | Model A classification-first Multi-task BF16 LoRA SFT | **IN PROGRESS**；不得由文档任务干扰 |
| 2 | Model A正式validation/evaluation与checkpoint冻结 | SFT完成后；no formal test/U_final tuning |
| 3A | CICIDS2017 `MULTI_DATASET_COMPATIBILITY_GATE` | label/raw/GT/session/Evidence/leakage/group split |
| 3B | ToN-IoT `MULTI_DATASET_COMPATIBILITY_GATE` | 同上；CSE-CIC-IDS2018为条件性第三候选 |
| 4 | Dataset-specific adapter → common session → canonical label/evidence → grouped split | 构造multi-domain corpus；不直接concat CSV |
| 5 | Model B continuation SFT | warm-start Model A；Edge replay；dataset/class-balanced sampling |
| 6 | Basic-only / Full-Evidence One-Shot / Strong Static / Rule / Supervisor | shared Qwen、information domain、max budget |
| 7 | mixed-domain RLAIF-GRPO + classification CE | 仅在SFT与Agent baselines稳定后；共享policy |
| 8A | Independent Unknown | Known validation + U_dev only；Unknown != insufficient/abstain |
| 8B | First U_final + ablation + statistics + writing | one-way sealed evaluation；few-shot不在关键路径 |

Safety dependency: any sanitizer, RAG, Supervisor, Evidence action, Memory or Unknown setting that can affect U_final must freeze before Phase 8B. Phase labels never permit U_final-driven tuning.

## 6. DeepSeek execution roles

DeepSeek Flash is the current configurable default for three isolated roles:

- Teacher: Evidence-State corpus assistance, with verified GT only as immutable context;
- Judge: online/asynchronous semantic reward for current-policy GRPO rollouts;
- Supervisor: formal inference action choice, never GT and never direct fine reclassification.

Each role has independent Prompt, Schema, permissions, cache and logs. Codex implements and runs the orchestration but is not the formal Teacher/Judge.

## 7. Agent and evidence Gates

Observation Evidence为Basic、Packet/Payload、Application、Temporal与Relation；Knowledge RAG严格独立。Only real AVAILABLE evidence is legal. RAG只处理knowledge gap；Observation gap必须由真实traffic evidence回答。Evidence充分时停止，不为了展示Agent而继续调用工具。

Formal comparison includes Basic-only, Full-Evidence One-Shot, Strong Static, RulePolicy and DeepSeek Flash Supervisor with the same Qwen, tool domain and maximum budget. Metrics include Accuracy/Macro-F1、per-class、Evidence calls、tokens、latency、cost与stop behavior。The first Agent experiment runs without Experience Memory; Memory is a later isolated experiment.

## 8. Evaluation isolation

No formal test or U_final may select:

- Prompt/serialization/pooling/LoRA/hyperparameters;
- Teacher/Judge rubric;
- Unknown algorithm/threshold;
- sanitizer, KB, retriever or RAG top-k;
- Supervisor prompt/budget/policy;
- Memory retrieval settings.

Temporal/Graph/Memory evaluation is chronological within capture/scenario. One reconstructed session remains one result.

## 9. Deferred / optional work

- Pure Generative SFT ablation;
- DPO;
- Far and Mixed secondary presets;
- IoT-23 and other historical adapter-based external checks outside the first Model B domains;
- tokenizer training/ablation;
- QLoRA main experiment and thinking-on;
- Low-Resource Unknown Stress Test;
- Learnable Agent Policy RL;
- continual LoRA and Agent Growth;
- few-shot novel-class registration / Class Memory onboarding.

## 10. Current stop point

DEC-0022 records Model A data/corpus acceptance while retaining DEC-0020's classification/sufficiency decoupling. DEC-0023 freezes active/sequential Observation-Evidence acquisition as the core question and adds the Model B route. Model A `READY_FOR_FORMAL_SFT=true`; Formal SFT is now **IN PROGRESS**. `RL_RUN=false` and `UNKNOWN_ALGORITHM_FROZEN=false`.

**NEXT ACTION: safely finish and validate Model A, then run the CICIDS2017 and ToN-IoT Compatibility Gates.** Do not restart or replace the current Formal SFT. GRPO, Unknown, U_final and formal Agent experiments have not started. Few-shot is not a required milestone.
