# Edge-IIoTset 最终锁定前客观可行性审查

## 审查范围

本目录记录 Phase 2 的数据事实与最小可执行探针。目标是判断 Edge-IIoTset 是否具备支持“会话序列、past-only 上下文、class-held-out Unknown、few-shot 新类接入和本地/服务器协作”的基本条件；本报告**不构成主数据集最终锁定**，也未启动 Qwen 训练。

证据优先级为：本地完整归档及 SHA-256、可复现探针输出、作者 Kaggle/论文/IEEE DataPort 等官方资料、最后才是明确标注的推断。原始数据位于被 `.gitignore` 排除的 `data/external/edge_iiotset/`，不会进入 Git。

## 执行摘要

建议判定为 **PROVISIONAL_PASS_WITH_LIMITATIONS**。完整作者版归档已下载、官方 MD5 一致并解压；原始 PCAP、逐包 CSV、正常流量和 14 类攻击均存在，可重建双向五元组会话并构造同一捕获内的 past-only 上下文。主要限制是：每个攻击类别基本只有一个独立攻击捕获，文件/场景/类别高度耦合；原始 CSV 时间缺少完整日期且 MITM 时间为空；一个官方 PCAP 存在异常尾部记录；few-shot 只能先证明 sample-level 可执行，不能宣称 capture/run 独立。

| Gate | 临时结果 | 核心依据 |
|---|---|---|
| A 来源、许可、完整性 | 通过但有限制 | 作者 Kaggle、CC BY-NC-SA 4.0、完整 ZIP MD5；1 个官方 PCAP 异常 |
| B 标签与粒度 | 通过 | 14 攻击细类、Normal、5 个粗类；CSV 为逐包导出 |
| C PCAP/CSV 对齐 | 部分通过 | 数量与时间可基本对应，但不能按行直接一一拼接 |
| D 双向会话 | 通过最小探针 | 5 元组、capture 边界、30/60 秒均可执行 |
| E 跨会话关联 | 有条件通过 | PCAP epoch 可排序并 past-only；必须限于同 capture/split |
| F 泄漏与捷径 | 高风险 | 随机切分显著虚高；端点、端口、时间、Payload/URI 均可能泄漏 |
| G K/U 与 few-shot | class-held-out 可行，few-shot 有限 | 数量足够，但攻击类缺乏多次独立捕获 |
| H LLM 输入长度 | 通过初始探针 | 16 包 + 上下文 + 少量应用证据 + RAG 约 683–911 tokens（估算） |
| I 本地/服务器分工 | 通过 | 原始 PCAP 留本地；服务器只需冻结后的派生数据与清单 |

## 文件导航

- 来源、许可和存储：`source_manifest.json`、`license_and_access.md`、`storage_inventory.md`、`file_inventory.csv`
- 标签与字段：`label_schema.md`、`class_counts.csv`、`raw_schema.md`
- 可执行探针：`pcap_csv_alignment.md`、`sessionization_probe.md`、`session_statistics.csv`、`temporal_context_probe.md`
- 研究可行性：`leakage_probe.md`、`ku_fewshot_feasibility.md`、`llm_input_probe.md`、`local_server_workflow.md`
- 综合判定：`provisional_verdict.md`
- 复现辅助：`run_minimal_probe.py`、`build_full_inventory.py` 及相应 JSON 探针输出。
