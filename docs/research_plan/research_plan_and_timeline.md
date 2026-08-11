# 网络流量开放识别与自适应取证智能体：执行计划与时间表

> 本文件由`research_plan_detailed.md`派生，只定义任务、依赖、Gate和时间；研究语义冲突时以详细版为准。更新时间：2026-08-11。

## 1. 当前主线与冻结状态

论文研究会话级网络流量的开放世界新类别生命周期。后训练Qwen3.5-9B直接读取网络证据并独立执行第一次fine/coarse分类与证据充分度分析，冻结的开放集评分/校准层据其模型信号产生Unknown决策；Adaptive Decision Agent根据分类、Unknown结果、证据缺口、工具状态和预算，决定接受、退回粗类、扩展包/时间/图上下文、请求应用层证据、检索知识、重新分类、拒识或请求人工。

正式主链路为：

```text
网络流量样本
→ 会话级混合表示
→ 后训练Qwen3.5-9B第一次分类
→ fine/coarse候选、证据状态及可供开放集计算的模型信号
→ Frozen Unknown Scoring / Calibration
→ Agent按需取证、重新分类、拒识或接入新类
```

不同数据集保留原生标签，通过统一`DatasetLabelSchema`、`CanonicalSessionRecord`和Session Evidence Card运行同一方法，不强制统一ATT&CK。双数据集角色现已冻结：Edge-IIoTset承担完整方法开发与主实验，IoT-23承担另一原生标签体系和独立scenario/capture下的外部验证。

| 项目 | 状态 | 执行含义 |
| --- | --- | --- |
| Edge-IIoTset | **主数据集，带冻结限制使用** | 完整运行闭集/coarse/fine、Near/Far/Mixed Unknown、传统强基线、Agent、1/5/10-shot和成本/恢复实验；不宣称跨攻击run泛化 |
| IoT-23 | **第二数据集，Production ready（带限制）** | 官方日志/PCAP、统一Adapter、独立scenario划分、原生coarse `Exploitation` U_final及1/5-shot support/query均已冻结；压缩外部验证仍须限制小样本结论 |
| CICIoMT2024、X-IIoTID等 | 历史候选/备选 | 既有审计保留，不再是当前立即执行主线 |
| 其他NF3/NF-ToN/CICIoT2023等 | 退出当前主线 | 停止广泛候选搜索；仅在IoT-23生产构建出现新阻断并新增Decision时重选第二数据集 |
| 会话表示 | 接口和初始包预算已定 | 两个Adapter输出`CanonicalSessionRecord`；序列最多保存16包，首次分类使用前8包，Agent可请求第9至16包 |
| K_known/U_dev/U_final | **已冻结且本轮未改变** | Edge Near/Far/Mixed与IoT-23原生coarse预设均已进入Production manifest；`U_final`继续严格隔离 |
| Edge paper-grade split | **v2已完成（带限制）** | `CONSTRAINED_CHRONOLOGICAL_BOUNDARY_V2`保留7,619,032个identity；ZERO/CRITICAL_LOW均降为0；DDoS_UDP与OS_Fingerprinting仍为structural limitation |
| SFT候选 | **PLAN_B已物化，尚未训练** | `CLASS_BALANCED_DIVERSITY_AWARE_SFT_SELECTION_V1`仅取`K_known ∩ train`；Near/Far/Mixed为16,979/15,895/15,404条唯一sample |
| Qwen3.5-9B SFT/DPO | 尚未开始 | Qwen是主分类器；默认text-only BF16 LoRA SFT、冻结视觉模块并使用non-thinking输出，QLoRA仅为降级路线，DPO保持条件性 |
| Supervisor/Runtime/Policy | **工程foundation已实现** | deterministic Runtime、RulePolicy合同与provider-neutral Supervisor backend preparation已通过synthetic/Fake Provider审计；真实provider、正式配置与实验尚未开始 |
| Production→Runtime | **Safe Adapter v1已实现** | exact allow-list Initial Evidence、9–16包、strict past-only temporal、匿名relation、phase/U_final与跨层泄漏测试通过；application/payload/production RAG仍UNAVAILABLE |

## 2. 任务依赖与数据Gate

