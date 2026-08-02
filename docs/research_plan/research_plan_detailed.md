# 面向网络Flow可观察ATT&CK父Technique的证据约束开放识别与少样本接入研究：详细方案

> Canonical repository path：`flow_security_agent/docs/research_plan/research_plan_detailed.md`。本文件是研究设计与实现规范的唯一权威事实源；`research_plan_and_timeline.md`和`research_plan_brief.md`是其派生视图，发生冲突时必须以本文件为准并及时同步修正。

拟定英文题目：**Evidence-Grounded Open-Set Recognition and Few-Shot Onboarding of Flow-Observable ATT&CK Techniques**

## Decision Status and Canonical Authority

本规范供后续Agent、开发人员和研究人员在修改数据角色、样本构造、标签、模型结构、可训练参数、训练阶段、损失函数、SFT/DPO/RLAIF或正式评价协议前查阅。状态含义如下：

| 状态 | 含义 |
| --- | --- |
| Confirmed | 已形成正式研究约束，改变时必须记录重大偏离 |
| Provisional | 当前采用的候选方案，允许由训练域验证结果调整 |
| TBD after Gate 0 | 只能在多数据集小样本审计后确定 |
| Optional | 不属于最低可行版本，需通过相应Gate后开展 |
| Rejected | 已明确排除出第一阶段正式路线 |

| 决策 | 状态 |
| --- | --- |
| Flow-only与父Technique主粒度 | Confirmed |
| CasinoLimit + 审计后的UWF-2024作为主训练来源 | Provisional，具体子集TBD after Gate 0 |
| 行为一致、按时间与行为关系排列的多Flow Episode | Provisional，必须通过Episode可行性审计和消融 |
| Qwen基础权重原则上冻结，使用可独立保存的增量参数 | Confirmed |
| SFT作为基础监督训练 | Confirmed |
| DPO作为优先低成本AI反馈偏好实验 | Provisional |
| 严格RLAIF | Optional，须通过独立执行Gate |
| UWF-2025与CAM-LDS进入基础训练或奖励设计 | Rejected |

## 1. 研究背景与缺口

### 1.1 为什么不再以普通闭集分类为主线

前期工作已完成Flow数据处理、LightGBM强基线、本地Qwen服务、结构化输出、RAG和批量实验基础，证明“Flow证据进入本地大模型”的工程链路可行。但在固定Schema、固定类别和同分布测试中，树模型通常已经具有较高的准确率、稳定性和效率；只让LLM复核低置信样本，难以充分说明大模型在识别问题中的必要性。

相关工作也已分别研究多Flow序列、流量Tokenizer、结构自监督、非IID分类、开放集检测、Unknown聚类和增量更新。因此，多Flow输入、Unknown检测或参数高效微调本身均不能单独构成本文的主要创新。

### 1.2 收紧后的研究矛盾

真实部署中会出现监督训练阶段未见的攻击Technique。普通开放集模型可以把异常样本判为Unknown，却不一定能回答它可能对应哪一种ATT&CK行为、当前Flow证据是否足够，以及获得少量新攻击mission后如何接入该类。另一方面，ATT&CK覆盖网络、主机进程、文件、注册表、账户、内存、云控制面、邮件、命令行和身份认证等多种遥测，仅凭Flow不可能验证完整知识矩阵。

因此，本研究只面向经审计确认的**网络Flow可观察ATT&CK父Technique子集**，研究一个连续链路：

```text
已知父Technique识别
→ 未见父TechniqueUnknown拒识
→ Flow证据约束的Top-k ATT&CK候选归因
→ 获得少量独立mission后的新Technique接入
```

潜在新增价值不在“检测Unknown”，而在拒识之后给出有证据边界的语义候选，并以独立攻击Episode完成低样本接入。

### 1.3 正式研究边界

- 正式输入为Flow-only；Payload、主机日志和PCAP内容不进入核心模型。
- 原始IP、绝对时间、文件名、mission ID和数据版本标识只用于审计、分组和追踪，不进入模型。
- 候选Episode只使用锚点时刻及其之前且行为关系可解释的Flow，不使用未来记录；该样本构造仍需Gate 0审计与正式消融验证。
- 研究不覆盖完整Enterprise ATT&CK，也不声称有限训练Technique可迁移到全部未知Technique。
- Process Injection、Modify Registry、Credential Dumping、Clear Event Logs、文件权限修改和本地主机命令执行等依赖主机遥测的行为不属于Flow-only有效标签空间。
- Agent、Tree-aware Reviewer和Static/Agentic比例复核不进入第一阶段正式实验。
- NF-ToN-IoT-v3不进入第一阶段训练、自监督、外测或ATT&CK标签映射。

旧工程中的OpenAI-compatible调用、本地Qwen服务、缓存、请求指纹、失败恢复、结构化/Pydantic校验、延迟与Token追踪、RAG元数据、Git与实验Manifest、NF-ToN-IoT-v3质量审计和LightGBM代码继续保留。

只有Gate 4通过后，Agent才可能用于展示Unknown候选、检索ATT&CK证据、请求额外上下文、辅助分析师确认新Technique和管理少样本接入；Agent不能弥补核心识别模型无效。

## 2. 研究问题与可检验假设

核心问题为：

> 在严格限定的网络Flow可观察ATT&CK父Technique子集中，能否通过统一标准化Flow表示、待验证的行为一致past-only多Flow Episode、结构后训练和Flow证据约束的ATT&CK语义对齐，使中型大模型可靠拒识训练阶段未见的Technique，给出有根据的ATT&CK候选，并在获得少量独立攻击mission或Episode后快速接入新Technique？

| 编号 | 研究问题 | 可检验假设 | 反证或收缩条件 |
| --- | --- | --- | --- |
| RQ1 | 统一标准化Flow表示与候选anchor+past context Episode是否优于单Flow和人工窗口统计？ | 跨连接关系在至少一组网络可观察父Technique上提供稳定增益 | 增益由IP、时间、来源、instance、mission或端口捷径解释，或普通窗口统计同样有效 |
| RQ2 | 结构后训练的Qwen能否识别跨来源已知父Technique并保持时间/外部泛化？ | 9B模型在K_core、UWF-2025冻结时间外测和CAM-LDS冻结外测的至少一项关键指标上优于Base Qwen/普通序列模型 | 只提高单一来源闭集指标，来源变化后退化且校准无改善 |
| RQ3 | 模型能否可靠拒识监督训练阶段未见的父Technique？ | 相比普通分数阈值，完整方法降低高置信误归类并改善开放指标 | 不优于energy、Mahalanobis、RoNeTC/GCLC等强方法 |
| RQ4 | Flow证据原型能否改善Unknown的Top-k ATT&CK候选排序？ | 相比普通文本Embedding和无证据语义对齐，Top-k、MRR或证据充分性稳定提高 | 候选结果主要复述ATT&CK文本，无法由Episode证据支撑 |
| RQ5 | 少量独立mission能否支持新父Technique接入？ | 语义增强episodic方法比普通增量训练或无语义few-shot具有更好的样本效率 | 独立mission不足，或新Technique缺少Flow可观察证据与可迁移行为原语 |

论文不依赖所有假设都成立。若只改善Unknown拒识，则贡献应收缩为开放集能力分析；若证据候选有效但few-shot数据不足，可形成语义归因研究；若多Flow、语义候选和few-shot均无稳定增益，应报告强基线、数据证据边界与失败原因，不扩大到Agent或更大模型。

## 3. 数据集、ATT&CK层级与标签设计

### 3.1 ATT&CK层级与v19.1统一

- **Tactic：**攻击者的战术目标，即“为什么做”，用于辅助层次监督。
- **父Technique：**实现目标的大类方法，即“怎样做”，是第一版主分类粒度。
- **Sub-technique：**父Technique下更具体的实现方式，只在数据和Flow证据充分时条件性细分。
- **Procedure：**具体组织、工具或攻击活动如何实施Technique，不作为主分类标签。

父Technique和Sub-technique不能作为同一级平行类别；一个攻击活动也可能包含多个Technique。所有数据标签统一映射到冻结的Enterprise ATT&CK v19.1，但保留原始标签，不覆盖原始语义。迁移表至少保存：

```text
original_attack_id
original_attack_version
original_tactic
is_sub_technique
original_parent_id
attack_id_v19_1
parent_id_v19_1
tactics_v19_1
mapping_status
mapping_reason
revoked_or_deprecated
replacement_id
observable_from_flow
```

父Technique/Sub-technique与revoked/deprecated ID逐项核验。ATT&CK v19将旧Defense Evasion相关结构调整为Stealth与Defense Impairment，旧Tactic不能整体机械映射；Tactic变化原则上不改变Technique主标签，除非Technique本身被废弃或替换。映射表、ATT&CK快照、版本与哈希随实验Manifest冻结。

### 3.2 覆盖范围必须分层报告

每个数据集分别报告：名义Technique覆盖、v19.1映射后的父Technique、Flow可观察父Technique、最终可用父Technique。审计前后三项均不得由论文中的名义数字推断：

| 数据来源 | 名义覆盖 | v19.1父Technique | Flow可观察父Technique | 最终可用父Technique |
| --- | --- | --- | --- | --- |
| CasinoLimit | 名义约67个Technique（以官方标签审计为准） | TBD | TBD | TBD |
| UWF-2024 Train Pool | 由入选子集标签决定 | TBD | TBD | TBD |
| UWF-2025 Holdout Family | 由正式测试子集决定 | TBD | TBD | TBD |
| CAM-LDS 2026 | 名义13个Tactic、81个Technique | TBD | TBD | TBD |
| TQH-C2 2026 | 加密C2专项标签 | TBD | TBD | TBD |
| UWF-ZeekData22 | 历史标签范围 | TBD | TBD | 仅历史对照 |

只有最后一列才是模型标签空间。不能把CasinoLimit或CAM-LDS的名义Technique数直接写成分类数，也不能用有限训练类声称识别完整ATT&CK。

