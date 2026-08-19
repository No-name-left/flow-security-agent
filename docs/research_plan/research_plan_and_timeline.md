# Open-World Continually Evolving LLM Traffic Agent：执行计划与时间表

> 状态：DEC-0025/DEC-0026/DEC-0027 canonical execution order
>
> 日期：2026-08-16
>
> 本文件只定义阶段、依赖、Gate与停止点；研究语义以[research_plan_detailed.md](research_plan_detailed.md)为最高权威，五个主实验、两个辅助实验、派生视图与统计规则见[experiment_protocol_v1.md](experiment_protocol_v1.md)。

## 1. 当前路线与已完成基础

方法核心是：

```text
Evidence-Conditioned Open-World Traffic Recognition
+ Empirically Grounded Typed-Evidence Acquisition
+ Evidence-Gated Continual Evolution
```

长期框架保留“open-world continually learning / self-evolving malicious
traffic Agent”，并区分三种机制/时间尺度（2026-08-20 review 同步，详见
[open_world_continual_agent_design.md](open_world_continual_agent_design.md)
§1.1）：A. REPRESENTATION / OBSERVATION ADAPTATION（当前 Model B V1 领地，
runtime typed Evidence + target-specific recovery correspondence）；
B. POLICY EVOLUTION（未来 RL acquisition/stopping/novelty-admission policy，
决策组件而非通用替代）；C. KNOWLEDGE / CLASS EVOLUTION（Unknown buffer →
clustering → verified feedback → 新类注册 → supervised adaptation + replay）。
长期候选 self-evolution（pi_0 → pi_1 → pi_2 → ...，verified novel-class
outcome 提供 delayed feedback）保持 LONG-TERM / CANDIDATE，未证实，未授权。

Model A已经冻结为single-domain controlled baseline和optional replay source；其closed-set分类成功，但LM Evidence-State branch对目标用途失败。NF3-ToN官方final processed artifact已通过reconciliation/schema/label Gate，24,000条pilot确认存在recoverable Known、可预测的Evidence utility和aggregate Evidence-conditioned open-world收益。

Dataset-v4 B1 formalization和formal experiment design现已完成；没有启动Model B、DeepSeek、continual、RL、下载或raw reprocessing。

## 2. Phase B1 — Dataset-v4 / NF3-ToN formalization

状态：`COMPLETE / PASS`。已把验证过的NF3-ToN artifact冻结成可训练、可复现且无明显identity/group/future leakage的Dataset-v4 core。

必须完成：

- 验证固定CSV SHA256 `53ec8f468a43ede9b1536fabc0390af2fa33ab4312b23ce4d864f186a4651f78`；
- 冻结七类taxonomy、label map和per-class support；
- 设计deterministic grouped/temporal train/development/test split；
- 冻结`BASIC_SUFFICIENT_KNOWN / RECOVERABLE_KNOWN / TRUE_UNKNOWN`合同；
- 预注册whole-class held-out Unknown rotations，不让held-out class进入classifier training或final threshold tuning；
- 冻结Basic、Temporal和Relation的semantic admissibility、availability、cost与model-safe serialization；
- 通过identity、source、time、label、future-context和cross-split leakage Gate。

输出：七类`CANONICAL_TAXONOMY_V1`、`GROUPED_TEMPORAL_HASH_70_15_15_V1` split（19,858,267 / 3,809,983 / 3,842,026）、三套whole-class rotations、strict-past history scope、2,000-row Teacher sample manifest和63-row semantic request manifest。small manifest/report/config tracked；2.08GB row manifest和request/offline truth保持Git-external。详见[dataset_v4_split_protocol.md](dataset_v4_split_protocol.md)。

## 3. Phase B2 — Model B static foundation

目标：建立Known representation/classification与独立novelty interface，不进行Evidence acquisition策略或continual update。

先从immutable TRAIN派生并比较exact-group representative与duplicate-group weighting；master split不变。随后执行Experiment 1低成本Gate：

1. fresh initialization vs matched Model-A warm start；
2. Qwen vs smaller traffic encoder/strong structured baseline；
3. Frozen-Qwen linear heads vs Qwen adaptation；
4. MSP、margin、energy和prototype distance的development-only comparison。

只有matched evidence说明warm start或Qwen共享表示有额外价值时才保留相应复杂度。True Unknown不是Fine Head的`K+1`类。

## 4. Phase B3 — Formal typed-Evidence utility

目标：执行Experiment 2，把semantic admissibility与operational utility分离，并正式验证哪个Evidence family值得获取。

执行顺序：

```text
Basic
Basic + Temporal
Basic + Relation
Basic + Temporal + Relation
```

每个sample的utility outcome必须由OOF/cross-fitted预测产生，并分别materialize `U_T/U_R/U_TR`。比较Basic、Always Full、cost-matched random、confidence、supervised utility和analysis-only oracle；报告`ΔNLL`、correctness recovery、FURK变化和acquisition cost。必须执行second seed或bootstrap robustness，逐类披露Recon_Scanning、Web_Injection、Credential等相反收益。

