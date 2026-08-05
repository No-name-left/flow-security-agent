# LLM论文与计算资源审查

## 1. 相关模型不是同一种训练路线

| 工作 | 实际基础模型 | 实际训练内容 | 输入/样本 | 硬件与规模 | 对本项目的直接含义 |
| --- | --- | --- | --- | --- | --- |
| DoLLM | Llama2-7B-chat，BF16 | 冻结主干；训练两层MLP Flow Tokenizer、线性投影和分类层；不是LoRA | 9个Flow统计字段，64条Flow组成序列；排序不是时间序列；15,000个训练序列 | 单RTX 4090；论文报告20轮 | 证明冻结7B加Flow前端可在单消费卡训练，但任务是Carpet Bombing DDoS；其“zero-shot”是同一数据集内留出攻击类型，不等于未见ATT&CK Technique。 |
| TrafficLLM：Generic Traffic Representation | ChatGLM2-6B、Llama2-7B为主，另有12B/13B规模对照 | 冻结主干，双阶段P-Tuning v2；每个PEFT约7.1MB、论文称约0.62%可训练参数 | 10个数据集、约40万样本；每类最多5,000条；随机8:1:1；输入最长3072 | 5×A100 80GB；6B PEFT更新约23GB、14小时/50k样本/20k步；完整7B重训只作开销对照 | 主要贡献是通用流量表示和跨任务适配，不是开放ATT&CK Reviewer；随机行划分不能直接复制到本项目。 |
| TrafficLLM：Open-Set Encrypted Traffic | GPT-2-small与Llama2-7B | GPT-2全量微调；Llama2-7B作特征提取器，4-bit QLoRA（r=8, alpha=32, dropout=0.05） | 7个加密流量序列数据集；约40%类别设为closed set；下游OpenMax、Background Class、k-LND | 2×RTX 4090；论文表中约39.2GB GPU；量化权重约3.7GB | 与上一个TrafficLLM是不同论文。它研究开放集加密流量和特征空间，不是指令式证据Reviewer，也不能据此声称单4090足够。 |
| MET-LLM | 论文仅称`Deepseek`，未报告可复现的具体checkpoint或参数量 | 安全语料继续预训练、专用BPE、DATA适配（prompt injection、对抗训练、动态mask） | Header与Payload分段；不是本项目Flow-only输入 | 论文称约14GB显存、单卡约2,500 flows/s | 不能把它写成“7B模型”。代码仓库目前没有可执行实现，模型身份和资源数字无法独立复验。 |
| Multi-Source Cybersecurity Logs | Qwen2.5-1.5B、Llama3.2-3B、Phi-4-mini 3.8B | LoRA r=16、alpha=32，最多3轮，少于1%参数 | 870 sessions（70 attack、800 benign），约230万事件；7条事件/chunk；训练/验证从随机chunk中取40%并过滤至≤2000 tokens | GPU未报告；最终训练22,896、验证3,065个chunk | 任务是系统/网络/浏览器多源日志Technique标注，不是Flow-only。随机chunk划分可能把同一session内容放入不同集合；公开数据包和许可本轮未找到。 |

DoLLM、两篇TrafficLLM和Multi-Source的数值来自本地缓存论文PDF逐页核验；MET-LLM使用出版页面与当前公开仓库。任何未报告硬件或checkpoint均保留为“未报告”，不猜测。

## 2. Qwen3.5-9B静态核验

官方checkpoint声明`Qwen3_5ForConditionalGeneration`，包含27层视觉塔和32层文本主干；文本隐藏维度4096、FFN 12288、词表248,320，层型为3个Gated DeltaNet线性注意力层加1个全注意力层的重复结构。官方safetensors索引总字节数19,306,216,416（约17.98 GiB BF16文件）。这不是“纯9B文本checkpoint”的简单Llama式结构，训练脚本应冻结视觉塔并在真实加载后确认text-only路径。

静态源码扫描得到的文本LoRA候选后缀为：`q_proj/k_proj/v_proj/o_proj`、`gate_proj/up_proj/down_proj`、`in_proj_qkv/in_proj_z/in_proj_b/in_proj_a/out_proj`。视觉层的`qkv/proj/linear_fc*`已排除。该结果只用于冒烟测试候选，不能替代运行时`named_modules()`核验。详见`qwen35_static_inspection.json`与`inspect_qwen35_modules.py`。

## 3. RTX 5090 32GB可行性

| 操作 | 估算显存口径 | 判断 |
| --- | --- | --- |
| BF16推理 | 17.98 GiB权重文件，加KV cache、视觉/文本模块、CUDA和服务框架开销；小上下文/低并发大致22–30 GiB | 条件可行，接近边界；不应直接启用262K上下文或高并发 |
| 4-bit推理 | 原始4-bit权重约4.5 GiB，含量化元数据、运行时和KV后通常约8–14 GiB | 可行，适合批量Reviewer基线；实际吞吐必须实测 |
| 4-bit QLoRA SFT | 量化基座、LoRA/梯度、优化器、激活与框架开销；2K、micro-batch=1估计约18–27 GiB | CONDITIONAL GO；使用BF16计算、NF4、梯度检查点、paged 8-bit optimizer和梯度累积 |
| 4-bit DPO | chosen/rejected激活与reference路径使峰值更高；若采用同一量化基座/adapter reference并顺序计算，估计约24–31 GiB | 高风险条件可行；先短序列小批次，不加载两份BF16模型 |
| 全参数微调 | 权重、梯度和Adam状态通常已超过140 GiB，未计激活 | NO-GO |
| 完整PPO-RLHF | policy/reference/reward/value等多模型与rollout | NO-GO |
| 27B完整训练 | 单卡32GB不具备现实余量 | NO-GO；仅量化推理或额外多卡/高显存资源 |

以上是资源规划区间，不是实测结果。建议顺序为：30–90分钟环境与加载冒烟；2–6小时SFT小样本pilot；主SFT约8–24小时；DPO pilot 2–6小时、主实验约6–18小时。时长受序列长度、样本数、FlashAttention/Transformers支持、磁盘与数据整理影响，正式预算只能在目标机器实测后冻结。

## 4. 冒烟测试边界

已生成`qwen35_9b_5090_smoke_test.py`，默认只做preflight，不下载权重、不运行训练。当前电脑无PyTorch和目标GPU，结果为`PREPARED_NOT_RUN`。在租赁机上应依次验证：版本兼容、BF16能力、4-bit加载、实际LoRA目标层、前向/反向单步、峰值显存、tokens/s、checkpoint保存/重载；任一失败时先缩短到2K、micro-batch=1并减少LoRA目标，而不是直接扩大资源承诺。
