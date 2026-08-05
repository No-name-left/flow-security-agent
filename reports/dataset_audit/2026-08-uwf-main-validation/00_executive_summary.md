# UWF作为Flow-only ATT&CK Technique主数据集的最终确认审查

审查日期：2026-08-04。冻结知识版本：MITRE Enterprise ATT&CK v19.1。本轮读取UWF官方公开目录的全部六个版本、50个周级Parquet，共27,111,594行、1.18 GB压缩数据；只运行CPU统计、Logistic Regression与LightGBM小样本探针。

## 最终结论

**UWF最终判定为 `CONDITIONAL_MAIN_DATASET`，尚不能冻结为正式主数据集。** 因此本轮不修改三份canonical研究计划，只给出明确的条件性迁移建议。

| 对象 | 判定 | 依据 |
| --- | --- | --- |
| Task 1：Benign/Malicious | GO WITH LIMITATIONS | 六个版本均可解释正常/恶意；Sum25-2同周同时含两类；去IP、绝对时间和端口后仍有很强CPU信号。但多数版本的正常与攻击集中在不同周，必须做版本/周分组和来源消融。 |
| Task 2：父Technique分类 | GO WITH LIMITED TECHNIQUE COVERAGE | 共观察到27个父Technique、0个Sub-technique。A/B类中T1018、T1046、T1110、T1595达到数量/周组门槛，但T1110的目标端口4848占99.9998%；严格排除单端口捷径后可靠候选只有T1018、T1046、T1595三个，未达到5个的确认门槛。 |
| Unknown拒识 | PARTIAL | 可构造完整留类协议，但建议final-held-out T1190/T1210属于C级伴随证据，结论必须限制为有限Flow证据下的拒识。 |
| 1/5/10-shot | PARTIAL / PARTIAL / PARTIAL | 按“一个shot是一条带标签Flow或确定性上下文”的新定义可执行；support/query使用不重叠的版本+周/文件代理组。缺少官方activity ID，不能声称是独立攻击任务级适配。 |

## 决定性证据

1. Data22公开Parquet只有`label_tactic`，没有逐Flow `label_technique`，只能用于Task 1/背景，不可作为Technique监督源。
2. Data24、Fall22、Fall24-2、Sum25-1/2直接提供`label_technique`；清洗后合计27个父Technique，未观察到任何带点号的Sub-technique ID。
3. 多Tactic记录会产生与原UID重复的`Duplicate`行；审计记录了33,053行此类记录，正式任务必须排除它们，不能把`Duplicate`当作类别。
4. Data22与Fall22前四个重叠周存在20,716、94,240、94,652和129,811个相同UID/精确Flow键，证实二者部分为包含关系，不能当独立域。其他同周版本未发现相同UID/精确Flow键，但仍共享环境与日期。
5. Data24五类CPU探针中，LightGBM从随机行划分Macro-F1 0.8360到周级留出0.8399，去端口后为0.8126；这说明存在Flow信号，但测试最小类仅23条，且固定攻击脚本可能形成捷径，不能作为正式结果。
6. 版本预测探针Macro-F1为0.9386，去端口后仍为0.7832，说明采集域差异明显；任何正式结论都必须报告来源预测和跨版本敏感性。T1110几乎完全绑定端口4848，因此只能作为受限/敏感性类别。

## 下一道明确Gate

允许开始可逆的正式预处理（`Duplicate`清理、ATT&CK精确映射、版本+周分组、去泄漏字段和固定split草案）以及5090环境冒烟准备；**暂不允许启动正式Qwen SFT**。升级为确认主数据集需满足下列之一：

- 获得至少第5个A/B级父Technique，且具有≥3个非重叠周/文件代理组和足够Flow；同时为至少2个A/B held-out类保留独立support/query组；或
- 明确批准把论文范围收缩为3个Known（T1046、T1110、T1595）+1个pseudo-unknown（T1018）+2个C级final-unknown（T1190、T1210）的“有限Technique覆盖”研究，并在标题、结论和评价中承认边界。

优先补充的数据不是更多同源Flow行，而是UWF官方mission/run映射、原始Sub-technique字段，或含新增A/B可观察Technique及独立分组的公开Flow标签数据。

官方来源：<https://datasets.uwf.edu/>；Data24标签机制：<https://www.mdpi.com/2306-5729/10/5/59>；ATT&CK知识：<https://attack.mitre.org/resources/attack-data-and-tools/>。
