# X-IIoTID

访问日期：2026-08-04

1. **名称、版本、年份：** X-IIoTID，IEEE IoT Journal 2022（DOI 首发 2021）。
2. **官方来源和原始论文：** [作者 GitHub 仓库](https://github.com/Alhawawreh/X-IIoTID)；[原始论文 DOI 10.1109/JIOT.2021.3102056](https://doi.org/10.1109/JIOT.2021.3102056)。
3. **是否真实可下载：** 作者仓库提供 AARNet CloudStor 链接，但仓库不含核心数据文件；本轮未验证该外链的完整下载，记为 `UNKNOWN`。
4. **许可证：** `UNKNOWN`。作者仓库未提供 LICENSE，机构论文记录显示论文本身 All Rights Reserved；二级 Kaggle 许可不作为官方数据许可证据。
5. **网络数据类型：** 网络 traffic/Zeek-derived features，与系统日志、应用日志、设备资源和 OSSEC/Zeek alert 合并为 68 列 CSV。
6. **能否只使用网络数据：** `UNKNOWN`。可抽取网络字段，但部分 fine（malicious insider、crypto-ransomware、文件/进程相关行为）可能失去标签语义。
7. **样本单位：** 汇总 feature record，包含 UID/时间戳和多源字段；独立 run 不是公开样本单位。
8. **coarse 类别及数量：** 9 个攻击 coarse + Benign。
9. **fine 类别及数量：** 18 个攻击 fine + Benign。
10. **网络可用 fine 类别估计：** `UNKNOWN`；名义 18 不等于纯网络可观察 18。
11. **Benign 数据：** 421,417 normal records，跨多个日期采集。
12. **attack/session/run/capture ID：** UID/时间戳存在；run/capture/step manifest 未在官方仓库公开。
13. **每个 fine 类的独立 group 数量：** `UNKNOWN`。
14. **是否有重复执行：** 原始论文说明每个攻击实验在不同时间/日期重复多次，但逐类次数为 `UNKNOWN`。
15. **标签如何生成：** 多源记录通过 UID/时间戳与攻击时间关联，形成 binary、coarse、fine 三层标签。
16. **标签能否落到网络样本：** 对部分攻击可行；对全部 18 fine 的 network-only 落点为 `UNKNOWN`。
17. **是否存在背景流量：** 原始论文示例显示攻击期间混合 normal 与 attack packet patterns；具体每个 fine 的背景为 `UNKNOWN`。
18. **是否存在 class-specific preprocessing：** `UNKNOWN`。
19. **group split 是否可行：** `UNKNOWN`。只有汇总 CSV、UID/时间戳而没有 run manifest，不能保证准确恢复执行边界。
20. **K/U 预注册是否可行：** 类别层次名义可行；独立 group、network-only 可观察性不足。
21. **near unknown 是否可行：** 名义可行；逐类 groups 为 `UNKNOWN`。
22. **far unknown 是否可行：** 名义可行；逐类 groups 为 `UNKNOWN`。
23. **1-shot 是否可行：** `UNKNOWN`。
24. **5-shot 是否可行：** `UNKNOWN`。
25. **10-shot 是否可行：** `UNKNOWN`。论文“repeated multiple times”没有证明每类至少 11 个独立活动。
26. **support/query 是否独立：** `UNKNOWN`。
27. **最大风险：** 汇总 CSV 混合多源与身份字段；没有官方 run manifest 时既可能发生行级泄漏，也无法证明 10+1-shot。
28. **尚缺证据：** 官方可访问核心文件、dataset license、完整 schema、逐类 run/capture 清单、攻击时间边界、网络-only 字段/标签审计。
29. **Hard Gate 逐项状态：**

| G1 | G2 | G3 | G4 | G5 | G6 | G7 | G8 | G9 | G10 |
|---|---|---|---|---|---|---|---|---|---|
| UNKNOWN | PASS_PARTIAL | UNKNOWN_NETWORK_USABLE | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | PASS_PARTIAL | UNKNOWN |

30. **最终状态：** `INSUFFICIENT_EVIDENCE`。论文提供重复执行线索，但不足以判定 G1/G3/G4/G5/G7/G10 通过。

## 关键证据位置

- 作者 README：820,834 records、68 features、三层标签、9 coarse/18 fine、多源特征。
- 原始论文：UID/时间戳关联、多次攻击实验、跨多日期 Benign/attack 采集。
- 作者 dataset_file.txt：仅给出 CloudStor 外链；仓库无 run manifest 或 license。
