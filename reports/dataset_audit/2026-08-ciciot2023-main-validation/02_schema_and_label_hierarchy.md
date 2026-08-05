# Schema与原生标签层级

## 样本语义

论文列出47个统计字段，但CSV样本是固定包数窗口的统计摘要，而不是可唯一还原五元组、方向和持续时间的传统双向Flow。论文的预处理流程对Benign及非大规模攻击使用10包窗口，对DDoS、DoS和Mirai使用100包窗口。该设计必须在模型解释、跨数据集兼容和捷径审计中显式标记。

官方混合CSV没有capture ID、attack-run ID、设备组或原始文件映射。169个`part-*`文件由PySpark合并、随机打散后写出，不能解释为169次独立捕获。

## 原生标签

保留CICIoT2023自身层级，不强行映射MITRE ATT&CK：

- 细粒度：33种攻击加`BenignTraffic`，共34类；
- 粗粒度：Benign、DDoS、DoS、Mirai、Recon、Spoofing、BruteForce、Web，共8类；
- 论文报告总行数46,686,579；逐类数量见`03_class_distribution.csv`。

二级探针实际只出现32类，缺少`DDoS-PSHACK_Flood`和`DDoS-RSTFINFlood`，并仅提供39个数值字段。因此探针不用于确认官方文件完整性，也不据此删除标签。

## 对统一Evidence Card的影响

若作为工程兼容数据接入，Adapter必须声明`sample_semantics=packet_window_summary`、窗口规模来源和缺失的Flow标识字段。模型不得把这些行描述成具备完整五元组或双向会话语义的Flow，也不得由RAG补造未观测信息。
