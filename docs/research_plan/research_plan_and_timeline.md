# 面向网络Flow可观察ATT&CK父Technique的证据约束开放识别与少样本接入研究：计划与时间表

> Canonical repository path：`flow_security_agent/docs/research_plan/research_plan_and_timeline.md`。本文件是阶段控制与时间安排视图；唯一权威研究与实现规范为同目录下的`research_plan_detailed.md`，发生冲突时以detailed为准并同步修正本文件。

拟定英文题目：**Evidence-Grounded Open-Set Recognition and Few-Shot Onboarding of Flow-Observable ATT&CK Techniques**

## 1. 研究问题与目标

### 1.1 核心问题与研究边界

普通同分布、封闭类别的结构化Flow分类已经能够被LightGBM、XGBoost等传统模型较好处理。多Flow输入、流量Tokenizer、自监督训练和Unknown检测也分别已有研究。因此，本研究不以“LLM替代树模型”“多Flow本身”或“检测Unknown本身”作为创新主张，而聚焦：

> 在严格限定的网络Flow可观察ATT&CK父Technique子集中，能否通过统一标准化Flow表示、待验证的行为一致past-only多Flow Episode、结构后训练和Flow证据约束的ATT&CK语义对齐，使中型大模型可靠拒识监督训练阶段未见的Technique，给出有依据的ATT&CK候选，并在获得少量独立攻击实例、mission或运行后快速接入新Technique？

正式输入为Flow-only，不使用Payload、PCAP内容或主机日志作为核心模型输入。ATT&CK包含大量只能由进程、文件、注册表、账户和命令行等遥测确认的技术；数据集名义约67或81个Technique不等于Flow可用类别数，最终标签空间必须经过多数据集兼容性、标签质量、独立实例数量和Flow可观察性审计。

### 1.2 五个研究问题

| 研究问题 | 需要回答的内容 | 主要比较 |
| --- | --- | --- |
| RQ1：Flow行为表示 | anchor + past context的关系Episode能否比单Flow及人工窗口统计更有效地表达跨连接行为？ | Anchor-only、单Flow、固定窗口统计、无约束序列、关系约束Episode、随机/打乱/删除上下文 |
| RQ2：跨来源已知类 | 结构后训练后的Qwen能否识别跨来源核心父Technique，并在2025 UWF与CAM-LDS冻结外测中保持泛化？ | 单源、naive pooled、source-balanced pooled、Base Qwen、完整9B模型 |
| RQ3：Unknown拒识 | 面对监督训练阶段未见的父Technique，模型能否避免高置信误归入已知类？ | max softmax、energy、Mahalanobis、RoNeTC、GCLC等 |
| RQ4：语义候选归因 | 对已拒识Episode，Flow证据原型能否比普通ATT&CK文本Embedding更准确地排序Top-k候选？ | Top-1/3/5、MRR、证据充分性与候选校准 |
| RQ5：新Technique接入 | 获得少量独立攻击活动后，语义增强方法能否比普通增量训练和无语义few-shot更快接入新父Technique？ | 数据决定的shot梯度、跨实例/mission/run评价及适配成本 |

### 1.3 潜在贡献

当前潜在贡献均为待验证假设：

1. 构建严格区分“ATT&CK完整语义”“网络Flow可观察证据”和“Flow无法证明内容”的父Technique证据原型；
2. 计划验证anchor + past behavior-coherent context表示，并在有效时与证据原型对齐；
3. 建立区分核心跨来源集合与广覆盖并集、并连续评价Unknown拒识、Top-k候选和data-dependent few-shot接入的多数据源协议。

统一字段、Adapter、Tokenizer、QLoRA、多Flow输入、Unknown检测、ATT&CK文本RAG和Agent编排均不能单独构成创新。论文价值必须通过强基线、来源捷径检查、冻结时间/外部测试、鲁棒性和失败分支验证。

## 2. 核心技术路线

### 2.1 正式流程

