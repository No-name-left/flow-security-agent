# CICIoMT2024

访问日期：2026-08-04

1. **名称、版本、年份：** CICIoMT2024，2024。
2. **官方来源和原始论文：** [UNB CIC 官方页面](https://www.unb.ca/cic/datasets/iomt-dataset-2024.html)；[原始论文 DOI 10.1016/j.iot.2024.101351](https://doi.org/10.1016/j.iot.2024.101351)。
3. **是否真实可下载：** 官方下载入口存在；目录说明包括 Bluetooth、WiFi_and_MQTT、PCAP 和 CSV 的 train/test。未下载大型数据。
4. **许可证：** `UNKNOWN`。论文开放获取不等于数据 license 已确认。
5. **网络数据类型：** 网络 tap 捕获的 PCAP；Wi-Fi/MQTT 提取特征 CSV；Bluetooth PCAP。
6. **能否只使用网络数据：** 能。
7. **样本单位：** PCAP、提取窗口/记录、设备生命周期 profiling capture。
8. **coarse 类别及数量：** Benign + 5 个攻击 coarse：DDoS、DoS、Recon、Spoofing、MQTT。
9. **fine 类别及数量：** 18 个 Wi-Fi/MQTT 攻击 fine；另有 BLE DoS 描述。
10. **网络可用 fine 类别估计：** 18 个 nominal fine 均为网络行为；独立执行充分性另行判断。
11. **Benign 数据：** 有；包括攻击目录中的 benign 和 profiling 的 power/idle/active/interaction。
12. **attack/session/run/capture ID：** 文件/PCAP 层级存在；正式 run/session ID 为 `UNKNOWN`。
13. **每个 fine 类的独立 group 数量：** `UNKNOWN`。
14. **是否有重复执行：** `UNKNOWN`。官方“18 attacks were executed”不能证明每类 11 次独立执行。
15. **标签如何生成：** 攻击类型目录/PCAP 与对应 extracted CSV；更细的逐样本 ground-truth 规则为 `UNKNOWN`。
16. **标签能否落到网络样本：** 名义上可落到对应 PCAP/CSV；攻击 capture 内背景区分规则为 `UNKNOWN`。
17. **是否存在背景流量：** 有独立 benign/profiling；攻击 capture 中并发背景为 `UNKNOWN`。
18. **是否存在 class-specific preprocessing：** 官方特征统计中 `Number` 均值约 9.5、多个统计字段近固定，提示窗口构造需审计；是否类别相关为 `UNKNOWN`。
19. **group split 是否可行：** `UNKNOWN`。官方 train/test 目录不自动等于 activity-disjoint。
20. **K/U 预注册是否可行：** 类别结构名义可行；group 数与隔离证据不足。
21. **near unknown 是否可行：** 名义可行（同一 DoS/DDoS/MQTT coarse 内留 fine）；group 数为 `UNKNOWN`。
22. **far unknown 是否可行：** 名义可行；group 数为 `UNKNOWN`。
23. **1-shot 是否可行：** `UNKNOWN`。
24. **5-shot 是否可行：** `UNKNOWN`。
25. **10-shot 是否可行：** `UNKNOWN`；没有 10 support + 1 query 的官方证据。
26. **support/query 是否独立：** `UNKNOWN`。
27. **最大风险：** 目录中的 train/test 或多个设备 PCAP 可能只是同一攻击执行的切片/目标观测；固定窗口特征还可能引入捷径。
28. **尚缺证据：** 完整文件 manifest、每类 PCAP 数和命名语义、执行时间/run ID、train/test 生成规则、特征提取脚本、license。
29. **Hard Gate 逐项状态：**

| G1 | G2 | G3 | G4 | G5 | G6 | G7 | G8 | G9 | G10 |
|---|---|---|---|---|---|---|---|---|---|
| PASS | UNKNOWN | PASS | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | PASS_PARTIAL | UNKNOWN |

30. **最终状态：** `INSUFFICIENT_EVIDENCE`。名义类别合格，但 G4/G5/G7/G8/G10 尚未得到官方证据。

## 关键证据位置

- 官方页面 Data Description：18 attacks、5 classes、40 devices、PCAP/CSV 与 train/test 目录。
- 官方页面攻击列表：DDoS 4、DoS 4、Recon 4、Spoofing 1、MQTT 5。
- 官方特征统计：`Number` 和多项窗口统计提示需核验提取单位。
