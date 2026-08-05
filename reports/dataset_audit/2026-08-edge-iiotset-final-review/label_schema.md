# 标签 Schema 与样本粒度

## 原生标签

原始逐包 CSV 含两个标签列：`Attack_label`（0/1）和 `Attack_type`（细类）。实测 14 个攻击文件各自只含一种攻击且 `Attack_label=1`；10 个正常文件仅含 `Normal` 且 `Attack_label=0`。攻击细类为：Backdoor、DDoS_HTTP、DDoS_ICMP、DDoS_TCP、DDoS_UDP、MITM、OS_Fingerprinting、Password、Port_Scanning、Ransomware、SQL_injection、Uploading、Vulnerability_scanner、XSS。

整理版 ML CSV 将 `OS_Fingerprinting` 写为 `Fingerprinting`；本审查在统计表中统一为 `Fingerprinting`，正式 Schema 必须保留该可追溯映射，不能把二者当成两个类别。

论文和官方说明将攻击组织为五个粗类：

| 粗类 | 细类 |
|---|---|
| DoS/DDoS | DDoS_HTTP、DDoS_ICMP、DDoS_TCP、DDoS_UDP |
| Information Gathering | Fingerprinting、Port_Scanning、Vulnerability_scanner |
| MITM | MITM |
| Injection | SQL_injection、XSS |
| Malware | Backdoor、Password、Ransomware、Uploading |

Normal 是独立背景类。细类及粗类均有明确组织依据，但粗类是由细类确定性映射得到，并非原始 CSV 中的额外列。

## 样本粒度判定

原始 CSV 的 63 个字段以 `frame.time`、地址、协议字段和逐包 Payload/flags 为主，且多数 CSV 行数与配对 PCAP 包数接近，因此一行应解释为 **Wireshark/TShark 风格逐包导出记录**，不是 flow/session。标签逐行存在，但攻击文件本身与类别一一对应；PCAP 中未导出为 CSV 的包造成数量差异，不能按行号直接拼接。

双向会话标签只能在 capture 边界内从文件级/逐包一致标签继承。当前实测未发现单个原始攻击 CSV 内混合 Normal 与攻击，也未发现同一文件中的标签冲突；这反而意味着 capture/文件路径是强标签捷径。正式模型不得使用文件名、capture 名和路径。

各类 ML 行数、原始 CSV 包记录、PCAP 包数和最小探针会话数见 `class_counts.csv`；逐文件标签扫描证据见 `raw_label_probe.json`。
