# 网络流量开放识别与自适应取证智能体研究计划（权威详细版）

> 文档状态：Canonical / Authoritative
>
> 冻结日期：2026-08-12
>
> 解释顺序：本文件是最高研究语义权威；`docs/training/near_mainline_training_protocol_v1.md`是训练/Open-world执行权威，Agent架构文档是Runtime/Supervisor/RAG/Memory设计权威，时间表、简版和交接不得覆盖它们。审计产生新证据但尚未写入Decision Log时，不自动改变研究方案。

## 0. 当前冻结方案概览

### 0.1 研究问题与正式主链路

本文研究：**后训练大语言模型能否直接理解会话级网络证据并完成已知攻击的细粒度/粗粒度分类，独立开放集评分层能否据其模型信号可靠识别Unknown；在单次证据不足时，受约束Agent能否按需扩展包序列、历史关联、应用层证据和安全知识，并在效果、风险与成本之间选择接受、重分类、拒识或新类接入。**

正式主链路冻结为：

```text
网络流量样本
→ 会话级混合表示
→ Qwen3.5-9B共享语言表示
→ Fine Classification Head输出Known fine logits
  + 原始LM Head输出Evidence State
→ deterministic fine→coarse mapping
→ Independent Unknown Scoring / Calibration
→ DeepSeek Flash Supervisor在Runtime约束下按需取证
→ Qwen重新评价或输出Known / Coarse / Unknown / Abstain
→ 可选人工标注与Class Memory新类注册
```

Qwen第一次就直接读取网络证据，是正式主分类模型，不再作为LightGBM/XGBoost的Reviewer。正式trained model使用冻结Qwen base、可训练LoRA与一个简单Linear Fine Classification Head；Fine Head是唯一正式fine决策源，coarse由冻结映射得到，LM Head只生成简短Evidence State而不并行生成另一份fine label。传统模型只承担基线、诊断与可选消融，不决定哪些样本调用Qwen，也不向Qwen提供必需概率。

正式Unknown不是第K+1类，也不由未经验证的LLM自报概率决定。它在Near SFT和RLAIF-GRPO后冻结主Qwen，使用Known validation与`U_dev`比较margin、entropy、energy和prototype distance等独立方法；`U_final`只在算法、阈值及所有会影响最终推理的Prompt、sanitizer、RAG和Supervisor配置冻结后打开。

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

当前Agent主方案采用DeepSeek Flash Supervisor读取Qwen Traffic Expert输出和Evidence State，并在deterministic Python Runtime约束下每轮选择一个合法动作。Supervisor不是第二分类器，不能覆盖Fine Head；Runtime负责Schema、capability、预算、最大轮数、去重、信息隔离、故障处理和Trace。DeepSeek Flash是当前可配置provider default，运行manifest必须记录实际endpoint/model ID；Teacher、Judge与Supervisor的Prompt、Schema、权限和日志严格分离。

Agent的基本闭环进一步明确为`Evidence State → 识别缺失证据 → 选择对应证据源/合法动作 → 更新状态 → 重分类或停止`。动态性来自根据当前证据缺口、可用能力和剩余预算选择下一步，而不是在Qwen不确定时无差别调用全部工具；这一细化不改变Qwen首次分类、独立Unknown层和Agent所在位置。

架构回溯、Edge-IIoTset Phase 2客观审查、双数据集最终可行性验收和Production Data Freeze已经完成。生产级`CanonicalSessionRecord`、两个Adapter、60秒会话构造、K/U、support/query、provenance guard、字段白名单与training manifest均已冻结并通过postfix审计（带已记录限制）。随后完成的paper-grade split revision以`CONSTRAINED_CHRONOLOGICAL_BOUNDARY_V2`替换Edge旧physical assignment，并以`CLASS_BALANCED_DIVERSITY_AWARE_SFT_SELECTION_V1`的`PLAN_B`物化三套preset的SFT候选；该修订不改变canonical identity、sessionization、label或Near/Far/Mixed成员。deterministic Runtime foundation及provider-neutral Traffic Expert/Supervisor backend preparation已经实现并通过synthetic/fake-provider工程审计；`production_runtime_adapter_v1`现已将v2 `initial_model_views`及packet/temporal/relation真实资产按exact allow-list封装为Runtime `EvidenceItem`/`CapabilityStatus`，并通过真实数据、跨层泄漏、phase/U_final和完整回归审计。Phase B现已将Application Evidence、sanitized payload和generic Knowledge RAG从contract-only推进为仅覆盖合法Near K-known TRAIN的Git-external sidecar/KB/index；formal Agent Runtime tool wiring仍未完成。官方`Qwen/Qwen3.5-9B` raw模型已在独立text-only vLLM环境完成provider/backend/真实Production受控smoke；`RAW_SMOKE_TRAFFIC_EXPERT_PROMPT_V0`只证明基础设施连通性。Training Protocol v1现已实现Transformers/PEFT harness、dynamic Linear Fine Head、正式Prompt/schema、`ATTENTION_MASKED_MEAN_V1`、真实LoRA inventory与`COMPACT_SAFE_EVIDENCE_V1`，并通过真实9B两步dry-run和save/load/resume smoke。DeepSeek provider、角色隔离、Teacher Prompt V3及250条分层pilot已经通过；V3 bulk完成22,957/22,957且quarantine为0，最终V2 SFT corpus、pair/manual/token audit与formal launcher preflight均PASS。DEC-0020正式解耦classification CE资格与Evidence sufficiency：每个合法TRAIN K-known session恰有一个真实primary state获得CE，受控低证据auxiliary不获得CE；Teacher sufficiency只监督当前Evidence是否足以停止额外取证。Qwen正式训练、Unknown算法和Agent正式实验/benchmark尚未开始。

