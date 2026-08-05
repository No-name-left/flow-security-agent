# Edge-IIoTset + IoT-23最终可行性Gate

> 本报告保留2026-08-06 Gate的实测事实与判定。报告生成时记录的“下一步”已由DEC-0010更新：正式下载、全量解析、Production Adapter与训练资产生成转移到远程服务器，当前执行说明见`docs/SERVER_MIGRATION.md`。

## 最终判定

- **整体：PASS_WITH_LIMITATIONS**
- **Edge-IIoTset：PASS_WITH_LIMITATIONS**
- **IoT-23：PASS_WITH_LIMITATIONS**

## 已实测事实

1. Edge代表性PCAP可由TShark重建双向会话、前16包、摘要与split内60秒past-only上下文；标签在所选逐包CSV中保持文件级一致。
2. IoT-23官方Zeek日志可解析，并能通过时间与五元组和官方PCAP稳定匹配；7个capture足以构造训练、验证、完全留出测试及一个完整unknown_final场景。
3. 两个Adapter均输出`CanonicalSessionRecord`；模型初始视图不包含IP、绝对时间、文件名、数据集名或capture/scenario ID。
4. 去除service category后的行为白名单RF在非随机划分上仍相对多数类/随机基线存在可重复的非随机信号；full-behavior与service-only结果仅用于捷径敏感性诊断，具体数值见轻量报告。
5. 未发现会阻止进入正式数据生成的标签、解析或直接泄漏问题。

## 冻结限制

- Edge多数攻击类仍只有一个capture；只能声称控制捷径后的同采集环境效果，sample-level few-shot不等于跨run few-shot。
- IoT-23主外测采用原生行为标签的独立scenario协议；Capture-42的完整未知场景只有6条FileDownload恶意流，Unknown主结果需另以预注册类/场景补足样本或明确小样本置信区间。
- Capture-42的PCAP被TShark报告为尾部截断，Somfy-01仍有24条官方日志未与PCAP匹配；当前已匹配部分足以通过Gate，正式source manifest必须显式记录异常处置。
- 本轮Adapter是可复现验收实现，不是全量生产流水线；正式阶段仍需冻结全量manifest、K/U和异常文件处置。
- 未运行Qwen推理或训练，所有轻量模型数值均为审计探针而非论文结果。

## 决策

双数据集方案可以进入正式数据生成和GPU服务器训练准备，但必须保留上述限制。下一步唯一动作是：**将本轮验收Adapter固化为生产数据流水线，并冻结全量split、K/U、support/query和训练manifest。**