### 3.3 CasinoLimit：第一主训练来源

CasinoLimit来自BreizhCTF 2024攻防活动，公开资料描述其包含114个相同挑战的独立实例，提供Zeek网络日志与已标注Flow，标签结合Shell会话分析、网络传播和专家复核。其较新的采集时间和较多独立攻击实例使其成为核心Technique监督、Known/Unknown、候选归因、episodic meta-training、few-shot接入及来源内Internal Test的第一候选。

限制同样必须前置：114个实例共享挑战与网络拓扑；名义Technique覆盖不等于Flow可观察类别；部分标签可能从主机行为传播到网络会话；正常背景是否可靠、每个Technique的独立实例数及标签能否定位到Flow/Episode均待审计。划分按challenge instance、participant/team和独立攻击活动完成，同一实例不得跨split，support与query/test来自不同实例，并检查参赛者、固定拓扑、IP、端口和攻击位置捷径。

来源：*CasinoLimit: An Offensive Dataset Labeled with MITRE ATT&CK Techniques*，RAID 2025，DOI `10.1109/RAID67961.2025.00039`；数据集DOI `10.5281/zenodo.17256954`。

### 3.4 UWF-2024 Train Pool：第二主训练来源

`UWF-2024 Train Pool`是审计后形成的概念性训练池，不是新数据集：

1. UWF-ZeekDataFall24-2作为主要候选；
2. UWF-ZeekData24中2024年2—3月的非重叠数据，审计通过后可作辅助训练来源；
3. Data24中2024年10—11月与Fall24-2存在相同周目录，必须先做记录与时间重叠审计，不得默认重复加入。

该训练池用于提供近期企业式Zeek Flow、可靠Benign候选、与CasinoLimit不同的网络环境、补充Flow行为、父Technique监督候选、近期Internal Test、Task 0和训练划分内结构自监督。是否进入Technique监督取决于mission边界、Episode标签定位、独立mission数、Flow可观察性、父子关系、ATT&CK版本、重复风险和Benign可靠性。若Fall24-2只支持Tactic或二分类，它仍可用于Task 0、结构自监督和背景建模，但不能强行承担父Technique监督。

### 3.5 UWF-2025 Temporal Holdout Family

UWF-ZeekDataSum25-1和Sum25-2在未证明相互独立前统一视为`UWF-2025 Temporal Holdout Family`。两者均不得进入正式训练、Stage A、校准、阈值、原型或模型选择，也不得用其中一个调参后将另一个宣称为独立测试。

正式用途是评价CasinoLimit + UWF-2024训练后的模型在2025 UWF环境中对Known父Technique可靠交集、Task 0、校准和鲁棒性的变化。若Gate 0证明二者具有明确独立采集边界，可条件性地选择较早且覆盖较广者作辅助训练/验证、较晚者作时间外测；若重叠或关系不明，则整个家族继续冻结，或只选择标签质量更高者测试。审计前不承诺具体处理。

### 3.6 CAM-LDS 2026：冻结跨数据集外测

CAM-LDS名义上包含13个ATT&CK Tactic、81个Technique、七个攻击场景和多次独立模拟运行，并提供NetFlow、系统日志与安全告警。正式实验只使用NetFlow或可转换到公共Flow字段的网络数据，不使用系统日志、Wazuh或Suricata告警作为模型输入。

其角色是2026年跨组织、跨环境、跨Schema的冻结外部测试，评价Flow可观察父Technique的zero-shot候选、证据充分性、性能下降和条件性few-shot。它不参与基础训练、Stage A-D、校准、阈值或模型选择；由于没有正常用户行为模拟，不用于Task 0主结果。81个名义Technique中很多只能由主机日志确认，最终只选Flow可观察、标签可定位且有足够独立运行的父Technique。zero-shot必须先于任何support，few-shot的support与query/test来自不同simulation run或scenario variant。

来源：*CAM-LDS: Cyber Attack Manifestations for Automatic Interpretation of System Logs and Security Alerts*，arXiv `2603.04186`；数据集DOI `10.5281/zenodo.18390561`，使用时记录具体版本。

### 3.7 可选与历史数据

- **TQH-C2 2026：**仅作为非最低版本的加密C2专项外测，评价TLS、QUIC、HTTP、beacon interval、jitter和逐Flow ATT&CK标签，不作主训练或扩大通用Technique数量。数据集DOI `10.5281/zenodo.21435571`。
- **UWF-ZeekData22：**不再是主训练集，仅用于历史域对照、2022→2024/2025概念漂移和“是否使用Data22结构预训练”的消融；不自动进入Stage A。
- **NF-ToN-IoT-v3：**缺少可靠ATT&CK Technique标签，继续作为历史资产。
- **Multi-Source Cybersecurity Logs 2026：**在确认存在可独立获取、标签可靠的Flow子集前只作候选与相关工作。
- **Atomic-EVTX、COMISET、Linux-APT：**以主机事件为主，不符合Flow-only输入。
- **CTU-IDSEVAL-6、BigFlow-NIDS：**标签不适合广覆盖ATT&CK父Technique主任务。

### 3.8 K_core与K_union

`K_core`要求父Technique原则上至少在两个独立数据来源或环境出现，在每个来源具有足够独立实例/mission/run，Flow可观察、标签可定位、v19.1映射一致且不依赖数据集特有字段。它用于核心主结果、跨来源泛化、source leave-one-out、时间迁移和证据原型评价。

`K_union`由CasinoLimit与UWF-2024训练池所有审计合格的Flow可观察父Technique组成，用于扩大覆盖、单源已知分类、Unknown留类、稀有Technique few-shot及附录实验。只在单一来源出现的Technique必须分来源报告，不构成跨数据集泛化证据，也不能以总体Macro-F1掩盖来源差异。

### 3.9 联合训练与来源捷径

联合训练不是把所有Flow行直接拼接。两来源先映射到ATT&CK v19.1，只使用可靠公共字段并显式记录missing/availability mask；dataset name、source ID、文件名、年份、目录、原始IP和绝对时间不进入模型。训练按独立实例/mission采样，并按来源和Technique平衡或分层，防止大型扫描活动支配训练。

至少比较CasinoLimit-only、UWF-2024-only、naive pooled和source-balanced pooled；source-adversarial/source-invariant约束为可选。保存source metadata供审计但与输入物理隔离，运行source probe、leave-one-source-out或train-one-test-another。若增益可由来源识别解释，不得称为行为泛化。

### 3.10 Gate 0：Multi-Dataset Selection, Compatibility and Observability Audit

第一阶段采用`metadata-first, selective-download`，先获取官方说明、datasheet、README、标签、Technique/Tactic统计、instance/mission/run元数据、少量Flow样本、目录、许可证和校验和，不下载所有全量数据。每个数据集生成：

```text
dataset_id
dataset_version
release_date
collection_period
organization
environment
traffic_or_log_type
flow_schema
label_method
attack_version_original
nominal_tactic_count
nominal_technique_count
parent_technique_count_after_mapping
flow_observable_parent_count
benign_available
independent_instance_count
independent_mission_count
independent_run_count
label_granularity
episode_localization_quality
flow_label_quality
duplicate_or_overlap_risk
known_overlap_with_other_sources
storage_size
license
eligible_for_supervised_train
eligible_for_structural_pretraining
eligible_for_internal_test
eligible_for_temporal_test
eligible_for_external_test
eligible_for_zero_shot
eligible_for_few_shot
exclusion_reason
```

专项检查Data24/Fall24-2在2024年10—11月的重叠、Sum25-1/Sum25-2关系、UWF共享mission或记录、CasinoLimit每类独立实例和Flow证据、CAM-LDS的NetFlow可观察性、公共字段、v19.1迁移、Benign可靠性及support/query可分性。Gate 0预计4—7天；结束后才能冻结UWF-2024组成、UWF-2025测试子集、K_core/K_union、Known/pseudo/final unknown、shot梯度、CAM-LDS可用Technique和TQH-C2是否启用。

### 3.11 下载与存储策略

- CasinoLimit优先下载`labelled_flows`和`flows_zeek`，syslogs不作为模型输入；
- UWF优先Technique/Tactic metrics、mission元数据和必要conn Parquet周，不默认下载PCAP；
- CAM-LDS只提取NetFlow和标签，系统日志仅用于人工核验；
- TQH-C2如启用，优先features、labels和Zeek日志，不下载大体积PCAP。

所有资产保存文件校验和、数据版本、下载日期和许可证；冻结外测数据在文件与权限层面和训练池隔离。

## Dataset Origin, Collection Setting and Intended Role

每个数据源的Manifest必须记录：名称与版本、发布机构、采集时间、发布年份、国家或组织背景、环境类型、原始数据类型、可用Flow类型、PCAP/Payload可用性、标签来源与粒度、Benign情况、是否以攻击为主、独立instance/mission/run单位、原始ATT&CK版本、预期角色、优势、局限和Gate 0问题。无法由当前可靠资料确认的字段一律标为`TBD after Gate 0`。

