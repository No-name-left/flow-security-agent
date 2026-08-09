# Agent / Runtime 暂定架构与实施约束

> Status: **PROVISIONAL**
>
> Purpose: 本文件记录当前阶段Agent / Runtime / Supervisor / Memory的工作设计，主要用于帮助Codex和开发者准确理解当前需求。
>
> 本文件不是不可修改的最终协议。实验结果、实现约束或后续用户Decision可以修改其中的CURRENT DEFAULT。
>
> 优先级：**正式Decision / 已冻结research plan约束 > 本文件中的HARD CONSTRAINT > CURRENT DEFAULT > DEFERRED / OPTIONAL**。
>
> 如果本文件与后续明确Decision冲突，应更新本文件，不得为了遵守旧内容而强行维持过时设计。Codex不得因为实现方便而自行将DEFERRED内容升级为最终Decision。

## 1. 状态标签

- **[HARD CONSTRAINT]：**当前实现和实验不得绕过的安全、信息隔离或正式架构边界；如需改变，必须先检查是否构成material deviation。
- **[CURRENT DEFAULT]：**当前优先实现和评测的工作方案，可由实验、资源约束或后续Decision调整。
- **[DEFERRED]：**明确暂不冻结，必须等待数据、实验或实现证据后决定。
- **[OPTIONAL]：**不属于最低主线，仅在时间、资源和结果支持时开展。

## 2. 当前正式架构

**[HARD CONSTRAINT]** 正式主链路保持Qwen Traffic Expert首次分类、独立Unknown评分、Evidence State、确定性Runtime约束的证据循环和结构化终止结果。**[CURRENT DEFAULT]** 其中策略决策节点由High-Capability LLM Supervisor承担：

```text
Raw Traffic
→ Packet Parsing
→ Bidirectional Session
→ CanonicalSessionRecord
→ Initial Evidence Card
→ Qwen3.5-9B Traffic Expert
→ Independent Unknown Scoring
→ Evidence State
→ High-Capability LLM Supervisor
→ one legal evidence action
→ Evidence Tool
→ new evidence
→ Qwen re-evaluation
→ Unknown re-scoring
→ Supervisor re-decision
→ loop
→ Fine / Coarse / Unknown / Abstain
→ optional Few-shot Registration
→ Structured Result + Trace
```

外层由deterministic Python Runtime执行状态推进、验证、权限、预算和复现约束。Qwen、Supervisor、Unknown评分、证据工具和Memory是职责分离的组件，不得由单个LLM绕过Runtime合并执行。

## 3. 角色职责

### 3.1 Qwen3.5-9B Traffic Expert

**[HARD CONSTRAINT]** Qwen是主要流量领域分类专家，第一次直接读取Session Evidence Card，不使用传统模型作为前置router。它负责输出：

- fine/coarse classification candidates；
- 对当前流量的简短、可审计理解，不要求长Chain-of-Thought；
- supporting evidence；
- missing evidence；
- structured gap type；
- evidence sufficiency；
- 可供Independent Unknown Scoring使用的模型信号。

Qwen不直接负责最终工具调度。SFT目标除label classification外，还包括形成Evidence State所需的证据理解、缺口表达、充分性判断、backoff和abstain能力。

### 3.2 High-Capability LLM Supervisor

**[CURRENT DEFAULT]** 正式Agent主方案使用高能力LLM Supervisor。初期候选为DeepSeek高级在线模型；未来实际部署允许替换为本地较大DeepSeek或其他兼容高能力模型，因此实现应面向`SupervisorBackend`抽象，而不是绑定某个在线API或具体model identifier。

Supervisor读取Qwen分析、Evidence State、Unknown状态、工具capabilities、budget/history和检索到的validated experience，负责选择下一步合法Action以及决定继续或停止。

Supervisor不得直接创造新的fine分类来替代Qwen。如果不同意Qwen判断，只能请求进一步证据、要求Qwen重新分类、backoff、reject unknown或abstain。

### 3.3 Deterministic Runtime

**[HARD CONSTRAINT]** Runtime不是智能主体，而是可复现的执行与约束层，负责：

