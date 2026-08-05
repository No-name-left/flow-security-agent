# 泄漏与捷径验收

## 已实测结果

- 未来上下文违规：0。
- 模型视图禁止字段键违规：0；原始端点值违规：0。
- IoT-23 scenario跨split：`{}`。
- sample_id、无序双向端点键、完整证据哈希和量化近似特征的跨split结果见`gate_results.json`中的`leakage.split_overlap`。端点键重复只表示通信对复现，不等于同一会话重复；同一会话和完整证据跨split均为0。
- 保守去重：输入76865条，移除35546条，输出41319条；冲突标签证据组全部删除。
- 原始端口仅用于会话/标签对齐；默认模型输入为service category，特征提取代码不含raw port。`learnability`同时保存无service和service-only探针，用于识别服务类别捷径。
- RF的`DictVectorizer`只在训练记录上fit；本轮没有使用测试数据拟合归一化、编码、校准或阈值。

## 解释边界

Edge的同一capture会按冻结协议出现在train/validation/test三个时间块中，但跨块gap内会话被丢弃，且上下文只在split内部生成。这控制直接泄漏但不能提供跨run独立性。IoT-23则要求scenario/capture完全不跨split。

固定URI、topic、用户名、Payload和攻击字符串未进入基础模型视图；应用层能力只以可用性布尔值表示。本轮没有证明所有近重复均已消除，正式数据生成仍需保留近重复敏感性审计。
