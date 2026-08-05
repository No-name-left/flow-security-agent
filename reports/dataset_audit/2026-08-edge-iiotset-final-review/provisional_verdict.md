# 建议判定：PROVISIONAL_PASS_WITH_LIMITATIONS

## 判定

Edge-IIoTset 具备原始 PCAP、逐包 CSV、Normal、14 个攻击细类、5 个攻击粗类和足够的样本级数量；双向会话、包序列、同捕获 past-only 上下文、class-held-out Unknown 及 1/5/10-shot 协议均能运行。因此没有出现“完全不能重建会话、没有标签或类别数量不足”等阻断性 FAIL 证据。

但现阶段**不能最终锁定为唯一主数据集**。最大问题不是文件规模，而是实验独立性：攻击文件几乎与类别一一对应且每类通常只有一个捕获，随机 session 切分会共享同一场景、端点和攻击活动；few-shot support/query 也只能先做到 sample-level。另有时间字段缺失、应用/Payload 捷径和一个官方 PCAP 异常。这些限制足以要求继续验证，但尚不足以判为 PROVISIONAL_FAIL。

与第二数据集的兼容目前只在接口层可行：保留 Edge-IIoTset 原生细类，通过统一 Session Evidence 和 `DatasetLabelSchema` 适配器，在共同粗类或 Unknown 任务上比较；不得把 Edge 的端口/IP/设备捷径迁移为通用 Schema。由于本阶段没有审查第二数据集，不能声称跨数据集标签和会话定义已经对齐。

## Gate 汇总

| Gate | 结果 | 关键事实 |
|---|---|---|
| A | PASS_WITH_LIMITATION | 作者发布、学术许可、完整 ZIP 哈希一致；Vulnerability PCAP 有异常尾部记录 |
| B | PASS | 原生二值 + 14 细类；粗类可确定映射；CSV 为逐包记录 |
| C | PARTIAL_PASS | 配对文件数量/时间基本对应，不能按行号无损对齐 |
| D | PROBE_PASS | 30/60 秒双向会话可构造；正式解析器和标签冲突规则待固化 |
| E | CONDITIONAL_PASS | PCAP 时间支持 past-only；必须限 capture/split，CSV 时间不能跨捕获 |
| F | HIGH_RISK | shortcut-only 随机切分 Macro-F1 99.82%；去捷径/端点分组显著下降 |
| G | CONDITIONAL_PASS | class-held-out 和 sample-level few-shot 可行；capture/run 独立性不足 |
| H | PROBE_PASS | 16 包 + 上下文 + 应用证据 + 小 RAG 的中位估算低于 1k tokens |
| I | PASS | 原始数据本地保留，服务器用冻结派生数据即可 |

## 最终锁定前仍需补齐的最小证据

1. 在 Linux/TShark 或另一成熟 PCAP 库中复核全部 PCAP，特别是 `Vulnerability scanner attack.pcap`，确认异常位置和可恢复范围。
2. 用正式会话化实现复现代表性统计，稳定处理 timestamp 倒序、非 TCP/UDP、缺失端口和 mixed-label。
3. 冻结去捷径字段白名单并做时间块/端点/可用 capture 级敏感性分析；不得以随机切分为主结果。
4. 明确数据集角色：若作为主数据集，需由第二数据集承担跨场景/跨 run 验证；若无法获得该证据，应降低 Edge-IIoTset 的论文结论强度。
5. 在正式 session 上预注册 K/U、去重、support/query 与 past-only split 内索引，再决定是否进入模型训练。

本判定只建议 Edge-IIoTset 继续进入锁定前验证，不新增 Decision Log，不改变当前研究架构，也不授权 Phase 3 或 Qwen 训练。
