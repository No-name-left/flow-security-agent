# 旧竞赛项目资产复用审计

## 1. 审计范围与结论

本报告只审计 `pcap_llm_demo` 中与新 Flow 论文项目可能相关的工程资产。重点阅读了项目主线说明、运行配置，以及推理、结构化输出、RAG、session/evidence card、实验运行、结果合并和部署相关脚本；未把归档报告、历史输出和比赛数据逐项展开。

**建议采用 B：新建干净仓库，选择性迁移旧代码。**

理由是：旧项目在 OpenAI-compatible 调用、逐记录恢复、失败记录、结构化输出和 RAG 文档处理方面已有可用积累，但完整主线仍以 `PCAP → Zeek/TShark → 竞赛标签 → PCAP级聚合 → 官方提交` 为中心。并发、resume 和分片等较成熟能力又集中在一个 1583 行的竞赛总控脚本中。继续原仓改造会长期携带无关依赖和隐含语义；完全从零重写则会浪费已经验证过的推理与恢复逻辑。

代码检索没有发现 LightGBM、group-aware OOF、60 秒 causal context、QLoRA、DPO、DeepSeek Orchestrator 或 Parquet 实验管线。因此，旧项目不能提供新论文的核心学习与 Agent 实现，只能提供外围工程部件。

> 成本判断中的“迁移”是指抽取通用函数并为新接口补测试，不等于复制整个旧脚本。

## 2. 候选资产与成本判断

