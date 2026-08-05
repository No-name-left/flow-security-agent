# 网络流量开放识别与自适应取证智能体：执行计划与时间表

> 本文件由`research_plan_detailed.md`派生，只定义任务、依赖、Gate和时间；研究语义冲突时以详细版为准。更新时间：2026-08-06。

## 1. 当前主线与冻结状态

论文研究会话级网络流量的开放世界新类别生命周期。后训练Qwen3.5-9B直接读取网络证据并独立执行第一次fine/coarse分类、Unknown判断与证据充分度分析；Adaptive Decision Agent根据Qwen输出、证据缺口、工具状态和预算，决定接受、退回粗类、扩展包/时间/图上下文、请求应用层证据、检索知识、重新分类、拒识或请求人工。

正式主链路为：

```text
网络流量样本
→ 会话级混合表示
→ 后训练Qwen3.5-9B第一次分类
→ fine / coarse / Unknown分数 / supporting与missing evidence
→ Agent按需取证、重新分类、拒识或接入新类
```

不同数据集保留原生标签，通过统一`DatasetLabelSchema`、`CanonicalSessionRecord`和Session Evidence Card运行同一方法，不强制统一ATT&CK。双数据集角色现已冻结：Edge-IIoTset承担完整方法开发与主实验，IoT-23承担另一原生标签体系和独立scenario/capture下的外部验证。

| 项目 | 状态 | 执行含义 |
| --- | --- | --- |
| Edge-IIoTset | **主数据集，带冻结限制使用** | 完整运行闭集/coarse/fine、Near/Far/Mixed Unknown、传统强基线、Agent、1/5/10-shot和成本/恢复实验；不宣称跨攻击run泛化 |
| IoT-23 | **第二数据集，最终可行性验收通过（带限制）** | 官方日志/PCAP、统一Adapter和独立scenario划分均已实测；在原生标签下运行scenario-held-out闭集、一套Unknown和一套Agent上下文增益，正式Unknown支持数仍须补足或限制结论 |
| CICIoMT2024、X-IIoTID等 | 历史候选/备选 | 既有审计保留，不再是当前立即执行主线 |
| 其他NF3/NF-ToN/CICIoT2023等 | 退出当前主线 | 停止广泛候选搜索；仅在IoT-23生产构建出现新阻断并新增Decision时重选第二数据集 |
| 会话表示 | 接口和初始包预算已定 | 两个Adapter输出`CanonicalSessionRecord`；序列最多保存16包，首次分类使用前8包，Agent可请求第9至16包 |
| K_known/U_dev/U_final | 未冻结 | 正式数据与split确定后、任何训练前预注册 |
| Qwen3.5-9B SFT/DPO | 尚未开始 | Qwen是主分类器；SFT等待数据和表示冻结，DPO保持条件性 |
| RulePolicy/LearnablePolicy | 研究框架已定，算法未定 | 可比较规则、contextual bandit或小型policy network，不提前锁定 |

## 2. 任务依赖与数据Gate

```text
DEC-0009与双数据集最终Gate同步
→ DEC-0010与本地可复现资产push归档
→ 选择服务器并配置独立存储与基础环境
→ 从官方来源下载、校验并复跑数据Gate
→ 将CanonicalSessionRecord与两个验收Adapter固化为生产流水线
→ 冻结两个数据集各自的全量split、K/U、support/query和训练manifest
→ 配置GPU模型环境
→ Qwen3.5-9B加载与小规模QLoRA/SFT冒烟
→ Edge-IIoTset完整主实验
→ IoT-23压缩外部验证
```

启动训练前必须确认：Edge生产级会话与标签可用；两个Adapter输出统一Schema；包级字段和会话摘要可复现；split、K/U、support/query和训练manifest冻结；精确重复与直接泄漏受控；会话及past-only上下文只在各split内部独立构造；known-only和full-frozen知识域隔离。IoT-23官方数据、标签和scenario隔离已通过最小验收，但正式Unknown支持数和全量manifest仍须冻结。

传统模型不进入正式主链路。LightGBM、XGBoost、Random Forest和Logistic Regression只作为闭集/开放集、速度/成本、泄漏诊断及可选融合基线；树模型OOF概率不是Qwen训练的必要输入。

## 3. 冻结实验协议

### 3.1 输入、Known、Unknown与few-shot

- 基础输入为双向会话前8个包的方向、长度、IAT、协议/flags，加会话持续时间、双向包数/字节数、包长/IAT统计和缺失声明；包序列最多保存16包，Agent可请求第9至16包。
- 应用层字段、有限脱敏Payload、past-only时间上下文和局部图摘要由Agent按需获取；缺失证据通过`capabilities`和`missing_fields`声明。
- `K_known`进入Qwen SFT和传统基线；`U_dev`只用于Unknown与策略开发；`U_final`对训练、Prompt、known-only RAG、阈值、策略和人工调参完全隔离。
- Unknown至少覆盖Near、Far和Mixed多套预注册组合并使用多个随机种子。
- 阶段A使用known-only知识做Unknown拒识；阶段B只对已拒识样本开放full-frozen RAG做Top-k候选；阶段C获得sample-level 1/5/10-shot后注册新类，并在无相同记录或精确重复的query上评价。
- 只使用锚点之前的信息；训练、验证、测试分别构造会话和上下文，不跨split检索邻居。

