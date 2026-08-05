# 最终设计快照（2026-08-04）

```text
原生标签Flow数据 + 可审计source group
→ DatasetLabelSchema（不统一类别名称）
→ group-disjoint split + 3套K/U预注册×3 seeds
→ LightGBM/XGBoost + group-aware OOF概率
→ Evidence Card（Flow/因果上下文/树概率/不确定性/缺失字段）
→ RulePolicy / LearnablePolicy Evidence-Decision Tree
   ├─ 接受fine或退回coarse
   ├─ 扩展past-only context
   ├─ 按需known-only RAG / Qwen Reviewer
   ├─ 拒识Unknown / abstain
   └─ 拒识后full-frozen候选 → 1/5/10-shot → 注册新类
→ 分类、Unknown、遗忘、任务成功、恢复、预算、延迟与成本评价
```

数据角色：CICIoT2023=`ENGINEERING_ONLY`；UWF=可选ATT&CK/Flow补充；CasinoLimit=历史连接案例；正式主数据与第二复现数据待限界Gate。

模型边界：Qwen3.5-9B QLoRA-SFT是Gate后主Reviewer；27B可选；DPO条件性；PPO非必做。当前未批准正式Qwen训练。

实验编号固定为：实验一闭集能力边界；实验二开放集与自适应决策；实验三1/5/10-shot接入；实验四多数据集原生标签兼容。
