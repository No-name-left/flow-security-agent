# Flow Security Agent 项目交接指南

> 适用对象：首次接手本项目的开发者或Agent。
>
> 最近核验：2026-08-06；本地阶段收尾与服务器迁移准备已进入归档/推送流程。
>
> 研究语义冲突时，以`docs/research_plan/research_plan_detailed.md`及其Decision Log为唯一权威来源；当前最新生效决定为DEC-0010，DEC-0006至DEC-0009继续有效。

## 1. 一分钟了解当前项目

项目研究会话级网络流量的开放世界新类别生命周期。正式主链路已经从“传统模型主分类+Qwen复核”纠偏为：

```text
网络流量样本
→ 会话级混合表示
→ 后训练Qwen3.5-9B独立执行第一次分类
→ fine / coarse / Unknown分数 / supporting与missing evidence
→ Adaptive Decision Agent按需扩展证据、重新分类、拒识或接入新类
```

Qwen是正式主分类模型，不是LightGBM/XGBoost的Reviewer。传统模型只作为闭集/开放集、速度/成本、泄漏诊断和可选融合基线；树模型OOF概率不是Qwen SFT的必需输入。

Agent在Qwen第一次分类后决定“下一步需要什么证据或是否停止”，确定性Python工具负责具体执行。Agent可以请求更多包、past-only时间上下文、局部通信图、合法应用层证据或RAG，再通过`RECLASSIFY`调用同一主Qwen；`CALL_LLM_EXPERT`已退出正式动作集。

## 2. 2026-08-06冻结状态

### 2.1 架构回溯已完成

本轮回溯报告位于：

`reports/architecture_audit/2026-08-llm-mainline-correction/`

审计确认旧架构主要存在于三份计划、交接文档和历史报告中。仓库尚未实现正式LightGBM/XGBoost主分类、OOF Tree-aware训练、Qwen Reviewer SFT、选择性Qwen路由或Agent主循环，因此没有已运行的旧pipeline需要回滚。

三份正式计划现已统一为LLM独立分类、会话级混合表示和Agent动态取证。DEC-0001至DEC-0009完整保留；DEC-0008冻结Edge-IIoTset主实验与IoT-23外部验证的双数据集方案，DEC-0009记录双数据集最终可行性验收`PASS_WITH_LIMITATIONS`，DEC-0010将正式数据下载、全量解析和训练资产生成迁移到远程服务器。DEC-0005的sample-level信息隔离原则仍可继承，但其中CICIoMT立即主线和传统模型Reviewer安排已被后续决定替代。

### 2.2 当前数据角色

| 对象 | 当前角色 | 接手含义 |
| --- | --- | --- |
| Edge-IIoTset | **主数据集，带冻结限制使用** | 承担完整闭集/coarse/fine、Unknown、Agent、1/5/10-shot及成本/恢复主实验；采用capture内时间块与隔离gap，不宣称跨攻击run泛化 |
| IoT-23 | **第二数据集，已通过最终可行性验收（带限制）** | 官方标签、PCAP对齐、统一Adapter和独立scenario划分已实测；承担闭集、Unknown和Agent上下文增益的压缩外部验证，正式Unknown支持数仍须补足或限制结论 |
| CICIoMT2024、X-IIoTID | 历史候选与备选说明 | 既有审计继续保留，但不再是当前立即执行主线 |
| DataSense、UWF、CICIoT2023等 | 历史候选或后续复现资源 | 不因已通过旧Gate自动成为新主数据 |
| CasinoLimit | 历史连接研究 | 不作为逐流量主监督数据 |
| NF3、NF-ToN等其他候选 | 退出当前主线 | 停止广泛数据集搜索；仅在IoT-23生产构建出现新阻断并新增Decision时重选第二数据集 |
| K_known/U_dev/U_final | 未冻结 | 正式数据、会话单位与split确定后、任何训练前预注册 |
| 正式模型与实验 | 尚未开始 | Qwen SFT/DPO、Unknown、传统基线和Agent均没有正式论文结果 |

### 2.3 Edge-IIoTset Phase 2 审查已完成

审查报告位于：

`reports/dataset_audit/2026-08-edge-iiotset-final-review/`