### 0.6 ONE_MAINLINE_FIRST与协议权威

DEC-0019冻结`ONE_MAINLINE_FIRST`：第一条完整论文路线只执行Edge Near，seed为`20260809`，Near `K_known`为Backdoor、DDoS_HTTP、DDoS_TCP、MITM、Normal、Password、Port_Scanning、Ransomware、SQL_injection、Uploading、Vulnerability_scanner；`U_dev`为DDoS_ICMP、OS_Fingerprinting；`U_final`为DDoS_UDP、XSS。SFT继续使用已冻结PLAN_B的16,979个唯一`K_known ∩ train`候选，不重新搜索PLAN A/B/C。

Near先完成Raw/传统基线、classification-first Multi-task SFT、RLAIF-GRPO加classification CE保持、Independent Unknown、Basic/Fixed Full/RulePolicy/DeepSeek Flash Supervisor、Experience Memory和1/5/10-shot Class Memory闭环。只有`NEAR_MAINLINE_COMPLETE=true`后，才恢复Far、Mixed、IoT-23、Pure Generative SFT、DPO、Tokenizer/QLoRA/thinking、Low-Resource stress、Learnable Agent Policy RL或continual LoRA等deferred轨道。

[Near-First Training and Open-World Protocol v1](../training/near_mainline_training_protocol_v1.md) 已冻结架构、权限、隔离、训练阶段和checkpoint lineage；Phase B已按train-only小规模流程选择pooling、LoRA v1、serialization和SFT初始配置，其中LR、epochs、gradient accumulation与evidence loss weight继续标记`VALIDATION_TUNABLE`。Unknown threshold、formal RAG top-k和Supervisor budget仍须在各自合法阶段选择。当前外部高能力默认是可配置的DeepSeek Flash，并严格区分Teacher、RLAIF Judge与formal Supervisor三个逻辑角色。Codex只负责工程、编排、调用、审计和报告，不是正式Teacher/Judge模型。

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
3. 构建由deterministic Runtime约束、DeepSeek Flash formal Supervisor决策且具有显式状态、动作、预算、停止和轨迹记录的Adaptive Decision Agent，并与强Static、RulePolicy及可选可学习策略公平比较；
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

**Edge-IIoTset承担完整方法开发与主实验。** 在其原生标签下运行Qwen独立闭集及coarse/fine分类、Near/Far/Mixed Unknown、传统模型强Unknown基线、传统模型Unknown后随机分配新标签的诊断、Agent动态扩展包/时间上下文/应用证据/RAG、1/5/10-shot新类接入、RulePolicy、强Static、DeepSeek Flash formal Supervisor、可选LearnablePolicy以及成本、延迟、恢复和输出合法性评价。

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

### 2.5 Edge paper-grade physical split与SFT候选层

Edge完整Production Dataset继续保留真实session分布，Primary dedup只依据immutable backend identity。类别不平衡、模型视图重复或SFT算力预算不得反向删除canonical session；完整数据仍服务真实分布统计、evaluation、Unknown、past-only Temporal/Graph Context、sensitivity和复现审计。

正式Edge physical assignment采用`CONSTRAINED_CHRONOLOGICAL_BOUNDARY_V2`：每个capture内部按`timestamp_start, sample_id`排序；大capture使用70%/15%/15%的session-rank时间边界，小capture在预先固定的候选网格内以evaluation support、合法train diversity、比例与quarantine为顺序做deterministic boundary search；任何跨边界session以及边界两侧合计5秒local embargo内的session均进入quarantine。禁止random shuffle或跨capture混合切分。split revision只重建assignment及其依赖资产，不重新TShark、canonical或sessionize；7,619,032个Edge stable identity的计数、有序SHA256和唯一性在修订前后完全一致。正式新分配为train 5,294,777、validation 1,073,539、test 1,110,343、quarantine 140,373；ZERO从1降为0，CRITICAL_LOW从2降为0，因此`PAPER_EVALUATION_READINESS_GATE=PASS_WITH_LIMITATIONS`。MITM与OS_Fingerprinting的validation/test仍属LOW；DDoS_UDP和OS_Fingerprinting因train evidence diversity不足标记为`STRUCTURALLY_INSUFFICIENT_KNOWN`，这些只是分析/readiness状态，不改变任何K/U角色。

Phase A必须报告而不能把model-view equality误作identity：相对旧split，Edge-only exact cross-split collision group增加104、near-signature collision group增加303，但backend identity cross-split leakage保持0；Primary继续保留现实重复行为，`EXACT_EVAL_CLEAN`与`NEAR_EVAL_CLEAN`只作为train不变的evaluation sensitivity。候选比较和最终矩阵保存在`reports/edge_split_revision_v2/phase_a_split_candidate_comparison.json`。

SFT训练候选与完整Production资产严格分层。`CLASS_BALANCED_DIVERSITY_AWARE_SFT_SELECTION_V1`只允许`K_known ∩ physical train`进入候选，禁止validation、test、`U_dev`或`U_final`。每类先覆盖distinct near groups，再覆盖distinct exact groups，之后才允许每个exact group内有限且deterministic的multiplicity；真实`sample_id`保持唯一，不复制JSONL伪造样本。PLAN_A/B/C分别比较较小、平衡中等和较大高覆盖预算；当前选择`PLAN_B`，Near/Far/Mixed分别物化16,979、15,895和15,404条候选。该采样用于减少高重复大类对examples、tokens、loss contribution和gradient updates的不成比例支配，不意味着LLM为每类分配固定参数，也不要求所有类机械等量。renderer与Tokenizer尚未冻结，因此token量仅为estimate。

