# 面向网络Flow可观察ATT&CK技术的开放识别与少样本接入研究方案

## 1. 研究问题与目标

传统Flow分类通常假设训练和测试具有相同类别，只能在预设标签中选择。真实网络出现训练阶段未见的攻击技术时，封闭集模型容易将其高置信误判为某个已知类。研究因此关注三个连续问题：

1. 能否发现当前流量不属于任何已知ATT&CK Technique；
2. 能否依据多条Flow之间的时间、端点和通信关系，给出有证据支持的Top-k候选；
3. 获得少量独立新攻击活动后，能否快速接入该Technique。

输入严格限定为Flow-only，包括连接、协议、包数、字节数、持续时间、状态和时间关系等元数据，不使用Payload、PCAP内容或主机日志作为核心模型输入。ATT&CK中许多技术需要进程、文件、注册表、账户或命令行证据，无法由Flow单独确认。因此，研究对象不是完整ATT&CK，而是经过数据质量和可观察性审计后的父Technique子集。

一条Flow有时不足以判断扫描、周期通信或跨主机攻击行为，但多Flow也不能任意拼接。计划先确认数据集是否提供可信的instance、mission、攻击步骤或simulation run边界，再以有相对明确标签的锚点行为为预测对象，只加入发生在此前且与锚点相关的Flow作为上下文。这个Episode方案是待验证假设，不是已经成立的样本单位，也不表示上下文中每条Flow都属于同一Technique。

研究不以“大模型替代LightGBM”或普通闭集准确率提升为目标。LightGBM/XGBoost、普通序列模型和开放集方法仍是强基线；Qwen的价值需要体现在跨Flow关系、未知类候选归因和新Technique少样本接入上。

## 2. ATT&CK标签口径与多数据集审计

第一版以父Technique为主分类粒度。Tactic表示攻击目标，用于辅助监督；Sub-technique是更具体的实施方式，仅在Flow证据和独立攻击活动充足时细分；Procedure描述具体工具或活动，不作为正式分类标签。

不同数据集采用不同ATT&CK版本和标签粒度，所有标签计划统一映射到冻结的Enterprise ATT&CK v19.1，同时保留原始攻击ID、原始版本、父子关系、原始Tactic、v19.1映射、映射理由、废弃或替换状态以及Flow可观察性。v19将旧Defense Evasion相关结构调整为Stealth与Defense Impairment，不能整体机械映射；父Technique、Sub-technique和废弃ID需要逐项核验。

名义Technique数量不等于最终类别数。CasinoLimit名义约67个、CAM-LDS名义81个Technique，但其中部分标签来自主机行为或安全告警，未必能由网络Flow确认。每个数据集都必须区分：

```text
名义Technique覆盖
→ ATT&CK v19.1映射后的父Technique
→ Flow可观察父Technique
→ 标签可定位且独立实例充分的最终可用父Technique
```

第一项正式工作是4—7天的多数据集选择、兼容性与可观察性审计，而不是下载全部数据或训练模型。审计除数据版本、标签、Flow Schema、独立活动、重叠和许可证外，还要区分原始Flow记录、数据集实际标注单位和模型训练sample，检查能否先划分数据再构造无泄漏的锚点+过去上下文样本。审计前不预设最终类别数、Episode长度、Known/Unknown划分或shot数量。

## 3. 数据角色与选型

### 3.1 两类主训练来源

**CasinoLimit是第一主训练来源。**该数据来自BreizhCTF 2024攻防活动，公开资料描述其包含114个相同挑战的独立实例，并提供Zeek网络日志和已标注Flow。标签结合Shell会话分析、网络传播和专家复核，独立攻击实例较多，适合开展父Technique监督、Known/Unknown、候选归因、少样本训练与来源内Internal Test。

但114个实例共享挑战和网络拓扑，部分标签可能从主机行为传播到网络会话，每个Technique的独立实例数、实际Flow证据和可靠正常背景仍待审计。数据必须按challenge instance、participant/team和独立攻击活动划分，同一实例不能跨训练、验证和测试。

**UWF-2024 Train Pool是第二主训练来源。**它不是一个新数据集，而是审计后由近期UWF数据组成的训练池：

- UWF-ZeekDataFall24-2作为主要候选；
- UWF-ZeekData24中2024年2—3月的非重叠数据可作为辅助候选；
- Data24中2024年10—11月与Fall24-2存在相同周目录，必须先完成记录和时间重叠审计。