| 数据源 | 来源与环境类型 | 原始/可用网络数据 | 标签与独立单位 | 预期角色 | 主要限制与TBD |
| --- | --- | --- | --- | --- | --- |
| CasinoLimit | BreizhCTF 2024攻防竞赛与受控靶场；真实参赛者在共同挑战环境中操作；不是企业生产流量 | Zeek网络日志与已标注Flow；另有主机/系统信息但不进入核心输入；PCAP/Payload情况TBD | 标签结合Shell会话分析、网络传播和专家复核；按challenge instance、participant/team和攻击活动分组 | 第一攻击Technique训练候选；来源内Known/Unknown、Top-k和few-shot；不单独承担Task 0主结果 | 多实例共享挑战、拓扑与目标；正常背景、精确label unit、每类独立实例和Flow标签可靠性TBD |
| UWF-2024 Train Pool | UWF发布的近期受控网络安全研究或企业式网络环境；不同于CTF攻击环境 | Zeek记录、mission元数据及入选conn数据；不默认使用PCAP | 标签可能位于Flow、mission或时间区间；按week、mission、capture和连续时间块分组 | 近期训练域；Task 0；父Technique监督候选；企业式背景补充 | Fall24-2/Data24重叠、Benign质量、label unit、Episode定位和可观察性TBD；同一时段Flow不得自动继承mission标签 |
| UWF-2025 Temporal Holdout Family | 2025年UWF后续受控环境；Sum25-1与Sum25-2关系未明 | Zeek/Flow候选，具体版本与Schema待核验 | mission、时间和标签粒度TBD | 冻结时间外测；Known可靠交集、Task 0漂移、校准与鲁棒性 | 两子集重叠、可比Known类和真实时间外测能力TBD；禁止进入Stage A、SFT、DPO、RLAIF、校准和模型选择 |
| CAM-LDS 2026 | 受控攻击场景或cyber-range式多源安全日志环境 | NetFlow、系统日志与安全告警；核心项目只用NetFlow或公共Flow字段 | 按scenario、simulation run和variant；Technique到NetFlow的定位质量TBD | 冻结跨数据集外测；Flow可观察Technique的zero-shot和条件性few-shot | 名义Technique不等于Flow可观察Technique；无Task 0主结果；不参与训练、预训练、校准或奖励设计 |
| UWF-ZeekData22 | 较早UWF Zeek与ATT&CK受控研究数据 | Zeek Flow；其他原始类型按历史Manifest记录 | mission/时间块，具体映射沿用审计结果 | 历史对照、可选结构预训练消融、2022→2024/2025漂移 | 不作为当前主训练；不自动进入Stage A |
| TQH-C2 | 加密C2专项研究数据候选 | features、labels、Zeek日志；PCAP不优先下载 | 逐Flow标签与运行单位待审计 | Optional专项外测 | 不扩大通用Technique类别，不进入最低版本 |
| NF-ToN-IoT-v3及主机日志型数据 | 历史Flow资产或主机事件数据 | NF-v3为Flow；其他以主机日志为主 | 缺少适配当前任务的可靠父Technique标签 | Rejected于第一阶段正式实验 | NF-v3保留历史审计；主机日志不符合Flow-only边界 |

各数据集的发布机构、国家背景、采集日期、许可证、精确版本、PCAP/Payload可用性与原始ATT&CK版本必须由官方datasheet或Gate 0材料核验，不根据记忆补充。

## 4. 统一标准化Flow表示（内部工作名FlowIR）

### 4.1 名称与定位

本文正式称其为**统一标准化Flow表示（canonical flow representation）**；“FlowIR”仅是项目内部工作名称，不是领域现有标准。字段统一、单位换算、missing mask或Adapter本身也不构成主要创新，其作用是提供确定性输入、防止捷径并支持Episode和后训练。

第一阶段只使用CasinoLimit与UWF-2024之间可靠公共字段，并为CAM-LDS NetFlow外测保留确定性映射。跨Schema的目标是保证公平输入与可审计缺失，不是用来源特有字段扩大信息量；NF-v3仍不属于当前统一范围。

### 4.2 功能范围

| 功能 | 处理原则 |
| --- | --- |
| 字段与单位 | 冻结字段映射、时间/字节等单位及连接状态枚举 |
| 时间 | 使用相对Episode锚点或前序Flow的时间，不输入绝对日期时间 |
| 数值长尾 | 候选`log1p`、鲁棒缩放和分位数分箱，参数只由训练集拟合 |
| 实体 | 原始IP只存审计侧；Episode内映射为`HOST_1`、`HOST_2`等临时实体 |
| 协议/端口 | 协议统一枚举，端口采用区间或服务类别；精确端口仅作消融 |
| 缺失 | 区分真实零、缺失和不适用；显式记录missing mask与field availability |
| 版本 | 记录转换版本、源字段追踪、Schema版本和校验结果；source metadata仅存审计侧 |

模型输入不包含dataset name、source ID、文件名、捕获名、instance/mission/run ID、数据年份和直接暴露标签的字段。所有变换均可复现、可审计、可回溯到源记录。

### 4.3 捷径与信息边界

端口、服务状态、字段可用性和Schema差异仍可能泄露来源，需要source probe和消融检查。统一表示不推断源数据中不存在的字段，不用零伪装缺失值，也不把ATT&CK知识写入Flow观测。来源、版本和原始IP可用于分组及错误分析，但与模型输入物理分离。

## 5. 行为一致、按因果顺序排列的多Flow Episode（待验证假设）

多Flow Episode不是数据集原生提供、天然正确的样本单位，而是必须经过Gate 0与消融验证的建模假设。本文所称“因果顺序”只表示时间方向、行为关联与不使用未来信息，不声称从Flow中完成严格因果发现。时间相邻的Flow不能被简单拼接并统一赋予一个Technique标签。

### 5.1 Raw Record, Label Unit and Model Sample

1. **Raw record：**一条Zeek `conn`记录或等价NetFlow记录，通常对应一条Flow。
2. **Label unit：**由数据集标注机制决定，可能是单Flow、mission/攻击步骤、时间区间、challenge instance或simulation run。
3. **Model sample：**可不同于原始Flow，但必须尊重原始标签边界，不能令时间窗口中所有Flow默认继承同一Technique。

当前优先验证的样本形式为：

```text
S_i = (a_i, C_i, R_i, y_i)
```

- `a_i`：具有相对明确父Technique标签的锚点Flow、攻击步骤或活动锚点；
- `C_i`：锚点发生前、与其行为相关的上下文Flow集合；
- `R_i`：上下文Flow之间以及上下文与锚点之间的关系；
- `y_i`：锚点或攻击步骤的父Technique标签。

模型判断的是锚点攻击行为或攻击步骤的Technique；上下文Flow只提供行为证据，不表示Episode内每条Flow都属于同一Technique。CasinoLimit精确label unit、UWF mission与Flow标签对应关系及CAM-LDS run内标签定位均为`TBD after Gate 0`。

### 5.2 硬性构造规则

1. **先split，后生成Episode。**先按instance、mission、week、capture、scenario或simulation run划分训练、验证和测试，再分别生成Episode；禁止先生成重叠窗口后随机拆分。
2. **边界隔离。**Episode不得跨数据集、challenge instance、mission、simulation run、已知攻击活动或训练/验证/测试边界。
3. **past-only。**预测时刻为`t`时，只允许使用`t`及之前的Flow。双向离线Episode只能作为明确标注的上界实验。
4. **行为关联。**上下文选择结合相同源/目标、共享端点、重复通信、端口扩展、扇出/扇入、周期性和时间间隔；固定时间窗口只是基线。
5. **多Technique重叠。**优先缩小到有标签锚点；必要时采用多标签；无法区分则标为`ambiguous`并排除出主监督训练，不强压成单标签。
6. **确定性与可追溯。**截断、采样、关系阈值和最大长度均版本化，并能回溯到原始记录。

### 5.3 关系与Episode质量审计

候选关系包括`SAME_SOURCE`、`SAME_DESTINATION`、`REPEATED_PAIR`、`NEW_DESTINATION`、`NEW_PORT`、`FAN_OUT`、`FAN_IN`、`BURST`、`PERIODIC`、`PORT_SWEEP`和顺序关系。关系由确定性工具计算，不从ATT&CK文本反推当前样本关系。

每个数据源与split至少统计以下字段，正式审计前均为`TBD after Gate 0`：

```text
episode_length
label_purity
relevant_flow_ratio
background_contamination
anchor_coverage
duplicated_context_ratio
cross_episode_overlap
has_explicit_anchor
label_localization_quality
```

若没有明确锚点、label purity或relevant flow ratio无法达到预注册要求，相关Episode不得进入父Technique主监督。

### 5.4 Technique的Flow可观察性分层

| 类型 | 定义 | Episode使用原则 |
| --- | --- | --- |
| A：单Flow可观察 | 单条Flow已有较强证据 | Anchor/Single Flow为主，多Flow仅作可选增强 |
| B：上下文增强型 | 锚点有歧义，前序或同活动Flow可提高判断可靠性 | 比较Anchor-only与关系约束Episode |
| C：关系依赖型 | 证据主要来自重复、扇出、扫描、周期、认证尝试序列或跨主机关系 | 合理判断需要多Flow关系，但仍须锚点和边界 |
| D：Flow证据不足 | 主要依赖进程、命令、文件、注册表、内存或Payload | 不进入第一阶段父Technique监督；最多作为Unknown、粗粒度候选或不可观察案例 |

多Flow Episode不强行用于所有Technique。K_core和K_union只纳入审计合格类别，可观察性分层是Gate 0的正式输出。

### 5.5 显著Flow捷径与正式输入对照

若只提供Episode级标签，模型可能找到最显眼的一条Flow完成分类，而忽略上下文和关系。训练与评价因此区分anchor、context、supporting flows和supporting relations，并规划以下稳定实验ID：

| ID | 输入对照 |
| --- | --- |
| E-A01 | Anchor Flow only |
| E-A02 | Single Flow |
| E-A03 | Fixed-window aggregated statistics |
| E-A04 | Unconstrained temporal Flow sequence |
| E-A05 | Relation-constrained past-only Episode |
| E-A06 | Mission-boundary approximate-oracle Episode |
| E-A07 | Random context |
| E-A08 | Shuffled context |
| E-A09 | Salient-flow removal |
| E-A10 | Context removal |
| E-A11 | Evidence-only Episode |

模型训练可加入`supporting_flows`与`supporting_relations`弱监督、relation prediction、顺序恢复或顺序判别，以及“单Flow外观相似但上下文不同”的hard negative。反事实实验包括删除最显著Flow、随机替换上下文、打乱顺序、删除全部前序上下文和只保留证据Flow。普通Attention权重不能单独证明证据忠实性。

