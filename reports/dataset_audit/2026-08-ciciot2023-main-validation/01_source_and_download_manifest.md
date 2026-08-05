# 来源与下载清单

## 官方来源

- 数据集主页：<https://www.unb.ca/cic/datasets/iotdataset-2023.html>
- 论文：Neto et al., *CICIoT2023: A Real-Time Dataset and Benchmark for Large-Scale Attacks in IoT Environment*, Sensors 2023，DOI <https://doi.org/10.3390/s23135941>
- 官方页面声明提供PCAP、CSV、示例与补充材料；论文报告105个设备、33种攻击和Benign。

## 本轮实际获取

| 对象 | 状态 | 用途 |
| --- | --- | --- |
| 官方CSV/PCAP压缩包 | 未下载 | 官方下载表单/重定向在本轮访问中未成功；不得写成已核验完整文件 |
| Kaggle镜像目录 | 仅检查元数据 | 可见169个CSV分片及大型资产，但未将其当作官方来源组，也未下载完整库 |
| HF二级镜像`lacg030175/CIC-IoT-2023-raw` | 下载9,600行审计样本 | 仅用于CPU信号、捷径、重复及开放集可触发性探针 |
| PCAP | 未下载 | 本轮严格限界审计不进行完整PCAP重处理 |

二级探针落盘于`data/raw/ciciot2023_audit_probe/`（受Git忽略），Parquet SHA-256为`99c8e90beeb22a710096cf5aa6a3d43bce434347986389fef4dce957b77d408b`。机器可读清单见`probe_download_manifest.json`。网络来源、镜像和随机拆分属性均随结果记录，不允许把二级镜像的数值冒充官方benchmark。
