# DataSense：官方归档与 Schema 证据

## 官方材料确认的内容

UNB/CIC [官方数据页](https://www.unb.ca/cic/datasets/iiot-dataset-2025.html)和[原始论文](https://doi.org/10.3390/electronics14204095)确认：数据来自 40 台异构设备构成的 IIoT 测试床，网络流量通过交换机端口镜像并由 TShark 连续捕获；MQTT/传感器日志通过 Filebeat 与 Elasticsearch 收集，所有设备统一时区以进行时间对齐。网络与日志是并行归档的数据源，因此概念上可以只保留网络输入，把日志限制为 ground truth 或审计材料。

论文列出 84 个集成特征：前 8 个为日志特征；其余为网络可观察特征，包括包数与方向、端口/协议/IP/MAC 多样性、分片、TCP/IP 标志、包间隔、TTL、窗口大小、包长、头部长度、IP 长度、MSS 和 payload 长度统计。这里的 payload length 是长度统计，不等于读取 payload 内容。

## 标签结构

官方材料明确为 49 个攻击类型、7 个攻击大类，加 Benign 后形成 50-class：

- DDoS 14 类；
- DoS 14 类；
- Recon 9 类；
- Web 5 类；
- Bruteforce 2 类；
- MITM 3 类；
- Malware/Mirai 2 类；
- Benign 1 类。

因此“50”表示 49 个攻击标签加 Benign 的 fine 标签空间，而不是 50 次独立攻击执行。论文虽写有“50 realistic attacks/scenarios”，其方法正文进一步明确为 49 distinct attack types；没有说明每类重复执行了多少次。

## 归档可访问性

官方入口为 `https://cicresearch.ca/IOTDataset/Datasense/`。入口要求提交姓名、邮箱、机构、职位和国家后跳转至文件浏览页。未登记直接访问 `browse.php` 返回 HTTP 403。由于本轮不得伪造信息或绕过访问限制，未取得：

- 官方文件树、归档大小和许可证文本；
- PCAP/CSV/日志文件名；
- README、manifest、schema 或 run/capture ID；
- fine 标签到 PCAP、时间区间和执行记录的映射。

## 官方评价流程的限制

论文说明先将分离的时间戳 PCAP 与传感器日志做时间对齐，再聚合为统一多变量时间序列；之后分别构造二分类、8 类和 50 类数据，并采用**分层 80/20**训练/测试划分。该流程不是 run-aware group split。

Benign 共记录 12 小时，但论文评价只随机选取 1 小时，其中 5 分钟用于设备 profiling，其余被切为互不重叠的 10 秒片段。10 秒片段属于同一长时记录的窗口，不能计为独立 benign session。

## Schema 结论

纯网络版本在字段层面具有可行基础，且至少 DoS、DDoS、Recon、部分 MITM/Bruteforce/Mirai 类具有明确网络行为；但归档级 schema、标签字段、唯一标识和 PCAP→派生记录映射无法从公开材料确认。现阶段只能确认“存在可分离的网络源”，不能确认“存在满足正式 run-level 设计的可用表”。