```text
DEC-0009与双数据集最终Gate同步（已完成）
→ DEC-0010与服务器初始化、官方数据恢复（已完成）
→ Production Data Freeze、provenance、K/U、support/query和training manifest（已完成）
→ deterministic Runtime与provider-neutral backend preparation（已完成）
→ 提升至main唯一长期基线并标记baseline-pre-model-20260811（已完成）
→ Edge paper-grade split、Paper Evaluation Readiness、PLAN_A/B/C与PLAN_B候选物化（已完成）
→ Production→Runtime白名单adapter与跨层泄漏测试（已完成）
→ 经另行授权后配置本地OpenAI-compatible Qwen Traffic Expert环境
→ Qwen3.5-9B加载与text-only BF16 LoRA SFT小规模冒烟
→ Edge-IIoTset完整主实验
→ IoT-23压缩外部验证
```

启动训练前的数据条件已经冻结：Edge生产级会话与标签可用；两个Adapter输出统一Schema；包级字段和会话摘要可复现；split、K/U、support/query和training manifest已冻结；identity dedup、exact/near sensitivity与直接泄漏受控；会话及past-only上下文只在各split内部独立构造；known-only和full-frozen知识域隔离。IoT-23正式原生coarse Unknown与1/5-shot资产已验证，限制仍须进入实验结论。

传统模型不进入正式主链路。LightGBM、XGBoost、Random Forest和Logistic Regression只作为闭集/开放集、速度/成本、泄漏诊断及可选融合基线；树模型OOF概率不是Qwen训练的必要输入。

## 3. 冻结实验协议

### 3.1 输入、Known、Unknown与few-shot

- 基础输入为双向会话前8个包的方向、长度、IAT、协议/flags，加会话持续时间、双向包数/字节数、包长/IAT统计和缺失声明；包序列最多保存16包，Agent可请求第9至16包。
- 应用层字段、有限脱敏Payload、past-only时间上下文和局部图摘要由Agent按需获取；缺失证据通过`capabilities`和`missing_fields`声明。
- `K_known`进入Qwen SFT和传统基线；`U_dev`不得作为主分类监督进入SFT，只用于Unknown算法、校准/阈值、证据扩展与策略开发；`U_final`对SFT/DPO、Prompt、known-only RAG、Unknown算法选择、阈值、Agent/策略训练和人工调参完全隔离。
- Unknown至少覆盖Near、Far和Mixed多套预注册组合并使用多个随机种子。
- 阶段A使用known-only知识做Unknown拒识；阶段B只对已拒识样本开放full-frozen RAG做Top-k候选；阶段C获得sample-level 1/5/10-shot后注册新类，并在无相同记录或精确重复的query上评价。
- Edge physical assignment使用capture内chronological v2：complete-session crossing quarantine加local 5秒embargo；不random shuffle，不跨capture混切。Paper readiness与Production integrity分开报告。
- 完整Production保持真实分布；正式SFT候选单独使用`PLAN_B`，按near diversity→exact diversity→bounded multiplicity选择，sample ID唯一，不让百万级高重复类按raw frequency支配examples/tokens/loss/gradient updates。
- 只使用锚点之前的信息；训练、验证、测试分别构造会话和上下文，不跨split检索邻居。

### 3.2 Qwen与Agent

Qwen3.5-9B直接承担第一次known fine/coarse分类、证据充分度和supporting/missing evidence输出，并提供可供open-set计算的模型信号；独立Frozen Unknown Scoring / Calibration层负责正式Unknown决策，具体算法和阈值只使用`K_known`与`U_dev`开发。LLM自报confidence/unknown probability只作为待验证变量。正式训练默认采用text-only BF16 LoRA SFT，冻结视觉模块，使用原生Tokenizer、固定证据卡序列化和non-thinking/direct-response；QLoRA仅为显存或兼容性降级。分类头或标签Token、Unknown具体算法、SFT样本格式、Tokenizer扩展与领域继续预训练均未冻结。

Agent在Qwen第一次分类后选择：`ACCEPT_FINE`、`BACKOFF_COARSE`、`EXPAND_PACKETS`、`EXPAND_TEMPORAL_CONTEXT`、`EXPAND_GRAPH_CONTEXT`、`REQUEST_APPLICATION_EVIDENCE`、`RETRIEVE_KNOWLEDGE`、`RECLASSIFY`、`REJECT_UNKNOWN`、`RETURN_TOPK`、`REQUEST_LABEL`、`REGISTER_NEW_CLASS`或`ABSTAIN`。`CALL_LLM_EXPERT`不再是正式动作。