主结论必须回答：多Flow是否优于单Flow；增益是否来自真实关系而非输入数量；模型是否使用时间顺序；是否只依赖最显眼的一条Flow。LightGBM/XGBoost使用同一past-only窗口统计，普通Transformer接收相同序列，保证比较公平。

## 6. 模型结构与规模

### 6.1 基本结构

```text
标准化Flow字段
→ 数值编码 + 类别/缺失Embedding
→ Flow Token
→ 时间位置与关系编码
→ 轻量Episode编码器
→ Qwen表示空间
→ 父Technique/Tactic/Unknown/原型匹配与结构化输出
```

Adapter第一版保持简单；FlowIR文本化Episode作为Base Qwen基线。Adapter、Tokenizer和QLoRA只是实现手段，必须通过消融证明其必要性。

### 6.2 模型规模分工

- **Qwen3.5-9B主模型：**完成Stage A-D、完整实验矩阵、多seed、消融、Known/Unknown、候选归因、data-dependent few-shot、鲁棒性和效率评价。
- **Qwen3.5-27B有限验证：**仅使用最佳配置，在代表性Known、Unknown和few-shot条件下测试模型规模上界，回答9B是否受容量限制；不重复所有seed、数据比例、窗口和消融。
- **Qwen3.5-4B可选：**用于pipeline和小样本调试，可选进入scale curve，不要求作为主结果。
- **DeepSeek：**只用于少量Teacher、原型整理或分析辅助，不逐Episode分类。

模型变大不能补足Flow中不存在的进程、文件或注册表证据。27B验证不改变Flow可观察标签边界。

### 6.3 参数分类与冻结边界

总体结构保持为：

```text
Flow字段编码器
→ 多Flow Episode编码器
→ Qwen隐藏空间投影
→ Qwen3.5-9B
→ Technique / Tactic / Prototype / Unknown / Evidence输出
```

| 参数类别 | 组成 | 默认策略 |
| --- | --- | --- |
| Qwen基础权重 | 原始Qwen3.5-9B参数 | 原则上冻结，不做全参数微调 |
| LoRA参数 | 加到Qwen线性层的低秩增量 | 可训练、独立保存、加载和选择性合并；目标层TBD |
| Flow前端 | 数值/类别Embedding或MLP、availability/missing mask Embedding | 可训练；按阶段设置学习率或条件冻结 |
| Episode模块 | 时间Embedding、关系Embedding、Episode Encoder、Qwen projector | 可训练；必要性须由E-A系列消融验证 |
| 任务模块 | Technique/Tactic头、Prototype投影、Known/Unknown或energy scoring、evidence定位头 | 按相应监督任务训练 |

Qwen基础权重冻结不意味着阶段间互不干扰。连续训练同一LoRA、Flow Encoder或Episode Encoder仍可能迁移或遗忘前序能力；多个LoRA直接相加也不被默认认为有效。Adapter composition若开展，必须作为独立实验。

### 6.4 Checkpoint继承与遗忘控制

推荐继承链为：

```text
Base Qwen
→ checkpoint_StageA
→ checkpoint_StageA_B_SFT
→ checkpoint_StageA_B_C
→ Stage D calibration artifacts

checkpoint_StageA_B_SFT
├── checkpoint_SFT_DPO
└── checkpoint_SFT_RLAIF
```

每个阶段保留独立checkpoint，后阶段不得覆盖前阶段唯一结果。Stage B从Stage A初始化，Stage C从Stage A+B初始化；Stage D通常冻结模型，仅拟合温度、阈值和校准参数。DPO和RLAIF从冻结SFT checkpoint分别建立实验分支，不互相覆盖。

遗忘控制包括：后续阶段保留少量前序任务，replay部分Stage A/B样本，不同模块使用不同学习率，分别监控Flow Encoder、Episode Encoder和LoRA，并同时记录当前任务与前序任务指标。是否冻结前端模块由训练域实验决定，不预先声称不存在灾难性遗忘。

### 6.5 训练与输出

9B首选QLoRA、BF16计算、4-bit NF4和梯度检查点，checkpoint只依据允许的训练域验证集选择。建议输出：

```json
{
  "known_status": "unknown",
  "known_technique": null,
  "candidate_techniques": [
    {
      "id": "Txxxx",
      "score": 0.71,
      "supporting_flow_indices": [2, 5],
      "supporting_relations": ["fan_out", "new_port"]
    }
  ],
  "evidence_sufficient": false,
  "confidence": 0.0
}
```

Unknown不强制输出唯一高置信Technique。候选证据必须存在于输入Episode；`confidence`是待校准分数，不直接解释为真实概率。

## 7. Stage A：流量结构自监督后训练

Stage A只使用CasinoLimit正式训练实例和UWF-2024正式训练划分中允许使用的无标签Episode，不使用CasinoLimit Validation/Internal Test、final held-out Technique、UWF-2025家族、CAM-LDS、TQH-C2、Data24/Fall24未去重部分或其他冻结外测。Data22只允许出现在独立历史预训练消融中。Stage A学习Flow模态和跨Flow结构，不直接学习ATT&CK标签。

首版只保留2-3项：

1. **Masked Flow Attribute Reconstruction：**恢复protocol、port class、packet/byte bin、connection state、relation token和可用字段；
2. **Flow Relation Prediction：**判断same source、same destination、repeated pair、fan-out、fan-in、new port、sequence order和continuous behavior；
3. **Next Behavior Pattern Prediction（可选）：**预测下一Flow的离散行为模式，而非精确连续值。

负样本只能在正式训练划分内构造，不得通过文件名、年份、来源或明显Schema差异完成任务。若自监督只降低自身损失而不改善Unknown、候选或few-shot指标，则停止扩大训练。

## 8. Stage B：父Technique层次监督与Flow证据原型

### 8.1 层次监督目标

Stage B同时优化：

1. 父Technique主分类；
2. Tactic辅助预测；
3. Episode embedding与正确Flow证据原型对齐；
4. 与错误或易混淆原型拉开；
5. evidence-flow grounding。

若一个mission包含多个Technique且Episode定位可靠，可采用层次多标签；若标签只能落到mission级，不伪造成单Flow标签。Sub-technique仅在Gate 0确认可行的少数父类内加入辅助细分。

### 8.2 Flow证据原型

每个父Technique原型至少包含：

```text
technique_id
technique_name
parent_technique
tactic_ids
flow_observable_behaviors
typical_entities
temporal_patterns
communication_relations
supporting_evidence
required_or_high_value_evidence
insufficient_evidence_conditions
non_flow_observable_aspects
confusable_techniques
negative_evidence
source_references
attack_version
```

正式零样本证据原型只使用冻结的公共知识：MITRE ATT&CK官方Technique/Sub-technique说明、Detection Strategies、Network Traffic Flow相关Data Components，以及与UWF最终测试实例无关且可由Flow验证的通用Procedure Examples。原型必须分开记录ATT&CK完整语义、Flow可观察证据和Flow不能证明的内容。

数据集的mission/instance/run说明只用于标签有效性审计、父Technique/Sub-technique解析、活动边界与Technique实施确认、Flow可观察性判断、Episode定位及评价后的错误分析。最终held-out Technique的零样本原型不得吸收其具体工具、IP、端口、服务、时间、环境或实施步骤，第一版不从CasinoLimit、UWF或CAM-LDS的实例说明生成原型。若后续提炼通用规则，只能使用Known训练角色，在held-out角色划分前以统一规则去除实例细节，并报告纯MITRE公共知识消融。

每个原型Manifest记录ATT&CK v19.1版本、知识快照时间、生成规则、来源列表、是否使用任何数据集信息、冻结时间及内容哈希/版本。final held-out、UWF-2025和CAM-LDS测试开始后不得更新知识快照或原型。

### 8.3 Hard negative

Hard negative包括同一Tactic中的相似父Technique、通信模式相近但攻击目标不同的Technique、相同端口但时序关系不同的Technique，以及宏观行为相似但证据充分性不同的Technique。模型不能只通过Technique名称或Tactic共现完成对齐。

### 8.4 创新假设

潜在创新不是普通ATT&CK文本Embedding，而是**Flow证据约束的Technique原型学习**：将行为一致的past-only Episode与网络可观察证据、必要证据、负证据和不可观察边界共同对齐。其有效性必须相对普通文本Embedding、无证据语义对齐和普通Prototype Network验证。

## SFT、DPO与RLAIF的训练分工

### SFT：基础且必做

SFT属于监督学习，使用固定输入与可核验标准答案，负责学习父Technique、Tactic、Known/Unknown训练代理任务、结构化输出、`supporting_flow`弱监督、`supporting_relation`弱监督和ATT&CK父子层级一致性。候选损失可组合生成式交叉熵、分类交叉熵、对比损失和证据定位损失；SFT不依赖在线探索或奖励，是后续偏好/RL分支的共同基础。

### DPO：优先的AI反馈偏好优化

DPO在冻结SFT checkpoint上使用chosen/rejected回答对，优先约束：谨慎拒识优于无证据强行分类；正确父Technique优于过度细分Sub-technique；真实Flow证据优于不存在或无关索引；合理Top-k优于Flow不可观察候选；承认证据不足优于虚构Payload、命令、文件或主机细节。DPO不需要独立奖励模型，通常不视为严格在线强化学习，是SFT之后的优先低成本对齐实验。

### RLAIF：有执行Gate的严格实验路线

RLAIF用于研究AI反馈能否改善evidence faithfulness、calibrated abstention、Flow不可观察推断控制、supporting flow/relation一致性、Top-k合理性和高置信错误。它不能替代有明确标签的Technique SFT。

奖励由两部分候选组成：

