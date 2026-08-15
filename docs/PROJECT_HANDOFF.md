# Flow Security Agent 项目交接指南

> 最近核验：2026-08-15。
>
> 当前长期主线：`main`；本轮DEC-0024只修改研究/架构文档，不push。
>
> 当前状态：Model A Formal SFT与正式validation已完成；Known classification `PASS`，generative Evidence State `FAIL`。研究主线已调整为`Open-World Continually Evolving LLM Traffic Agent`。Dataset-v4 source preflight、Evidence Utility Gate、Model B0、Unknown continual stream和RL均未开始。

## 1. 权威链

研究语义冲突时依次服从：

1. `docs/research_plan/research_plan_detailed.md`及DEC-0024；
2. `docs/research_plan/open_world_continual_agent_design.md`：当前三Plane、Dataset-v4、continual与RL详细架构；
3. `docs/research_plan/multi_dataset_v4_design.md`：source/session/taxonomy/static+stream合同；
4. `docs/training/near_mainline_training_protocol_v1.md`：Model A历史执行/lineage合同，Model B顺序受DEC-0024 override；
5. `docs/design/agent_architecture_provisional.md`：Runtime实现边界；
6. 本文件：当前实现事实与下一动作。

`task_definition_v2.md`继续是Model A Dataset-v3/Evidence-v2/Teacher-v2数据合同。历史DEC、报告和旧协议不得覆盖DEC-0024。

## 2. Model A冻结结果

| Item | Result |
| --- | --- |
| Run | `near-sft-v3-20260812T230311Z-d93789de` |
| Final checkpoint | `checkpoint-step-00001794`，immutable/Git-external |
| Formal Macro-F1 | `0.9984831207613943` |
| Accuracy / micro-F1 | `0.9984524914887032` |
| Raw Qwen zero-shot Macro-F1 | `0.5617499100465918` |
| Frozen-Qwen linear probe | 3,600 balanced TRAIN records；Macro-F1 `0.9815630112607532` |
| Basic-sufficient classification | 2,694；Macro-F1 `0.9988867951762442` |
| Basic-insufficient classification | 537；Macro-F1 `0.9973544973544973` |
| Evidence-State schema | valid rate `1.0`；severe hallucination 0 |
| Evidence sufficiency | overall F1 `0.9101351351`；Basic-insufficient F1 `0` |
| Gap prediction | micro-F1 `0`；532/537 insufficient误判sufficient |

Interpretation:

```text
MODEL_A_ROLE=LEGACY_CONTROLLED_DOMAIN_AND_BASELINE
MODEL_A_KNOWN_CLASSIFICATION=PASS
MODEL_A_EVIDENCE_STATE=FAIL
MODEL_A_WARM_START=PROVISIONAL_PENDING_ABLATION
```

Closed-set classification不再是主要创新。Frozen representation已高度有用；linear probe和Formal SFT训练量不同，性能差不能当作精确LoRA uplift。Teacher semantic sufficiency不等于operational utility，Model A LM Evidence State不能直接控制runtime acquisition。

权威报告：`reports/training_readiness/model_a_formal_evaluation_v1.md`。

## 3. 新主线与三Plane

```text
Plane A — Perception
Qwen3.5-9B frozen base + LoRA → shared h
→ Family Head + Fine Head + MSP/Energy/Prototype Unknown
→ optional Evidence Decision Head [Utility Gate后]
→ LM Head仅解释/描述

Plane B — Control
Known classify / Unknown reject / defer buffer
+ Knowledge / verified feedback
+ optional Evidence actions [Gate后]
→ deterministic Runtime authority

Plane C — Evolution
Unknown Buffer → verified feedback → class confirmation
→ verified new samples + old replay
→ head/LoRA adaptation → Release Gate
→ Model B_t → Model B_{t+1} or rollback
```

Runtime拥有capability、strict-past、future leakage、budget、hidden oracle、class registration、model release/rollback和trace authority。模型预测/置信度不是GT；Memory增长本身不等于模型进化。

## 4. 可复用数据与工程资产

