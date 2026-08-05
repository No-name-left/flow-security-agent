# IoT23Adapter最小验收

结论：**PASS_WITH_LIMITATIONS**。本轮从官方CTU服务器选择7个capture，没有下载20GB完整包。

| Scenario/capture | 角色 | 官方日志行 | PCAP匹配记录 | 匹配率 | 标签摘要 |
|---|---|---:|---:|---:|---|
| CTU-IoT-Malware-Capture-8-1 | train | 10403 | 10403 | 100.00% | `{"Benign": 2181, "CommandAndControl": 8222}` |
| CTU-IoT-Malware-Capture-20-1 | validation | 3209 | 3209 | 100.00% | `{"Benign": 3193, "CommandAndControl": 16}` |
| CTU-IoT-Malware-Capture-21-1 | validation | 3286 | 3285 | 99.97% | `{"Benign": 3272, "CommandAndControl": 14}` |
| CTU-IoT-Malware-Capture-34-1 | test | 23145 | 23145 | 100.00% | `{"Benign": 1923, "CommandAndControl": 6706, "Reconnaissance": 122, "Availability": 14394}` |
| CTU-IoT-Malware-Capture-42-1 | unknown_final | 4426 | 4426 | 100.00% | `{"FileTransfer": 6, "Benign": 4420}` |
| CTU-Honeypot-Capture-4-1 | train | 452 | 452 | 100.00% | `{"Benign": 452}` |
| CTU-Honeypot-Capture-7-1-Somfy-01 | test | 130 | 106 | 81.54% | `{"Benign": 130}` |

主scenario-held-out行为任务冻结为：Capture-8训练，Capture-20/21验证，Capture-34测试；Philips-Hue加入训练Benign，Somfy-01加入测试Benign。Capture-42整体仅作unknown_final场景，FileDownload类只有6条恶意流，因此Unknown结论必须标记小样本限制。

已实测：Zeek标签可解析，时间戳与五元组可和PCAP匹配；两个Adapter输出同一Schema。IoT-23使用自己的原生行为标签和独立split，不是Edge分类器的直接零样本测试。

解析限制：Capture-42的PCAP被TShark报告为文件尾部截断，但截断前解析结果仍匹配全部4,426条官方日志记录；Somfy-01有24/130条日志未匹配。两项均不阻断本轮Gate，但必须保留在正式source manifest与异常处置清单中。
