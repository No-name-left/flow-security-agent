# 条件性计划修改建议（未应用）

本文件只记录在研究范围获得批准或数据Gate升级后应写入canonical计划的内容；当前三份计划保持不变。

1. 将UWF描述为“条件性主监督家族”，明确Data22仅承担Task 1，Data24/Fall24-2/Fall22非重叠周构成父Technique训练池，Sum25承担有限时间敏感性。
2. 冻结两层任务：Task 1 Benign/Malicious；Task 2仅Flow可观察的ATT&CK父Technique。UWF当前没有Sub-technique监督，但保留未来确定性映射接口。
3. 初始候选写为`K_known={T1046,T1595}`、`K_known_secondary={T1110}`、`K_pseudo_unknown={T1018}`、`K_final_unknown={T1190,T1210}`；强调T1110端口捷径和final类C级限制。
4. Few-shot明确为Flow/context shot，support/query按不重叠版本+周/文件代理组；不得称为独立mission-shot。
5. RAG只检索ATT&CK定义、可观察边界和Top-k候选，不替代Flow标签或独立shot。
6. 在Qwen SFT前新增Data Gate：至少5个可靠A/B Known或导师批准有限三类范围；来源预测、去端口和完整group泄漏审计通过。
7. CasinoLimit继续作为MIL弱监督/案例与可观察边界补充，不进入UWF逐Flow主监督。
