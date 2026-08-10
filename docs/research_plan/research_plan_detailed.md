# 网络流量开放识别与自适应取证智能体研究计划（权威详细版）

> 文档状态：Canonical / Authoritative
>
> 冻结日期：2026-08-09
>
> 解释顺序：本文件高于执行时间表和导师简版；审计产生新证据但尚未写入Decision Log时，不自动改变研究方案。

## 0. 当前冻结方案概览

### 0.1 研究问题与正式主链路

本文研究：**后训练大语言模型能否直接理解会话级网络证据并完成已知攻击的细粒度/粗粒度分类，独立开放集评分层能否据其模型信号可靠识别Unknown；在单次证据不足时，受约束Agent能否按需扩展包序列、历史关联、应用层证据和安全知识，并在效果、风险与成本之间选择接受、重分类、拒识或新类接入。**

正式主链路冻结为：

```text
网络流量样本
→ 会话级混合表示
→ 后训练Qwen3.5-9B独立执行第一次分类
→ 输出fine/coarse候选、证据状态、supporting/missing evidence及可供开放集计算的模型信号
→ Frozen Unknown Scoring / Calibration
→ Agent判断接受、扩展证据、重新分类、拒识或接入新类
```

Qwen第一次就直接读取网络证据，是正式主分类模型，不再作为LightGBM/XGBoost的Reviewer。传统模型只承担基线、诊断与可选消融，不决定哪些样本才调用Qwen，也不向Qwen提供必需概率。正式Unknown评分由独立、冻结、可复现的open-set scoring/calibration层产生，具体算法可比较class/token logits、margin、entropy、energy、embedding/prototype distance或辅助open-set head，最终方案仍待实验确定；LLM自报confidence或unknown probability只作为待验证变量或消融，不能未经验证直接充当正式Unknown score。

### 0.2 当前数据角色

| 数据集/资产 | 当前角色 | 当前结论 |
| --- | --- | --- |
| Edge-IIoTset | **主数据集，带冻结限制使用** | 承担完整方法开发与主实验；Phase 2已确认会话、上下文、Unknown和sample-level few-shot可执行，但多数攻击类只有一个主要capture，主结论限定于控制直接捷径后的同采集环境 |
| IoT-23 | **第二数据集，已通过最终可行性验收（带限制）** | 官方日志、PCAP对齐、统一Adapter和独立scenario划分均已实测可行；Production已冻结原生coarse `Exploitation` U_final及1/5-shot support/query，承担原生标签体系下的scenario/capture外部验证 |
| CICIoMT2024、X-IIoTID | 历史候选与备选说明 | 保留既有审计材料，但不再作为当前立即执行主线；是否启用须由后续数据审查决定 |
| DataSense 2025、UWF、CICIoT2023等 | 历史候选或后续复现资源 | 既有审计结论继续有效，但不因已有报告自动进入新主线 |
| CasinoLimit | 历史连接研究/案例参考 | relation到Flow的唯一连接覆盖过低，不作为逐流量主监督数据 |
| NF-ToN-IoT-v3等既有资产 | 工程与数据工具参考 | 相关Adapter、审计和分组代码可复用，不自动决定正式数据角色 |

停止继续广泛搜索数据集，NF3、NF-ToN、CICIoT2023等不再重新提升为当前主线。IoT-23已通过最小官方数据验收；除非正式全量构建出现新的阻断性证据，否则不再选择第二数据集。此前双门槛审计仍是历史证据，其中“CICIoMT首选、X-IIoTID立即备用”的旧执行顺序由后续决定替代。

### 0.3 会话级混合表示

基础输入不再限定为单行Flow。当前冻结到“会话级混合表示”层级：双向会话的前N个包方向、包长度、包间时间、网络层/传输层协议、TCP flags等头部信息，以及会话持续时间、双向包数/字节数、包长/IAT统计和字段缺失声明。

包序列允许可变长度，保存上限暂定16包；第一次分类暂定使用前8包和会话摘要，Agent可请求第9至16包。完整Payload不作为默认输入；HTTP、DNS、MQTT等应用层字段及有限脱敏Payload由Agent在合法且可观测时按需请求。正式任务采用Qwen3.5-9B post-trained模型的文本模式、原生Tokenizer和固定Session Evidence Card序列化，冻结视觉编码器及多模态对齐模块，语言模型相关模块采用BF16 LoRA SFT；正式分类默认使用non-thinking/direct-response。QLoRA仅在显存不足、框架兼容性问题或量化消融时作为降级/备用路线，thinking模式、专用Tokenizer与大规模领域继续预训练仅为可选扩展。

### 0.4 Unknown与新类生命周期

每个正式数据集保留原生coarse/fine标签，并在训练前独立冻结：

```text
K_known：基础训练和SFT可见
U_dev：不得作为主分类模型监督标签进入SFT，只用于Unknown算法、阈值/校准、证据扩展与策略开发
U_final：最终评测前完全隔离

Qwen已知类分类 + Frozen Unknown Scoring / Calibration（known-only知识）
→ 对已拒识样本进行full-frozen知识候选识别
→ 获得sample-level的1/5/10-shot support
→ REQUEST_LABEL / 建立新类记忆或轻量适配
→ REGISTER_NEW_CLASS
→ 在无相同记录和精确重复的query上评价新类与旧类遗忘
```

至少预注册Near、Far和Mixed三套Unknown组合并使用多个随机种子。`U_final`不得进入Qwen训练、SFT/DPO、Prompt示例、known-only RAG、Unknown算法选择、阈值开发、Agent/策略训练、错误驱动调参或人工挑选。sample-level few-shot不得声称为跨攻击run泛化。

### 0.5 Agent与当前Gate

Agent读取Qwen第一次分类的粗细类别、证据状态、supporting/missing evidence、可供open-set计算的模型信号、冻结Unknown评分结果和当前工具状态，再决定是否接受或追加证据。Agent是动态取证和决策层，不是“传统分类器决定是否调用Qwen”的路由器。

当前Agent主方案采用High-Capability LLM Supervisor读取Qwen Traffic Expert输出和Evidence State，并在deterministic Python Runtime约束下每轮选择一个合法动作。Supervisor不直接替代Qwen产生fine分类；Runtime负责Schema、capability、预算、最大轮数、去重、信息隔离、故障处理和Trace。初期Supervisor可使用DeepSeek高级在线模型，未来可由兼容本地高能力模型替换，具体model identifier仍未冻结。

Agent的基本闭环进一步明确为`Evidence State → 识别缺失证据 → 选择对应证据源/合法动作 → 更新状态 → 重分类或停止`。动态性来自根据当前证据缺口、可用能力和剩余预算选择下一步，而不是在Qwen不确定时无差别调用全部工具；这一细化不改变Qwen首次分类、独立Unknown层和Agent所在位置。

架构回溯、Edge-IIoTset Phase 2客观审查、双数据集最终可行性验收和Production Data Freeze已经完成。生产级`CanonicalSessionRecord`、两个Adapter、60秒会话构造、全量split、K/U、support/query、provenance guard、字段白名单与training manifest均已冻结并通过postfix审计（带已记录限制）。deterministic Runtime foundation及provider-neutral Traffic Expert/Supervisor backend preparation已经实现并通过synthetic/fake-provider工程审计；Production安全投影到Runtime `EvidenceItem`/`CapabilityStatus`的轻量adapter、真实provider/model、分类输出最终Schema、Unknown算法、SFT格式和Agent实验算法仍未完成或未冻结。Qwen训练和正式实验尚未开始。

## 1. 研究动机、核心假设与预期贡献

单行Flow统计压缩了包顺序和会话交互；传统表格模型虽能高效建立强基线，却不能代表LLM对序列化网络证据、缺失证据和动态取证的全部能力。若Qwen只接收传统分类器挑出的困难样本，论文评价的仍是一个树模型主导的选择性复核系统，无法公平回答领域后训练LLM能否独立承担网络流量分类。

核心假设为：