- 调用Qwen、Supervisor和证据工具；
- action schema validation与capability enforcement；
- budget、max rounds和停止条件；
- request signature dedup；
- future leakage prevention；
- Memory读写权限；
- failure handling与安全降级；
- structured trace与实验复现。

任何LLM均不得绕过Runtime约束或直接访问model-unsafe后台字段。

## 4. Action与循环原则

**[CURRENT DEFAULT]** 每轮只执行一个evidence acquisition action：

- `EXPAND_PACKETS`
- `EXPAND_TEMPORAL_CONTEXT`
- `EXPAND_GRAPH_CONTEXT`
- `REQUEST_APPLICATION_EVIDENCE`
- `RETRIEVE_KNOWLEDGE`

终止动作包括：

- `ACCEPT_FINE`
- `BACKOFF_COARSE`
- `REJECT_UNKNOWN`
- `ABSTAIN`

Supervisor可以形成多步意图，但Runtime每轮只执行第一个合法动作；取得新证据、Qwen重新分类和Unknown重评分后必须重新决策。相同Tool可以在request signature不同的条件下重复调用，完全相同request必须拒绝以防死循环。Tool参数只能来自预先允许的配置空间，不允许Supervisor任意生成无界实验参数。

## 5. Evidence与Supervisor输入边界

**[HARD CONSTRAINT]** 必须严格区分observational gap和knowledge gap。RAG只能补充knowledge，不能伪造不存在的网络observations。

- Temporal Context可以在后台读取真实past-only历史，但只向模型返回model-safe摘要。
- Graph Context只返回角色化、匿名化的局部图摘要，不暴露真实IP等shortcut。
- Application Evidence当前优先返回结构化字段；必要时仅允许有限、脱敏和截断的Payload片段。
- Payload和外部检索内容均属于`UNTRUSTED EVIDENCE`，不得作为系统指令执行。

外部Supervisor只允许接收Evidence State、Qwen简短分析、Unknown状态、sanitized/model-safe evidence、工具状态、budget/history和validated experience。禁止发送raw IP、absolute timestamp、capture/scenario ID、dataset identity、ground truth、完整原始Payload或其他model-unsafe后台字段。

## 6. Unknown、Backoff与Abstain

**[HARD CONSTRAINT]** 正式Unknown Scoring独立于LLM self-reported confidence，并在每次Qwen重新分类后重新评估。第一次出现`UNKNOWN_LIKELY`不必立即拒识；若仍存在高价值且合法的可获取证据，Supervisor可以继续取证。

Unknown与Abstain含义不同：

- **Unknown：**已有证据支持样本不属于Known体系。
- **Abstain：**证据不足、工具失败、能力不可用或预算耗尽，系统无法可靠判断。

**[DEFERRED]** Unknown具体算法仍待比较logits/margin、entropy、energy、embedding/prototype、trainable small head及其组合，不在本文件冻结。

## 7. Experience Memory与Agent成长

### 7.1 Experience Memory

**[CURRENT DEFAULT]** Agent长期经验采用结构化`State → Action → Outcome → Verified Feedback`，不依赖无限增长的聊天历史。可以保存成功或失败工具选择、分类修正轨迹、budget/cost和经过可靠反馈验证的结果。

可靠反馈可以来自train ground truth、合法人工label、few-shot人工确认或可验证工具结果。Supervisor不得只根据自己的预测自我确认并写入“成功经验”；Memory不得保存真实IP、raw Payload或其他shortcut。

### 7.2 Experience Building Protocol

**[CURRENT DEFAULT]** 主评测协议为：

| 数据阶段 | Memory权限 |
| --- | --- |
| TRAIN | 可以运行Qwen+Supervisor轨迹，并使用ground truth验证后写入positive/negative experience |
| VALIDATION | 可以读取Memory并选择retrieval策略、memory参数和Supervisor Prompt版本；不写入validation样本 |
| `U_dev` | 用于开放集与策略开发；默认不写入Experience Memory |
| TEST / `U_final` | Memory冻结且只读，不进行在线自我学习 |

