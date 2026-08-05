# 证据来源清单

本清单区分“官方元数据/论文”“已完整下载的小型资产”“Range或ZIP成员选择性提取”和“尚未核验”。缓存位于仓库外的`dataset_audit_cache`，避免把原始数据写入Git仓库。

## 官方资料

| 主题 | 主要来源 | 本轮用途 |
| --- | --- | --- |
| Enterprise ATT&CK v19.1 | [MITRE CTI GitHub release](https://github.com/mitre-attack/attack-stix-data/releases/tag/v19.1)与官方STIX | 冻结ID、父子关系、revoked/deprecated状态；STIX SHA256为`bdf1ce86a4e604214c5076d37ae4dcb322678afc528df8492e6fdc1b554f5da3` |
| CasinoLimit | [Zenodo 17256954](https://zenodo.org/records/17256954)、`output.zip`、标签与relation元数据、选择性Flow成员 | 实例数、文件结构、标签支持、Flow Schema、relation连接试跑 |
| UWF | [UWF官方数据页](https://datasets.uwf.edu/)、各数据集Parquet目录及Technique metrics | 周级标签分布、Schema、同周重叠和时间捷径 |
| CAM-LDS | [Zenodo 18390561](https://zenodo.org/records/18390561)、场景ZIP中央目录与`attackmate.json`成员 | 场景/运行数、攻击脚本ATT&CK标签、NetFlow可获得性核验 |
| Qwen3.5-9B | [官方模型仓库](https://huggingface.co/Qwen/Qwen3.5-9B)、config、safetensors index、Transformers实现 | 架构、权重字节数、LoRA目标层静态候选、单卡资源边界 |
| DoLLM | [arXiv 2405.07638](https://arxiv.org/abs/2405.07638) PDF | 模型、训练参数、序列定义和硬件核验 |
| TrafficLLM（通用表示） | [arXiv 2504.04222](https://arxiv.org/abs/2504.04222) PDF | 双阶段P-Tuning、模型规模、资源与划分核验 |
| TrafficLLM（开放集加密流量） | [Computer Networks DOI](https://doi.org/10.1016/j.comnet.2025.111847) | GPT-2/Llama2角色、QLoRA、OpenMax等开放集方法和双4090资源核验 |
| MET-LLM | [ScienceDirect](https://doi.org/10.1016/j.eswa.2025.130621)、[代码仓库](https://github.com/Superagentsys/MET-LLM) | 检查点表述、Tokenizer/DATA、显存与吞吐；仓库当前仅说明，代码待发布 |
| Multi-Source Cybersecurity Logs | [arXiv 2606.18190](https://arxiv.org/abs/2606.18190) PDF | 模型规模、LoRA、session/chunk构造、随机chunk划分与公开性检查 |

## 已触及数据

- 完整下载：CasinoLimit `output.zip`；6个UWF周Parquet；MITRE v19.1 STIX；论文PDF及官方元数据。
- 选择性提取：CasinoLimit 3个Flow CSV成员及ZIP尾部；CAM-LDS scenario 7的`attackmate.json`和ZIP中央目录；未下载完整CAM PCAP。
- 部分下载：CasinoLimit `syslogs_labels.zip`仅为标签结构核验，不作为模型输入。
- 缓存总触及量：324,015,050字节（约0.302 GiB），低于首阶段5 GiB和总量25 GiB限制。

每个本地资产的URL、大小、SHA256、完整性与许可记录见`16_download_manifest.json`。

## 证据等级

1. **已验证：**官方文件完整读取或官方归档中的完整成员已解析。
2. **选择性验证：**只检查官方大文件的中央目录、Range或代表性完整成员，结论不得扩展到未读取部分。
3. **论文报告：**只由论文正文确认，未由代码/数据包复验。
4. **未解决：**官方资产未找到、许可未确认或连接关系尚未通过最小试跑；列入`17_unresolved_questions.md`。