| 文件/目录 | 当前功能 | 新项目对应用途 | PCAP/竞赛耦合 | 代码质量 | 预计迁移成本 | 从零重写成本 | 建议 |
|---|---|---|---|---|---|---|---|
| `scripts/run_phase1_pipeline.py` 中的 `run_api`、缓存和 usage 相关函数 | OpenAI-compatible 调用；线程池并发；线程本地 client；超时、固定间隔重试；逐记录结果缓存；Prompt SHA-256 校验；延迟与 Token 记录；失败记录 | Reviewer/Teacher 批量推理执行器和 Trace Logger | 整文件高，所列函数中 | 需大改 | 中 | 中至高 | 重构迁移 |
| `scripts/run_qwen_openai_compatible.py` | 串行批推理；超时与重试；错误分类；failed-record；resume；usage；按记录过滤重跑 | 通用命令行推理入口和失败重跑工具 | 中，固定 TA 标签及旧 Prompt 标记 | 需大改 | 中 | 中 | 仅抽取错误分类、结果记录和重跑思路；不整文件迁移 |
| 上述两个 runner 中的 `parse_json_objects`、`extract_json_object`、`validate_*` | 从 Markdown fence、thinking 文本或混杂输出中抽取 JSON；校验 record ID、标签、置信度和必填理由 | Reviewer Validator、Teacher Validator 的解析层 | 中，校验字段和标签写死 | 需小改 | 低 | 低至中 | 重构迁移 |
| `scripts/qwen35_rag_utils.py` 中的 runtime profile、front matter、tokenize、JSON/fence 工具 | 环境变量覆盖、密钥不落盘、运行配置读取、Markdown 元数据解析、粗略 Token 预算、文本清理 | 模型 endpoint 配置、知识文档读取、Prompt 预算工具 | 低至中，存在旧根目录、标签和泄漏词表 | 需小改 | 低 | 低 | 轻度修改后复用所需函数 |
| `configs/runtime_profiles.yaml` 的 `nvidia_ubuntu_online_api` 设计 | 将 endpoint、model、上下文预算和 thinking 开关外置；密钥来自环境变量 | NVIDIA/vLLM 客户端运行配置模板 | 低；默认 profile 和另一 profile 为 Ascend | 需小改 | 很低 | 很低 | 仅迁移配置结构，删除 Ascend 默认值 |
| `scripts/build_rag_chunks.py` | 读取带 YAML front matter 的 Markdown，按标题/段落和长度切分，保留 doc/source/category/keywords 元数据并导出 JSONL | 新安全知识库的可追踪 chunk 构建器 | 低，元数据名仍含旧 attack stage/type | 需小改 | 很低 | 低 | 直接迁移后改元数据字段 |
| `scripts/build_keyword_index.py`、`scripts/retrieve_rag.py`、`scripts/test_rag_retrieval.py` | 关键词打分、metadata bonus、定向 boundary card、去重、top-k 和检索回归样例 | Reviewer RAG 的可解释检索基线 | 中至高，硬编码旧攻击类型、TA边界和 payload signature | 需大改 | 中 | 中 | 参考设计后重新实现 |
| `scripts/build_rag_query.py` | 从 session/PCAP 规则特征构造查询，并按 TA 混淆组强制定向知识卡 | 根据 Flow、树概率和 margin 构造新 RAG 查询 | 高 | 需大改 | 高 | 中 | 参考设计后重新实现 |
| `rag/knowledge/protocols/`、`false_positive_rules/`、`observable_evidence/` | 协议解释、误报边界、不可观察证据约束 | 新知识库的主题清单和反例设计参考 | 中，文内普遍含旧 stage/TA 映射 | 需大改 | 中 | 中 | 仅参考设计；按新标签和权威来源重建 |
| `rag/knowledge/competition_labels/`、`competition_decision_boundaries/`、`tool_fields/` | 比赛 TA 编码、竞赛边界、Zeek/TShark 字段说明 | 无直接用途 | 高 | 需大改 | 高 | 很低 | 放弃 |
| `scripts/build_qwen35_session_prompts.py` 中的压缩、预算和 Prompt manifest 思路 | 核心证据优先、RAG 后截断、Prompt 长度保护、Prompt 元数据记录 | 新 EvidenceCard Prompt Builder 与 Prompt Manifest | 高，字段、指令和标签均为 PCAP/TA | 需大改 | 中至高 | 中 | 仅参考设计 |
| `scripts/build_session_cards.py`、`session_card_indicators.py`、`build_classification_records.py` | 从 Zeek/TShark 生成 session card，构造 scan/auth/C2 group，记录缺失/加密/可观察证据 | 新 `EvidenceCard` 的设计参考 | 高 | 需大改 | 高 | 中 | 参考思想后重新实现 |
| `scripts/run_phase1_pipeline.py` 的 `run_state.json`、`config_effective.json`、Prompt hash、routing/failure 输出 | 保存有效配置、阶段状态、逐记录 Trace、路由和失败产物 | Experiment Manifest、Trace Logger、Artifact Manager | 中至高，路径和阶段写死 | 需大改 | 中 | 中 | 抽取契约与字段后重新实现 |
| `scripts/merge_phase1_shards.py` | 合并 predictions，按 record ID 去重并重建比赛提交 | 新实验 shard 合并 | 高，直接依赖官方导出 | 需大改 | 中 | 很低 | 重写 |
| `scripts/run_small_api_eval.py`、`estimate_api_eval_cost.py` | 汇总调用延迟、Token 和 API 费用，生成小规模评估报告 | Reviewer/Agent 成本台账 | 中，数据选择、指标和 Prompt 形态绑定旧任务 | 需大改 | 中 | 低至中 | 仅复用计算公式和字段定义 |
| `README_DEPLOY.md`、`docs/deployment/*` | 描述 OpenAI-compatible endpoint 与环境变量；没有实际 vLLM 启动脚本 | 新 NVIDIA/vLLM 部署清单的参考 | 中；含 Ascend、Zeek 和比赛环境 | 需大改 | 中 | 低 | 仅参考；Serving 启动重新编写 |

### 实现质量中的重要限制

