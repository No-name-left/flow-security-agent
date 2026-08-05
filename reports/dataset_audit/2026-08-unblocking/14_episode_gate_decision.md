# Episode Gate决策

| Gate条件 | 状态 | 证据 |
| --- | --- | --- |
| 1. 明确anchor | 未通过 | CasinoLimit候选多义；UWF无公开mission anchor |
| 2. anchor标签可追溯 | 部分 | relation/system label链可追溯，但候选Flow未人工确认 |
| 3. relation规则冻结 | 未通过 | R3+R4可复算，但尚无人审精确率 |
| 4. 同split/同活动context | 未通过 | UWF无活动边界；CasinoLimit活动边界未确认 |
| 5. past-only | 可实现 | 代码规则可限制时间方向，但不足以单独放行 |
| 6. 覆盖与歧义可接受 | 未通过 | relation覆盖33.46%，多义33.03%，唯一0.43% |
| 7. 多Technique污染可测 | 未通过 | 监督单元尚未冻结 |
| 8. supporting Flow可审计 | 部分 | 候选及邻居已输出，但未形成金标准 |
| 9. 不依赖近重复窗口 | 未通过 | 无活动级独立性证据 |
| 10. context增量probe | 未执行 | 前九项未解除，不运行结果驱动probe |

结论：Episode不升级为正式主输入。最低风险的正式候选输入为**Anchor Flow**；若数据补充后仍无可靠Episode，则使用只在split内部构造的固定past-only聚合统计，并保留Single Flow/Anchor Flow强基线。Episode只作为失败分析或未来附加实验。