Edge标签正式语义保持`DIRECT_EVIDENCE_UNANIMOUS_ONLY`优先；当前官方CSV缺乏稳定frame number或绝对frame time，无法形成formal packet/frame direct mapping，故7,619,032个session使用`VERIFIED_CAPTURE_FALLBACK`。该fallback只在PCAP/CSV hash、100%单标签purity、expected label一致和session不跨capture全部通过时成立；24/24 capture通过，conflict与unmatched均为0。论文必须描述为official single-label capture + verified companion CSV + within-capture session reconstruction，不得声称人工session-level ground truth。

## 3. K/U预注册与信息隔离

### 3.1 三类集合

- `K_known`：覆盖多种coarse、包含易难类且样本充足；可进入Qwen SFT以及传统模型基线训练。
- `U_dev`：约2—4类，仅用于Unknown算法、阈值、证据扩展策略、RulePolicy/Supervisor策略开发、可选LearnablePolicy和合法RAG路由开发，不进入主分类模型监督。
- `U_final`：最终评测前完全隔离；不得进入SFT/DPO、Prompt示例、known-only RAG、Unknown算法选择、阈值开发、Agent/策略训练、错误驱动调参或人工挑选。

正式训练前预注册Near、Far、Mixed多套组合与随机种子，全部报告，不依据结果挑选最优组合。

### 3.2 三阶段生命周期

**阶段A：Unknown Rejection。** Qwen主分类SFT只使用`K_known`监督数据和known-only冻结知识；Fine Head输出唯一正式Known fine logits，coarse由冻结映射得到，LM Head输出证据充分度、supporting/missing evidence及可供open-set计算的模型信号；冻结的Unknown Scoring / Calibration层再产生正式Unknown决策。Unknown算法和阈值只能使用`K_known`与`U_dev`开发，`U_dev`标签不得作为主分类模型监督进入SFT。

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

Qwen3.5-9B直接读取Session Evidence Card。正式trained model由冻结base、可训练LoRA、一个简单Linear Fine Classification Head和保留的原始LM Head组成。Fine Head读取`h_session`并输出`|K_known|` logits，是trained model唯一正式fine分类源；不增加Coarse Head，coarse由冻结fine→coarse映射得到。原始LM Head只输出brief behavior summary（有价值时）、supporting/missing evidence、evidence sufficiency、gap type和backoff相关Evidence State，不生成竞争性的fine label。

Pooling已在last meaningful prompt position、无新增token的explicit prompt ending和attention-masked mean之间用22个合法K-known TRAIN representation比较，冻结为`ATTENTION_MASKED_MEAN_V1`；该选择不修改tokenizer或embedding。Qwen3.5真实`named_modules()` inventory冻结248个LoRA targets，覆盖Gated DeltaNet、Gated Attention和FFN，不能只沿用旧模型的q/k/v/o假设。base、vision、embedding和原始LM Head冻结；只训练LoRA与Fine Head。

Training #1是classification-first Multi-task BF16 LoRA SFT：`L_SFT=lambda_cls*L_classification+lambda_ev*L_evidence_generation`，official/verified GT只监督Fine Head classification，Evidence State来自确定性规则、受控mask/stage、DeepSeek Flash Teacher、自动一致性过滤和有界人工审查。Teacher可把GT作为不可修改上下文，但不得决定标签或创造Observation。

`CLASSIFICATION_SUFFICIENCY_DECOUPLED_V1`冻结两个互不门控的变量：`classification_ce_eligible`由TRAIN、K-known、verified GT、无泄漏/U_final、合法provenance与deterministic primary-state protocol决定；`evidence_sufficient`由Teacher/Evidence-State表示当前可见证据是否足以作出有用分类并停止额外取证。合法primary即使`sufficient=false`仍计算CE；人为删除关键证据的controlled auxiliary只训练Evidence LM并mask CE。GT只存在于backend target，不进入serialized input、Prompt、RAG query、Payload或任何model-visible metadata，因此该监督不是label leakage。

Training #2从SFT checkpoint clone/reference后执行`RLAIF-GRPO + classification CE preservation`。Fine Head CE保持Known分类并继续更新Fine Head/LoRA；GRPO只优化随rollout变化的grounding、evidence sufficiency、missing evidence、gap、backoff/abstention、幻觉惩罚、schema和brevity。Fine Head correctness对同一input的rollout group是常数，不能声称为主要组内GRPO reward。DeepSeek Flash Judge在线/异步评价current-policy rollout，RL Prompt Pool固定来自合法Near `K_known TRAIN` Evidence states；DPO保持deferred。

Raw Qwen没有Fine Head，可用生成式分类Prompt形成raw baseline；它与custom-head trained model接口不完全相同。完整训练权限、阶段、可调参数与checkpoint lineage以`docs/training/near_mainline_training_protocol_v1.md`为准。

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

当前正式Agent主方案为DeepSeek Flash formal Supervisor；实现面向`SupervisorBackend`抽象，以便在线服务与未来本地兼容模型替换。`RulePolicy`作为必须保留的强可复现baseline，`Strong Static`继续提供预先冻结且合理的固定取证次序；`LearnablePolicy`仅为可选扩展。各策略共享Evidence State、动作白名单、工具、信息域和预算合同。

强Static Pipeline必须使用相同的Qwen、工具、信息域和最大预算，并包含合理的固定取证顺序、retry、fallback和validator。固定全证据只代表在共同预算内预先提供全部指定证据的上界或消融，不等同于Adaptive Agent。只有Supervisor或其他动态策略在预算匹配条件下提高任务目标适应性、任务成功、恢复或utility-cost，才能说明动态策略有价值；不能通过给Agent更多信息、更多调用预算或故意削弱Static/RulePolicy获得结论。

