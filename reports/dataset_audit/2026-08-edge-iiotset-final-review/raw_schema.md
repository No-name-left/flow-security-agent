# 原始字段审查与正式白名单建议

## Schema 事实

原始和 ML 整理 CSV 均观察到 63 列，主要包括：

- 时间与端点：`frame.time`、`ip.src_host`、`ip.dst_host`；
- ARP/ICMP：opcode、地址、checksum、sequence、timestamp 等；
- TCP/UDP：端口、flags、长度、sequence、ack、stream、time delta、Payload 等；
- HTTP：method、URI、referer、file_data、content_length、response 等；
- DNS：query name/type、retransmission 等；
- MQTT/Modbus：topic、message、flags、length、transaction/unit id 等；
- 标签：`Attack_label`、`Attack_type`。

`frame.time` 在多数原始 CSV 中表现为“年份 + 时分秒”，缺少月/日；MITM CSV 中为 `0.0`。PCAP 则保留 epoch 时间。后续时间排序应以 PCAP 为准，不得仅凭 CSV `frame.time` 跨捕获拼接。

## 正式 Flow/Session 白名单建议（候选）

| 处理 | 字段/证据 | 原因 |
|---|---|---|
| 默认允许 | 协议、双向包/字节、持续时间、IAT、方向、TCP flags、握手完整性、前 N 包长度与方向 | 可由 PCAP 确定性重建，接近部署可观察证据 |
| 条件允许 | 目的/源端口或服务族 | 有业务意义，但当前数据中端口可能与类别固定绑定，需有/无端口消融 |
| 仅应用证据消融 | HTTP method/长度、DNS 类型、MQTT/Modbus 类型与长度 | 可提供额外语义，但应使用小型白名单并检查缺失率/场景捷径 |
| 默认禁止 | 原始 IP、绝对时间、文件/capture/path、stream/sequence/checksum、设备唯一标识 | 容易识别场景而非行为 |
| 默认禁止 | 原始 Payload、完整 URI/query、HTTP file_data、MQTT message/topic、DNS 完整名称 | 可能直接包含攻击脚本或唯一字符串，不符合主要 Flow-only 口径 |
| 永久禁止输入 | `Attack_label`、`Attack_type` | 目标泄漏 |

数值序列建议使用定长 JSON 数组或紧凑字段对象，明确单位、缺失值和截断；缺失应用字段应显式记为 unavailable，而不是填充推断内容。该白名单是下一阶段的候选规范，尚未冻结为最终特征集合。
