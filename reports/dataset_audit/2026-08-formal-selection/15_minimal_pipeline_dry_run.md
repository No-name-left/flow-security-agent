# 最小数据链路试跑

## 目的与边界

本试跑只验证数据适配链，不训练模型、不计算性能。实例固定为CasinoLimit `ravissant`，链路为：

```text
完整Flow CSV
→ system_labels中的event_uid/Technique
→ relations中的时间、端点与端口
→ Enterprise ATT&CK v19.1 exact mapping
→ 时间窗口候选Flow
→ 有向/方向归一五元组匹配
→ 候选证据样本
```

## 结果

- 物理数据行371,109；成功解析371,105；4行格式异常或被跳过。
- system label 27条、relation 3条。
- 两条`T1570` relation在严格有向匹配下均为0；方向归一后分别命中2和3条候选Flow。
- 一条`T1572` relation在123条时间窗口候选中仍无端点匹配。
- ATT&CK v19.1映射为exact active；未使用名称模糊匹配。

状态：`PARTIAL_PASS_WITH_JOIN_WARNINGS`。这证明元数据链路和候选样本格式可实现，也证明不能假定relation中的方向与Flow行方向一致。零命中可能来自端点通配、地址记录错误、采集方向、Flow文件成员不匹配或标签传播。另一个实例`robotique`还观察到relation地址`10.35.*.20`与Flow地址`10.135.193.20`形式不一致，进一步说明需要显式异常规则和人工抽查。

## 下一步通过条件

在不同Technique、不同relation模式和多个实例上重复；报告严格命中、方向归一命中、零命中、歧义命中和解析失败比例。只有规则在训练/验证数据上预先冻结且测试不再人工修补，才能构造正式Episode。完整机器可读证据见`dry_run_evidence.json`。