### 5.3 轨迹与反馈

每个样本保存`sample_id → evidence state → Qwen output → action/reason → tool input/result → next state → stop reason → final prediction → unknown score → cost/latency → truth → error source → update action`。获得真实标签后，将错误归因到SESSION_CONSTRUCTION、PACKET_EVIDENCE、CONTEXT_SELECTION、APPLICATION_EVIDENCE、RAG_QUERY/EVIDENCE、LLM_CLASSIFICATION、UNKNOWN_DECISION、POLICY、CLASS_MEMORY、LABEL_SCHEMA、DATA_LEAKAGE或TOOL_FAILURE，只更新相关组件。

组件级归因同时构成反馈边界，而不只是论文统计：**Level 1样本级适应**只为当前样本取得新的合法证据，不更新参数；**Level 2策略级适应**面向相似状态下反复选错工具或过早停止，更新RulePolicy规则、离线验证并版本化Supervisor Prompt/策略，或更新可选LearnablePolicy，不直接归因于Qwen；**Level 3模型级适应**仅在充分且正确的证据已提供、Qwen仍持续出现同类理解或分类错误时，才考虑补充SFT数据，DPO仍受既定条件Gate约束。Unknown阈值/校准错误应更新Unknown scoring/calibration，RAG错误应优先修复query、retrieval或知识条目。禁止采用“所有错误均回流SFT”的无归因路线。

### 5.4 Runtime与Memory边界

deterministic Runtime负责Qwen、Supervisor和工具调用，以及Action验证、capability、预算、最大轮数、request去重、future leakage防护、Memory权限、失败处理与结构化Trace；LLM不得绕过Runtime。Supervisor只接收model-safe Evidence State、Qwen简短分析、Unknown状态、sanitized evidence、工具状态、预算/历史和validated experience，不接收真实IP、绝对时间、capture/scenario或dataset identity、ground truth和完整原始Payload。

Experience Memory保存经可靠反馈验证的`State→Action→Outcome`经验；train可验证后写入，validation与`U_dev`默认不写入，TEST/`U_final`冻结只读。Class Memory只保存人工确认的新类别support，必须与Experience Memory分离；few-shot注册默认不立即更新Qwen权重。独立Agent Growth Stream仅为可选实验，主test不得边评测边学习。具体Memory embedding、index、top-k和capacity仍未冻结。

## 6. 训练边界与启动条件

训练/Open-world执行权威是`docs/training/near_mainline_training_protocol_v1.md`。Architecture/permission protocol已冻结，但`SFT_RUN=false`、`RL_RUN=false`、`UNKNOWN_ALGORITHM_FROZEN=false`。

正式第一主线只使用Near PLAN_B的16,979个唯一`K_known ∩ physical train`候选；完整Production分布不因训练预算改变。阶段0–6可表示Initial、9–16包、Temporal、Graph、Application、Sanitized Payload和Knowledge RAG，但只有真实AVAILABLE且通过model-safe contract的Evidence才可生成；同一session使用bounded stage multiplicity和diversity-aware sampling。

SFT前必须实现training-side Transformers/PEFT harness，冻结`SERIALIZATION_V1`、Prompt/response schema v1、pooling contract、LoRA module inventory assertion及Application/Payload/RAG Evidence Contract。官方Tokenizer保持主线；先比较current与compact safe serialization，不训练新Tokenizer。vLLM继续服务raw inference/smoke，不能因OpenAI-compatible API不暴露hidden state而放弃Fine Head。

Training #1训练LoRA+Fine Head的classification-first Multi-task SFT；Training #2从独立保存的SFT checkpoint继续执行RLAIF-GRPO并以classification CE防漂移。Teacher/Judge/Supervisor均使用当前可配置DeepSeek Flash default，但作为权限、Prompt、Schema和日志隔离的三种角色。DeepSeek不会提前生成完整RL dataset；current policy每步产生rollout group，Judge评价后形成group-relative objective。

Near primary checkpoint冻结后，Independent Unknown只用Known validation与`U_dev`比较margin、entropy、energy和prototype distance；优先不训练新网络，small learned Unknown head仅为backup。`U_dev`不作为Unknown第K+1类监督Qwen，`U_final`不进入任何开发。Novel class第一版使用Class Memory/prototype，不立即continual LoRA。

LoRA rank/alpha/dropout、LR、batch、epochs、loss weight、GRPO group size/reward weight、pooling、Unknown threshold、RAG top-k和Supervisor budget属于小范围**VALIDATION TUNABLE**；不得用formal test或`U_final`，不得大网格搜索，也不得因结果不理想修改K/U、split、PLAN_B或总体架构。

## 7. 四组核心实验

### 实验一：LLM独立分类与传统基线

比较Logistic Regression、Random Forest、LightGBM/XGBoost、原始Qwen3.5-9B和后训练Qwen3.5-9B。任务覆盖Benign/Malicious、原生coarse和fine分类。所有模型使用可公平比较的数据划分；传统模型读取其合法表格特征，Qwen读取冻结的会话级混合表示。

报告Macro-F1、分类别指标、混淆、校准、速度和成本，回答后训练LLM独立分类的能力、代价和边界。传统模型是强基线，不是Qwen前置模块。

### 实验二：开放集与自适应取证主实验

传统模型开放集基线与单次Qwen+冻结Unknown继续作为必要参照；Agent部分按四个因果问题组织：

