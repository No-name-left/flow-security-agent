# Dataset-v4 / NF3-ToN Core Design

> 状态：DEC-0025/DEC-0026 frozen core data + DEC-0027 derived-view rules
>
> 日期：2026-08-16
>
> “Multi-dataset”保留为外部domain stress与replication能力，不再要求多源合并才能成立。方法与模型见[model_b_evidence_openworld_design.md](model_b_evidence_openworld_design.md)。

## 1. Core artifact

Dataset-v4核心优先冻结为official final processed `NF3-ToN-IoT` artifact：

```text
CSV_SHA256=53ec8f468a43ede9b1536fabc0390af2fa33ab4312b23ce4d864f186a4651f78
ARTIFACT_RECONCILIATION=PASS
RAW_REPROCESSING_REQUIRED=false
SCHEMA=PASS
LABELS=PASS_EXACT_MATCH_TO_PAPER_AND_UQ_CATALOGUE
```

文档中的53与57 feature-count差异是non-blocking catalogue/reporting口径，不改变CSV身份、schema或label validity。

## 2. Source roles

| Source | DEC-0025 role | Core dependency |
| --- | --- | --- |
| NF3-ToN-IoT | `CORE_PRIORITY` | Yes |
| NF3-UNSW-NB15 | `SECONDARY_EXTERNAL_DOMAIN_STRESS / REPLICATION_CANDIDATE` | No |
| NF3-BoT-IoT | `SECONDARY_EXTERNAL_DOMAIN_STRESS / REPLICATION_CANDIDATE` | No |
| NF3-CSE-CIC-IDS2018 | `SECONDARY_EXTERNAL_DOMAIN_STRESS / REPLICATION_CANDIDATE` | No |
| Edge-IIoTset Model A | `LEGACY_CONTROLLED_DOMAIN_BASELINE / OPTIONAL_REPLAY_SOURCE` | No |
| CICIoT2023 | `NOT_REQUIRED_FOR_CORE` | No |
| raw CIC / raw ToN | `NOT_REQUIRED_FOR_CORE` | No |

已有cross-source结果为`WEAK_AND_DOMAIN_DEPENDENT`，正式解释为secondary domain-stress finding。它不能伪装成跨域问题已解决，也不再阻塞NF3-ToN core或Model B。

## 3. Frozen taxonomy

`CANONICAL_TAXONOMY_V1`是：

```text
Benign
Backdoor
Credential
DDoS
DoS
Recon_Scanning
Web_Injection
```

约六类攻击机制加Benign足以回答核心问题。DEC-0026已根据official mapping、全量class/split support与whole-class holdout feasibility冻结该集合；`mitm/ransomware`不是targets。不得为增加类别数量主动搜索或下载更多数据。

## 4. Formal record contract

Dataset-v4 record至少需要：

- immutable `sample_id`与source artifact version；
- official fine/broad label与冻结class index；
- deterministic group/time/split assignment；
- model-safe Basic features；
- admissible Temporal/Relation availability与cost；
- OOF Basic与Evidence-augmented outcomes；
- evaluation state和Unknown-rotation membership；
- model-visible/backend-only field separation。

source filename/path、dataset identity、absolute run/capture identity、attack schedule、GT join evidence、split identity和future information均不可进入模型。

## 5. Evidence contract

### 5.1 Semantic admissibility

Basic、Temporal和Relation必须label-free、test-time available、causal/past-only并具有合法网络语义。当前NF3 flow artifact只授权它真实承载的bounded sample-local features；不得把不存在的packet/payload/application语义写成已实现。

### 5.2 Operational utility

每个family的utility来自OOF/cross-fitted Basic与Basic+family决策差，而不是Teacher semantic sufficiency。正式artifact必须存fold/seed、prediction provenance、correctness recovery、loss delta与availability；in-fold target是hard fail。

### 5.3 Core families

第一轮比较：Basic、Basic+Temporal、Basic+Relation、Basic+Temporal+Relation。Application/Payload/Knowledge均为optional；只有后续data support与utility Gate同时通过才纳入。

## 6. Split and leakage protocol

B1已冻结`GROUPED_TEMPORAL_HASH_70_15_15_V1`（seed `20260816`）：五分钟时间块+无序endpoint pair组成private group，再由label-free stable hash整组分配；禁止普通random row split。七类TRAIN/VALIDATION/FINAL_TEST为`19,858,267/3,809,983/3,842,026`，source/exact-duplicate/activity-group cross-split均为0。完整协议见[dataset_v4_split_protocol.md](dataset_v4_split_protocol.md)。

