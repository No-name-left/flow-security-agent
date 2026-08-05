# CICIoMT2024：独立 Run 与 Few-shot 证据

## Wi-Fi 攻击

官方材料确认 Wi-Fi 攻击包含 ARP Spoofing，DoS/DDoS 的 ICMP、SYN、TCP、UDP Flood，以及 Recon 的 Port Scan、OS Scan、Ping Sweep、Vulnerability Scan。论文使用 4 台 Raspberry Pi 攻击者与 7 台 Wi-Fi 设备，但未报告每个 fine 类的重复执行次数、参数组合数或独立 PCAP 数。

结论：13 个 Wi-Fi fine 类的独立 run 数全部为 `UNKNOWN`。

## MQTT 攻击

官方材料确认 15 个模拟 MQTT 设备，以及 Malformed Data、DoS/DDoS Connect Flood、DoS/DDoS Publish Flood 五个 fine 标签。论文描述了工具和攻击实现，但没有逐类重复次数、run_id 或 capture 边界。

结论：5 个 MQTT fine 类的独立 run 数全部为 `UNKNOWN`。

## BLE 攻击

论文说明 BLE DoS 方法在各 healthcare device 上复现，拓扑包含 14 个 BLE 设备，并单列多台设备的结果。但它未说明每台设备进行了多少次独立执行，也未明确一个 PCAP 是否对应一个设备/一次执行；BLE 捕获链与 Wi-Fi/MQTT 不同，不能把设备数或文件数自动当成同构 run 数。

结论：BLE DoS 的独立 run 数与其在 19-class 标签空间中的位置均为 `UNKNOWN`。

## Benign / Profiling

原始论文明确：Wi-Fi power profiling 为逐设备约 2 分钟启动加 3 分钟余量；10 个适用 BLE 设备有类似 power capture；idle 为两个 13 小时夜间捕获；active 以若干批次累计 26 小时；interaction 分 Physical/LAN/WAN。公开材料未给出这些实验的文件级 manifest 和独立 session 总数，无法证明至少 40 个独立 benign run，也不能确认攻击期间是否持续包含可标注的正常背景流量。

## PCAP、train/test 与 run 的关系

论文只说明按可用 PCAP 文件的 80/20 形成 train/test，之后对“大 PCAP”进行 TCPDUMP 分块。缺少文件树和执行日志时，无法回答：

- 一个原始 PCAP 是否等于一个独立 run；
- 同一次攻击是否被切成多个 PCAP/chunk；
- train/test 是否共享同一连续捕获、设备或参数；
- CSV 是否保留原始 PCAP/chunk 标识。

因此官方 train/test 不能直接认证 G7，现成 CSV 的 10/100 包类相关窗口还构成 G9 风险。

## 1/5/10-shot 结论

逐类 run 数没有 A/B 级证据，无法预注册 K≥10、U_dev≥2、U_final≥4 并满足 20/12/15 run 门槛；也无法证明 U_final 的 10 个 support run 与至少 5 个 query run 相互独立。正式 1/5/10-shot 当前不可行，等待作者或官方 manifest 确认。
