# Known/Unknown候选设计

以下仅是标签语义层面的候选压力测试，不是已冻结正式split。每套均含Dev Unknown与Final Unknown，Final至少2个near和2个far；far所属粗类不进入该preset的Known。

| Preset | Dev near | Dev far | Final near | Final far | Known排除粗类 |
| --- | --- | --- | --- | --- | --- |
| A | DoS-HTTP_Flood；DDoS-SlowLoris | SqlInjection；CommandInjection | DDoS-HTTP_Flood；Recon-PingSweep | Backdoor_Malware；XSS | Web |
| B | Mirai-greip_flood；Recon-OSScan | BrowserHijacking；Uploading_Attack | DDoS-ACK_Fragmentation；DoS-SYN_Flood | DNS_Spoofing；MITM-ArpSpoofing | Web、Spoofing |
| C | DDoS-ICMP_Fragmentation；Recon-PortScan | Backdoor_Malware；CommandInjection | DDoS-UDP_Fragmentation；Recon-OSScan | DictionaryBruteForce；Uploading_Attack | BruteForce、Web |

每套正式实验需使用3个数据随机种子，但随机种子只能控制组分配/训练，不能把同一攻击活动拆开。当前缺少group ID，因此三套preset均停留在设计层。

RAG需区分：`known-only frozen RAG`只含Known类别定义；`full frozen RAG`可含全体公开类别知识但在看到测试样本前冻结。两者都不得写入Final Unknown样本、答案或基于最终结果调Prompt。
