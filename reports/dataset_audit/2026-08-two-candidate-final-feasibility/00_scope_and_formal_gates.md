# 两候选单一主数据集最终可行性审查：范围与门槛

## 审查目标

本轮只审查 DataSense: CIC IIoT Dataset 2025 与 CICIoMT2024，判断其中是否至少一个能够**单独**承担论文正式主数据，并同时支持网络行为输入、coarse/fine 分类、Known 分类、Development Unknown、Final Unknown、Unknown 拒识、独立活动级 1/5/10-shot、support/query 隔离、无泄漏 group split 和 Adaptive Decision Agent 正式评价。

最终状态只使用：`PASS_SINGLE_MAIN_DATASET`、`FAIL_SINGLE_MAIN_DATASET`、`BLOCKED_PENDING_AUTHOR_CONFIRMATION`。`BLOCKED` 不等于通过，也不授权启动正式 Qwen、SFT、DPO 或 Agent 实验。

## 正式 Gate

| Gate | 最低要求 |
|---|---|
| G1 | 可构造纯网络输入，且至少 16 个 fine 类在网络侧可观察 |
| G2 | Benign + 至少 5 个 coarse + 至少 16 个 fine；可预注册 K≥10、U_dev≥2、U_final≥4（2 near + 2 far） |
| G3 | 每个 K fine 至少 20 个独立 run |
| G4 | 每个 U_dev fine 至少 12 个独立 run |
| G5 | 每个 U_final fine 至少 15 个独立 run，其中 10 个 support、至少 5 个 query |
| G6 | 至少 40 个可区分的独立 benign session/run，覆盖多个时间或环境 |
| G7 | 可恢复 run/capture/session/scenario 标识与 PCAP→CSV 关系，支持无泄漏 group split |
| G8 | attack execution→run/capture→network→label 的可复核链路 |
| G9 | 排除类相关窗口、采样率、IP、设备、协议、路径和同源 train/test 等捷径 |
| G10 | 官方核心文件、标签、metadata 和研究许可实际可获得 |

## 证据规则

A级为官方 manifest、原始文件树、运行日志或明确 run_id；B级为官方 README 或原始论文明确说明重复执行与划分；C级仅为文件名/目录推断；D级为包数、Flow 数、CSV 行数或摘要。正式 PASS 的每个 Gate 必须有 A/B 级证据。C/D 级不得用于证明独立 run 数或 few-shot 可行性。

## 取证边界

- 检索截止时间：2026-08-04（Asia/Shanghai）。
- 仅使用 UNB/CIC 官方页面、原始论文、作者预印本与官方归档入口。
- CIC 下载表单页面可公开访问，但 `browse.php` 在未提交登记信息时返回 HTTP 403。本轮未伪造个人信息、未提交表单、未绕过权限。
- 仅下载 DataSense 的 8,960,775 字节官方论文 PDF 到临时目录进行核验；未下载任何数据归档或大型 PCAP。
- 未运行分类器、Qwen、SFT、DPO、PPO 或 Agent。

## 总体结论

两套数据均没有在当前公开可核验材料中提供逐 fine 类独立 run 数、run/capture manifest、可靠 support/query 隔离和完整标签追溯链。因此本轮没有找到合格的单一主数据集；两者均为 `BLOCKED_PENDING_AUTHOR_CONFIRMATION`。
