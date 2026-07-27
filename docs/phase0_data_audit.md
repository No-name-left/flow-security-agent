# Phase 0：NF-ToN-IoT-v3 数据审计与 Grouping 分析

## 1. 当前结论

官方 NF-ToN-IoT-v3 压缩包已通过 ZIP CRC、BagIt SHA-1 和真实 CSV 内容交叉验证。全量 27,520,260 条 Flow 的 Schema、标签和数据质量审计已经完成。

数据中没有 `capture_id`、`source_file`、`scenario_id`、`activity_id` 或 campaign/event 标识。基于端点和时间间隔构造的三个候选 grouping 方案均存在明显方法学取舍和超大 group，尚不足以直接冻结正式划分。因此当前状态为：

```text
Phase 0 data audit completed.
Final split not frozen pending grouping decision.
```

本轮未生成 70/15/15 split、sample manifest 或 Internal Test，也未进入 60 秒上下文、LightGBM、OOF 或 Reviewer 阶段。

## 2. 官方压缩包验收

| 项目 | 实测结果 |
| --- | --- |
| 文件名 | `02934b58528a226b_NFV3DATA-A11964_A11964.zip` |
| 文件大小 | 417,476,635 bytes（约 398.14 MiB） |
| 本地修改时间 | 2026-07-27 18:16:55.784（Asia/Shanghai） |
| SHA-256 | `b3b6256e970a8986d87716edea4bfd436d68f04058bf5c26cf67e6d839c83698` |
| 格式 | ZIP，文件头 `50 4B 03 04` |
| 成员数 | 7 |
| 成员压缩后合计 | 417,475,153 bytes |
| 成员解压后合计 | 5,302,890,536 bytes（约 4.94 GiB） |
| 最大成员 | `data/NF-ToN-IoT-v3.csv`，5,302,886,266 bytes |
| 解压前可用空间 | 约 107.6 GB，充足 |

完整性检查结果：

- ZIP 中央目录可读取；
- 所有成员 CRC 检查通过；
- BagIt `manifest-sha1.txt` 中两个 payload 的 SHA-1 全部匹配；
- `tagmanifest-sha1.txt` 中三个 tag 文件的 SHA-1 全部匹配；
- 解压后的主体 CSV SHA-1 为 `24854ca3072ab7c2ade9ebfb202345a666a94cfe`，与包内清单一致；
- 解压后的特征说明 SHA-1 为 `d028597391217f78df3db31c1dbd96805203196f`，与包内清单一致。

压缩包不是 HTML、临时下载文件或中断文件。原 ZIP 保留在 `data/raw/`，解压内容位于 `data/raw/extracted/`；两者均由 `.gitignore` 中的 `data/` 规则排除。

### 2.1 包内成员

| 成员 | 压缩大小（bytes） | 解压大小（bytes） |
| --- | ---: | ---: |
| `FurtherInformation.txt` | 118 | 143 |
| `bag-info.txt` | 475 | 839 |
| `bagit.txt` | 55 | 55 |
| `manifest-sha1.txt` | 115 | 134 |
| `tagmanifest-sha1.txt` | 123 | 164 |
| `data/NF-ToN-IoT-v3.csv` | 417,473,273 | 5,302,886,266 |
| `data/NetFlow_v3_Features.csv` | 994 | 2,935 |

BagIt 元数据记录了 University of Queensland、2025-02-28、官方 eSpace 入口和打包标识 `02934b58528a226b_NFV3DATA-A11964_A11964`，与 DOI `10.48610/44d7c5e`、RDM ID `343e2e8c-6e6e-4a0c-813d-a46acea1b7f4` 一致。

## 3. 文件结构与真实 Schema

包中包含一个主体 Flow CSV 和一个特征字典 CSV，不是多分片数据。

| 文件 | 数据行数 | 列数 | 说明 |
| --- | ---: | ---: | --- |
| `NF-ToN-IoT-v3.csv` | 27,520,260 | 55 | 主体 Flow 数据 |
| `NetFlow_v3_Features.csv` | 53 | 2 | 特征名称与描述 |

主体 CSV 共 27,520,261 行（含表头）。PyArrow 全量解析成功，未发现格式损坏或中途 Schema 变化。

### 3.1 “53 features”与CSV列数的关系

特征字典列出 53 个 NetFlow-v3 特征；主体 CSV 的前 53 列与该字典的特征集合完全一致，但排列顺序不同。CSV 末尾另有：

- `Label`：二分类标签，`0/1`；
- `Attack`：原始十分类标签。

因此：

```text
53 extracted features + 2 label columns = 55 CSV columns
```

### 3.2 完整列名与 dtype

除 `IPV4_SRC_ADDR`、`IPV4_DST_ADDR` 和 `Attack` 为 string 外，其余 52 列均被真实数据稳定解析为 int64。

