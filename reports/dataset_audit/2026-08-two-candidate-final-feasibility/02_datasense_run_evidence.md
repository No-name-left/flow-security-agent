# DataSense：独立 Run 与 Few-shot 证据

## 独立执行证据

原始论文称 49 个 distinct attack types 在测试床不同组件或整个网络上执行，并称 PCAP “segmented according to the targeted components of each attack”。这只说明归档按攻击目标/组件组织，不能证明一个 PCAP 等于一次独立执行，也不能证明每类存在多个独立执行。

逐 fine 类核验结果见 `08_per_class_independent_group_counts.csv`：49 个攻击类及 Benign 的独立 run 数全部为 `UNKNOWN`。官方材料公布的是包数、日志数、场景名和攻击工具；这些均为 D 级数量证据，不能替代 run 数。

## Benign

官方论文确认 12 小时正常运行，覆盖工作时段及非工作时段，这是时间覆盖的正面证据。但公开材料未说明这 12 小时由多少个独立 capture/session 组成，也未提供至少 40 个独立 session 的 manifest。论文使用的 10 秒窗口来自随机选取的一小时连续记录，不能作为 40 个独立 benign run。

## 数据划分与泄漏

官方评价在网络与日志聚合后进行分层 80/20 划分。没有证据表明同一攻击执行、相邻窗口或同一捕获不会跨 train/test。论文还提供固定测试床 IP/MAC 与攻击工具清单；若没有 run-level 分组和 shortcut audit，这些信息可能成为场景捷径。

## 1/5/10-shot 结论

当前不能为任一 fine 类证明 15 个独立 U_final run，也不能形成 10 个 support run 与至少 5 个 query run。把一个长 PCAP 的窗口、同一执行的目标组件分片、包或日志行作为 shot 均不合格。因此 1/5/10-shot、U_dev、U_final 与 support/query 隔离均为**正式不可启动，等待作者/归档确认**。

## 缺失的决定性材料

1. 每类独立执行次数及成功/失败记录；
2. run_id/capture_id/scenario_id、开始结束时间、攻击者和目标；
3. PCAP 分段与原始攻击执行之间的多对一/一对一关系；
4. fine 标签到 PCAP、日志和派生窗口的追溯表；
5. Benign 独立 session/capture 清单；
6. 可按 run 构造 K/U_dev/U_final/support/query 的证据。
