# 本地与租用服务器分工

> 历史Phase 2工作流：其中“本地保留完整解压数据并生成训练资产”的安排已由DEC-0010取代。当前执行口径见`docs/SERVER_MIGRATION.md`，正式下载、全量解析和训练资产生成均转移到远程服务器。

## 本地侧

1. 保留官方 ZIP、完整解压 PCAP/CSV、来源和哈希清单。
2. 用双实现复核异常 PCAP及代表性 PCAP/CSV 对齐。
3. 冻结标签 Schema、字段白名单、capture 边界、去重规则和 split manifest。
4. 从 PCAP 重建会话、前 N 包序列和同 split 内 past-only 索引。
5. 运行小规模 CPU 探针、泄漏诊断、卡片格式与 token 抽样。
6. 生成分片 Parquet/JSONL、重建日志和数据卡。

## 服务器侧

1. 部署 Qwen3.5-9B 和训练/推理环境。
2. 执行 QLoRA/SFT、Unknown、Agent、Static 及多随机种子实验。
3. 保存模型、训练日志、推理 trace、成本和失败记录。
4. 将结果 manifest 和必要预测带回本地汇总。

正常情况下服务器**不需要全部原始 PCAP**。应上传：冻结后的会话序列与摘要、标签 Schema、split/support/query manifest、past-only 上下文索引、应用证据索引、源文件 SHA-256 和精确重建脚本版本。仅当服务器端必须重新会话化或检查解析差异时才上传受影响 PCAP 子集。

建议派生数据使用 Parquet 分片（数值/列表）和 JSONL 卡片（LLM 输入）双格式，以 `run_id + source_hash + schema_version + split_version` 标识。任何服务器端重新生成都不得改变 K/U 或 split；差异必须产生新版本，而不是覆盖旧数据。

完整原始数据当前占约 10.48 GiB 解压空间；全量 session 派生估计 2–15 GiB，取决于 Parquet/JSONL 和包序列。正式上传量应通过分层采样和训练集规模冻结后实测，不把本估计当成预算承诺。
