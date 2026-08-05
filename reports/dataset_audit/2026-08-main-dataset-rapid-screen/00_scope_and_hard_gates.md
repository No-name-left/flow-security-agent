# 正式主数据集快速筛查：范围与硬门槛

## 目的与边界

本轮于 2026-08-04 对 8 个种子候选进行 metadata-first 快速筛查，只判断其是否值得进入完整数据审计。筛查保持现有论文路线不变：网络行为为主要输入、数据集原生 coarse/fine 标签、Known/Development Unknown/Final Unknown 预注册、Unknown 拒识、独立活动级 1/5/10-shot、新类 support/query 隔离、无泄漏 group split 和自适应决策 Agent。

本轮没有下载完整 PCAP、完整数据归档或大文件，没有运行分类器、GPU、Qwen、SFT、DPO、PPO 或 Agent 实验。结论仅来自官方数据页、官方仓库、原始论文及其明确公开的元数据。所有未被官方证据确认的事实均记为 `UNKNOWN`，不将 CSV 行数、包数、Flow 数、设备数或同一攻击的文件分片当作独立活动数。

## 状态规则

| 状态 | 含义 |
|---|---|
| `PASS_TO_FULL_AUDIT` | G1–G10 均通过，或有充分官方证据表明可在完整审计中直接验证通过 |
| `FAIL_HARD_GATE` | 至少一项硬门槛已被官方证据确认失败 |
| `INSUFFICIENT_EVIDENCE` | 尚无确认失败，但缺少足以判为通过的官方证据；`UNKNOWN` 不等于通过 |

## G1–G10 冻结口径

| Gate | 快速筛查要求 | 常见误判 |
|---|---|---|
| G1 | 主要模型输入可由 PCAP、Flow、Zeek、NetFlow、会话或网络 Episode 构成 | 用主机、浏览器、传感器或 provenance 作为识别标签不可缺少的输入 |
| G2 | attack/scenario/run/step 可追溯到 capture/session，再落到网络样本或 Episode | 只按文件名或宽时间窗广播标签 |
| G3 | Benign + 至少 5 个可用 coarse 攻击类 + 至少 12 个网络可用 fine 攻击类 | 只数论文中名义出现的攻击名称 |
| G4 | 每个主要 Known 类至少 3 个可恢复的独立 run/session/capture/episode | 把同一执行产生的大量 Flow 当成多个独立组 |
| G5 | few-shot 类至少 10 个独立 support group + 1 个独立 query group | 把同一 PCAP 的不同 Flow/窗口当作不同 shot |
| G6 | 训练前可冻结 K_known、至少 2 个 U_dev、至少 4 个 U_final（2 near + 2 far） | 训练后按结果挑 Unknown |
| G7 | Known train/val/test、U_dev、U_final support/query 能按真实活动完全隔离 | 默认官方随机 train/test 无泄漏 |
| G8 | 不存在不可消除的类别相关窗口、采样、IP、设备、端口或路径捷径 | 以设备/文件/攻击者身份代替行为分类 |
| G9 | Benign 有多独立来源，最好在攻击 capture 中也有背景业务 | 正常日与攻击日完全可分 |
| G10 | 官方入口、核心文件、标签/manifest、目录规模和研究使用许可可核验 | 只有论文中的 available 声明或二级镜像 |

## 本轮结论摘要

8 个种子候选中，4 个确认触发 Hard Gate，4 个因独立活动、few-shot 或下载/许可元数据不足而为 `INSUFFICIENT_EVIDENCE`，没有 `PASS_TO_FULL_AUDIT`。因此本轮不推荐任何候选进入完整审计，也不修改正式研究计划。
