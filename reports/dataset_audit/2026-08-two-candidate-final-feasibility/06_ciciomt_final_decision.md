# CICIoMT2024 最终决定

**最终状态：`BLOCKED_PENDING_AUTHOR_CONFIRMATION`**

## 判断

CICIoMT2024 具备纯网络 PCAP、5 个 coarse 类和至少 18 个 Wi-Fi/MQTT fine 攻击标签，标签广度达到候选规模；原始 PCAP 也为统一重提 Flow 特征提供了理论基础。但公开材料没有逐类独立执行数、原始文件树或 run/capture manifest。

G3-G5 的 20/12/15 run 数量、G6 的 40 个独立 benign session、G7-G8 的 run 级划分与标签追溯均无法证明。G9 另有明确风险：官方 CSV 对不同类别使用 10 或 100 包窗口，且大 PCAP 会被切分为并行处理 chunk；现有 train/test 文件目录不能证明执行级隔离。G10 也因归档浏览需个人登记且未公开可见许可证/manifest 而未完成。

## 最大阻塞

最大阻塞是**无法确认 PCAP 文件、TCPDUMP chunk 与独立攻击执行的关系，以及逐 fine 类到底有多少独立 run**。这使得 K/U_dev/U_final、support/query 和 Agent 策略开发/最终测试之间的隔离均无法落地。

## 对正式实验的影响

- 不允许据此启动正式 Qwen/SFT/DPO/Agent 实验。
- 不能直接使用官方派生 CSV 作为正式无捷径主数据；若后续解锁归档，需统一重提特征并先完成 run-level audit。
- 若作者确认每类独立执行数低于硬门槛，状态应改为 `FAIL_SINGLE_MAIN_DATASET`；只有完整 A/B 级 manifest 同时满足全部 Gate 时才可重新评估为 PASS。
