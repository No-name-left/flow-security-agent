# Windows-APT 2025

访问日期：2026-08-04

1. **名称、版本、年份：** Windows-APT 2025，Mendeley Data version 3，数据发布 2025；Data in Brief 论文 2026。
2. **官方来源和原始论文：** [Mendeley Data DOI 10.17632/b8fmtzvpy8.3](https://doi.org/10.17632/b8fmtzvpy8.3)；[原始论文 DOI 10.1016/j.dib.2026.112569](https://doi.org/10.1016/j.dib.2026.112569)。
3. **是否真实可下载：** 是；原始论文列出 19 个 CSV、manifest、validation summary、配置和示例材料。
4. **许可证：** CC BY 4.0（Mendeley Data 记录）。
5. **网络数据类型：** Wazuh/Sysmon 多源 Windows 事件中的网络字段；无 raw PCAP。
6. **能否只使用网络数据：** 否。标签所需的命令、进程、文件、哈希、路径、登录和主机事件不可由网络字段替代。
7. **样本单位：** Wazuh/Sysmon log record、采集周期、APT-inspired scenario。
8. **coarse 类别及数量：** 名义覆盖约 10 个 ATT&CK tactics；不是网络原生 coarse/fine 层次。
9. **fine 类别及数量：** ATT&CK techniques，精确唯一数量为 `UNKNOWN`。
10. **网络可用 fine 类别估计：** 少于 12 个已确认；完整数量为 `UNKNOWN`。
11. **Benign 数据：** 有正常日志基线。
12. **attack/session/run/capture ID：** scenario manifest 和 validation summary 提供 scenario/run 级信息；无网络 capture ID。
13. **每个 fine 类的独立 group 数量：** validation summary 记录重复运行，但逐 network-observable fine 的合格组数为 `UNKNOWN`。
14. **是否有重复执行：** 是，validation summary 记录每个 scenario 的 run 数和成功率。
15. **标签如何生成：** 36 个 APT-inspired scenario 按 MITRE ATT&CK 映射，Wazuh/Sysmon 事件含 tactic/technique 字段并经 validation cycle 审核。
16. **标签能否落到网络样本：** 不能对大多数技术成立；主要落到 host log event。
17. **是否存在背景流量：** 有正常日志；网络攻击 capture 背景为 `UNKNOWN`。
18. **是否存在 class-specific preprocessing：** `UNKNOWN`。
19. **group split 是否可行：** scenario 级可行，但对 network-only 任务无意义。
20. **K/U 预注册是否可行：** 不适用于当前 network-primary 主数据口径。
21. **near unknown 是否可行：** `UNKNOWN`。
22. **far unknown 是否可行：** `UNKNOWN`。
23. **1-shot 是否可行：** 可能在 host-log 任务中可行；当前任务为否。
24. **5-shot 是否可行：** 当前 network-only 任务为否。
25. **10-shot 是否可行：** 当前 network-only 任务为否。
26. **support/query 是否独立：** scenario/run 可隔离，但网络证据不足，不能满足当前任务。
27. **最大风险：** 因 ATT&CK 标签丰富而误将主机遥测数据当成 Flow 主数据。
28. **尚缺证据：** 即使补充网络字段清单，也无法消除标签对主机事件的结构性依赖。
29. **Hard Gate 逐项状态：**

| G1 | G2 | G3 | G4 | G5 | G6 | G7 | G8 | G9 | G10 |
|---|---|---|---|---|---|---|---|---|---|
| **FAIL** | PASS | FAIL_NETWORK_ONLY | UNKNOWN | FAIL_CURRENT_TASK | FAIL_CURRENT_TASK | PASS_SCENARIO_LEVEL | UNKNOWN | UNKNOWN | PASS |

30. **最终状态：** `FAIL_HARD_GATE`。G1 已确认失败。

## 关键证据位置

- 原始论文 §3：36 scenarios、约 102k records、19 CSV、manifest 与 validation summary。
- 原始论文数据字段：Full-log、commands、payloads、hashes、paths、Wazuh/Sysmon tactic/technique 等主机语义。
