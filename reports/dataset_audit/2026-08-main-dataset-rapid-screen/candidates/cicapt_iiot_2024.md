# CICAPT-IIoT 2024

访问日期：2026-08-04

1. **名称、版本、年份：** CICAPT-IIoT 2024，2024。
2. **官方来源和原始论文：** [UNB CIC 官方页面](https://www.unb.ca/cic/datasets/iiot-dataset-2024.html)；[原始论文 arXiv:2407.11278](https://arxiv.org/abs/2407.11278)。
3. **是否真实可下载：** 官方入口存在；本轮未下载大型归档。
4. **许可证：** `UNKNOWN`。
5. **网络数据类型：** raw/processed network PCAP/CSV；同时包含 provenance graph/logs。
6. **能否只使用网络数据：** 只能覆盖部分步骤，不能保留完整 fine technique 语义。
7. **样本单位：** packet、Flow、provenance node/edge、APT attack step/phase。
8. **coarse 类别及数量：** 8 个 ATT&CK tactics/阶段。
9. **fine 类别及数量：** 20 余个 ATT&CK techniques。
10. **网络可用 fine 类别估计：** 少于 12 个已确认；screen capture、clipboard、file discovery、credential files、local account、data staged 等需主机/provenance。
11. **Benign 数据：** 有 Phase 1/背景数据。
12. **attack/session/run/capture ID：** Attack_info.csv 含 Caldera attack time、PID、category；两阶段 capture。正式逐 technique 独立 run ID 为 `UNKNOWN`。
13. **每个 fine 类的独立 group 数量：** 主要来自一个 APT29-inspired campaign；不足以证明每类 3 或 11 个独立活动。
14. **是否有重复执行：** `UNKNOWN`；论文强调一个 APT 场景及两阶段，而非逐技术多次独立执行。
15. **标签如何生成：** Caldera 编排信息、attack_info 时间/PID/category 与 network/provenance 数据关联。
16. **标签能否落到网络样本：** 部分可落到；大量技术只能由 provenance/host 语义确认。
17. **是否存在背景流量：** 有 benign/Phase 1；攻击期间背景细节为 `UNKNOWN`。
18. **是否存在 class-specific preprocessing：** `UNKNOWN`。
19. **group split 是否可行：** 否；单一 campaign/阶段不能提供所有集合所需独立活动。
20. **K/U 预注册是否可行：** 否。
21. **near unknown 是否可行：** 名义 tactics 允许定义，但独立执行与网络证据不足，实际为否。
22. **far unknown 是否可行：** 名义可定义，实际独立 group 不足。
23. **1-shot 是否可行：** `UNKNOWN`；个别步骤或可作为行为 episode，但不满足完整主数据要求。
24. **5-shot 是否可行：** 否，未证实独立重复。
25. **10-shot 是否可行：** 否。
26. **support/query 是否独立：** 否；不能把同一 campaign 的步骤/Flow 分片当作独立 query。
27. **最大风险：** 丰富的 ATT&CK 标签来自多源 provenance，而不是纯网络可观察的独立攻击类。
28. **尚缺证据：** 逐 technique 独立执行清单；但 G1/G3 的网络可观察性缺口已经足以停止。
29. **Hard Gate 逐项状态：**

| G1 | G2 | G3 | G4 | G5 | G6 | G7 | G8 | G9 | G10 |
|---|---|---|---|---|---|---|---|---|---|
| **FAIL** | PASS_PARTIAL | **FAIL_NETWORK_USABLE** | FAIL | **FAIL** | FAIL | FAIL | UNKNOWN | PASS_PARTIAL | UNKNOWN |

30. **最终状态：** `FAIL_HARD_GATE`。G1、G3、G5 已确认失败。

## 关键证据位置

- 原始论文 §3：一个 APT29-inspired scenario、两阶段、20+ techniques、network + provenance。
- 官方技术列表包含大量不可从 Flow 直接观察的文件、屏幕、剪贴板、账户和凭据动作。
