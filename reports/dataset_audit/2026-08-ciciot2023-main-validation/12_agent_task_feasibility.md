# 自适应决策Agent任务可行性

## 可观察状态

探索性探针确认存在低margin/高熵、错误高置信、粗细标签冲突、未知分数升高和字段语义异常等状态，可用于开发以下动作的确定性接口：ACCEPT_FINE、BACKOFF_COARSE、EXPAND_CONTEXT、RETRIEVE_KNOWLEDGE、CALL_LLM_EXPERT、REJECT_UNKNOWN、RETURN_TOPK、REQUEST_LABEL、REGISTER_NEW_CLASS、ABSTAIN。

## 评价边界

CICIoT2023当前只能支持**工程级**RulePolicy和轻量LearnablePolicy冒烟：验证动作合法性、预算遵从、失败恢复、输出有效性和trace。它不能提供正式的跨活动任务成功率，因为状态、支持样本和query都无法按独立活动隔离。

Agent的价值不预设为提升分类准确率；应在相同工具、RAG和Reviewer预算下与强Static Pipeline比较任务成功、恢复、预算、延迟和成本。若分类、任务完成和恢复均无增益且成本更高，应结论为Static更合适。该方法论独立于CICIoT2023是否通过主数据集Gate。
