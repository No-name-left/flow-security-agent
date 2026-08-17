# Flow Security Agent 项目交接指南

> 最近核验：2026-08-17。
>
> 当前长期主线：`main`；本次文档冻结基于`a3379b290df99fd717248a7c86b9ecce2a047b11`，DEC-0025/0026/0027已接受。
>
> 当前状态：Model A训练/评估完成；NF3-ToN Dataset-v4 B1 formalization与Experiment Protocol v1已冻结；bounded Evidence/open-world feasibility通过但有class-conditional limitations；pre-price Teacher cache v1（2,000/2,000 valid）与semantic reference v1（63/63 valid）已生成并冻结；Core Hypothesis Gate 1已完成，**状态YELLOW**（Temporal modest consistent positive；Relation always-on negative且conditional value unresolved；Full在frozen RF probe为negative）；Model B、continual与fast RL均未启动。

## 1. 权威链

研究语义冲突时依次服从：

1. [research_plan_detailed.md](research_plan/research_plan_detailed.md)及DEC-0025/0026/0027；
2. [experiment_protocol_v1.md](research_plan/experiment_protocol_v1.md)：formal experiments、derived-view isolation、baselines、metrics与统计；
3. [model_b_evidence_openworld_design.md](research_plan/model_b_evidence_openworld_design.md)：Model B representation、utility、novelty与Gate；
4. [open_world_continual_agent_design.md](research_plan/open_world_continual_agent_design.md)：Controller、Runtime与continual边界；
5. [multi_dataset_v4_design.md](research_plan/multi_dataset_v4_design.md)：NF3-ToN Dataset-v4 data contract；
6. [dataset_v4_b1_runtime_contract.md](research_plan/dataset_v4_b1_runtime_contract.md)：B1 observation/Evidence/runtime/action/Teacher-cache工程合同；
7. [dataset_v4_split_protocol.md](research_plan/dataset_v4_split_protocol.md)：冻结taxonomy/identity/split/rotation/history/sample population；
8. [near_mainline_training_protocol_v1.md](training/near_mainline_training_protocol_v1.md)：Model A历史执行/lineage合同；
9. [agent_architecture_provisional.md](design/agent_architecture_provisional.md)：Runtime implementation boundary；
10. 本文件：当前事实与下一动作。

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

online fast policy的冻结四动作是`STOP_AND_CLASSIFY`、`ACQUIRE_TEMPORAL`、`ACQUIRE_RELATION`和`ENTER_NOVELTY_DETECTION`；后者只是进入独立novelty detector。buffer/query/register/adapt属于slow continual control。heuristic/supervised utility是强基线，Double DQN是planned low-cost Gate；LLM-level RL不进入core。

## 4. NF3-ToN权威artifact与可行性

