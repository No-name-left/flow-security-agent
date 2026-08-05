# Episode可行性与S0—S5状态

Episode不是数据集原生单位。本轮只检验能否从官方标签和少量Flow重建“锚点+过去相关Flow”，未证明多Flow建模有效。

| 状态 | 含义 | 当前证据 |
| --- | --- | --- |
| S0 Metadata | 官方实例/周/run和标签元数据存在 | CasinoLimit、UWF、CAM均通过 |
| S1 Label mapping | 标签可显式映射到ATT&CK v19.1 | CasinoLimit 65个active exact通过，T1562待人工；UWF direct ID可映射；CAM仅scenario 7样本通过 |
| S2 Activity grouping | 可冻结独立活动group | CasinoLimit instance与UWF week可用作保守上界；细粒度activity仍不足；CAM run可分组但数量不均 |
| S3 Anchor localization | 标签可定位到候选时间/端点关系 | CasinoLimit仅73/114实例有relation；UWF有逐Flow标签但无activity ID；CAM Flow连接未核验 |
| S4 Flow join | 锚点/关系能稳定连接到Flow | CasinoLimit dry-run部分通过：3个relation中2个只在方向归一后命中，1个无命中；其他数据未完成 |
| S5 Leakage-safe sample | 先split、后在集合内构造past-only Episode并通过质量门槛 | 未通过；只能形成实现规范和候选样本 |

## Episode质量门槛

- anchor必须有可审计标签来源和唯一活动归属；不能把窗口内所有Flow自动继承同一Technique。
- context只来自同一split、同一允许活动边界、时间不晚于anchor；记录候选数、命中规则和截断原因。
- 对direction-normalized、IP通配、缺失端口和时间边界分别记录，禁止静默宽松匹配。
- 统计anchor覆盖率、Flow连接率、label purity、背景污染、重复Episode、显著Flow占比和跨group相似度。
- 对Anchor-only、固定窗口统计、随机/打乱context、显著Flow删除和relation-constrained Episode做同数据对照。

当前整体结论为`PARTIAL / CONDITIONAL`。S4和S5未通过前，Stage A/SFT数据构造不得宣称完成。