- H1：双向包序列与会话摘要能为Qwen提供比单行Flow更完整、仍可审计的行为证据；
- H2：领域SFT可使Qwen3.5-9B直接完成known fine/coarse分类、证据充分度与可供独立Unknown评分使用的稳定模型信号输出；
- H3：在第一次分类证据不足时，Agent按需扩展包、时间上下文、局部图、应用层证据或RAG，比固定取证流程获得更好的任务成功—成本—风险权衡；
- H4：严格隔离Unknown知识、候选归因与sample-level few-shot接入可以形成可审计的新类别生命周期。

预期贡献包括：

1. 构建以后训练Qwen为首次分类器的会话级网络流量开放识别框架；
2. 设计从基础会话证据到包、跨会话、应用层和知识证据的分层按需取证机制；
3. 构建由deterministic Runtime约束、High-Capability LLM Supervisor决策且具有显式状态、动作、预算、停止和轨迹记录的Adaptive Decision Agent，并与强Static、RulePolicy及可选可学习策略公平比较；
4. 建立同时评价Known分类、Unknown风险、新类接入、旧类遗忘、证据充分度、任务成功、恢复能力和计算成本的实验协议。

若分类、Unknown与动态任务均改善，可形成完整方法贡献；若分类基本不变但拒识、取证效率、恢复或成本改善，贡献集中于可信和自适应系统能力；若Agent无优势，则由强Static承担推荐流程，Agent作为适用边界分析。任何结论均须来自冻结数据与公平基线，不预设LLM或Agent一定有效。

## 2. 数据策略与数据Gate

### 2.1 原生标签与统一会话接口

不同数据集保留原生标签，不强制统一为ATT&CK。每个Adapter通过统一接口提供：

```text
DatasetLabelSchema
├─ dataset_name / version / sample_unit
├─ benign_label
├─ coarse_labels / fine_labels / parent_of
├─ label_description
├─ known_classes / dev_unknown_classes / final_unknown_classes
├─ session_or_capture_group（若可靠存在）
├─ support_pool / query_pool
└─ missing_fields / prohibited_model_fields
```

ATT&CK、CAPEC、协议说明和官方类别描述可作为知识来源，但映射本身不包装成论文创新。不同标签空间的绝对Macro-F1不直接混用。

两个数据集通过各自的Dataset Adapter输出统一`CanonicalSessionRecord`：

```text
CanonicalSessionRecord
├─ sample_id
├─ dataset_name
├─ scenario_or_capture_id
├─ split
├─ timestamp_start / timestamp_end
├─ packet_sequence[]
│  ├─ direction
│  ├─ packet_length
│  ├─ relative_iat
│  ├─ protocol
│  └─ tcp_flags
├─ session_summary
│  ├─ duration
│  ├─ bidirectional_packet_counts / bidirectional_byte_counts
│  ├─ packet_length_statistics / iat_statistics
│  ├─ handshake_state
│  └─ service_category
├─ temporal_context
├─ application_evidence
├─ label_schema_id
├─ fine_label / coarse_label
├─ capabilities / missing_fields
└─ prohibited_model_fields
```

`dataset_name`、`scenario_or_capture_id`、真实IP和绝对时间只用于后台审计、划分、会话重建和上下文索引，不直接进入模型。包序列可变长、保存上限暂定16包；首次分类暂定读取前8包和会话摘要，Agent可请求第9至16包。应用层证据和Payload不是必需字段；缺失能力必须通过`capabilities`和`missing_fields`显式声明，不得伪造。

### 2.2 双数据集职责与独立训练测试

**Edge-IIoTset承担完整方法开发与主实验。** 在其原生标签下运行Qwen独立闭集及coarse/fine分类、Near/Far/Mixed Unknown、传统模型强Unknown基线、传统模型Unknown后随机分配新标签的诊断、Agent动态扩展包/时间上下文/应用证据/RAG、1/5/10-shot新类接入、RulePolicy、强Static、High-Capability LLM Supervisor、可选LearnablePolicy以及成本、延迟、恢复和输出合法性评价。

Edge的使用限制同时冻结：多数攻击类别只有一个主要capture；不宣称跨攻击run泛化；随机包、随机记录或随机会话切分不能作为主结论；Known类采用capture内时间块、隔离gap和split内past-only上下文；Unknown类按完整类别隔离；sample-level few-shot不描述为跨run few-shot；外部泛化证据由IoT-23补充。

**IoT-23承担独立scenario/capture外部验证。** 它不作为“Edge模型不经适配的普通测试集”，而是在IoT-23原生标签体系下建立训练场景、验证场景和完全留出的测试场景，优先选择在多个独立scenario中重复出现的恶意软件家族或行为标签，执行scenario-held-out闭集验证、一套class-held-out Unknown和一套Agent时间/相关会话上下文增益实验；数据允许时增加1-shot或5-shot新类接入。最终Gate使用Capture-8与Honeypot-4训练、Capture-20/21验证、Capture-34与Somfy-01测试，并以Capture-42整体探测`unknown_final`；该最小预设证明流程可执行，但Capture-42只有6条FileDownload恶意流，不能直接充当正式Unknown主结果，正式manifest冻结前必须补足或明确小样本区间。

IoT-23允许使用独立LoRA、分类头、标签Token或`DatasetLabelSchema`适配。外部验证回答的是同一套数据接口、Qwen分类协议、Unknown生命周期和Agent决策方法能否在另一采集环境、另一原生标签体系和独立scenario划分上成立。两个数据集不物理拼接训练、不要求细类完全相同，也不直接比较不同标签空间的绝对Macro-F1。Edge到IoT-23的直接零样本迁移只作为未来可选的二分类或共同粗类实验，不进入最低主线。

### 2.3 Dataset Adapter、会话构造与泄漏控制

```text
EdgeAdapter:
PCAP及标签资料
→ 双向会话
→ 包序列、摘要、上下文和原生标签
→ CanonicalSessionRecord

IoT23Adapter:
官方PCAP + conn.log.labeled
→ 通过scenario、时间和通信标识对齐标签
→ 双向会话、包序列、摘要和上下文
→ CanonicalSessionRecord
```

两个Adapter可以采用不同的原始解析实现，但输出Schema、序列化协议、模型调用接口和评测接口保持一致。`Session Evidence Card`是`CanonicalSessionRecord`面向模型的安全投影，不包含后台审计和禁止模型使用的字段。

基础样本为双向会话。训练、验证、测试应先冻结分组与split，再分别在集合内部重建会话、包序列和跨会话上下文；不得跨split检索邻居或聚合历史。

跨会话关联只使用锚点之前的信息，可包括：past-only同源近期会话数、不同目的IP/端口数、同一目标的不同来源数、重复通信、未完成握手比例、会话间隔、周期性、总包数/总字节数和局部通信图摘要。原始IP只用于会话、关系查询和分组，绝对时间只用于排序、时间块和past-only检索；文件名、capture/scenario ID、数据集来源和攻击脚本编号不得输入模型。

原始端口需转换为服务类别或进行无端口消融。完整Payload不默认输入，固定URI、topic、用户名和明显攻击字符串不作为基础证据；应用层字段和有限脱敏Payload必须有字段白名单、缺失声明、隐私与可复现边界，并由Agent按需请求。所有归一化、编码、特征选择和校准只在训练集拟合；保存split manifest、源数据哈希、预测和随机种子。

### 2.4 数据Gate

启动SFT前至少冻结：Edge原生标签Schema、生产级会话重建规则、`CanonicalSessionRecord`、EdgeAdapter冒烟结果、包级/摘要字段白名单、split、K/U、support/query、known-only与full-frozen知识域、精确重复控制和直接泄漏检查。Edge主结论限定为同采集环境内、控制直接捷径后的方法效果。

IoT-23范围受限验收已完成：7个官方capture的Zeek标签可解析，PCAP与`conn.log.labeled`最低匹配率为81.54%，可构造训练、验证、完全留出测试和完整留出Unknown场景；IoT23Adapter与EdgeAdapter输出同一Schema。其通过结论带三项限制：Somfy-01仍有24条日志未匹配，Capture-42 PCAP被TShark报告为尾部截断但已匹配全部4,426条官方日志，且该场景未知恶意支持数仅6。外部正式实验必须在生产Adapter、独立split及K/U预注册后启动，不得把本轮RF探针当作论文结果。

## 3. K/U预注册与信息隔离