| 问题 | 主要比较与控制 |
| --- | --- |
| Q1 更多证据本身是否有价值 | `Basic Session Evidence` vs 在共同最大预算内预先冻结的`Fixed Full Evidence` |
| Q2 动态按需取证是否优于固定方式 | `Fixed Full Evidence`、`Strong Static`、`RulePolicy`、DeepSeek Flash formal Supervisor及可选`LearnablePolicy`使用相同Qwen、工具、信息域和最大预算 |
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

### 实验五（OPTIONAL）：Low-Resource Unknown Stress Test

该实验是预注册的辅助压力测试，不属于当前主线完成条件，不改变Near/Far/Mixed，也不与其主结果混合平均。它研究数据稀缺驱动的Unknown难度是否不同于主实验的semantic near/far难度：将一个或少数low-resource fine class从该实验对应的SFT监督中完全held out，评价系统能否避免高置信度误归Known、由Independent Unknown识别，并在少量人工support后通过Class Memory改善后续识别。

候选只能依据任何Qwen运行前的session support、exact diversity、near diversity和coarse-parent结构预注册，禁止根据`U_final`或模型结果事后挑选最差类别。当前`LOW_RESOURCE_UNKNOWN_CANDIDATE_POOL`为Backdoor、DDoS_UDP、MITM、OS_Fingerprinting、Ransomware和XSS；它是候选池而不是冻结最终held-out集合。若执行，至少分别报告数据允许的`LOW_RESOURCE_SHARED_PARENT`与`LOW_RESOURCE_ABSENT_PARENT`情况，并报告Unknown AUROC/AUPR、FPR@target TPR、unknown recall、误分类去向、backoff/abstain、Agent evidence usage和few-shot registration performance。流程继续使用同一Independent Unknown、Supervisor、Runtime和Class Memory，不新增专门的low-resource Agent；状态保持`PLANNED_OPTIONAL_NOT_RUN`。

## 8. 评价、复现与统计

- 每套Unknown preset至少使用多个随机种子；具体数量在数据与算力确认后冻结。
- `U_final`只运行冻结系统，结果不回流模型、阈值、Prompt、RAG、策略或训练。
- 保存数据、代码、模型、Prompt、RAG、证据序列化和工具配置指纹，以及run ID、split manifest、失败和resume记录。
- Agent除分类指标外还报告end-to-end task success、evidence/tool选择成功、recovery、budget compliance和output validity，并分别统计证据请求率、Qwen调用次数、Supervisor轮数、RAG/各工具调用次数、延迟、Token/API成本和utility-cost曲线。
- 比较Static与Agent时必须使用同一Qwen、工具、信息域和最大预算，并进行budget-matched主比较；成本受限子集须在实验前固定，不按模型结果定制。固定全证据、Static、Rule与Learnable的资源差异须单独披露，不能把额外调用量解释为策略增益。
- 错误分析须同时给出错误来源和组件级处置去向，区分样本级取证、策略更新、Qwen SFT、Unknown校准及RAG修复，避免把不同组件的问题汇总为单一模型误差。
- 会话和past-only关联必须在训练、验证、测试内部独立构造，并检查固定身份、时间和来源捷径。

## 9. 时间与依赖

`ONE_MAINLINE_FIRST`取代同时展开Near/Far/Mixed/IoT-23的旧四周并行排期。Phase A和Phase B均已完成；当前只完成D–E的final pre-training acceptance与corpus冻结，本次文档同步不授权自动启动任何训练或benchmark。

| Phase | 工作 | 状态/退出条件 |
| --- | --- | --- |
| A | Production、v2 split、PLAN_B、Safe Adapter、Evidence Fidelity、官方raw Qwen部署 | **COMPLETE / PASS_WITH_LIMITATIONS** |
| B | training-side harness、pooling、LoRA inventory、serialization v1、Prompt/schema v1、Application/Payload contracts、RAG Evidence Contract | **COMPLETE / PASS_WITH_LIMITATIONS** |
| C | Near Raw Qwen与强传统baseline | 未开始；可复现manifest |
| D–E | 多stage Near SFT corpus；DeepSeek Flash Teacher、自动一致性过滤、有界人工审计 | **COMPLETE / PASS**；22,957 records，仅合法K_known TRAIN |
| F–G | Training #1 Multi-task LoRA SFT及validation | 未开始；Checkpoint A |
| H–J | 固定RL Prompt Pool；Training #2 RLAIF-GRPO + classification CE及validation | 未开始；Checkpoint B |
| K–M | 冻结primary Qwen；Known validation + U_dev开发并冻结Independent Unknown | 未开始；U_final仍sealed |
| N | 首次U_final open-set evaluation | 仅在全部相关开发配置冻结后一次性打开 |
| O–P | 完成Application/Payload/RAG；Basic、Fixed Full、RulePolicy、DeepSeek Flash Supervisor | 未开始；相同信息域/预算 |
| Q–R | Experience Memory；1/5/10-shot Class Memory | 未开始；test/U_final只读 |
| S | Near mainline complete | `NEAR_MAINLINE_COMPLETE=true` |

若O/P中仍有会影响U_final route的未冻结配置，必须在N之前完成其validation-safe实现与冻结；阶段编号不授权看过U_final后再调sanitizer、RAG、Supervisor或Memory。只有Phase S后才恢复Far、Mixed、IoT-23和其他deferred ablation。

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
| 应用层或Payload暂不可用 | 中间阶段fail closed并显式声明缺失；Near最终完成前必须实现并冻结sanitizer、能力边界与捷径审计，否则不得宣称完整方法 |
| BF16 LoRA收益小或显存/框架受限 | 保留原始Qwen基线、缩小高价值样本；必要时降级为QLoRA；取消DPO、27B和继续预训练 |
| 实验预算不足 | 只推进Near ONE_MAINLINE_FIRST与其必要baseline；Far、Mixed、IoT-23、DPO、27B和扩展消融继续deferred，Phase S后再恢复 |

