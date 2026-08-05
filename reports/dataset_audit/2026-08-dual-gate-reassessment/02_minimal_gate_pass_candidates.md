# 最低发表门槛通过候选

## 结论概览

20 个数据集中，6 个达到 `PASS_MINIMAL`，2 个达到 `PASS_MINIMAL_NARROW`，12 个为 `FAIL_MINIMAL`，没有遗留 `UNKNOWN_MINIMAL`。这里的“通过”只表示可以构造可复现的**样本级**已知类训练、类级 Unknown 留出和少样本 support/query；不自动证明跨运行、跨设备或跨环境泛化。

### PASS_MINIMAL（6）

| 数据集 | 最低任务可如何成立 | 必须限制的结论 |
| --- | --- | --- |
| CICIoMT2024 | 18 个网络攻击细类 + Benign；官方 PCAP/CSV；可整类留作 Unknown | 10/100 包窗口与设备/协议捷径须审计；不能宣称 activity-level few-shot |
| DataSense 2025 | 网络 PCAP、49 个攻击场景细类 + Benign；传感器日志不是最低任务的必需输入 | 先核验归档和 Flow 化规则；标签应表述为“场景标注的网络样本” |
| X-IIoTID | 从 68 列中冻结纯网络可见字段，使用 18 个细类和 9 个粗类 | 不使用主机、资源、IDS 与泄漏列；部分标签的纯网络可观察性需单独讨论 |
| UWF | 逐 Flow ATT&CK 父 Technique；16 个标签达到最低 10 support + query 记录条件 | 仅是 sample-level few-shot；版本、周、端口与来源捷径风险很高 |
| Gotham 2025 | 纯网络 PCAP/packet CSV，Benign 与不少于 12 个已计数攻击标签 | 同一攻击在多个设备接口的观测必须去重/分组 |
| CICIoT2023 | 33 类攻击 + Benign，官方固定包数网络统计窗口及逐类计数 | 样本语义必须写成“固定包数、攻击场景来源的网络统计窗口”；窗口大小是强捷径风险 |

### PASS_MINIMAL_NARROW（2）

| 数据集 | 通过原因 | 窄范围原因 |
| --- | --- | --- |
| NF-ToN-IoT-v3 | 9 个攻击类别、Benign、官方精确 Flow 计数，最小类也远超样本级支持需求 | 只有 9 个攻击细类，不达到优选的 12/16 类规模 |
| GeNIS | 10 个攻击细类、Benign、PCAPNG 与 5/10/30/60 秒 Flow；最小类至少 20 条 | 只有 10 个攻击细类和 3 个粗类，适合窄范围论文或先导实验 |

## Unknown 与 few-shot 的最低实现

对上述 8 个候选，`U_final` 必须在类别级冻结，并完全排除于分类器训练、SFT、Prompt 示例、prototype、阈值和 Agent 训练。10-shot 可从训练可见部分抽取 10 条不同记录，query 使用不重复记录；同一条记录、精确重复或派生副本不得跨 support/query。若缺少独立活动 ID，应明确称为 sample-level 10-shot，而不是 independent-event 10-shot。

## 最低门槛未通过者（12）

- 类别数量不足：NF-CSE-CIC-IDS2018-v3（6）、NF-BoT-IoT-v3（4）、TQH-C2（3）。
- 样本—攻击标签关系或 Benign 不成立：CasinoLimit、CAM-LDS。
- Flow-only 不能支撑足够细类：CICAPT-IIoT2024、Multi-Source Cybersecurity Logs、Windows-APT 2025。
- 任务语义不是攻击分类：CSTNET、ISCX Tor 2016、ISCX VPN 2016、APP-53 2023。
