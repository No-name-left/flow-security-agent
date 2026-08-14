# 面向恶意流量分析的成本感知主动证据获取研究计划（权威详细版）

> 文档状态：Canonical / Authoritative
>
> 冻结日期：2026-08-14
>
> 解释顺序：本文件是最高研究语义权威；`docs/training/near_mainline_training_protocol_v1.md`是训练/Open-world执行权威，Agent架构文档是Runtime/Supervisor/RAG/Memory设计权威，时间表、简版和交接不得覆盖它们。审计产生新证据但尚未写入Decision Log时，不自动改变研究方案。

## 0. 当前冻结方案概览

> **DEC-0023当前状态：**DEC-0022冻结的六类Observable Dataset v3、Evidence-v2、Teacher-v2与corpus v3继续作为Model A的权威训练输入，正在进行的Formal Near Multi-task SFT不得废弃或干扰。论文主线进一步聚焦为**面向LLM恶意流量分析的成本感知主动/序贯Observation-Evidence获取**；Edge-only Model A是controlled benchmark和warm start，正式论文路线增加CICIDS2017、ToN-IoT优先的multi-dataset Model B。Unknown rejection保留，few-shot novel-class registration降为Future Work/Optional Extension。

### 0.1 研究问题与正式主链路

本文的核心问题是：**对于一个target session，是否必须在第一次推理前取得全部可用信息；还是可以先提供廉价但有用的Basic-v2，由Qwen同时判断“更像什么攻击”与“当前Observation是否已经充分”，并在证据不足时由受约束Supervisor选择下一种Observation Evidence，使系统在分类效果与evidence/token/latency cost之间取得更好的序贯决策。**

LLM traffic classification、Agent、RAG与few-shot unseen-class adaptation本身都不是研究空白，也不单独构成本研究的创新。正式方法的研究对象是`cost-aware active / sequential observation-evidence acquisition for LLM-based malicious traffic analysis`：何时继续观察、下一步观察什么、何时停止，以及这种选择相对固定完整表示是否带来可测量的utility-cost收益。

正式主链路冻结为：

```text
网络流量样本
→ 会话级混合表示
→ Qwen3.5-9B共享语言表示
→ Fine Classification Head输出Known fine logits
  + 原始LM Head输出Evidence State
→ deterministic fine→coarse mapping
→ Independent Unknown Scoring / Calibration
→ 若Observation不足，DeepSeek Flash Supervisor在Runtime约束下选择一个bounded Evidence action
→ deterministic Runtime执行、校验、去重并返回新Evidence
→ Qwen重新评价
→ STOP_AND_CLASSIFY / Known / Coarse / Unknown / Abstain
```

Qwen第一次就直接读取网络证据，是正式主分类模型，不再作为LightGBM/XGBoost的Reviewer。正式trained model使用冻结Qwen base、可训练LoRA与一个简单Linear Fine Classification Head；Fine Head是唯一正式fine决策源，coarse由冻结映射得到，LM Head只生成简短Evidence State而不并行生成另一份fine label。传统模型只承担基线、诊断与可选消融，不决定哪些样本调用Qwen，也不向Qwen提供必需概率。

正式Unknown不是第K+1类，也不由未经验证的LLM自报概率决定。它在Near SFT和RLAIF-GRPO后冻结主Qwen，使用Known validation与`U_dev`比较margin、entropy、energy和prototype distance等独立方法；`U_final`只在算法、阈值及所有会影响最终推理的Prompt、sanitizer、RAG和Supervisor配置冻结后打开。

### 0.2 Model A / Model B与多数据集角色

| 模型/数据集 | 当前角色 | 当前结论 |
| --- | --- | --- |
| **Model A / Edge-IIoTset** | Single-domain controlled benchmark、当前Formal SFT、后续Model B warm start与replay安全锚点 | Dataset v3、六类Known（Normal、DDoS_HTTP、DDoS_TCP、Password、SQL_injection、Vulnerability_scanner）、Teacher-v2和corpus v3均已冻结；完整训练、验证并保留，不因多数据集路线而废弃 |
| **Model B / CICIDS2017** | 第一优先新增domain | raw PCAP、payload、labeled flows与attack metadata兼容统一session/evidence重建；细粒度taxonomy与当前任务接近，先通过Compatibility Gate再进入正式数据处理 |
| **Model B / ToN-IoT** | 第二优先新增domain | raw PCAP、Zeek/Bro logs、CSV与SecurityEvents GT支持另一网络环境中的session provenance和Evidence构建；先通过Compatibility Gate |
| CSE-CIC-IDS2018 | 时间与兼容性允许时的第三候选 | 规模大且有PCAP/log/schedule/flow labels；是否纳入由前两域pilot后的成本和兼容性决定 |
| ISCX-Botnet、Bot-IoT | 第二优先候选 | 用于补充botnet/behavior diversity，不在第一轮关键路径 |
| USTC-TFC2016、DoHBrw | 低优先、特定用途 | 只在其原始证据和标签语义适合特定消融时使用 |
| IoT-23及其他既有候选 | 历史审计、adapter参考或后续可选外测 | 已有结论保留，不再自动占据Model B第一批正式位置 |

Model A不是被替换的试验品：它是高质量、可控的单域基线和Model B的初始化锚点。最终论文不应只依赖Edge-IIoTset；Model B优先在Edge + CICIDS2017 + ToN-IoT上验证统一session/evidence interface与跨域鲁棒性，必要时才增加CSE-CIC-IDS2018。多数据集不是直接拼接CSV，而是统一session semantics、label semantics和Observation Evidence interface。

### 0.3 会话级混合表示

基础输入不再限定为单行Flow。`Basic-v2`冻结为cheap-but-useful会话级混合表示：whole-session安全摘要、前8个packet metadata、与每个packet显式对齐的有界脱敏payload，以及可低成本确定性取得的structured Application metadata。Basic-v2不是Full Evidence；扩展Observation family仍包括`PACKET_PAYLOAD`、`APPLICATION`、`TEMPORAL`与`RELATION`，Knowledge family为`KNOWLEDGE`。

包序列允许可变长度，保存上限暂定16包；Basic读取前8包，后续动作可请求第9至16包及其合法bounded payload。payload sidecar必须显式保存session、packet index、direction、relative time、protocol、presence/length、sanitized content和sanitization version，不能依赖数组顺序猜测对齐。Temporal-v2只允许10/60/180/300秒past-only horizon；Relation-v2允许ARP/link-layer和合法关系context而不改变target session定义。正式任务继续采用Qwen3.5-9B text-only、原生Tokenizer、BF16 LoRA和non-thinking/direct-response；QLoRA、thinking与专用Tokenizer仍是deferred/backup。

### 0.4 Unknown、Evidence Insufficient与可选新类扩展

每个正式数据集保留原生coarse/fine标签，并在训练前独立冻结：

