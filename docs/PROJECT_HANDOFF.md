# Flow Security Agent 项目交接指南

> 最近核验：2026-08-18（instruction hygiene与DEC-0028定点更新）。
>
> **阅读方式：本文档是按需历史/上下文阅读（on-demand），不是Agent默认bootstrap。** 默认入口是[AGENT_CONTEXT.md](AGENT_CONTEXT.md)；当前授权、禁止项与git checkpoint以AGENT_CONTEXT为准。本文不复制Gate的详细指标（见`reports/research_audit/` formal JSON/MD）。
>
> 当前长期主线：`main`；本次文档冻结基于`a3379b290df99fd717248a7c86b9ecce2a047b11`，DEC-0025/0026/0027已接受；2026-08-18新增DEC-0028。
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
STRONG_NEURAL_OSR_EVIDENCE_GATE=DEC_0028_AUTHORIZED_PROTOCOL_DRAFTING_ONLY
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
NEXT_ACTION=SEPARATE_FORMAL_MODEL_B_LAUNCH_TASK
  (2026-08-20: Model B V1协议已FROZEN并preregistered——
   protocol sha256 3479f1a5eb…、serializer sha256 95d159fab5…、
   preregistration reports/research_audit/model_b_recovery_aware_representation_v1_preregistration.json、
   formal runner tools/run_model_b_recovery_aware_representation_v1.py
   （仅通过允许的检查：syntax/import/static/dry-run/synthetic smoke，无任何formal fit）。
   MODEL_B_V1_READY_TO_LAUNCH=true；MODEL_B_FORMAL_TRAINING_STARTED=false。
   Formal训练/launch命令必须由新的独立研究任务显式授权——
   NEXT_ACTION_AUTHORIZED=false，本pre-launch任务禁止执行launch命令、
   禁止任何formal Qwen fit、probe、bootstrap、FINAL_TEST。
   历史条目 `STRONG_NEURAL_OSR_PROTOCOL_DRAFT_AND_REVIEW`（DEC-0028,
   2026-08-18）仍为pending pre-Model-B baseline前提，由未来任务处理)