### 3.1 三类集合

- `K_known`：覆盖多种coarse、包含易难类且样本充足；可进入Qwen SFT以及传统模型基线训练。
- `U_dev`：约2—4类，仅用于Unknown算法、阈值、证据扩展策略、RulePolicy/Supervisor策略开发、可选LearnablePolicy和合法RAG路由开发，不进入主分类模型监督。
- `U_final`：最终评测前完全隔离；不得进入SFT/DPO、Prompt示例、known-only RAG、Unknown算法选择、阈值开发、Agent/策略训练、错误驱动调参或人工挑选。

正式训练前预注册Near、Far、Mixed多套组合与随机种子，全部报告，不依据结果挑选最优组合。

### 3.2 三阶段生命周期

**阶段A：Unknown Rejection。** Qwen主分类SFT只使用`K_known`监督数据和known-only冻结知识，输出Known fine/coarse候选、证据充分度、supporting/missing evidence及可供open-set计算的模型信号；冻结的Unknown Scoring / Calibration层再产生正式Unknown决策。Unknown算法和阈值只能使用`K_known`与`U_dev`开发，`U_dev`标签不得作为主分类模型监督进入SFT。

**阶段B：Knowledge-assisted Candidate Identification。** 仅对已拒识样本开放full-frozen RAG，返回Top-k候选、证据边界和人工确认需求；不与监督细类准确率混为一谈。

**阶段C：Few-shot Onboarding。** 为`U_final`预先冻结sample-level support/query；support取1/5/10条不同记录，建立新类记忆、原型或可选轻量适配并注册新类；query不得含相同记录或精确重复。不得根据query结果选择support、调Prompt或更新原型。

## 4. 模型与证据表示

### 4.1 传统模型仅作为基线

Logistic Regression、Random Forest、LightGBM和XGBoost用于闭集强基线、开放集拒识基线、速度/成本基线、数据泄漏诊断，以及可选混合消融或部署变体。它们不进入正式主链路，不负责筛选Qwen样本，也不向Qwen提供必需概率。

若实验保留树模型OOF预测，仅用于传统模型自身的校准、开放集基线或可选融合消融，不能作为Qwen SFT的必要输入。

### 4.2 Session Evidence Card

Session Evidence Card是提供给Qwen和工具的安全证据载体，至少包含：数据集原生Schema、会话标识的匿名化引用、前N个包的方向/长度/IAT/协议/flags、会话持续时间与双向统计、字段缺失声明、当前可观察证据、已请求证据、知识来源和预算状态。

Agent扩展后可加入past-only时间上下文、局部通信图摘要、合法应用层字段、有限脱敏Payload和RAG结果。传统模型概率只能作为可选消融字段，不属于正式Qwen输入合同。不可观察信息不得由Qwen或RAG补造。

Evidence State则是随决策过程更新的策略语义合同：它应表达当前fine/coarse候选、open-set信号或Unknown决策状态、证据是否充分、supporting/missing evidence及缺口类型、当前可用能力、已请求与明确不可获得的证据、当前与剩余预算、决策深度、历史动作和工具失败。上述内容用于约束策略输入、动作合法性和轨迹记录，暂不锁定为最终字段名或JSON Schema。

### 4.3 Qwen3.5-9B主分类模型

Qwen3.5-9B直接读取Session Evidence Card并执行第一次分类，承担：

- known fine classification；
- coarse classification与必要退回；
- evidence sufficiency判断；
- supporting evidence与missing evidence输出；
- 提供可供独立Unknown Scoring / Calibration计算的模型信号。

SFT用于学习会话证据序列化、`K_known`原生标签语义、粗细层次、证据充分度、supporting/missing evidence、结构化输出以及证据不足时的backoff/abstain行为，而不是使用`U_dev`或`U_final`监督学习未知类别，也不是复核树模型错误。首次分类暂定前8包、保存上限16包；正式任务采用text-only、冻结视觉模块和默认non-thinking模式。当前不冻结分类头或标签Token、Unknown具体算法、置信校准方式、SFT样本格式和第9至16包的具体请求策略。

### 4.4 RAG信息域

知识来源可包括数据集官方类别描述、协议说明、ATT&CK、CAPEC、公开攻击行为说明和已批准的新类记忆。known-only RAG服务阶段A；full-frozen RAG只在合法拒识后服务阶段B；few-shot memory只在获得support标签后建立。`U_final`名称和描述不得泄漏到阶段A。

RAG不是每个样本默认调用的通用补全器。Evidence State须概念性地区分两类缺口：**观测证据缺口**表示真实流量信息尚未被观察，例如包序列、历史行为、关系上下文或合法应用层字段不足，应调用相应网络取证工具；**知识证据缺口**表示已有观测需要协议、攻击行为或标签语义解释，才优先调用`RETRIEVE_KNOWLEDGE`。例如“过去60秒是否访问多个目标端口”只能由past-only时间上下文回答，RAG不得推断或补造该观测。三阶段RAG信息隔离保持不变。

## 5. Adaptive Decision Agent

### 5.1 状态、动作与停止

Agent状态至少表达：当前fine/coarse候选、open-set信号与冻结Unknown决策状态、证据充分度、supporting/missing evidence、缺失证据类型、可用能力、当前包数与上下文范围、已请求证据历史、明确不可获得的证据、RAG状态、历史动作、工具异常、决策深度、当前/剩余预算、成本和延迟。这是研究层面的语义合同，不提前冻结最终Schema字段。

`missing_evidence_type`仅服务工具选择，不增加新的分类任务：观测证据缺口指尚未取得的真实网络观测，知识证据缺口指已有观测缺少外部语义解释。候选映射如下：

| 缺口或状态 | 优先候选动作 |
| --- | --- |
| 包序列或传输交互不足 | `EXPAND_PACKETS` |
| 扫描、突发、周期性或历史行为不足 | `EXPAND_TEMPORAL_CONTEXT` |
| 多源、多目标、关系或局部拓扑不足 | `EXPAND_GRAPH_CONTEXT` |
| 合法应用协议可观察字段不足 | `REQUEST_APPLICATION_EVIDENCE` |
| 协议、安全行为或标签语义知识不足 | `RETRIEVE_KNOWLEDGE` |
| 证据充分或无法继续获取 | `RECLASSIFY`、`ACCEPT_FINE`、`BACKOFF_COARSE`、`REJECT_UNKNOWN`或`ABSTAIN` |

该映射约束候选动作与状态语义，避免“低置信就任意调用工具”，但不把RulePolicy硬编码为永久算法；RulePolicy和LearnablePolicy仍可在同一状态、动作、工具与预算合同上选择不同合法动作。

动作集合：

| 动作 | 含义 |
| --- | --- |
| ACCEPT_FINE | 接受Qwen的高可信细类 |
| BACKOFF_COARSE | 只接受可靠粗类 |
| EXPAND_PACKETS | 请求更多合法包级序列 |
| EXPAND_TEMPORAL_CONTEXT | 请求past-only近期会话摘要 |
| EXPAND_GRAPH_CONTEXT | 请求局部通信图摘要 |
| REQUEST_APPLICATION_EVIDENCE | 请求合法应用层字段或有限脱敏Payload |
| RETRIEVE_KNOWLEDGE | 按当前缺失证据检索知识 |
| RECLASSIFY | 使用扩展后的证据再次调用主Qwen分类 |
| REJECT_UNKNOWN | 拒识为Unknown |
| RETURN_TOPK | 返回证据约束候选 |
| REQUEST_LABEL | 请求人工标注 |
| REGISTER_NEW_CLASS | 满足冻结条件后注册新类 |
| ABSTAIN | 证据不足或预算耗尽时停止 |

`CALL_LLM_EXPERT`不再是正式动作：Qwen已是必经主分类器，追加调用统一由`RECLASSIFY`表达。状态机、工具白名单、预算和最大深度强制动作合法与可复现。

当前默认由Supervisor提出动作，Runtime每轮只验证并执行一个合法证据动作；相同Tool可在request signature不同的前提下重复调用，完全相同request必须拒绝。Supervisor可以表达多步意图，但新证据返回后必须重新读取状态并决策。