```text
K_known：基础训练和SFT可见
U_dev：不得作为主分类模型监督标签进入SFT，只用于Unknown算法、阈值/校准、证据扩展与策略开发
U_final：最终评测前完全隔离

Qwen已知类分类 + Frozen Unknown Scoring / Calibration（known-only知识）
→ Evidence不足：继续获取合法Observation Evidence，而不是宣判Unknown
→ Evidence充分但不属于Known taxonomy：Unknown rejection
```

`Evidence Insufficient != Unknown`。前者表示当前合法Observation尚不足，应进入bounded acquisition loop；后者要求Observation已经足以支撑“不属于Known taxonomy”的判断。`Unknown != low confidence`，`Unknown != Abstain`。至少预注册Near、Far和Mixed三套Unknown组合并使用多个随机种子；`U_final`信息隔离保持不变。sample-level few-shot novel-class registration不再属于当前论文核心实验、关键路径或贡献，仅可作为Future Work/Optional Extension简述。

### 0.5 Agent与当前Gate

Agent读取Qwen第一次分类的粗细类别、证据状态、supporting/missing evidence、可供open-set计算的模型信号、冻结Unknown评分结果和当前工具状态，再决定是否接受或追加证据。Agent是动态取证和决策层，不是“传统分类器决定是否调用Qwen”的路由器。

当前Agent主方案采用DeepSeek Flash Supervisor读取Qwen Traffic Expert输出和Evidence State，并在deterministic Python Runtime约束下每轮选择一个合法动作。Supervisor不是第二分类器，不能覆盖Fine Head；Runtime负责Schema、capability、预算、最大轮数、去重、信息隔离、故障处理和Trace。DeepSeek Flash是当前可配置provider default，运行manifest必须记录实际endpoint/model ID；Teacher、Judge与Supervisor的Prompt、Schema、权限和日志严格分离。

Agent的基本闭环进一步明确为`Evidence State → 识别缺失证据 → 选择对应证据源/合法动作 → 更新状态 → 重分类或停止`。动态性来自根据当前证据缺口、可用能力和剩余预算选择下一步，而不是在Qwen不确定时无差别调用全部工具；这一细化不改变Qwen首次分类、独立Unknown层和Agent所在位置。

架构回溯、Production Data Freeze、paper-grade `CONSTRAINED_CHRONOLOGICAL_BOUNDARY_V2`、Runtime foundation、Safe Adapter、raw Qwen部署与training harness均已完成，继续作为可复用基础。此前11类PLAN_B、Application/Payload/RAG TRAIN sidecar、Teacher Prompt V3 bulk和22,957-record corpus曾通过当时合同的验收，但后续class-conditional observability审计证明“verified capture label”不等于“每个session有fine-class evidence”。因此DEC-0021暂停旧formal launcher并要求重建；DEC-0022现已完成新的eligible population、Basic-v2、packet-aligned payload、Temporal/Relation/Application-v2、multi-gap Evidence State与Teacher-v2验收。旧corpus保留为历史证据，不得进入正式SFT。DEC-0020的classification/sufficiency解耦继续有效。Model A Formal SFT已启动；Unknown算法和Agent正式实验/benchmark均未开始。

### 0.6 Task Definition v2与Model A→Model B过渡

`ONE_MAINLINE_FIRST`和正式训练seed `20260809`继续有效；`U_dev`仍为DDoS_ICMP、OS_Fingerprinting，`U_final`仍为DDoS_UDP、XSS且保持sealed。DEC-0021规定`MAX_MAIN_CLASSES=8`及八类pre-model候选；最终eligibility冻结六类Normal、DDoS_HTTP、DDoS_TCP、Password、SQL_injection、Vulnerability_scanner。MITM因缺少与target endpoint关联的ARP/relation异常、Port_Scanning因capture呈现同destination port 80而无法支持port-scan fine语义，均不进入主CE。Backdoor为Long-Horizon Temporal Case Study，Uploading/Ransomware为Observability-Limited/Abstain辅助集。

Near执行顺序先完成Evidence-v2、全split eligibility、Observable Dataset v3、Teacher-v2与新SFT corpus，再执行classification-first Multi-task SFT并形成Model A。Model A validation后，进入CICIDS2017与ToN-IoT Compatibility Gate、统一多数据集pipeline和Model B continuation SFT；Active Evidence baselines稳定后才构建mixed-domain RLAIF。Independent Unknown保留，few-shot不再进入关键路径。

[Near-First Training and Open-World Protocol v1](../training/near_mainline_training_protocol_v1.md)继续冻结架构、权限、隔离和checkpoint lineage，但其旧11类/旧corpus执行输入由DEC-0021替代。当前DeepSeek仍严格区分Teacher、Judge与Supervisor；Codex只负责工程、编排、调用、审计和报告。

## 1. 研究动机、核心假设与预期贡献

单行Flow统计压缩了包顺序和会话交互；传统表格模型虽能高效建立强基线，却不能代表LLM对序列化网络证据、缺失证据和动态取证的全部能力。若Qwen只接收传统分类器挑出的困难样本，论文评价的仍是一个树模型主导的选择性复核系统，无法公平回答领域后训练LLM能否独立承担网络流量分类。

核心假设为：

- H1：双向包序列与会话摘要能为Qwen提供比单行Flow更完整、仍可审计的行为证据；
- H2：领域SFT可使Qwen3.5-9B直接完成known fine/coarse分类、证据充分度与可供独立Unknown评分使用的稳定模型信号输出；
- H3：在第一次分类证据不足时，Agent按需扩展Packet/Payload、Application、Temporal或Relation Observation，比固定预取完整表示获得更好的accuracy—evidence/token/latency cost权衡；
- H4：统一session/label/evidence合同与dataset-balanced replay使上述acquisition机制能够扩展到多个公开traffic domain，而不被单一Edge采集环境或大型外部域淹没。

预期贡献包括：

1. 将LLM恶意流量分析表述为成本感知的序贯Observation-Evidence获取问题，而非固定traffic representation上的一次性分类；
2. 提出multi-task Traffic Expert，显式分离Fine Classification与Evidence-State estimation，分别判断“是什么”与“当前是否已经知道得足够”；
3. 提出bounded Supervisor + deterministic Runtime的selective acquisition机制，按需获取Packet/Payload、Application、Temporal与Relation Evidence；
4. 通过Basic-only、Full-Evidence One-Shot、Strong Static、RulePolicy与Agent的预算匹配比较，量化accuracy—evidence/token/latency cost trade-off；
5. 在多来源公开traffic benchmarks上使用统一session/evidence interface验证cross-domain robustness，避免方法只对单一Edge-IIoTset成立。

RLAIF是对第3/4项trajectory policy的后续优化，不单独夸大为主要创新；Unknown是开放世界鲁棒性扩展；few-shot不是当前贡献。若Agent无优势，则由强Static承担推荐流程，Agent作为适用边界分析。任何结论均须来自冻结数据与公平基线，不预设LLM或Agent一定有效。

### 1.1 Related Work定位与创新边界

现有工作已经充分说明LLM traffic classification、open-set classification、multi-flow建模、RAG和few-shot adaptation都不是空白。论文不得再声称“基于LLM的恶意流量分类很少”“Agent用于流量分类几乎无人研究”或“few-shot新类识别本身是主要创新”。正式边界如下：