Agent以Evidence State表达当前候选、Unknown状态、证据充分度、缺失证据类型、可用能力、请求历史、工具失败和剩余预算，并按`状态→识别缺口→选择合法证据源→更新状态→重分类或停止`运行。观测缺口必须通过包、past-only时间/关系上下文或合法应用字段取得真实网络证据；只有协议、行为或标签语义的知识缺口才优先使用RAG，RAG不得补造未观察到的流量事实。

当前Agent主方案使用High-Capability LLM Supervisor读取Qwen Traffic Expert输出和Evidence State，由deterministic Python Runtime执行Schema、capability、预算、去重、轮数、Memory权限、故障和Trace约束。Supervisor每轮只选择一个合法动作，不直接替代Qwen输出fine分类；通过`SupervisorBackend`抽象允许初期在线高能力模型在未来替换为本地兼容模型，具体型号尚未冻结。

RulePolicy是必须保留的强可复现baseline，Strong Static继续包含合理的固定取证、retry、fallback与validator；LearnablePolicy仅为可选扩展。Experience Memory只保存经过可靠反馈验证的决策经验，train可写、主test/`U_final`冻结只读；人工确认新类的Class Memory与其分离。错误先归因到证据、策略、Qwen、Unknown校准、RAG或工具等对应组件，再决定更新位置。

### 3.3 四组实验

| 实验 | 主要比较 | 回答的问题 |
| --- | --- | --- |
| 一：LLM独立分类能力 | LR、RF、LightGBM/XGBoost、原始Qwen、后训练Qwen | Qwen独立分类的能力、成本及相对传统强基线的边界 |
| 二：开放集与自适应取证 | 传统开放集、单次Qwen+冻结Unknown；Basic vs Fixed Full；预算匹配的Fixed Full、强Static、RulePolicy、High-Capability LLM Supervisor及可选LearnablePolicy；逐项证据源消融 | 区分更多证据本身、动态选择、高能力Supervisor和各证据源的贡献，并检验收益是否来自额外资源 |
| 三：1/5/10-shot新类接入 | 重训、最近邻/原型、Qwen ICL、RAG原型、Agent注册和可选LoRA | 新类能否低成本接入且不显著遗忘旧类 |
| 四：IoT-23独立场景外部验证 | IoT-23独立适配与scenario split下的闭集、一套Unknown和一套Agent上下文增益；允许时增加1/5-shot | 同一接口、Qwen协议、Unknown生命周期和Agent决策能否适用于另一采集环境和原生标签Schema |

主要指标包括Known Macro-F1、Unknown AUROC/AUPR/FPR95/OSCR/H-score、层次退回、新类F1与遗忘、任务成功、证据/工具选择、恢复、预算遵从、输出合法、Qwen/Supervisor/RAG/工具调用、延迟和成本。

实验二中Agent与Static固定使用相同Qwen、工具、信息域和最大预算，报告证据请求率、Qwen/RAG/工具调用次数、延迟、Token/API成本与utility-cost曲线。packet、temporal、graph、application和RAG分别消融；固定全证据用于回答证据上界，不等同于动态Agent。

在传统开放集基线完成后，实现“Unknown拒识+被拒识样本随机分配至候选新类”的零信息标签扩展诊断，并输出Known-to-Novel FPR、新类Macro-F1、混淆矩阵及多随机种子结果；该诊断不替代合理的传统Unknown拒识基线。

主Near/Far/Mixed完成后可按时间与readiness决定是否执行独立的`OPTIONAL: Low-Resource Unknown Stress Test`。候选只依据pre-model session support与exact/near diversity，禁止根据模型结果事后挑类；若执行，必须与主结果分开报告scarcity-driven Unknown拒识和few-shot Class Memory注册，且不改变现有K/U。当前状态为`PLANNED_OPTIONAL_NOT_RUN`。

## 4. 当前可执行工作与停止项

### 4.1 本阶段已执行