```text
NF3_TON_ARTIFACT_RECONCILIATION=PASS
NF3_TON_OFFICIAL_FINAL_ARTIFACT=true
NF3_TON_RAW_REPROCESSING_REQUIRED=false
NF3_TON_CSV_SHA256=53ec8f468a43ede9b1536fabc0390af2fa33ab4312b23ce4d864f186a4651f78
DATASET_V4_ROW_MANIFEST_SHA256=faa5220beae65f06591e7ea399c59092985135b81860fcd2388f20cadaa7c095
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

master split不可改写。数据中有`1,816,137`个duplicate copies（480,040 groups）；它们不是cross-split leakage，但B2前必须派生exact-group representative与duplicate-group-weighted训练视图，primary evaluation同时给duplicate-balanced/deduplicated与raw-prevalence sensitivity。历史`UNKNOWN_CANONICAL_LABEL_N=9984`现只称`OUT_OF_CORE_FINE_LABEL_POOL_N=9984`，绝非True Unknown。

现有Model A Teacher V3/v2与blind-calibration外部缓存已经核验，但schema/population/action vocabulary均不匹配Model B，仅为`LEGACY_REFERENCE`。`teacher_cache_v1`的2,000条sample list与63条semantic request list已按冻结design materialize并通过FINAL_TEST、source/group-role和payload leakage Gate；2026-08-17已按冻结prompt完成DeepSeek response生成。详见[teacher_cache_v1_generation_report.md](../reports/research_audit/teacher_cache_v1_generation_report.md)与[dataset_v4_final_split_report.md](../reports/dataset_v4/dataset_v4_final_split_report.md)。

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

## 8. Formal Experiment Protocol v1

五个主实验固定为：

1. Model B closed-set/representation：LightGBM、小神经编码器、Frozen-Qwen linear、fresh LoRA、可选Model-A warm start；
2. Typed Evidence utility：Basic/Temporal/Relation/Full，比较always/random/confidence/supervised/oracle；
3. Evidence-conditioned open world：三套whole-class rotations、simple novelty、FURK/Unknown matched比较；
4. Evidence-gated continual：至少三种两类顺序，direct与gated buffer使用相同adaptation/replay；
5. Fast Agent-policy RL：confidence、supervised utility、Teacher（如有）、Double DQN、可选BC→DQN。

辅助实验是family-level missing-Evidence robustness与secondary external-domain stress。正式模型至少3 seeds；RL/continual至少3 stream/order seeds，资源允许用5；bootstrap单位是private group/temporal block，禁止naive row bootstrap。FINAL_TEST只作sealed static/continual final；如需拆分，必须在开封前freeze互斥group-aware subviews。

```text
EXPERIMENT_PROTOCOL_STATUS=FROZEN_DESIGN_NOT_RUN
RL_STATUS=PLANNED_LOW_COST_AGENT_POLICY_COMPONENT_PENDING_FORMAL_GATE
LLM_LEVEL_RL=NOT_PLANNED_FOR_CORE
```

## 9. 执行阶段与当前停点

```text
B0_MODEL_A_AND_FEASIBILITY=COMPLETE_PASS_WITH_LIMITATIONS
B1_DATASET_V4_CONTRACT=FROZEN_PASS_SAMPLE_MANIFEST_READY
CORE_HYPOTHESIS_GATE_1=YELLOW   (kill gate complete 2026-08-17, 3 seeds;
  see reports/research_audit/core_hypothesis_gate_v1.md — not PASS, not FAIL)
