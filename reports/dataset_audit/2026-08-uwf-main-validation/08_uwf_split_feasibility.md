# UWF分组划分可行性

## Group层级

公开数据没有mission/run/scenario或原始PCAP标识。正式优先级冻结为：`版本+原始周文件`（主group）→ `版本+日期`（更细敏感性）→ `版本+日期+源主机`（工程代理）。最后一类只用于诊断，不能称为真实攻击activity。

划分必须先分group，再在各集合内排除Duplicate、采样、拟合编码器和构造past-only上下文。`uid/community_id`、五元组近邻、文件、日期和周不得跨split。原始IP、绝对时间、文件/版本标识不得成为模型特征。

## Task 1

Task 1具备可实施的分组方案：Data24、Fall22、Fall24-2、Sum25-1/2均同时含Benign和Malicious，Sum25-2的2025-05-25周在同一Schema、同一周内同时含689,849条Benign和456,278条T1595，排除了“二类必然来自不同格式”的最坏情况。

建议在正式预处理阶段冻结候选：

- train/validation/internal test均使用完整、不重叠的周文件，且每个集合包含正常组和攻击组；
- Sum25-2 2025-05-25混合周仅作版本/时间外推敏感性，不参与阈值调节；
- 报告按版本、周、日期的性能，并运行去IP/绝对时间/端口和来源预测消融。

由于多数版本的正常和攻击集中在不同周，Task 1判为`GO WITH LIMITATIONS`，不是无条件GO。

## Task 2

27个父Technique中，只有T1018、T1046、T1110、T1595在A/B可观察性和≥3周组、≥100 Flow上达到基础数量门槛；其中T1110几乎完全由目标端口4848决定，严格可靠集合进一步缩为T1018、T1046、T1595三类。

推荐条件性集合：

| 角色 | Technique | 说明 |
| --- | --- | --- |
| `K_known` | T1046、T1595 | 跨版本、跨周且端口不单一；作为最稳核心。 |
| `K_known_secondary` | T1110 | 5周、871,188 Flow，但99.9998%固定端口4848；只在端口消融通过后升级。 |
| `K_pseudo_unknown` | T1018 | B级、30,774 Flow、3周组；只在Fall24-2出现，适合开发期完整留类。 |
| `K_final_unknown` | T1190、T1210 | 分别9/5周组，但均为C级伴随证据；只能形成受限Unknown结论。 |

该集合能构造grouped train/validation/test与完整留类，但达不到“至少5个可靠Known A/B父Technique”的正式确认条件。基础Technique任务判为`GO WITH LIMITED TECHNIQUE COVERAGE`。

## 稳定性限制

Data24五类每周重复出现，适合做周级留出CPU探针，但T1048测试周仅23条、T1078与T1110均存在固定脚本/端口特征；Macro-F1不能直接外推为开放场景性能。正式split必须冻结后再查看测试结果，不得按结果更换周或类别。