当证据已充分、相关能力不可用、合法动作不能再改变状态、重试上限/最大深度到达或预算耗尽时必须停止，并根据冻结规则接受、退回粗类、拒识或abstain；工具失败只能触发白名单内的retry/fallback，不得无限循环。

### 5.2 策略与公平基线

当前正式Agent主方案为High-Capability LLM Supervisor；实现面向`SupervisorBackend`抽象，以便在线服务与未来本地兼容模型替换。`RulePolicy`作为必须保留的强可复现baseline，`Strong Static`继续提供预先冻结且合理的固定取证次序；`LearnablePolicy`仅为可选扩展。各策略共享Evidence State、动作白名单、工具、信息域和预算合同。

强Static Pipeline必须使用相同的Qwen、工具、信息域和最大预算，并包含合理的固定取证顺序、retry、fallback和validator。固定全证据只代表在共同预算内预先提供全部指定证据的上界或消融，不等同于Adaptive Agent。只有Supervisor或其他动态策略在预算匹配条件下提高任务目标适应性、任务成功、恢复或utility-cost，才能说明动态策略有价值；不能通过给Agent更多信息、更多调用预算或故意削弱Static/RulePolicy获得结论。

### 5.3 轨迹与反馈

每个样本保存`sample_id → evidence state → Qwen output → action/reason → tool input/result → next state → stop reason → final prediction → unknown score → cost/latency → truth → error source → update action`。获得真实标签后，将错误归因到SESSION_CONSTRUCTION、PACKET_EVIDENCE、CONTEXT_SELECTION、APPLICATION_EVIDENCE、RAG_QUERY/EVIDENCE、LLM_CLASSIFICATION、UNKNOWN_DECISION、POLICY、CLASS_MEMORY、LABEL_SCHEMA、DATA_LEAKAGE或TOOL_FAILURE，只更新相关组件。

组件级归因同时构成反馈边界，而不只是论文统计：**Level 1样本级适应**只为当前样本取得新的合法证据，不更新参数；**Level 2策略级适应**面向相似状态下反复选错工具或过早停止，更新RulePolicy规则、离线验证并版本化Supervisor Prompt/策略，或更新可选LearnablePolicy，不直接归因于Qwen；**Level 3模型级适应**仅在充分且正确的证据已提供、Qwen仍持续出现同类理解或分类错误时，才考虑补充SFT数据，DPO仍受既定条件Gate约束。Unknown阈值/校准错误应更新Unknown scoring/calibration，RAG错误应优先修复query、retrieval或知识条目。禁止采用“所有错误均回流SFT”的无归因路线。

### 5.4 Runtime与Memory边界

deterministic Runtime负责Qwen、Supervisor和工具调用，以及Action验证、capability、预算、最大轮数、request去重、future leakage防护、Memory权限、失败处理与结构化Trace；LLM不得绕过Runtime。Supervisor只接收model-safe Evidence State、Qwen简短分析、Unknown状态、sanitized evidence、工具状态、预算/历史和validated experience，不接收真实IP、绝对时间、capture/scenario或dataset identity、ground truth和完整原始Payload。

Experience Memory保存经可靠反馈验证的`State→Action→Outcome`经验；train可验证后写入，validation与`U_dev`默认不写入，TEST/`U_final`冻结只读。Class Memory只保存人工确认的新类别support，必须与Experience Memory分离；few-shot注册默认不立即更新Qwen权重。独立Agent Growth Stream仅为可选实验，主test不得边评测边学习。具体Memory embedding、index、top-k和capacity仍未冻结。

## 6. 训练边界与启动条件

SFT仅在正式数据、会话样本、split、K/U、字段白名单、信息域和泄漏控制冻结后启动。正式默认训练路线为Qwen3.5-9B post-trained模型的text-only BF16 LoRA SFT：冻结视觉编码器和多模态对齐模块，LoRA只作用于需要训练的语言模型模块，使用原生Tokenizer、固定Session Evidence Card序列化和non-thinking/direct-response输出。QLoRA只在显存不足、框架兼容性问题或量化消融时作为降级/备用路线。

DPO仅在SFT后确认存在证据幻觉、过度自信、错误拒识或动作偏好问题，且能构造可靠chosen/rejected对时开展LoRA DPO。DPO不是当前必做项，也不代表完整PPO-RLHF。9B全参数训练、27B正式训练、PPO/GRPO和大规模领域继续预训练均不属于当前主线。

以下内容明确未冻结：分类头或标签Token、Unknown评分与校准的具体算法、SFT样本格式、第9至16包的请求策略、精确时间窗口、Agent学习算法、服务器规格和最终泛化声明。正式Unknown算法只允许由`K_known`和`U_dev`开发，`U_final`只用于冻结后的最终评价。

## 7. 四组核心实验

### 实验一：LLM独立分类与传统基线

比较Logistic Regression、Random Forest、LightGBM/XGBoost、原始Qwen3.5-9B和后训练Qwen3.5-9B。任务覆盖Benign/Malicious、原生coarse和fine分类。所有模型使用可公平比较的数据划分；传统模型读取其合法表格特征，Qwen读取冻结的会话级混合表示。

报告Macro-F1、分类别指标、混淆、校准、速度和成本，回答后训练LLM独立分类的能力、代价和边界。传统模型是强基线，不是Qwen前置模块。

### 实验二：开放集与自适应取证主实验

传统模型开放集基线与单次Qwen+冻结Unknown继续作为必要参照；Agent部分按四个因果问题组织：

| 问题 | 主要比较与控制 |
| --- | --- |
| Q1 更多证据本身是否有价值 | `Basic Session Evidence` vs 在共同最大预算内预先冻结的`Fixed Full Evidence` |
| Q2 动态按需取证是否优于固定方式 | `Fixed Full Evidence`、`Strong Static`、`RulePolicy`、High-Capability LLM Supervisor及可选`LearnablePolicy`使用相同Qwen、工具、信息域和最大预算 |
| Q3 各证据源贡献什么 | 分别移除packet expansion、temporal context、graph context、application evidence和RAG |
| Q4 收益是否只来自更多资源 | 对齐Agent与Static预算，并报告证据请求、Qwen/RAG/工具调用、延迟、Token成本、预算遵从及utility-cost曲线 |

`Basic Session Evidence`回答不追加证据的能力，`Fixed Full Evidence`回答更多证据的上界，Strong Static、RulePolicy与Supervisor的预算匹配比较才回答动态选择是否必要。不得通过为Agent额外开放信息域、调用次数或预算制造优势；若某证据源在数据中不可用，应报告能力边界而非伪造完整消融。

#### 传统模型零信息新类扩展诊断

该诊断只用于展示传统闭集模型在没有新类别训练样本和类别语义时的能力边界，不是强传统开放世界算法，也不能替代合理的传统Unknown拒识基线。协议如下：

1. 传统分类器只使用`K_known`训练，不接触`U_dev`和`U_final`的分类标签样本；
2. 先加入合理的Unknown拒识机制，可使用校准后的最大概率、margin、entropy、树间分歧或已知分布距离；
3. 最终测试时先判断样本属于某个Known类别还是Unknown；
4. 对被拒识为Unknown的样本，将输出空间临时扩展为M个候选新类别；
5. 由于模型没有任何新类样本、类别语义或特征映射，只能在M个新类别中均匀随机分配，随机识别水平约为`1/M`；
6. 使用固定随机种子并重复多个种子，报告均值和标准差；
7. `U_final`类别名称只在最终诊断阶段作为输出选项公开，不参与训练、Unknown阈值开发、特征选择或Agent训练。

结果分别报告：`Closed-set classifier`将未知样本强制归入Known类别；`Classifier + Unknown rejection`输出Known类别或统一Unknown；`Classifier + naïve unseen-label expansion`再将被拒识样本随机分配给具体新类别。指标包括Unknown detection AUROC/AUPR或Recall、Known-to-Novel FPR、真正未知样本进入新类池的比例、新类别具体识别Accuracy与Macro-F1、新类混淆矩阵、不同Unknown阈值下Known污染率—新类Recall权衡，以及多随机种子均值和标准差。

