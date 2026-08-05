# 本地数据清理计划（2026-08-06）

## 前置条件

- 远程推送已成功：`origin/main`接收提交`6d84b40`。
- 所有目标均已使用`Resolve-Path`解析，位于`flow_security_agent`仓库内，不是仓库根、父目录、`.git`、用户目录或桌面根目录。
- 目标均未被Git跟踪；属性检查未发现symlink、junction或reparse point。
- Edge官方完整ZIP暂不删除；IoT-23有官方逐场景URL和已保存SHA256。
- 删除前可用空间：`113,688,387,584` bytes。

## Dry-run结果

下表为拟删除的精确对象。目录大小按递归普通文件求和；不会使用父目录通配符。

| 数据集/类型 | 精确相对路径 | 类型 | 文件数 | bytes | 恢复依据 | 批准 |
| --- | --- | --- | ---: | ---: | --- | --- |
| Edge-IIoTset | `data/external/edge_iiotset/extracted` | 目录 | 52 | 11,248,814,873 | 保留的官方ZIP、MD5和Edge下载工具 | true |
| Edge-IIoTset | `data/external/edge_iiotset/official_subset` | 目录 | 17 | 356,784,784 | 官方ZIP、Gate source manifest | true |
| Edge-IIoTset | `data/external/edge_iiotset/official_subset_archives` | 目录 | 18 | 62,431,515 | 官方ZIP，可重新抽取 | true |
| IoT-23 | `data/external/iot23/official_subset` | 目录 | 22 | 152,400,120 | CTU官方逐场景URL、SHA256和下载工具 | true |
| Gate输出 | `reports/data_feasibility_gate_20260806/edge_smoke.jsonl` | 文件 | 1 | 8,877,364 | `run_final_gate.py`与checksum manifest | true |
| Gate输出 | `reports/data_feasibility_gate_20260806/iot23_smoke.jsonl` | 文件 | 1 | 6,839,837 | `run_final_gate.py`与checksum manifest | true |
| Gate输出 | `reports/data_feasibility_gate_20260806/qwen_input_samples.jsonl` | 文件 | 1 | 377,036 | `run_final_gate.py`与checksum manifest | true |
| Gate输出 | `reports/data_feasibility_gate_20260806/lightweight_model_predictions.csv` | 文件 | 1 | 2,275,803 | `run_final_gate.py`与checksum manifest | true |
| 重复工具 | `data/external/edge_iiotset/resumable_official_download.py` | 文件 | 1 | 4,038 | 已由Git中的`tools/dataset_download/download_edge_iiotset.py`替代 | true |
| 测试缓存 | `.test-tmp/ciciot_deps` | 目录 | 28 | 5,075,160 | 可由测试环境重建 | true |
| Pytest临时目录 | `pytest-cache-files-0h_5awb8` | 目录 | 0 | 0 | 无长期资产；当前访问被拒绝 | false |
| Pytest临时目录 | `pytest-cache-files-zdp2mu2w` | 目录 | 0 | 0 | 无长期资产；当前访问被拒绝 | false |
| Python缓存 | `reports/data_feasibility_gate_20260806/__pycache__` | 目录 | 1 | 82,110 | Python自动重建 | true |
| Python缓存 | `scripts/__pycache__` | 目录 | 4 | 9,079 | Python自动重建 | true |
| Python缓存 | `src/flowsec/__pycache__` | 目录 | 2 | 5,353 | Python自动重建 | true |
| Python缓存 | `src/flowsec/data/__pycache__` | 目录 | 7 | 60,081 | Python自动重建 | true |
| Python缓存 | `src/flowsec/llm/__pycache__` | 目录 | 6 | 34,301 | Python自动重建 | true |
| Python缓存 | `src/flowsec/rag/__pycache__` | 目录 | 2 | 11,593 | Python自动重建 | true |
| Python缓存 | `tests/__pycache__` | 目录 | 12 | 61,865 | Python自动重建 | true |
| Python缓存 | `tests/data/__pycache__` | 目录 | 8 | 52,794 | Python自动重建 | true |
| Python缓存 | `tools/dataset_audit/__pycache__` | 目录 | 6 | 216,768 | Python自动重建 | true |
| Python缓存 | `tools/dataset_download/__pycache__` | 目录 | 2 | 14,912 | Python自动重建 | true |

预计最多删除`11,844,429,386` bytes（约11.03 GiB）。只有`deletion_plan.json`中`approved_for_deletion: true`且删除前安全复核仍通过的条目会被删除。

实际删除`11,839,354,226` bytes（约11.03 GiB）；`.test-tmp/ciciot_deps/`因 Windows `Access Denied` 未删除，其余批准目标均已完成。磁盘实测可用空间增加`11,832,135,680` bytes。

## 明确不删除

- Edge唯一完整官方ZIP：目标服务器尚未实际验证下载，按保守策略保留。
- `data/raw/`中的NF-ToN等既有数据：不属于本轮Edge/IoT-23清理范围。
- `docs/research_plan/.obsidian/`：用户笔记只忽略，不删除。
- 所有Git源代码、测试、文档、报告、manifest和校验和。
- 历史审计表`reports/dataset_audit/2026-08-unblocking/03_casinolimit_join_results.csv`：不属于本轮删除范围，继续本地保留且不纳入Git。
- `.test-tmp/node_modules`是指向Codex共享runtime的junction；不递归删除`.test-tmp`，仅删除其中已确认不是reparse point的`ciciot_deps`。
- 两个`pytest-cache-files-*`目录在严格解析时返回访问拒绝，按“无法完整确认即跳过”规则保留，不提升权限强删。