1. 回溯旧的“传统模型主分类+Qwen Reviewer”架构影响；
2. 区分已实施基础设施、历史基线、计划文字和未执行设想；
3. 纠偏三份研究计划并新增DEC-0006、DEC-0007；
4. 完成Edge-IIoTset官方数据获取和Phase 2客观可行性审查；
5. 新增DEC-0008，冻结Edge主实验与IoT-23外部验证的双数据集职责；
6. 使用最小官方数据完成双数据集最终Gate，两个Adapter、标签对齐、无直接身份泄漏、no-service非随机可学习性和Qwen输入合同均通过，新增DEC-0009；
7. 冻结正式数据处理向远程服务器迁移的执行位置与恢复方案，新增DEC-0010；
8. 完成本地收尾、GitHub `main`可复现停止点与受限数据清理；
9. 完成远程服务器初始化、官方数据恢复、Production全量冻结、provenance与class-role复审；
10. 完成deterministic Runtime foundation、provider-neutral backend preparation及其安全集成；
11. 将全部必要历史提升至唯一长期分支`main`，并将pre-model基线`3ab33e36c8508bcd31afac2e12c094ae1fe0a964`标记为`baseline-pre-model-20260811`；
12. 完成Edge paper-grade split revision、label provenance final verification、Paper Evaluation Readiness、SFT PLAN_A/B/C simulation、PLAN_B候选物化和Low-Resource pre-model candidate analysis；Low-Resource Unknown Stress Test只登记为OPTIONAL且未运行。

### 4.2 本阶段停止

- 不把验收Adapter和RF探针写成生产流水线或论文结果；
- 不在全量split、K/U、support/query及训练manifest冻结前启动Qwen训练；
- 不冻结分类头/标签Token、Unknown算法、SFT格式、精确时间窗口或Agent学习算法；
- 不启动Qwen SFT、DPO、继续预训练、正式传统模型训练或Agent实验；
- 不把已完成的服务器数据/代码冻结写成模型或训练已经完成；当前没有模型权重，真实provider、Qwen下载与训练均须另行授权；
- 不恢复传统分类器筛选Qwen样本、Tree-aware Reviewer或固定`Classifier→RAG/LLM`主链路。

## 5. T0后四周时间表

T0定义为：生产级`CanonicalSessionRecord`和两个Adapter通过回归，Edge与IoT-23各自原生标签Schema、split、K/U、support/query、包/摘要字段、信息域和training manifest获得冻结。该条件已由Production Data Freeze达成；外部正式实验仍未启动。

| 阶段 | 主要工作 | 产出与退出条件 |
| --- | --- | --- |
| 双数据集最终Gate | 以最小官方数据实测标签、PCAP对齐、两个Adapter、非随机RF、捷径、泄漏和Qwen输入合同，并同步DEC-0009 | 整体`PASS_WITH_LIMITATIONS`；证据归档于`reports/data_feasibility_gate_20260806/` |
| 本地收尾与服务器迁移 | push代码、报告、manifest、哈希与下载说明，完成受限数据清理并租用可SSH访问的服务器 | **已完成：**DEC-0010生效，GitHub `main`形成可复现停止点；本地不再承担正式全量处理 |
| 服务器初始化 | **已完成：**验证Git同步，初始化独立数据/资产/模型目录，确认硬件/GPU、权限与数据处理环境 | 仓库和基础环境可复现；不把具体平台、GPU型号或路径冻结为研究方法 |
| 生产Adapter与manifest冻结 | **已完成：**固化`CanonicalSessionRecord`和两个Adapter；冻结全量split、K/U、support/query、异常文件处置和training manifest | `PRODUCTION_DATA_READY=true`，限制已记录 |
| Main基线同步 | **已完成：**集成Production、Runtime与provider-neutral backend preparation，完整审计后提升至唯一长期分支`main`并打基线标签 | 审计起点`main=origin/main=3ab33e36...`，`baseline-pre-model-20260811`指向该提交；状态同步commit不自动push |
| Edge数据协议修订 | **已完成：**只重建split-dependent资产，完成v2 split、readiness、PLAN_A/B/C、PLAN_B候选及provenance final Gate | identity universe与K/U不变，`SPLIT_REVISION_STATUS=PASS_WITH_LIMITATIONS`，无Qwen/SFT运行 |
| T0后第1周 | 配置GPU模型环境；加载Qwen3.5-9B并使用冻结PLAN_B候选完成text-only BF16 LoRA SFT小规模冒烟；完成传统和原始Qwen基线 | 模型、独立Unknown评分接口与数据链路可运行，无Final泄漏 |
| T0后第2周 | 完成Edge Qwen主训练、闭集/coarse/fine和强Static | Qwen稳定输出fine/coarse、证据状态和开放集模型信号，冻结Unknown层产生可复现决策 |
| T0后第3周 | 完成Edge Near/Far/Mixed Unknown、deterministic Runtime、RulePolicy和High-Capability LLM Supervisor；LearnablePolicy与DPO仅作条件性判断 | Edge实验一、实验二和utility-cost结果冻结 |
| T0后第4周 | 完成Edge sample-level 1/5/10-shot、错误/成本分析及IoT-23压缩外部验证；同步论文初稿 | 实验三、实验四、限制和复现清单完成 |