UWF-2024用于提供近期企业式Zeek Flow、可靠正常背景候选、不同于CasinoLimit的网络环境、父Technique监督候选、结构自监督和近期Internal Test。若某个UWF子集只能支持Tactic或正常/攻击二分类，则只承担相应任务，不能强行用于父Technique监督。

### 3.2 两类冻结外测

**UWF-2025 Temporal Holdout Family用于时间外测。**UWF-ZeekDataSum25-1和Sum25-2均为2025年数据，在证明二者不存在记录、时间或采集环境重叠前，统一视为一个冻结测试家族。两者不进入训练、结构自监督、阈值、证据原型和模型选择，主要评价2024训练后的Known父Technique可靠交集、正常/攻击检测、校准和鲁棒性变化；只有独立性审计通过后，才重新决定是否分设辅助验证与正式时间外测。

**CAM-LDS 2026用于独立外部测试。**它跨组织、环境和Schema，提供NetFlow以及多种系统日志与告警。核心实验只使用NetFlow或可转换为公共Flow字段的数据，不使用系统日志、Wazuh或Suricata告警补充模型证据。CAM-LDS没有正常用户行为模拟，因此不用于正常/攻击二分类主结果；只评价Flow可观察、标签可定位且有足够独立运行的父Technique。zero-shot必须先于任何CAM-LDS支持样本，few-shot的支持与测试来自不同模拟运行或场景变体。

TQH-C2 2026仅作为资源允许时的加密C2专项外测；UWF-ZeekData22降为历史域对照和可选结构预训练消融，不再是主训练集；NF-ToN-IoT-v3及以主机日志为主的数据不进入第一阶段正式方案。

## 4. 多来源训练与任务设计

多个数据源联合训练的目的在于扩大行为和环境覆盖，而不是把所有Flow行直接拼接。简单拼接可能使模型根据CasinoLimit格式、UWF字段、固定拓扑或背景差异识别数据来源，而不是学习攻击行为。

计划建立两个父Technique集合：

- **K_core核心集合：**原则上要求同一父Technique至少出现在两个独立来源或环境，在每个来源具有足够独立实例、mission或运行，能够由Flow观察、标签可定位且ATT&CK映射一致。它用于最重要的主分类、跨来源泛化、时间迁移和证据原型评价。
- **K_union扩展并集：**由CasinoLimit和UWF-2024中所有审计合格的Flow可观察父Technique组成，用于扩大类别覆盖、单来源已知分类、Unknown留类和稀有Technique少样本实验。单来源Technique不能作为跨数据集泛化证据，结果必须分来源报告。

联合训练先统一到ATT&CK v19.1和可靠公共Flow字段，用缺失/可用掩码记录字段差异。dataset name、source ID、目录、年份、原始IP和绝对时间不进入模型。采样按独立实例或mission进行，并同时平衡数据源和Technique，避免大型扫描活动以Flow数量压倒其他类别。

最低要求比较CasinoLimit-only、UWF-2024-only、直接合并、来源平衡合并四种训练方式，并使用来源探针（source probe）测试模型表示是否能够轻易预测数据来源；同时开展leave-one-source-out或train-one-test-another。复杂的来源对抗训练只作为可选扩展。若联合训练收益来自来源识别，不得解释为跨环境行为泛化。

正式任务分为：

| 任务 | 定位 |
| --- | --- |
| Task 0：正常/攻击检测 | 支撑任务，主要在具有可靠同源正常背景的UWF-2024内部训练，并在UWF-2025评价时间变化 |
| Task 1：已知父Technique分类 | 在攻击或可疑Episode上预测K_core或K_union中的已知父Technique |
| Task 2：Unknown拒识与Top-k候选 | 先判断未见类别，再在Flow可观察候选池中给出候选和证据充分性 |
| Task 3：少样本接入 | 模型冻结后，用少量独立新类活动更新原型或轻量参数，并在其他独立活动上评价 |

不得用UWF Benign和CasinoLimit Attack直接构造二分类，否则模型可能只学习数据来源。CasinoLimit只有在审计确认存在可信同环境正常背景后，才开展来源内正常/攻击实验。

## 5. 模型训练与未见Technique处理

核心流程为：