- **可验证规则奖励：**JSON与Technique ID合法、父子层级一致、supporting flow索引和relation真实存在、final held-out协议未破坏、不输出禁用字段、训练代理标签或Unknown结果正确；
- **AI评审奖励：**不超出Flow可观察范围，证据不足时适当拒识，解释由Episode支持，候选排序符合ATT&CK语义与Flow行为，不虚构Payload、命令、文件或主机证据。

只有同时满足下列条件，才进入PPO、GRPO或其他尚待选择的严格RL训练：

1. SFT基线稳定；
2. Episode构造与label unit审计通过；
3. AI评审rubric、模型版本和提示冻结；
4. AI评审与人工抽查达到预注册的一致性要求；
5. 奖励设计不使用冻结测试标签或实例说明；
6. 已具备SFT、SFT+DPO和rules-only奖励对照；
7. 实测资源与时间不超出当前预算边界。

Gate失败时保留SFT并完成DPO，将严格RLAIF记录为未执行或负结果，不为满足形式运行不可靠RL。正式比较至少规划`E-B01 SFT`、`E-B02 SFT+DPO`、`E-B03 SFT+rules-only RL`和`E-B04 SFT+RLAIF`；混合规则/AI奖励为Optional。除Macro-F1外，同时评价Unknown指标、高置信错误、ECE/Brier、Top-k/MRR、evidence sufficiency、supporting flow质量、hallucinated evidence rate、训练稳定性、时间和成本。

## 9. Task 0—3与少样本接入

### 9.1 Task 0：正常/攻击支撑检测

Task 0主要在具有可靠同源正常背景的UWF-2024内部训练和评价，并在UWF-2025冻结家族上评价时间变化。其作用是过滤明显正常Episode、验证基础检测能力并为Technique任务提供入口，不作为主要创新。不得用UWF Benign与CasinoLimit Attack直接拼成二分类；CasinoLimit只有在Gate 0确认存在可信同环境正常背景后，才开展来源内二分类。CAM-LDS无正常用户行为模拟，不用于该任务主结果。

### 9.2 Task 1：已知父Technique分类

在已确认攻击或可疑的Episode上预测K_core或K_union中的已知父Technique。K_core主结果按来源与总体分别报告；K_union中的单来源Technique不能被解释为跨来源泛化。比较单Flow、相同窗口LightGBM/XGBoost、普通Transformer、Base Qwen和完整模型。

### 9.3 Task 2：Unknown拒识与零样本ATT&CK候选

输入Episode后先判断其属于某个已知父Technique，或不属于任何已知父Technique。Unknown阶段比较max softmax、energy、Mahalanobis、Dirichlet evidence、prototype distance、RoNeTC和GCLC等方法，不要求立即识别Unknown身份。

对已判定为Unknown的Episode，使用冻结的ATT&CK官方文本和Flow证据原型，在**经审计确认可由网络Flow合理观察的候选池**内输出Top-k父Technique、证据充分性和候选分数。不在完整ATT&CK范围内无约束盲猜，也不强制输出唯一标签。

该任务是“未见标注Flow、允许读取公共Technique语义”的零样本候选归因，不等同于已经识别新Technique。主要指标为Top-1/3/5、MRR、evidence sufficiency和candidate calibration。

### 9.4 Task 3：新Technique少样本接入

获得经过确认的新Technique攻击样本后，更新Technique prototype，或更新轻量Adapter/LoRA，并在其他独立instance、mission或simulation run上测试。只有该阶段才称为few-shot adaptation。

一个shot原则上等于一个独立攻击活动单位：CasinoLimit使用独立challenge instance/攻击活动，UWF使用独立mission，CAM-LDS使用独立simulation run或scenario variant；不能等于随机一条Flow。Support和query/test不能来自同一单位。shot梯度由Gate 0按各Technique独立单位数决定，统一称为**zero-shot + data-dependent few-shot adaptation**。

基础模型开发期间，Final held-out Technique对Stage A、B、C、D、超参数、阈值、模型选择和方法选择完全不可见。模型、数据角色与评价协议冻结后，最终评价按固定顺序执行：

```text
先在预先指定的final query/test mission上完成zero-shot Unknown与Top-k候选并锁定结果
→ 再使用预先指定的support mission进行few-shot adaptation
→ 最后在剩余且独立的query/test mission上评价适配后模型
```

Support数量与选择规则须事先冻结，不得因结果不理想重新选择；support与query/test必须来自不同mission，query/test不得用于早停、checkpoint选择、原型修订或任何适配决策。

### 9.5 Stage C：Episodic Few-Shot Meta-Training

在已知父Technique中循环模拟“新类接入”：

```text
暂时把已知Technique A视为新类
→ 提供一个或若干support mission
→ 在A的其他独立mission上预测
→ 轮换至Technique B、C
```

模型学习如何利用Technique语义和support Episode建立新类表示。Stage C只使用Known父Technique模拟新类接入，Final held-out Technique不得出现在meta-training中。该训练只能学习“如何适配新类”，不能保证识别全部未见ATT&CK技术；其成立条件是新Technique可由Flow观察，并与已有行为原语存在可迁移关系。

### 9.6 Stage D：开放集与可靠性校准

从训练可用父Technique中留出validation pseudo-unknown，比较max probability、energy、Mahalanobis、Dirichlet evidence、prototype distance等，确定Unknown阈值、evidence sufficiency阈值、candidate output阈值和校准规则。Final held-out unknown、各Internal Test、UWF-2025和CAM-LDS不得参与阈值选择。

## 10. 数据划分与防泄漏

### 10.1 CasinoLimit划分

按challenge instance、participant/team和独立攻击活动分组，同一实例不得跨训练、验证和测试。需要检查同一参与者在多个实例中的关联、固定拓扑/IP/端口、攻击位置和玩家行为捷径。Final held-out Technique的support与query/test必须来自不同实例或独立攻击活动。

### 10.2 UWF划分与重叠

按week、mission、capture和连续时间块分组，相同周、mission、exact duplicate和高度相关记录不得跨split。Data24与Fall24-2的重叠周只能保留一个来源；UWF-2025家族在主协议中整体冻结。缩放、Episode参数、阈值和校准只能由训练年份的训练/验证数据拟合。

### 10.3 CAM-LDS划分

按simulation run、scenario和variant划分，同一运行不得同时进入support和query。若某Technique只存在于一个场景，不声称跨场景泛化。先报告zero-shot，再进行条件性few-shot；核心模型只读取NetFlow公共字段。

### 10.4 角色、Episode与变换隔离

父Technique角色包括Known training、validation pseudo-unknown、final held-out unknown、条件性few-shot support/query以及排除/背景分析。角色在查看最终结果前冻结；Final held-out不进入Stage A-D或模型/方法选择，validation pseudo-unknown只用于训练域开发。

每个数据源和split分别构造Episode，边界附近只能访问同集合、同允许活动边界且时间不晚于锚点的Flow。缩放、分箱、词表、缺失统计、关系阈值和校准参数只在允许的训练/验证数据上确定。UWF-2025、CAM-LDS和其他冻结外测不参与任何拟合。

### 10.5 来源捷径、去重与Manifest

exact duplicate与高度相关Episode不能跨split；source metadata保留在审计侧但不进入输入。使用source probe以及IP、绝对时间、instance/mission/run ID、participant、拓扑、捕获名、年份、精确端口和文件来源探针检查捷径。报告每个父Technique在各来源的Flow、Episode与独立实例/mission/run数，不以合并总量掩盖来源差异。

Manifest冻结数据哈希、数据版本、许可证、下载日期、v19.1迁移表、父子映射、K_core/K_union、数据角色、分组、标准化版本、Episode规则、ATT&CK知识快照、原型来源与哈希、随机种子和代码提交标识。任何外测结果不得反向修改这些内容。

## 11. 强基线与复现等级

| 类别 | 基线 | 作用 |
| --- | --- | --- |
| 表格单Flow | LightGBM / XGBoost | 普通闭集强基线 |
| 表格多Flow | LightGBM / XGBoost + 相同因果窗口统计 | 判断Episode学习是否超过人工聚合 |
| 序列 | 普通sequence Transformer | 判断Qwen与结构后训练是否必要 |
| 关系模型 | 简单GNN或Flow关系模型 | 比较显式图关系与Episode编码 |
| 文本大模型 | Base Qwen文本化Episode | 判断结构Adapter与后训练增益 |
| Adapter消融 | Qwen + 标准化Flow Adapter但无结构自监督 | 分离Adapter与Stage A |
| 普通原型 | Prototype Network | 比较无ATT&CK语义的few-shot |
| 文本相似 | ATT&CK文本Embedding与Episode embedding直接相似度 | 判断证据原型是否超过普通文本 |
| 开放分数 | max softmax、energy、Mahalanobis、Dirichlet/prototype distance | 基本Unknown基线 |
| 开放强基线 | RoNeTC | 比较多视图不确定性/证据式开放检测 |
| 开放世界强基线 | GCLC | 比较图对比、距离Unknown和新类更新 |
| OOD结构基线 | ETooL或可复现近邻方法 | 区别于已知类Non-IID/OOD结构后训练 |
| 完整方法 | Flow证据原型对齐的9B模型 | 主方法 |

每项需标注“完整复现”“方法思想复现”或“仅定性比较”。若代码、输入粒度或数据许可不支持严格复现，不得虚构数值对比。

## 12. 实验矩阵

### 12.1 Track A：CasinoLimit数据源内开放识别

在按challenge instance/participant/攻击活动隔离的CasinoLimit上，比较单Flow、LightGBM相同因果窗口、普通Transformer/关系模型、文本化Base Qwen、Adapter无Stage A和完整9B。评价独立实例间的Known父Technique、Unknown拒识、Top-k候选和data-dependent few-shot接入，并检查正常背景、固定拓扑、IP、端口和攻击位置捷径。

