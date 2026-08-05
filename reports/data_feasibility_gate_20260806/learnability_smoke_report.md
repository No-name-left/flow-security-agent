# 轻量可学习性冒烟

本结果只用于数据Gate，不是论文成绩。模型均为100棵、最大深度14的Random Forest，使用种子17和41；输入严格来自行为白名单。主可学习性判据使用no-service特征，另保留full-behavior和service-only捷径敏感性探针。

| 数据任务 | 训练/测试 | 类别 | 多数类Macro-F1 | RF Macro-F1均值±标准差 | RF Balanced Accuracy均值 |
|---|---:|---|---:|---:|---:|
| Edge time-block fine-label smoke (no-service primary) | 2338/1574 | Backdoor, DDoS_HTTP, Normal, Port_Scanning | 0.1205 | 0.9498±0.0072 | 0.9379 |
| IoT-23 scenario-held-out behavior smoke (no-service primary) | 2110/2269 | Benign, CommandAndControl | 0.3980 | 0.7328±0.0016 | 0.7911 |
| Edge shortcut sensitivity (full behavior) | 2338/1574 | Backdoor, DDoS_HTTP, Normal, Port_Scanning | 0.1205 | 0.9446±0.0127 | 0.9318 |
| Edge shortcut sensitivity (service-only) | 2338/1574 | Backdoor, DDoS_HTTP, Normal, Port_Scanning | 0.1205 | 0.7926±0.0000 | 0.7950 |
| IoT-23 shortcut sensitivity (full behavior) | 2110/2269 | Benign, CommandAndControl | 0.3980 | 0.7349±0.0023 | 0.7940 |
| IoT-23 shortcut sensitivity (service-only) | 2110/2269 | Benign, CommandAndControl | 0.3980 | 0.2526±0.0000 | 0.4987 |

通过判据是相同非随机划分下明显超过多数类/随机基线，并且不是只依赖总体Accuracy。完整支持数、逐类Recall、混淆矩阵和两个种子结果见`gate_results.json`；预测见`lightweight_model_predictions.csv`。
