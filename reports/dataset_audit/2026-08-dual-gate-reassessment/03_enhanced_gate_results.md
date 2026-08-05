# 增强研究门槛结果

## 总结

加入 R1—R12 后，完整 `PASS_ENHANCED` 数量为 **0**。这不推翻 8 个最低门槛候选，而是说明当前没有一个数据集能够同时无条件支撑“细粒度 Flow 开放识别 + 官方活动分组 + group-level few-shot + 跨环境验证 + 完整捷径审计”的全部强结论。

## 最低门槛候选的增强结论

| 数据集 | 增强状态 | 已有增强资产 | 尚缺的关键条件 |
| --- | --- | --- | --- |
| CICIoMT2024 | PARTIAL_ENHANCED | PCAP、18 细类/5 粗类、Benign、公开攻击说明 | 独立 run manifest；统一窗口；设备/协议/文件捷径审计 |
| DataSense 2025 | PARTIAL_ENHANCED | PCAP、49/7 层次、同步时间、现代 IIoT 场景 | 核心归档 schema；run/capture manifest；精确 Flow 落标和 group-level support/query |
| X-IIoTID | PARTIAL_ENHANCED | 18/9 层次、UID/时间、多日记录 | 纯网络字段冻结、官方 run manifest、跨源捷径审计、数据许可说明 |
| UWF | PARTIAL_ENHANCED | 逐 Flow ATT&CK、跨版本/周、已完成重复与来源探针 | 官方 activity ID；更多可靠可观察 Technique；弱化固定端口/版本捷径 |
| Gotham 2025 | PARTIAL_ENHANCED | PCAP、现代多设备网络、攻击编排元数据、层次标签 | attack-event manifest；跨接口副本关系；每类独立运行数 |
| CICIoT2023 | PARTIAL_ENHANCED | 33/7 层次、PCAP、Benign、完整窗口计数 | 一类一次攻击实验、无 run ID、10/100 包类别特定窗口 |
| NF-ToN-IoT-v3 | PARTIAL_ENHANCED | 大规模 Flow、精确标签计数、原始 PCAP 来源 | v3 中无 run/activity ID；缺少可靠 grouped few-shot；场景捷径风险 |
| GeNIS | PARTIAL_ENHANCED | PCAP、场景/步骤、精确 Flow 标签、多个窗口长度 | 类别仅 10 个；每类独立重复活动有限；跨环境证据不足 |

## 未通过最低门槛但仍有增强资产的数据集

TQH-C2 是最典型的“工程与实验设计强、任务类别不足”：36 个独立 cell、3 种加密 profile、4 个 beacon interval、3 个 jitter、并发 Benign、逐 Flow 标签、PCAP、manifest 和脚本都很完整，适合做跨 profile 鲁棒性辅助实验；但它只有 `malicious_c2`、`malicious_lateral`、`malicious_recon` 三个恶意标签，因此不能成为本项目的细粒度主数据集。

CAM-LDS 有 34 个 simulation run 和 ATT&CK 步骤元数据，CICAPT-IIoT2024 有 APT provenance；二者都可以服务运行级或多源案例分析，但前者缺 Benign 与直接 Flow join，后者的细粒度语义大量依赖主机/provenance，因此仍是 `FAIL_ENHANCED`。NF-CSE 与 NF-BoT 有 PCAP 来源和大量 Flow，但细类数量不足。其余任务语义不匹配的数据集不进入增强候选。

## 解释边界

增强门槛失败的正确解释是“不能声称活动级、跨设备或跨环境泛化”，而不是“不能做任何开放集实验”。最低门槛候选仍可做 class-level holdout、sample-level few-shot、RAG 与 Reviewer 研究，只需把独立性单位、窗口语义和捷径风险写清楚。