Unknown阶段比较max softmax、energy、Mahalanobis、Dirichlet/prototype distance及可复现的RoNeTC/GCLC；候选阶段比较普通ATT&CK文本Embedding、无证据语义对齐、普通Prototype和完整Flow证据原型。拒识与候选指标分开报告。

### 12.2 Track B：UWF近期企业Flow与时间迁移

在UWF-2024正式训练子集内部完成Task 0、可行的Task 1和强基线，再将模型、标准化、阈值、证据原型和标签映射全部冻结，测试UWF-2025家族中Known父Technique可靠交集及Task 0的时间变化。报告source performance、target performance、performance drop、校准、高置信错误和鲁棒性。

若UWF-2024某子集只能支持二分类或Tactic，不将其伪造成父Technique结果。Sum25-1/Sum25-2关系未确认前不做“一个调参、一个独立测试”。

### 12.3 Track C：CasinoLimit + UWF联合训练

固定公共字段、v19.1标签映射和相同评价协议，比较：

1. CasinoLimit-only；
2. UWF-2024-only；
3. naive pooled；
4. source-balanced pooled；
5. source-balanced pooled + source-adversarial/source-invariant约束（可选）；
6. K_core跨来源主结果；
7. K_union广覆盖结果；
8. leave-one-source-out或train-one-test-another。

至少实施source-balanced sampling和source probe。比较来源预测准确率、分来源分类结果、共享Technique表示和联合训练增益；若模型能轻易从表示恢复数据来源，或增益只来自单来源Technique与Schema绑定，不得解释为行为泛化。

### 12.4 Track D：CAM-LDS冻结跨数据集外测

在不使用CAM-LDS训练、Stage A-D、校准、阈值或模型选择的前提下，只使用NetFlow公共字段评价Flow可观察父Technique的zero-shot Unknown、Top-k候选、证据充分性、跨Schema/环境性能下降和条件性few-shot。Final held-out先完成并锁定zero-shot；support与query/test来自不同simulation run或scenario variant。

CAM-LDS没有正常用户模拟，不报告Task 0主结果；主机日志和告警仅作标签/可观察性人工核验。若某Technique只存在一个场景或NetFlow无法定位，则排除或降为案例分析。TQH-C2仅在主实验完成后作为加密C2专项Track。

### 12.5 few-shot、模型规模与可能结论

各Track按独立instance/mission/run构造support/query，比较普通增量训练、只更新原型、无语义few-shot、Stage C episodic方法和完整语义增强方法。shot梯度由Gate 0冻结；Final held-out必须先锁定zero-shot结果，再使用预定support适配，query/test不得用于早停、checkpoint或原型修改。

9B完成核心矩阵；27B仅在最佳方法和代表性Known、Unknown、zero-shot/few-shot条件下有限验证。结果同时报告性能、适配参数、支持活动数、训练时间和推理成本。

- **Unknown、候选和few-shot均改善：**支持“证据约束的开放识别与新类接入”完整贡献。
- **Unknown不优于强基线，但候选/few-shot改善：**贡献集中在拒识后的语义归因与接入。
- **候选改善但few-shot受mission限制：**形成证据原型研究，并明确数据边界。
- **仅已知类改善：**不足以支撑当前核心创新，应收缩为Flow结构后训练研究。
- **联合训练只学习来源：**不声称跨来源泛化，退回单源或K_core并重新设计平衡与输入。
- **各环节均无稳定优势：**报告Flow证据限制、强基线和失败分析，不继续Agent、TQH-C2或更大模型扩展。

## 13. 评价指标与统计

### 13.1 已知父Technique

- Macro-F1、Micro-F1、分类别Precision/Recall/F1、Balanced Accuracy和混淆矩阵；
- 层次/多标签任务使用macro/micro F1、mAP及父子一致性；
- 分别报告CasinoLimit、UWF-2024、K_core、K_union、UWF-2025和CAM-LDS结果；
- UWF-2024 source→UWF-2025 target及训练域→CAM-LDS的performance drop。

Task 0另行报告二分类指标，只在具有可靠同源正常背景的UWF内部形成主结果，不与Technique分类Macro-F1混合。

### 13.2 Known / Unknown

- AUROC、AUPR、Unknown F1、FPR@95TPR、OSCR；
- Known Macro-F1；
- ECE、Brier score、Risk-Coverage和高置信误归类率。

### 13.3 候选归因与few-shot

- Top-1、Top-3、Top-5、Mean Reciprocal Rank；
- evidence sufficiency准确性/一致性及candidate calibration；
- data-dependent shot下的性能、相对无语义基线提升、adaptation gain和样本效率；
- support/query均按独立mission统计，不按Flow行统计。

### 13.4 鲁棒性与成本

- 扰动前后绝对性能与performance drop；
- 训练时长、峰值显存、吞吐、P50/P95 Episode延迟、Token数和模型产物大小；
- 9B/27B效果-成本差异；
- source probe准确率、分来源性能差异与联合训练额外成本；
- API调用与实际费用，如使用。

### 13.5 统计可靠性

9B核心结果采用多个随机种子；资源不足时按mission或scenario做bootstrap置信区间。主要比较报告均值、标准差或95%置信区间，并在同一测试Episode上使用适当配对检验。27B有限验证和无法完全复现的基线应明确探索性或定性性质。

## 14. 鲁棒性、消融与错误分析

### 14.1 正式鲁棒性实验

扰动包括：

- 随机Flow丢失；
- Episode截断；
- IAT jitter；
- packet/byte统计扰动；
- 无害背景Flow插入；
- 部分字段缺失；
- 连接顺序轻微扰动；
- 不同Episode长度；
- 不同时间窗口。

扰动应保持基本网络语义合理，不能通过制造明显非法值来夸大性能下降。比较LightGBM窗口统计、普通Transformer、Base Qwen、完整模型、`w/o structural self-supervision`和`w/o evidence prototype`。

### 14.2 关键消融

1. 单Flow、人工窗口与原始Episode；
2. 标准化文本输入、Adapter无Stage A、完整Stage A；
3. 去除相对时间、实体关系或各类关系标记；
4. 去除missing/availability mask；
5. 精确端口、端口类别及无端口；
6. 各自监督任务与组合；
7. 普通ATT&CK文本、无证据语义和完整证据原型；
8. 无Stage C、普通Prototype Network和episodic meta-training；
9. 不同开放分数与校准策略；
10. CasinoLimit-only、UWF-2024-only、naive pooled与source-balanced pooled；
11. K_core与K_union、leave-one-source-out和source probe；
12. 不使用Data22与使用Data22结构预训练的历史消融；
13. Qwen 9B与有限27B规模对照。

### 14.3 错误类别

错误按输入不可观察、父子标签或v19.1迁移歧义、instance/mission/run与Episode定位不足、关系缺失、Known混淆、Unknown漏拒/过拒、候选原型误导、few-shot过拟合、Schema/来源捷径和时间漂移分类。所有案例引用真实Flow索引、关系与标签来源，不能用模型生成解释替代证据。

## 15. 实施顺序

| 阶段 | 工作 | 完成判据 |
| --- | --- | --- |
| 前4—7天 | metadata-first审计CasinoLimit、UWF-2024候选、Sum25家族和CAM-LDS；检查标签、公共字段、重叠、独立活动、许可证、Flow可观察性和v19.1迁移 | 多数据集审计表、选择性下载清单、Gate 0初判 |
| 第1—2周 | 冻结训练/外测角色、K_core/K_union、Known/pseudo/final、无泄漏划分和统一表示；完成Anchor-only、Single Flow、候选Episode与LightGBM窗口统计等输入基线 | 数据/标签/知识Manifest、Episode质量报告、输入消融基线与source probe |
| 第2—3周 | 完成CasinoLimit-only、UWF-2024-only、naive/source-balanced pooled首轮；运行Stage A与基础SFT，保存独立检查点并执行Gate 1 | 单源/联合训练首表、`checkpoint_StageA`、`checkpoint_StageA_B_SFT`与捷径报告 |
| 第3—4周 | 完成Stage C/D与DPO分支；评估SFT与DPO递进结果，执行RLAIF Gate；冻结final held-out zero-shot/few-shot协议 | Unknown—候选—接入链路、DPO检查点、RLAIF Gate记录与联合训练来源分析 |
| 第5—6周 | 完成UWF-2025冻结时间外测、CAM-LDS冻结外测、鲁棒性和条件性few-shot；仅在RLAIF Gate通过后运行有限严格RL对照 | 时间迁移、跨数据集、鲁棒性、条件性RLAIF与错误分析 |
| 第7—8周 | 完成多seed/分组bootstrap、模块遗忘与检查点谱系分析；Gate 4后有限验证27B；补齐成本、图表与全文 | 完整论文初稿、检查点/指标追踪表与复现清单 |

写作与实验同步：Gate 0完成即冻结数据章节；原型Schema冻结后撰写方法；实验前建立空结果表和统计协议。第一月不承诺完成全部论文级重复或27B矩阵。

## 16. 风险、失败分支与Gates

