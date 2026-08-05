# 尚未解除的明确问题

1. UWF作者能否公开论文所述mission log、run/activity ID或原始capture映射？没有该信息时，周/文件只能是代理group。
2. 公开UWF为何只发布父Technique？是否存在未公开的原始Sub-technique标签及其版本说明？
3. T1110几乎完全绑定目标端口4848是否是实验脚本固有设置？若去端口/跨环境不能维持，应从Known核心移除。
4. 是否接受“有限Technique覆盖”论文范围：T1046/T1595为核心Known，T1110为受限Known，T1018为pseudo-unknown，T1190/T1210为C级final-unknown？若不接受，必须补充新的A/B Flow可观察标签数据。
5. 在正式Qwen SFT前，需对冻结split的所有组执行完整UID/community_id/近邻五元组泄漏检查，并人工抽查Duplicate清洗与标签可观察性。

这些问题不会阻止Schema适配和CPU预处理，但会阻止把UWF写成无条件主数据集以及启动正式长周期SFT。下一步优先补元数据或新增A/B Technique数据，不再重复同一目录的类别计数。