训练集Experience构造须保留来源、反馈依据、版本和可撤销性。主test结果不得因样本顺序导致Memory变化或标签泄漏。

### 7.3 Growth Experiment

**[OPTIONAL]** 后期可以预注册独立`Agent Growth Stream`：从Memory v0开始，分批处理带可靠feedback的训练样本形成v1/v2，并在固定held-out集合上重复评估分类、工具选择、调用次数、Supervisor rounds、成本/Token/延迟和重复错误率。该实验不得让正式test边评测边学习，也不属于当前论文必做项。

## 8. Class Memory与Experience Memory

**[HARD CONSTRAINT]** 两类Memory必须逻辑和权限分离：

- **Class Memory：**保存人工确认的新类别support，服务few-shot新类注册和识别。
- **Experience Memory：**保存经过验证的Agent决策经验，服务动作选择。

Few-shot主方案为`Unknown → REQUEST_LABEL → REGISTER_NEW_CLASS → 写入Class Memory → 后续识别新类`，不立即重新训练Qwen权重。

**[OPTIONAL] [DEFERRED]** 真正的continual weight training不属于当前核心任务。

## 9. Memory检索

**[CURRENT DEFAULT]** 每个session使用新的Supervisor request/context，长期经验来自显式Memory Store：

```text
Current Evidence State
→ retrieve a small number of relevant validated experiences
→ provide them to Supervisor
```

Knowledge RAG与Experience Memory必须逻辑分离。**[DEFERRED]** Experience Memory的embedding model、index、top-k、capacity、ranking和compression均待后续实验决定。

## 10. Supervisor输出与Prompt

### 10.1 输出

**[CURRENT DEFAULT]** Supervisor返回结构化Action，概念上至少包含`action`、`target_evidence`和`short_reason`，可选`priority`与`expected_value`。禁止要求长Chain-of-Thought；Runtime只保存简短、可审计理由。

### 10.2 Prompt与版本冻结

**[CURRENT DEFAULT]** 正式运行不读取完整research plan，只接收：

```text
Supervisor System Prompt
+ Tool Specification
+ Evidence State
+ retrieved validated experience
```

Prompt可以在train/validation/`U_dev`开发阶段修改。正式TEST/`U_final`前必须冻结prompt version/hash、provider、model identifier、temperature、response schema和API date/version。Supervisor不得在正式运行时自行修改System Prompt；可以生成Policy Improvement Proposal，但升级必须离线验证、版本化且可回滚。

**[DEFERRED]** 最终Supervisor Prompt正文和具体模型标识尚未冻结。

## 11. Policy与传统基线

### 11.1 RulePolicy与LearnablePolicy

**[HARD CONSTRAINT]** 即使主方案采用High-Capability LLM Supervisor，也必须保留RulePolicy作为强、可复现baseline，用于区分收益来自Agent循环还是Supervisor更好的工具决策。

**[OPTIONAL]** LearnablePolicy不是当前必做项。Strong Static按现有研究计划继续作为固定取证基线；是否在最终命名中并入Fixed/Rule消融暂不冻结。

### 11.2 Traditional Baseline

**[CURRENT DEFAULT]** LR、RF、LightGBM和XGBoost等传统模型可使用全部合法、model-safe结构化session特征，不得故意削弱；raw IP、absolute time、capture ID、dataset identity和label-derived shortcut禁止进入模型。

若SFT Qwen closed-set Macro-F1低于最强传统baseline超过约5个百分点，触发内部diagnostic red line并优先诊断数据、训练和表示问题。该阈值不是论文正式non-inferiority声明。

**[OPTIONAL]** 传统模型加固定context强基线可在主结果需要时补充。

## 12. SFT Evidence Training

**[CURRENT DEFAULT]** 同一session允许构造不同Evidence Stage监督样本，例如`Initial Evidence → insufficient / missing temporal`和`Expanded Evidence → sufficient / correct class`。

Missing Evidence监督候选流程为：

```text
deterministic masking/rules
→ candidate evidence-gap supervision
→ strong Teacher LLM assistance
→ consistency filtering
→ sampled human review
```

