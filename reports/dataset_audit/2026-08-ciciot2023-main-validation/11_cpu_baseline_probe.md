# CPU基线与信号探针

## 范围

数据为二级镜像中每个实际标签200条训练、100条验证，共9,600行；随机划分、无capture隔离。模型为CPU LightGBM、Random Forest和Logistic Regression。目的仅是判断数据是否存在可学习信号、明显捷径和困难状态。

| 任务 | LightGBM Macro-F1 | RF Macro-F1 | LR Macro-F1 |
| --- | ---: | ---: | ---: |
| 二分类 | 0.633 | 0.660 | 0.531 |
| 8个粗类 | 0.708 | 0.694 | 0.572 |
| 32个实际细类 | 0.614 | 0.616 | 0.558 |

细分类LightGBM ECE为0.150，高置信错误率为0.041，说明存在适合校准、拒识、回退与知识调用的困难样本。训练规模从每类25增至200条时Macro-F1由0.529增至0.614，尚未显示饱和。

Preset A探索性MSP未知检测：Known Macro-F1=0.697、未知AUROC=0.799、FPR@95TPR=0.516。该数值只表明未知分数不是完全无信息，高FPR也显示任务并不轻松；不能作为正式开放集结果。

可复现机器结果见`cpu_probe_results.json`，脚本为`tools/dataset_audit/ciciot2023_main_validation.py`。没有运行GPU、Qwen、SFT、DPO或PPO。