该诊断希望区分“发现样本不属于Known”与“识别它具体属于哪个新类”，并检验强行扩展标签空间是否表现为新类漏检、Known流量污染和新类之间近似随机混淆。它不能单独用于证明LLM优越；正式公平比较仍是`传统强分类器+合理Unknown拒识`、`后训练Qwen+Unknown`和`Qwen+Agent动态证据扩展`。

指标包括Known Macro-F1、Unknown AUROC/AUPR、FPR95、OSCR、H-score、层次退回、错误接纳Unknown、证据请求率、Qwen调用次数、Supervisor轮数、RAG调用次数、各类工具调用次数、任务成功、预算遵从、恢复成功、输出合法、延迟、Token/API成本及utility-cost曲线。

主要消融包括：只有会话基础证据、无包扩展、无时间上下文、无图上下文、无应用层证据、无RAG、固定取证、Rule vs Learnable、无成本惩罚和预算匹配。具体组合在数据可用性确认后压缩，不预先假定所有证据源都存在。

### 实验三：1/5/10-shot新类接入

比较传统模型重训、最近邻/原型、Qwen in-context、RAG语义原型、Agent注册新类和可选LoRA。主实验为sample-level 1/5/10-shot，报告新类Precision/Recall/F1、Unknown到新类转化、旧类Macro-F1与遗忘、标注样本数、接入时间、更新/推理成本和重分类调用率。存在可靠活动标识时再增加group-level增强实验。

### 实验四：IoT-23独立场景外部验证

IoT-23已通过带限制的最终可行性验收，正式阶段在其原生标签体系和独立模型适配下复现实验协议的压缩子集：scenario-held-out闭集、一套class-held-out Unknown和一套Agent时间/相关会话上下文增益；允许时增加1-shot或5-shot新类接入。训练、验证和测试按IoT-23 scenario隔离，测试scenario完全留出。

本实验评价统一接口、Qwen分类协议、Unknown生命周期和Agent决策方法在另一采集环境与原生标签Schema中的适用性，不要求Edge最终分类器直接零样本识别IoT-23细类，不进行物理合并训练，也不把两个标签空间的绝对Macro-F1直接比较。

## 8. 评价、复现与统计

- 每套Unknown preset至少使用多个随机种子；具体数量在数据与算力确认后冻结。
- `U_final`只运行冻结系统，结果不回流模型、阈值、Prompt、RAG、策略或训练。
- 保存数据、代码、模型、Prompt、RAG、证据序列化和工具配置指纹，以及run ID、split manifest、失败和resume记录。
- Agent除分类指标外还报告end-to-end task success、evidence/tool选择成功、recovery、budget compliance和output validity，并分别统计证据请求率、Qwen调用次数、Supervisor轮数、RAG/各工具调用次数、延迟、Token/API成本和utility-cost曲线。
- 比较Static与Agent时必须使用同一Qwen、工具、信息域和最大预算，并进行budget-matched主比较；成本受限子集须在实验前固定，不按模型结果定制。固定全证据、Static、Rule与Learnable的资源差异须单独披露，不能把额外调用量解释为策略增益。
- 错误分析须同时给出错误来源和组件级处置去向，区分样本级取证、策略更新、Qwen SFT、Unknown校准及RAG修复，避免把不同组件的问题汇总为单一模型误差。
- 会话和past-only关联必须在训练、验证、测试内部独立构造，并检查固定身份、时间和来源捷径。

## 9. 时间与依赖

| 阶段 | 工作 | 退出条件 |
| --- | --- | --- |
| 方案与数据角色冻结 | 同步三份计划、Decision Log与交接文档；冻结Edge主实验与IoT-23外部验证职责 | DEC-0008已生效；不再广泛搜索数据集 |
| 双数据集最终可行性验收 | 使用最小官方数据核验两个Adapter、标签对齐、非随机划分、泄漏、轻量可学习性和Qwen输入合同 | DEC-0009生效；整体`PASS_WITH_LIMITATIONS`，原始证据位于`reports/data_feasibility_gate_20260806/` |
| 本地收尾与服务器迁移 | 将代码、报告、manifest、校验和与下载说明推送到远程；本地仅保留可复现资产及必要的唯一归档 | **已完成：**DEC-0010生效，GitHub `main`已形成可复现停止点，本地可重建大数据已受限清理 |
| 服务器初始化 | **已完成：**验证Git同步，初始化独立存储/资产/模型目录，确认硬件与GPU，配置数据处理环境 | 仓库、目录、权限、基础软件和数据下载条件可复现；研究计划不绑定具体平台、GPU型号或目录 |
| 服务器数据与生产接口冻结 | **已完成：**从官方来源下载和校验数据；将验收Adapter固化为生产流水线，冻结全量split、K/U、support/query、异常文件处置和training manifest | `PRODUCTION_DATA_READY=true`、`CLASS_ROLE_SUPPORT_GATE=PASS`、postfix audit为`PASS_WITH_LIMITATIONS` |
| T0前冻结 | **已完成：**冻结两个数据集的split、各自K/U、support/query、字段白名单和training manifest；完成信息隔离、重建、恢复与Git冻结 | 正式资产在服务器可复现，大型数据资产保持Git外 |
| T0后第1周 | 加载Qwen3.5-9B并完成text-only BF16 LoRA SFT小规模冒烟；完成传统与原始Qwen基线 | 模型、数据、独立Unknown评分接口和结构化输出链路可运行，无Final泄漏 |
| 第2周 | 完成Edge Qwen主训练、闭集/coarse/fine与强Static基线 | 主Qwen稳定输出fine/coarse、证据状态和开放集模型信号，冻结Unknown层产生可复现决策 |
| 第3周 | 在已实现deterministic Runtime foundation与provider-neutral backend preparation上完成Production adapter、正式证据工具、Edge Near/Far/Mixed Unknown、RulePolicy与High-Capability LLM Supervisor实验；LearnablePolicy和DPO仅作条件性判断 | Edge实验一、实验二及utility-cost主结果冻结 |
| 第4周 | 完成Edge sample-level 1/5/10-shot、成本与错误分析；执行IoT-23压缩外部验证并同步论文初稿 | 实验三、实验四、限制与可复现清单完成 |

T0定义为生产级`CanonicalSessionRecord`、两个Adapter、Edge与IoT-23各自split/K/U、字段白名单、support/query和training manifest获得冻结之日；该条件已于Production Data Freeze达成。当前还完成了deterministic Runtime foundation及provider-neutral real-backend preparation的安全集成，但尚未完成Production→Runtime轻量adapter、真实provider/model配置、Qwen下载或训练。正式训练使用满足Qwen3.5-9B BF16 LoRA需求的单卡GPU服务器，具体平台、型号、路径和软件小版本不作为研究方法冻结项。

## 10. 风险与降级路线

| 风险 | 处理/降级 |
| --- | --- |
| Edge单capture与类别/场景耦合 | 采用capture内时间块、隔离gap、split内past-only和捷径消融；主结论限定于同采集环境，外部证据由IoT-23补充 |
| Edge异常PCAP或部分字段不可用 | 用成熟解析器复核并记录可恢复范围；缺失能力显式声明，不改变Edge主数据角色或虚构证据 |
| IoT-23最小子集与正式Unknown支持不足 | 保留已通过的原生标签和scenario协议；正式manifest中补足预注册未知类/场景，或明确小样本置信区间，不以当前6条未知恶意流支撑主结论 |
| 会话重建或标签粒度不可靠 | 收缩为可验证的会话/流记录单位，并限制结论；不得虚构跨会话监督 |
| 包数或上下文过长 | 首次分类使用前8包与摘要，Agent最多扩展至16包；通过预算和受限past-only摘要控制长度 |
| 固定IP、时间、capture或脚本捷径 | 后台关联与模型输入分离；做白名单、去身份和敏感性对照 |
| Qwen不优于传统基线 | 报告分类能力与成本边界，并检查Unknown、证据充分度和few-shot价值；不恢复树模型主导架构 |
| Agent不优于强Static | Static成为推荐系统；Agent作为适用边界和负结果分析，不强行宣称有效 |
| 缺失证据类型判断错误或用RAG代替真实观测 | 以`capabilities`、缺失声明和动作validator限制候选工具；观测缺口只能调用真实取证工具，能力不可用时backoff或abstain |
| Agent收益来自额外信息或预算 | 强制与Static共享Qwen、工具、信息域和最大预算，报告逐类调用量及utility-cost；无法预算匹配的结果只作为上界补充 |
| 错误反馈更新了错误组件 | 先完成组件级归因；Unknown问题回到校准层、RAG问题回到检索链、策略问题回到Policy，只有充分证据下持续的Qwen错误进入SFT候选 |
| 应用层或Payload不可用 | 保留基础会话、包序列、past-only关联与RAG；缺失证据显式声明 |
| BF16 LoRA收益小或显存/框架受限 | 保留原始Qwen基线、缩小高价值样本；必要时降级为QLoRA；取消DPO、27B和继续预训练 |
| 一个月实验过多 | 保留Edge实验一、开放集最小实验二、sample-level实验三及IoT-23三项压缩验证；优先取消复杂策略、DPO和外部few-shot扩展 |