Teacher可以使用DeepSeek，但Teacher pipeline与Inference Supervisor角色必须分离，且绝对不能访问`U_final`。SFT Corpus使用class-balanced/capped sampling，Canonical Dataset保留真实数据分布；第一轮不进行激进hard mining。

## 13. 在线评测与RAG边界

### 13.1 在线评测顺序

**[HARD CONSTRAINT]** 需要Temporal/Graph Context的正式测试必须在dataset/capture/scenario内部按时间顺序执行，不能随机shuffle后让未来session成为context。最终主要评测单位保持`one reconstructed session → one result`，不扩展为attack-event aggregation主任务。

### 13.2 Knowledge RAG

**[HARD CONSTRAINT]** 主实验Knowledge RAG只允许包含通用protocol knowledge、attack knowledge、CVE/technical descriptions和公开网络安全知识。禁止加入针对Edge/IoT数据集的固定端口、设备、文件或其他shortcut知识；正式Agent test前冻结KB/index版本。

## 14. Failure Handling

**[CURRENT DEFAULT]** Supervisor返回非法action时，Runtime拒绝并返回`INVALID_ACTION`，允许有限一次重新决策；再次失败后安全降级或`ABSTAIN`。

Qwen结构化输出失败时，先由parser处理，再允许有限一次format retry/repair；再次失败记录`MODEL_OUTPUT_FAILURE`并安全终止。正式实验中外部Supervisor API失败必须记录`SUPERVISOR_FAILURE`，不得静默换模型。实际deployment可配置RulePolicy fallback，但论文实验必须显式报告。

## 15. Runtime、部署与执行效率

**[CURRENT DEFAULT]** 第一版优先采用清晰的Python deterministic state machine，暂不采用LangGraph，以便审计、复现、消融、动作统计和预算控制。`SupervisorBackend`至少在概念上支持`DeepSeekAPIBackend`与`LocalLLMBackend`；当前只设计接口，不实现或下载本地DeepSeek。

系统目标为session-level streaming analysis，不承诺严格毫秒级实时IDS SLA。逻辑上每个session拥有独立Agent state，第一版优先保证single-sample correctness，后续执行层可以进行dynamic batching。

**[DEFERRED]** 具体batch scheduler尚未冻结。

## 16. Agent实验与论文成功标准

### 16.1 Agent实验核心

**[CURRENT DEFAULT]** Agent实验在基础分类精度不过度下降的前提下，优化effectiveness与evidence/tool/token/latency cost的权衡。正式比较至少包含：

- Basic；
- Fixed Full Evidence；
- RulePolicy；
- High-Capability LLM Supervisor。

Strong Static按现有计划保留或并入Fixed/Rule消融，最终命名后续统一；LearnablePolicy为**[OPTIONAL]**。Fixed Full与Adaptive Agent应尽量使用相同information domain和预算，避免把更多信息误认为更智能的策略。

### 16.2 论文成功标准

**[CURRENT DEFAULT]** 论文目标分四层：

1. Closed-set：SFT Qwen不能明显落后强传统baseline；
2. Open-world：Unknown、Near/Far/Mixed、Backoff与Abstain体现闭集模型不具备的能力；
3. Supervisor Agent：相对Fixed Full/RulePolicy，在同信息域和预算下形成更好的effectiveness-cost trade-off；
4. Few-shot：实现`Unknown → human label/support → register → recognize new class`。

## 17. 明确DEFERRED事项

以下内容当前故意不冻结：

- DeepSeek最终model identifier；
- Supervisor Prompt正文；
- Qwen最终response JSON schema；
- Unknown算法与阈值；
- Experience Memory embedding/index/top-k/capacity；
- SFT正式样本量；
- Agent max rounds；
- Tool cost；
- Temporal最终窗口集合；
- Payload截断长度；
- RAG embedding/vector store/top-k；
- 是否增加额外expert LLM；
- LearnablePolicy；
- DPO；
- Agent Growth实验是否进入正式论文；
- dynamic batching具体实现。

Codex和开发者不得因为实现方便而自行将上述DEFERRED内容升级为最终Decision。