```text
CasinoLimit + Gate 0审计后的UWF-2024 Train Pool
→ Multi-Dataset Selection, Compatibility and Observability Audit
→ Enterprise ATT&CK v19.1显式标签迁移
→ K_core核心跨来源集合 / K_union审计合格并集
→ 统一标准化Flow公共字段
→ 先按instance / mission / run划分数据
→ Anchor + past behavior-coherent context样本及Episode质量审计
→ Flow Adapter / Flow Tokenizer
→ Qwen3.5-9B
→ Stage A：训练来源内的流量结构自监督
→ Stage B / SFT：父Technique层次监督、结构化输出与Flow证据定位
→ Stage C：Known类内Episodic Few-Shot Meta-Training
→ Stage D：冻结模型后的开放集与可靠性校准
→ 从SFT checkpoint独立分支DPO与有Gate的RLAIF
→ Task 0正常/攻击支撑检测
→ Task 1已知父Technique分类
→ Task 2 Unknown拒识与Top-k ATT&CK候选
→ Task 3 data-dependent few-shot新Technique接入
→ UWF-2025冻结时间外测
→ CAM-LDS 2026冻结跨数据集外测
```

多Flow Episode是待审计和消融验证的建模假设，不是数据集原生标签单位。本项目所称“因果顺序”只表示past-only、行为关联和不使用未来信息，不声称严格因果发现。模型预测锚点Flow或攻击步骤的Technique，上下文只提供证据，不代表Episode中每条Flow都继承同一标签。

### 2.2 ATT&CK版本、标签集合与联合训练

所有数据标签映射到冻结的Enterprise ATT&CK v19.1，同时保留原始ID、原始版本、父子关系、原始Tactic、v19.1映射、映射理由、废弃/替换状态、Flow可观察性和映射版本。ATT&CK v19将旧Defense Evasion相关结构调整为Stealth与Defense Impairment，不能机械整体映射；父Technique/Sub-technique和revoked/deprecated ID需逐项核验。

- **K_core：**原则上要求同一父Technique出现在至少两个独立来源或环境，在各来源均有足够独立实例、mission或运行，标签可定位到Episode、可由Flow合理观察且不依赖来源特有字段。用于最有说服力的主分类、跨来源泛化、source leave-one-out和证据原型评价。
- **K_union：**由CasinoLimit和UWF-2024训练池全部审计合格的Flow可观察父Technique组成。用于数据源内部分类、Unknown留类、稀有Technique少样本和广覆盖附加实验。单来源Technique不能作为跨数据集泛化证据，必须分来源报告。

多数据源不能简单按Flow行纵向拼接。联合训练只使用可靠公共字段，以availability/missing mask标记缺失；dataset name、source ID、目录、年份、原始IP和绝对时间与模型输入物理隔离。按独立实例或mission以及数据源和Technique平衡采样，至少比较naive pooling与source-balanced pooling，并使用source probe和leave-one-source-out检查模型是否学习来源而非攻击行为。

### 2.3 数据角色

| 数据 | 正式角色 | 关键限制 |
| --- | --- | --- |
| CasinoLimit | 第一主训练来源；Technique监督、Known/Unknown、候选、episodic few-shot、接入及来源内Internal Test | 114个实例共享挑战与拓扑；按instance、participant/team和攻击活动分组；名义覆盖、正常背景、每类独立实例和Flow证据均待Gate 0审计 |
| UWF-2024 Train Pool | 第二主训练来源；近期企业式Flow、正常背景候选、Technique监督候选、结构自监督及近期Internal Test | 主要候选为Fall24-2和Data24中2024年2—3月非重叠数据；Data24 2024年10—11月须先与Fall24-2做记录重叠审计 |
| UWF-2025 Temporal Holdout Family | 冻结时间外测；Known可靠交集、Task 0时间变化、校准与鲁棒性 | Sum25-1与Sum25-2在独立性证明前视为同一家族，均不进入训练、自监督、调参、阈值或原型修改 |
| CAM-LDS 2026 | 冻结跨组织、跨环境、跨Schema外部测试；zero-shot候选与条件性few-shot | 只使用NetFlow或统一公共字段；不使用系统日志、Wazuh或Suricata告警；无正常用户模拟，不用于Task 0主结果 |
| TQH-C2 2026 | 可选加密C2专项外测 | 仅在主实验完成且资源允许时开展，用于协议、beacon/jitter与逐Flow标签专项验证，不扩大通用Technique数量 |
| UWF-ZeekData22 | 历史域对照和可选结构预训练消融 | 不再是主训练集；不自动进入Stage A，比较使用与不使用Data22对2024/2025结果的影响 |
| NF-ToN-IoT-v3等 | 历史资产、相关工作或未来候选 | 缺少适合当前任务的可靠ATT&CK父Technique标签，不进入第一阶段正式训练与测试 |

