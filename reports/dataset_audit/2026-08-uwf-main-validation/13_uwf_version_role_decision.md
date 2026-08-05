# UWF版本角色决策

以下角色是条件性方案，不代表主数据集已经冻结。

| version | date_range | technique_count | usable_technique_count | benign_available | overlap_status | train_role | validation_role | internal_test_role | temporal_test_role | exclusion_reason |
| --- | --- | ---: | ---: | --- | --- | --- | --- | --- | --- | --- |
| UWF-ZeekData22 | 2021-12—2022-02 | 0 | 0 | 是 | 与Fall22前四周大规模逐行重叠 | Task 1背景/正常与恶意Flow；不进Task 2 | Task 1可选 | 不作独立Fall22外测 | 否 | 无Technique字段，仅Tactic。 |
| UWF-ZeekData24 | 2024-02—2024-11 | 5 | 2（T1110/T1595，其中T1110受端口限制） | 是 | 与Fall24-2共享两周但无精确Flow重复 | Task 1与受限Technique训练池；Data24五类CPU基线 | 整周留出 | 整周留出 | 否 | 攻击/正常周分离；T1048/T1078/T1110/T1190端口捷径明显。 |
| UWF-ZeekDataFall22 | 2021-12—2022-10 | 22 | 2（T1046/T1595） | 是 | 前四周为Data22近似子集 | 只用不重叠的后期攻击周补充T1046/T1595 | 可选整周 | 不与Data22互作独立测试 | 否 | 多数Technique仅1—10 Flow或为C/D级。 |
| UWF-ZeekDataFall24-2 | 2024-09—2024-12 | 9 | 3（T1018/T1046/T1595） | 是 | 与Data24共享日期/环境 | 主要条件性Technique训练池 | 整周留出 | 整周留出 | 否 | T1018只在该版本出现；后期正常周与攻击周分离。 |
| UWF-ZeekDataSum25-1 | 2025-05—2025-07 | 6 | 2（T1046/T1595） | 是 | 与Sum25-2共享前四周/环境 | 不进入核心阈值拟合 | 否 | 否 | 2025后续非重叠周作有限时间外测 | 后期由T1595扫描主导，许多周无Benign。 |
| UWF-ZeekDataSum25-2 | 2025-05—2025-06 | 2 | 2（T1046/T1595） | 是 | 与Sum25-1共享周，前两周community_id有交集 | 不作为独立训练域 | 否 | 2025-05-25混合周可作Task 1来源敏感性 | 只作有限同环境时间测试 | 不是Sum25-1的独立外部域。 |

多版本联合训练仅允许在以下条件下开展：先按版本+周绑定group；Data22/Fall22精确重叠行只保留一个来源；统一到交集Schema；排除IP/绝对时间/UID/文件/版本/VLAN；每类报告版本和端口支配度。对UWF家族之外的泛化仍需独立公开数据，Sum25不能替代真正外部域。
