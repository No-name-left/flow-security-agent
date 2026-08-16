# Flow Security Agent 项目交接指南

> 最近核验：2026-08-16。
>
> 当前长期主线：`main`；DEC-0025已接受，计划修订任务不push。
>
> 当前状态：Model A训练/评估完成；NF3-ToN Dataset-v4 B1 formalization、bounded Evidence/open-world feasibility均通过但后者有class-conditional limitations；Model B、continual与RL均未启动。

## 1. 权威链

研究语义冲突时依次服从：

1. [research_plan_detailed.md](research_plan/research_plan_detailed.md)及DEC-0025/0026；
2. [model_b_evidence_openworld_design.md](research_plan/model_b_evidence_openworld_design.md)：Model B representation、utility、novelty与Gate；
3. [open_world_continual_agent_design.md](research_plan/open_world_continual_agent_design.md)：Controller、Runtime与continual边界；
4. [multi_dataset_v4_design.md](research_plan/multi_dataset_v4_design.md)：NF3-ToN Dataset-v4 data contract；
5. [dataset_v4_b1_runtime_contract.md](research_plan/dataset_v4_b1_runtime_contract.md)：B1 observation/Evidence/runtime/action/Teacher-cache工程合同；
6. [dataset_v4_split_protocol.md](research_plan/dataset_v4_split_protocol.md)：冻结taxonomy/identity/split/rotation/history/sample population；
7. [near_mainline_training_protocol_v1.md](training/near_mainline_training_protocol_v1.md)：Model A历史执行/lineage合同；
8. [agent_architecture_provisional.md](design/agent_architecture_provisional.md)：Runtime implementation boundary；
9. 本文件：当前事实与下一动作。

[task_definition_v2.md](research_plan/task_definition_v2.md)只定义Model A Dataset-v3/Evidence-v2/Teacher-v2 provenance，不定义Model B operational utility。

## 2. Model A冻结结果

| Item | Result |
| --- | --- |
| Run | `near-sft-v3-20260812T230311Z-d93789de` |
| Final checkpoint | `checkpoint-step-00001794`，immutable/Git-external |
| Formal Macro-F1 | `0.9984831207613943` |
| Accuracy / micro-F1 | `0.9984524914887032` |
| Raw Qwen zero-shot Macro-F1 | `0.5617499100465918` |
| Frozen-Qwen linear probe | 3,600 balanced TRAIN；Macro-F1 `0.9815630112607532` |
| Basic-sufficient classification | Macro-F1 `0.9988867951762442` |
| Basic-insufficient classification | Macro-F1 `0.9973544973544973` |
| Evidence sufficiency | overall F1 `0.9101351351`；Basic-insufficient F1 `0` |
| Gap prediction | micro-F1 `0`；532/537 insufficient误判sufficient |

```text
MODEL_A_ROLE=LEGACY_CONTROLLED_DOMAIN_BASELINE_AND_OPTIONAL_REPLAY
MODEL_A_KNOWN_CLASSIFICATION=PASS
MODEL_A_EVIDENCE_STATE=FAILED_FOR_TARGET_PURPOSE
MODEL_A_WARM_START=PROVISIONAL_PENDING_MATCHED_ABLATION
```

Closed-set分类不再是主要创新。Model A LM Evidence State和Teacher semantic sufficiency不得控制Model B runtime或充当utility GT。权威评估为[model_a_formal_evaluation_v1.md](../reports/training_readiness/model_a_formal_evaluation_v1.md)。

## 3. DEC-0025方法主线

```text
Evidence-Conditioned Open-World Traffic Recognition
+ Empirically Grounded Typed-Evidence Acquisition
+ Evidence-Gated Continual Evolution
```

正式状态是`BASIC_SUFFICIENT_KNOWN`、`RECOVERABLE_KNOWN`和`TRUE_UNKNOWN`。系统先预测是否值得获取Temporal/Relation Evidence，重新评价Known；只有recovery exhausted、不可用或不值得成本后，才进入独立novelty detector。observability-limited样本不能冒充True Unknown。

Model B候选使用Qwen shared representation + Fine Head，并允许small Utility Head或external small selector。Unknown不是K+1类，第一轮比较MSP、margin、energy和prototype distance。Qwen价值必须用small/structured/Frozen-Qwen baselines检验。

Controller动作是`STOP_AND_CLASSIFY`、`ACQUIRE_EVIDENCE(E_j)`、`ENTER_NOVELTY_DETECTION`、`BUFFER_UNKNOWN`、`REQUEST_LABEL`和`TRIGGER_CONTINUAL_ADAPTATION`。首版为deterministic/supervised utility policy；RL只是optional extension，LLM RL未授权。

## 4. NF3-ToN权威artifact与可行性

```text
NF3_TON_ARTIFACT_RECONCILIATION=PASS
NF3_TON_OFFICIAL_FINAL_ARTIFACT=true
NF3_TON_RAW_REPROCESSING_REQUIRED=false
NF3_TON_CSV_SHA256=53ec8f468a43ede9b1536fabc0390af2fa33ab4312b23ce4d864f186a4651f78
CORE_RESEARCH_FEASIBILITY=PASS_WITH_LIMITATIONS
```

`CANONICAL_TAXONOMY_V1`已冻结为Benign、Backdoor、Credential、DDoS、DoS、Recon_Scanning和Web_Injection。

24,000条pilot结果：

