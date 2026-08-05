# Qwen输入端到端冒烟

- 真实序列化输入：200条，Edge与IoT-23使用同一Evidence结构。
- 初始包预算：前8包；最大保存：16包。
- Schema与序列化检查：True。
- Unknown输出路径：True；capability工具门控：True。
- 输入字符长度统计：`{"Edge-IIoTset": {"min": 844, "median": 1346.0, "p95": 1738.0, "max": 1748}, "IoT-23": {"min": 820, "median": 1122.0, "p95": 1724.2, "max": 1732}}`。
- 本轮未调用在线或本地模型，未下载Qwen权重；只验证输入、动作与输出JSON合同。真实样例见`qwen_input_samples.jsonl`。