## 11. 当前已完成、未完成与下一步

已完成：旧资产选择性迁移；通用OpenAI-compatible LLM调用、结构化验证、缓存/resume/trace；RAG文档摄取；数据合同、精确重复、Ground Truth匹配、分组与审计工具；多轮历史数据审计；架构回溯与方案纠偏；Edge-IIoTset完整官方数据获取及Phase 2审查；双数据集角色冻结；Edge/IoT-23最终可行性验收；远程服务器初始化与官方数据恢复；生产级`CanonicalSessionRecord`、EdgeAdapter/IoT23Adapter、60秒session、全量split/K/U/support/query、provenance、identity dedup、leakage/determinism/readiness及Git冻结；deterministic Runtime foundation、Memory/预算/终止安全合同、provider-neutral LLM backend preparation和Fake Provider集成审计。

尚未完成：Production安全投影到Runtime合同的轻量白名单adapter；生产证据工具与正式Session Evidence Card封装；真实provider transport/smoke；传统模型正式基线；Qwen SFT/DPO；Unknown算法；High-Capability LLM Supervisor、强Static和可选LearnablePolicy的正式配置与实验；四组论文实验。现有Runtime/LLM结果仅来自mock、synthetic或Fake Provider工程审计，不是模型或论文结果。

下一执行顺序：

1. 实现轻量、白名单式Production→Runtime adapter，将`initial_model_views`显式封装为`EvidenceItem`并映射`CapabilityStatus`，加入禁止backend/canonical字段泄漏的跨层测试；
2. 在另行授权后实现最小真实provider transport/smoke，冻结前仍不得把Fake Provider结果描述为真实模型结果；
3. 配置GPU模型环境和Qwen3.5-9B，完成text-only BF16 LoRA SFT小规模冒烟；
4. 按冻结协议选择Unknown scoring并执行Edge-IIoTset主实验和IoT-23压缩外部验证。

## 附录A：端到端执行链路速查

本节只将前述冻结方案按先后顺序汇总，不替代数据Gate、模型、Agent、实验和Decision Log中的详细约束。

### A. 研究项目执行链路

1. **数据集选择与可行性Gate。** Edge-IIoTset承担完整主实验，IoT-23承担独立scenario外部验证；核验官方来源、原生标签、PCAP/日志可解析性、潜在捷径与任务可执行性。
2. **下载、校验与原始数据归档。** 在服务器从官方来源获取数据，记录hash、文件清单和异常文件，保证原始输入可核验、可恢复。
3. **Production数据预处理与标签对齐。** 已从PCAP解析packet、重建双向session，并将官方ground truth映射到统一`CanonicalSessionRecord`；Edge-IIoTset Label Provenance Audit及24-capture guard已通过（带已记录限制），不得绕过其hash、label purity与quarantine规则。
4. **数据清洗、split与泄漏控制。** 只依据immutable backend identity处理真正重复记录，冻结chronological/scenario split、隔离gap、split内past-only上下文、字段白名单及exact/near-duplicate sensitivity；模型输入继续隔离真实身份、绝对时间和capture来源。
5. **冻结`K_known`、`U_dev`与`U_final`。** Edge预注册Near/Far/Mixed Unknown，IoT-23保留自身原生标签空间；`U_final`在最终评测前严格隔离，不参与模型、阈值、Prompt、RAG或策略开发。
6. **生成support/query与训练manifest。** 冻结1/5/10-shot support、无相同记录或精确重复的query、各阶段训练可见范围和数据版本，完成Production Data Freeze。
7. **Git与服务器正式版本冻结。** Production实现已保存在独立server分支，并与最终real-backend preparation分支在独立integration分支经no-ff合并、审查和测试；不得直接覆盖、rebase或绕过双分支核验。
8. **部署Qwen3.5-9B与训练环境。** 建立独立训练环境，下载模型并验证GPU、Tokenizer、推理、显存占用和结构化输出；BF16 LoRA SFT为默认路线，QLoRA仅作显存/兼容性fallback或量化消融。
9. **建立原始Qwen与传统模型基线。** 在同一冻结数据协议上运行LR、RF、LightGBM/XGBoost和未经SFT的Qwen，得到closed-set、速度和成本参考；传统模型只承担基线与诊断，不作为Qwen前置路由器。
10. **构造SFT训练数据。** 仅从合法`K_known/train`进行可复现采样，生成Session Evidence Card监督样本；Canonical全量资产与实际SFT采样规模分别记录。
11. **执行BF16 LoRA SFT。** 先进行小规模smoke test，再正式训练Qwen3.5-9B，使其学习fine/coarse分类、形成Evidence State所需的证据充分性与supporting/missing evidence，以及backoff/abstain行为。
12. **评价Raw Qwen与SFT Qwen。** 比较分类能力、结构化输出、证据理解、速度和成本，确认领域后训练的收益、失败类型与适用边界。
13. **选择并校准Unknown Scoring。** 只使用`K_known`和`U_dev`比较logit/margin/entropy/energy/embedding/prototype等候选信号，冻结独立开放集评分和阈值；Qwen自报confidence仅作消融，`U_final`不得用于选择或调参。
14. **执行开放集Near/Far/Mixed实验。** 评价Known分类、Unknown拒识、coarse backoff、风险—覆盖率和错误接纳Unknown，并按预注册组合与随机种子完整报告。
15. **完成Adaptive Evidence Agent。** 在已实现的Evidence State、deterministic Runtime和可替换Backend foundation上接入Production安全投影与正式证据工具，由High-Capability LLM Supervisor依据missing evidence在预算内每轮选择一个packet、temporal、graph、application或RAG动作，再触发Qwen重分类或停止。
16. **比较Static、RulePolicy与Supervisor。** 在相同Qwen、工具、信息域和最大预算下比较Basic、Fixed Full Evidence、Strong Static、RulePolicy、High-Capability LLM Supervisor与可选LearnablePolicy，判断自适应证据选择及高能力策略是否产生价值。
17. **完成RAG与证据源消融。** 分别评价packet expansion、temporal context、graph context、application evidence和RAG的增量，并报告tool/Qwen/Supervisor/RAG调用、Token、延迟、budget compliance和utility-cost。
18. **执行Few-shot新类接入。** 使用预注册1/5/10-shot support测试`REQUEST_LABEL`、`REGISTER_NEW_CLASS`及新类query识别，并写入与Experience Memory分离的Class Memory，同时评价Unknown到新类转化与旧类遗忘。
19. **条件性开展DPO。** 只有SFT后存在稳定的偏好、过度自信或动作选择问题，且能构造可靠chosen/rejected pair时才开展；否则跳过，不把DPO视为主线成立的必需步骤。
20. **进行IoT-23独立外部验证。** 在IoT-23自身标签空间和scenario split下复现closed-set、一套Unknown和一套Agent压缩实验，不要求Edge模型直接零样本识别IoT-23细类。
21. **最终统计、敏感性与错误分析。** 汇总closed-set、open-set、Agent、few-shot、exact/near sensitivity、成本以及组件级错误来源，冻结论文正式结果和复现清单。
22. **论文整理与写作。** 按“后训练LLM分类→Unknown开放识别→自适应取证Agent→Few-shot新类接入”组织图表、消融、案例、限制和复现说明，形成完整论文。

