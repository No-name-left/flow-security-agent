# CasinoLimit实例、标签与Flow连接审查

## 1. 资产结构

官方Zenodo记录说明数据来自BreizhCTF 2024的114个游戏实例。`output.zip`实际包含140个Flow验证JSON、114个system label文件和73个relation文件；`labelled_flows.zip`包含140个Flow CSV成员。由此可知“Flow文件数”“系统标签实例数”和“relation可连接实例数”不是同一统计单位。

审计得到9,243条system label记录和66个原始Technique ID。65个可在Enterprise ATT&CK v19.1中exact-active匹配；`T1562`在v19.1中仍有ID但已revoked，标为`EXACT_HISTORICAL_REVIEW`。映射不使用名称模糊匹配。

## 2. 独立实例支持

| 最少实例支持 | 原始Technique数 | 排除全doubt/历史待审后 |
| ---: | ---: | ---: |
| 1 | 66 | 65 |
| 5 | 42 | 41 |
| 8 | 38 | 37 |
| 10 | 35 | 34 |
| 15 | 31 | 30 |
| 20 | 25 | 24 |

这些只是“标签在实例中出现”，不代表可从Flow定位。尤其`T1595`有690条标签、73个实例，但全部`doubt=true`；不能把它计入可靠核心集。逐实例明细见`06_casinolimit_instance_technique_matrix.csv`。

## 3. relation连接与可观察性

relation-linked非doubt实例较多的类别包括：`T1046=58`、`T1082=39`、`T1018=32`、`T1016=12`、`T1021=10`、`T1572=10`、`T1125=7`、`T1105=5`。但`T1082/T1016/T1125`等主机语义不能仅凭Flow确认，即使relation指向一段网络活动，也更适合作为归因上下文而非Flow分类标签。

当前保守集合：

- `K_core = {T1018, T1046}`：非doubt实例≥20、relation可连接实例≥20，且Flow上下文有合理可观察行为。
- `K_fewshot = {T1021, T1105, T1572}`：非doubt实例≥15、至少5个relation可连接实例，证据为部分可观察或关系增强。
- `K_attribution_only`：实例支持较多但核心语义依赖主机/内容，或Flow只能提供伴随证据。
- `K_excluded`：支持不足、完全doubt、历史映射待审或Flow不可观察/不可连接。

完整分类见`10_flow_observability_audit.csv`。这些集合必须在扩大adapter验证后再冻结。

## 4. Flow Schema与质量

抽取的完整CSV字段为：`machine_name,timestamp,duration,src_ip,dst_ip,src_port,dst_port,bytes,packets,protocol,proctitles,labels`。缺少Zeek conn常见的双向字节/包、service、conn_state/history；`bytes/packets`表现为单记录方向。CSV值存在前导空格，需显式`skipinitialspace`或等价规范化。三个样本的`labels`和`proctitles`列未提供可直接使用的逐行Technique标签，因此必须走外部label/relation连接。

140个Flow成员中有26个没有对应system label实例；`harmonie`与`spatial`文件只有表头。正式数据适配器必须保留成员存在、空文件、解析失败和标签缺失状态，不能静默丢弃。

## 5. 结论

114个实例足以支持“按实例分组”的审计与少量Technique实验，但不足以证明66类广覆盖Flow分类可行。当前Gate为`CONDITIONAL GO`：只有relation-to-Flow连接在多实例、多Technique上达到预注册质量后，CasinoLimit才能作为有限父Technique训练源；否则应降为活动级归因或案例数据。
