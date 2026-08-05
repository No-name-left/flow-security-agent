# CICIoMT2024：官方归档与 Schema 证据

## 官方材料确认的内容

UNB/CIC [官方数据页](https://www.unb.ca/cic/datasets/iomt-dataset-2024.html)、[作者预印本](https://www.preprints.org/manuscript/202402.0898)和[原始论文](https://doi.org/10.1016/j.iot.2024.101351)确认数据来自 40 台 IoMT 设备，覆盖 Wi-Fi、MQTT 与 BLE。Wi-Fi/MQTT 流量由 network tap 捕获；BLE 使用手机与 Ubertooth/snoop log 方案。原始网络数据以 PCAP 保存，Wi-Fi/MQTT 另有派生 CSV。

官方目录说明为：

- `Bluetooth/attacks/{train,test}`：benign 与 attack 原始 PCAP；
- `Bluetooth/profiling`：power profiling PCAP；
- `WiFi_and_MQTT/attacks/{train,test}`：benign/attack PCAP；
- `WiFi_and_MQTT/attacks/csv/{train,test}`：派生 CSV；
- `WiFi_and_MQTT/profiling`：多种 profiling PCAP 及 CSV。

## 标签与协议范围

官方 fine 攻击列表包含 Wi-Fi/MQTT 的 18 类：DDoS 4、DoS 4、Recon 4、ARP Spoofing 1、MQTT 5；另有 BLE DoS 实验。论文的 ML 任务为 19-class（Benign + 18 个 Wi-Fi/MQTT 攻击标签），但公开材料没有明确 BLE DoS 与该 19-class 标签空间的对应关系，因此 BLE 必须单独报告，不能直接当成额外同构 fine 类。

## 派生 Schema 与预处理

作者预印本列出 44 个网络特征，包括 Header Length、Duration、Rate/Srate、TCP flags、协议指示、包长与 IAT、Number、Magnitude、Radius、Covariance、Variance、Weight 和 Protocol Type。公开网页给出的 `Number` 中位数 9.5、`Weight` 中位数 141.55 与论文的窗口设计一致。

论文明确使用两种**类相关包窗口**：Recon、ARP、MQTT malformed、BLE 和 Benign 等使用 10 包窗口；MQTT flood、DoS、DDoS 等使用 100 包窗口。现成 CSV 因而存在由预处理链暴露类别的风险，不适合直接作为无捷径正式主表。理论上可从原始 PCAP 统一重提特征，但前提是先恢复独立 run 和标签边界。

## 归档可访问性

官方入口为 `https://cicresearch.ca/IOTDataset/CICIoMT2024/`。与 DataSense 相同，入口要求个人登记；未登记访问 `browse.php` 返回 HTTP 403。本轮未提交虚构信息，因而没有取得真实文件树、单文件大小、文件哈希、README/manifest 或小型样例。

## 归档结论

PCAP、CSV、train/test 目录的存在由官方材料确认，但“官方已有 train/test”不等于 run 独立。论文说明先将可用 PCAP 文件按 80/20 分组，随后又用 TCPDUMP 把大 PCAP 切成小块以并行提取。没有 manifest 时，文件数、chunk 数和 CSV 数均不能解释为独立执行数。