至少审计：

- immutable sample identity overlap；
- exact/near model-view collision；
- group/run/device/time leakage；
- scaler/encoder/feature-selection fit仅用train；
- OOF fold independence；
- class-map/index consistency；
- Unknown whole-class isolation；
- threshold development与final Unknown隔离。

artifact级split保留原始行身份与官方label，不需要raw PCAP重建。

master split保持immutable。`1,816,137`个duplicate copies已因grouping实现0 cross-split，但正式训练前仍须按[experiment_protocol_v1.md](experiment_protocol_v1.md)派生exact-group representative与duplicate-group-weighted TRAIN view；primary evaluation同时给duplicate-balanced/deduplicated与raw-prevalence sensitivity。不得为此修改master assignment。

## 7. Open-world rotations

每次rotation选择一个或多个whole semantic class作为True Unknown。该类不得进入classifier training、utility target model training（当target会泄漏class identity时）或final threshold tuning；Full合法Evidence必须可观测。

Credential、Recon_Scanning、Web_Injection已冻结为三套whole-class rotations。各held-out class从对应Known classifier train与threshold development中完整移除，FINAL_TEST held-out observations只用于sealed evaluation。当前pilot的class-specific limitations仍必须在B3/B4逐类报告；Observability-limited或Full仍无信息的样本不能当Unknown。

## 8. Pilot evidence and limitations

固定24k pilot显示：

- Basic/Full OOF Macro-F1 `0.9241027728324086/0.9542507313534688`；
- recoverable Known `2,879/24,000`；
- utility AUROC/AUPR `0.9559201214445113/0.6823986368255095`；
- Direct/Evidence-conditioned Unknown AUROC `0.7583657442883499/0.7683698955976005`；
- FURK `0.3062080536912752 → 0.24161073825503357`；
- acquisition rate `0.1459902525476296`。

Recon_Scanning Unknown separation弱；Web_Injection Unknown改善但FURK恶化；Credential FURK改善但fixed-FPR recall下降。当前Full仅bounded sample-local Temporal+Relation。结论是concept feasibility，不替代formal single-family、seed/bootstrap和cost sensitivity。

## 9. Formalization outputs

B1已生成：

- tracked small artifact manifest与SHA256；
- frozen taxonomy decision；
- split/group protocol与per-class counts；
- Evidence field/availability/cost schema；
- Known/Unknown rotation registry；
- leakage audit与OOF fold manifest；
- Git-external formal row assets。

报告明确区分artifact/taxonomy/split frozen与Model B not started。逐行manifest、reference records和Teacher request/offline truth保持Git-external。

## 10. Secondary domain stress

其他NF3 source只在core static/open-world protocol稳定后进入。它们用于检验representation、utility selector和novelty在domain shift下是否失效，不要求与core物理合并，也不因mapping不完美修改core taxonomy。

secondary experiment必须单独报告source、mapping quality、support和calibration，不把pooled IID成绩冒充cross-domain generalization。

## 11. Raw/payload extension rule

CICIoT2023、raw CIC、raw ToN或新PCAP只有在一个明确研究问题必须依赖packet/payload family、该family已有semantic contract且utility Gate通过后，才能另行Decision授权。当前`RAW_PCAP_REQUIRED_FOR_CORE=false`，禁止预防性下载。

## 12. Go/No-Go boundaries

Dataset-v4 formalization PASS至少要求：artifact hash匹配、label/class map一致、各split support可用、whole-class holdout可实现、无identity/group/future leakage、Evidence fields真实、OOF provenance完整。任一失败先修formalization，不启动Model B掩盖数据问题。

当前状态：

```text
NF3_TON_ARTIFACT_FROZEN=true
CANONICAL_TAXONOMY_V1=FROZEN_PASS
FORMAL_SPLIT=FROZEN_PASS
UNKNOWN_ROTATIONS=Credential,Recon_Scanning,Web_Injection
TEACHER_CACHE_V1_SAMPLE_MANIFEST_READY=true
TEACHER_CACHE_STATUS=FROZEN_COMPLETE_2000_VALID
SEMANTIC_REFERENCE_STATUS=FROZEN_COMPLETE_63_VALID
CORE_HIGH_TOKEN_DEEPSEEK_DEPENDENCY_COMPLETE=true
MODEL_B=NOT_STARTED
CORE_FEASIBILITY=PASS_WITH_LIMITATIONS
NEXT_ACTION=PREPARE_DUPLICATE_AWARE_DATA_VIEWS_AND_START_MODEL_B_LOW_COST_GATES
```