## 11. 当前已完成、未完成与下一步

已完成：Production Data Freeze与Git冻结；Edge `CONSTRAINED_CHRONOLOGICAL_BOUNDARY_V2`（train 5,294,777、validation 1,073,539、test 1,110,343、quarantine 140,373，identity leakage 0）；Near/Far/Mixed PLAN_B候选与label provenance；deterministic Runtime、provider-neutral backend和`production_runtime_adapter_v1`；Evidence Fidelity Gate；官方`Qwen/Qwen3.5-9B` revision `c202236...`的16/16文件、独立vLLM BF16 text-only服务、六类Production、packet 9–16与past-only Temporal raw smoke。上述是基础设施，不是论文benchmark。

当前online Runtime capability：Initial AVAILABLE；packet 9–16 AVAILABLE_PER_SESSION；Temporal AVAILABLE且past-only；Relation AVAILABLE_WITH_LIMITATION；Application、Sanitized Payload和Production Knowledge RAG的formal online tool wiring仍UNAVAILABLE。与此同时，三者的合法Near K-known TRAIN sidecar/KB/index已作为Git-external预训练资产冻结并进入最终corpus；不得把training asset readiness误写成online Runtime已实现。

DEC-0019与Training Protocol v1冻结Near-first及总体架构；Phase B已经实现training-side harness、Fine Head、Prompt/schema/serialization、TRAIN-only Application/Payload/RAG sidecars、角色隔离和真实Qwen smoke。DEC-0020进一步冻结classification/sufficiency解耦：Fine Head学习当前Evidence下的known-class posterior，Evidence State学习支持度、缺口及是否值得继续取证；只有controlled lower-evidence auxiliary mask CE。

`SFT_RUN=false`；`RL_RUN=false`；`UNKNOWN_ALGORITHM_FROZEN=false`。Final pre-training acceptance已完成：Teacher V3 bulk、final corpus/audits、formal config/launcher preflight与回归全部PASS；该完成状态不产生训练checkpoint或论文结果。

**`READY_TO_START_FORMAL_NEAR_SFT=true`，下一动作仅为`START_FORMAL_NEAR_MULTI_TASK_SFT`。** 本readiness任务不自动启动SFT；GRPO、Unknown、U_final或Agent实验仍不授权。

## 附录A：端到端执行链路速查

本节只将前述冻结方案按先后顺序汇总，不替代数据Gate、模型、Agent、实验和Decision Log中的详细约束。

### A. 研究项目执行链路

1. **已完成数据与工程Gate：**Edge/IoT角色、Production Freeze、v2 chronological split、K/U、support/query、PLAN_B、Safe Adapter、Evidence Fidelity和raw Qwen部署。
2. **ONE_MAINLINE_FIRST：**只推进Near seed `20260809`，保持指定K/U与16,979个PLAN_B候选。
3. **Phase B readiness：**实现training-side harness，冻结pooling、LoRA inventory、serialization、Prompt/schema及Application/Payload/RAG Evidence Contract。
4. **Phase C baseline：**在合法model-safe输入上运行Raw Qwen、LightGBM、XGBoost、Random Forest等强baseline。
5. **Phase D–G SFT：**构造bounded multi-stage corpus，由规则+masking+DeepSeek Flash Teacher+一致性过滤+有界人工审查生成Evidence targets，训练Checkpoint A并只用validation选择。
6. **Phase H–J RLAIF：**冻结Near K_known TRAIN RL Prompt Pool，由current Qwen生成rollout group，deterministic reward与DeepSeek Flash Judge形成GRPO信号，同时用classification CE保持Fine Head，生成独立Checkpoint B。
7. **Phase K–M Unknown：**冻结Checkpoint B，只用Known validation+U_dev选择Independent Unknown算法/阈值，不把Unknown作为第K+1类训练Qwen。
8. **Phase N U_final：**在Prompt、serialization、sanitizer、RAG、Supervisor、Memory及Unknown都冻结后第一次打开DDoS_UDP/XSS；结果不得回流。
9. **Phase O–P Agent：**完成按需Application/Payload/RAG，按相同Qwen、信息域和预算比较Basic、Fixed Full、RulePolicy、DeepSeek Flash Supervisor。
10. **Phase Q–R Memory/new class：**先无Experience Memory，再做verified TRAIN experience；对Unknown取得1/5/10-shot人工support后用Class Memory/prototype注册，不立即continual LoRA。
11. **Phase S：**冻结Near end-to-end结果，之后才恢复Far、Mixed、IoT-23及其他ablation。

```text
Raw Qwen → Near Multi-task SFT → Checkpoint A
→ RLAIF-GRPO + Classification CE → Checkpoint B
→ Independent Unknown calibration → Agent integration → Class Memory
```

### B. 系统实际识别链路

