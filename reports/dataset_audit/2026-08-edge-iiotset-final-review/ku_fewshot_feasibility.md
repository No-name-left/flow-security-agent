# K/U 与 1/5/10-shot 可行性

## 可行部分

作者 ML CSV 的 15 类均有至少 1,001 行；全量 60 秒五元组探针中最少的攻击类也有 215 个会话（Fingerprinting）和 245 个会话（MITM）。因此 class-held-out Unknown 和每类 1/5/10 个 support 的**样本级协议**在数量上可执行。Normal 始终作为 Known 背景，不进入未知攻击集合。

以下三组仅为可复现候选，尚未冻结：

| 候选 | U_dev | U_final | K_known 攻击类（另含 Normal） | 设计含义 |
|---|---|---|---|---|
| Near | Fingerprinting、XSS | DDoS_HTTP、Port_Scanning、SQL_injection、Ransomware | Backdoor、DDoS_ICMP、DDoS_TCP、DDoS_UDP、MITM、Password、Uploading、Vulnerability_scanner | 多数未知类在 Known 中有同粗类近邻 |
| Far | Backdoor、Uploading | MITM、SQL_injection、XSS、Ransomware | 四类 DDoS、Fingerprinting、Password、Port_Scanning、Vulnerability_scanner | U_final 中包含粗类未见或语义跨度更大的类别 |
| Mixed | Fingerprinting、Backdoor | DDoS_HTTP、MITM、XSS、Ransomware | DDoS_ICMP、DDoS_TCP、DDoS_UDP、Password、Port_Scanning、SQL_injection、Uploading、Vulnerability_scanner | 同时包含近邻与远离未知类 |

类别计数见 `class_counts.csv`。上述集合完整覆盖 14 个攻击类，不为凑整牺牲粗类关系；最终仍需根据正式 session 质量和研究问题预注册。

## 关键限制

攻击数据基本是“一类一个 PCAP/攻击活动”。因此：

- `U_final` 整类从训练和开发中隔离是可实现的；
- 1/5/10-shot support 与 query 可以做到 session 不重叠、exact duplicate 不重叠；
- 但 support/query 往往仍来自同一 capture/run，不能声称跨攻击活动泛化；
- Known 类内部也难以同时满足同类多 run 的 train/validation/test 隔离，随机 session 切分会偏乐观。

候选实施原则是先按类别冻结 K/U，再在每个 capture 内按时间块加隔离带构造 sample-level support/query，去重后从 support 固定抽取 1/5/10 个会话；剩余后续时间块作 query。该协议只能缓解相邻包/会话泄漏，不能创造不存在的独立 run。

在未引入第二数据集或额外独立捕获前，本数据集适合回答“受控 class-held-out 和少样本接入是否可执行”，不适合单独支撑“跨场景 few-shot 泛化”的强结论。
