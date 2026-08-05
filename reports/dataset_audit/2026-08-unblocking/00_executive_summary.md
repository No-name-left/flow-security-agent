# 数据集解除阻塞审计：执行摘要

## 结论

当前数据组合判定为 **NO-GO / 数据补充**，尚不能启动正式Qwen SFT。问题不在Flow总量，而在可审计监督单元不足：CasinoLimit的4,865条relation中，自动规则仅覆盖33.46%，且只有0.43%得到唯一候选；UWF论文描述了mission log，但当前公开下载树未提供可用于复算的mission/activity ID。因而目前不能冻结多类别`K_known`、独立`K_final_unknown`或shot协议。

| 关键问题 | 审计结果 | 决策 |
| --- | --- | --- |
| CasinoLimit relation→Flow | 1,628/4,865条relation有候选；21条唯一、1,607条多义、3,237条零命中 | 自动结果只作候选，需人工确认；不得直接训练 |
| Flow解析 | 官方尾部自由文本列存在5,031,034条未转义逗号；连接所需前置字段可完整解析，65,311,400行无跳过 | 只读取命名连接字段并单列数据质量问题 |
| 可训练Technique | `T1046`有33个非doubt且已连接实例的上限，但连接覆盖仍低且未人工确认；其余B/C类不足10个，`T1595`全为doubt | 当前0个正式Known；`T1046`仅保留人工复核候选 |
| UWF活动边界 | 公开Flow带Technique标签，但无公开mission/activity ID；启发式时间簇不能当shot | 可作有限Flow/周级分析，不能承担正式few-shot |
| 跨来源交集 | 名义ID交集8个，语义与Schema概念可比的主要是`T1018/T1046/T1595`；可靠活动级交集为0 | 当前无可冻结`K_core` |
| Episode | 连接、活动边界、歧义与context增量probe均未过Gate | 正式输入降为Anchor Flow或固定past-only聚合 |

## 立即行动边界

- **可继续：**人工复核优先队列；联系数据作者获取CasinoLimit直接映射与UWF mission log；只做候选数据集元数据审查；执行RTX 5090环境加载/单步反传冒烟。
- **暂停：**正式Qwen SFT、DPO/RLAIF、Episode主输入训练、以当前数据声称开放Technique识别或跨来源泛化。
- **数据获取：**完整CasinoLimit labelled Flow已按官方MD5验证，不再重复下载；不下载PCAP、模型权重或全量主机日志。

复算入口为`tools/dataset_audit/unblocking_audit.py`。细节见本目录其余报告和机器可读的`audit_summary.json`。
