# Multi-Source Cybersecurity Logs: An ATT&CK-Labeled Dataset and SLM Evaluation

访问日期：2026-08-04

1. **名称、版本、年份：** Multi-Source Cybersecurity Logs: An ATT&CK-Labeled Dataset and SLM Evaluation，arXiv:2606.18190，2026。
2. **官方来源和原始论文：** 独立官方数据来源为 `UNKNOWN`；[原始论文](https://arxiv.org/abs/2606.18190)。
3. **是否真实可下载：** 否；截至访问日未从原始论文找到数据仓库或文件清单入口。
4. **许可证：** `UNKNOWN`。
5. **网络数据类型：** 网络事件与系统、浏览器事件同步记录。
6. **能否只使用网络数据：** 否。论文明确说明完整攻击与 technique 识别需要关联三类来源。
7. **样本单位：** event、20 分钟 session、chunk。
8. **coarse 类别及数量：** 12 个 ATT&CK tactics；Benign/suspicious session。
9. **fine 类别及数量：** 53 个 ATT&CK techniques。
10. **网络可用 fine 类别估计：** `UNKNOWN`，且不能假设 53 个均网络可观察。
11. **Benign 数据：** 800 个 benign sessions。
12. **attack/session/run/capture ID：** 70 attack sessions、800 benign sessions；具体公开字段为 `UNKNOWN`。
13. **每个 fine 类的独立 group 数量：** `UNKNOWN`；70 attack sessions 分布于 53 techniques，不足以推断 11/group。
14. **是否有重复执行：** 有 70 次 attack simulations，但逐 technique 重复数为 `UNKNOWN`。
15. **标签如何生成：** 对同步多源事件标注 malicious 和 ATT&CK technique ID。
16. **标签能否落到网络样本：** 不能对全部 technique 成立；论文任务依赖跨源上下文。
17. **是否存在背景流量：** 有 benign sessions；攻击 session 内背景细节为 `UNKNOWN`。
18. **是否存在 class-specific preprocessing：** `UNKNOWN`。
19. **group split 是否可行：** session 级原则上可行，但数据未公开，无法核验。
20. **K/U 预注册是否可行：** 否；G1/G10 已失败。
21. **near unknown 是否可行：** `UNKNOWN`。
22. **far unknown 是否可行：** `UNKNOWN`。
23. **1-shot 是否可行：** `UNKNOWN`。
24. **5-shot 是否可行：** `UNKNOWN`。
25. **10-shot 是否可行：** `UNKNOWN`，总 session/technique 比例也不支持积极推断。
26. **support/query 是否独立：** session 级理论上可独立；公开数据不可核验，记为 `UNKNOWN`。
27. **最大风险：** 论文贡献本身是三源关联；移除主机与浏览器将改变标签语义和任务。
28. **尚缺证据：** 官方数据仓库、license、schema、manifest、逐 technique session 数、network-only 标签覆盖。
29. **Hard Gate 逐项状态：**

| G1 | G2 | G3 | G4 | G5 | G6 | G7 | G8 | G9 | G10 |
|---|---|---|---|---|---|---|---|---|---|
| **FAIL** | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | PASS | **FAIL** |

30. **最终状态：** `FAIL_HARD_GATE`。G1 与 G10 已确认失败，停止深入。

## 关键证据位置

- 原始论文 Introduction/Methodology：870 sessions（70 attack、800 benign）、约 2.3M events、三源同步、53 techniques。
- 原始论文明确表述完整攻击需要 system/network/browser correlation；页面未给出数据下载或 availability 链接。
