# 旧审计复用与缺口闭合

| 事项 | 旧审计状态 | 本轮处理 | 当前结论 |
| --- | --- | --- | --- |
| Data24/Fall24-2及Sum25同周重叠 | 已对6个Parquet做spot check | 扩展到全部50个周文件并复算10对重叠周 | 同周名称不等于逐行副本；但Data22/Fall22前四周存在大规模精确包含，Sum25/Data24家族仍共享环境和日期。 |
| ATT&CK v19.1 ID映射 | 已完成精确external_id映射 | 对全部UWF原始Technique复用同一映射器 | 27个父Technique均为精确活动ID；未观察到Sub-technique。 |
| Flow可观察性 | 已按A/B/C/D提出审计框架 | 对UWF全部27类逐类重评并加入Flow/周组/端口支配门槛 | A/B共5类，4类满足数量/周组；排除T1110单端口捷径后严格可靠类只有3个。 |
| Schema | 仅抽查Data24等6个文件 | 读取六版本全部文件Schema fingerprint | 每个版本内部Schema一致；跨版本为23/25/26/27列四种形态，Data22没有Technique/Binary字段，部分版本增加VLAN/CVE。 |
| 活动边界 | 已确认公开树未暴露mission/activity ID | 保留结论，不重复搜索；新增文件/周/日期/源-日期代理组 | 缺失activity ID仍限制“独立攻击活动”结论，但不再自动否决Flow-shot few-shot。 |
| Few-shot | 旧定义要求独立mission，因此判定NO-GO | 按冻结新定义：shot可为Flow/确定性上下文，support/query按不重叠代理组 | T1018/T1046/T1110/T1595可做1/5/10-shot；T1190/T1210仅C级PARTIAL。 |
| Episode Gate | 旧审计未通过 | 不重跑CasinoLimit/Episode | Episode不再是UWF主任务必要条件；单Flow与past-only上下文即可进入审计。 |
| CPU信号与泄漏 | 未做完整UWF分类探针 | 新增随机/周分组、去端口、标签打乱、版本预测和二分类时间外推 | Technique有信号，但来源捷径很强；结果仅用于数据Gate。 |

## 不再构成NO-GO的旧结论

“没有公开mission/activity ID”不再意味着1/5/10-shot必然不可执行，因为本轮已冻结shot为一条带标签Flow或确定性Flow上下文。可复现的版本+周/文件代理组足以保证support与query不共享同一文件组。旧结论仍然约束论文措辞：这些组不是已验证的独立攻击mission，不能用来声称任务级元学习或独立活动泛化。

## 仍然有效的旧警告

- 先划group，再在split内部清洗、采样和构造past-only上下文。
- IP、绝对时间、文件名、周和版本只可用于分组、审计与消融，不进入正式模型输入。
- Data24/Fall24-2、Sum25-1/Sum25-2不能仅因名称不同而当成独立外部域。
- RAG不能补造Flow中不存在的主机、Payload或攻击成功证据。
- CasinoLimit审计结论未被本轮改写；它仍是MIL弱监督/案例候选，不承担UWF的主监督角色。
