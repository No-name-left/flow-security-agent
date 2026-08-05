# 开放集与few-shot最终可行性

冻结知识来源以MITRE ATT&CK官方数据为准：https://attack.mitre.org/resources/attack-data-and-tools/

## 冻结集合

在“自动连接尚无人审、UWF无公开活动ID”的当前证据下：

- `K_known = ∅`：没有父Technique达到正式SFT监督门槛；
- `K_pseudo_unknown = ∅`：没有可与final-held-out隔离的验证类；
- `K_final_unknown = ∅`：没有同时满足全程不可见、独立support和独立query的类别；
- `K_attribution_only`：CasinoLimit中除历史审查项`T1562`外的65个ATT&CK v19.1可映射ID可进入冻结公共候选库，但不得提供Flow监督或实例细节。

空集合不是永久删除这些Technique，而是防止在证据不足时提前泄漏角色。人工确认或新数据加入后必须重新按同一门槛冻结，不能依据测试效果挑类。

## RAG与few-shot分工

RAG只检索冻结的ATT&CK公开知识，构造Technique语义/Flow可观察证据原型、Top-k候选、不可观察边界和新类原型初始化。它不能生成真实Flow行为，不能替代独立support，也不能修复错误relation。

few-shot的一个shot必须是一项独立instance、mission、run或人工确认活动。当前shot协议不释放；恢复后优先1/3/5-shot。1/5/10-shot只有在每个final类约20个可靠活动且support/query严格分离时才进入主实验。

## 原任务可实施性

`Known分类 → Unknown拒识 → RAG候选 → few-shot接入`在方法上仍合理，但当前数据不满足训练与评价前提。可以先实现无数据依赖的接口、validator和5090冒烟，不可把它们写成正式实验结果。若最终只能确认`T1046`，任务应收缩为单类证据/可观察性案例，而不是继续声称多类开放识别。