## 6. 里程碑与停止条件

| Gate | 通过条件 | 不通过时 |
| --- | --- | --- |
| G0 Edge数据与会话 | Edge合法可用，标签与会话粒度可解释，包序列/摘要可构造，限制已冻结 | 使用capture内时间块与隔离gap，限制结论；异常文件显式处理，不以随机切分替代 |
| G0b IoT-23验收 | **已带限制通过：**官方数据可解析、标签可用、可构造独立scenario训练/验证/测试 | 固化生产Adapter；处理Somfy未匹配记录和正式Unknown支持数，不重选数据集 |
| G1 输入与基线 | 会话表示可复现，传统强基线和原始Qwen基线可公平运行 | 收缩到可验证表示，限制结论，不虚构跨会话能力 |
| G2 Qwen SFT | 后训练Qwen能稳定输出分类、证据状态和可供独立Unknown评分使用的模型信号，且无Final信息泄漏 | 停止DPO/规模扩展，保留原始Qwen与失败边界 |
| G3 Agent | 相同Qwen、工具、信息域和预算下，High-Capability LLM Supervisor相对Rule/Static至少改善任务成功、恢复或utility-cost | Rule/Static成为推荐方案，Supervisor Agent降为边界分析 |
| G4 Few-shot | support/query无相同记录或精确重复，新类提升且旧类遗忘可控 | 保留Unknown与候选识别；group-level只在有可靠活动标识时追加 |

## 7. 风险与压缩顺序

Edge单capture、固定端点和时间捷径通过capture内时间块、隔离gap、后台字段隔离和敏感性消融控制，主结论限定为同采集环境。IoT-23已通过官方数据、标签和scenario隔离Gate；正式阶段重点处理Somfy-01最低81.54%匹配率及Capture-42未知恶意样本仅6条的限制，不恢复广泛数据集搜索。会话或包证据不足时收缩输入并限制结论；Qwen无优势时报告相对传统基线的能力与成本边界；Agent无优势时采用强Static。

时间不足时依次取消继续预训练/Tokenizer扩展、27B、DPO、复杂LearnablePolicy和IoT-23 few-shot扩展；BF16 LoRA因显存或兼容性受阻时才降级为QLoRA。保留可复现数据、Edge实验一、开放集最小实验二、sample-level实验三、IoT-23三项压缩验证和论文初稿。

## 8. 下一执行顺序

1. **已完成：**Edge split/SFT data protocol回归、报告和Git冻结已进入本地main；
2. **已完成：**Production Runtime Safe Adapter v1、真实数据smoke、phase/U_final与跨层泄漏回归；
3. **下一步需另行授权：**实现只接收Runtime model-safe prompt的本地OpenAI-compatible Qwen Traffic Expert transport/smoke；
4. 随后加载Qwen3.5-9B并使用PLAN_B候选完成text-only BF16 LoRA SFT小规模冒烟；
5. 执行Edge-IIoTset完整主实验和IoT-23压缩外部验证；主实验与时间允许时，再按预注册规则决定是否执行独立的OPTIONAL Low-Resource Unknown Stress Test。

## 9. 端到端流程速查（压缩版）

### 9.1 研究项目执行链路