| 工作方向 | 主要研究对象 | 与本研究的边界 |
| --- | --- | --- |
| TrafficLLM | generic traffic representation、traffic-domain tokenizer、跨traffic task adaptation | 我们不把通用representation本身作为核心，而研究对当前session是否需要继续取得Evidence |
| ETooL | multi-flow temporal/burst/relation structure在non-IID/OOD下的鲁棒表示 | 其Temporal/Relation思想高度相关；区别是我们不默认预先构造全部multi-flow结构，而研究是否及何时选择性获取 |
| MalRAG | 从历史恶意traffic库检索content/structural/temporal相似流量以支持open-set identification | 其retrieval回答“从历史库取什么”；我们的核心回答“当前目标流量还需要观察什么”，且Knowledge不能替代Observation |
| TrafficGPT / open-set TrafficLLM | LLM/Transformer traffic representation与open-set classifier | 是必须比较/讨论的固定表示和open-set相关路线，不等同于主动Evidence获取 |
| NIDS-GPT / Take Package as Language | GPT-style packet/traffic representation与细粒度入侵分类 | 证明LLM fine classification已有直接先例；我们的贡献不在“首次用GPT做NIDS” |
| ICT-META | n-way k-shot unseen traffic-class inference-time adaptation | 直接覆盖few-shot unseen-class adaptation，因此该方向不再作为本论文核心 |
| **OURS** | 当前session的Observation sufficiency、下一Evidence、停止时机与成本 | 以bounded Supervisor和deterministic Runtime优化accuracy—evidence/token/latency trade-off，并在多域上验证 |

Multi-Agent、RAG、RL或多数据集都只是实现或验证手段。核心因果问题始终是：相对Basic-only与固定完整表示，selective acquisition是否在相同信息域和预算下提供更好的utility-cost边界。

## 2. 数据策略与数据Gate

### 2.1 多数据集统一pipeline、Canonical Label与会话接口

多数据集正式处理链路冻结为：

```text
Raw Dataset
→ Dataset-specific Ground-Truth / Provenance Adapter
→ Common Session Reconstruction
→ Canonical Label Contract
→ Common Evidence Contract
→ Leakage Sanitization
→ Grouped / Run-aware Split
→ Multi-domain Training Corpus
```

我们统一的不是CSV columns，而是`session semantics + label semantics + Observation Evidence interface`。各dataset原始flow row不能天然视为同一种训练对象；凡有raw traffic的正式Agent数据，尽量经过common sessionizer。无法从raw traffic重建兼容session的数据只能保留为classification-only external baseline，不得伪装成完整Evidence-Agent sample。

不同数据集保留原生标签，不强制统一为ATT&CK。每个Adapter通过统一接口提供：

```text
DatasetLabelSchema
├─ dataset_name / version / sample_unit
├─ source_label / canonical_family / canonical_fine_label
├─ mapping_quality: EXACT | FAMILY_ONLY | UNSUPPORTED
├─ benign_label
├─ coarse_labels / fine_labels / parent_of
├─ label_description
├─ known_classes / dev_unknown_classes / final_unknown_classes
├─ session_or_capture_group（若可靠存在）
├─ support_pool / query_pool
└─ missing_fields / prohibited_model_fields
```

`source_label`保留官方语义；`canonical_family`用于跨域coarse evaluation；`canonical_fine_label`只在语义真正一致时建立；`mapping_quality`至少为`EXACT`、`FAMILY_ONLY`或`UNSUPPORTED`。例如CICIDS `Web Attack SQL Injection → Web_Attack → SQL_injection → EXACT`；普通`DDoS`若无HTTP/TCP subtype证据只能映射为`DDoS → UNKNOWN_SUBTYPE → FAMILY_ONLY`，不得强行并入DDoS_HTTP或DDoS_TCP。宁可扩展Fine Head到新的K维，也不错误合并攻击概念。ATT&CK、CAPEC、协议说明和官方类别描述可作为知识来源，但映射本身不包装成论文创新；不同标签空间的绝对Macro-F1不直接混用。

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

### 2.2 Model A与Multi-dataset Model B

**Model A是已冻结的single-domain controlled benchmark。** 它使用Edge-IIoTset Dataset v3、六类Known、Teacher-v2 Evidence-State supervision和corpus v3。当前Formal Near Multi-task SFT完整保留；其checkpoint、validation与后续Agent结果构成Model A baseline，也是Model B的warm start。Model A的限制继续披露：多数攻击类别只有一个主要capture，主结论限于控制直接捷径后的同采集环境，不能宣称跨攻击run或跨domain泛化。

**Model B是正式multi-domain continuation route。** 第一批优先接入CICIDS2017与ToN-IoT；兼容性和资源允许时增加CSE-CIC-IDS2018。新增domain先通过轻量Compatibility Gate，再由dataset-specific GT/provenance adapter、common sessionizer、canonical label mapping和common Evidence contract构建可审计样本。Model B不要求所有source fine labels完全相同：`EXACT`类可进入shared fine evaluation，`FAMILY_ONLY`只进入coarse或独立source-label任务，`UNSUPPORTED`不得被错误并类。

Model B优先从Model A checkpoint warm-start。若Known taxonomy从6扩展到K，Fine Classification Head按canonical mapping复制原六类rows并初始化新增rows；Qwen backbone、LoRA、LM Head与已学Evidence-State能力继承。训练必须同时使用旧Edge replay和新增数据，采用dataset-balanced与class-aware/class-balanced sampling，避免大型CIC/CSE域淹没高质量Edge Teacher corpus或造成catastrophic forgetting。Model B对Model A clean validation的可接受退化阈值在multi-domain pilot前预注册，不在此写死不可调整的百分点。

多域监督采用“大量classification-only + 少量高质量Evidence-State”组合：clean external samples令`L_cls=ON, L_evidence=MASKED`；每个新domain再抽取代表性sessions运行完整Evidence builder与少量DeepSeek Teacher，令两项loss均ON。Teacher数量由pilot决定，不对每个外部样本全量调用API。

### 2.3 Dataset Adapter、会话构造与泄漏控制

```text
EdgeAdapter:
PCAP及标签资料
→ 双向会话
→ 包序列、摘要、上下文和原生标签
→ CanonicalSessionRecord

CICIDS2017Adapter / ToNIoTAdapter / optional CSE-CIC-IDS2018Adapter:
官方PCAP + flow/log/event schedule/GT
→ 通过dataset-specific时间、通信标识和事件语义分配GT
→ 双向会话、包序列、摘要和上下文
→ CanonicalSessionRecord
```

各Adapter只负责把raw PCAP、official labels与event schedule转换为target-session GT/provenance；它不改变模型结构。attacker/victim IP、absolute timestamp、capture filename、scenario ID、dataset ID与attack schedule只允许存在于private provenance和GT assignment层，不能进入model-visible Evidence。Adapter可采用不同原始解析实现，但输出Schema、序列化协议、模型调用接口和评测接口保持一致。`Session Evidence Card`是`CanonicalSessionRecord`面向模型的安全投影。

