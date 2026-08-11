# 网络流量开放识别与自适应取证智能体研究计划（导师简版）

> 2026-08-11同步；详细语义以`research_plan_detailed.md`为准，训练/Open-world执行以`../training/near_mainline_training_protocol_v1.md`为准。

## 一、论文问题与第一主线

论文研究：Qwen3.5-9B能否从会话级网络证据学习已知攻击表示，独立Unknown层能否识别开放世界样本，受约束Agent能否按需获取真实证据并在效果—成本之间优于固定流程，以及少量人工支持能否通过Class Memory接入新类。

正式trained Traffic Expert为冻结Qwen base + LoRA + Linear Fine Classification Head + 原始LM Head。Fine Head决定Known fine class，coarse由确定性映射得到；LM Head只输出supporting/missing evidence、sufficiency和gap等Evidence State。传统模型只作强baseline，不是Qwen router/reviewer。

```text
Session Evidence → Qwen representation
→ Fine Head + LM Evidence State
→ Independent Unknown
→ DeepSeek Flash Supervisor + deterministic Runtime
→ on-demand Evidence → Qwen re-evaluate
→ Fine / Coarse / Unknown / Abstain
→ optional Class Memory
```

## 二、ONE_MAINLINE_FIRST

先只跑Edge-IIoTset Near：seed `20260809`；11个冻结K_known；U_dev为DDoS_ICMP、OS_Fingerprinting；U_final为DDoS_UDP、XSS；SFT使用16,979个PLAN_B `K_known ∩ train`候选。不得重选K/U、split或PLAN。

Near先完成Raw/传统baseline、Multi-task SFT、RLAIF-GRPO、Independent Unknown、Basic/Fixed Full/RulePolicy/DeepSeek Flash Supervisor、Experience Memory和1/5/10-shot Class Memory。Far、Mixed、IoT-23及其他ablation在Near完整闭环后再执行。

## 三、两次训练与Unknown

Training #1：classification-first Multi-task BF16 LoRA SFT。

```text
L_SFT = lambda_cls * Fine Head CE + lambda_ev * Evidence generation
```

GT只监督分类；Evidence targets来自规则、受控mask/stage、DeepSeek Flash Teacher、一致性过滤和有界人工审查。Teacher不能决定标签或创造Observation。

Training #2：从独立SFT checkpoint继续RLAIF-GRPO，并保留Fine Head classification CE。GRPO优化grounding、sufficiency、missing evidence、gap、backoff/abstention、幻觉和schema；Fine correctness在同input rollout group内是常数，不是主要组内reward。DeepSeek Flash Judge在线/异步评价current-policy rollouts，不提前生成完整RL dataset。

随后冻结Qwen，只用Known validation与U_dev比较margin、entropy、energy和prototype distance。Unknown不是K+1类，不训练U_dev/U_final进Qwen；U_final只在所有相关配置冻结后打开。

## 四、Evidence、RAG、Payload与Agent

当前Production已实现Initial、packet 9–16、past-only Temporal和有限匿名Relation；Application、Sanitized Payload和Production RAG当前UNAVAILABLE，但不是永久禁用。最终Near按需支持真实Application字段和有界、protocol-aware、sanitized、untrusted Payload，并做shortcut audit。

RAG只补knowledge gap，不默认每样本调用，也不能把知识当成当前session observation。第一版使用通用protocol/attack/CVE知识和BM25+dense hybrid retrieval；禁止dataset/capture/U_final shortcut。

DeepSeek Flash Teacher、Judge、Supervisor是三个权限隔离角色。Supervisor不是第二分类器，只能请求一个合法Evidence动作、要求Qwen重评、backoff、reject或abstain；Runtime负责权限、预算、去重、U_final/GT隔离和Trace。

## 五、当前状态与下一步

Production Freeze、Edge v2 split、PLAN_B、Safe Adapter、Evidence Fidelity和官方raw Qwen本地/runtime smoke均已完成；这些不是论文结果。SFT、RL、Unknown、正式baseline、Agent与few-shot实验均未运行。

当前协议已在架构/权限层冻结；pooling、LoRA数值、LR/loss weight、Unknown threshold、RAG top-k和Supervisor budget仍只允许小规模train/validation-safe选择，不得看formal test/U_final。

**NEXT IMPLEMENTATION PHASE：Phase B Training Protocol Readiness。** 实现training-side Transformers/PEFT harness，冻结pooling、LoRA module assertion、serialization v1、Traffic Expert Prompt/schema v1、Application/Payload contracts和RAG Evidence Contract。不要在文档阶段启动训练或benchmark。
