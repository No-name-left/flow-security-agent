# 清理后保留资产

## Git中保留

- `README.md`、`AGENTS.md`、`docs/PROJECT_HANDOFF.md`和三份正式研究计划；
- `docs/SERVER_MIGRATION.md`及`tools/dataset_download/`官方下载/校验工具；
- `src/`、`scripts/`、`tools/dataset_audit/`和全部测试；
- 双数据集Gate报告、JSON manifest、标签Schema、字段白名单、泄漏/可学习性结果和可复现脚本；
- 不含真实流量的`tests/fixtures/canonical_session_record.example.json`。

## 本地但不进入Git

- Edge唯一完整官方ZIP：`data/external/edge_iiotset/edgeiiotset-cyber-security-dataset-of-iot-iiot.zip`，大小`1,746,605,436` bytes，MD5 `d0f9be0185845a1ef4ed31cc6db4a9b2`。目标服务器尚未实际验证重下载，因此保守保留。
- `data/raw/`中的既有NF-ToN资产：不属于本轮Edge/IoT-23清理范围。
- `docs/research_plan/.obsidian/`：用户笔记保留，本轮只通过`.gitignore`排除。
- `reports/dataset_audit/2026-08-unblocking/03_casinolimit_join_results.csv`：历史审计数据表，不属于本轮删除范围，保持忽略状态。
- `.test-tmp/ciciot_deps/`：删除时遇到 Windows `Access Denied`，共 28 个文件、5,075,160 bytes；未提升权限强制删除。
- `.test-tmp/node_modules`：指向Codex共享runtime的junction，按安全规则跳过，不触碰其目标目录。
- `pytest-cache-files-0h_5awb8`和`pytest-cache-files-zdp2mu2w`：严格检查时访问被拒绝，按安全规则跳过且不提升权限强删。

## 恢复入口

- Edge：`python tools/dataset_download/download_edge_iiotset.py --output-root "$EDGE_DATA_ROOT"`；
- IoT-23：`python tools/dataset_download/download_iot23_gate_subset.py --output-root "$IOT23_DATA_ROOT"`；
- 详细服务器目录、环境变量、Gate复跑与Git禁入规则见`docs/SERVER_MIGRATION.md`。
