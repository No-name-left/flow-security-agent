# 网络流量开放识别与自适应取证智能体研究计划（导师简版）

## 一、论文准备研究什么

本研究面向开放世界恶意网络流量识别。核心不是让传统分类器先筛选困难样本，再由大模型复核，而是通过领域后训练，使Qwen3.5-9B Traffic Expert直接读取会话级网络证据并独立执行第一次分类；当证据不足或疑似出现未知攻击时，再由deterministic Runtime约束的高能力LLM Supervisor决定是否扩展证据、重新分类、拒识或接入新类。

```text
网络流量样本
→ 双向会话的包级序列与会话摘要
→ text-only BF16 LoRA后训练Qwen输出细类、粗类、证据状态及开放集模型信号
→ 独立冻结的Unknown评分与校准
→ 高能力LLM Supervisor按需选择证据，deterministic Runtime验证并执行
→ 接受、重新分类、拒识Unknown或接入新类
```

**研究执行总链：**数据与Gate → Production Freeze → Qwen部署与基线 → BF16 LoRA SFT → 独立Unknown → Supervisor Agent → Few-shot → IoT-23外部验证 → 最终实验与论文。

**系统识别总链：**Raw Traffic → Packet/Session → CanonicalSessionRecord → Initial Evidence Card → Qwen Traffic Expert → Frozen Unknown Scoring → Evidence State → High-Capability LLM Supervisor → Runtime执行一个合法动作并重分类 → Fine / Coarse / Unknown / Abstain → Structured Result + Trace。

研究重点是三个相互衔接的问题：Qwen能否独立完成已知攻击分类、独立开放集评分层能否可靠拒识Unknown；动态取证能否在有限预算下改善证据不足样本；获得sample-level的1/5/10个标注样本后，系统能否接入新类且控制旧类遗忘。

## 二、数据与输入方案

每个数据集保留原生粗粒度和细粒度标签，通过统一`DatasetLabelSchema`接口接入，不强制统一为ATT&CK标签。

**正式采用Edge-IIoTset作为带限制使用的主实验数据集，并采用已通过最终可行性验收的IoT-23作为外部验证数据集。** 以Edge-IIoTset完成完整开放识别和Agent实验，以IoT-23的独立场景验证方法在另一原生标签体系和采集环境中的适用性；两个数据集通过统一会话接口接入，不强行统一标签或直接合并训练。IoT-23的通过结论保留最小场景匹配和未知恶意支持数限制，NF3等候选不再进入当前主线。

基础输入采用会话级混合表示：双向会话前8个包的方向、长度、包间时间、协议与TCP flags，加会话持续时间、双向包数/字节数、包长/IAT统计和缺失字段声明；序列最多保存16包，Agent可按需请求第9至16包。完整Payload不默认输入；past-only跨会话关系、应用层字段、有限脱敏Payload和RAG知识由Agent在需要且合法时获取。

训练、验证和测试分别构造会话与历史上下文，不跨split检索邻居。IP可用于后台关联，但固定真实身份、文件名、绝对时间、capture名称和攻击脚本编号不得成为标签捷径。Edge现采用capture-local chronological v2与边界隔离；完整Production保持真实分布，正式SFT另用仅含`K_known ∩ train`的class-balanced、diversity-aware PLAN_B候选。

主Near/Far/Mixed之外，可在时间允许时执行独立的OPTIONAL Low-Resource Unknown Stress Test，以pre-model稀缺性选取held-out攻击类，研究scarcity-driven Unknown拒识与few-shot Class Memory注册；该实验不改变现有K/U且当前未运行。

## 三、核心方法

Qwen3.5-9B是正式主分类模型，第一次就读取网络证据，直接承担known fine/coarse分类、证据充分度及supporting/missing evidence输出。正式训练默认使用文本模式BF16 LoRA SFT，冻结视觉模块并采用non-thinking直接响应；QLoRA只作为资源或兼容性降级。Unknown由独立、冻结、可复现的开放集评分与校准层处理，不直接把LLM自报概率当作正式分数。LightGBM、XGBoost、Random Forest和Logistic Regression只作为闭集/开放集、速度/成本、泄漏诊断及可选融合基线；树模型OOF概率不是Qwen训练的必要输入。