基础样本为双向会话。不得对所有sessions做简单random row split；优先按attack run、capture、host/group或scenario隔离，再分别在split内部构建past-only上下文。正式评测至少区分in-domain validation/test、cross-capture/cross-run test与cross-dataset shared-class test。必要时可并列保留paper-compatible split，但主要结论优先使用leakage-controlled split。

跨会话关联只使用锚点之前的信息，可包括：past-only同源近期会话数、不同目的IP/端口数、同一目标的不同来源数、重复通信、未完成握手比例、会话间隔、周期性、总包数/总字节数和局部通信图摘要。原始IP只用于会话、关系查询和分组，绝对时间只用于排序、时间块和past-only检索；文件名、capture/scenario ID、数据集来源和攻击脚本编号不得输入模型。

原始端口需转换为服务类别或进行无端口消融。完整Payload不默认输入，固定URI、topic、用户名和明显攻击字符串不作为基础证据；应用层字段和有限脱敏Payload必须有字段白名单、缺失声明、隐私与可复现边界，并由Agent按需请求。所有归一化、编码、特征选择和校准只在训练集拟合；保存split manifest、源数据哈希、预测和随机种子。

### 2.4 `MULTI_DATASET_COMPATIBILITY_GATE`

Model A的Edge数据Gate与限制保持冻结。每个新增domain先执行轻量、高价值的`MULTI_DATASET_COMPATIBILITY_GATE`：

1. 官方label语义是否清楚；
2. raw traffic是否真实可得；
3. GT能否可靠映射回common session；
4. 随机抽样session的model-safe Evidence是否与GT一致；
5. 是否存在明显capture/run label propagation；
6. 是否存在IP/time/dataset identity shortcut；
7. 是否能实现run/capture/group隔离split；
8. Basic-v2及可用的Observation Evidence family是否可真实构造。

Gate PASS后进入正式数据处理。只有发现类似Edge-IIoTset的严重granularity、label propagation或leakage异常时，才升级为深度audit；不默认对每个新增dataset重复Edge级长审计。缺失某Evidence family必须记录`evidence_family_available=false`，不能用0或空字符串冒充“真实没有事件”。

### 2.5 Edge paper-grade physical split与SFT候选层

Edge完整Production Dataset继续保留真实session分布，Primary dedup只依据immutable backend identity。类别不平衡、模型视图重复或SFT算力预算不得反向删除canonical session；完整数据仍服务真实分布统计、evaluation、Unknown、past-only Temporal/Graph Context、sensitivity和复现审计。

正式Edge physical assignment采用`CONSTRAINED_CHRONOLOGICAL_BOUNDARY_V2`：每个capture内部按`timestamp_start, sample_id`排序；大capture使用70%/15%/15%的session-rank时间边界，小capture在预先固定的候选网格内以evaluation support、合法train diversity、比例与quarantine为顺序做deterministic boundary search；任何跨边界session以及边界两侧合计5秒local embargo内的session均进入quarantine。禁止random shuffle或跨capture混合切分。split revision只重建assignment及其依赖资产，不重新TShark、canonical或sessionize；7,619,032个Edge stable identity的计数、有序SHA256和唯一性在修订前后完全一致。正式新分配为train 5,294,777、validation 1,073,539、test 1,110,343、quarantine 140,373；ZERO从1降为0，CRITICAL_LOW从2降为0，因此`PAPER_EVALUATION_READINESS_GATE=PASS_WITH_LIMITATIONS`。MITM与OS_Fingerprinting的validation/test仍属LOW；DDoS_UDP和OS_Fingerprinting因train evidence diversity不足标记为`STRUCTURALLY_INSUFFICIENT_KNOWN`，这些只是分析/readiness状态，不改变任何K/U角色。

Phase A必须报告而不能把model-view equality误作identity：相对旧split，Edge-only exact cross-split collision group增加104、near-signature collision group增加303，但backend identity cross-split leakage保持0；Primary继续保留现实重复行为，`EXACT_EVAL_CLEAN`与`NEAR_EVAL_CLEAN`只作为train不变的evaluation sensitivity。候选比较和最终矩阵保存在`reports/edge_split_revision_v2/phase_a_split_candidate_comparison.json`。

SFT训练候选与完整Production资产严格分层。历史`CLASS_BALANCED_DIVERSITY_AWARE_SFT_SELECTION_V1`曾只允许`K_known ∩ physical train`并选择PLAN_B（Near/Far/Mixed 16,979/15,895/15,404）；DEC-0021已将该11类population标为superseded historical。Dataset v3仍复用“只从eligible TRAIN、优先覆盖near/exact diversity、真实sample ID唯一、不复制JSONL、不得使用validation/test/U_dev/U_final”的原则，但最终候选数和class map必须依据v3 manifest重新冻结。

Edge标签正式语义保持`DIRECT_EVIDENCE_UNANIMOUS_ONLY`优先；当前官方CSV缺乏稳定frame number或绝对frame time，无法形成formal packet/frame direct mapping，故7,619,032个session使用`VERIFIED_CAPTURE_FALLBACK`。该fallback只在PCAP/CSV hash、100%单标签purity、expected label一致和session不跨capture全部通过时成立；24/24 capture通过，conflict与unmatched均为0。论文必须描述为official single-label capture + verified companion CSV + within-capture session reconstruction，不得声称人工session-level ground truth。

DEC-0021进一步修正该边界：`VERIFIED_CAPTURE_FALLBACK`只验证label provenance，不等价于每个session具有fine-class observation。主train/validation/test必须逐observation执行`Fine-Class Observation Eligibility Contract`，并排除`GENERIC_BACKGROUND`、`NETWORK_UNOBSERVABLE`、`WRONG_GRANULARITY`和`LABEL_PROPAGATION_ONLY`。三套split使用同一准入合同，默认保留v2 assignment后分别过滤；只有过滤导致不可用support时才允许在模型结果前构建deterministic grouped/chronological split v3。完整规则与exclusion审计字段以`task_definition_v2.md`为准。

## 3. K/U预注册与信息隔离

### 3.1 三类集合

- `K_known`：覆盖多种coarse、包含易难类且样本充足；可进入Qwen SFT以及传统模型基线训练。
- `U_dev`：约2—4类，仅用于Unknown算法、阈值、证据扩展策略、RulePolicy/Supervisor策略开发、可选LearnablePolicy和合法RAG路由开发，不进入主分类模型监督。
- `U_final`：最终评测前完全隔离；不得进入SFT/DPO、Prompt示例、known-only RAG、Unknown算法选择、阈值开发、Agent/策略训练、错误驱动调参或人工挑选。

Model A的Near/Far/Mixed组合与随机种子已预注册并继续保持；不得依据结果改选组合。Model B的新增K/Unknown mapping必须在其训练前按canonical label与source support另行预注册，不能借多数据集路线查看或改写Model A `U_final`。

### 3.2 Unknown生命周期与Observation分流

