# EdgeAdapter最小验收

结论：**PASS_WITH_LIMITATIONS**。本轮使用6个代表性官方PCAP，生成会话、前16包序列、会话摘要和split内60秒past-only上下文。

| Capture | 标签 | PCAP包 | 会话 | 分配结果 | CSV标签稳定 |
|---|---|---:|---:|---|---|
| Normal_Heart_Rate | Normal | 170263 | 10573 | `{"train": 5212, "validation": 1854, "test": 2466}` | True |
| Port_Scanning | Port_Scanning | 21583 | 10908 | `{"train": 5959, "validation": 1640, "test": 2213}` | True |
| DDoS_HTTP | DDoS_HTTP | 229122 | 12145 | `{"train": 4545, "validation": 336, "test": 569}` | True |
| Backdoor | Backdoor | 24590 | 1424 | `{"train": 541, "validation": 43, "test": 664}` | True |
| SQL_Injection | SQL_injection | 51213 | 4433 | `{"unknown_dev": 4433}` | True |
| Ransomware | Ransomware | 10525 | 1364 | `{"unknown_final": 1364}` | True |

已实测：文件级标签在所选CSV内稳定；Known会话按capture内时间块分配，边界gap中的会话被丢弃；Unknown按完整类别隔离；模型视图不含IP、绝对时间、文件名或capture ID。

冻结限制：攻击类通常只有一个capture，因此该划分只支持同采集环境的时间块结论，不支持跨攻击run泛化。Vulnerability Scanner异常PCAP仅由capinfos复核并保留在风险记录，不进入本轮模型冒烟。