### 3.2 Qwen与Agent

Qwen3.5-9B直接承担第一次known fine/coarse分类、Unknown/open-set判断、证据充分度和supporting/missing evidence输出。分类头或标签Token、Unknown算法、校准方式、SFT样本格式、Tokenizer扩展与领域继续预训练均未冻结。

Agent在Qwen第一次分类后选择：`ACCEPT_FINE`、`BACKOFF_COARSE`、`EXPAND_PACKETS`、`EXPAND_TEMPORAL_CONTEXT`、`EXPAND_GRAPH_CONTEXT`、`REQUEST_APPLICATION_EVIDENCE`、`RETRIEVE_KNOWLEDGE`、`RECLASSIFY`、`REJECT_UNKNOWN`、`RETURN_TOPK`、`REQUEST_LABEL`、`REGISTER_NEW_CLASS`或`ABSTAIN`。`CALL_LLM_EXPERT`不再是正式动作。

强Static使用相同Qwen、工具、信息域和预算，并包含合理的固定取证、retry、fallback与validator。Agent具体采用规则、contextual bandit、小型policy network或其他方法，待数据与预实验决定。

### 3.3 四组实验

| 实验 | 主要比较 | 回答的问题 |
| --- | --- | --- |
| 一：LLM独立分类能力 | LR、RF、LightGBM/XGBoost、原始Qwen、后训练Qwen | Qwen独立分类的能力、成本及相对传统强基线的边界 |
| 二：开放集与自适应取证 | 传统开放集、单次Qwen、Qwen+强Static、Qwen+RulePolicy、Qwen+LearnablePolicy、可选全证据上界 | Unknown与动态取证是否改善任务成功和utility-cost |
| 三：1/5/10-shot新类接入 | 重训、最近邻/原型、Qwen ICL、RAG原型、Agent注册和可选LoRA | 新类能否低成本接入且不显著遗忘旧类 |
| 四：IoT-23独立场景外部验证 | IoT-23独立适配与scenario split下的闭集、一套Unknown和一套Agent上下文增益；允许时增加1/5-shot | 同一接口、Qwen协议、Unknown生命周期和Agent决策能否适用于另一采集环境和原生标签Schema |

主要指标包括Known Macro-F1、Unknown AUROC/AUPR/FPR95/OSCR/H-score、层次退回、新类F1与遗忘、任务成功、证据/工具选择、恢复、预算遵从、输出合法、重分类/RAG调用率、延迟和成本。

在传统开放集基线完成后，实现“Unknown拒识+被拒识样本随机分配至候选新类”的零信息标签扩展诊断，并输出Known-to-Novel FPR、新类Macro-F1、混淆矩阵及多随机种子结果；该诊断不替代合理的传统Unknown拒识基线。

## 4. 当前可执行工作与停止项

### 4.1 本阶段已执行

1. 回溯旧的“传统模型主分类+Qwen Reviewer”架构影响；
2. 区分已实施基础设施、历史基线、计划文字和未执行设想；
3. 纠偏三份研究计划并新增DEC-0006、DEC-0007；
4. 完成Edge-IIoTset官方数据获取和Phase 2客观可行性审查；
5. 新增DEC-0008，冻结Edge主实验与IoT-23外部验证的双数据集职责；
6. 使用最小官方数据完成双数据集最终Gate，两个Adapter、标签对齐、无直接身份泄漏、no-service非随机可学习性和Qwen输入合同均通过，新增DEC-0009；
7. 冻结正式数据处理向远程服务器迁移的执行位置与恢复方案，新增DEC-0010；
8. 记录仍可复用的传统模型、LLM、RAG、结构化输出和数据审计资产。

### 4.2 本阶段停止

- 不把验收Adapter和RF探针写成生产流水线或论文结果；
- 不在全量split、K/U、support/query及训练manifest冻结前启动Qwen训练；
- 不冻结分类头/标签Token、Unknown算法、SFT格式、精确时间窗口或Agent学习算法；
- 不启动Qwen SFT、DPO、继续预训练、正式传统模型训练或Agent实验；
- 本地收尾阶段不租赁或配置GPU服务器；完成仓库push后，下一动作转为选择服务器并配置数据与基础环境；
- 不恢复传统分类器筛选Qwen样本、Tree-aware Reviewer或固定`Classifier→RAG/LLM`主链路。

## 5. T0后四周时间表

