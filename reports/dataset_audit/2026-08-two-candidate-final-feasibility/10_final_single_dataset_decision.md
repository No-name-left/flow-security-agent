# 单一主数据集最终决定

## 最终回答

1. **是否找到合格单一主数据：否。** 当前没有任一候选获得全部 Gate 的 A/B 级证据。
2. **DataSense：** `BLOCKED_PENDING_AUTHOR_CONFIRMATION`。
3. **CICIoMT2024：** `BLOCKED_PENDING_AUTHOR_CONFIRMATION`。
4. **最大阻塞：** DataSense 缺少逐 fine 类独立执行与 PCAP→run→label manifest；CICIoMT 缺少 PCAP/chunk→独立执行映射与逐类 run 数，同时现成 CSV 有类相关 10/100 包窗口。
5. **是否允许启动正式 Qwen 实验：否。** BLOCKED 不是数据 Gate 通过。
6. **是否关闭公开单一数据集搜索路线：是，暂时关闭。** 本轮已按限定范围完成两候选最终审查；除非作者回复或官方归档 manifest 解锁，不继续扩大公开候选或重复网页检索。
7. **是否进入受控核心数据设计：可以进入设计准备，但不能把它当作已获正式数据。** 可并行准备 run manifest schema、统一 Flow 提取规范与 controlled-core 采集/整合方案；任何正式训练仍需数据 Gate 再审。

## 为什么不能用“足够多的包/Flow”替代

两套数据的包量和派生实例量都很大，但论文项目的 shot 单位是独立攻击活动。一个长 PCAP 的窗口、同一次执行的分片或多个 CSV 行在统计上高度相关，不能支持独立 support/query、未知攻击最终隔离或 Agent 的无泄漏评价。

## 形式化能力判断

| 能力 | DataSense | CICIoMT2024 |
|---|---|---|
| 纯网络输入 | 官方材料支持 | 官方材料支持 |
| coarse/fine 标签广度 | 支持 | 支持 |
| Known 闭集训练 | 数据行层面可做；正式 run-level 尚未通过 | 数据行层面可做；正式 run-level 尚未通过 |
| U_dev / U_final | 无法证明 | 无法证明 |
| Unknown 拒识 | 可设计但不能正式评测 | 可设计但不能正式评测 |
| 独立活动 1/5/10-shot | 不可确认 | 不可确认 |
| support/query 隔离 | 不可确认 | 不可确认 |
| 无泄漏 group split | 不可确认 | 不可确认 |
| Adaptive Decision Agent 正式评价 | 不可启动 | 不可启动 |

## 可改变结论的最小新证据

作者或官方归档需提供：逐类独立执行次数、run/capture manifest、每次执行的时间/攻击者/目标、PCAP 与派生 CSV 映射、Benign 独立 session 清单、train/test 的执行级划分依据及明确数据许可。收到后只需重跑 Gate 审查，无需重新扩大数据集搜索。
