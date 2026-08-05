# 旧架构资产清单

## 1. 已实施代码

已实施部分是通用基础设施，不等同于旧架构主流程：

- OpenAI-compatible模型调用、超时、重试、并发与shard；
- Pydantic结构化输出验证；
- 输入、Prompt、模型、生成参数、运行时和Schema指纹；
- 原子缓存、resume、失败隔离、usage/latency trace；
- Markdown/YAML front matter RAG摄取与来源元数据；
- 数据字段角色、直接泄漏检查、精确重复签名、Ground Truth匹配、候选分组和CSV审计；
- NF-ToN/ToN-IoT相关审计脚本和若干LightGBM CPU探针。

没有发现正式LightGBM/XGBoost训练pipeline、OOF训练数据生成器、Qwen SFT/DPO训练器、Evidence Card实现、Unknown正式算法、选择性Qwen路由器或Agent执行器。

## 2. 计划文字中的旧架构

纠偏前的三份计划及交接文档将系统描述为：传统模型输出coarse/fine概率与不确定性，OOF结果进入Tree-aware Qwen Reviewer，Agent再决定是否调用Reviewer或接受树模型结果。这是计划设想，不是已运行代码。

本轮撤销其正式定位：传统模型降为基线；Qwen直接第一次分类；Agent围绕Qwen证据状态动态取证；`CALL_LLM_EXPERT`由`RECLASSIFY`等动作取代。

## 3. 历史基线与审计材料

- CICIoT2023和UWF等报告中的LightGBM数值是数据可学性或捷径风险探针，不是论文正式结果。
- `reports/plan_consistency/2026-08-ciciot2023-replan/`记录的是当时方案快照，应保留以解释决策演进。
- `docs/legacy_migration_summary.md`和`docs/phase0_data_audit.md`记录旧执行顺序，属于历史工程上下文。
- `configs/data/ton_iot_ground_truth.yaml`中的OOF/LightGBM/Reviewer用途限制属于当时的数据权限描述，尚未形成新主线实现。

## 4. 尚未执行的设想

以下内容此前虽在计划中出现，但均未完成，不能描述为遗留实现：

- Tree-aware Qwen3.5-9B Reviewer；
- group-aware OOF概率作为SFT必需输入；
- selective Qwen只处理困难样本；
- `Classifier→RAG/LLM`正式固定链；
- `CALL_LLM_EXPERT` Agent动作；
- RulePolicy/LearnablePolicy正式训练与对照；
- SFT、DPO、Unknown、few-shot及论文主结果。