Application、Payload、Knowledge只在数据可用、语义合法且utility Gate通过时追加；不是第一轮必需action。

## 5. Phase B4 — Evidence-conditioned open-world evaluation

Experiment 3正式比较至少：

1. `Basic → Direct Novelty`；
2. `Basic uncertainty → Always Acquire Full → Novelty`；
3. `Basic uncertainty → Utility-conditioned Evidence Acquisition → Novelty`。

并加入cost-matched random/confidence、可选Teacher和后续RL policy。三套whole-class rotation固定为Credential、Recon_Scanning与Web_Injection；novelty至少比较MSP、margin、energy和prototype/Mahalanobis。

这一区分“额外信息本身的收益”和“智能选择Evidence的收益”。报告Macro-F1、Unknown AUROC/AUPR、OSCR、FURK、Evidence Recovery Rate、Acquisition Rate、Average Acquisition Cost和Known accuracy after recovery，并提供overall/per-class/bootstrap结果。

进入Unknown的必要条件是Evidence recovery已完成、无可用family或预测收益不值得成本。observability-limited样本不得进入True Unknown主评测。

## 6. Phase B5 — Fast Agent-policy RL

Experiment 5使用Git-external offline Evidence episode cache，四动作固定为STOP、Temporal、Relation与进入novelty。比较confidence heuristic、supervised utility、可选Teacher、Double DQN和可选Teacher-BC→DQN。

```text
RL_STATUS=PLANNED_LOW_COST_AGENT_POLICY_COMPONENT_PENDING_FORMAL_GATE
LLM_LEVEL_RL=NOT_PLANNED_FOR_CORE
```

只有RL在多seed上改善performance-cost frontier时才作为突出组件；否则保留heuristic/supervised policy并报告negative result。PPO/GRPO/RLAIF/direct Qwen RL不进入core。

## 7. Phase B6/B7 — Continual evolution

Experiment 4只在B1–B4 static foundation稳定且fast policy接口已冻结后开始：

```text
Residual Unknown
→ Unknown Buffer
→ optional clustering
→ verified feedback
→ REGISTER_NEW_CLASS
→ supervised continual adaptation + old replay
→ regression/release gate or rollback
```

先执行no adaptation、new-only、replay、LwF等continual baselines；再以完全相同adaptation/replay比较direct novelty buffer与Evidence-gated buffer，并保留oracle-clean ceiling。至少运行Credential→Recon、Recon→Web、Web→Credential三种顺序。报告buffer purity、可选clustering ARI/NMI、新类学习、旧类遗忘、BWT、label-query count及release结果。self-label、confidence和cluster tightness不得作为GT。

当前状态：`LITERATURE_SUPPORTED_IMPLEMENTATION_PENDING`，不是B1–B4 blocker。

## 8. Conditional extensions与辅助实验

在core Gates之后才执行multi-Unknown grouping、slow evolution controller、missing-Evidence robustness和external-domain stress。slow controller不改变verified-label supervised adaptation或immutable release gate。

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
PHASE_B1=COMPLETE_PASS
TEACHER_CACHE_STATUS=FROZEN_COMPLETE_2000_VALID
SEMANTIC_REFERENCE_STATUS=FROZEN_COMPLETE_63_VALID
CORE_HIGH_TOKEN_DEEPSEEK_DEPENDENCY_COMPLETE=true
PHASE_B2=NOT_STARTED
PHASE_B3=NOT_STARTED
PHASE_B4=NOT_STARTED
PHASE_B5_FAST_RL=PLANNED_PENDING_FORMAL_GATE_NOT_STARTED
PHASE_B6_B7_CONTINUAL=LITERATURE_SUPPORTED_IMPLEMENTATION_PENDING
EXPERIMENT_PROTOCOL_V1=FROZEN_DESIGN_NOT_RUN
```

pre-price Teacher cache v1（2,000）与semantic reference v1（63）已于2026-08-17在researcher显式授权下生成完毕并冻结（`TEACHER_CACHE_STATUS=FROZEN_COMPLETE_2000_VALID`、`SEMANTIC_REFERENCE_STATUS=FROZEN_COMPLETE_63_VALID`，详见[teacher_cache_v1_generation_report.md](../../reports/research_audit/teacher_cache_v1_generation_report.md)）。下一动作（DEC-0028，2026-08-18）是起草/评审预注册的Strong Neural OSR Evidence Gate协议（pre-Model-B基线）；历史条目`PREPARE_DUPLICATE_AWARE_DATA_VIEWS_AND_START_MODEL_B_LOW_COST_GATES`已被取代、不得执行；Model-B low-cost design Gates尚未启动，正式Model-B训练、continual与RL仍未授权。
