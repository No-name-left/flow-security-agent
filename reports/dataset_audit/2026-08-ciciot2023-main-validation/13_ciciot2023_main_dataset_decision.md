# CICIoT2023主数据集最终判定

## 决定：ENGINEERING_ONLY

CICIoT2023不进入当前论文的正式主训练、正式known/unknown划分或few-shot最终评价。它可保留用于：

1. 原生34类/8粗类层级的Adapter与输出Schema开发；
2. 窗口构造捷径和标签层级消融；
3. RulePolicy、工具异常恢复和预算约束的工程冒烟；
4. 在论文主结果完成后的非正式兼容性或敏感性补充，并明确随机/来源不隔离限制。

## 为什么不是CONDITIONAL_GO

需要补齐的不是普通清洗或参数选择，而是发布数据中不存在的独立活动身份。论文描述每种攻击只执行一次，使少样本support/query独立性即使恢复文件映射也未必成立。这触及核心科学评价协议，不能用随机行拆分、Spark分片或聚类伪组代替。

## 不受影响的研究设计

- 数据集各自保留原生标签，不强制统一ATT&CK；
- 研究主线仍为结构化证据、Known/Unknown、Tree-aware Qwen Reviewer与自适应决策Agent；
- 3套Unknown preset×3 seeds、known-only/full frozen RAG、1/5/10-shot隔离协议继续作为正式数据集的选择条件；
- SFT必须等主数据集、group split、K/U和信息隔离全部冻结后才可开始；DPO仍为条件性，PPO不作为必需项。

## 重新审查条件

只有获得可审计的窗口—捕获—攻击活动映射、证明目标类拥有足够独立活动，并通过无泄漏划分与few-shot隔离复核后，才可重新评估主数据集角色。
