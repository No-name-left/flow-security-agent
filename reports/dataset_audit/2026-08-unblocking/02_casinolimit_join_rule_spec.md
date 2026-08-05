# CasinoLimit relation-to-Flow连接规范

官方数据记录：https://zenodo.org/records/17256954

## 输入与规范化

- 实例键采用Unicode NFKC、去首尾/内部空白、大小写折叠，并以ZIP成员basename映射。
- CSV使用`skipinitialspace`；时间解析为无时区的同源时间轴；端口转为nullable integer；空串、`nan/none/null/<NA>`统一为空。
- 官方尾部自由文本列不是标准CSV。连接只读取确定出现在其前的`timestamp/src_ip/dst_ip/src_port/dst_port`，非标准尾列另计，不解析为监督依据。
- relation时间采用闭区间`[start,end]`。±1/10/100/1000 ms仅输出敏感性诊断，不进入主规则。

## 冻结规则层级

| 规则 | 条件 | 自动用途 |
| --- | --- | --- |
| R0 | 严格方向、精确IP、两端端口、闭区间时间 | 可形成唯一候选时仍需语义抽查 |
| R1 | 仅交换网络方向，其余严格 | 记录候选；需确认采集方向 |
| R2 | 双向endpoint-set归一，其余严格 | 记录候选；不得按命中率擅自选择 |
| R3 | 仅对relation原文明确出现的`*`/`?`应用通配 | 允许，不扩展到任意模糊IP |
| R4 | 仅对relation原文缺失的相应端口取消约束 | 允许，不忽略已给出的服务端口 |
| R5 | 上述规则无命中，或需地址/时间异常修复 | 人工队列，永不自动进入训练 |

实际relation全部带明确通配源IP且全部缺失源端口，其中2,373条还缺失目的端口，因此严格R0—R2不具备应用前提。主自动候选规则为方向归一后的`R3+R4`：保留relation中仍然存在的IP/端口约束，并在闭区间内检索。方向仅允许direct/reverse/both三种可解释结果。

拒绝以下规则：时间窗内任意Flow、忽略已有目的端口、任意IP模糊匹配、把`10.35`与`10.135`自动互换、为了提高覆盖率扩大时间容差、按最终Technique结果反向选择规则。它们会引入不可量化的假阳性或测试驱动调参。

## 全量结果

按relation去重后，4,865条中1,628条由`R3+R4`得到候选，3,237条进入R5；21条唯一命中、1,607条多义。零命中主要为时间窗内无Flow（1,967）、端点不匹配（1,251）和已有端口约束不匹配（19）。±1秒只使25条R5 relation出现候选，不能证明容差正确；地址重映射诊断使13条出现候选，同样不自动采用。

所有自动候选仍需人工语义确认。复算命令：

```powershell
python tools/dataset_audit/unblocking_audit.py --cache-root ..\dataset_audit_cache --report-dir reports\dataset_audit\2026-08-unblocking
```
