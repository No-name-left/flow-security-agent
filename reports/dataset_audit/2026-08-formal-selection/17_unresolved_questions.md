# 尚未解决的问题与人工决策

## 会阻止正式训练的问题

1. CasinoLimit relation的源/目的方向、通配IP、缺失端口、时间边界和错误地址应采用何种确定性规范；需用多实例人工金标准验证。
2. 26个无system label的Flow成员和2个仅表头成员是否排除；140个Flow文件与114个标签实例的正式对应表如何冻结。
3. `T1562`在ATT&CK v19.1中的历史标签如何处理；不得自动替换。
4. 当前`K_core={T1018,T1046}`是否过小；`T1021/T1105/T1572`在relation连接和证据边界复核后能否升级。
5. UWF能否由攻击脚本/时间清单恢复比week更细的独立活动ID；若不能，few-shot与Episode只能采用保守周级或连续时间组。
6. UWF正常与攻击时间分离能否通过同周背景或匹配采样控制；否则Task 0不得作为核心结论。

## 不阻止审计、但限制外测的问题

7. CAM-LDS原始Zenodo中直接NetFlow文件的确切路径、Schema以及`attackmate`步骤到Flow的连接方式；本轮只确认了场景7脚本元数据。
8. CAM-LDS很多场景只有一个run，哪些Flow可观察Technique真正具有独立support/query仍未知。
9. Sum25-1后续周与2024训练域的共同Technique过少且受扫描支配，时间外测的统计解释需在冻结标签交集后确定。
10. Multi-Source Cybersecurity Logs的公开数据包、许可和session级split是否可获得；未解决前只作相关工作。

## 计算与模型人工决策

11. 目标RTX 5090环境的CUDA、PyTorch、Transformers/vLLM/bitsandbytes组合是否完整支持Qwen3.5 hybrid architecture与4-bit训练。
12. 官方checkpoint包含视觉塔；需在运行时确认冻结/不加载策略和LoRA模块列表，不能只依据静态后缀。
13. DPO是否能在32GB内保持必要序列长度；如果只能通过过度截断实现，应保留SFT并把DPO降级为可行性结果。
14. MET-LLM未披露具体DeepSeek checkpoint，不能作为参数规模或单卡可行性的定量对照。

所有问题应通过训练域数据、公开资料或目标硬件冒烟解决，不得根据最终test结果反向调整。
