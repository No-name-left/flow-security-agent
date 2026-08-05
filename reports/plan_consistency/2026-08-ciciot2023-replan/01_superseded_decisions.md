# 被替代决定与历史保留

本次不静默删除旧路线。权威Decision Log保留DEC-0001至DEC-0003，并新增DEC-0004。

| 旧决定 | 当前处理 | 原因/证据 |
| --- | --- | --- |
| 所有数据统一到ATT&CK父Technique | 已替代 | 标签修复消耗大且非方法创新；改为原生层次Schema兼容 |
| UWF作为唯一正式主数据 | 已替代 | 可可靠观察Technique和独立活动不足；降为专项补充 |
| CasinoLimit作为逐Flow监督来源继续挽救 | 已停止 | relation连接唯一率过低、系统步骤标签不等于Flow标签 |
| 单一数据集承担闭集、Unknown、few-shot和外测全部任务 | 已替代 | 允许不同数据集承担不同任务，但各自实验必须无泄漏 |
| 固定Classifier→RAG→LLM可代表Agent | 已替代 | 新方案要求显式状态、A0—A9动作、预算、停止、Rule/Learnable策略 |
| Unknown在训练后临时隐藏任意类别 | 已替代 | 训练前预注册3套near/far/mixed×3 seeds，U_final严格隔离 |
| few-shot可按Flow行抽样 | 明确禁止 | support/query必须按独立capture/run；否则只算工程实验 |
| CICIoT2023可直接成为主数据 | 经审计否决 | 固定包窗口、无source group、每攻击一次实验；判`ENGINEERING_ONLY` |
| 27B、DPO或PPO为固定主线 | 已降级 | 9B为主；DPO条件性；PPO不属于当前必做 |

替代决定自2026-08-04生效。若未来出现官方activity映射、独立运行或新数据证据，可通过新的Decision Log条目重审，但不能直接回滚文档。
