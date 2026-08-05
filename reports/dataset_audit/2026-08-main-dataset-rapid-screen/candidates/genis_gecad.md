# GeNIS / GECAD Network Intrusion Scenarios

访问日期：2026-08-04

1. **名称、版本、年份：** GeNIS: GECAD Network Intrusion Scenarios，Zenodo record 14919237，2025（记录后续更新至 2026）。
2. **官方来源和原始论文：** [Zenodo 官方记录](https://doi.org/10.5281/zenodo.14919237)；原始 Data in Brief 论文 DOI：[10.1016/j.dib.2025.111487](https://doi.org/10.1016/j.dib.2025.111487)。
3. **是否真实可下载：** 是。官方记录列出 0-info.zip、PCAPNG、flows、scenarios 和 preprocessed 五个归档及大小。
4. **许可证：** `UNKNOWN`。论文为 Creative Commons 开放获取，但本轮页面抽取未显示数据记录的具体 license 值。
5. **网络数据类型：** PCAPNG；5/10/30/60 秒间隔生成的标注 Flow；场景级数据。
6. **能否只使用网络数据：** 能。
7. **样本单位：** 包、固定间隔 Flow、攻击步骤或顺序攻击场景。
8. **coarse 类别及数量：** Benign；3 个攻击 coarse：Brute Force、DoS、Reconnaissance。
9. **fine 类别及数量：** 10 个攻击 fine：FTP/SMB/SSH brute force；Hulk/ICMP/Push&Ack/Slowloris/UDP DoS；DNS/Nmap recon。
10. **网络可用 fine 类别估计：** 10。
11. **Benign 数据：** 有，包含管理员、用户和背景流量。
12. **attack/session/run/capture ID：** 有场景、步骤、capture 时间边界；独立 run ID 为 `UNKNOWN`。
13. **每个 fine 类的独立 group 数量：** `UNKNOWN`。
14. **是否有重复执行：** 多个顺序场景，但每个 fine 类是否有足够独立重复为 `UNKNOWN`。
15. **标签如何生成：** 按官方攻击场景/步骤 ground truth 和流量时间关系生成标注 Flow。
16. **标签能否落到网络样本：** 能。
17. **是否存在背景流量：** 是。
18. **是否存在 class-specific preprocessing：** 官方提供四种统一 Flow 间隔；是否存在类别特定处理未发现，记为 `UNKNOWN`。
19. **group split 是否可行：** 场景级可能可行，但逐 fine 支持数量为 `UNKNOWN`。
20. **K/U 预注册是否可行：** 否，类别数量先于其他条件触发 G3。
21. **near unknown 是否可行：** 否；类别层次不足以满足冻结的完整设计。
22. **far unknown 是否可行：** 否。
23. **1-shot 是否可行：** `UNKNOWN`。
24. **5-shot 是否可行：** `UNKNOWN`。
25. **10-shot 是否可行：** 否，未证实每个候选类有 10+1 独立活动。
26. **support/query 是否独立：** 否，现有证据不足以构造严格独立的 10+1。
27. **最大风险：** 名义类别结构低于论文冻结门槛，不能通过更多 Flow 或窗口弥补。
28. **尚缺证据：** 精确 license、逐 fine 场景重复次数；但这些不会修复 G3。
29. **Hard Gate 逐项状态：**

| G1 | G2 | G3 | G4 | G5 | G6 | G7 | G8 | G9 | G10 |
|---|---|---|---|---|---|---|---|---|---|
| PASS | PASS | **FAIL** | UNKNOWN | UNKNOWN | FAIL | UNKNOWN | UNKNOWN | PASS | UNKNOWN |

30. **最终状态：** `FAIL_HARD_GATE`。停止原因：G3 明确失败。

## 关键证据位置

- Zenodo 描述与文件清单：37M+ packets、2.8M+ flows、5/10/30/60 秒间隔及五个归档。
- 原始论文数据分类表：3 个攻击 coarse、10 个攻击 fine、8 个顺序场景。