```text
CasinoLimit + UWF-2024训练池
→ ATT&CK v19.1映射与公共Flow表示
→ 先按instance / mission / run划分
→ 锚点行为 + 过去相关Flow及关系
→ Qwen3.5-9B结构后训练与基础SFT
→ SFT后的DPO，以及通过Gate后才开展的RLAIF
→ Known识别 / Unknown拒识
→ Flow证据约束的Top-k ATT&CK候选
→ 少量独立攻击活动支持的新Technique接入
→ UWF-2025时间外测与CAM-LDS外部测试
```

样本构造必须先按instance、mission、week、capture、scenario或simulation run划分训练、验证和测试，再在各集合内部加入past-only上下文。上下文需要通过共享端点、重复通信、端口扩展、扇入/扇出或周期性等关系筛选，固定时间窗口只作为基线；混有多个Technique且无法确定锚点的样本不强制压成单标签。

Technique按证据分为单Flow可观察、上下文增强、关系依赖和Flow证据不足四类。多Flow不强行用于所有类别，证据不足类不进入第一阶段父Technique监督。计划比较Anchor-only、单Flow、普通窗口统计、无约束Flow序列和关系约束Episode，并通过随机上下文、顺序打乱、删除显著Flow和删除全部上下文检查模型是否真正使用关系，而非只依赖最明显的一条Flow。

Stage A只使用CasinoLimit正式训练实例和UWF-2024正式训练划分，学习Flow字段、时间关系和跨Flow结构。CasinoLimit验证/Internal Test、final held-out Technique、UWF-2025、CAM-LDS、TQH-C2和未去重的UWF数据均不能进入。Data22只允许在单独历史预训练消融中使用。

基础SFT学习明确的父Technique、Tactic、结构化输出和supporting flow/relation。DPO在SFT后用偏好对优化谨慎拒识、证据忠实性和避免过度细分，不等同于严格在线强化学习。RLAIF是条件性实验，只在SFT稳定、Episode审计通过、AI评审规则冻结并与人工抽查一致、奖励不使用测试标签且成本允许时开展；它不替代SFT。

Qwen基础权重原则上冻结，但LoRA、Flow编码器和Episode编码器连续训练仍可能遗忘前序能力。Stage A、SFT、Stage C、DPO和RLAIF分别保存checkpoint或校准artifact，不用后阶段覆盖前阶段唯一结果；DPO与RLAIF从同一冻结SFT结果建立独立分支。

Stage C只在Known父Technique内部模拟少样本接入，Stage D通常冻结模型，只用训练域validation pseudo-unknown拟合阈值和校准参数。

Final held-out Technique在Stage A—D、超参数、阈值、模型和方法选择期间完全不可见。模型与协议冻结后，依次执行：

```text
不提供任何新类支持样本
→ 在预定query/test上锁定zero-shot Unknown与Top-k结果
→ 使用预先划定的少量support instance/mission/run进行适配
→ 在其他独立query/test上评价适配后的识别能力
```

support数量和选择规则提前冻结，不得因结果不理想重新挑选。一个shot代表独立攻击活动单位，而不是一条随机Flow。正式零样本原型只使用测试前冻结的MITRE ATT&CK公共知识；各数据集的任务说明只用于标签、活动边界、Flow可观察性和错误分析，不能将具体工具、IP、端口、时间或环境写入held-out原型。

## 6. 四个实验Track与评价

| Track | 数据与比较 | 回答的问题 |
| --- | --- | --- |
| A：CasinoLimit来源内开放识别 | 独立实例上的LightGBM窗口统计、普通Transformer、Base Qwen、完整9B；Known/Unknown、候选和few-shot | 广覆盖攻击Technique能否跨独立实例拒识、归因和接入 |
| B：UWF近期企业Flow与时间迁移 | UWF-2024内部Task 0/1；模型冻结后在UWF-2025可靠Known交集测试 | 正常/攻击与已知Technique能否承受时间、环境和校准变化 |
| C：CasinoLimit + UWF联合训练 | 单源、直接合并、来源平衡合并、可选来源不变约束；K_core/K_union、source probe和leave-one-source-out | 联合训练是否学习共享行为而非来源捷径 |
| D：CAM-LDS冻结外测 | 只用NetFlow公共字段进行zero-shot Unknown、Top-k、证据充分性和条件性few-shot | 方法能否迁移到独立组织、环境和Schema |