作者 Kaggle 版本 5 的完整 ZIP 已下载，大小 1,746,605,436 bytes，MD5 与官方对象一致；已解压 52 个成员、11,248,814,873 bytes，其中含 24 个 PCAP、26 个 CSV、PDF 和 README。原始数据位于被 `.gitignore` 排除的 `data/external/edge_iiotset/`。

最小探针确认可以从 PCAP 构造双向五元组会话、前 N 包序列和同 capture/split 的 past-only 30/60 秒上下文；14 个攻击 CSV 各自只有单一攻击标签，10 个正常 CSV 只有 `Normal`。这一事实同时形成严重结构性风险：攻击 capture/场景与标签高度耦合，每类通常只有一个独立攻击活动，随机 session 切分和 sample-level few-shot 均可能虚高。作者哈希一致归档中的 `Vulnerability scanner attack.pcap` 还有异常尾部记录，需第二解析器复核。

Phase 2的原始建议仍作为审计事实保留；DEC-0008在承认其限制的基础上，将Edge更新为“主数据集，带冻结限制使用”，并用IoT-23独立scenario补充外部证据。异常PCAP、单capture与捷径风险没有被撤销，仍须进入正式Adapter、split和论文限制。该决定不等于已授权Qwen训练。

### 2.4 双数据集最终可行性验收已完成

验收目录为`reports/data_feasibility_gate_20260806/`，入口报告为`final_gate_report.md`，可复现脚本为`run_final_gate.py`。本轮使用6个Edge代表性PCAP和7个IoT-23官方capture，生成3,753条Edge及3,222条IoT-23可交付冒烟记录；两个Adapter均输出统一`CanonicalSessionRecord`。IoT-23验收划分为Capture-8/Honeypot-4训练、Capture-20/21验证、Capture-34/Somfy-01测试、Capture-42整体`unknown_final`。

直接泄漏检查未发现模型视图中的IP、绝对时间、文件名、数据集或capture/scenario身份，past-only未来引用为0，跨split相同会话和完整证据重叠为0。两随机种子的no-service RF仅作Gate探针：Edge Macro-F1为0.9498±0.0072，IoT-23为0.7328±0.0016，均超过各自多数类基线；不得作为论文结果。冻结限制为Edge多数攻击类只有一个capture且Vulnerability Scanner PCAP异常，IoT-23 Somfy-01最低PCAP/日志匹配率81.54%，Capture-42 PCAP尾部截断但全部4,426条日志已匹配，且只有6条FileDownload恶意流。本轮只验证Qwen真实输入和JSON合同，没有调用或训练模型。

## 3. 当前正式输入与实验口径

### 3.1 会话级混合输入

两个Dataset Adapter统一输出`CanonicalSessionRecord`，基础模型输入是其安全投影：双向会话前8个包的方向、长度、IAT、协议/flags，以及会话持续时间、双向包数/字节数、包长/IAT统计和缺失字段声明。序列最多保存16包，Agent可请求第9至16包。

完整Payload不默认输入。更多包、past-only同源/同目标关联、局部通信图、HTTP/DNS/MQTT等应用层字段、有限脱敏Payload和RAG是Agent可按需请求的扩展证据。训练、验证、测试分别独立构造会话和历史上下文，禁止跨split检索邻居。

IP可用于后台关联，但固定真实身份不应直接进入模型；文件名、绝对时间、capture名称和攻击脚本编号不得形成标签捷径。

### 3.2 Known、Unknown和few-shot

- 每个数据集保留原生标签，不强制统一ATT&CK；
- 使用统一`DatasetLabelSchema`接口；
- `K_known`用于Qwen SFT及传统基线；
- `U_dev`仅用于Unknown、证据扩展和策略开发；
- `U_final`不得进入训练、Prompt、known-only RAG、阈值、策略或人工调参；
- 预注册Near/Far/Mixed Unknown并使用多个随机种子；
- 阶段A使用known-only知识做Unknown拒识；
- 阶段B仅对已拒识样本开放full-frozen RAG做Top-k候选；
- 阶段C使用sample-level 1/5/10-shot执行`REQUEST_LABEL`与`REGISTER_NEW_CLASS`，并评价旧类遗忘；
- sample-level结果不得声称为跨攻击run泛化。

