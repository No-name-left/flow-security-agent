# 短名单与后续审计决策

## 最终判定

`NO_SINGLE_DATASET_CANDIDATE_FOUND`

本轮 8 个候选中没有 `PASS_TO_FULL_AUDIT`，因此不推荐任何候选进入完整数据审计。以下排序只是**后续元数据取证优先级**，不是 full audit 推荐，也不改变“正式主数据集尚未确定”的现状。

## 前两名：元数据取证优先级

### 1. DataSense: CIC IIoT Dataset 2025

值得继续关注的原因是类别层次、原始 PCAP、Benign 与攻击时的并发背景在官方论文中都有较强证据，名义类别覆盖明显超过 G3。最大未决问题不是数据量，而是 49 个 fine 类各自是否被独立重复执行，以及官方 PCAP 的“按目标组件分段”能否恢复真实 run，而不是同一执行的切片。

若未来仅做一次最小证据补充，首先应取得：文件树、attack/scenario manifest、每个 attack type 的 run/capture 清单、时间边界、攻击者/目标映射、许可文本。若官方材料仍只给每类一个场景或目标组件切片，应立即停止，不进入 full audit。

### 2. CICIoMT2024

其优势是网络输入明确、PCAP 与 CSV 均有官方入口，并恰好覆盖 5 个 coarse 和 18 个 nominal fine。最大未决问题是“18 attacks were executed”究竟表示 18 个攻击类型各一次，还是包含可独立分组的多次执行；官方 train/test 目录也未证明按活动隔离。

若未来仅做一次最小证据补充，首先应取得：PCAP 文件清单、train/test 下每类文件数及命名规则、采集时间、目标设备、攻击执行 ID、特征窗口脚本。若文件只是同一 run 的目标/设备切片，或没有任何 fine 类达到 11 个独立活动，应立即停止。

## 未推荐的原因分布

| 原因 | 涉及候选 |
|---|---|
| 类别数量确认不足 | GeNIS；CICAPT-IIoT 的网络可用 fine 类 |
| 独立 run / 10+1 few-shot 无证据 | DataSense、Gotham、CICIoMT、X-IIoTID；CICAPT-IIoT 明确不足 |
| 标签无法仅靠网络证据成立 | Multi-Source Logs、Windows-APT、CICAPT-IIoT |
| group-disjoint 划分未证明 | DataSense、Gotham、CICIoMT、X-IIoTID |
| 官方核心数据或许可未完全核验 | Multi-Source Logs、DataSense、Gotham、CICIoMT、X-IIoTID |

## 结论约束

没有候选被证明可严格支持独立活动级 1/5/10-shot。后续如获得新的官方 manifest，可重新做一次仅针对 G4/G5/G7/G10 的证据更新；在此之前不得以完整下载或模型试跑代替结构性审计。
