# LLM主分类架构回溯审计

## 审计范围

本记录形成于2026-08-05，用于追踪“传统模型主分类+Qwen复核”旧架构如何进入当前计划，并确认哪些已实现资产可在“后训练Qwen独立首次分类+Agent动态取证”新主线中继续使用。

本轮只读检查了Git状态、三份研究计划及其Decision Log、交接文档、基础设施说明、`src/`、`scripts/`、`configs/`、`tests/`和相关历史报告。除本目录、三份研究计划和交接文档外，没有修改代码、配置、数据或历史审计材料；没有下载数据、运行模型或正式实验。

## 核心结论

1. 旧架构的主要影响位于三份研究计划和交接文档；部分历史审计和计划一致性报告也保留相同叙述，但属于当时的历史证据。
2. 仓库尚未实现LightGBM/XGBoost正式主分类、OOF Tree-aware训练、Qwen Reviewer SFT、选择性Qwen路由或Agent策略，因此本次不需要撤销已运行模型或重构正式pipeline。
3. 已实现的OpenAI-compatible运行时、结构化输出、缓存/resume/trace、RAG摄取、数据合同、重复检测、分组与Ground Truth匹配均为通用资产，可直接服务Qwen主分类和Agent工具调用。
4. 历史LightGBM/XGBoost审计探针仍可作为传统强基线和泄漏诊断参考，但不能继续定义正式主链路。
5. Edge-IIoTset只是当前第一主数据候选，尚未锁定；本轮没有下载或审查它。

## 正式纠偏结果

```text
网络流量样本
→ 会话级混合表示
→ 后训练Qwen3.5-9B独立执行第一次分类
→ 输出fine、coarse、Unknown分数和证据状态
→ Agent按需扩展证据、重新分类、拒识或接入新类
```

详细影响见`affected_files.md`，旧架构资产分类见`old_architecture_inventory.md`，可复用资产见`reusable_assets.md`，未决问题见`unresolved_questions.md`。
