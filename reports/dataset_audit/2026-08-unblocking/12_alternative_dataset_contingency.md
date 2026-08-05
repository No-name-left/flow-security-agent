# 补充数据应急方案

元数据来源：CAM-LDS https://zenodo.org/records/18390561 ；Multi-Source Cybersecurity Logs https://arxiv.org/abs/2606.18190

条件检索已触发：可靠Known少于5、final-held-out少于2、无正式1/3/5-shot、跨源可靠交集为0且Episode未通过。

| 优先级 | 路径 | 元数据结论 | 下一步 |
| --- | --- | --- | --- |
| 1 | UWF原始mission log/映射 | 论文明确描述所需字段，但公开下载树未暴露 | 联系作者/维护方索取版本化mission log；获得后先复算活动数，不先下载更多Flow |
| 2 | CasinoLimit官方直接映射或人工金标准 | 已有完整Flow与instance；瓶颈是relation多义/零命中 | 先人工审45条；若精确率可接受，再扩大并询问作者地址/方向语义 |
| 3 | CAM-LDS | 2026公开数据有34个simulation run、81个Technique、NetFlow和attackmate步骤时间，但无正常用户模拟；旧审计未证明Technique步骤能直接定位到NetFlow记录 | 只下载一个小run做直接连接probe；通过后才重审，暂不进入正式数据角色 |
| 4 | 2026 Multi-Source Cybersecurity Logs | 论文称870 sessions、53个Technique和逐entry标签，但面向系统/网络/浏览器多源日志；公开数据位置、网络记录是否为可统一Flow、活动独立性仍待核实 | 等待正式数据/代码并做metadata-first复核，不因论文统计直接采用 |
| 5 | 常规NetFlow IDS数据 | Flow与类别通常充足，但缺少ATT&CK Technique和独立攻击活动 | 仅可作Task 0或工程预训练，不解决本论文主标签问题 |

筛选标准保持不变：公开可得、直接Flow/可独立提取Flow、父Technique标签可定位、明确run/activity、每类多个独立运行、非纯主机日志且核心类别不依赖Payload。未找到同时无条件满足这些要求的新数据集，因此本轮没有自动下载候选大文件。

CAM-LDS官方页面说明每个压缩包对应simulation run并含NetFlow与time-based attackmate标签，但也明确无正常用户模拟；这使其值得做小probe，却不足以直接解除主训练Gate。新数据进入前必须运行与本轮相同的label-unit、join、observability与shot审计。
