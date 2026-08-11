# 远程服务器迁移与数据恢复

> 当前状态（2026-08-11）：远程服务器初始化、官方数据恢复、Gate复核和Production Data Freeze已完成；Edge paper-grade split/SFT revision已进入本地`main`基线`3f75023f9b40e652de9c5ce1cbd6c00d8b4de5f4`。`feat/production-runtime-adapter`已完成`production_runtime_adapter_v1`、真实v2数据smoke和跨层泄漏/U_final测试，完整回归为254 passed；`PRODUCTION_DATA_READY=true`，尚未下载Qwen、调用真实模型/API或启动训练。

## 1. 已冻结的数据角色

- **Edge-IIoTset：**正式主实验数据集，Gate状态为`PASS_WITH_LIMITATIONS`。用于闭集、Unknown、Agent动态取证、包级证据/RAG和sample-level 1/5/10-shot实验。多数攻击类只有单个capture，因此不得声称跨攻击run泛化。
- **IoT-23：**独立scenario外部验证数据集，Gate状态为`PASS_WITH_LIMITATIONS`。保留原生标签和独立train/validation/scenario-held-out test，不与Edge细类物理合并训练。
- 两者分别解析，通过`CanonicalSessionRecord`统一方法接口。Gate Adapter仍保留为历史验收参考；正式实现位于`src/flowsec/production/`。

正式原始数据位于服务器`/root/autodl-tmp/datasets/`；原始Production Freeze资产位于`/root/autodl-tmp/processed/production_data_freeze_v1/`，其完整报告位于`/root/autodl-tmp/experiments/production_data_freeze_20260809/`。Edge v2 split-dependent资产位于`/root/autodl-tmp/processed/edge_split_revision_v2/`，完整小型运行manifest位于`/root/autodl-tmp/experiments/edge_split_revision_v2/`；它们都在Git仓库外。代码、配置、测试与小型复现报告进入Git。Edge完整归档与解压成员已在服务器逐项验哈希，当前不得擅自删除。

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
- 正式场景：Capture-8、Honeypot-4、Capture-20、Capture-21、Capture-34、Somfy-01、Capture-42，以及按最小必要原则新增的Capture-3。
- 不需要下载20 GB完整归档；工具只下载上述场景的PCAP、官方`conn.log.labeled`及数据集README，并使用`source_download_manifest.json`中已实测的SHA256校验。

```bash
python tools/dataset_download/download_iot23_gate_subset.py --output-root "$IOT23_DATA_ROOT"
```

Capture-42仍只作为6条FileTransfer恶意流的probe，不能单独支撑正式Unknown主结论。正式冻结新增一个官方Capture-3：Reconnaissance/PartOfAHorizontalPortScan作为`U_dev`，Exploitation/Attack作为`U_final`；三份新增文件的URL、大小和SHA256已写入服务器下载manifest。

## 3. 推荐服务器目录与环境变量

建议数据、派生资产、模型与Git仓库分开：

```text
$PROJECT_ROOT/                 Git仓库
$EDGE_DATA_ROOT/               Edge官方归档、解压数据和生产子集
$IOT23_DATA_ROOT/              IoT-23已选scenario目录
$ARTIFACT_ROOT/                manifest、session、split、训练资产和实验输出
$MODEL_ROOT/                   基础模型、LoRA与checkpoint
```

本服务器实际布局：

```bash
export PROJECT_ROOT=/root/autodl-tmp/workspace/flow-security-agent
export EDGE_DATA_ROOT=/root/autodl-tmp/datasets/edge_iiotset
export IOT23_DATA_ROOT=/root/autodl-tmp/datasets/iot23
export ARTIFACT_ROOT=/root/autodl-tmp/processed
export MODEL_ROOT=/root/autodl-tmp/models
export TSHARK_BIN="$(command -v tshark)"
export CAPINFOS_BIN="$(command -v capinfos)"
```

不要把数据根目录设置在Git仓库内；即使误放，`.gitignore`也只是一道防线，不能替代提交前检查。

## 4. 服务器执行顺序

1. **已完成：**clone/pull仓库并确认任务baseline；安装独立Python数据环境、TShark/Capinfos及项目依赖。
2. **已完成：**创建数据/资产/模型目录并确认约600GB数据盘、读写权限与GPU硬件。
3. **已完成：**从官方来源获取Edge和IoT-23数据，校验归档、成员和scenario哈希。
4. **已完成：**以新输出目录复跑最终可行性Gate：

```bash
export FLOWSEC_GATE_OUTPUT="$ARTIFACT_ROOT/data_feasibility_gate_smoke"
python reports/data_feasibility_gate_20260806/run_final_gate.py
```

