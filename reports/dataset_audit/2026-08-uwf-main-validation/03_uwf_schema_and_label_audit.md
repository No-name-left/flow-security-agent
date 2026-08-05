# UWF Schema与标签审计

## 行语义与通用字段

每个Parquet行对应一条Zeek `conn`连接记录，可按论文主线视为一条Flow。六个版本共享连接状态、持续时间、源/目标IP与端口、协议、服务、双向字节/包数、`uid`、`community_id`、`ts/datetime`等核心字段；Fall24-2与Sum25-2额外含`vlan`，Data24及2024/2025版本含`label_cve`。

下列字段只用于分组或审计，不进入正式模型输入：原始IP、绝对时间、`uid`、`community_id`、文件名、周、版本、VLAN和标签字段。端口虽然可以进入主基线，但必须提供删除端口消融。

## 标签字段

| 版本 | 二分类口径 | ATT&CK字段 | 标签类型 | 结论 |
| --- | --- | --- | --- | --- |
| Data22 | `label_tactic=none`为Benign，其余为Malicious | 无`label_technique` | Tactic-only | 不可用于Technique监督。 |
| Data24 | `label_binary`及`label_tactic/technique` | `label_technique` | 父Technique | 5类，逐Flow直接附着。 |
| Fall22 | 同上 | `label_technique` | 父Technique | 22类，但多数极稀疏或Flow不可观察。 |
| Fall24-2 | 同上 | `label_technique` | 父Technique | 9类。 |
| Sum25-1 | 同上 | `label_technique` | 父Technique | 6类。 |
| Sum25-2 | 同上 | `label_technique` | 父Technique | 2类。 |

全家族观察到27个父Technique，所有有效原始标签均以`Tdddd`形式精确映射到Enterprise ATT&CK v19.1；没有任何`Tdddd.ddd` Sub-technique标签，因此Sub-technique数为0。`Unknown`、`Other`不是数据原生标签；`none`表示正常流量。

## Duplicate与标签传播

Data24论文说明标签由mission log中的时间区间、IP和端口与Conn数据连接，允许1分钟slop，再结合STIX补充Technique-to-Tactic关系。一个Technique对应多个Tactic时，公开数据会为同一UID保留一条真实Technique行，并生成若干`label_technique=Duplicate`的重复Tactic行。例如T1078同一UID可出现一条T1078和三条Duplicate。本轮分别发现Data24 18,144、Fall22 3,068、Fall24-2 8,309、Sum25-1 3,532行Duplicate。

正式清洗规则应冻结为：保留原始行用于审计；Task 1/2建模排除`Duplicate`行；只接受正则`^T\d{4}(\.\d{3})?$`的Technique ID；若未来出现Sub-technique，依据ATT&CK v19.1的`subtechnique-of`关系映射父类，不使用名称相似度。

当前公开目录没有mission log、run/scenario/activity ID，也没有逐Flow标签置信度。论文所述29,550条mission log未随当前Parquet下载树公开，因此Flow标签可追溯到公开方法说明，但不能还原每条Flow属于哪一次独立攻击活动。
