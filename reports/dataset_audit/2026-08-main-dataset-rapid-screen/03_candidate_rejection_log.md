# 候选淘汰与证据不足日志

访问日期：2026-08-04。`UNKNOWN` 不按通过处理。

## 已确认 Hard Gate 失败

| 候选 | 状态 | 确认失败项 | 依据与停止原因 |
|---|---|---|---|
| GeNIS | `FAIL_HARD_GATE` | G3 | 官方层次仅包含 Brute Force、DoS、Recon 三个攻击 coarse 类，以及 10 个攻击 fine 类，低于 5/12 门槛。无需继续下载数据。 |
| Multi-Source Cybersecurity Logs | `FAIL_HARD_GATE` | G1、G10 | 原始论文明确把系统、网络、浏览器三源关联作为技术识别前提；截至访问日未找到论文指向的独立官方数据仓库或下载清单。 |
| Windows-APT 2025 | `FAIL_HARD_GATE` | G1 | 数据主体是 Wazuh/Sysmon Windows 事件，ATT&CK 技术语义依赖命令、进程、文件、注册表等主机字段；网络字段只能辅助 ground truth。 |
| CICAPT-IIoT 2024 | `FAIL_HARD_GATE` | G1、G3、G5 | 一个 APT29 启发的场景整合网络和 provenance；20 余技术中大量为主机/文件/进程语义，网络侧无法保留至少 12 个已证实可用 fine 类，且单一 campaign 不支持独立 10+1-shot。 |

## 证据不足，不得冒充通过

| 候选 | 状态 | 已确认优势 | 阻止 PASS 的最小缺口 |
|---|---|---|---|
| DataSense 2025 | `INSUFFICIENT_EVIDENCE` | 官方 PCAP、Benign、7 个攻击 coarse、49 个 attack fine，攻击 capture 中存在其他设备并发活动 | 官方逐类 run/scenario manifest、每个 fine 的独立执行次数、可恢复 group ID、按活动隔离的划分证明、确切数据许可 |
| CICIoMT2024 | `INSUFFICIENT_EVIDENCE` | PCAP/CSV、Benign、5 个攻击 coarse、18 个 nominal fine | 官方 train/test 是否按独立攻击执行划分；每个 fine 的 run/capture 数；是否有至少一个类达到 11 个独立活动；窗口生成是否引入类别捷径 |
| Gotham Dataset 2025 | `INSUFFICIENT_EVIDENCE` | 原始 PCAP、设备级 packet CSV、脚本化标签、Benign、类别数量名义上达标 | 78 个设备侧 capture 可能是同一攻击事件的分布式副本；需要 attack-event manifest 证明逐类独立执行数，而不是设备数 |
| X-IIoTID | `INSUFFICIENT_EVIDENCE` | 官方三层标签为 9 coarse/18 fine，论文称攻击实验多次重复，数据含 UID/时间戳 | 作者仓库未公开逐类 run manifest 或重复次数；公开汇总 CSV 是否能恢复独立执行、网络-only 可用 fine 数和许可证均未确认 |

## 共性失败模式

1. **独立 run 证据最普遍缺失。** 论文通常报告攻击类型、包数或 Flow 行数，却不提供每个 fine 类的独立执行清单。
2. **few-shot 的 10+1 门槛无法由行级数据证明。** 设备、目标组件、文件分片和时间窗口不能替代独立攻击执行。
3. **多源 APT 数据的标签落点与网络可观察性冲突。** ATT&CK 标签丰富不代表纯网络输入可以识别。
4. **官方 train/test 不等于 group-disjoint。** CICIoMT 的目录结构需要 manifest 证明其划分单位。
5. **许可与核心元数据常不完整。** 部分门户提供下载入口，但未在公开页面给出可直接核验的 dataset license、run manifest 或文件级 schema。