| Gate/风险 | 通过条件或风险信号 | 决策 |
| --- | --- | --- |
| Gate 0：多数据集选择、兼容性与可观察性 | CasinoLimit与至少一个UWF-2024子集可承担明确训练角色；重叠、公共字段、v19.1映射、Flow证据、独立活动、raw record与label unit可审计；候选anchor+past context Episode有明确锚点、边界和质量统计；可构造K_core或有解释力的K_union、Known/pseudo/final及至少一种few-shot | Episode审计失败则回退Anchor-only或Single Flow；数据/标签审计失败则不训练大规模Qwen，并缩小Technique子集、调整数据角色、退回Tactic级或放弃ATT&CK Technique主任务 |
| Gate 1：任务确有难度且无来源捷径 | held-out Technique使传统/序列基线退化，source probe及IP、时间、端口、instance/mission/run、participant、拓扑和版本探针不能解释主要结果 | 失败则重做划分与输入；若仍由来源决定，不报告行为泛化 |
| Gate 2：Episode与结构后训练有效 | 完整方法须在“Flow证据约束的Top-k候选归因”或“data-dependent few-shot接入”至少一个核心增量目标上，稳定优于Anchor-only、Single Flow、LightGBM相同窗口统计、普通Transformer、Base Qwen及对应普通Prototype/无语义few-shot；还须完成仅显著Flow、移除显著Flow、仅上下文与关系打乱等输入控制，排除收益只来自单条捷径Flow。同时Known Macro-F1、Unknown指标、ECE、高置信错误和成本不得出现不可接受退化。增益须由多seed或mission-aware bootstrap/置信区间支持，并通过IP、时间、端口、mission与版本捷径检查；仅提高普通闭集Known准确率不足以通过 | Episode无增益则回退Anchor-only/Single Flow；结构后训练无核心增益则停止语义扩展或Agent，收缩为边界研究 |
| Gate 3：证据原型有效 | 相比文本Embedding、无证据对齐和普通Prototype，在Top-k、MRR、few-shot或证据充分性上稳定增益 | 失败则ATT&CK仅作标签/解释，不作为核心贡献 |
| Gate 4：模型规模与扩展 | 9B方法成立且资源允许 | 才测试27B，并决定Agent、TQH-C2或其他扩展 |
| Gate R：RLAIF严格RL可行性 | SFT与DPO基线稳定；规则奖励可确定复算；AI Judge与人工抽查具有足够一致性；奖励黑客、长度偏置和标签泄漏受控；冻结测试集不进入奖励、策略更新或模型选择；预算足以完成至少一个固定协议和重复 | 未通过则停止RLAIF，保留SFT+DPO为正式偏好优化结果，不将DPO表述为完整RLHF |
| Flow可观察父Technique过少 | high/medium类别或独立mission不足 | 退回Tactic级、缩小技术子任务或重新选择主问题，不强行实验 |
| UWF重叠或时间标签不兼容 | Data24/Fall24或Sum25家族关系不清，Known可靠交集过小 | 冲突部分不入训练；整个家族冻结或只选标签质量更高者测试 |
| CasinoLimit来源捷径 | 共享挑战/拓扑使source或instance信息主导 | 强化分组与消融；必要时缩小为来源内开放识别，不宣称跨环境泛化 |
| CAM-LDS可观察类别过少 | 名义Technique主要依赖主机日志或运行不足 | 缩小外测子集、只做候选/案例分析，不使用系统日志补足核心输入 |
| 27B资源不足 | 无法完成代表性配置 | 保留9B完整结论；27B不是论文成立条件 |
| 基线无法直接复现 | 输入、代码、数据许可不兼容 | 标注方法思想复现或定性比较，不伪造严格对比 |

最低可行版本保留多数据集Gate 0、CasinoLimit与一个审计合格UWF-2024训练来源、统一表示、审计通过的anchor+past context Episode及其输入消融、9B Stage A-D、基础SFT与DPO递进对照、单源与source-balanced联合训练、source probe、一个final unknown协议、Top-k候选、至少一种few-shot、UWF-2025时间外测和CAM-LDS可行子集外测。RLAIF仅在Gate R通过后进入；优先取消Sub-technique、source-adversarial、TQH-C2、Data22预训练、27B、复杂图完整复刻和Agent。

## 17. 资源与预算

### 17.1 9B主实验

首选RTX 5090 32GB单卡，以4-bit QLoRA、BF16、梯度检查点和梯度累积完成9B训练。正式租用前以少量Episode测量32/64 Flow长度的显存、吞吐、Stage A-D单步时长和推理延迟。资源不足时依次缩短Episode、降低batch、减少自监督任务、减少训练样本和重复次数，但不取消无泄漏划分与强基线。

### 17.2 27B有限验证

27B只在Gate 4后使用最佳配置验证代表性Known、Unknown和few-shot条件。是否采用单卡量化推理、参数高效训练或额外高显存租赁，依据9B结果和届时报价决定；当前不预设完整27B训练，也不把其费用提前并入整月主预算。

### 17.3 费用

| 项目 | 暂定预算 | 用途 |
| --- | ---: | --- |
| RTX 5090 32GB GPU服务器 | 约2000元/月 | 9B Stage A-D、主实验、多seed与鲁棒性 |
| DeepSeek API及必要云端辅助 | 约600元 | ATT&CK原型整理、困难样本检查和可选Teacher；不逐Episode分类 |
| 合计 | 约2600元 | 计划值，按实际时长与调用记录 |

## 18. 直接参考工作与方案边界