UWF-2024的具体组成和UWF-2025的正式测试子集必须在Gate 0后冻结。若Fall24-2只能支持Tactic或二分类，可用于Task 0、训练划分内结构自监督和背景建模，但不得强行用于父Technique监督。Sum25-1与Sum25-2若证实独立，才可条件性地将较早者作为辅助训练/验证、较晚者作为时间外测；关系不明时整个家族继续冻结。

### 2.4 Sample与Episode可行性

Gate 0必须分别确认raw record、数据集label unit和模型sample。候选sample为`S_i=(a_i,C_i,R_i,y_i)`：`a_i`是有相对明确标签的锚点，`C_i`是其过去的行为相关Flow，`R_i`是关系，`y_i`是锚点或攻击步骤标签。先按instance/mission/week/capture/run完成split，再在各split内部生成Episode；不得跨活动、数据集或测试边界，也不得令窗口内所有Flow自动继承同一标签。

Technique按A类单Flow可观察、B类上下文增强、C类关系依赖、D类Flow证据不足分层。Episode质量需审计锚点覆盖、label purity、相关Flow比例、背景污染、上下文重复和跨Episode重叠，审计前均为TBD。正式对照包括Anchor-only、单Flow、固定窗口统计、无约束序列、关系约束past-only Episode、随机/打乱上下文、显著Flow删除、上下文删除和evidence-only。

### 2.5 Task 0—3与训练数据权限

- **Task 0：正常/攻击检测。**支撑任务，主要在具有可靠同源正常背景的近期UWF内部完成，并评价2024→2025时间迁移。不得用UWF Benign与CasinoLimit Attack拼成来源混淆的二分类。
- **Task 1：已知父Technique分类。**在攻击或可疑Episode条件下预测K_core或K_union中的已知父Technique。
- **Task 2：Unknown拒识与Top-k候选。**先判断未见父Technique，再在Flow可观察候选池内输出Top-k和证据充分性，不强制唯一标签。
- **Task 3：data-dependent few-shot接入。**基础模型和协议冻结后，使用预先划定的少量新类实例/mission更新原型或轻量参数，并在其他独立实例/mission/run上评价。

Stage A只允许使用CasinoLimit正式训练实例和UWF-2024正式训练划分中的Flow。CasinoLimit验证/Internal Test、final held-out Technique、UWF-2025、CAM-LDS、TQH-C2、未去重的Data24/Fall24以及Data22均不得进入；Data22仅可在独立历史预训练消融中使用。Stage B—D继续遵守final held-out完全不可见原则。

Final held-out Technique不得进入Stage A—D，也不得参与超参数、阈值、模型或方法选择。模型、数据角色和协议冻结后，先在不使用任何support的条件下完成zero-shot Unknown与Top-k候选并锁定结果，再使用预先冻结的support实例/mission进行适配，最后在不同实例、mission或run的query/test上评价。不得重新挑选support或使用query/test早停、选checkpoint和修改原型。

正式zero-shot证据原型只使用测试前冻结的MITRE ATT&CK公共知识。数据集说明仅用于标签、活动边界、Flow可观察性和Episode定位审计，不得向held-out原型提供具体工具、IP、端口、时间、环境或实施步骤。冻结ATT&CK版本、知识快照、来源、生成规则和原型哈希。

### 2.6 参数、Checkpoint与SFT/DPO/RLAIF

Qwen基础权重原则上冻结；LoRA、Flow字段/缺失Embedding、时间/关系Embedding、Episode Encoder、projector和任务/证据头是可训练候选。基础权重冻结不代表连续训练同一LoRA或前端不会遗忘。各阶段独立保存`Stage A`、`Stage A+B SFT`、`Stage A+B+C`和Stage D校准artifact；DPO与RLAIF从冻结SFT checkpoint分别建立分支，后阶段不得覆盖前阶段唯一结果。