- `run_phase1_pipeline.py` 的 per-record Prompt hash 校验比通用 runner 的仅按 record ID 恢复更可靠，迁移时应以前者为准，并进一步加入模型、Schema、数据版本和生成参数指纹。
- 并发只存在于竞赛总控脚本；独立的 `run_qwen_openai_compatible.py` 是串行 runner。重试为固定等待，没有指数退避、抖动、按错误类型决定是否重试或原子 checkpoint。
- JSON 处理是实用的启发式抽取与手写字段校验，不是通用 JSON Schema/Pydantic 验证；也没有证据字段真实性、Agent tool result 或跨字段逻辑校验。
- `build_keyword_index.py` 会生成倒排索引，但当前 `retrieve_rag.py` 实际仍逐 chunk 打分，`--index` 参数没有参与检索；`vector` 和 `hybrid` 选项也只是占位并会报错。因此不应把现有 RAG 当作可扩展检索框架直接搬运。
- 知识卡中的 `source_type: official_or_distilled` 多数没有可直接用于论文复现的精确出处。通用协议与“不可编造不可观察证据”的原则有价值，但正式知识库需重新标注来源、适用 Schema 和版本。
- 存在较大规模 `unittest` 和脚本式回归测试，覆盖 API payload、resume、稳定分片、路由失败隔离、Prompt budget 和 RAG 命中等行为；但测试与旧 fixture/标签绑定，需迁移测试意图而非整个测试文件。本轮抽查中纯分片测试通过，其余选定测试因审计环境临时目录权限未能执行，未将其计作通过。

## 3. 四类资产清单

### 3.1 强烈建议直接或轻度修改后复用

1. `build_rag_chunks.py` 的 front matter、chunk 和 source metadata 管线。
2. `qwen35_rag_utils.py` 中 runtime profile、Markdown 元数据、fence 清理和基础 JSON 工具。
3. `run_phase1_pipeline.py` 中 Prompt hash 校验、逐记录缓存、线程本地 OpenAI client、usage/latency/failed-record 记录；以独立包方式抽取。
4. 两套 runner 中的 JSON 抽取和 record ID/置信度校验骨架；标签与输出 Schema 全部替换。
5. `runtime_profiles.yaml` 的 NVIDIA/OpenAI-compatible 配置思想和环境变量密钥策略。
6. 与上述能力对应的单元测试意图：resume 不重复调用、分片不重叠、失败记录不吞掉成功结果、usage 被保留。

### 3.2 建议参考设计后重新实现

1. 新 `EvidenceCard`：继承“显式缺失字段、可观察证据边界、输入预算”思想，不继承旧 session 字段。
2. 新 RAG query/retriever：继承 boundary card、去重、top-k、source trace 思想，删除 TA、Zeek 和 payload 触发器，并真正接入所选索引。
3. 新 Prompt Builder：继承核心证据优先和 manifest 思想，输入改为 Flow、60 秒因果上下文、OOF 树概率、margin/entropy 和可选 RAG。
4. Experiment Manifest、Trace Logger、Artifact Manager：参考旧 `run_state` 和输出目录，但以 run ID、数据/代码/模型指纹和原子写入重新设计。
5. 新成本与评测模块：保留 Token、延迟、调用次数和费用字段，指标改为论文任务所需的分类、Reviewer 净纠错与 Agent task success。

### 3.3 可以后续再考虑

1. `run_qwen_openai_compatible_isolated.py` 的进程级硬超时。它能处理 SDK 调用卡死，但每请求启进程的开销较大，先观察 vLLM 稳定性。
2. `session_card_indicators.py` 的敏感文本清理与 URI 脱敏。Flow-only 主线不处理 payload，当前不是关键路径。
3. 旧 critic/conflict diagnostics。新 Security Reviewer 与 Validator 稳定后，再决定是否需要二次 critic。
4. 关键词 RAG 作为无需额外模型的可解释基线；不应替代后续经过验证的正式检索实现。

### 3.4 明确不迁移