```text
数据与Gate → Production Freeze → Qwen部署 → Raw/Traditional Baseline → BF16 LoRA SFT → Unknown → Supervisor Agent → Few-shot → IoT-23外部验证 → 最终实验 → 论文
```

### B. 系统实际识别链路

1. **接收原始网络流量。** 系统接收PCAP或等价网络捕获数据；数据来源和真实身份只保留在backend审计层，不直接进入模型。
2. **解析Packet。** 提取timestamp、packet length、L3/L4协议、TCP flags等可观察字段，并将不同协议结构统一投影为可审计字段。
3. **重建双向Session。** 将同一次双向通信的packet聚合为session；Edge正式构造采用双向通信关系与冻结的60秒inactivity规则，且session不跨capture/source。
4. **构造`CanonicalSessionRecord`。** 保存backend身份、完整session统计、包序列、能力声明和可扩展证据，同时将真实IP、绝对时间、capture ID等model-unsafe字段与模型视图隔离。
5. **构造Initial Session Evidence Card。** 第一次分类提供前`min(N, 8)`个packet的方向、长度、IAT、协议和flags，加完整session summary；service category不进入Primary View。
6. **由Qwen3.5-9B第一次分类。** 后训练Qwen直接输出fine/coarse候选、supporting evidence、missing evidence、evidence sufficiency及可供open-set计算的模型信号，不经过传统模型路由。
7. **执行独立Unknown Scoring。** 冻结的开放集评分/校准层根据Qwen可用模型信号判断样本是否偏离Known类别；LLM自报概率不作为正式Unknown依据。
8. **建立Evidence State。** 汇总类别候选、Unknown状态、supporting/missing evidence、capabilities、请求历史、工具失败、历史动作、剩余预算及少量validated experience。
9. **由Supervisor判断停止或继续。** High-Capability LLM Supervisor读取model-safe状态，在Runtime约束下每轮提出一个合法动作；证据充分时选择`ACCEPT_FINE`、`BACKOFF_COARSE`、`REJECT_UNKNOWN`或`ABSTAIN`，否则进入按需证据扩展。
10. **按需执行`EXPAND_PACKETS`。** 包交互证据不足时读取第9至16个packet；完整session仍用于summary，并不表示第17包以后从原始记录中删除。
11. **按需执行`EXPAND_TEMPORAL_CONTEXT`。** 查询当前session之前的合法past-only历史，例如近期session数、目标/端口多样性、通信频率和时间间隔。
12. **按需执行`EXPAND_GRAPH_CONTEXT`。** 获取当前通信主体与其他session的局部关系摘要，辅助分析扫描、集中攻击、多源或多目标行为。
13. **按需执行`REQUEST_APPLICATION_EVIDENCE`。** 仅在协议可解析、字段合法且数据实际可观察时取得HTTP、DNS、MQTT等应用层证据或有限脱敏Payload。
14. **按需执行`RETRIEVE_KNOWLEDGE`。** RAG只补充协议、攻击行为或标签语义等knowledge gap，不替代真实流量中缺失的observational evidence。
15. **更新Evidence State。** 将新增证据、未获得或不可用证据、工具失败、预算消耗和request history写回当前状态。
16. **Qwen重新分类。** 使用扩展后的证据重新输出fine/coarse、supporting/missing evidence、evidence sufficiency及模型信号。
17. **重新评估Unknown。** 独立评分/校准层根据新的模型状态重新计算开放集判断，不改变冻结算法和阈值。
18. **执行Supervisor循环决策。** deterministic Runtime在预算和最大深度内重复`Evidence State → Supervisor action → evidence tool → Qwen → Unknown → new Evidence State`，直至满足停止条件。
19. **输出Known Fine或Coarse。** 证据充分且属于Known时接受fine；只能可靠确认上层类别时执行`BACKOFF_COARSE`。
20. **输出Unknown或Abstain。** 明显偏离Known时执行`REJECT_UNKNOWN`；证据不足、能力不可用或预算/重试耗尽时执行`ABSTAIN`，不强行猜测。
21. **可选执行Few-shot新类接入。** 对已拒识Unknown，只有获得合法人工support标签后才执行`REQUEST_LABEL`和`REGISTER_NEW_CLASS`并用于后续新类识别；这不是普通样本的必经步骤。
22. **生成结构化结果与Trace。** 保存最终prediction、Known/Unknown状态、supporting evidence、backoff/abstain、Agent动作、工具调用、成本/延迟和可审计trace。

```text
Raw Traffic → Packet Parsing → Bidirectional Session → CanonicalSessionRecord → Initial Evidence Card → Qwen Traffic Expert → Frozen Unknown Scoring → Evidence State → High-Capability LLM Supervisor → one legal action via Deterministic Runtime → Evidence Acquisition → Reclassification → Fine / Coarse / Unknown / Abstain → Structured Result + Trace
```

## 12. Material Deviation and Decision Log

