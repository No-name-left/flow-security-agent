# 分组划分可行性

## CasinoLimit 8/3/4门槛试验

使用114个system-label实例作为不可拆分group，随机种子`20260803`，第43次确定性搜索找到80/17/17个实例的train/validation/test划分。对24个非doubt且实例支持≥20的Technique，三个集合均满足至少8/3/4个实例。精确实例清单和逐类计数见`13_split_feasibility.json`。

状态为`FEASIBLE_ON_INSTANCE_LABEL_PRESENCE`，而不是“正式split已冻结”。原因如下：

- 标签出现不代表存在可连接Flow；许多类别为D类主机语义。
- 一个实例内可能有多次相关事件，活动边界未必等于instance边界。
- 参与者、共享拓扑、目标主机与固定端口仍可能形成捷径。
- `T1595`全为doubt，未计入可靠集合。

因此下一步应把分组矩阵从“标签存在”升级为“至少一个通过适配器质量门槛的可连接Episode”，再重新执行8/3/4搜索。`K_core`只用两类时可考虑更严格的实例隔离和多seed；`K_fewshot`则需要额外5个support和10个query实例的预留测试，不能与主test重叠。

## UWF与CAM-LDS

UWF只能按week/capture/活动段划分，不能按Flow随机切分；当前没有足够证据构造mission级8/3/4。CAM-LDS有34个run但分布极不均匀（18/2/6/1/1/5/1），且无正常run；很多场景无法同时支持train/validation/test或support/query，因而不具备主训练split条件。
