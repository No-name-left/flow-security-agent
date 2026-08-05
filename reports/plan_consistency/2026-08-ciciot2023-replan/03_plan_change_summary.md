# 计划变更摘要

1. detailed前部增加可独立阅读的冻结方案概览，成为唯一权威规范。
2. 数据路线由“统一ATT&CK、单库包办”改为“原生标签接口、多数据任务分工”。
3. 写入CICIoT2023 `ENGINEERING_ONLY`结论、窗口构造风险及不能启动SFT的原因。
4. UWF降为可选专项，CasinoLimit停止逐Flow标签挽救；不恢复旧K集合。
5. 固定`K_known/U_dev/U_final`、3 presets×3 seeds和Final信息隔离。
6. 固定Unknown拒识→冻结知识候选→独立活动1/5/10-shot接入三阶段。
7. 将Agent改为Evidence-Decision Tree，定义RulePolicy、LearnablePolicy、A0—A9动作、预算、停止、trace和组件级反馈。
8. 将主实验统一为闭集、开放Agent、few-shot、多数据集四组；普通闭集Accuracy不再作为主要创新。
9. SFT继续受数据Gate约束；DPO条件性，PPO和27B移出最低范围。
10. 时间表以T0数据与协议冻结为起点，删除已否决路线的训练安排。

三份计划没有写入尚未获得的正式模型结果，CPU探针只保留为审计线索。外部镜像需在本目录一致性检查通过后由canonical单向同步。