```text
FLOW_START_MILLISECONDS, FLOW_END_MILLISECONDS,
IPV4_SRC_ADDR, L4_SRC_PORT, IPV4_DST_ADDR, L4_DST_PORT,
PROTOCOL, L7_PROTO, IN_BYTES, IN_PKTS, OUT_BYTES, OUT_PKTS,
TCP_FLAGS, CLIENT_TCP_FLAGS, SERVER_TCP_FLAGS,
FLOW_DURATION_MILLISECONDS, DURATION_IN, DURATION_OUT,
MIN_TTL, MAX_TTL, LONGEST_FLOW_PKT, SHORTEST_FLOW_PKT,
MIN_IP_PKT_LEN, MAX_IP_PKT_LEN,
SRC_TO_DST_SECOND_BYTES, DST_TO_SRC_SECOND_BYTES,
RETRANSMITTED_IN_BYTES, RETRANSMITTED_IN_PKTS,
RETRANSMITTED_OUT_BYTES, RETRANSMITTED_OUT_PKTS,
SRC_TO_DST_AVG_THROUGHPUT, DST_TO_SRC_AVG_THROUGHPUT,
NUM_PKTS_UP_TO_128_BYTES, NUM_PKTS_128_TO_256_BYTES,
NUM_PKTS_256_TO_512_BYTES, NUM_PKTS_512_TO_1024_BYTES,
NUM_PKTS_1024_TO_1514_BYTES,
TCP_WIN_MAX_IN, TCP_WIN_MAX_OUT,
ICMP_TYPE, ICMP_IPV4_TYPE,
DNS_QUERY_ID, DNS_QUERY_TYPE, DNS_TTL_ANSWER,
FTP_COMMAND_RET_CODE,
SRC_TO_DST_IAT_MIN, SRC_TO_DST_IAT_MAX,
SRC_TO_DST_IAT_AVG, SRC_TO_DST_IAT_STDDEV,
DST_TO_SRC_IAT_MIN, DST_TO_SRC_IAT_MAX,
DST_TO_SRC_IAT_AVG, DST_TO_SRC_IAT_STDDEV,
Label, Attack
```

真实数据提供了源/目的 IP、端口、协议、Flow 起止时间和双向 IAT/IPAT 统计；没有额外的 capture、PCAP、scenario、activity、campaign、event 或 source-file 字段。

## 4. 标签审计

### 4.1 原始标签拼写

原始 `Attack` 取值为：

```text
Benign, Backdoor, dos, ddos, injection,
mitm, password, ransomware, scanning, xss
```

除 `Benign` 和 `Backdoor` 外，其余八类在原 CSV 中使用小写。这不是额外类别。配置通过显式 mapping 转为论文展示所用的 DoS、DDoS、Injection、MITM、Password、Ransomware、Scanning 和 XSS；原始 CSV 不作修改。

### 4.2 十分类分布

| Canonical 类别 | 原始值 | Flow 数 | 比例 |
| --- | --- | ---: | ---: |
| Benign | `Benign` | 16,792,214 | 61.0176% |
| Backdoor | `Backdoor` | 203,384 | 0.7390% |
| DoS | `dos` | 203,456 | 0.7393% |
| DDoS | `ddos` | 4,141,256 | 15.0480% |
| Injection | `injection` | 381,777 | 1.3873% |
| MITM | `mitm` | 6,013 | 0.0218% |
| Password | `password` | 1,594,777 | 5.7949% |
| Ransomware | `ransomware` | 3,971 | 0.0144% |
| Scanning | `scanning` | 1,358,977 | 4.9381% |
| XSS | `xss` | 2,834,435 | 10.2994% |

Binary 分布为：

| 标签 | Flow 数 | 比例 |
| --- | ---: | ---: |
| Benign (`Label=0`) | 16,792,214 | 61.0176% |
| Malicious (`Label=1`) | 10,728,046 | 38.9824% |

没有未知二分类值或额外十分类值；`Attack=Benign` 与 `Label=0`、其他攻击与 `Label=1` 的对应关系在 27,520,260 行上零冲突。

## 5. 数据质量

### 5.1 完整性和范围

- missing/null：0；
- NaN：0；
- `+inf/-inf`：0；
- 所有数值字段负值：0；
- Flow end 早于 start：0；
- 全局 start timestamp 逆序：0；
- 时间范围：2019-04-23 14:09:50.618 UTC 至 2019-04-29 14:45:55.861 UTC；
- duration 与 end-start 的差值超过 1 ms：0；
- `MIN_TTL > MAX_TTL`、最短包长大于最长包长、最小 IP 包长大于最大 IP 包长：均为 0；
- 端口范围为 0–65535，协议编号范围为 1–58，TTL 范围为 0–255。

