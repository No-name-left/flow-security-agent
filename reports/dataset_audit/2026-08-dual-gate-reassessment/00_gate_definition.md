# 数据集双门槛复审口径

审查日期：2026-08-05。本轮只重判数据集角色，不修改研究计划、交接文档、代码、测试或配置，也不下载大型数据。

## 1. 为什么改用双门槛

此前审查把“独立攻击运行、严格 group split、group-level 10-shot、跨环境泛化”等增强条件同时用于主数据集准入，导致若干具备充分网络记录、细粒度标签和样本级开放集能力的数据集被过早否决。本轮将“能否支撑一篇范围受限但可复现的论文”与“能否支撑更强的泛化结论”分开。

最低门槛允许以 Flow、NetFlow、会话、固定窗口或 Episode 作为网络样本；标签可来自受控攻击场景，只要样本—标签关系明确。样本级 1/5/10-shot 是合法实验单位，不再要求每个 shot 来自独立攻击运行。相应结论必须写成“样本级少样本适配”，不得偷换为“跨任务、跨环境或跨攻击活动泛化”。

## 2. 最低发表门槛（M1—M8）

| Gate | 判定问题 | 最低通过条件 |
| --- | --- | --- |
| M1 | 是否为网络输入 | PCAP、Flow、NetFlow、网络会话、网络窗口或网络 Episode 均可；不要求主机日志或传感器日志 |
| M2 | 标签能否落到样本 | 存在 Benign/Normal 与攻击标签；标签可以是场景级，但必须准确写明样本语义 |
| M3 | 攻击细类是否足够 | 12 类及以上为 `PASS_MINIMAL`；8—11 类为 `PASS_MINIMAL_NARROW`；少于 8 类失败 |
| M4 | 记录量是否支持拆分 | 每个入选类别需有足够不同记录支持 known train/validation/test，并为 `U_dev`、`U_final` 保留 10 条 support 和 query；无法核实时记未知 |
| M5 | Unknown 是否可隔离 | `U_final` 整类不进入分类器、SFT、Prompt 示例、prototype、阈值或 Agent 训练 |
| M6 | 基本泄漏控制 | 控制精确重复；support/query 不含同一条记录；标签、文件名和官方 split 字段不进入模型特征 |
| M7 | 是否可合法获得 | 已公开下载，或存在官方且可执行的注册/申请流程 |
| M8 | 是否支持知识卡 | 官方论文、说明文档或 ATT&CK/攻击定义足以构造 RAG 类别卡 |

最低门槛状态只使用：`PASS_MINIMAL`、`PASS_MINIMAL_NARROW`、`FAIL_MINIMAL`、`UNKNOWN_MINIMAL`。

## 3. 增强研究门槛（R1—R12）

增强门槛在最低门槛之上进一步检查：官方 run/activity/capture ID、可靠 group split、group-level few-shot、IP/设备/端口/时间/文件来源捷径审计、类别特定窗口、多个参数/目标/环境、精确 Flow 标签、攻击期间 Benign、原始 PCAP、跨环境验证、层次标签以及现代攻击或 ATT&CK 语义。

增强状态只使用：`PASS_ENHANCED`、`PARTIAL_ENHANCED`、`FAIL_ENHANCED`、`UNKNOWN_ENHANCED`。其中 `PASS_ENHANCED` 表示最低门槛通过且增强条件整体成立；`PARTIAL_ENHANCED` 表示最低门槛通过、但只能支撑部分增强结论；最低门槛失败的数据集不会因若干工程优点被误记为完整增强通过。

## 4. 证据与不确定性规则

- `HIGH`：官方数据页、原始论文、官方 README 或已下载文件审计直接支持。
- `MEDIUM`：官方描述充分，但核心归档、字段或完整计数尚未逐文件复核。
- `LOW`：主要依赖二级论文或搜索摘要，只能支持排除性判断，不可用于冻结正式方案。
- 缺少 run ID、活动级独立性或严格 group split，只影响增强门槛；不得单独否决最低门槛。
- 若任务语义本身是应用、网站、VPN/Tor 或主机事件分类，即使“类别很多”，也不能把这些类别当成攻击细类。

## 5. 主要证据源

本轮优先复用仓库中 `2026-08-formal-selection`、`2026-08-unblocking`、`2026-08-uwf-main-validation`、`2026-08-ciciot2023-main-validation`、`2026-08-main-dataset-rapid-screen` 与 `2026-08-two-candidate-final-feasibility` 的既有审计。新增外部核验仅针对证据缺口，主要包括：UQ NF-v3 官方清单、UNB CIC 官方数据页、Zenodo 官方记录、X-IIoTID 作者仓库、GeNIS 原始论文、TQH-C2 官方 README、CSTNET DOI/DataCite 元数据，以及本地保存的 MET-LLM 论文。

核心公开入口：[UQ NF-v3 清单](https://staff.itee.uq.edu.au/marius/NIDS_datasets/)、[UNB CIC 数据集目录](https://www.unb.ca/cic/datasets/)、[X-IIoTID 作者仓库](https://github.com/Alhawawreh/X-IIoTID)、[GeNIS Zenodo](https://doi.org/10.5281/zenodo.14919237)、[Gotham Zenodo](https://doi.org/10.5281/zenodo.14502760)、[TQH-C2 Zenodo](https://zenodo.org/records/21435571)、[CSTNET DOI 元数据](https://api.datacite.org/dois/10.21227/4394-fv34)。
