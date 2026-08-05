# UWF主数据集最终判定

## Gate结果

| Gate | 判定 | 说明 |
| --- | --- | --- |
| Task 1 | GO WITH LIMITATIONS | 二分类有直接标签、同周混合样本和去泄漏字段CPU信号；仍有强周/版本捷径。 |
| Task 2基础父Technique | GO WITH LIMITED TECHNIQUE COVERAGE | 27类名义覆盖，严格可靠A/B类仅T1018/T1046/T1595三类；不足5类。 |
| grouped split | GO（代理组） | 可按版本+周/文件划分；不是官方activity级split。 |
| held-out Unknown | PARTIAL | T1018可作B级pseudo-unknown；T1190/T1210可作C级final-unknown。 |
| 1-shot | PARTIAL | 推荐类均有非重叠support/query周组，但final类为C级。 |
| 5-shot | PARTIAL | Flow数足够；独立性仅到周/文件代理组。 |
| 10-shot | PARTIAL | T1018/T1046/T1595为GO，T1110/T1190/T1210为受限PARTIAL；不是mission-shot。 |
| 去泄漏字段CPU信号 | 部分通过 | Data24周留出LightGBM Macro-F1 0.8399，去端口0.8126；同时版本预测0.9386，说明真实信号与域捷径并存。 |

## 最终等级

**B. `CONDITIONAL_MAIN_DATASET`。** 未满足`CONFIRMED_MAIN_DATASET`所需的Task 1无条件GO、至少5个可靠Known A/B父Technique、2个额外A/B held-out Unknown以及已验证的activity级独立性。因此不能把UWF写入计划为“已冻结正式主数据集”。

本结论不是`AUXILIARY_ONLY`：UWF确实提供逐Flow父Technique、跨周组和可复算信号，可承担有限覆盖主线的条件性原型。它也不是`REJECTED`：问题集中在标签空间和独立性，而非数据不可读或完全无信号。

## 允许与禁止

- **允许正式预处理：**排除Duplicate、精确ATT&CK映射、统一交集Schema、冻结版本+周group、构造split草案与past-only上下文。
- **允许准备5090环境冒烟：**可以准备环境清单和最小加载/单步测试；当前未租用5090，不得写成已完成。
- **暂不允许正式Qwen SFT：**先通过有限标签范围的人为批准或补齐至少第5个可靠A/B类及2个A/B held-out类，并对冻结split复核来源/端口捷径。

## 从Conditional升级的具体条件

1. 获得UWF官方mission/run映射或等价活动边界，以便把周代理进一步验证为独立活动；
2. 补充至少2个新的A/B Flow可观察父Technique，其中至少1个进入Known、至少2个可完整留作Unknown，且每类具有非重叠support/query组；或明确批准有限三类Known论文范围；
3. 在冻结的完整候选split上重复CPU来源预测、去端口和近重复审计；
4. 人工复核T1110固定端口4848是否来自数据生成脚本，并决定是否只作为捷径案例。

下一步不应继续无目标地下载更多同源Flow，而应优先索取UWF mission metadata/Sub-technique标签，或寻找能补足A/B Technique与独立group的公开Flow标签数据。
