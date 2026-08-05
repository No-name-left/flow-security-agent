# Gotham Dataset 2025

访问日期：2026-08-04

1. **名称、版本、年份：** Gotham Dataset 2025，Zenodo record 14502760，2025。
2. **官方来源和原始论文：** [Zenodo 官方记录](https://doi.org/10.5281/zenodo.14502760)；[原始论文 arXiv:2502.03134](https://arxiv.org/abs/2502.03134)；[作者标签工具仓库](https://github.com/othmbela/gotham-network-packet-labeller)。
3. **是否真实可下载：** 是。Zenodo 提供 23.8 GB 的 GothamDataset2025.zip；本轮未下载。
4. **许可证：** `UNKNOWN`。本轮页面抽取未显示具体 license 值。
5. **网络数据类型：** 78 个仿真 IoT 设备接口处分别捕获的 PCAP；packet-level CSV。
6. **能否只使用网络数据：** 能。
7. **样本单位：** 包、设备接口 capture、攻击事件。
8. **coarse 类别及数量：** 官方/论文分组为 Normal、Brute Force、C&C、DoS、Infection、Network Scanning；即 5 个攻击 coarse。
9. **fine 类别及数量：** 名义上至少 12 个，包括 Mirai/Merlin 多种 flood、scan、CoAP amplification、Telnet brute force、C&C/transfer/download 等阶段。
10. **网络可用 fine 类别估计：** 名义上至少 12；精确去重后的官方 fine 清单为 `UNKNOWN`。
11. **Benign 数据：** 有，且 Zenodo 描述明确包含正常与恶意网络流量。
12. **attack/session/run/capture ID：** 设备 capture 可区分；标签工具使用攻击编排时间和攻击者元数据；独立 attack-run ID 为 `UNKNOWN`。
13. **每个 fine 类的独立 group 数量：** `UNKNOWN`。
14. **是否有重复执行：** `UNKNOWN`；78 个设备 capture 不能视作 78 次独立攻击执行。
15. **标签如何生成：** 脚本化攻击及编排元数据确定攻击时间、攻击者与类型，再映射到 packet CSV。
16. **标签能否落到网络样本：** 能，但同一攻击事件在多个设备接口的副本关系需审计。
17. **是否存在背景流量：** 有 Benign；攻击 capture 内背景范围的精确说明为 `UNKNOWN`。
18. **是否存在 class-specific preprocessing：** `UNKNOWN`。每设备独立捕获与攻击者/设备身份可能形成捷径。
19. **group split 是否可行：** `UNKNOWN`；必须按 attack event 而不是 device file 划分。
20. **K/U 预注册是否可行：** 类别名义上可行，独立 group 证据不足。
21. **near unknown 是否可行：** 名义上可能（同一 DoS/C&C coarse 内 fine 留出），但 group 数为 `UNKNOWN`。
22. **far unknown 是否可行：** 名义上可能，group 数为 `UNKNOWN`。
23. **1-shot 是否可行：** `UNKNOWN`。
24. **5-shot 是否可行：** `UNKNOWN`。
25. **10-shot 是否可行：** `UNKNOWN`；无官方逐类 10+1 独立事件清单。
26. **support/query 是否独立：** `UNKNOWN`。
27. **最大风险：** 分布式设备 capture 记录的是同一网络攻击在不同接口的观测，不得误计为独立 run；设备/攻击者身份也可能泄漏类别。
28. **尚缺证据：** attack-event manifest、逐 fine 重复次数、同一事件跨设备文件映射、精确标签表、license。
29. **Hard Gate 逐项状态：**

| G1 | G2 | G3 | G4 | G5 | G6 | G7 | G8 | G9 | G10 |
|---|---|---|---|---|---|---|---|---|---|
| PASS | PASS | PASS_NOMINAL | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | PASS | UNKNOWN |

30. **最终状态：** `INSUFFICIENT_EVIDENCE`。不能用 78 个设备或 23.8 GB 规模证明独立活动充分。

## 关键证据位置

- Zenodo Overview/Usage：78 个设备接口、每设备 CSV、raw PCAP、23.8 GB 归档。
- 原始论文与作者工具：脚本化攻击、分布式 capture、packet 标签生成。