1. Production解析packet并重建不跨capture的双向60秒session，backend身份和GT不进入模型。
2. `production_runtime_adapter_v1`输出前1–8包、whole-session safe summary与真实capability状态。
3. Qwen共享语言backbone产生`h_session`；Fine Head输出Known fine logits，coarse由确定性映射得到，LM Head输出简短Evidence State。
4. Independent Unknown根据冻结logits/representation信号评分，不使用LLM自报Unknown或K+1训练类。
5. DeepSeek Flash Supervisor读取model-safe Evidence、Fine Head结果、Evidence State、Unknown、capabilities、budget/history；它不直接改fine label。
6. deterministic Runtime每轮只执行一个合法且非重复的packet 9–16、Temporal、Graph、Application、Sanitized Payload或Knowledge RAG动作。
7. Observation与Knowledge严格分离；Payload/RAG均为有界untrusted evidence，RAG不能发明当前session observation。
8. 新Evidence触发Qwen与Unknown重新评价，循环直至Fine、Coarse Backoff、Unknown或Abstain。
9. 对已拒识Unknown，只有合法human/oracle support才能`REGISTER_NEW_CLASS`并写入Class Memory。
10. Runtime保存结构化result、动作、Evidence、Unknown、成本、延迟、provider identity和可审计Trace。