Unknown检测报告AUROC、AUPR、Unknown F1、FPR@95TPR、OSCR、Known Macro-F1和校准误差；候选归因报告Top-1/3/5、平均倒数排名、证据充分性和候选校准；few-shot同时报告支持活动数、跨活动性能、适配参数、时间和成本。Unknown拒识正确与候选归因正确分开计算。

鲁棒性实验包括Flow丢失、Episode截断、时间或包/字节统计扰动、背景Flow插入、字段缺失和窗口变化。K_core与K_union、各来源及各外测域分别报告，不用总体Macro-F1掩盖来源差异。

训练方法至少比较SFT、SFT+DPO、SFT+rules-only奖励和条件性SFT+RLAIF。除分类指标外，还评价高置信错误、校准、证据充分性、supporting flow质量、虚构证据率、训练稳定性、时间和成本；若RLAIF Gate失败，明确报告未执行而不运行不可靠RL。

## 7. 时间安排、模型规模与阶段门

Qwen3.5-9B承担完整训练、消融、多随机种子和鲁棒性实验；Qwen3.5-27B只在9B核心方法成立后验证少量最佳配置。模型变大不能补足Flow不可观察证据，27B不是方案成立条件。

| 时间 | 主要工作 |
| --- | --- |
| 前4—7天 | 审计raw record、label unit、锚点/活动边界、Flow可观察性、数据重叠和无泄漏Episode可行性 |
| 第1—2周 | 冻结数据角色、K_core/K_union、split和sample规则；完成Anchor、单Flow、窗口与关系Episode基线 |
| 第2—3周 | 完成Stage A与基础SFT并保存独立checkpoint；完成单源/联合训练和显著Flow/上下文反事实检查 |
| 第3—4周 | 完成Stage C/D和SFT+DPO；先进行final zero-shot再做few-shot；评估RLAIF Gate |
| 第5—6周 | 完成UWF-2025、CAM-LDS和鲁棒性；Gate通过时开展rules-only及小规模RLAIF |
| 第7—8周 | 多随机种子、遗忘与成本分析、有限27B验证、图表和论文初稿 |

Gate 0要求至少确认CasinoLimit和一个UWF-2024子集具有合法、可定位且Flow可观察的训练角色，并能够构造K_core或有解释力的K_union、Unknown及一种few-shot；失败时不得启动大规模Qwen训练。Gate 1检查真实开放难度和来源/IP/时间/拓扑捷径。

Gate 2要求完整模型在Top-k候选或data-dependent few-shot至少一个核心目标上稳定超过相同窗口LightGBM、普通Transformer、Base Qwen及普通Prototype/无语义few-shot，同时Known、Unknown、校准、高置信错误和成本无不可接受退化。Gate 3再专门判断Flow证据原型是否超过普通ATT&CK文本Embedding和普通Prototype。只有核心方法成立且资源允许，才开展27B、TQH-C2或Agent扩展。

## 8. 风险、预期贡献与预算

预期贡献是：构建区分ATT&CK完整语义、Flow可观察证据和不可观察边界的技术原型；验证跨来源、行为一致的past-only多Flow上下文能否与证据原型有效对齐；建立同时区分K_core/K_union、Unknown、候选归因和独立攻击活动少样本接入的多数据源评价协议。以上均需由实验验证。

主要风险包括：CasinoLimit共享挑战和拓扑形成捷径；UWF-2024子集标签或重叠关系不足以支持父Technique监督；Sum25家族无法证明独立；CAM-LDS名义Technique多数不能由NetFlow观察；K_core过小；正常背景不可靠；联合训练只学习数据来源。对应处理是缩小Technique子集、退回Tactic级、调整数据角色、只报告单源结果、将ATT&CK降为解释层，或放弃缺少证据的外测，不强行维持预设类别和实验。

数据获取采用“元数据优先、选择性下载”：CasinoLimit优先labelled flows和Zeek Flow；UWF优先标签指标、mission元数据和必要conn Parquet周；CAM-LDS只提取NetFlow与标签；TQH-C2如启用，优先features、labels和Zeek日志。核心实验不默认下载PCAP或主机日志，所有资产记录版本、下载日期、许可证和校验和。

- RTX 5090 32GB GPU服务器租用1个月：约2000元
- DeepSeek API及必要云端辅助：约600元
- 合计：约2600元
