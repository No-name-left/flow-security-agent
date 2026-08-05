# 正式数据角色决策

## 判定原则

`GO`表示现有证据足以按冻结协议进入相应角色；`CONDITIONAL GO`表示只有完成列明条件后才可进入；`NO-GO`表示不适合当前Flow-only ATT&CK开放识别主任务。角色按数据集分别判定，不因“公开”或“名义Technique多”自动放宽。

| 数据 | 主训练 | 内部测试 | 时间外测 | 独立外测 | Episode/few-shot | 最终判定 |
| --- | --- | --- | --- | --- | --- | --- |
| CasinoLimit | 条件：只用可连接、可观察、非doubt类别 | 可按实例冻结 | 否 | 否 | 条件可用 | CONDITIONAL GO |
| UWF Data24/Fall24-2 | 条件：周/活动分组、去时间捷径；两者不可视为独立域 | 条件可用 | 否 | 不能互为独立外测 | 缺少原生活动ID，需保守构造 | CONDITIONAL GO |
| UWF Sum25-1 | 不进入主训练 | 否 | 条件：仅后续非共享周、已知交集 | 否 | 不作few-shot主数据 | CONDITIONAL GO |
| UWF Sum25-2 | 不单独训练 | 否 | 只作共享周/标签审计 | 否 | 否 | CONDITIONAL GO（辅助） |
| CAM-LDS | 否 | 否 | 否 | 当前否；找到直接NetFlow+标签连接后可重审 | 仅运行级案例候选 | NO-GO（主线） |
| NF-ToN-IoT-v3 | 否 | 否 | 否 | 否 | 否 | NO-GO（本任务） |

## 进入训练前的硬条件

1. CasinoLimit：完成至少跨多个实例的relation窗口连接验证；冻结方向归一、通配IP、端口缺失和时间边界规则；逐Technique报告可连接活动数，而非仅标签存在数。
2. UWF：先按week/capture/连续活动分组，再在split内部构造样本；同周Data24/Fall24-2和Sum25-1/Sum25-2作为同一家族处理；通过时间、来源、IP和端口probe。
3. ATT&CK：只接受v19.1 exact active或人工记录的迁移；`T1562`保持待人工审查；不做字符串模糊匹配。
4. 标签空间：`K_core/K_union/K_fewshot`在连接质量和跨源实际交集确认后重新冻结；当前集合仅供下一轮adapter验证。
5. 模型：Qwen训练只能在数据Gate和RTX 5090冒烟均通过后启动。

## 替代路线

若CasinoLimit连接仍不稳定，则将其降为活动级ATT&CK归因/案例分析，不做逐Flow监督；若UWF时间/类别捷径无法控制，则只保留同源周级检测或描述性漂移实验；若两者都不能形成可信父Technique主任务，应停止大模型训练并重新选择数据或收缩到少量明确网络Technique，而不是用更多Flow行掩盖label unit问题。
