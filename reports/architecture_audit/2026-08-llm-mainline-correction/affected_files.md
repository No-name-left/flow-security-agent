# 受旧架构影响的文件

| 文件或范围 | 影响类型 | 审计判断 | 本轮处理 |
| --- | --- | --- | --- |
| `docs/research_plan/research_plan_detailed.md` | 当前权威计划 | 将LightGBM/XGBoost写成主分类器，将Qwen写成Tree-aware Reviewer，并要求OOF概率 | 系统纠偏；保留全部历史Decision Log，新增DEC-0006/0007 |
| `docs/research_plan/research_plan_and_timeline.md` | 派生执行计划 | 依赖`Classifier→OOF→Reviewer`的任务和时间顺序 | 同步为Qwen首次分类、会话表示和Agent动态取证 |
| `docs/research_plan/research_plan_brief.md` | 导师简版 | 将LLM定位为传统模型困难样本复核器 | 同步为后训练LLM独立分类主线 |
| `docs/PROJECT_HANDOFF.md` | 当前交接状态 | 把旧架构和CICIoMT立即执行顺序写成现行状态 | 同步新的主链路、Edge-IIoTset候选状态和下一步边界 |
| `README.md` | 项目入口 | 仍使用Flow/NetFlow和旧的Flow-first概括，但没有实现传统分类器主链路 | 本轮不修改；后续项目入口同步时再调整 |
| `docs/legacy_migration_summary.md`、`docs/phase0_data_audit.md` | 历史工程记录 | 记录先做LightGBM/OOF再构造Reviewer数据的当时路线 | 保留为历史，不覆盖或改写 |
| `reports/plan_consistency/2026-08-ciciot2023-replan/` | 历史计划快照 | 明确包含传统模型主分类和Reviewer设计 | 保留并标为历史证据，不作为现行规范 |
| `reports/dataset_audit/**` | 历史数据审计 | 部分报告按传统模型信号、Unknown或Reviewer可行性筛选候选 | 保留审计事实；模型探针只作为基线/泄漏诊断证据 |
| `configs/data/ton_iot_ground_truth.yaml` | 历史数据合同 | `oof_fold_assignment`、`lightgbm_input`、`reviewer_output`反映旧用途限制 | 不修改；配置尚未进入新主线，可在对应资产重新启用时迁移语义 |
| `tools/dataset_audit/*.py` | 已实施审计代码 | 含LightGBM探针，但没有正式主分类或Reviewer pipeline | 可作为CPU信号/泄漏诊断工具，不需删除 |
| `src/flowsec/llm/` | 已实施通用代码 | 测试模型名偶有`reviewer`字样，但运行时无Reviewer架构耦合 | 直接复用；未来输出Schema由主分类任务定义 |
| `src/flowsec/data/`、`src/flowsec/rag/` | 已实施通用代码 | 提供字段角色、重复、分组、事件匹配和RAG摄取 | 复用并扩展为会话输入、跨会话上下文和知识工具 |

未发现已实现的`base_classifier`、`selective_qwen`、`CALL_LLM_EXPERT`调度器、Tree-aware SFT训练器或Agent主循环。相关名称主要存在于计划文字和历史报告中。
