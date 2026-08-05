# 最终数据角色决策

## 当前冻结角色

| 资产 | 当前角色 | 允许 | 禁止 |
| --- | --- | --- | --- |
| CasinoLimit | 条件性连接研究与人工标注候选；暂非正式训练源 | join规则审计、人工复核、单类可观察性probe | 正式SFT、直接66类监督、未经确认的Episode/few-shot |
| UWF Data24/Fall24-2 | 周级Flow标签与时间/捷径审计候选 | Task 0/有限Technique工程基线、保守week split | mission级shot、活动级Episode、同周数据互称独立域 |
| UWF Sum25-1后续周 | 有限时间漂移候选 | 共同Technique/校准漂移描述性评价 | 完整开放集时间外测、用于调参 |
| UWF Sum25-2 | 重叠审计 | 与Sum25-1核对 | 作为独立训练/测试域 |
| ATT&CK v19.1 | 冻结RAG和归因知识 | 公共Technique定义、证据边界、候选原型 | 数据集实例细节、held-out行为监督 |
| CAM-LDS/其他候选 | metadata-first应急 | 小规模直接Flow连接probe | 未过Gate前进入主训练 |

## 判档

当前为 **NO-GO / 数据补充**：正式Known为0，final-held-out为0，可靠跨源共同Technique为0，UWF无公开细粒度activity，Episode Gate失败。名义上的114个CasinoLimit实例、8个交集ID或数千万Flow都不能替代独立且可定位的监督活动。

若人工复核使`T1046`等至少3—4类成立但仍不足最低门槛，可转为Narrowed Conditional GO，研究Flow可观察性或有限Technique边界；只有至少5个Known、2个final-held-out、1/3/5-shot独立query及一个可信时间/跨源测试成立，才升级Minimum GO。

因此，正式训练时间线暂停在Gate 0。环境和软件冒烟可并行推进，但模型checkpoint不得被描述为论文训练结果。
