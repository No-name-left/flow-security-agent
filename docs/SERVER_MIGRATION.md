# 远程服务器迁移与数据恢复

> 当前状态（2026-08-09）：远程服务器已经租用并可通过VS Code SSH访问，数据盘约600GB；尚未在服务器clone/pull仓库、初始化目录、确认GPU、下载正式数据或配置Qwen。当前唯一阶段为`SERVER INITIALIZATION`。

## 1. 已冻结的数据角色

- **Edge-IIoTset：**正式主实验数据集，Gate状态为`PASS_WITH_LIMITATIONS`。用于闭集、Unknown、Agent动态取证、包级证据/RAG和sample-level 1/5/10-shot实验。多数攻击类只有单个capture，因此不得声称跨攻击run泛化。
- **IoT-23：**独立scenario外部验证数据集，Gate状态为`PASS_WITH_LIMITATIONS`。保留原生标签和独立train/validation/scenario-held-out test，不与Edge细类物理合并训练。
- 两者分别解析，通过`CanonicalSessionRecord`统一方法接口。当前Gate Adapter是可复现原型，不是生产流水线。

本地不再保留可重建的解压PCAP/CSV、IoT-23场景副本和大型冒烟JSONL/预测表。代码、测试、报告、manifest、哈希和下载工具进入Git。由于尚未在目标服务器实际验证Kaggle下载，唯一一份Edge官方完整压缩包暂时保留；服务器验证成功后再单独决定是否删除。

## 2. 官方来源与校验

### Edge-IIoTset

- 官方发布页：`https://www.kaggle.com/datasets/mohamedamineferrag/edgeiiotset-cyber-security-dataset-of-iot-iiot`
- 下载API：`https://www.kaggle.com/api/v1/datasets/download/mohamedamineferrag/edgeiiotset-cyber-security-dataset-of-iot-iiot`
- 归档文件：`edgeiiotset-cyber-security-dataset-of-iot-iiot.zip`
- 文件大小：`1,746,605,436` bytes
- 官方归档MD5：`d0f9be0185845a1ef4ed31cc6db4a9b2`

下载工具支持断点续传、大小检查和MD5校验：

```bash
python tools/dataset_download/download_edge_iiotset.py --output-root "$EDGE_DATA_ROOT"
```

### IoT-23

- 官方数据目录：`https://mcfp.felk.cvut.cz/publicDatasets/IoT-23-Dataset/`
- 当前Gate场景：Capture-8、Honeypot-4、Capture-20、Capture-21、Capture-34、Somfy-01、Capture-42。
- 不需要下载20 GB完整归档；工具只下载上述场景的PCAP、官方`conn.log.labeled`及数据集README，并使用`source_download_manifest.json`中已实测的SHA256校验。

```bash
python tools/dataset_download/download_iot23_gate_subset.py --output-root "$IOT23_DATA_ROOT"
```

当前Capture-42只有6条FileDownload未知恶意流，不能单独支撑正式Unknown主结论。生产manifest冻结前须补充少量官方scenario，或预注册小样本置信区间与结论边界。

## 3. 推荐服务器目录与环境变量

建议数据、派生资产、模型与Git仓库分开：

```text
$PROJECT_ROOT/                 Git仓库
$EDGE_DATA_ROOT/               Edge官方归档、解压数据和生产子集
$IOT23_DATA_ROOT/              IoT-23已选scenario目录
$ARTIFACT_ROOT/                manifest、session、split、训练资产和实验输出
$MODEL_ROOT/                   基础模型、LoRA与checkpoint
```

示例：

```bash
export PROJECT_ROOT=/workspace/flow_security_agent
export EDGE_DATA_ROOT=/data/flowsec/edge_iiotset
export IOT23_DATA_ROOT=/data/flowsec/iot23/official_subset
export ARTIFACT_ROOT=/data/flowsec/artifacts
export MODEL_ROOT=/data/flowsec/models
export TSHARK_BIN="$(command -v tshark)"
export CAPINFOS_BIN="$(command -v capinfos)"
```

不要把数据根目录设置在Git仓库内；即使误放，`.gitignore`也只是一道防线，不能替代提交前检查。

## 4. 服务器执行顺序

1. 在已租用服务器clone/pull仓库并确认本地`main`与远程哈希一致；安装Python 3.11、TShark/Capinfos及项目依赖。
2. 创建上述数据、资产和模型目录，确认约600GB数据盘的挂载点、磁盘空间、读写权限与GPU硬件；具体路径和硬件写入后续环境manifest，不写死进研究计划。
3. 使用两个下载工具从官方来源获取数据并完成哈希验证。
4. 以新的输出目录复跑最终可行性Gate，验证服务器解析环境：

```bash
export FLOWSEC_GATE_OUTPUT="$ARTIFACT_ROOT/data_feasibility_gate_smoke"
python reports/data_feasibility_gate_20260806/run_final_gate.py
```

5. 对照`reports/data_feasibility_gate_20260806/gate_results.json`、`dataset_manifest.json`和`split_manifest.json`检查记录数、匹配率、泄漏项和随机种子。Gate RF仅为数据探针，不得写成论文结果。
6. 将Gate中的`EdgeAdapter`、`IoT23Adapter`和`CanonicalSessionRecord`重构进生产模块；当前尚无可声称存在的Production Adapter命令入口。
7. 生产Adapter通过回归后，冻结全量split、K/U、support/query、异常文件处置和训练manifest。
8. 最后配置GPU模型环境，加载Qwen3.5-9B post-trained模型并运行text-only BF16 LoRA SFT小规模冒烟：冻结视觉编码器和多模态对齐模块，使用non-thinking/direct-response。QLoRA仅在显存不足或框架兼容性受限时作为降级路线；不得跳过数据冻结直接训练。

现有Gate脚本已支持`EDGE_DATA_ROOT`、`IOT23_DATA_ROOT`、`FLOWSEC_GATE_OUTPUT`、`TSHARK_BIN`和`CAPINFOS_BIN`。Edge根目录应包含`official_subset/`和`extracted/Edge-IIoTset dataset/`；IoT-23根目录直接指向七个场景所在的`official_subset`。

## 5. Git禁入内容与恢复依据

禁止提交PCAP/PCAPNG、原始或大型CSV、数据集压缩包、大型JSONL/Parquet、模型权重、checkpoint、虚拟环境、日志、缓存、临时下载文件、`.env`、Kaggle凭据、SSH私钥和API Token。提交前必须检查暂存文件大小和敏感信息。

恢复依据保存在：

- `reports/data_feasibility_gate_20260806/source_download_manifest.json`：本轮实际输入的大小与SHA256；
- `reports/data_feasibility_gate_20260806/checksum_manifest.json`：Gate产物校验和；
- `reports/data_feasibility_gate_20260806/split_manifest.json`：最小划分协议；
- `reports/data_feasibility_gate_20260806/run_final_gate.py`：可复现Gate脚本；
- `tools/dataset_download/`：官方数据下载与校验入口。

尚未完成的事项包括服务器Git/目录/硬件与数据环境初始化、正式数据下载和Gate复核、生产Adapter、全量manifest与K/U冻结、Qwen模型配置与下载、正式传统基线、BF16 LoRA SFT、独立Unknown算法/校准和Agent/论文实验；服务器已租用不等于这些工作已经开始。