| 日期 | ID | 原决定 | 新决定 | 替代原因与审查证据 | 可逆性 | 后续影响 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-08-02 | DEC-0001 | 多Flow Episode与SFT/DPO/RLAIF边界较粗 | detailed成为canonical；Episode为待验证anchor+past-only假设；SFT为基础、DPO条件性、RLAIF设Gate | 需要可执行、可审计的阶段规范 | 可由实验修订 | 建立Gate 0与分阶段训练边界 |
| 2026-08-03 | DEC-0002 | CasinoLimit与UWF预设为主训练，CAM-LDS预设外测 | CasinoLimit/UWF改为条件性；CAM-LDS主线NO-GO | `reports/dataset_audit/2026-08-formal-selection/`暴露label unit、连接和独立性限制 | 可在新增官方证据后重审 | 暂停按旧K集合训练 |
| 2026-08-04 | DEC-0003 | 条件性Casino/UWF仍可能直接形成K与shot | 撤回旧K；K/U为空，正式SFT暂停 | `reports/dataset_audit/2026-08-unblocking/`：Flow连接多义、UWF无公开mission ID、无独立query | 可在可靠活动元数据补齐后重审 | 禁止释放shot和正式训练 |
| 2026-08-04 | DEC-0004 | 所有数据统一ATT&CK、由单一数据集承担完整任务；Agent容易退化为固定串联 | 各数据集保留原生标签并通过统一接口验证；CICIoT2023定为`ENGINEERING_ONLY`；正式主数据继续过Gate；研究转向K/U生命周期和Rule/Learnable自适应决策 | 老师要求减少标签修复；CICIoT2023官方论文与`reports/dataset_audit/2026-08-ciciot2023-main-validation/`确认缺少独立group且存在窗口构造捷径 | 方法设计可逆；CIC角色仅在获得可靠activity映射后可重审 | 旧ATT&CK统一路线被替代；UWF降为专项补充；CasinoLimit不再挽救；SFT继续等待数据Gate；四组实验和信息隔离成为新冻结协议 |
| 2026-08-05 | DEC-0005 | 独立run/group、group-level few-shot和完整捷径控制是启动Hard Gate；CICIoMT/DataSense因缺少逐类run证据被阻塞 | 采用最低功能Gate启动主线，将活动级分组和完整捷径控制降为增强实验；CICIoMT2024为首选正式主数据候选，X-IIoTID为立即可切换的第一备用 | `reports/dataset_audit/2026-08-dual-gate-reassessment/`确认6个数据集已满足sample-level研究的最低功能条件；老师要求尽快形成可执行进度，避免数据审计和候选搜索继续扩张 | 数据角色可在最小验收失败时按停止规则切换；双层Gate与sample-level口径冻结 | 主实验改为class-level Unknown、sample-level open-set及1/5/10-shot；group/run级实验保留为增强项；明日进入CICIoMT获取、基线和Unknown实现，不再扩大搜索 |
| 2026-08-05 | DEC-0006 | 传统模型进行主要分类，Qwen复核困难样本 | 后训练Qwen直接执行首次分类；传统模型降为强基线和可选消融；Agent围绕Qwen结果执行动态取证、拒识和新类接入 | 老师认为传统分类器主导、LLM复核不足以体现LLM作用；阅读MET-LLM等工作后已决定采用领域后训练LLM独立分类；旧架构在计划改写中被错误恢复 | 主链路冻结；分类输出与策略细节仍可由实验修订 | 撤销Tree-aware Reviewer正式主线、传统模型OOF概率必需输入、selective Qwen正式定位和`CALL_LLM_EXPERT`主动作；DEC-0005中相关Reviewer与立即执行顺序被部分替代 |
| 2026-08-05 | DEC-0007 | 正式输入被限制为单行Flow/Flow-only统计证据 | 基础输入改为双向会话的包级序列与会话摘要；包扩展、跨会话关联、应用层证据、有限Payload和RAG由Agent按需获取 | 包顺序和会话交互比单行Flow保留更多行为信息，同时使Agent拥有真实、可测量的证据扩展动作 | 表示层级冻结；精确N、窗口、应用字段和Tokenizer仍待实验 | 后续数据审查必须验证会话重建与past-only关联；旧Flow-only字段计划降为传统基线或会话摘要资产 |
| 2026-08-06 | DEC-0008 | Edge-IIoTset仅为第一候选，第二数据集未定，多数据集实验为可选 | 冻结Edge-IIoTset为“主数据集，带冻结限制使用”，指定IoT-23为待范围受限验收的第二数据集；不物理合并训练，各自保留原生标签、独立训练/验证/测试和模型适配，通过`CanonicalSessionRecord`与Dataset Adapter统一接口 | `reports/dataset_audit/2026-08-edge-iiotset-final-review/`确认Edge会话、上下文、class-held-out Unknown及sample-level few-shot可执行，同时暴露单capture、捷径和跨run证据不足；需由IoT-23独立scenario补充外部适用性证据，并停止候选搜索扩张 | Edge主数据角色冻结；IoT-23仅在官方数据不可解析、标签不可用或无法构造scenario隔离时允许重选；接口字段可在Adapter冒烟后向后兼容修订 | Edge承担完整四类方法实验；IoT-23承担scenario-held-out闭集、一套Unknown和一套Agent上下文增益，允许时追加1/5-shot；NF3等停止进入当前主线；首次分类前8包、Agent最多扩展至16包 |
| 2026-08-06 | DEC-0009 | IoT-23为待验收第二数据集，统一Adapter、标签对齐、非随机可学习性和模型输入安全尚未实测 | 双数据集最终可行性验收整体判定`PASS_WITH_LIMITATIONS`：Edge-IIoTset继续作为带限制主数据集，IoT-23正式冻结为独立scenario外部验证数据集；两个数据集分别适配、保留原生标签且不物理合并，通过`CanonicalSessionRecord`统一方法接口 | `reports/data_feasibility_gate_20260806/`实测两个Adapter、7个IoT-23官方capture、PCAP/日志对齐、split内past-only上下文、直接泄漏、两种子no-service RF及Qwen输入合同；Edge与IoT-23 no-service Macro-F1分别为0.9498和0.7328，均明显超过同划分多数类基线 | 数据集角色冻结；生产Schema可向后兼容修订。若正式构建暴露新的阻断性标签或scenario证据，须新增Decision而非静默换库 | 可进入生产数据生成与GPU准备；保留Edge单capture/异常PCAP、IoT-23 Somfy最低81.54%匹配、Capture-42尾部截断及仅6条未知恶意流限制；验收RF不得作为论文结果 |
| 2026-08-06 | DEC-0010 | 正式数据处理默认继续在本地进行，再把冻结派生数据交给GPU服务器 | 正式原始数据下载、全量解析、会话化和训练资产生成迁移至远程服务器；本地只保留可复现代码、测试、报告、manifest、校验和、下载说明和必要小型fixture。唯一Edge官方完整归档在目标服务器下载尚未实测前保守保留 | 双数据集Gate已通过，本地继续存放约十余GB解压副本没有研究收益；服务器侧统一数据处理、资产路径和后续训练可减少重复搬运。官方来源、文件规模、哈希及恢复工具已归档于`docs/SERVER_MIGRATION.md`和Gate manifest | 数据角色、实验协议和模型架构不变；执行位置可在新增Decision后调整 | 执行顺序冻结为push仓库→选择服务器→配置存储/环境→官方数据下载与校验→Production Adapter→manifest冻结→GPU模型环境与Qwen冒烟；不得把迁移写成正式预处理或训练已开始 |
| 2026-08-09 | DEC-0011 | 当前生效方案仍把QLoRA写成默认SFT路线，并可能将Qwen自报Unknown分数理解为正式开放集评分；文本/多模态与thinking模式未明确 | 正式主训练冻结为Qwen3.5-9B post-trained模型的text-only BF16 LoRA SFT，冻结视觉编码器与多模态对齐模块，默认non-thinking/direct-response；QLoRA仅为资源或兼容性降级。Qwen学习`K_known`分类、证据状态和可供开放集计算的模型信号，正式Unknown由独立Frozen Unknown Scoring / Calibration层产生 | 单卡服务器已进入初始化阶段，需要在下载模型和生成训练资产前消除训练精度、监督权限与Unknown接口歧义；独立评分层可避免把未经验证的LLM自报概率直接当作开放集分数，并保持算法可比较 | BF16 LoRA、text-only和独立Unknown接口冻结；Unknown具体算法、分类头/标签Token及SFT格式仍可通过`K_known`和`U_dev`实验确定 | `U_dev`不得作为主分类监督进入SFT，`U_final`继续完全隔离；DPO仍为条件性LoRA DPO；不开展9B全参、27B正式训练、PPO/GRPO或大规模领域继续预训练 |
| 2026-08-09 | DEC-0012 | 初版Production Freeze把完整`NO_SERVICE_VIEW`签名作为全局winner去重键，误将不同真实session的相同模型输入视为同一记录，并通过`test > validation > train`等隔离优先级删除合法重复行为 | 冻结Production数据的身份去重与跨split相似性处理原则：Primary dedup只使用由dataset/version、source content hash、canonical bidirectional session identity、确定性source span/ordinal与session start构成的immutable backend identity（当前稳定`sample_id`）；model-view equality不等于sample identity，different backend identity即使exact/near view相同或标签不同也保留。exact/near cross-split collision只进入audit和预注册sensitivity；`EXACT_EVAL_CLEAN`/`NEAR_EVAL_CLEAN`固定train不变，仅从validation/test移除更早split已见signature。现实重复行为不用于控制规模或平衡，后续由独立可复现training sampler处理；readiness必须检查每个preset/role的class support与few-shot support/query可实现性 | Pre-Commit Scientific Audit发现Edge 7,619,032条constructed session仅保留790,708条，6,562,147条由跨split model-view全局winner删除，DDoS_UDP train变为0；该机制改变真实分布而非仅消除身份泄漏。决定在任何Qwen下载、训练或推理前作出，因此废止旧near“保留最高隔离split”规则不属于结果驱动修改 | backend identity定义、Primary retention原则与evaluation-clean方向冻结；near量化精度、后续training sampler和Unknown算法仍只能通过新增Decision或预注册实验修订 | 不修改DEC-0008/0009冻结的Edge/IoT角色、Near/Far/Mixed及IoT K/U、60秒session、capture内chronological 70/15/15+gap、Capture-3 unknown pool、`PRIMARY_VIEW=NO_SERVICE_VIEW`、past-only context或U_final隔离；旧over-dedup资产必须标为`superseded_overdedup_run`并全量重建 |

生效关系：DEC-0001至DEC-0011作为历史记录完整保留。DEC-0005中的sample-level信息隔离原则继续有效；其中CICIoMT立即主线、传统模型主分类和Tree-aware Reviewer相关安排由DEC-0006/0007替代，未冻结主数据与第二数据集、可选多数据集实验和N=8/16/32候选口径由DEC-0008替代；IoT-23“待验收”状态和Adapter未实测口径由DEC-0009替代；本地继续生产数据和“服务器只接收冻结派生数据”的安排由DEC-0010替代；正式训练精度/模式与Unknown评分接口以DEC-0011为准；Production Primary去重、cross-split exact/near collision和evaluation-clean sensitivity以DEC-0012为准。历史Decision中的QLoRA与旧相似性处置原文只保留当时状态，不再代表当前默认路线。