| 工作 | 已解决的问题 | 本研究如何借鉴 | 必须与其区分的边界 |
| --- | --- | --- | --- |
| [Evaluating LLMs for Flow-Based Intrusion Detection](https://doi.org/10.1007/s10462-025-11432-2) | 在结构化Zeek Flow上比较小型LLM、传统ML和深度模型，显示普通闭集任务中树模型仍强且吞吐占优 | 保留强LightGBM/XGBoost与效果-成本评价 | 不以普通IID闭集超过树模型作为主要价值证明 |
| [A Systematic Comparison of LLMs for Network Intrusion Detection](https://doi.org/10.1145/3696379) | 比较不同LLM及Prompt/RAG/微调与传统方法 | 借鉴公平模型比较和成本口径 | 本文重点是未见父Technique后的拒识、候选和接入，不是再做一轮Prompt比较 |
| [DoLLM](https://arxiv.org/abs/2405.07638) | 使用多Flow顺序与Flow Tokenizer检测Carpet Bombing DDoS | 作为多Flow LLM和Tokenizer近邻基线 | 多Flow输入本身不新；本文不只换Qwen重做DDoS，而研究多父Technique开放识别和ATT&CK归因 |
| [Large Language Models powered Malicious Traffic Detection](https://arxiv.org/abs/2503.18487) | 概括LLM作为Classifier、Encoder、Predictor，并以多Flow案例说明潜力 | 借鉴把LLM作为结构编码器及成本/泛化讨论 | 架构综述和单攻击案例尚不能回答证据化Unknown候选及mission级few-shot |
| [ETooL](https://arxiv.org/abs/2505.20866) | 研究流量关系结构、自监督指令调优和Non-IID/OOD分类 | 借鉴结构后训练与OOD强基线 | 结构自监督和已知类OOD本身不新；本文研究训练未见父Technique的拒识、语义候选与新类接入 |
| [MET-LLM](https://doi.org/10.1016/j.eswa.2025.130621) | 使用流量领域Tokenizer、Header/Payload、安全语料预训练及参数高效适配，并研究约100-1000条新类样本下的快速适配 | 借鉴Tokenizer/PEFT和鲁棒性设计 | Tokenizer和LoRA不构成创新；本文Flow-only，以独立mission为shot，研究更低样本和ATT&CK Flow证据约束 |
| [RoNeTC](https://doi.org/10.1109/TIFS.2025.3544067) | 通过Dirichlet证据和多视图不确定性实现可靠Known/Unknown分类 | 作为强开放集基线，避免只比较最大概率阈值 | Unknown检测不是主要创新；本文新增目标在拒识后的候选归因和few-shot接入 |
| [GCLC](https://doi.org/10.1109/TIFS.2026.3705313) | 使用交互图、图增强、对比聚类、Mahalanobis Unknown检测及新类更新 | 作为图结构、Unknown与更新强基线 | Unknown聚类和增量更新本身不新；本文必须证明ATT&CK证据候选和mission级few-shot的额外价值 |
| [NetLLM](https://arxiv.org/abs/2402.02338) | 以网络数据编码器、LLM主干、任务头和参数高效适配处理网络任务 | 借鉴模块化Adapter—LLM设计 | 其主要任务不是ATT&CK恶意Flow开放识别 |
| [NetVigil](https://www.usenix.org/conference/nsdi24/presentation/hsieh) | 利用流量交互图和对比学习进行鲁棒、低成本异常检测 | 借鉴关系模型基线、鲁棒和成本评价 | 本文验证局部past-only关系Episode，并进一步评价父Technique语义候选 |
| CasinoLimit，RAID 2025，DOI `10.1109/RAID67961.2025.00039`；数据集DOI `10.5281/zenodo.17256954` | 提供BreizhCTF 2024独立挑战实例、Zeek日志和ATT&CK标签 | 第一主训练来源，支持来源内开放识别与少样本接入 | 共享挑战/拓扑、标签传播、正常背景和Flow可观察类别仍需Gate 0核验 |
| [UWF-ZeekData24](https://doi.org/10.3390/data10050059)及近期UWF系列 | 提供与ATT&CK关联的企业Zeek数据 | 审计后构成UWF-2024训练池与UWF-2025冻结时间外测 | Data24/Fall24与Sum25家族重叠关系不能预设；不得重复使用相同周或记录 |
| CAM-LDS，arXiv `2603.04186`；数据集DOI `10.5281/zenodo.18390561` | 提供多场景、多运行的NetFlow、系统日志与安全告警及ATT&CK标签 | 只取NetFlow公共字段进行2026冻结跨数据集外测 | 名义81个Technique不等于Flow可观察类别；无正常用户模拟，系统日志不进核心模型 |
| TQH-C2，数据集DOI `10.5281/zenodo.21435571` | 提供跨TLS、QUIC和HTTP的加密C2专项流量 | 主实验完成后的可选鲁棒性外测 | 不作为主训练来源，也不扩大通用Technique标签空间 |
| MITRE ATT&CK官方：[Network Traffic Flow](https://attack.mitre.org/datacomponents/DC0078/)、[Network Traffic Content](https://attack.mitre.org/datacomponents/DC0085/)与[Detection Strategies](https://attack.mitre.org/detectionstrategies/) | 区分Flow元数据、网络内容和检测语义 | 构建Flow证据原型、不可观察边界和冻结知识快照 | ATT&CK文本不是样本标签，不能证明当前Episode发生某Technique |
| 侯剑等：《加密恶意流量检测及对抗综述》，软件学报，2024，35(1):333-355，DOI:10.13328/j.cnki.jos.006891 | 综述主动/被动加密恶意流量检测、侧信道/明文/原始流量特征及混淆、干扰学习和隐藏信息等对抗风险 | 支持Flow/侧信道检测在Payload不可见条件下的必要性，并据此加入输入扰动与鲁棒性实验 | 该综述不直接证明本文模型有效；仅用于界定加密、混淆和对抗背景 |

最接近工作的共同结论是：多Flow、Tokenizer、自监督、OOD、Unknown和新类更新均已有先例。本文必须验证的不是模块组合，而是：**Flow可观察证据原型能否把Unknown拒识、ATT&CK Top-k候选和基于独立mission的少样本接入连接起来，并在强开放集与无语义few-shot基线上产生可复验增益。**

## 19. Open Questions

以下事项集中标为`TBD after Gate 0`或`Provisional`，不得在代码中先行固化为未经记录的正式决定：

1. CasinoLimit的精确label unit及Flow级证据标签是否存在；
2. UWF mission、攻击步骤、时间区间与Flow标签的对应关系；
3. 各来源Episode锚点如何确定，以及无明确锚点样本如何处理；
4. Episode最大长度、past-only时间范围、关系阈值和截断规则；
5. Qwen输入使用软Token、结构化文本还是二者对照；
6. Episode Encoder是否必要，还是普通Transformer/聚合统计已足够；
7. LoRA目标层、rank、学习率及Flow前端冻结策略；
8. Stage A是否对核心Top-k或few-shot产生稳定增益；
9. RLAIF采用PPO、GRPO或其他算法，AI Judge模型与rubric如何选择；
10. AI Judge与人工抽查的一致性阈值；
11. K_core、K_union、Known、pseudo-unknown和final held-out的最终类别；
12. 不同数据集的公共字段、缺失策略及source shortcut风险；
13. UWF-2024训练池、UWF-2025家族与Data24/Fall24/Sum25重叠关系；
14. CAM-LDS外测可用Technique数与support/query运行数量；
15. TQH-C2、Data22预训练消融和27B验证是否进入最终范围。

上述事项只能由Gate 0、小样本审计和训练域验证协议冻结，不能根据Internal Test、UWF-2025或CAM-LDS结果反向修改。

## Agent Execution Specification

### Data Permission Matrix

`Y`表示正式允许，`C`表示满足行内条件后允许，`N`表示禁止，`O`表示仅独立Optional实验。所有训练权限均进一步受Known/pseudo/final角色和split约束。

| 数据 | Stage A | SFT | Meta-training | DPO | RLAIF reward/design | Calibration | Validation | Internal test | Temporal test | External test | Few-shot support | Few-shot query |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CasinoLimit train roles | Y | Y | Y，仅Known | C，仅训练角色偏好对 | C，仅训练角色且通过RLAIF Gate | C，训练域validation | Y | N | N | N | C，预划support | C，冻结独立query |
| CasinoLimit Internal Test | N | N | N | N | N | N | N | Y | N | N | N | N |
| UWF-2024 train roles | Y | C，标签/锚点合格 | C，仅Known且独立mission足够 | C，仅训练角色 | C，仅训练角色且通过Gate | C，训练域validation | Y | N | N | N | C，预划support | C，冻结独立query |
| UWF-2024 Internal Test | N | N | N | N | N | N | N | Y | N | N | N | N |
| UWF-2025 family | N | N | N | N | N | N | N | N | Y | N | N | N |
| CAM-LDS 2026 | N | N | N | N | N | N | N | N | N | Y | C，zero-shot锁定后且独立run | C，与support不同run |
| TQH-C2 | N | N | N | N | N | N | N | N | N | O | N | O，按专项协议 |
| UWF-ZeekData22 | O，仅历史预训练消融 | N | N | N | N | N | N | O，历史对照 | O，漂移分析 | N | N | N |
| NF-v3/主机日志型数据 | N | N | N | N | N | N | N | N | N | N | N | N |

冻结外测的标签、实例说明、系统日志或人工错误分析不得进入DPO偏好构造、AI Judge rubric、奖励函数、阈值、Prompt或原型修订。

### Stage Input/Output Contract

| 阶段 | 输入 | 输出 | 允许更新 | 必须冻结 | 质量门槛 | 失败分支 |
| --- | --- | --- | --- | --- | --- | --- |
| Gate 0 | 官方元数据、标签、少量Flow、目录/校验和 | 数据/标签/权限Manifest、label unit与Episode可行性报告 | 审计记录 | 外测角色不得因预览标签改变 | 重叠、可观察性、独立活动和锚点可审计 | 缩小标签/数据角色或停止大模型训练 |
| Split & Sample Build | 冻结分组表、raw records、label units | split清单、anchor-context-relation样本与质量统计 | 构造参数仅用训练域验证 | split、test和final held-out角色 | 先split后Episode，无跨边界与未来信息 | 回退Anchor-only/Single Flow或排除ambiguous |
| Stage A | 允许的训练Flow/Episode | `checkpoint_StageA` | Flow/Episode前端与Stage A LoRA分支 | Base Qwen、所有外测/测试数据 | 自监督外还需改善下游或通过预注册继续条件 | 停止Stage A，保留无自监督基线 |
| Stage B / SFT | Stage A checkpoint、Known监督样本、公共ATT&CK原型 | `checkpoint_StageA_B_SFT` | LoRA、前端、任务/证据头（按配置） | Base Qwen、final held-out和外测 | Known、结构输出、证据定位与层级一致性稳定 | 简化损失/输入，保留强基线 |
| Stage C | SFT checkpoint、Known内episodic任务 | `checkpoint_StageA_B_C` | Stage C分支允许参数 | Base Qwen、Final held-out | 跨独立活动few-shot优于无语义基线且无严重遗忘 | 停止meta-training，保留普通Prototype/增量训练 |
| Stage D | 冻结模型、训练域validation pseudo-unknown | 温度、阈值、校准与候选规则 | 通常只更新校准artifact | 模型参数、final held-out、Internal/外测 | 校准与Unknown指标无不可接受退化 | 回退简单分数/验证集规则 |
| DPO | 冻结SFT checkpoint、训练角色chosen/rejected | `checkpoint_SFT_DPO` | 独立DPO LoRA/分支 | SFT checkpoint、所有测试角色 | 可信性改善且分类/校准无严重退化 | 保留SFT，记录DPO负结果 |
| RLAIF | 冻结SFT checkpoint、训练角色奖励数据、冻结Judge/rubric | `checkpoint_SFT_RLAIF`及奖励日志 | 独立RL分支 | SFT、测试标签、Judge/rubric与奖励版本 | RLAIF Gate全部通过、训练稳定且预算允许 | 不执行严格RL；保留SFT/DPO/rules-only |
| Final Evaluation | 冻结模型/协议与各测试域 | 只读预测、指标、trace与成本报告 | 不允许更新模型/阈值/原型 | 全部训练artifact | zero-shot先锁定，few-shot严格按预注册support/query | 报告不可评估或协议失败，不回流调参 |

### Experiment Registry

| ID | 实验 | 回答的问题 |
| --- | --- | --- |
| E-A01 | Anchor-only | 锚点Flow是否已经解释大部分性能 |
| E-A02 | Aggregate-window | 普通past-only窗口统计是否足够 |
| E-A03 | Relation-constrained Episode | 行为关系与顺序是否产生独立增益 |
| E-A04 | Random/Shuffled/Removed Context | 模型是否真实使用上下文与顺序 |
| E-A05 | Salient-flow removal / Evidence-only | 模型是否只依赖最显著Flow及证据子集是否充分 |
| E-B01 | SFT | 明确标签与证据监督的基础能力 |
| E-B02 | SFT + DPO | 低成本偏好优化是否改善拒识和证据忠实性 |
| E-B03 | SFT + rules-only RL | 可验证规则奖励的增量价值 |
| E-B04 | SFT + RLAIF | AI反馈严格RL是否值得其风险与成本 |
| E-C01 | Source-balanced pooling | 联合训练是否超过naive pooling且不依赖来源 |
| E-C02 | Source probe / leave-one-source-out | 表示是否编码数据源捷径 |
| E-D01 | UWF-2025 temporal | 时间迁移、校准与鲁棒性下降 |
| E-D02 | CAM-LDS external | 跨组织、环境和Schema的冻结外测 |

Agent执行实验时必须引用稳定ID、对应Manifest和Decision Status，不得自行改变数据权限、final held-out角色或正式评价顺序。

## Material Deviation and Decision Log

会改变研究含义、实验可比性、数据权限或论文结论的偏离必须与代码修改在同一PR或commit中记录；普通重构、日志增强、变量重命名、单元测试修复、路径兼容和不改变协议的性能优化不要求更新本规范。

| Date | Change ID | Status | Previous Decision | New Decision | Reason | Evidence or Experiment | Affected Data | Affected Stages | Affected Metrics | Compatibility Impact | Updated Files | Approved/Confirmed By |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-08-02 | DEC-0001 | Confirmed/Provisional mixed，见Decision Status | 多Flow Episode与阶段训练边界描述较粗；SFT/DPO/RLAIF分工未形成执行规范 | detailed提升为canonical specification；Episode改为待验证的anchor+past context假设；SFT为基础，DPO优先，RLAIF设Gate；基础权重冻结不等于无遗忘 | 将已讨论清楚的研究原则转为可执行、可审计规范 | 尚无实验结果；依据当前研究设计审查 | 全部候选数据角色与sample协议 | Gate 0、Stage A-D、SFT/DPO/RLAIF、Final Evaluation | Episode、Known/Unknown、Top-k、evidence、校准与成本 | timeline/brief/README需同步；后续重大偏离必须登记 | detailed、timeline、brief、README | Not recorded |