- Edge Production Data Freeze、7,619,032 stable identities、label-provenance与`CONSTRAINED_CHRONOLOGICAL_BOUNDARY_V2`；
- Dataset-v3六类eligible train/validation/test `1,318,688 / 270,851 / 279,057`；
- Model A corpus v3 `14,350 records / 11,958 sessions`，SHA256 `d93789de29b746d923660bb2e4ccad501412e75303ddf95f7087c85f6c67d6ca`；
- 3,231条`EXACT_EVAL_CLEAN` validation；
- Basic-v2、packet-index-aligned Payload、Application-v2、10/60/180/300s strict-past Temporal-v2与scoped Relation-v2；
- deterministic Runtime、Production Safe Adapter、provider-neutral boundary、local Qwen、training harness与checkpoint/evaluation tooling；
- Observation/Knowledge与private/model-visible分离、session-weight、U_final隔离等安全合同。

这些资产支持Model A复现和Dataset-v4 adapter设计，但不能证明新的source GT、cross-domain、Unknown、continual或Evidence utility。

## 5. Dataset-v4当前设计

| Role | Sources |
| --- | --- |
| Primary source preflight | CICIDS2017, CSE-CIC-IDS2018, ToN-IoT |
| Legacy controlled | Edge-IIoTset-clean |
| Fallback/gap filling | Bot-IoT, UNSW-NB15, DoHBrw, USTC-TFC2016 |

最终组成和taxonomy均为`PROVISIONAL`。每个source先以少量capture/run和几百sessions检查raw/GT、GT unit、session join、granularity、observability、leakage、group split、taxonomy mapping与Evidence capability。通过前禁止全量下载/scan/build。

统一链路：dataset-specific GT Adapter → private SourceAttackEvent → Common Sessionizer → CanonicalSession/Label/Evidence → static split + continual stream。Fine loss仅`EXACT`；`FAMILY_ONLY`只训练Family Head；`AMBIGUOUS/UNSUPPORTED`默认监督OFF。

在training前按canonical semantic class冻结`K0/U_dev/U_final/U_inc`。同义类不得经另一dataset泄漏。Future GT保持hidden，只有`REQUEST_ANALYST_FEEDBACK`后可返回。

## 6. Cheap Gates

### Source Compatibility Gate

每个candidate输出`PASS | PASS_WITH_LIMITATIONS | FAIL`。capture/file label propagation + unsupported session evidence、GT unit不明、无法解决的identity leakage均hard fail。

### Evidence Utility Gate

使用Frozen-Qwen representation和stratified OOF/cross-fitting比较Basic与Basic+单一Evidence。Teacher只可提供semantic relevance，不能产生operational utility GT。只有困难subset上稳定可重复、bootstrap与第二seed/reference model支持的增益才允许Evidence Decision Head/Active Evidence/RL。

### Warm-start Gate

同data/steps/LR/heads比较fresh LoRA与Model A warm start；只有更好且无Evidence/Unknown偏置并通过Edge regression才选Model A。

### RL Gate

先证明非RL continual loop，再比较RL-0 Heuristic与RL-1 small policy。只有RL-1长期收益稳定才考虑RL-2 Qwen policy LoRA；还需导师、reward、trajectory和GPU确认。

## 7. DeepSeek、RAG与verified feedback

DeepSeek现在是offline Teacher、policy demonstration source、semantic reviewer和optional Supervisor baseline；不是永久online control core，不替代classifier、verified label、Class Registry或Release Gate。

RAG继续与Observation分开，并使用`RAG_VERSION_t`或future-knowledge exclusion，防止未revealed Unknown label/signature泄漏。

只有analyst/sandbox/threat-intelligence/delayed-GT模拟产生verified feedback。Unknown cluster compactness、LLM confidence或self-prediction都不能注册新类。

## 8. 阶段与当前停点

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
```

下一动作必须是单独授权的Source Compatibility Preflight和bounded Evidence Utility Pilot设计。当前禁止：大型数据下载、全量PCAP、Model B0 SFT、bulk Teacher、RLAIF/PPO/GRPO、U_final、修改Model A checkpoint或self-training。

## 9. Advisor boundary

`ADVISOR_CONFIRMATION_REQUIRED=true`：确认“RL让模型持续进化”是A）RL学控制策略、verified-label supervised continual learning学新类（当前默认），还是B）RL必须直接更新Qwen traffic representation/classifier（高成本RL-2）。确认前不得投入LLM RL。

## 10. Git与环境

Large data、PCAP、Parquet、Teacher cache、features、checkpoint、model weights和logs保持Git-external。当前任务只允许docs/必要small research report，不push。

Qwen环境：`/root/autodl-tmp/conda/qwen35-runtime`。Production/data环境：`/root/autodl-tmp/conda/flow-data`。任何secret不得进入repo、manifest或日志。