1. **数据与Gate：**冻结Edge-IIoTset主实验和IoT-23独立scenario外部验证职责，从官方来源下载、校验并归档原始数据。
2. **Production构建：**已解析packet、重建双向session、对齐标签并生成`CanonicalSessionRecord`。Edge Label Provenance Audit与24-capture guard已通过（带记录限制），hash、purity、fallback与quarantine规则不得绕过。
3. **数据冻结：**按immutable backend identity处理真正重复；Edge现采用paper-grade capture-local chronological v2、crossing quarantine与5秒embargo，并冻结split内past-only上下文、字段白名单、exact/near sensitivity、K/U、support/query和PLAN_B SFT候选manifest。
4. **版本集成：**Production、Runtime与provider-neutral backend preparation已审查、测试并进入统一`main`基线`3ab33e36...`。
5. **环境与基线：**部署Qwen3.5-9B训练环境，在冻结数据上运行传统模型和Raw Qwen基线；传统模型不承担前置路由。
6. **SFT：**仅从`K_known/train`构造监督数据，先smoke test，再执行默认text-only BF16 LoRA SFT；QLoRA只作资源/兼容性fallback或量化消融。
7. **SFT评价：**比较Raw Qwen与SFT Qwen的分类、证据理解、结构化输出、速度和成本。
8. **Unknown：**只用`K_known`和`U_dev`选择并校准独立Unknown评分，在预注册Near/Far/Mixed上评价；`U_final`在最终测试前隔离。
9. **Adaptive Agent：**实现deterministic Runtime与可替换`SupervisorBackend`，由High-Capability LLM Supervisor根据Evidence State每轮选择一个合法动作；在相同Qwen、工具、信息域和预算下比较Basic、Fixed Full、Strong Static、RulePolicy、Supervisor和可选LearnablePolicy。
10. **消融与Few-shot：**消融packet、temporal、graph、application和RAG，随后使用预注册1/5/10-shot support评价新类接入与旧类遗忘。
11. **条件性DPO与外部验证：**DPO只在可靠偏好问题和数据存在时开展；在IoT-23自身标签与scenario split下完成closed-set、Unknown和Agent压缩验证。
12. **结果与论文：**汇总正式指标、成本、敏感性、组件级错误和限制，按“Qwen分类→Unknown→Adaptive Agent→Few-shot”完成论文。

```text
数据与Gate → Production Freeze → Qwen部署 → Raw/Traditional Baseline → BF16 LoRA SFT → Unknown → Supervisor Agent → Few-shot → IoT-23外部验证 → 最终实验 → 论文
```

### 9.2 系统实际识别链路

1. 接收PCAP或等价捕获并解析packet可观察字段，来源和真实身份只留在backend审计层。
2. 按双向通信关系和已冻结的60秒inactivity规则重建session；Edge Label Provenance与Production Freeze已确认该口径，session不跨capture。
3. 生成隔离model-unsafe字段的`CanonicalSessionRecord`，再构造前8包加完整session summary的Initial Evidence Card；service category不进入Primary View。
4. 后训练Qwen3.5-9B直接输出fine/coarse候选、supporting/missing evidence、evidence sufficiency和开放集模型信号，不经过传统模型路由。
5. 独立Frozen Unknown Scoring / Calibration产生正式Unknown判断，不采用未经验证的LLM自报概率。
6. Evidence State汇总分类、Unknown、缺失证据、capabilities、请求历史、工具失败、动作、剩余预算和少量validated experience。
7. High-Capability LLM Supervisor读取model-safe状态，由deterministic Runtime约束每轮只执行一个合法动作；Supervisor不直接替代Qwen输出fine分类。
8. 按需扩展第9至16包、past-only时间上下文、局部关系图或合法应用层证据；完整session继续用于summary。
9. 只有knowledge gap才调用RAG，observational gap必须取得真实网络观测，RAG不得补造流量事实。
10. 新证据和失败写回Evidence State，Qwen重新分类，独立Unknown层重新评估，再由Supervisor决策。
11. Runtime在预算和最大深度内循环，最终输出Fine、Coarse、Unknown或Abstain；合法人工support存在时才写入独立Class Memory并执行新类注册。
12. 保存结构化最终结果、supporting evidence、Agent动作、工具调用、成本/延迟和完整Trace。

```text
Raw Traffic → Packet Parsing → Bidirectional Session → CanonicalSessionRecord → Initial Evidence Card → Qwen Traffic Expert → Frozen Unknown Scoring → Evidence State → High-Capability LLM Supervisor → one legal action via Deterministic Runtime → Evidence Acquisition → Reclassification → Fine / Coarse / Unknown / Abstain → Structured Result + Trace
```