主要极值包括：`IN_BYTES` 最大 79,846,944、`OUT_BYTES` 最大 70,221,306、`IN_PKTS` 最大 1,220,131、`OUT_PKTS` 最大 1,350,048、Flow duration 最大 120,999 ms。它们属于需要后续树模型和错误分析关注的长尾值，但未直接判定为非法。

### 5.2 重复行

使用 CSV 数据行精确文本相等的 BLAKE2b-128 分区哈希统计：

| 项目 | 数量 |
| --- | ---: |
| 重复簇 | 480,040 |
| 除首次出现外的重复行 | 1,816,137 |
| 重复比例 | 6.5993% |
| 单一记录最大重复次数 | 437 |

128 位哈希碰撞概率可忽略但不为数学上的零。重复比例足以构成重要泄漏风险；任何后续 split 都必须保证同一重复簇不会跨集合，不能简单随机按行划分。

### 5.3 常量、近常量与稀疏列

- 常量列：0；
- 近常量列：`FTP_COMMAND_RET_CODE`，99.6794% 为 0；
- 零值比例超过 95% 的列：
  - `FTP_COMMAND_RET_CODE`；
  - `RETRANSMITTED_IN_BYTES/PKTS`；
  - `RETRANSMITTED_OUT_BYTES/PKTS`；
  - `ICMP_TYPE`、`ICMP_IPV4_TYPE`；
  - `DNS_TTL_ANSWER`；
  - `DST_TO_SRC_IAT_MIN`。

这类稀疏不等于无效，后续只能在 Train/Validation 内判断是否保留。

### 5.4 IAT 一致性提示

发现：

- 149,230 行 `SRC_TO_DST_IAT_MIN > SRC_TO_DST_IAT_AVG`；
- 367,515 行 `DST_TO_SRC_IAT_MIN > DST_TO_SRC_IAT_AVG`；
- `IAT_AVG > IAT_MAX` 为 0。

该现象可能与生成器的整数取整、单包方向处理或字段实现有关，不能在没有生成代码证据时自行修正。原值保留，并在后续 Evidence Card 中避免把这些统计解释为严格连续数学量。

### 5.5 关键基数

| 字段 | cardinality | 最常见值（数量） |
| --- | ---: | --- |
| `IPV4_SRC_ADDR` | 15,270 | `192.168.1.32`（5,674,551） |
| `IPV4_DST_ADDR` | 8,777 | `192.168.1.195`（2,940,587） |
| `L4_SRC_PORT` | 65,536 | `443`（3,378,364） |
| `L4_DST_PORT` | 65,536 | `80`（5,648,073） |
| `PROTOCOL` | 5 | `6`（22,875,991） |
| `L7_PROTO` | 133 | `0`（8,452,498） |

## 6. Feature-role contract

机器可读 contract 位于 `configs/data/nf_ton_iot_v3.yaml`，其规范化 fingerprint 为
`c5d340578b26836d84df708cbcd95b628a47b163e6193476fd26b2635b101d3c`。

| 角色 | 数量 | 内容 |
| --- | ---: | --- |
| `model_feature` | 49 | 端口、协议、字节/包、持续时间、标志、TTL、吞吐、包长、重传、DNS/FTP、IAT 等数值特征 |
| `context_only` | 4 | 两个 raw IP 与两个绝对时间戳；允许 grouping、时间排序和后续 causal context，不直接进入 LightGBM |
| `label` | 2 | `Label` 与 `Attack` |
| `grouping_only` / `identifier` / `metadata` | 0（原始 CSV） | CSV 未提供天然活动或采集标识；后续派生的 `source_file/source_row/sample_id/group_id` 才属于这些角色 |

自动泄漏检查保证 raw IP、绝对时间戳、标签和后续 group/source 标识不进入 `model_feature`。

## 7. Group/activity 结构

### 7.1 天然 group 检查

主体 CSV 只有一个文件，且没有 capture/scenario/activity/campaign/event/session 标识。文件级 group 只有一个，不能用于 70/15/15。时间戳全局单调，因此可以研究因果 episode，但无法从发布文件直接证明某个 episode 等于独立攻击活动。

相同 key 的正间隔抽样画像如下：

| 候选 key | key 数 | p99 | p99.5 | p99.9 |
| --- | ---: | ---: | ---: | ---: |
| 有向 `(src,dst)` | 25,488 | 11.9 s | 60.0 s | 1,513.4 s |
| 无向 `{src,dst}` | 20,711 | 9.2 s | 56.6 s | 1,130.2 s |
| `src` 主机 | 15,270 | 3.3 s | 7.0 s | 54.9 s |

间隔在 p99 后呈连续长尾而非清晰唯一断点。因此候选比较采用接近 p99.5 且便于解释的阈值：通信对 60 秒、源主机 10 秒。阈值只用于审计候选，不代表最终冻结。

### 7.2 三个候选方案