B2_MODEL_B_STATIC_FOUNDATION=NOT_STARTED
B3_TYPED_EVIDENCE_UTILITY=NOT_STARTED
B4_EVIDENCE_CONDITIONED_OPEN_WORLD=NOT_STARTED
B5_FAST_AGENT_POLICY_RL=PLANNED_PENDING_FORMAL_GATE_NOT_STARTED
B6_CONTINUAL_BASELINES=LITERATURE_SUPPORTED_IMPLEMENTATION_PENDING
B7_EVIDENCE_GATED_CONTINUAL=NOT_STARTED
B8_PLUS_CONDITIONAL_EXTENSIONS=NOT_STARTED
```

B2前必须保留fresh-vs-Model-A warm-start、Qwen-vs-small；B3必须保留Basic/Temporal/Relation/combined与second-seed/bootstrap；B4必须比较Direct novelty、Always acquire Full和Utility-conditioned。

## 10. Teacher状态、下一动作与禁止项

```text
TEACHER_CACHE_STATUS=FROZEN_COMPLETE_2000_VALID
SEMANTIC_REFERENCE_STATUS=FROZEN_COMPLETE_63_VALID
CORE_HIGH_TOKEN_DEEPSEEK_DEPENDENCY_COMPLETE=true
TEACHER_CACHE_MODEL=deepseek-v4-flash
TEACHER_CACHE_PROMPT_SHA256=dd86d4acac26c6ae7f89806c9511752f62a3c5ad1365498dc9bba8163cf87096
TEACHER_CACHE_ARTIFACT_SHA256=e2bc5599a98419cca723cf9b8a3f542e17a2afdfd720256e759931ab2b64a964
SEMANTIC_REFERENCE_ARTIFACT_SHA256=9830704256bcfd05c6c3fae40ea8b055a2dbef63565a5f03c9894ce71009ad74
NEXT_ACTION=PREPARE_DUPLICATE_AWARE_DATA_VIEWS_AND_START_MODEL_B_LOW_COST_GATES
```

**Core Hypothesis Gate 1（2026-08-17，kill gate）**：`CORE_HYPOTHESIS_GATE_1=YELLOW`，不relabel为PASS。Temporal为modest consistent positive（3/3 seeds ΔMacro-F1 > 0，mean Δ≈+0.0065，net recovery≈+0.0066；意义明确的attack-class recovery：DoS、Web_Injection）；Relation在frozen RF probe下always-on为negative（mean recoverable≈0.0455但harm>recovery），存在非零recovery故conditional value unresolved；Temporal+Relation整体negative。先前24k pilot的强recoverability（~0.12）未以同等强度复现。全部数字见[core_hypothesis_gate_v1.md](../reports/research_audit/core_hypothesis_gate_v1.md)（JSON：[core_hypothesis_gate_v1.json](../reports/research_audit/core_hypothesis_gate_v1.json)）。

Gate 1后下一proposed gate为**Conditional Evidence Utility Separability（CORE_HYPOTHESIS_GATE_1B）**：在获取Evidence前，仅凭runtime-visible Basic state预测HELP vs HARM，尤其Temporal conditional utility与Relation unique/conditional utility。该提议**尚未授权**（`NEXT_ACTION_AUTHORIZED=false`），Gate 1B、Model B、RL、open-world、continual均不得在未授权下启动。

`teacher_cache_v1`的2,000条与semantic reference的63条response已于2026-08-17按冻结prompt生成完毕（2,000/2,000与63/63 schema-valid，0失败、0重试；token：input 4,528,644 / output 156,469）。生成工具与15个targeted tests已进入仓库；raw/normalized response与manifest保持Git-external。详见[teacher_cache_v1_generation_report.md](../reports/research_audit/teacher_cache_v1_generation_report.md)。旧Model A Teacher caches仍为`LEGACY_REFERENCE`，不能作为Model B GT或直接复用。

Teacher v1经验限制（真实baseline行为，不是generation failure）：冻结prompt下`ACQUIRE_RELATION=0`、`ENTER_NOVELTY_DETECTION=0`（action分布`STOP_AND_CLASSIFY=741`、`ACQUIRE_TEMPORAL=1259`）。不得改prompt、重跑、删除结果或人为补action。角色边界因此为：

```text
TEACHER_SUPERVISOR_BASELINE=VALID
POLICY_DEMONSTRATION=VALID_WITH_ACTION_SUPPORT_LIMITATION
OPTIONAL_IMITATION_INITIALIZATION=LIMITED_NOT_DEFAULT
```

这2,000条不是“完整四动作imitation dataset”；Teacher仍不是classification/utility/Unknown/continual GT或RL reward GT。

继续禁止：未经授权的Model B/Qwen运行、正式训练、continual实现、RL、数据下载、raw PCAP处理、修改Model A checkpoint、self-training、打开sealed FINAL_TEST；未经明确授权的push。

### DO NOT REOPEN

- NF3-ToN core source、artifact identity、七类taxonomy、source mapping；
- master split、source-row identity、10/60/300 strict-past history、三套Unknown rotations；
- “Known / recoverable Known / True Unknown”及Unknown-after-Evidence顺序；
- Model A checkpoint与其Evidence-State失败结论；
- Teacher不提供classification/utility/Unknown/continual GT；
- no self-label、verified feedback before registration、supervised adaptation+replay、release/rollback；
- CICIoT/raw CIC/raw ToN不是core依赖，不因类别数量重启dataset search；
- LLM-level PPO/GRPO/RLAIF不进入core。

## 11. Git、环境与入口

Long-term branch是`main`；本次冻结从`a3379b290df99fd717248a7c86b9ecce2a047b11`出发，landing policy是local ff-only、clean、no push。未来Agent先运行`git branch --show-current && git rev-parse HEAD && git status --short`，不要凭本文猜最终commit hash。

Large data、PCAP、Parquet、Teacher response cache、features、RL episodes、continual streams、checkpoints、model weights和logs保持Git-external；Git只保存小manifest、hash、protocol和report。Qwen环境为`/root/autodl-tmp/conda/qwen35-runtime`；Production/data环境为`/root/autodl-tmp/conda/flow-data`。任何secret不得进入repo、manifest或日志。