传统开放集基线另设零信息新标签扩展诊断：先执行合理Unknown拒识，再将被拒识样本随机分配至候选新类，用于区分Unknown检测与具体新类识别。该弱诊断不替代强Unknown基线，也不能单独证明LLM优越。

### 3.3 Agent动作与公平比较

正式动作包括`ACCEPT_FINE`、`BACKOFF_COARSE`、`EXPAND_PACKETS`、`EXPAND_TEMPORAL_CONTEXT`、`EXPAND_GRAPH_CONTEXT`、`REQUEST_APPLICATION_EVIDENCE`、`RETRIEVE_KNOWLEDGE`、`RECLASSIFY`、`REJECT_UNKNOWN`、`RETURN_TOPK`、`REQUEST_LABEL`、`REGISTER_NEW_CLASS`和`ABSTAIN`。

强Static必须使用相同Qwen、工具、信息和最大预算，并包含合理的固定取证、retry、fallback和validator。Agent策略可能是规则、contextual bandit、小型policy network或其他方法，尚未冻结。

## 4. 当前下一步与停止规则

本阶段已完成架构审计、三份计划纠偏、Edge-IIoTset Phase 2审查、双数据集方案冻结及最终可行性验收。当前停止在生产数据生成之前，不进入模型训练。

冻结的执行顺序如下；双数据集Gate已经完成，本地阶段只做归档、推送和经批准的数据清理：

1. **已完成：**双数据集最终Gate、三份研究计划、DEC-0009与DEC-0010同步；
2. 整理并push代码、测试、报告、manifest、校验和、下载工具与`docs/SERVER_MIGRATION.md`；
3. 选择并租赁服务器，配置基础环境和独立数据/资产/模型目录；
4. 在服务器从官方来源下载Edge-IIoTset与IoT-23，校验哈希并复跑Gate；
5. 将验收版`CanonicalSessionRecord`、EdgeAdapter和IoT23Adapter固化为生产数据流水线；
6. 冻结两个数据集各自的全量split、K/U、support/query、异常文件处置和训练manifest，完成回归、近重复敏感性及IoT-23 Unknown支持数检查；
7. 配置GPU模型环境，加载Qwen3.5-9B并完成小规模QLoRA/SFT冒烟；
8. 执行Edge-IIoTset完整主实验和IoT-23压缩外部验证。

IoT-23已通过官方数据、标签和scenario隔离Gate；除非生产构建出现新的阻断性证据并新增Decision，否则不得重选第二数据集，也不得自动恢复“CICIoMT首选、X-IIoTID立即切换”或重新开启主数据集搜索。

## 5. 现有工程资产与尚未实现

### 已有且可复用

- `src/flowsec/llm/`：OpenAI-compatible调用、超时、重试、并发、缓存、resume、失败隔离、usage/latency trace；
- `src/flowsec/llm/structured_output.py`：JSON提取与Pydantic验证，可承载主Qwen和Agent工具Schema；
- `src/flowsec/rag/`：Markdown/YAML front matter摄取、chunk和来源元数据；
- `src/flowsec/data/schema.py`：字段角色和直接泄漏检查，可扩展为会话输入合同；
- `src/flowsec/data/event_matching.py`、`grouping.py`和`audit.py`：重复、事件匹配、候选分组和数据审计基础；
- `tools/dataset_audit/`：历史数据审计和LightGBM CPU探针，可作基线/泄漏诊断。
- `tools/dataset_download/`：Edge官方归档和IoT-23七场景的服务器下载、恢复与哈希校验入口；
- `reports/data_feasibility_gate_20260806/run_final_gate.py`：验收版EdgeAdapter、IoT23Adapter、统一会话记录、泄漏/捷径检查、RF和Qwen输入合同的可复现参考实现；应重构进生产模块，不应原样充当正式流水线。
- `docs/SERVER_MIGRATION.md`：服务器目录、环境变量、官方来源、校验、Gate复跑、Git禁入内容与后续顺序。

### 尚未实现，不得描述成已有结果