高能力LLM Supervisor读取Qwen第一次分类、Unknown状态和证据缺口，可选择接受细类、退回粗类、扩展包序列、扩展时间或局部图上下文、请求应用层证据、检索知识、重新分类、拒识、请求标注、注册新类或abstain；deterministic Runtime负责动作合法性、预算、轮数、信息隔离和Trace。Supervisor不替代Qwen产生fine分类，RulePolicy保留为强可复现baseline，LearnablePolicy仅为可选扩展。

Agent根据证据充分度与缺失证据类型按需选择包、时间/关系上下文、应用层证据或RAG：真实观测缺口由网络取证补充，知识缺口才调用RAG。错误先做组件级归因，再更新对应的证据、策略、Qwen、Unknown校准或检索组件，而不把所有错误统一回流SFT。

经过可靠反馈验证的Experience Memory只服务动作选择，正式test与`U_final`期间冻结只读；人工确认新类使用独立Class Memory。在线Supervisor未来允许替换为本地兼容高能力模型，具体型号和Memory检索实现尚未冻结。

每个正式数据集在训练前冻结`K_known`、`U_dev`和`U_final`。SFT只使用`K_known`主分类监督；`U_dev`只用于Unknown算法、校准和策略开发；`U_final`不得进入SFT/DPO、Prompt、known-only RAG、算法选择、阈值、Agent/策略训练和人工调参。实验先评价Unknown拒识，再对已拒识样本使用full-frozen知识做候选识别；获得sample-level 1/5/10-shot标注后再注册新类并评价旧类遗忘。

## 四、核心实验与论文结论

| 实验 | 核心比较 | 论文回答 |
| --- | --- | --- |
| 实验一：LLM独立分类能力 | 传统强基线、原始Qwen、后训练Qwen | Qwen独立分类的能力、成本和适用边界 |
| 实验二：开放集与自适应取证 | 传统开放集、单次Qwen、Fixed/强Static、RulePolicy、高能力LLM Supervisor和可选LearnablePolicy | Unknown、动态证据扩展和Supervisor决策是否改善任务成功与效果—成本权衡 |
| 实验三：1/5/10-shot新类接入 | 重训、原型、Qwen/RAG、Agent注册和可选LoRA | 新类能否低成本加入且不显著遗忘旧类 |
| 实验四：IoT-23独立场景验证 | 原生标签和独立scenario划分下的闭集、Unknown与Agent上下文增益 | 方法能否适用于另一采集环境和原生标签Schema |

同时设置传统模型零信息扩展新标签的诊断对照，区分Unknown拒识能力与具体新类识别能力。

若Qwen、Unknown与动态取证均有效，可形成完整方法贡献；若分类变化不大但拒识、证据获取、恢复或成本改善，贡献集中于可信和自适应系统能力；若Agent没有优势，则由强Static承担推荐流程，Agent作为适用边界分析。论文不预设LLM或Agent一定优于传统基线。

## 五、实施计划与当前进度

当前已完成通用LLM调用、结构化输出、缓存/resume/trace、RAG摄取、数据合同、研究架构回溯、双数据集最终可行性验收，以及服务器官方数据恢复和Production Data Freeze。正式`CanonicalSessionRecord`、两个Adapter、60秒session、identity dedup、标签provenance、K/U、support/query和training manifest均已冻结并通过postfix审计（带记录限制）；后续Edge paper-grade split revision、Paper Evaluation Readiness与PLAN_B SFT候选物化也已完成，`PRODUCTION_DATA_READY=true`。Edge多数攻击类只有一个主要capture，IoT-23部分外部验证支持仍偏少，因此两者的结论限制不变。Qwen训练和正式实验尚未开始。

deterministic Runtime foundation、Memory/预算/终止安全合同及provider-neutral Traffic Expert/Supervisor backend preparation也已完成synthetic/Fake Provider工程审计，并与Production共同进入唯一长期分支`main`；pre-model基线`3ab33e36c8508bcd31afac2e12c094ae1fe0a964`标记为`baseline-pre-model-20260811`。本轮split/SFT data protocol完成回归与Git冻结后的唯一推荐工程下一步，是轻量、白名单式Production→Runtime adapter及跨层泄漏测试；真实provider、Qwen配置/下载和text-only BF16 LoRA冒烟均须另行授权。研究计划不绑定具体平台、GPU型号或目录；分类头或标签Token、Unknown具体算法、SFT格式、Agent学习算法和条件性DPO仍待后续实验决定。
