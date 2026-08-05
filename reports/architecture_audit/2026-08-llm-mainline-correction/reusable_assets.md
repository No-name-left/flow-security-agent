# 可复用资产

| 资产 | 新架构用途 | 复用判断与边界 |
| --- | --- | --- |
| `src/flowsec/llm/runtime.py` | Qwen首次分类、重新分类、教师模型或Agent模型调用 | 直接复用；调用层不依赖传统分类器 |
| `src/flowsec/llm/structured_output.py` | fine/coarse/Unknown/证据状态及Agent工具结果验证 | 直接复用；需新增任务专用Pydantic Schema |
| `src/flowsec/llm/cache.py`、`fingerprint.py`、`trace.py` | 可复现推理、resume、成本/延迟和失败轨迹 | 直接复用；Evidence Card与知识域应纳入输入指纹 |
| `src/flowsec/config.py`与`configs/runtime.example.yaml` | 本地Qwen/vLLM和兼容API配置 | 直接复用；不表示模型已部署 |
| `src/flowsec/rag/ingestion.py` | known-only、full-frozen及few-shot memory知识语料 | 轻度扩展；仍需检索、排序、信息域隔离和索引指纹 |
| `src/flowsec/data/schema.py` | DatasetLabelSchema、字段白/黑名单及模型/后台关联角色 | 重构扩展；当前合同偏NF-ToN固定字段，尚非会话Schema |
| `src/flowsec/data/event_matching.py` | 精确重复控制、事件/会话归属及泄漏审计 | 参考或轻改；不能把IP身份直接作为模型特征 |
| `src/flowsec/data/grouping.py` | 会话候选、past-only上下文和group增强实验 | 参考设计后扩展；当前实现只针对NF-ToN字段和简单pair/gap规则 |
| `src/flowsec/data/audit.py`及`tools/dataset_audit/` | 数据可读性、标签/字段/重复与泄漏诊断 | 继续复用；LightGBM仅作为信号与捷径诊断或正式基线 |
| `tests/` | LLM调用、缓存、结构输出、RAG来源与数据工具回归保护 | 继续保留；新会话、K/U、信息隔离和Agent需新增测试 |
| 历史LightGBM/XGBoost探针 | 闭集/开放集、速度/成本与泄漏诊断基线 | 保留思想和可复用代码，不进入Qwen正式输入链 |

不建议复用旧的Reviewer命名、OOF必需输入合同、选择性Qwen路由规则和`CALL_LLM_EXPERT`动作设计。它们会把主链路重新耦合到传统模型。