**阶段A：Unknown Rejection。** Qwen主分类SFT只使用`K_known`监督数据和known-only冻结知识；Fine Head输出唯一正式Known fine logits，coarse由冻结映射得到，LM Head输出证据充分度、supporting/missing evidence及可供open-set计算的模型信号；冻结的Unknown Scoring / Calibration层再产生正式Unknown决策。Unknown算法和阈值只能使用`K_known`与`U_dev`开发，`U_dev`标签不得作为主分类模型监督进入SFT。

正式分流顺序是：先判断Observation是否充分；不足时继续请求合法Evidence。只有在Observation充分且冻结open-set层判定不属于Known taxonomy时，才输出Unknown。预算耗尽、能力不可用或Evidence仍不足时输出Abstain/Backoff，不能把这些状态统称Unknown。

Knowledge-assisted candidate identification可作为Unknown后的辅助分析，但不得与监督fine accuracy混用。人工support、Class Memory与few-shot novel-class registration移至Future Work/Optional Extension；它们不再是当前核心实验、timeline依赖或论文贡献。

## 4. 模型与证据表示

### 4.1 传统模型仅作为基线

Logistic Regression、Random Forest、LightGBM和XGBoost用于闭集强基线、开放集拒识基线、速度/成本基线、数据泄漏诊断，以及可选混合消融或部署变体。它们不进入正式主链路，不负责筛选Qwen样本，也不向Qwen提供必需概率。

若实验保留树模型OOF预测，仅用于传统模型自身的校准、开放集基线或可选融合消融，不能作为Qwen SFT的必要输入。

### 4.2 Session Evidence Card

Session Evidence Card是提供给Qwen和工具的安全证据载体，至少包含：数据集原生Schema、会话标识的匿名化引用、前N个包的方向/长度/IAT/协议/flags、会话持续时间与双向统计、字段缺失声明、当前可观察证据、已请求证据、知识来源和预算状态。

Agent扩展后可加入past-only时间上下文、局部通信图摘要、合法应用层字段、有限脱敏Payload和RAG结果。传统模型概率只能作为可选消融字段，不属于正式Qwen输入合同。不可观察信息不得由Qwen或RAG补造。

Evidence State v2冻结为multi-gap策略合同。它至少包含`evidence_sufficient`、grounded `supporting_evidence`、去重的`missing_evidence[]`、`primary_gap`、`gap_type`和`recoverability`。缺口family只能是`PACKET_PAYLOAD`、`APPLICATION`、`TEMPORAL`、`RELATION`、`KNOWLEDGE`；domain只能是`OBSERVATIONAL`、`KNOWLEDGE`、`MIXED`、`NONE`；recoverability只能是`ALREADY_SUFFICIENT`、`RECOVERABLE_WITH_AVAILABLE_TOOLS`、`NOT_RECOVERABLE_FROM_AVAILABLE_NETWORK_EVIDENCE`。Qwen可声明多个真实gap，Supervisor仍只选择一个bounded action，Runtime仍逐动作执行和重评。

### 4.3 Qwen3.5-9B主分类模型

Qwen3.5-9B直接读取Session Evidence Card。正式trained model由冻结base、可训练LoRA、一个简单Linear Fine Classification Head和保留的原始LM Head组成。Fine Head读取`h_session`并输出`|K_known|` logits，是trained model唯一正式fine分类源；不增加Coarse Head，coarse由冻结fine→coarse映射得到。原始LM Head只输出brief behavior summary（有价值时）、supporting/missing evidence、evidence sufficiency、gap type和backoff相关Evidence State，不生成竞争性的fine label。

Pooling已在last meaningful prompt position、无新增token的explicit prompt ending和attention-masked mean之间用22个合法K-known TRAIN representation比较，冻结为`ATTENTION_MASKED_MEAN_V1`；该选择不修改tokenizer或embedding。Qwen3.5真实`named_modules()` inventory冻结248个LoRA targets，覆盖Gated DeltaNet、Gated Attention和FFN，不能只沿用旧模型的q/k/v/o假设。base、vision、embedding和原始LM Head冻结；只训练LoRA与Fine Head。

Training #1是classification-first Multi-task BF16 LoRA SFT：`L_SFT=lambda_cls*L_classification+lambda_ev*L_evidence_generation`，official/verified GT只监督Fine Head classification，Evidence State来自确定性规则、受控mask/stage、DeepSeek Flash Teacher、自动一致性过滤和有界人工审查。Teacher可把GT作为不可修改上下文，但不得决定标签或创造Observation。

`CLASSIFICATION_SUFFICIENCY_DECOUPLED_V1`冻结两个互不门控的变量：`classification_ce_eligible`由TRAIN、K-known、verified GT、无泄漏/U_final、合法provenance与deterministic primary-state protocol决定；`evidence_sufficient`由Teacher/Evidence-State表示当前可见证据是否足以作出有用分类并停止额外取证。合法primary即使`sufficient=false`仍计算CE；人为删除关键证据的controlled auxiliary只训练Evidence LM并mask CE。GT只存在于backend target，不进入serialized input、Prompt、RAG query、Payload或任何model-visible metadata，因此该监督不是label leakage。

Training #2从SFT checkpoint clone/reference后执行`RLAIF-GRPO + classification CE preservation`。Fine Head CE保持Known分类并继续更新Fine Head/LoRA；GRPO只优化随rollout变化的grounding、evidence sufficiency、missing evidence、gap、backoff/abstention、幻觉惩罚、schema和brevity。Fine Head correctness对同一input的rollout group是常数，不能声称为主要组内GRPO reward。DeepSeek Flash Judge在线/异步评价current-policy rollout，RL Prompt Pool固定来自合法Near `K_known TRAIN` Evidence states；DPO保持deferred。

Raw Qwen没有Fine Head，可用生成式分类Prompt形成raw baseline；它与custom-head trained model接口不完全相同。完整训练权限、阶段、可调参数与checkpoint lineage以`docs/training/near_mainline_training_protocol_v1.md`为准。

### 4.4 RAG信息域

知识来源可包括数据集官方类别描述、协议说明、ATT&CK、CAPEC和公开攻击行为说明。known-only RAG服务Known阶段；full-frozen RAG只在合法拒识后用于候选解释。`U_final`名称和描述不得泄漏到开发阶段。未来若研究Class Memory，只能在获得人工support后建立，并需另行预注册。

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
| ABSTAIN | 证据不足或预算耗尽时停止 |

`CALL_LLM_EXPERT`不再是正式动作：Qwen已是必经主分类器，追加调用统一由`RECLASSIFY`表达。状态机、工具白名单、预算和最大深度强制动作合法与可复现。

`REQUEST_LABEL`与`REGISTER_NEW_CLASS`不在当前论文正式动作集合；若未来恢复few-shot/Class Memory扩展，必须另行预注册并版本化动作合同。

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

Experience Memory保存经可靠反馈验证的`State→Action→Outcome`经验；train可验证后写入，validation与`U_dev`默认不写入，TEST/`U_final`冻结只读。Experience Memory与Knowledge RAG严格区分。Class Memory只允许作为Future Work/Optional Extension保存人工确认的新类别support，并必须与前两者分离；当前主实验不执行few-shot注册。主test不得边评测边学习。具体Memory embedding、index、top-k和capacity仍未冻结。