SFT是必做的基础监督训练，学习明确父Technique/Tactic、结构化输出和证据定位。DPO使用chosen/rejected偏好对，优先改善谨慎拒识与证据忠实性，不描述为严格在线RL。RLAIF只在SFT稳定、Episode审计通过、Judge/rubric冻结且人工一致性可接受、奖励不使用测试标签、具备SFT/DPO/rules-only对照并满足预算时执行；否则保留SFT+DPO并记录严格RLAIF未执行或负结果。

### 2.7 下载与存储原则

采用`metadata-first, selective-download`：Gate 0先获取官方说明、datasheet、README、标签、Technique/Tactic统计、instance/mission/run元数据、少量Flow样本、目录与校验和，不预先下载全部数据。

- CasinoLimit优先`labelled_flows`和`flows_zeek`，不下载syslogs作为模型输入；
- UWF优先标签指标、mission元数据和所需conn Parquet周，不默认下载PCAP；
- CAM-LDS只提取NetFlow与标签，系统日志仅供人工核验；
- TQH-C2如启用，优先features、labels和Zeek日志，不下载大体积PCAP。

所有正式资产保存版本、下载日期、许可证和校验和。

## 3. 核心实验与Gates

### 3.1 四个实验Track

| Track | 核心比较 | 主要问题 |
| --- | --- | --- |
| A：CasinoLimit来源内开放识别 | 独立实例上的单Flow、窗口统计、序列模型、Base Qwen、完整9B；Known/Unknown、Top-k和few-shot | 广覆盖攻击Technique能否跨独立实例分类、拒识、归因和接入 |
| B：UWF近期企业Flow与时间迁移 | UWF-2024来源内Task 0/1；冻结模型在UWF-2025可靠Known交集上的性能、校准与鲁棒性下降 | 正常/攻击支撑任务和已知Technique能否承受时间与环境变化 |
| C：CasinoLimit + UWF联合训练 | CasinoLimit-only、UWF-2024-only、naive pooled、source-balanced pooled、可选source-invariant约束；K_core、K_union及leave-one-source-out | 联合训练是否提高行为覆盖而非学习来源捷径 |
| D：CAM-LDS冻结外测 | zero-shot Unknown、Top-k、证据充分性、跨Schema下降及条件性few-shot；只用NetFlow公共字段 | 方法能否迁移到独立组织、环境和Schema |

TQH-C2仅作为可选专项Track，评价TLS、QUIC、HTTP传输、beacon interval与jitter变化，不属于最低版本。四个Track共享强基线、Unknown/候选分离评价和final held-out的“先zero-shot、后few-shot”顺序。

### 3.2 Go/No-Go Gates

| Gate | 通过条件 | 失败分支 |
| --- | --- | --- |
| Gate 0：Multi-Dataset Selection, Compatibility and Observability Audit | CasinoLimit与至少一个UWF-2024子集具备明确raw record、可审计label unit、锚点/活动边界和Flow可观察父Technique；重叠、公共字段、v19.1映射、独立实例和外测角色可审计；能够先split后构造至少一种无泄漏sample、K_core或有解释力的K_union及Known/pseudo/final协议 | 不训练大规模Qwen；回退Anchor-only/Single Flow、缩小Technique子集、调整数据角色、退回Tactic级或放弃主任务 |
| Gate 1：任务确有难度且无来源捷径 | held-out Technique使强基线退化；source probe、IP、时间、端口、拓扑、participant、mission和版本探针不能解释主要结果 | 重做划分和输入；若仍由来源决定，不报告行为泛化 |
| Gate 2：多Flow与结构后训练建立有效基础 | 完整模型在Flow证据约束Top-k候选或data-dependent few-shot至少一个核心目标上稳定优于单Flow、相同窗口LightGBM、普通Transformer、Base Qwen及普通Prototype/无语义few-shot，同时Known、Unknown、ECE、高置信错误和成本无不可接受退化，多seed或分组置信区间支持增益 | 不继续证据语义、27B或Agent扩展；收缩为能力边界或重新设计Episode |
| Gate 3：ATT&CK证据原型有效 | 相比普通ATT&CK文本Embedding、无证据约束对齐和普通Prototype，在Top-k、MRR、few-shot或证据充分性上稳定增益 | ATT&CK降为标签/解释层，不作为核心方法贡献 |
| Gate 4：模型规模与扩展 | 9B核心方法成立且资源允许 | 才测试27B，并决定Agent、TQH-C2或其他扩展 |
| Gate R：严格RLAIF可执行 | SFT稳定；Episode审计通过；Judge/rubric冻结且与人工抽查一致；奖励不使用测试标签；已有SFT、DPO和rules-only对照；预算允许 | 不运行严格RL；保留SFT与DPO，将RLAIF标为未执行或负结果 |