| Metric | Result |
| --- | ---: |
| OOF Basic / Full Macro-F1 | `0.9241027728324086 / 0.9542507313534688` |
| Recoverable Known | `2,879 / 24,000` (`0.11995833333333333`) |
| Utility AUROC / AUPR | `0.9559201214445113 / 0.6823986368255095` |
| Direct / Evidence-conditioned Unknown AUROC | `0.7583657442883499 / 0.7683698955976005` |
| FURK | `0.3062080536912752 → 0.24161073825503357` |
| Acquisition rate | `0.1459902525476296` |

限制：Recon_Scanning Unknown separation弱；Web_Injection Unknown改善但FURK变差；Credential FURK改善但fixed-FPR recall下降；当前Full仅bounded sample-local Temporal+Relation；single-family、second-seed/bootstrap仍待formal Gate。

权威报告：

- [nf3_core_feasibility_gate.md](../reports/dataset_v4_preflight/nf3_core_feasibility_gate.md)；
- [nf3_ton_evidence_openworld_feasibility.md](../reports/dataset_v4_preflight/nf3_ton_evidence_openworld_feasibility.md)。

## 5. Dataset-v4与source角色

`NF3-ToN-IoT`是core。artifact identity、B1 observation、Basic/Temporal/Relation、runtime state、四动作、novelty-entry、Teacher-cache I/O、七类taxonomy、grouped split、whole-class Unknown rotations、strict-past history与actual cache sample list均已冻结。七类TRAIN/VALIDATION/FINAL_TEST为`19,858,267/3,809,983/3,842,026`；source/exact-duplicate/activity-group cross-split均为0。final Evidence cost仍由后续Gate冻结。

现有Model A Teacher V3/v2与blind-calibration外部缓存已经核验，但schema/population/action vocabulary均不匹配Model B，仅为`LEGACY_REFERENCE`。`teacher_cache_v1`的2,000条sample list与63条semantic request list已按冻结design materialize并通过FINAL_TEST、source/group-role和payload leakage Gate；仍未调用DeepSeek、未生成response。详见[dataset_v4_final_split_report.md](../reports/dataset_v4/dataset_v4_final_split_report.md)。

`NF3-UNSW-NB15`、`NF3-BoT-IoT`、`NF3-CSE-CIC-IDS2018`是secondary external-domain stress/replication candidates。已有cross-source generalization弱且domain-dependent，不阻塞core，也不得写成已解决。

CICIoT2023、raw CIC和raw ToN为`NOT_REQUIRED_FOR_CORE`；不下载、不重处理。Edge assets、Runtime、Dataset-v3、Evidence-v2与Model A checkpoint继续保留作baseline/provenance/replay候选。

## 6. Evidence、DeepSeek与Unknown边界

Evidence分为：

- Semantic Admissibility：label-free、test-time available、causal/past-only、网络语义合法；
- Operational Utility：由OOF/cross-fitted Basic与Basic+family的决策改善产生。

核心family是Basic、Temporal和Relation；Application/Payload/Knowledge是optional。DeepSeek只作offline semantic reviewer、optional demonstrations/explanations和optional Supervisor baseline，不产生utility GT。

True Unknown必须whole-class held out，不得参加classifier training或final threshold tuning，并且Full合法Evidence下可观测。冻结rotations为Credential、Recon_Scanning和Web_Injection。

## 7. Continual boundary

```text
Residual Unknown → Unknown Buffer → optional clustering
→ verified feedback → REGISTER_NEW_CLASS
→ supervised adaptation + old replay
→ old/new/Unknown/domain-stress release gate
→ release or rollback
```

self-prediction、confidence、cluster tightness和Memory写入不是GT或模型进化。当前`CONTINUAL_FEASIBILITY_STATUS=LITERATURE_SUPPORTED_IMPLEMENTATION_PENDING`。

## 8. 执行阶段与当前停点

```text
B0_MODEL_A_AND_FEASIBILITY=COMPLETE_PASS_WITH_LIMITATIONS
B1_DATASET_V4_CONTRACT=FROZEN_PASS_SAMPLE_MANIFEST_READY
B2_MODEL_B_STATIC_FOUNDATION=NOT_STARTED
B3_TYPED_EVIDENCE_UTILITY=NOT_STARTED
B4_EVIDENCE_CONDITIONED_OPEN_WORLD=NOT_STARTED
B5_CONTINUAL_EVOLUTION=LITERATURE_SUPPORTED_IMPLEMENTATION_PENDING
B6_RL=OPTIONAL_NOT_AUTHORIZED
```

B2前必须保留fresh-vs-Model-A warm-start、Qwen-vs-small；B3必须保留Basic/Temporal/Relation/combined与second-seed/bootstrap；B4必须比较Direct novelty、Always acquire Full和Utility-conditioned。

## 9. 下一动作与禁止项

```text
NEXT_ACTION=GENERATE_PREPRICE_DEEPSEEK_CACHE_AND_SEMANTIC_REFERENCE
```

该API动作尚未启动，必须由researcher另行显式授权。Model-B低成本design Gates已解除B1前置阻塞但本轮没有启动。继续禁止：未经授权的Model B/Qwen/DeepSeek运行、正式训练、continual实现、RL、数据下载、raw PCAP处理、修改Model A checkpoint、self-training、打开sealed final Unknown或push。

## 10. Git与环境

Large data、PCAP、Parquet、Teacher cache、features、checkpoints、model weights和logs保持Git-external。Qwen环境为`/root/autodl-tmp/conda/qwen35-runtime`；Production/data环境为`/root/autodl-tmp/conda/flow-data`。任何secret不得进入repo、manifest或日志。