## 6. 训练边界与启动条件

训练/Open-world执行权威是`docs/training/near_mainline_training_protocol_v1.md`。Architecture/permission protocol已冻结；Model A Formal Near Multi-task SFT已启动且正在运行，本文档更新不得停止、重启、替换或改变该run/checkpoint。`RL_RUN=false`、`UNKNOWN_ALGORITHM_FROZEN=false`。

正式第一主线只使用Observable Dataset v3中`eligible TRAIN ∩ FINAL_MAIN_CLASSES`的唯一session；旧Near PLAN_B 16,979候选及其22,957-record corpus不再是formal输入。每个session以Basic-v2作为唯一primary，再只生成最多1–2个由真实gap驱动的controlled auxiliary states；不随机隐藏Evidence、不穷举组合。完整Production canonical分布、identity与原split不会因training预算改变。

SFT前必须升级并冻结Basic-v2 serialization、Traffic Expert/Evidence State v2 schema、active final class map、pooling contract、LoRA module inventory assertion及Evidence-v2 contract。现有harness与官方Tokenizer继续复用；formal preflight必须逐record校验fine label/class index、每session最多一个CE primary、最多三个states及session weight sum。旧formal config/launcher在v3 acceptance前必须fail closed。

Training #1训练LoRA+Fine Head的classification-first Multi-task SFT；Training #2从独立保存的SFT checkpoint继续执行RLAIF-GRPO并以classification CE防漂移。Teacher-v2只在eligibility完成后为新population标Evidence State，不决定fine GT；旧Teacher annotations不可复用。Teacher/Judge/Supervisor继续作为权限、Prompt、Schema和日志隔离的三种角色。

Model A checkpoint冻结并完成正式validation后，进入新增domain Compatibility Gate与Model B构建。Model B从Model A warm-start，扩展Fine Head时保留已映射rows，以Edge replay、dataset-balanced和class-aware sampling联合训练；不得只喂新domain继续训练。新增domain的大量clean sample只训练classification，少量代表性session再接受Evidence-State supervision。

Independent Unknown只用Known validation与`U_dev`比较margin、entropy、energy和prototype distance；优先不训练新网络，small learned Unknown head仅为backup。`U_dev`不作为Unknown第K+1类监督Qwen，`U_final`不进入任何开发。Few-shot novel-class registration不属于当前训练关键路径。

LoRA rank/alpha/dropout、LR、batch、epochs、loss weight、GRPO group size/reward weight、pooling、Unknown threshold、RAG top-k和Supervisor budget属于小范围**VALIDATION TUNABLE**；不得用formal test或`U_final`，不得大网格搜索，也不得因结果不理想修改K/U、split、PLAN_B或总体架构。

## 7. 正式实验结构

### Experiment A：Model A controlled SFT

完整保留当前Edge-only Model A Formal SFT与正式validation。比较Logistic Regression、Random Forest、LightGBM/XGBoost、raw Qwen3.5-9B和post-trained Model A，报告fine/coarse Macro-F1、per-class、校准、速度与成本。Model A是单域controlled benchmark、后续Agent基础与Model B warm start，不因论文扩展为多数据集而废弃。

### Experiment B：固定输入与表示基线

比较`Basic-only`、`Full-Evidence One-Shot`以及按可复现性选择的TrafficLLM/ETooL式固定representation baseline。Full-Evidence One-Shot必须保留，它回答“若一开始提供全部合法Evidence，性能上界和成本是多少”；不能用固定全证据替代active acquisition，也不能为了突出Agent而削弱该基线。

### Experiment C：Active Evidence Acquisition

在同一Qwen、工具、信息域与最大预算下比较Strong Static、RulePolicy、DeepSeek Flash Supervisor和完整Agent。核心因果问题为：

| 问题 | 比较与指标 |
| --- | --- |
| 更多Evidence本身是否有效 | Basic-only vs Full-Evidence One-Shot |
| selective acquisition是否优于固定方式 | Full/Static/Rule/Supervisor在budget-matched条件下比较 |
| 哪类Observation产生收益 | 分别移除Packet/Payload、Application、Temporal、Relation；Knowledge单独报告 |
| 收益是否只来自额外资源 | 同时报告Accuracy/Macro-F1、per-class、Evidence calls、tokens、latency、cost、stop behavior与utility-cost curve |

Evidence充分时必须`STOP_AND_CLASSIFY`；Observation不足时继续获取；能力不可用、预算耗尽或无法恢复时backoff/abstain。RAG不能替代Observation。RLAIF若执行，只优化跨domain共享acquisition trajectory，不建立Edge/CIC/ToN三套互不相干的policy。

### Experiment D：Multi-domain Model B

Model B第一版为Edge + CICIDS2017 + ToN-IoT，必要时增加CSE-CIC-IDS2018。比较`Model A→Edge`、`Model A→External`、`Model B→Edge`与`Model B→External`，分别报告in-domain、cross-capture/run与cross-dataset shared-family/shared-class结果。实验检验multi-domain supervision是否改善cross-domain robustness，同时保持Model A clean validation和Evidence-State/acquisition能力。

### Experiment E：OOD / Unknown

保留Independent Unknown rejection，使用Known validation与`U_dev`选择并冻结margin、entropy、energy、prototype distance等方法，再按既有隔离规则评估`U_final`。明确区分Unknown、Evidence Insufficient和Abstain；不把Unknown做成K+1类，也不把few-shot registration扩成核心实验。Low-Resource Unknown Stress Test如执行仅为optional auxiliary analysis，不进入主完成条件。

## 8. 评价、复现与统计

- 每套Unknown preset至少使用多个随机种子；具体数量在数据与算力确认后冻结。
- `U_final`只运行冻结系统，结果不回流模型、阈值、Prompt、RAG、策略或训练。
- 保存数据、代码、模型、Prompt、RAG、证据序列化和工具配置指纹，以及run ID、split manifest、失败和resume记录。
- Agent除分类指标外还报告end-to-end task success、evidence/tool选择成功、recovery、budget compliance和output validity，并分别统计证据请求率、Qwen调用次数、Supervisor轮数、RAG/各工具调用次数、延迟、Token/API成本和utility-cost曲线。
- 比较Static与Agent时必须使用同一Qwen、工具、信息域和最大预算，并进行budget-matched主比较；成本受限子集须在实验前固定，不按模型结果定制。固定全证据、Static、Rule与Learnable的资源差异须单独披露，不能把额外调用量解释为策略增益。
- 错误分析须同时给出错误来源和组件级处置去向，区分样本级取证、策略更新、Qwen SFT、Unknown校准及RAG修复，避免把不同组件的问题汇总为单一模型误差。
- 会话和past-only关联必须在训练、验证、测试内部独立构造，并检查固定身份、时间和来源捷径。

## 9. 时间与依赖

已完成的数据与工程Gate不得删除或重做。执行路线从“Edge Near完整闭环后才考虑外域”调整为“先完成并验证Model A，再进入multi-dataset Model B与active acquisition”，但不干扰正在运行的Model A Formal SFT。