## 4. 实施顺序、时间与预算

第一项正式工作是4—7天的多数据集元数据、小样本、标签、重叠和可观察性审计，不是批量下载或模型训练。论文级稳定结果预计需要6—8周。

| 阶段 | 主要工作 | 阶段产物 |
| --- | --- | --- |
| 前4—7天 | metadata-first审计CasinoLimit、UWF与CAM-LDS；确认raw record、label unit、锚点/活动边界、公共字段、重叠、Flow可观察性及ATT&CK迁移；先做split与Episode可行性设计 | 多数据集审计表、sample/Episode可行性报告、下载决策、Gate 0初判 |
| 第1—2周 | 冻结数据角色、K_core/K_union、Known/pseudo/final、无泄漏split、公共字段、候选sample规则与质量指标；完成Anchor/Single/Window/Episode强基线 | 数据/标签/sample/知识Manifest、输入对照、source probe |
| 第2—3周 | 完成Stage A与基础SFT，分别保存Stage A和Stage A+B SFT checkpoint；完成单源/联合训练与显著Flow/上下文反事实检查 | 基础SFT、阶段checkpoint、Episode价值和捷径首表 |
| 第3—4周 | 完成Stage C/D并冻结模型/阈值/协议；完成SFT+DPO；先做final zero-shot再做预注册few-shot；评估RLAIF Gate | Unknown—候选—接入链路、DPO结果、RLAIF Go/No-Go |
| 第5—6周 | 完成UWF-2025与CAM-LDS冻结外测、鲁棒性；若Gate R通过，开展rules-only和小规模RLAIF分支 | 时间/外部结果、SFT/DPO/RLAIF对照或未执行说明 |
| 第7—8周 | 多seed/分组bootstrap；若9B成立，有限27B；补齐遗忘、成本、图表和论文 | 完整初稿、复现实验清单、扩展决策 |

预算不因候选数据增加而自动调整，仍以单卡RTX 5090 32GB完成9B QLoRA和主实验为基础：

- RTX 5090 32GB GPU服务器租用1个月：约2000元
- DeepSeek API及必要云端辅助：约600元
- 合计：约2600元

## 5. 当前待确认事项

只保留四类会改变正式协议的问题：

1. **数据、标签与sample可行性：**CasinoLimit/UWF精确label unit、锚点和Flow证据；UWF重叠；CAM-LDS可用Technique；A—D可观察性分层；Episode质量与是否优于Anchor/Single Flow。
2. **标签与输入统一：**ATT&CK v19.1迁移、K_core/K_union、公共字段、missing mask、Episode长度/关系/截断、软Token或文本输入、Episode Encoder必要性和来源捷径。
3. **Known / Unknown / few-shot协议：**各Track的Known、pseudo/final held-out、候选池、shot梯度，以及按instance/mission/run的support/query划分。
4. **模型与训练分支：**LoRA目标层、Stage A增益、模块冻结/学习率、遗忘控制、DPO偏好数据、RLAIF算法/Judge一致性、27B与最终预算。

上述事项只能由Gate 0、小样本审计和训练域验证协议冻结，不能根据Internal Test、UWF-2025或CAM-LDS结果反向修改。

重大偏离必须在同一PR或commit中同步更新canonical detailed并说明原因、影响数据/阶段/指标和决策状态；必要时同步本时间表与brief。普通重构、日志增强、变量重命名、单元测试修复、路径兼容及不改变协议的性能优化通常不要求更新研究计划。
