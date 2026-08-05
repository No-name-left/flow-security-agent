# 清理后验证

## 结果

状态：**COMPLETED_WITH_SAFE_SKIPS**。

- 按清单实际删除`11,839,354,226` bytes、164个普通文件；C盘可用空间由`113,688,387,584`增加到`125,520,523,264` bytes，实测增加`11,832,135,680` bytes（约11.02 GiB）。清单求和与盘符变化的少量差异来自文件系统分配和同期系统活动。
- Edge删除了解压目录、Gate子集、副本归档和重复下载脚本；**没有删除**唯一官方ZIP。
- IoT-23删除了本轮七个官方场景的PCAP、Zeek日志和metadata副本；URL、大小、SHA256、场景与split设计已保留在Git。
- 删除了四个可重建的大型Gate数据输出和十个普通Python缓存目录；报告、manifest、脚本、Schema和合成fixture均保留。

## 安全跳过

- `.test-tmp/ciciot_deps`：删除时遇到访问拒绝，仍保留28个文件、`5,075,160` bytes；未提升权限。
- `.test-tmp/node_modules`：指向Codex共享runtime的junction，未触碰。
- `pytest-cache-files-0h_5awb8`、`pytest-cache-files-zdp2mu2w`：严格检查访问被拒绝，未强删。
- Edge官方完整ZIP：`1,746,605,436` bytes，目标服务器尚未实际验证下载，按保守规则保留。
- `data/raw/`、`.obsidian/`和历史CasinoLimit审计表不属于本轮删除范围，均未删除。

## 完整性复核

- 19个实际删除目标均已验证不存在；所有安全跳过项和Edge归档状态已记录。
- `git fsck --no-dangling`通过；Git HEAD与`origin/main`在首个清理前推送后均为`6d84b40`。
- README、AGENTS、PROJECT_HANDOFF、SERVER_MIGRATION、三份计划、Gate报告/manifest、下载工具和合成fixture均存在且受Git跟踪。
- 40个受Git跟踪的JSON文件可解析。
- 清理后使用`PYTHONDONTWRITEBYTECODE=1`和禁用Pytest cache provider运行完整测试：**24 passed**。
- `git diff --check`通过；清理记录作为第二个逻辑提交单独推送。

本轮未删除源代码、文档、报告或Git文件，未开始正式数据预处理、Qwen训练或论文实验，也未产生GPU费用。
