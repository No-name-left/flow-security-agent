# DataSense 最终决定

**最终状态：`BLOCKED_PENDING_AUTHOR_CONFIRMATION`**

## 判断

DataSense 在输入模态和标签广度上很有吸引力：原始网络 PCAP 与同步日志并存，网络字段可独立抽取，49 个攻击 fine 标签覆盖 7 个 coarse 类。但是“标签多”和“包数大”不能证明独立活动足够。

当前公开证据无法确认 G2 中可实际分配的 K/U_dev/U_final、G3-G5 的逐类 run 门槛、G6 的 40 个独立 benign session、G7-G8 的执行级分组与追溯、G9 的无捷径重建，也无法在不提交登记信息的情况下核验 G10 的核心文件与许可证。官方分层 80/20 评价和 10 秒 benign 窗口不能替代这些要求。

## 最大阻塞

最大阻塞是**缺少逐 fine 类独立执行清单与 PCAP→run→label manifest**。只要这一材料未取得，不能判断是否满足每个 K 类 20 run、U_dev 12 run、U_final 15 run，也不能合法构造 1/5/10-shot。

## 对正式实验的影响

- 不允许据此启动正式 Qwen/SFT/DPO/Agent 实验。
- 可以保留为作者确认后的候选，但不能把其当前 50-class 随机/分层结果视为项目的正式无泄漏基线。
- 若作者确认多数 fine 类只有一次场景执行，状态应改为 `FAIL_SINGLE_MAIN_DATASET`；若提供满足全部 Gate 的 A/B 级 manifest，才可重新审查为 PASS。