T0定义为：生产级`CanonicalSessionRecord`和两个Adapter通过回归，Edge与IoT-23各自原生标签Schema、split、K/U、support/query、包/摘要字段、信息域和训练manifest获得冻结。IoT-23已通过最小可行性验收，但外部正式实验仍须等待上述生产资产冻结。

| 阶段 | 主要工作 | 产出与退出条件 |
| --- | --- | --- |
| 双数据集最终Gate | 以最小官方数据实测标签、PCAP对齐、两个Adapter、非随机RF、捷径、泄漏和Qwen输入合同，并同步DEC-0009 | 整体`PASS_WITH_LIMITATIONS`；证据归档于`reports/data_feasibility_gate_20260806/` |
| 本地收尾与服务器迁移 | push代码、报告、manifest、哈希与下载说明；选择服务器并配置独立数据/资产/模型目录；从官方来源恢复和校验数据 | DEC-0010生效，服务器复跑Gate通过；本地不再承担正式全量处理 |
| 生产Adapter与manifest冻结 | 在服务器固化`CanonicalSessionRecord`和两个Adapter；冻结全量split、K/U、support/query、异常文件处置和训练manifest | 输入、泄漏和信息域合同可复现，IoT-23正式Unknown支持数满足预注册要求或明确小样本边界 |
| T0后第1周 | 配置GPU模型环境；加载Qwen3.5-9B并完成小规模SFT冒烟；完成传统和原始Qwen基线 | 模型与数据链路可运行，无Final泄漏 |
| T0后第2周 | 完成Edge Qwen主训练、闭集/coarse/fine和强Static | Qwen独立输出fine/coarse、Unknown和证据状态 |
| T0后第3周 | 完成Edge Near/Far/Mixed Unknown、动态取证、RulePolicy和候选LearnablePolicy；DPO仅作条件性判断 | Edge实验一、实验二和utility-cost结果冻结 |
| T0后第4周 | 完成Edge sample-level 1/5/10-shot、错误/成本分析及IoT-23压缩外部验证；同步论文初稿 | 实验三、实验四、限制和复现清单完成 |

## 6. 里程碑与停止条件

| Gate | 通过条件 | 不通过时 |
| --- | --- | --- |
| G0 Edge数据与会话 | Edge合法可用，标签与会话粒度可解释，包序列/摘要可构造，限制已冻结 | 使用capture内时间块与隔离gap，限制结论；异常文件显式处理，不以随机切分替代 |
| G0b IoT-23验收 | **已带限制通过：**官方数据可解析、标签可用、可构造独立scenario训练/验证/测试 | 固化生产Adapter；处理Somfy未匹配记录和正式Unknown支持数，不重选数据集 |
| G1 输入与基线 | 会话表示可复现，传统强基线和原始Qwen基线可公平运行 | 收缩到可验证表示，限制结论，不虚构跨会话能力 |
| G2 Qwen SFT | 后训练Qwen能稳定输出分类、Unknown和证据状态，且无Final信息泄漏 | 停止DPO/规模扩展，保留原始Qwen与失败边界 |
| G3 Agent | 相同Qwen、工具和预算下，Rule/Learnable至少改善任务成功、恢复或utility-cost | 强Static成为推荐方案，Agent降为边界分析 |
| G4 Few-shot | support/query无相同记录或精确重复，新类提升且旧类遗忘可控 | 保留Unknown与候选识别；group-level只在有可靠活动标识时追加 |

## 7. 风险与压缩顺序

Edge单capture、固定端点和时间捷径通过capture内时间块、隔离gap、后台字段隔离和敏感性消融控制，主结论限定为同采集环境。IoT-23已通过官方数据、标签和scenario隔离Gate；正式阶段重点处理Somfy-01最低81.54%匹配率及Capture-42未知恶意样本仅6条的限制，不恢复广泛数据集搜索。会话或包证据不足时收缩输入并限制结论；Qwen无优势时报告相对传统基线的能力与成本边界；Agent无优势时采用强Static。

时间不足时依次取消继续预训练/Tokenizer扩展、27B、DPO、复杂LearnablePolicy和IoT-23 few-shot扩展；保留可复现数据、Edge实验一、开放集最小实验二、sample-level实验三、IoT-23三项压缩验证和论文初稿。

## 8. 下一执行顺序

1. 整理并push当前仓库，保留代码、报告、manifest、哈希和下载说明；
2. 选择并租赁服务器，配置基础环境和独立数据/资产/模型目录；
3. 在服务器从官方来源下载Edge-IIoTset与IoT-23并复跑数据Gate；
4. 将验收版`CanonicalSessionRecord`、EdgeAdapter和IoT23Adapter固化为生产数据流水线；
5. 冻结全量split、K/U、support/query、异常文件处置和训练manifest，并完成生产回归与Unknown支持数检查；
6. 配置GPU模型环境，加载Qwen3.5-9B并完成小规模SFT冒烟；
7. 执行Edge-IIoTset完整主实验和IoT-23压缩外部验证。