- PCAP 发现、解析及 `parse_public_pcaps.py` 等 PCAP 主线；
- Zeek、TShark fallback、Suricata 历史流程及其 tool-field 知识；
- `build_session_cards.py` 和 `build_classification_records.py` 的旧数据入口与分组逻辑；
- `build_pcap_level_records.py`、PCAP 级聚合和比赛高置信规则直出；
- `competition_label_schema.yaml`、TAxx 标签、technique-to-stage 映射与比赛边界卡；
- `export_official_submission.py`、官方 CSV/XLSX 格式和答案表评估；
- Ascend、CANN、vLLM-Ascend、910B 和 openEuler 专用部署内容；
- 强绑定旧目录的 shell runner、历史输出、SFT 候选数据、公开评估拼接结果及归档脚本。

## 4. 特别问题回答

### Q1：应选择 A、B 还是 C？

选择 **B：新建干净仓库，选择性迁移旧代码**。外围推理可靠性资产足以排除“完全从零”，而 PCAP/竞赛耦合及新核心模块的整体缺失又排除了“原仓继续改造”。

### Q2：第一批最值得迁移的具体文件/模块

按优先级排序：

1. `scripts/run_phase1_pipeline.py`：抽取 `run_api`、Prompt hash 缓存、usage/latency 和失败记录，不迁移主流程。
2. `scripts/test_phase1_vm_pipeline.py`：迁移 API、resume、shard、失败隔离相关测试用例的测试意图。
3. `scripts/run_qwen_openai_compatible.py`：抽取 `parse_json_objects`、错误分类和 failed-record 重跑接口。
4. `scripts/qwen35_rag_utils.py`：抽取 runtime profile、front matter、fence/JSON 和预算工具。
5. `scripts/build_rag_chunks.py`：作为新知识库 chunk builder 的起点。
6. `configs/runtime_profiles.yaml`：仅迁移 NVIDIA/OpenAI-compatible 配置结构。
7. `scripts/build_qwen35_session_prompts.py`：只迁移 Prompt budget/manifest 的设计与测试，不复制旧 Prompt。
8. `scripts/run_small_api_eval.py` 与 `scripts/estimate_api_eval_cost.py`：抽取 usage、延迟和费用字段及计算公式。

### Q3：哪些模块重写比迁移便宜？

- session/evidence card 构造、行为 group 和 60 秒上下文；
- `build_rag_query.py` 的特征触发与 TA 混淆规则；
- `retrieve_rag.py` 的正式检索核心；
- `run_phase1_pipeline.py` 的端到端总控、路由和输出目录管理；
- shard 合并、传统分类评测、比赛导出；
- vLLM 服务启动与 NVIDIA 训练/Serving 脚本；
- LightGBM、group-aware OOF、SFT/DPO 和 DeepSeek Agent Workflow——旧库中没有可迁移实现。

这些模块若迁移，需要先删除的旧语义多于能够保留的代码，重新定义干净接口更便宜。

### Q4：旧资产预计能节省多少工作？

总体判断为 **中等**。主要节省在 OpenAI-compatible 调用、逐记录失败恢复、结构化输出防御、Prompt/结果追踪、知识文档切分和成本记录；这些是容易在实验后期造成重复劳动的工程基础。

节省不会达到“明显”，因为新项目最核心的 Flow Schema 适配、无泄漏 60 秒上下文、LightGBM 与 group-aware OOF、tree-aware Reviewer 数据构造、QLoRA-SFT/DPO、DeepSeek 工具协议和 Agent Task Suite 均需新建。

## 5. 对新项目设计的影响

没有发现需要改变 `Flow / NetFlow → 60s causal context → LightGBM → Qwen3.5-9B Reviewer → Static / DeepSeek Agentic Workflow` 研究路线的旧资产，也没有可直接继承的 Agent 框架。

唯一值得提升为新项目硬性工程要求的遗产是：**每条 Reviewer/Teacher/Agent 调用都应具有输入与 Prompt 指纹、经过 Schema 校验的结果缓存、独立失败记录、usage/latency Trace 和可验证的 resume 行为。** 这不会改变论文方法，但能显著降低长时间 SFT 数据生成和系统实验的恢复风险。