| Phase | 工作 | 状态/退出条件 |
| --- | --- | --- |
| 1 | Edge Dataset v3、Teacher-v2、corpus v3、Model A Formal SFT | 数据/监督**COMPLETE / PASS**；Formal SFT **IN PROGRESS**，完成并保留checkpoint |
| 2 | Model A正式validation/evaluation | SFT完成后执行；不得用test/U_final调参 |
| 3 | Multi-dataset compatibility：CICIDS2017、ToN-IoT优先 | 轻量Gate；必要时CSE-CIC-IDS2018 |
| 4 | 统一GT adapter、session、canonical label、Evidence与grouped split；构造multi-domain corpus | 大量classification-only + 少量高质量Evidence-State |
| 5 | Model B multi-domain continuation SFT | 从Model A warm-start；Edge replay + dataset/class-balanced sampling |
| 6 | Basic/Full/Static/Rule/Supervisor active acquisition experiments | 相同信息域、最大预算；报告utility-cost |
| 7 | mixed-domain RLAIF | 仅在SFT与Agent baselines稳定后；一个共享acquisition policy |
| 8 | final Unknown/OOD、ablation、统计与writing | U_final仍遵守一次性sealed evaluation；few-shot不在关键路径 |

任何会影响U_final route的Prompt、serialization、sanitizer、RAG、Supervisor、Memory或Unknown配置，都必须在首次U_final前validation-safe冻结；阶段编号不授权看过U_final后再调参。

## 10. 风险与降级路线

| 风险 | 处理/降级 |
| --- | --- |
| Edge单capture与类别/场景耦合 | 保留Model A的capture内时间块、隔离gap、split内past-only和捷径消融；用CICIDS2017/ToN-IoT Model B补充跨域证据 |
| Edge异常PCAP或部分字段不可用 | 用成熟解析器复核并记录可恢复范围；缺失能力显式声明，不改变Edge主数据角色或虚构证据 |
| 新domain label或session语义不兼容 | 先过Compatibility Gate；`FAMILY_ONLY`只作coarse，`UNSUPPORTED`不强并类；必要时退回classification-only external baseline |
| 大型外部domain淹没Edge | dataset-balanced/class-aware sampling与Edge replay；Model A clean validation退化Gate在pilot前冻结 |
| 会话重建或标签粒度不可靠 | 收缩为可验证的会话/流记录单位，并限制结论；不得虚构跨会话监督 |
| 包数或上下文过长 | 首次分类使用前8包与摘要，Agent最多扩展至16包；通过预算和受限past-only摘要控制长度 |
| 固定IP、时间、capture或脚本捷径 | 后台关联与模型输入分离；做白名单、去身份和敏感性对照 |
| Qwen不优于传统基线 | 报告分类能力与成本边界，并检查Unknown与证据充分度；不恢复树模型主导架构 |
| Agent不优于强Static | Static成为推荐系统；Agent作为适用边界和负结果分析，不强行宣称有效 |
| 缺失证据类型判断错误或用RAG代替真实观测 | 以`capabilities`、缺失声明和动作validator限制候选工具；观测缺口只能调用真实取证工具，能力不可用时backoff或abstain |
| Agent收益来自额外信息或预算 | 强制与Static共享Qwen、工具、信息域和最大预算，报告逐类调用量及utility-cost；无法预算匹配的结果只作为上界补充 |
| 错误反馈更新了错误组件 | 先完成组件级归因；Unknown问题回到校准层、RAG问题回到检索链、策略问题回到Policy，只有充分证据下持续的Qwen错误进入SFT候选 |
| 应用层或Payload暂不可用 | 中间阶段fail closed并显式声明缺失；Near最终完成前必须实现并冻结sanitizer、能力边界与捷径审计，否则不得宣称完整方法 |
| BF16 LoRA收益小或显存/框架受限 | 保留原始Qwen基线、缩小高价值样本；必要时降级为QLoRA；取消DPO、27B和继续预训练 |
| 实验预算不足 | 保留已完成Model A，优先完成CICIDS2017+ToN-IoT的最小Model B与Basic/Full/Rule/Agent主比较；CSE-CIC、DPO、27B和扩展消融defer |

## 11. 当前已完成、未完成与下一步

已完成且可复用：Production Data Freeze与Git冻结；Edge `CONSTRAINED_CHRONOLOGICAL_BOUNDARY_V2`（train 5,294,777、validation 1,073,539、test 1,110,343、quarantine 140,373，identity leakage 0）；label provenance；deterministic Runtime、provider-neutral backend和`production_runtime_adapter_v1`；Evidence Fidelity Gate；官方Qwen raw部署与training harness。上述是基础设施，不是论文benchmark，也不自动证明session-level fine observation eligibility。

当前v1 online Runtime capability继续作为历史实现事实：Initial、packet 9–16、60s Temporal和limited Relation可用；Application/Payload/RAG formal online wiring未完成。旧TRAIN sidecars没有packet-index alignment且只覆盖旧候选，不能直接充当Evidence-v2正式资产。

DEC-0019与Training Protocol v1冻结Near-first及总体架构；DEC-0020的classification/sufficiency解耦继续有效。DEC-0021替代旧11类数据人口、旧Initial/payload/Temporal/Relation和single-gap Teacher监督；DEC-0022登记其完整实现与最终验收。

Model A Formal Near Multi-task SFT已启动且当前仍在服务器上运行；本次计划同步不修改训练代码、数据、配置、run或checkpoint，也不把中间状态写成论文结果。`RL_RUN=false`；`UNKNOWN_ALGORITHM_FROZEN=false`。旧Teacher V3 bulk、V2 corpus和acceptance只保留为superseded historical artifact。正式Dataset v3沿用filtered v2 assignment，六类train/validation/test为1,318,688/270,851/279,057；主generic/unobservable与sample identity overlap均为0。

Teacher-v2 raw cache为20,807/20,807 valid、quarantine 0。formal trajectory只保留至首次sufficient，并将161个terminal-inconsistent候选session从SFT supervision中quarantine；raw cache与target语义不改写。正式corpus为14,350 records / 11,958 sessions，SHA256 `d93789de29b746d923660bb2e4ccad501412e75303ddf95f7087c85f6c67d6ca`；3,231条Known validation使用`EXACT_EVAL_CLEAN`。8192-token Gate最大4,794、overflow 0；session-weight、label-map、U_final isolation与plan consistency均PASS。

**Model A readiness仍为`READY_FOR_FORMAL_SFT=true`，且`FORMAL_SFT_STARTED=true / IN_PROGRESS`。** 当前动作是安全完成Model A Formal SFT并执行正式validation；随后启动CICIDS2017与ToN-IoT的`MULTI_DATASET_COMPATIBILITY_GATE`。GRPO、Unknown、U_final与Agent正式实验仍未启动。

## 附录A：端到端执行链路速查

本节只将前述冻结方案按先后顺序汇总，不替代数据Gate、模型、Agent、实验和Decision Log中的详细约束。

