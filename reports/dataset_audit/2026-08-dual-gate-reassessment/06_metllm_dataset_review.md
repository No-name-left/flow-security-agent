# MET-LLM 所用数据集与当前任务的适配性

## 审查结论

MET-LLM 论文中的 ISCX Tor 2016、ISCX VPN 2016、APP-53 2023 和 CSTNET 2023，不能因为被论文用于“malicious encrypted traffic”叙事，就自动成为本项目的细粒度恶意 Flow 开放识别数据集。四者的公开标签语义主要是 Tor/non-Tor、VPN/non-VPN、应用或网站/OTT 签名。

| 数据集 | 公开样本/标签语义 | 最低门槛 | 对当前项目的合理用途 |
| --- | --- | --- | --- |
| ISCX Tor 2016 | PCAP/Flow；Browsing、Email、Chat、Streaming、FTP、VoIP、P2P 等应用类别及 Tor/non-Tor | FAIL_MINIMAL | 加密/匿名流量表征或应用识别基线 |
| ISCX VPN 2016 | PCAP/Flow；14 个 VPN/非 VPN 应用流量类别 | FAIL_MINIMAL | VPN 鲁棒性、应用识别或预训练语料 |
| APP-53 2023 | 53 个移动应用及时间/版本概念漂移 | FAIL_MINIMAL | 应用概念漂移研究；不能当作 53 种攻击 |
| CSTNET | 加密包/会话中的 OTT、网站或应用签名；官方 DOI 元数据未给攻击类表 | FAIL_MINIMAL | 通用加密流量表征参考；不再作为恶意开放识别候选 |

## 对 MET-LLM 结果的解读限制

本地论文给出的样本量和分类结果可以证明其模型处理异构加密流量序列的工程能力，但不能证明这些数据集具备本项目所需的攻击家族标签、Benign/Attack 语义和 Unknown 攻击隔离条件。尤其不能把“Tor”“VPN”“应用名称”直接重新命名为恶意攻击类。

因此，MET-LLM 对本项目更有价值的是输入表示、tokenization、域适配和多数据集评测思路，而不是它选择的四个正式评测数据集。若引用其性能，应明确原任务是加密流量/应用识别，避免把指标与恶意攻击开放识别的 Macro-F1、Unknown AUROC 或 OSCR 直接横向比较。

## 证据说明

- [UNB 官方 Tor 页面](https://www.unb.ca/cic/datasets/tor.html)明确列出七类应用，并说明 Tor 与非 Tor PCAP/Flow 的生成与标注方式。
- [UNB 官方 VPN 页面](https://www.unb.ca/cic/datasets/vpn.html)明确说明 14 个类别来自应用类型与 VPN 状态组合。
- APP-53 的相关论文材料将其用于 53 个移动应用的版本/时间漂移。
- [CSTNET 的 DOI 官方元数据](https://api.datacite.org/dois/10.21227/4394-fv34)将目标描述为 OTT 应用签名识别；没有官方攻击细类清单、Benign 定义或逐类攻击计数。
