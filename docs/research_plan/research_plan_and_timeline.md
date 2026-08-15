# Open-World Continually Evolving LLM Traffic Agent：执行计划与时间表

> 状态：DEC-0025 canonical execution order
>
> 日期：2026-08-15
>
> 本文件只定义阶段、依赖、Gate与停止点；研究语义以[research_plan_detailed.md](research_plan_detailed.md)为最高权威，Model B细节见[model_b_evidence_openworld_design.md](model_b_evidence_openworld_design.md)。

## 1. 当前路线与已完成基础

方法核心是：

```text
Evidence-Conditioned Open-World Traffic Recognition
+ Empirically Grounded Typed-Evidence Acquisition
+ Evidence-Gated Continual Evolution
```

Model A已经冻结为single-domain controlled baseline和optional replay source；其closed-set分类成功，但LM Evidence-State branch对目标用途失败。NF3-ToN官方final processed artifact已通过reconciliation/schema/label Gate，24,000条pilot确认存在recoverable Known、可预测的Evidence utility和aggregate Evidence-conditioned open-world收益。

当前只完成计划与架构收口，没有启动Model B、DeepSeek、continual、RL、下载或raw reprocessing。

## 2. Phase B1 — Dataset-v4 / NF3-ToN formalization

目标：把已验证的NF3-ToN artifact冻结成可训练、可复现且无leakage的Dataset-v4 core。

必须完成：

- 验证固定CSV SHA256 `53ec8f468a43ede9b1536fabc0390af2fa33ab4312b23ce4d864f186a4651f78`；
- 冻结candidate taxonomy的最终保留类、label map和per-class support；
- 设计deterministic grouped/temporal train/development/test split；
- 冻结`BASIC_SUFFICIENT_KNOWN / RECOVERABLE_KNOWN / TRUE_UNKNOWN`合同；
- 预注册whole-class held-out Unknown rotations，不让held-out class进入classifier training或final threshold tuning；
- 冻结Basic、Temporal和Relation的semantic admissibility、availability、cost与model-safe serialization；
- 通过identity、source、time、label、future-context和cross-split leakage Gate。

输出：small tracked manifest/report/config；大数据保持Git-external。taxonomy和rotations由本阶段结果冻结，不因pilot表现事后挑选。

## 3. Phase B2 — Model B static foundation

目标：建立Known representation/classification与独立novelty interface，不进行Evidence acquisition策略或continual update。

低成本Gate：

1. fresh initialization vs matched Model-A warm start；
2. Qwen vs smaller traffic encoder/strong structured baseline；
3. Frozen-Qwen linear heads vs Qwen adaptation；
4. MSP、margin、energy和prototype distance的development-only comparison。

只有matched evidence说明warm start或Qwen共享表示有额外价值时才保留相应复杂度。True Unknown不是Fine Head的`K+1`类。

## 4. Phase B3 — Formal typed-Evidence utility

目标：把semantic admissibility与operational utility分离，并正式验证哪个Evidence family值得获取。

执行顺序：

```text
Basic
Basic + Temporal
Basic + Relation
Basic + Temporal + Relation
```

每个sample的utility outcome必须由OOF/cross-fitted预测产生。比较`ΔNLL`、correctness recovery、FURK变化和acquisition cost；训练small Utility Head或external selector的选择由简单性优先的matched pilot决定。必须执行second seed或bootstrap robustness，逐类披露Recon_Scanning、Web_Injection、Credential等相反收益。

Application、Payload、Knowledge只在数据可用、语义合法且utility Gate通过时追加；不是第一轮必需action。

## 5. Phase B4 — Evidence-conditioned open-world evaluation

正式比较三条路径：

1. `Basic → Direct Novelty`；
2. `Basic uncertainty → Always Acquire Full → Novelty`；
3. `Basic uncertainty → Utility-conditioned Evidence Acquisition → Novelty`。

这一区分“额外信息本身的收益”和“智能选择Evidence的收益”。报告Macro-F1、Unknown AUROC/AUPR、OSCR、FURK、Evidence Recovery Rate、Acquisition Rate、Average Acquisition Cost和Known accuracy after recovery，并提供overall/per-class/bootstrap结果。

进入Unknown的必要条件是Evidence recovery已完成、无可用family或预测收益不值得成本。observability-limited样本不得进入True Unknown主评测。

## 6. Phase B5 — Continual evolution

仅在B1–B4 static foundation稳定后开始：

```text
Residual Unknown
→ Unknown Buffer
→ optional clustering
→ verified feedback
→ REGISTER_NEW_CLASS
→ supervised continual adaptation + old replay
→ regression/release gate or rollback
```

比较head-only与parameter-efficient adaptation；报告buffer purity、可选clustering ARI/NMI、新类学习、旧类遗忘、label-query count及release结果。self-label、confidence和cluster tightness不得作为GT。

当前状态：`LITERATURE_SUPPORTED_IMPLEMENTATION_PENDING`，不是B1–B4 blocker。

## 7. Phase B6 — Optional RL policy comparison

RL不是主研究成立条件。只有deterministic/supervised utility controller已稳定，且仍存在明确、可重复的sequential decision gap时，才比较：

```text
Utility Heuristic / Supervised Policy
vs
Small RL Policy
```

RL必须同时改善效果或cost-quality tradeoff。PPO/GRPO/RLAIF不是默认阶段；LLM-level RL为`HIGH_COST_NOT_AUTHORIZED`。

## 8. Secondary replication与conditional extension

`NF3-UNSW-NB15`、`NF3-BoT-IoT`和`NF3-CSE-CIC-IDS2018`只作secondary external-domain stress/replication candidates。已有cross-source weak/domain-dependent结果必须披露，但不阻塞core。

CICIoT2023、raw CIC和raw ToN均不属于core依赖。只有后续明确研究问题通过utility Gate且必须使用packet/payload时，才另行决策；当前不下载。

## 9. 跨阶段硬边界

- OOF/cross-fitting先于utility supervision；
- whole-class Unknown holdout先于模型结果；
- U/final Unknown不得训练classifier或调threshold；
- GT class不得进入runtime selector；
- Unknown只能在Evidence gate之后；
- verified feedback先于class registration与参数更新；
- low-cost ablation先于高成本训练；
- 每阶段失败时缩减路线，不用后续复杂度掩盖前置Gate失败。

## 10. 当前状态与下一动作

```text
MODEL_A_FREEZE=COMPLETE
NF3_TON_ARTIFACT_RECONCILIATION=PASS
NF3_TON_FEASIBILITY=PASS_WITH_LIMITATIONS
PLAN_ARCHITECTURE_REVISION=COMPLETE
PHASE_B1=NOT_STARTED
PHASE_B2=NOT_STARTED
PHASE_B3=NOT_STARTED
PHASE_B4=NOT_STARTED
PHASE_B5=LITERATURE_SUPPORTED_IMPLEMENTATION_PENDING
PHASE_B6=OPTIONAL_NOT_AUTHORIZED
```

下一动作是`FORMALIZE_DATASET_V4_AND_START_MODEL_B_LOW_COST_DESIGN_GATES`。本次计划修订不自行启动该动作。
