# UWF Unknown拒识可行性

## 冻结协议

一个held-out父Technique必须从训练、验证、阈值拟合、Prompt示例、SFT/DPO样本和模型选择中完全移除。冻结的ATT&CK v19.1公共知识可以保留在RAG库中，但不能包含测试Flow、样本统计或数据集特定实例。测试只判断Known/Unknown；RAG的Top-k候选另行评价，不反向改变真实标签。

## 推荐条件性集合

- `K_known={T1046,T1595}`；T1110仅列`known_secondary`，因为几乎完全固定端口4848。
- `K_pseudo_unknown={T1018}`：B级可观察、3个周/文件代理组，可用于开发拒识阈值但不参与最终选择。
- `K_final_unknown={T1190,T1210}`：分别4,660/366 Flow、9/5周组，能够完整留类并保留独立support/query；但二者为C级，只能提供伴随网络证据。

若论文必须坚持至少3个Known，可暂将T1110纳入，并把“有端口/无端口”作为强制双口径；若无端口结果不能维持，则回退到两类核心，不得用Flow数量掩盖捷径。

## 判定

Unknown拒识为`PARTIAL`。流程和group隔离可以实现，但当前没有同时满足“至少5个可靠Known A/B”与“至少2个额外A/B final-held-out”的标签空间。T1190/T1210可作为受限final未知类，用于研究拒识风险和RAG候选，不宜声称已解决一般ATT&CK Technique开放识别。

RAG在该协议中只提供Technique定义、协议/行为知识、Flow可观察边界与文本原型。UWF原始ID与ATT&CK v19.1可精确对齐，因此知识连接可实施；但UWF没有Sub-technique标签，RAG不能制造细粒度监督。
