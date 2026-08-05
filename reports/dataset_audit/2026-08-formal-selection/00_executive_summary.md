# 模型资源与正式数据集选型审查：执行摘要

审查日期：2026-08-03；ATT&CK知识基线：Enterprise ATT&CK v19.1；本轮未启动GPU训练、未下载模型权重、未下载完整PCAP。

## 结论

| 对象 | 决策 | 证据化结论 |
| --- | --- | --- |
| Qwen3.5-9B + RTX 5090 32GB | CONDITIONAL GO | 4-bit QLoRA、BF16计算、单卡微批次1和约2K上下文具有合理可行性；必须先在目标NVIDIA环境完成加载、单步训练、峰值显存和吞吐冒烟测试。全参数微调不可行。 |
| CasinoLimit | CONDITIONAL GO | 适合实例级开放识别、Episode/归因和有限可观察Technique研究；不具备把全部66个标签直接当作Flow分类类别的条件。Flow标签需经`system_labels → event_uid → relations → Flow`间接连接，当前最小试跑只部分成功。 |
| UWF Data24/Fall24-2 | CONDITIONAL GO | 有逐Flow Technique标签和共同Schema，但同周文件来自同环境与同时间窗口，且正常/攻击与时间高度耦合；只能按周/活动分组并控制时间捷径，不能作为两个独立域。 |
| UWF Sum25-1/Sum25-2 | CONDITIONAL GO | 共享四个日历周与环境，不是彼此独立外测；Sum25-1后续周可在冻结协议下作为有限时间外测，且只评价实际覆盖Technique。 |
| CAM-LDS | NO-GO（主Flow训练） | 官方为攻击模拟日志集，34次运行、7个场景、无正常用户模拟；本轮验证了攻击脚本ATT&CK元数据，但未从小样本中确认可直接连接的NetFlow记录与Schema。仅保留后续运行级案例研究候选。 |
| NF-ToN-IoT-v3 | NO-GO（本ATT&CK主任务） | 现有本地审计确认其适合Flow工程与攻击家族任务，但缺少可恢复的ATT&CK活动级Ground Truth。 |

## CasinoLimit标签空间初判

- 114个`system_labels`实例、140个Flow CSV、73个relation文件、9,243条标签记录、66个不同原始Technique ID。
- v19.1中65个ID可自动确认；`T1562`在v19.1中为历史/撤销对象，必须人工决定，不得静默替换。
- 非`doubt`实例支持达到1/5/8/10/15/20的Technique数分别为65/41/37/34/30/24。
- 加入Flow可观察性和relation可连接性后，当前保守`K_core={T1018,T1046}`；`K_fewshot={T1021,T1105,T1572}`。这些集合仍是审计产物，不是最终训练标签。
- `T1595`虽覆盖73个实例，但690条标签全部标记为`doubt`，不能按数量直接进入核心集。

## UWF重叠与捷径初判

Data24与Fall24-2在2024-10-27和2024-11-03两个周目录的时间范围重叠。已下载完整Parquet样本未发现相同UID或完全相同Flow键，只有第一周出现1个相同`community_id`；这支持“并非逐行副本”，不支持“两个独立环境”。Sum25-1和Sum25-2在2025-05-18至06-15共享四周，抽查06-08周同样未发现逐行重合，但应视为同一家族。UWF正常与攻击样本在多个周中几乎被时间切开，随机行划分会产生明显捷径。

## 本轮是否允许进入正式训练

暂不允许。Gate 0只达到“条件通过”：必须先解决CasinoLimit relation-to-Flow连接规则与流向规范、冻结可观察类别；UWF必须冻结周/活动分组并证明任务不由时间或来源预测；CAM-LDS必须先找到直接NetFlow样本和可审计标签连接。未满足这些条件前，不应投入长周期Qwen训练。

完整证据见同目录的模型审查、数据集矩阵、映射表、可观察性表、重叠表、split与dry-run报告。