- 生产级`CanonicalSessionRecord`、EdgeAdapter、IoT23Adapter、会话重建、包级序列和跨会话上下文；当前已有双数据集验收原型，但不是正式全量数据流水线；
- Session Evidence Card与应用层证据工具；
- 正式DatasetLabelSchema、K/U、support/query和split manifest；
- 传统闭集/开放集正式基线；
- Qwen3.5-9B主分类SFT、Unknown算法、校准与DPO；
- RulePolicy、LearnablePolicy、强Static与Agent主实验；
- 四组论文实验及论文结论。

## 6. 禁止与高风险操作

- 不得把Edge的带限制主数据角色写成跨攻击run泛化已经成立，也不得掩盖Phase 2的异常PCAP、单capture和捷径证据；
- 不把IoT-23带限制的最小验收写成正式论文实验完成，也不忽略其匹配率和未知支持数限制；无新Decision不重选第二数据集或重新搜索主数据集；
- 不恢复传统模型主分类、Tree-aware Reviewer、selective Qwen或`CALL_LLM_EXPERT`主动作；
- 不把树模型OOF概率写成Qwen训练必需输入；
- 不擅自冻结分类头/标签Token、Unknown算法、继续预训练、Tokenizer、SFT格式、DPO、精确N/窗口、Agent算法、服务器规格或泛化声明；
- 不让`U_final`进入训练、Prompt、RAG开发、阈值、策略或人工调参；
- 不把固定模块串联包装成Agent，不故意削弱Static基线；
- 不把历史审计探针写成论文结果；
- 不修改或丢弃用户工作树；特别保护`tests/test_structured_output.py`、README、AGENTS和`docs/research_plan/.obsidian/`；
- Git暂存、提交和推送必须有当前任务的明确授权；禁止`git add .`、`git add -A`、force push、rebase、reset或clean。

## 7. 必读顺序与事实源

1. `docs/research_plan/research_plan_detailed.md`，重点阅读DEC-0006至DEC-0010；
2. `reports/data_feasibility_gate_20260806/final_gate_report.md`、`gate_results.json`和`split_manifest.json`；
3. `docs/SERVER_MIGRATION.md`；
4. `reports/dataset_audit/2026-08-edge-iiotset-final-review/README.md` 与 `provisional_verdict.md`；
5. `reports/architecture_audit/2026-08-llm-mainline-correction/README.md`；
6. 同目录`affected_files.md`、`old_architecture_inventory.md`、`reusable_assets.md`和`unresolved_questions.md`；
7. `docs/research_plan/research_plan_and_timeline.md`；
8. `docs/research_plan/research_plan_brief.md`；
9. `docs/infrastructure_contract.md`；
10. 需要理解历史数据决策时，再读既有`reports/dataset_audit/`。

事实源优先级：canonical detailed中最新决定 → Decision Log → 本次架构回溯 → timeline/brief → 交接文档 → README与历史报告。历史报告不得覆盖DEC-0006/0007。

## 8. 工作树与验证提示

本阶段开始前工作树已经包含用户/前序改动，包括README、三份计划、受保护测试文件以及未跟踪的AGENTS、handoff、reports、tools和`.obsidian`。不要为追求干净执行reset、checkout、rebase或clean。

最终Gate运行了官方最小数据下载、PCAP解析、会话/标签对齐、哈希、泄漏与捷径检查、两随机种子RF及Qwen输入合同冒烟；没有调用或训练Qwen，也没有运行正式论文实验。DEC-0010只改变执行位置：服务器负责正式数据与训练资产，本地保留可复现元数据。任何后续数据角色、会话单位、输入证据、K/U、训练阶段、Unknown或Agent口径改变，必须同步更新canonical detailed的Decision Log与本交接文档。

## 9. 接手完成检查

接手者应能回答：Qwen为什么是首次主分类器；传统模型还承担什么；Edge与IoT-23分别负责哪些实验；为何两个数据集不合并训练；`CanonicalSessionRecord`如何统一接口并隔离后台字段；哪些证据只能由Agent按需获取；K/U与知识域如何隔离；单一攻击capture、捷径和异常PCAP怎样限制Edge结论；IoT-23何时才能进入外部实验；哪些训练和算法仍未决定。任一问题不清楚时，不应启动训练。