| 方案 | 定义 | group 数 | median | p90 | max | 纯 group 比例 | Flow 加权标签纯度 | 最大 group 占比 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 有向 `(src,dst)`，相邻间隔 >60 s 开新 group | 94,474 | 2 | 24 | 1,817,955 | 97.13% | 96.17% | 6.61% |
| B | 无向 `{src,dst}`，相邻间隔 >60 s 开新 group | 81,909 | 2 | 15 | 2,394,745 | 94.70% | 83.18% | 8.70% |
| C | `src` 主机，相邻间隔 >10 s 开新 group | 71,846 | 2 | 18 | 1,915,429 | 98.96% | 93.32% | 6.96% |

“纯 group”表示 group 内只有一种 `Attack` 标签；group 构造本身没有使用标签。

### 7.3 每类可识别 group 数

下表是每种候选定义下“包含该类别的 group 数”，不是已被证明确认的独立攻击活动数。混合标签 group 会计入多个类别。

| 类别 | A：有向通信对 | B：无向通信对 | C：源主机 |
| --- | ---: | ---: | ---: |
| Benign | 89,620 | 79,300 | 70,319 |
| Backdoor | 154 | 127 | 131 |
| DoS | 858 | 852 | 13 |
| DDoS | 1,224 | 888 | 821 |
| Injection | 881 | 853 | 312 |
| MITM | 327 | 326 | 333 |
| Password | 498 | 491 | 39 |
| Ransomware | 79 | 38 | 347 |
| Scanning | 1,986 | 1,823 | 240 |
| XSS | 1,558 | 1,550 | 40 |

三个候选在计数上都可覆盖三路划分，并在“group 数量上限”层面支持 Train 内五折；但方案 C 的 DoS、Password 和 XSS group 很少，分折会非常脆弱。数量充分不等于活动独立性已经得到证明。

### 7.4 风险与当前建议

- **方案 A**标签纯度最高于 B、类别覆盖较均衡，且保留方向信息，是当前最适合继续审查的候选。
- **方案 B**会把双向通信合并，最大 group 更大且 Flow 加权纯度只有 83.18%，当前不推荐。
- **方案 C**能把同一源主机的多目标突发放在一起，可能更接近扫描活动，但对 DDoS/DoS 的攻击角色未必正确，并使部分攻击家族只剩很少 group。
- 三种方案均存在 180 万以上的超大 group，会显著限制 70/15/15 比例和类别平衡。
- 方案 A 仍可能把同一 source 对多个 destination 的扫描/攻击活动拆到不同集合；方案 C 则可能把同一受害者对应的多源 DDoS 拆开。
- 数据没有攻击方向或活动真值，无法仅凭当前 CSV 判断哪种错误更严重。

因此建议把 A 作为后续首选候选，但**本轮不冻结**。需要决定是否接受“有向通信对＋60 秒 episode”作为可复现近似，或者进一步引入与原始 ToN-IoT 攻击日程/采集说明的对齐证据后再定义 class-aware activity group。

## 8. Split 与 Internal Test 状态

本轮没有生成 split。因而：

- Train/Validation/Internal Test Flow 数与 group 数：无；
- group overlap：不适用，尚未生成集合；
- sample completeness、sample_id uniqueness 和 split determinism：尚未执行；
- Internal Test 尚未冻结；
- 后续 group-aware 5-fold OOF 尚未生成，只能确认三个候选在名义 group 数上具备可行性。

正式 split 前还必须把精确重复簇并入 group isolation 约束，确保重复记录不跨集合。

## 9. 可复现产物与已知限制

Git 管理的实现包括：

- `configs/data/nf_ton_iot_v3.yaml`：真实 Schema、原始标签、canonical mapping 与 feature roles；
- `src/flowsec/data/`：流式审计、fingerprint 和 grouping 候选统计；
- `scripts/audit_nf_ton_iot_v3.py`；
- `scripts/analyze_nf_ton_iot_grouping.py`；
- `tests/data/`。

大型运行产物位于被 Git 忽略的 `artifacts/data/nf_ton_iot_v3/`：

- `phase0_audit.json`；
- `group_gap_profiles.json`；
- `group_candidates.json`。

完整测试结果为 `12 passed`，其中新增的 Schema、流式审计和 grouping 测试为
`3 passed`。测试时关闭 pytest cache，未修改既有无关测试内容。

当前主要限制是没有天然活动标识，也没有原始 PCAP/capture 对应关系；本研究仍保持 Flow-only，不因此引入 PCAP 正式实验。

## 10. Phase 0 判定

**数据获取、身份核验、Schema、标签、质量、feature-role 和候选 grouping 审计已通过；正式 split 未通过冻结条件。**

```text
Phase 0 data audit completed.
Grouping candidates evaluated on all 27,520,260 flows.
Final split not frozen pending grouping decision.
No downstream experiment has started.
```