### A. 研究项目执行链路

1. **Model A foundation：**Edge Production Freeze、v2 split、Dataset v3、Basic/Evidence-v2、Teacher-v2、corpus v3、Safe Adapter与raw Qwen均已完成。
2. **Model A SFT：**安全完成当前Formal Near Multi-task SFT并在冻结validation上评价；保留checkpoint作为controlled baseline与warm start。
3. **Multi-dataset Gate：**依次审查CICIDS2017、ToN-IoT；资源允许时审查CSE-CIC-IDS2018。
4. **Common data layer：**dataset-specific provenance adapter → common session → canonical label/evidence → leakage-safe grouped split。
5. **Model B：**扩展6→K Fine Head，继承backbone/LoRA/LM Head，联合Edge replay和external data进行balanced continuation SFT。
6. **Active acquisition：**在多域代表性数据上比较Basic、Full Evidence One-Shot、Static、Rule和Supervisor，报告accuracy-cost与stop behavior。
7. **RLAIF：**仅在SFT和Agent baseline稳定后构建mixed-domain trajectory subset，优化一个共享acquisition policy并保留classification CE。
8. **Open-world与收尾：**冻结Independent Unknown后一次性执行U_final；完成ablation、统计与writing。Few-shot仅留Future Work。

```text
Raw Qwen → Edge Model A Multi-task SFT
→ CICIDS2017/ToN-IoT common data contract
→ Multi-domain Model B continuation SFT
→ budget-matched Active Evidence experiments
→ optional mixed-domain RLAIF → Independent Unknown
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
9. Unknown、Evidence Insufficient与Abstain保持独立语义；few-shot/Class Memory不在当前主推理链路。
10. Runtime保存结构化result、动作、Evidence、Unknown、成本、延迟、provider identity和可审计Trace。

```text
Production Session → Runtime Safe Adapter → Evidence Stage
→ Qwen Traffic Expert → Fine Head + LM Evidence State
→ Independent Unknown → DeepSeek Flash Supervisor
→ Deterministic Runtime Evidence Tool → Qwen re-evaluate
→ Known Fine / Coarse / Unknown / Abstain
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
| 2026-08-13 | DEC-0021 | verified single-label capture provenance与旧11类PLAN_B population被当作每个reconstructed session都可用于fine classification，旧Initial/Teacher合同已完成并授权SFT | 冻结`FINE_CLASS_OBSERVATION_ELIGIBILITY_V2`：主类最多8个candidate；Backdoor为long-horizon case study，Uploading/Ransomware为observability-limited auxiliary；train/validation/test全部按同一full-observation contract过滤；Basic-v2含packet-aligned first-8 payload与cheap Application；Evidence State升级为固定family multi-gap；eligibility后重新运行Teacher-v2并生成corpus v3，旧formal launcher暂停 | capture-wide Evidence Salvage与class-conditional observability审计确认capture label不能证明每个session的fine evidence；Uploading/Ransomware网络不可观测，Backdoor仅少量long-horizon；旧payload缺packet index，Temporal/Relation/schema/population均不足以支撑新合同 | 主类population、eligibility、Basic/Evidence-v2、Teacher-v2和新corpus合同冻结；最终8/7/6类、eligible counts及是否沿用filtered old split由本轮pre-model数据Gate决定 | DEC-0019总体架构、DEC-0020 classification/sufficiency解耦、Production identity/sessionization、Near-first、U_dev/U_final isolation不变；旧11类PLAN_B/Teacher V3/V2 corpus变为superseded historical，`READY_FOR_FORMAL_SFT=false`直至新acceptance PASS |
| 2026-08-13 | DEC-0022 | DEC-0021的candidate、Evidence-v2、Teacher-v2与corpus仍是待实现状态，不能授权formal training | 冻结六类Observable Dataset v3与filtered v2 split；实现17-capture Evidence-v2；完成40-state Teacher smoke及20,807/20,807 resumable bulk；formal trajectory必须terminal sufficient并在首次sufficient停止；冻结11,958-session/14,350-record corpus v3与3,231条EXACT_EVAL_CLEAN validation | 六类正式train/validation/test为1,318,688/270,851/279,057，generic/unobservable/identity overlap为0；raw Teacher cache不改写，161个terminal-inconsistent session及6,116个post-sufficient反事实state仅从formal supervision quarantine；token max 4,794<8,192；weight/class-map/U_final/plan Gates PASS | Dataset v3、class map、Evidence schema、Teacher prompt/cache、trajectory curation、corpus/validation digests和`NEAR_SFT_CONFIG_V2`冻结；后续只能用validation做已预注册调参 | MITM/Port_Scanning不进入主CE；Backdoor/Uploading/Ransomware角色不变；旧assets仍保留；`READY_FOR_FORMAL_SFT=true`但`FORMAL_SFT_STARTED=false`，不授权RL/Unknown/U_final/Agent |
| 2026-08-14 | DEC-0023 | 论文主线同时强调LLM分类、Agent、RAG、Unknown与1/5/10-shot onboarding；Edge主实验后只以IoT-23独立适配作deferred外测 | 聚焦`COST_AWARE_ACTIVE_SEQUENTIAL_OBSERVATION_EVIDENCE_ACQUISITION`：保留正在训练的Edge Model A作为controlled baseline/warm start；正式增加CICIDS2017、ToN-IoT优先的multi-dataset Model B；Unknown保留，few-shot降为Future Work；mixed-domain RLAIF仅在SFT和Agent baselines稳定后执行 | TrafficLLM、ETooL、MalRAG、TrafficGPT/open-set TrafficLLM、NIDS-GPT与ICT-META已覆盖LLM traffic representation、multi-flow OOD、retrieval、open-set及few-shot适配；真正未被当前计划清晰隔离的问题是对当前session何时/按什么成本选择性获取Observation Evidence，以及该机制能否跨domain成立 | 核心问题、Model A/B顺序、dataset优先级、label/session/evidence合同与实验结构冻结；具体外部domain最终纳入、canonical K、Teacher抽样量和Model B sampling Gate由pre-model pilot冻结 | 不废弃DEC-0022数据/corpus或当前Formal SFT，不改变Qwen/Fine Head/LM Head/Supervisor/Runtime、Basic-v2、strict-past、U_final隔离；增加Compatibility Gate、canonical mapping quality、balanced replay与cross-domain evaluation；few-shot退出关键路径 |

生效关系：DEC-0001至DEC-0018作为历史记录完整保留。DEC-0011的BF16 LoRA、text-only、non-thinking与Independent Unknown边界继续有效；DEC-0019冻结总体架构，DEC-0020冻结classification/sufficiency解耦，DEC-0021定义数据合同，DEC-0022冻结Model A实际数据与formal training输入，DEC-0023重新聚焦论文问题并增加Model B路线。Production identity、60秒sessionization、v2 physical split、U_dev/U_final isolation、Qwen/Supervisor/Runtime职责、Basic-v2与当前checkpoint lineage不变。当前研究语义以DEC-0019至DEC-0023及`task_definition_v2.md`为准。