5. **已完成：**对照Gate记录数、匹配率、泄漏项和随机种子；Gate RF仍只作为数据探针。
6. **已完成：**将Adapter和Canonical schema重构为生产模块，命令入口为`flowsec-production-data`。
7. **已完成：**冻结全量split、K/U、support/query、异常文件处置和training manifest；最终`PASS_WITH_LIMITATIONS`且`PRODUCTION_DATA_READY=true`。
8. **已完成：**Production Data Freeze、Runtime foundation与provider-neutral backend preparation已审查、测试并进入唯一长期`main`基线。
9. **已完成、待短期分支Git冻结：**只重建Edge split-dependent assets，完成paper-grade physical split、Paper Evaluation Readiness、PLAN_A/B/C、PLAN_B SFT候选和label provenance final verification；未重新TShark/canonical/sessionize。
10. **当前下一步：**完成本轮分支冻结后，实现轻量、白名单式Production→Runtime adapter及跨层泄漏测试。真实provider smoke、GPU模型环境、Qwen3.5-9B下载和text-only BF16 LoRA SFT仍须分别获得明确授权；不得从本状态文档直接推导为可执行任务。

现有Gate脚本仍只负责七场景验收，并支持`EDGE_DATA_ROOT`、`IOT23_DATA_ROOT`、`FLOWSEC_GATE_OUTPUT`、`TSHARK_BIN`和`CAPINFOS_BIN`。正式生产CLI默认读取本服务器实际Edge解压根与包含八个场景的IoT-23根；Capture-3的精确恢复URL/hash/size保存在服务器下载manifest和Production Freeze source manifest中。

## 5. Git禁入内容与恢复依据

禁止提交PCAP/PCAPNG、原始或大型CSV、数据集压缩包、大型JSONL/Parquet、模型权重、checkpoint、虚拟环境、日志、缓存、临时下载文件、`.env`、Kaggle凭据、SSH私钥和API Token。提交前必须检查暂存文件大小和敏感信息。

恢复依据保存在：

- `reports/data_feasibility_gate_20260806/source_download_manifest.json`：本轮实际输入的大小与SHA256；
- `reports/data_feasibility_gate_20260806/checksum_manifest.json`：Gate产物校验和；
- `reports/data_feasibility_gate_20260806/split_manifest.json`：最小划分协议；
- `reports/data_feasibility_gate_20260806/run_final_gate.py`：可复现Gate脚本；
- `tools/dataset_download/`：官方数据下载与校验入口。
- `reports/production_data_freeze_20260809/`：正式冻结的小型复现摘要、schema/split/KU/training/audit关键manifest；完整source/统计与Parquet位于上述Git外实验/资产路径。
- `reports/edge_split_revision_v2/`：Edge paper-grade split、Phase A candidates、provenance、readiness、SFT PLAN_B、leakage/sensitivity与low-resource小型报告；完整Parquet保持Git外。

## 6. 2026-08-11服务器状态快照

- Edge官方归档为`1,746,605,436` bytes，MD5 `d0f9be0185845a1ef4ed31cc6db4a9b2`；解压清单为52个成员，其中24个PCAP、26个CSV，24/24 capture provenance通过。
- IoT-23 source manifest共19项且大小/哈希检查无缺失；正式数据角色覆盖8个scenario。
- 原始Production Freeze后台记录数为7,818,954，canonical session为7,569,346；`CLASS_ROLE_SUPPORT_GATE=PASS`、`CAPTURE_PROVENANCE_GATE=PASS`、`POSTFIX_PRECOMMIT_AUDIT=PASS_WITH_LIMITATIONS`。
- Edge v2保留全部7,619,032 stable identity，physical assignment为train 5,294,777、validation 1,073,539、test 1,110,343、quarantine 140,373；v2全部split-dependent canonical/index资产总计7,670,824行（含未改变的IoT-23部分），PLAN_B SFT候选Near/Far/Mixed为16,979/15,895/15,404。
- Production `_state/checkpoints`保留24个Edge和8个IoT checkpoint；checkpoint reuse audit为PASS，已完成capture不需要重新TShark。
- 独立`flow-data`环境为Python 3.11.15；TShark 3.6.2可用，Zeek未安装且当前冻结资产不依赖它。`/root/autodl-tmp/models`为空，没有模型权重；顶层`/root/autodl-tmp/checkpoints`为空。
- 当前服务器HTTPS GitHub push dry-run因没有可读用户名/凭据而失败。不要据此配置PAT、创建SSH key或安装`gh`；现有本地分支和两个bundle继续保留。

尚未完成：本轮短期分支的最终Git冻结、Production→Runtime白名单adapter、正式证据工具、真实provider transport/smoke、Qwen模型环境与下载、原始模型冒烟、BF16 LoRA SFT、正式传统基线、独立Unknown算法/校准和Agent/论文实验。OPTIONAL Low-Resource Unknown Stress Test仅预注册且未执行。`PRODUCTION_DATA_READY=true`不等于模型训练已开始。