```text
Production Session → Runtime Safe Adapter → Evidence Stage
→ Qwen Traffic Expert → Fine Head + LM Evidence State
→ Independent Unknown → DeepSeek Flash Supervisor
→ Deterministic Runtime Evidence Tool → Qwen re-evaluate
→ Known Fine / Coarse / Unknown / Abstain → optional Class Memory
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
| 2026-08-11 | DEC-0013 | Production physical split以wall-clock span 70/15/15和长session gap为主，导致Ransomware validation=0并令多个小类evaluation support不足 | 冻结Edge `CONSTRAINED_CHRONOLOGICAL_BOUNDARY_V2`：capture内按时间与stable sample ID排序，complete-session crossing quarantine加capture-local 5秒embargo；小capture使用pre-model deterministic readiness search，大capture使用70/15/15 rank boundary；只重建split-dependent资产 | 7,619,032条真实Production session的只读候选比较显示v2将ZERO 1→0、CRITICAL_LOW 2→0，identity leakage=0；selected assignment与正式manifest完全一致。Edge-only exact/near collision分别增加104/303，作为不改train的sensitivity披露而非identity删除依据 | physical split规则冻结；若未来修订必须在任何模型结果前新增Decision | canonical identity、60秒session、labels、Near/Far/Mixed、IoT角色与Primary identity dedup均不变；`PAPER_EVALUATION_READINESS_GATE=PASS_WITH_LIMITATIONS` |
| 2026-08-11 | DEC-0014 | DEC-0012只规定未来由独立training sampler控制规模，尚未冻结SFT候选的class/diversity协议 | 冻结`CLASS_BALANCED_DIVERSITY_AWARE_SFT_SELECTION_V1`并选择`PLAN_B`：仅`K_known ∩ physical train`，依次覆盖near group、exact group和有限group内multiplicity；sample ID唯一，完整Production分布不变 | pre-model PLAN_A/B/C simulation显示百万级高重复类若按raw frequency进入训练会支配examples/tokens/loss/gradient updates；PLAN_B在小类合法evidence与总体BF16 LoRA规模之间提供中等折中 | policy、eligibility、seed和PLAN_B候选manifest冻结；renderer/token estimate仍待训练前冻结 | Near/Far/Mixed候选分别16,979/15,895/15,404；validation/test/U_dev/U_final禁止进入SFT；未来oversampling必须单独记录权重而不得复制sample |
| 2026-08-11 | DEC-0015 | Edge Adapter的capture fallback已有provenance guard，但本轮split/SFT冻结前缺少最终统一确认 | 正式确认label assignment仍为direct evidence unanimous only优先；direct mapping不可用时，仅在PCAP/CSV hash、100% purity、expected label和within-capture isolation均通过后使用`VERIFIED_CAPTURE_FALLBACK` | 24/24 official capture通过；14 attack和10 Normal companion CSV均为预期单标签；7,619,032 session fallback、0 conflict、0 unmatched；官方CSV无稳定frame number/absolute frame time，故不得声称人工session-level ground truth | provenance policy冻结；若官方发布可精确frame mapping的新资产可新增Decision升级direct evidence | 论文措辞固定为verified single-label capture provenance + within-capture session reconstruction；不改变标签Schema |
| 2026-08-11 | DEC-0016 | 主Near/Far/Mixed只研究semantic near/far unknown，尚未单独预注册真实低资源类别的scarcity-driven Unknown问题 | 登记`Low-Resource Unknown Stress Test`为`OPTIONAL / PRE-REGISTERED EXPERIMENT IDEA`，候选仅依pre-model support与exact/near diversity选取，单独报告shared-parent/absent-parent、Unknown与few-shot registration结果 | v2 readiness确认DDoS_UDP、MITM、OS_Fingerprinting为LOW_RESOURCE_KNOWN，其中DDoS_UDP与OS_Fingerprinting为STRUCTURALLY_INSUFFICIENT_KNOWN；需要区分数据稀缺与语义距离，但不应阻塞主论文或事后挑类 | 非主线、可不执行；若执行须在模型结果前冻结最终held-out类和seed | 不改变Near/Far/Mixed或K/U；状态`PLANNED_OPTIONAL_NOT_RUN`；使用同一Independent Unknown、Supervisor与Class Memory，不新增Agent |
| 2026-08-11 | DEC-0017 | Production `initial_model_views`与Runtime合同之间只有计划中的轻量adapter边界，尚不能证明raw backend row、GT/K-U/split与source identity不会跨层进入Traffic Expert/Supervisor | 冻结`production_runtime_adapter_v1`：exact source allow-list→字段级model-safe校验→typed `EvidenceItem`/`CapabilityStatus`；backend provenance严格分离；1–8包+whole-session summary、9–16包、strict past-only temporal与匿名relation使用已物化资产；Application/payload/production RAG不可用时真实返回UNAVAILABLE；U_final只在外层formal-final授权后进入只读Runtime | 真实v2六类smoke、past/no-past、packet expansion、sensitive value/renderer/backend bypass、phase/U_final、determinism与254项完整回归均通过；不需要PCAP/TShark/canonical重建，也没有调用模型 | adapter/evidence schema版本冻结；未来application/payload/RAG或高吞吐索引可向后兼容扩展，改变model-visible字段/权限须新增Decision | Qwen部署只能面对Runtime renderer，不得直接读取Parquet/SQLite/PCAP；graph只报告真实支持的匿名角色/repeated relation；Unknown与Qwen正式Schema仍未冻结 |
| 2026-08-11 | DEC-0018 | Adapter已安全集成，但缺少required safe字段的最终正向值级证明、官方raw模型本地服务和真实Runtime→Qwen证据 | 登记部署事实：`PRODUCTION_RUNTIME_EVIDENCE_CONTRACT_V1`与正向/fail-closed Fidelity Gate通过；官方`Qwen/Qwen3.5-9B` revision `c202236235762e1c871ad0ccb60c8ee5ba337b9a`以独立vLLM 0.25.1、BF16、text-only、8192 context、non-thinking/direct-response部署；`RAW_SMOKE_TRAFFIC_EXPERT_PROMPT_V0`仅作smoke | 272条deterministic stratified PLAN_B审计的最大prompt为initial 971、packet-expanded 1607、temporal 1288 tokens；provider raw、typed fake-safe、六类真实Production、9–16包与past-only temporal均parse PASS且无显式reasoning，完整回归261 passed | 模型revision与本次可复现部署manifest固定；runtime小版本和资源参数可在新增部署审计后升级；Training Protocol、正式Prompt/Schema、LoRA target/rank、classification head、Tokenizer adaptation及Unknown均未冻结 | 权重/venv/cache/log保持Git外；原生Tokenizer继续使用，后续只建议先比较compact serialization；raw输出不作为性能或论文结论；SFT/RL/正式benchmark仍为NOT RUN |
| 2026-08-11 | DEC-0019 | Training Protocol仍把classification head/生成式fine二选一、PPO/GRPO非主线、Near/Far/Mixed并行推进、DeepSeek角色与Application/Payload/RAG最终职责写成未冻结 | 冻结`ONE_MAINLINE_FIRST`与Near Training Protocol v1：Near先完成全闭环；trained Qwen采用冻结base+LoRA+Linear Fine Head+保留LM Head，coarse使用确定性映射；Training #1为classification-first Multi-task SFT，Training #2为RLAIF-GRPO并用独立classification CE保持Fine Head；DeepSeek Flash是可配置Teacher/Judge/Supervisor默认且三角色隔离；Unknown在Qwen冻结后用K validation+U_dev独立开发；新类先用Class Memory；Application/Payload/RAG是按需最终能力 | Qwen3.5真实架构/hidden-state审计确认classification head需training-side harness；同input Fine Head correctness在LM rollout group内为常数，不能提供GRPO relative advantage；同时开发全部preset/ablation会阻碍第一条可审计端到端结果 | 主架构、权限、Near-first顺序和checkpoint lineage冻结；pooling、LoRA/训练数值、Unknown算法/阈值、RAG top-k、Supervisor budget仍按validation-safe小范围选择 | DEC-0011的BF16/text-only/独立Unknown继续有效，但其“PPO/GRPO不属于主线”及分类头未冻结口径被本Decision替代；SFT/RL仍NOT RUN；Far/Mixed/IoT-23与其他ablation延后至Near完成 |
| 2026-08-12 | DEC-0020 | Final Teacher pilot暴露旧实现把`classification CE eligible`与`Teacher.evidence_sufficient`相乘，导致合法primary Fine Head监督被Agent取证停止变量错误门控 | 冻结`CLASSIFICATION_SUFFICIENCY_DECOUPLED_V1`：每个合法TRAIN K-known session由deterministic protocol选择一个真实primary并计算classification CE，无论Teacher sufficiency true/false；controlled lower-evidence auxiliary只训练Evidence LM并mask CE；Teacher/Judge sufficiency只表达当前可见Evidence是否足以停止额外取证 | PLAN_B 16,979个session逐一primary审计覆盖全部11类且无model-visible GT/backend identity；V2 pilot极端保守证明旧耦合不可行，Prompt V3校准把sufficiency定义为operational classification sufficiency并保留grounding/Observation–Knowledge边界 | CE eligibility、primary/auxiliary、session weighting和GT backend-only边界冻结；sufficiency比例不作class quota或50/50优化，final Teacher/corpus必须通过独立质量Gate | 不是恢复裸GT或label shortcut；允许`classification_ce_eligible=true`且`evidence_sufficient=false`；未来RLAIF仍以semantic Judge reward加并行classification CE，Judge sufficiency不得门控CE |

生效关系：DEC-0001至DEC-0018作为历史记录完整保留。DEC-0005中的sample-level信息隔离原则继续有效；旧CICIoMT、传统Reviewer、Flow-only、IoT待验收、本地Production、over-dedup、旧physical split与未验证provenance口径依次由DEC-0006至DEC-0018替代。DEC-0011冻结的BF16 LoRA、text-only、non-thinking与Independent Unknown边界继续有效，但其分类头未冻结和PPO/GRPO非主线表述由DEC-0019替代；DEC-0020进一步取代任何“Teacher sufficiency门控classification CE”的旧口径。当前训练/Open-world主线以DEC-0019、DEC-0020及`docs/training/near_mainline_training_protocol_v1.md`为准；Production identity/split/SFT candidate/provenance/Runtime安全边界与raw部署事实仍分别以DEC-0012至DEC-0018为准。
