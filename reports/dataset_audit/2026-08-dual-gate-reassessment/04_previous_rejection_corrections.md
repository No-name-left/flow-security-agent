# 既有拒绝结论纠正

本表纠正的是**门槛解释**，不是篡改既有证据。此前的 run/group 缺口仍然真实存在，但现在只进入增强门槛。

| 数据集 | 既有结论倾向 | 本轮结论 | 纠正原因 |
| --- | --- | --- | --- |
| CICIoT2023 | 因单次实验、无 run ID、类别特定窗口而接近工程数据/非主线 | PASS_MINIMAL | 33 个有标签网络窗口类、Benign 和足量不同记录足以完成样本级开放识别；上述问题降为增强限制 |
| DataSense 2025 | 因无逐类 20 个独立 run、无 group manifest 而 BLOCKED | PASS_MINIMAL | 最低门槛不要求 20 个独立运行；网络 PCAP 可单独形成场景标注样本，49 类与记录量满足样本级任务 |
| CICIoMT2024 | 因无 11 个独立 group、官方 split 未证明活动隔离而 BLOCKED | PASS_MINIMAL | 18 个网络攻击类及官方 PCAP/CSV 足以做类级 Unknown 和样本级 few-shot；窗口与 group 问题留在增强门槛 |
| X-IIoTID | 因 network-only 可观察性和 run manifest 不明而整体证据不足 | PASS_MINIMAL | 冻结网络可见字段后可开展 18 类场景标注网络记录实验；不能据此声称纯 Flow 能证明所有攻击语义 |
| UWF | 条件性主数据集，因活动边界与可靠 Technique 数量不足而未冻结 | PASS_MINIMAL | 逐 Flow ATT&CK 标签与至少 16 个具备最低 support/query 记录的类别足以支持范围受限的 sample-level 研究 |
| Gotham 2025 | 因设备 capture 不等于独立 run 而证据不足 | PASS_MINIMAL | 最低门槛只要求不同记录和基本副本控制；事件独立性是增强项 |
| GeNIS | 因只有 10 个攻击细类而硬失败 | PASS_MINIMAL_NARROW | 新口径明确允许 8—11 类形成窄范围版本；其 PCAP、Flow、Benign 和计数均足够 |
| NF-ToN-IoT-v3 | 因不是 ATT&CK Technique 主任务、缺少活动分组而 NO-GO | PASS_MINIMAL_NARROW | 对“攻击家族开放识别”而非 ATT&CK Technique 任务，9 类可形成窄范围样本级研究 |

## 没有被“放宽”改变的结论

CasinoLimit 的问题是网络样本无法可靠继承 relation 标签，CAM-LDS 缺 Benign 且 Flow join 未证实，CICAPT-IIoT2024/Multi-Source/Windows-APT 的细粒度语义依赖非网络证据；这些不是 run-level 条件过严造成的，仍应失败。

ISCX Tor、ISCX VPN、APP-53 和 CSTNET 的类别主要是应用、网站、VPN/Tor 或 OTT 签名，不是攻击类别。类别数量再多也不能通过 M2/M3。TQH-C2 则是合法且严谨的网络安全数据，但只有三个恶意标签，仍低于最低类别数。
