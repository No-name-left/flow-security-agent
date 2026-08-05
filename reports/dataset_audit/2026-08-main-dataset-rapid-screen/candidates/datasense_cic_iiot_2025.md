# DataSense: CIC IIoT Dataset 2025

访问日期：2026-08-04

1. **名称、版本、年份：** DataSense: CIC IIoT Dataset 2025，2025。
2. **官方来源和原始论文：** [UNB CIC 官方页面](https://www.unb.ca/cic/datasets/iiot-dataset-2025.html)；[原始论文 DOI 10.3390/electronics14204095](https://doi.org/10.3390/electronics14204095)。
3. **是否真实可下载：** 官方下载入口已确认；本轮未下载大型数据，具体核心归档内容未逐文件验证。
4. **许可证：** `UNKNOWN`。官方页面未在本轮可见内容中明确给出数据 license。
5. **网络数据类型：** 端口镜像捕获的 PCAP；同步 MQTT/传感器/应用日志。
6. **能否只使用网络数据：** 可以构造 network-only 版本；至少 DoS、DDoS、Recon、Bruteforce、MITM 等大量类型有网络证据。
7. **样本单位：** 包、PCAP、按攻击目标组件分段的 capture；论文评估另使用 10 秒切片。
8. **coarse 类别及数量：** Benign + 7 个攻击类别：Recon、DoS、DDoS、Web、MITM、BruteForce、Malware。
9. **fine 类别及数量：** 49 个攻击 fine + Benign（50-class 任务）。
10. **网络可用 fine 类别估计：** 至少 12 个名义上有网络证据；逐类可观察性完整审查为 `UNKNOWN`。
11. **Benign 数据：** 12 小时正常采集；论文评估随机取 1 小时并切为 10 秒片段。
12. **attack/session/run/capture ID：** PCAP 按目标组件分段；正式 run/scenario ID、可复核 manifest 为 `UNKNOWN`。
13. **每个 fine 类的独立 group 数量：** `UNKNOWN`；官方论文报告包数/日志数，不报告逐类独立执行数。
14. **是否有重复执行：** `UNKNOWN`。49 个“distinct attack types”不等于每类多次独立执行。
15. **标签如何生成：** 受控攻击执行，网络与日志统一时间同步，PCAP 按攻击目标组件组织。
16. **标签能否落到网络样本：** 部分明确可行；逐包/逐 Flow 标签规则及背景剥离细节为 `UNKNOWN`。
17. **是否存在背景流量：** 是；论文说明攻击场景可同时包含其他设备活动。
18. **是否存在 class-specific preprocessing：** 有按目标组件分段；是否会把组件身份泄漏为类别为 `UNKNOWN`。Benign 评估使用 10 秒切片。
19. **group split 是否可行：** `UNKNOWN`；需 run manifest，而不能按 PCAP 段或行随机划分。
20. **K/U 预注册是否可行：** 类别结构名义可行；独立 group 支持为 `UNKNOWN`。
21. **near unknown 是否可行：** 名义上可行（例如同 coarse 内不同 flood/scan fine）；独立活动支持为 `UNKNOWN`。
22. **far unknown 是否可行：** 名义上可行；独立活动支持为 `UNKNOWN`。
23. **1-shot 是否可行：** `UNKNOWN`。
24. **5-shot 是否可行：** `UNKNOWN`。
25. **10-shot 是否可行：** `UNKNOWN`；没有官方 10 support + 1 query 证据。
26. **support/query 是否独立：** `UNKNOWN`。
27. **最大风险：** 大量包和 49 类掩盖了逐类独立 run 元数据缺失；目标组件分段可能造成设备/IP/文件捷径。
28. **尚缺证据：** 逐类 run/capture manifest、攻击开始/结束、重复执行次数、group ID、标签落点规则、文件树、精确 license。
29. **Hard Gate 逐项状态：**

| G1 | G2 | G3 | G4 | G5 | G6 | G7 | G8 | G9 | G10 |
|---|---|---|---|---|---|---|---|---|---|
| PASS | UNKNOWN | PASS | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | PASS | UNKNOWN |

30. **最终状态：** `INSUFFICIENT_EVIDENCE`。未发现确认的硬失败，但不能把类别数和包数替代 G4/G5/G7/G10。

## 关键证据位置

- 原始论文 §3.3–3.5：端口镜像、同步时间、12 小时 Benign、49 种攻击、PCAP 按目标组件分段。
- 原始论文 Table 4：逐攻击类型包数/日志数；该表没有逐类独立 run 数。