```

**Core Hypothesis Gate 1（2026-08-17，kill gate）**：`CORE_HYPOTHESIS_GATE_1=YELLOW`，不relabel为PASS。Temporal为modest consistent positive（3/3 seeds ΔMacro-F1 > 0，mean Δ≈+0.0065，net recovery≈+0.0066；意义明确的attack-class recovery：DoS、Web_Injection）；Relation在frozen RF probe下always-on为negative（mean recoverable≈0.0455但harm>recovery），存在非零recovery故conditional value unresolved；Temporal+Relation整体negative。先前24k pilot的强recoverability（~0.12）未以同等强度复现。全部数字见[core_hypothesis_gate_v1.md](../reports/research_audit/core_hypothesis_gate_v1.md)（JSON：[core_hypothesis_gate_v1.json](../reports/research_audit/core_hypothesis_gate_v1.json)）。

**Core Hypothesis Gate 1B（2026-08-17，kill gate）**：`CORE_HYPOTHESIS_GATE_1B=PASS`（Temporal primary gate 7/7：mean HELP AUROC 0.92、top15 capture 0.90、selector15 net +0.021 vs random +0.001、T7 aggregate CI lower>0；Relation conditional value SUPPORTED，UNIQUE_R rate≈0.019，random acquisition对Relation为harmful而selector为正）。即conditional Evidence utility可仅凭pre-acquisition Basic state分离。Gate 1保持YELLOW不变（`GATE_1_STATUS_CHANGED=false`，非rescue、未改阈值）。Gate 1B结果**未提交**（report/tool为untracked；artifacts在Git-external `core_gate_v1b/`）。下一proposed gate为**Open-World causal gate（before any Model B work）**，**尚未授权**（`NEXT_ACTION_AUTHORIZED=false`）；Model B、RL、open-world、continual均不得在未授权下启动。详见[core_hypothesis_gate_v1b.md](../reports/research_audit/core_hypothesis_gate_v1b.md)（JSON：[core_hypothesis_gate_v1b.json](../reports/research_audit/core_hypothesis_gate_v1b.json)）。

`teacher_cache_v1`的2,000条与semantic reference的63条response已于2026-08-17按冻结prompt生成完毕（2,000/2,000与63/63 schema-valid，0失败、0重试；token：input 4,528,644 / output 156,469）。生成工具与15个targeted tests已进入仓库；raw/normalized response与manifest保持Git-external。详见[teacher_cache_v1_generation_report.md](../reports/research_audit/teacher_cache_v1_generation_report.md)。旧Model A Teacher caches仍为`LEGACY_REFERENCE`，不能作为Model B GT或直接复用。

**Related Work / Novelty Reassessment（2026-08-17，文献审计，无实验；revision 1）**：已按公开prior art重定位claim安全。generic AFA（Li & Oliva ICML 2021）、cost-aware two-stage routing（Regol et al. NeurIPS 2025）、instance-specific acquisition（Guney/Norcliffe ICML 2025）、typed/temporal acquisition（arXiv:2508.18380/2507.12412/2603.11370/2211.05039）、acquire-before-abstain（arXiv:2606.16667）、open-world traffic classification、open-world continual traffic（OWETC 2023、SOUL、MI^2DAS）、buffer purification（Self-Purified Replay）均为`PRIOR_ART_EXISTS`。**Full-text sync（外部researcher workflow完成，本地Agent未访问PDF，provenance=`FULL_TEXT_REVIEW_COMPLETED_EXTERNALLY_BY_RESEARCHER_WORKFLOW`）**：RoNeTC（TIFS 2025）=多视图动态融合与uncertainty-based Known/Unknown均prior art；RoeCi（TMC 2026，DOI 10.1109/TMC.2026.3715471）="do more processing before rejecting Unknown" prior art，但对同一observation加MODEL CAPACITY/COMPUTE，不获取此前未观测的observation evidence；GCLC（TIFS 2026）=new-class discovery/clustering/human-confirmation/incremental-update prior art，不建模Evidence-recoverable Known污染。**C1 scope精确为`RUNTIME_OBSERVATION_ACQUISITION_BEFORE_NOVELTY`**（`INSUFFICIENT_OBSERVATION_OF_KNOWN != TRUE_NOVELTY`；partial observation→adaptive acquisition of previously unobserved runtime-legal evidence→reclassification before novelty；`PLAUSIBLY_NOVEL_PENDING_FULL_TRAFFIC_OSR_REVIEW`）、M1 RECOVERABILITY_AND_HARM_AWARE_TYPED_EVIDENCE_ROUTING（supporting；不claim generic instance-wise/typed/expected-utility-routing/AFA）、C2_CONDITIONAL EVIDENCE_GATED_UNKNOWN_CANDIDATE_PURIFICATION_FOR_SELF_EVOLUTION（在clustering/human-verification/new-class-adaptation前移除Evidence-recoverable Known；`PLAUSIBLE_NOVELTY_PENDING_OPEN_WORLD_AND_CONTINUAL_VALIDATION`）。`SELF_EVOLUTION_STATUS=PLANNED_CORE_SYSTEM_LOOP_PENDING_PURIFICATION_AND_CONTINUAL_VALIDATION`，self-evolution novelty≠continual learning本身；完整continual训练前必须先验证Evidence Gate是否真正净化Unknown candidate stream（Purification Gate，不做continual训练）。FURK=`PROPOSED_RECOVERABILITY_CONDITIONED_FALSE_UNKNOWN_DIAGNOSTIC`；RL保持optional non-core。下一Open-World Gate必须含：`POLICY_CONDITIONED_NOVELTY_CALIBRATION`、`NON_CHEATING_PRE_ACQUISITION_ROUTER`、`READ_ONLY_EVIDENCE_ACQUISITION_ASSUMPTION`、EVIDENCE_SUBSET_ANALYSIS（NONE/T/R/TR）、FURK分解与规定baselines，且**utility routing必须对比generic difficulty routing（LOW_CONFIDENCE/HIGH_ENTROPY）**。access register：`RONETC/ROECI/GCLC_FULL_TEXT_REVIEW=COMPLETE_EXTERNAL_RESEARCHER_WORKFLOW`，`ACO_ICML_2024_FULL_METHOD_REVIEW=PENDING`（MEDIUM_HIGH，不阻塞empirical gate，final first claim前必须核读）；`ACCESS_LIMITED_CRITICAL_PAPERS=1`；不得虚构method细节。详见[related_work_novelty_reassessment_v1.md](../reports/research_audit/related_work_novelty_reassessment_v1.md)（JSON：[related_work_novelty_reassessment_v1.json](../reports/research_audit/related_work_novelty_reassessment_v1.json)）与addendum [literature_novelty_reassessment_v1.md](research_plan/literature_novelty_reassessment_v1.md)（non-frozen，未改写experiment_protocol_v1.md/model_b_evidence_openworld_design.md，未新增DEC行）。

**Open-World Recoverability Gate V1（2026-08-17，kill gate）**：`OPEN_WORLD_RECOVERABILITY_GATE=FAIL`（4/7 criteria；severe failure成立——FURK_UTILITY > FURK_DIRECT在9/9 cells）。三套whole-class rotations（Credential/Recon_Scanning/Web_Injection）×3 seeds，6-class B/BT/BR/BTR（frozen Gate-1 RF config）+ TRAIN-only 3-fold OOF utility selectors（frozen Gate-1B config）+ population-relative policies（budget 0.15·N，P0–P7含random 100 reps、LOW_CONFIDENCE、HIGH_ENTROPY、UTILITY_TYPED、analysis-only ORACLE）+ per-policy policy-conditioned calibration（5% Known FUR，VAL_CALIB Known-only）+ MSP novelty score（1−max known proba，按实际acquired Evidence的model）。**核心负面结果**：typed utility acquisition使recoverable-Known false-Unknown显著恶化——FURK mean +0.235 vs direct（9/9 cells全恶化，pooled paired group bootstrap CI [0.082, 0.290]）、+0.230 vs random；而True Unknown识别**未受损**（Unknown AUROC mean +0.0098、recall@5%FUR mean +0.013）、Known分类**改善**（Macro-F1 mean +0.015，Evidence Recovery Rate mean 0.525）。机制证据：oracle（P7）也不能避免residual Known rejection上升（0.140→0.143 seed 20260817/Credential）——瓶颈是acquired Evidence下的MSP novelty scoring，不是routing质量；classification recovery不转移为novelty-score recovery。B14强制对比：utility routing**未**优于generic difficulty routing（vs LOW_CONFIDENCE FURK +0.052/+0.074/+0.002，vs HIGH_ENTROPY +0.344/+0.075/−0.139），故不claim utility-specific routing value。**Phase C（Unknown-Candidate Purification Gate）未运行**（B17 FAIL→STOP）；bootstrap已显示evidence-gated buffer的recoverable-Known污染高于direct buffer（diff +0.041，CI [0.005, 0.085]），purification foundation NOT established。Gate 1/Gate 1B结论不变（classification-utility findings复现）。**mainline含义**：下一proposed action=`REASSESS_RECOVERABILITY_CONDITIONED_OPEN_WORLD_MAINLINE`——在重新测试acquisition的开世界价值前，必须先解决acquired Evidence下的novelty scoring（如evidence-conditioned novelty calibration）；当前MSP+fixed-FPR路径不被本gate支持。结果**未提交、未push**（tool/test/report为untracked；artifacts在Git-external `open_world_recoverability_gate_v1/`）。详见[open_world_recoverability_gate_v1.md](../reports/research_audit/open_world_recoverability_gate_v1.md)（JSON：[open_world_recoverability_gate_v1.json](../reports/research_audit/open_world_recoverability_gate_v1.json)）。

Teacher v1经验限制（真实baseline行为，不是generation failure）：冻结prompt下`ACQUIRE_RELATION=0`、`ENTER_NOVELTY_DETECTION=0`（action分布`STOP_AND_CLASSIFY=741`、`ACQUIRE_TEMPORAL=1259`）。不得改prompt、重跑、删除结果或人为补action。角色边界因此为：

```text
TEACHER_SUPERVISOR_BASELINE=VALID
POLICY_DEMONSTRATION=VALID_WITH_ACTION_SUPPORT_LIMITATION
OPTIONAL_IMITATION_INITIALIZATION=LIMITED_NOT_DEFAULT
```

这2,000条不是“完整四动作imitation dataset”；Teacher仍不是classification/utility/Unknown/continual GT或RL reward GT。

继续禁止：未经授权的Model B/Qwen运行、正式训练、continual实现、RL、数据下载、raw PCAP处理、修改Model A checkpoint、self-training、打开sealed FINAL_TEST；未经明确授权的push；任何V2 probe/阈值/协议层面的rescue或shopping；Strong Neural OSR仅限协议起草/评审，任何评估须先冻结预注册commit（DEC-0028）。

**V1 failure attribution（2026-08-17，diagnostic only，V1 FAIL不变）**：
`OPEN_WORLD_V1_FAILURE_ATTRIBUTION_AND_FURK_AUDIT`完成。**FURK denominator
audit PASS**——每个rotation内6个policy（P0/P2/P3/P4/P5/P6）denominator完全
一致（Credential 1396/1569/1633、Recon 453/435/510、Web 1053/1200/1234），
row identity按行验证（stored recoverable column == frozen-model重算flag，
digest/block列row-aligned；9/9 cells的11项cross-verification全PASS）；
raw numerator与frozen report完全一致（1220/2295、895/1034、702/2043；
0.2653→0.4991、0.6402→0.7396、0.2013→0.5859）。**归因（raw counts，
≥2/3 rotations，无调参）**：F1 classification-utility target mismatch
(2/3，HELP novelty improve 0.446/0.531/0.406，worsen 0.516/0.428/0.547，
Spearman 0.08–0.29)；**F2 post-Evidence MSP misalignment（3/3，PRIMARY，
RBR 0.157/0.681/0.145、RCJ 0.394/0.734/0.568，R3=2179 pooled）**；F3
policy-conditioned calibration subgroup shift（3/3，threshold −0.029/
−0.085/−0.041；直接CALIB证据：CALIB Known POST P95 −0.029/−0.085/−0.041
而CALIB Recoverable P95 +0.011/+0.052/−0.004）；F4 router selection
failure（2/3，R1 share 0.60/0.07/0.75）。R2=0（定义性）；R3∩R4仅
68/157/53——83–90%的recovered-but-rejected行post-Evidence MSP已高于
DIRECT threshold本身（R4仅counterfactual，从未作为alternative method）。
True Unknown separation PRESERVED 3/3（AUROC delta +0.014/+0.002/+0.014）。
**V2_JUSTIFICATION=YES**（5条件全满足），PROSPECTIVE_V2_DESIGN_REQUIREMENT=
“novelty interface must explicitly model recovery state rather than
post-classification MSP alone”——概念性修正，非detector replacement，
未推荐Energy/Mahalanobis/OpenMax/neural binary detector。
RL_SEQUENTIAL_DECISION_JUSTIFICATION=PLAUSIBLE（analysis only，R3=2179/
9483>0.15；未run RL，RL不required）。状态：
C1_STATUS=V1_MECHANISM_FAILED_V2_PROSPECTIVE_JUSTIFIED；
M1_STATUS=CLASSIFICATION_CONDITIONAL_UTILITY_SUPPORTED_ONLY；
C2_STATUS=PAUSED_NOT_SUPPORTED_BY_V1；
SELF_EVOLUTION_STATUS=PLANNED_BUT_NOT_AUTHORIZED_PENDING_OPEN_WORLD_FOUNDATION。
V1 FAIL checkpoint commit=4fc7591（local only，push blocked: no GitHub
creds）；全部diagnostic outputs（tool/test/report md/json/context更新）
**未提交、未push**（等待researcher review）。详见
[open_world_gate_v1_failure_attribution.md](../reports/research_audit/open_world_gate_v1_failure_attribution.md)
（JSON：[open_world_gate_v1_failure_attribution.json](../reports/research_audit/open_world_gate_v1_failure_attribution.json)）。

**Recovery-Signal Characterization and Open-World Transfer Gate V2
（2026-08-17，preregistered kill gate；结果未提交、未push）**：
`RECOVERY_SIGNAL_CHARACTERIZATION_AND_OPEN_WORLD_TRANSFER_GATE_V2`按冻结
protocol执行完毕（preregistration commit `22c92c7`，protocol sha256
`b1d01629215470ba425c52f76dc5547c8bf4cb8e810a1ebcad30a853be2a5b7b`；
60/40 group-atomic SHA256 split of VAL_CALIB Known，stratum=(class,block)，
无RNG；POST_ONLY 7-dim vs TRAJECTORY 19-dim；capacity ladder
L=LR(scaled, C=1.0, l2, lbfgs, balanced) / N=RF(300, depth10, leaf20,
sqrt, balanced_subsample, seed)；ACCEPT_TARGET=post-Evidence Known预测
==真实label；calibration=5% Known FUR on V2_PROBE_CALIB，V1 tie语义；
bootstrap=1000 reps group-atomic paired，pooled over 9 cells）。**结果**：
信号——LINEAR NOT_ESTABLISHED（mean ΔAUROC +0.0009，CI [−0.0031,
+0.0041]；per-rotation −0.0029/+0.0058/+0.0031）、NONLINEAR
NOT_ESTABLISHED（mean +0.0002，CI [−0.0048, +0.0045]；
−0.0028/+0.0053/−0.0005）、**RECOVERY_TRAJECTORY_SIGNAL=WEAK**（linear
2/3 rotations为正但pooled CI lower ≤ 0且mean < +0.01）。**Transfer**：
OPEN_WORLD_TRAJECTORY_TRANSFER=NOT_ESTABLISHED——T2/T3/T4 PASS（RCJ
reduction mean 0.154，CI [−0.235, −0.028]；Unknown AUROC/recall未损失vs
N_POST），T1 FAIL（Web_Injection FURK +0.021 > 0.02，mean −0.045仍达标但
“no rotation worsens >0.02”不满足）、T5 FAIL（FURK_N_TRAJ−N_POST CI
upper +0.037 > 0）。**End-to-end**：END_TO_END_OPEN_WORLD_GAIN=
NOT_ESTABLISHED（E1–E4全FAIL：N_TRAJ pooled FURK 0.500 vs B0 0.292；
Unknown AUROC −0.020、recall −0.130 vs B0）。**CASE D**：
C1_STATUS=RECOVERY_SIGNAL_INCONCLUSIVE；NEXT_PROPOSED_ACTION=
RESEARCHER_REASSESS_COST_BENEFIT_BEFORE_MODEL_B。Accept-target
classification utility高（AUROC 0.914–0.921、AUPRC 0.994）但open-world
utility不跟随（FURK 0.50、RCJ 0.24）——myopic分类utility≠final open-world
utility继续成立，RL_SEQUENTIAL_DECISION_JUSTIFICATION=PLAUSIBLE（analysis
only），RL_REQUIRED=false。FURK denominator identity PASS（9483 pooled，
9 cells内6 methods全一致；per-cell 1396/453/1053/1569/435/1200/1633/
510/1234与V1 attribution一致）。Section 32（frozen V1 outputs）：
Spearman T/R/TR 0.134/0.203/0.235（CI全部>0，weak alignment）；
HELP improve 0.458/0.571/0.446、worsen 0.501/0.380/0.509（HELP内部
utility与novelty utility不一致，worsen≈improve）。Headroom diagnostics
（analysis only，非gate）：ROUTER_RECOVERY_HEADROOM 0.605/0.073/0.746、
INTERFACE_HEADROOM_PROXY 0.376/0.683/0.526。全部V2 artifacts在
Git-external `processed/dataset_v4_nf3_ton_v1/recovery_signal_characterization_gate_v2/`
（cells/features/probes/BUGFIX_LOG）；report md/json与context更新已于
2026-08-18 researcher review后进入本地checkpoint commit
（`V2_RESULT_COMMITTED=true`，仍未push）。
V2为CASE D（WEAK signal），**不构成Model B/RL/continual授权**；任何
Model B、novelty interface、purification工作均须researcher决策。
详见[recovery_signal_characterization_gate_v2.md](../reports/research_audit/recovery_signal_characterization_gate_v2.md)
（JSON：[recovery_signal_characterization_gate_v2.json](../reports/research_audit/recovery_signal_characterization_gate_v2.json)）。

**Strong Neural OSR授权（2026-08-18，DEC-0028，research decision only，无实验）**：V2 CASE D后researcher决定下一方法学步骤为**Strong Neural OSR Evidence Gate**——专用open-set representation（strong neural OSR）的预注册pre-Model-B基线。理由：V1/V2只测试了廉价output-level novelty接口（MSP变体），未评估专用open-set representation；瓶颈证据F2_POST_EVIDENCE_MSP_MISALIGNMENT（3/3）与V2 headroom diagnostics（analysis-only）指向novelty接口而非routing。约束：**无detector shopping；不授权Qwen/Model B；不授权RL/continual/purification；FINAL_TEST保持sealed；必须先起草协议并经researcher review，在任何评估指标计算前冻结frozen protocol+preregistration commit（沿用V2模式）；结果在researcher review前不提交不推送。** 当前仅授权协议起草/评审。范围说明：V2 protocol的“neural novelty detector NOT AUTHORIZED”条目是V2任务范围限制，不是永久项目禁令——任何未来novelty方法（含Strong Neural OSR）都须经各自授权的预注册协议。详见[research_plan_detailed.md](research_plan/research_plan_detailed.md) Decision Log DEC-0028。

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
