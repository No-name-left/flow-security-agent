# 网络流量开放识别与自适应取证智能体研究计划（导师简版）

> 2026-08-13同步；详细语义以`research_plan_detailed.md`和`task_definition_v2.md`为准，训练/Open-world执行以`../training/near_mainline_training_protocol_v1.md`为准。

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

## 二、ONE_MAINLINE_FIRST与Task Definition v2

先只跑Edge-IIoTset Near；U_dev仍为DDoS_ICMP、OS_Fingerprinting，U_final仍为DDoS_UDP、XSS且sealed。八类pre-model候选经Observation Eligibility冻结为六个主类：Normal、DDoS_HTTP、DDoS_TCP、Password、SQL_injection、Vulnerability_scanner。MITM与Port_Scanning因当前observation unit无法支持官方fine语义而排除。Backdoor为Long-Horizon Temporal Case Study；Uploading和Ransomware为Observability-Limited/Abstain辅助集，不进入主classification CE。

verified capture label不等于每个session有fine-class evidence。train/validation/test必须用同一Fine-Class Observation Eligibility Contract过滤generic、unobservable、wrong-granularity和label-propagation-only observations。优先保留现有chronological assignment再过滤；只有support不可用才允许deterministic grouped/chronological split v3。

Near先完成Raw/传统baseline、Multi-task SFT、RLAIF-GRPO、Independent Unknown、Basic/Fixed Full/RulePolicy/DeepSeek Flash Supervisor、Experience Memory和1/5/10-shot Class Memory。Far、Mixed、IoT-23及其他ablation在Near完整闭环后再执行。

## 三、两次训练与Unknown

Training #1：classification-first Multi-task BF16 LoRA SFT。

```text
L_SFT = lambda_cls * Fine Head CE + lambda_ev * Evidence generation
```

GT只监督分类；Evidence targets来自规则、受控mask/stage、DeepSeek Flash Teacher、一致性过滤和有界人工审查。`classification_ce_eligible`与`evidence_sufficient`互不门控：每个合法TRAIN K-known session的真实primary计算CE，即使当前Evidence不足；controlled lower-evidence auxiliary只训练Evidence LM并mask CE。GT只在backend target，绝不进入model-visible input。Teacher不能决定标签或创造Observation。

Training #2：从独立SFT checkpoint继续RLAIF-GRPO，并保留Fine Head classification CE。GRPO优化grounding、sufficiency、missing evidence、gap、backoff/abstention、幻觉和schema；Fine correctness在同input rollout group内是常数，不是主要组内reward。DeepSeek Flash Judge在线/异步评价current-policy rollouts，不提前生成完整RL dataset。

随后冻结Qwen，只用Known validation与U_dev比较margin、entropy、energy和prototype distance。Unknown不是K+1类，不训练U_dev/U_final进Qwen；U_final只在所有相关配置冻结后打开。

## 四、Evidence-v2、RAG、Payload与Agent

Basic-v2统一提供session summary、first-8 packet metadata、packet-index对齐的bounded sanitized payload和cheap structured Application metadata。后续Observation family固定为PACKET_PAYLOAD、APPLICATION、TEMPORAL、RELATION；Knowledge为KNOWLEDGE。Temporal只使用10/60/180/300秒strictly-past窗口，Relation允许ARP/link-layer context而不改变target session。

Evidence State v2支持真实multi-gap：`missing_evidence[]`、`primary_gap`、`gap_type`与`recoverability`。Qwen判断多个缺口，Supervisor仍只选一个action，Runtime确定性执行。RAG只补knowledge gap，不能证明当前session观察。

RAG只补knowledge gap，不默认每样本调用，也不能把知识当成当前session observation。第一版使用通用protocol/attack/CVE知识和BM25+dense hybrid retrieval；禁止dataset/capture/U_final shortcut。

DeepSeek Flash Teacher、Judge、Supervisor是三个权限隔离角色。Supervisor不是第二分类器，只能请求一个合法Evidence动作、要求Qwen重评、backoff、reject或abstain；Runtime负责权限、预算、去重、U_final/GT隔离和Trace。

## 五、当前状态与下一步

Production Freeze、Edge v2 split、Safe Adapter、Evidence Fidelity、官方raw Qwen本地/runtime smoke、Dataset v3、Evidence-v2、Teacher-v2与SFT corpus v3均已完成；这些不是论文结果。SFT、RL、Unknown、正式baseline、Agent与few-shot实验均未运行。

正式六类Dataset v3为train 1,318,688、validation 270,851、test 279,057；generic/unobservable主样本与sample identity overlap均为0。Basic-v2、packet-aligned payload、10/60/180/300秒strict-past Temporal、endpoint-linked Relation与structured Application已经物化。旧11类Teacher V3/22,957-record corpus只作为historical。

Teacher-v2 bulk为20,807/20,807 valid、quarantine 0；形式化轨迹只保留到首次sufficient并quarantine 161个terminal-inconsistent候选，未改写raw Teacher cache。正式corpus为14,350 records / 11,958 sessions，SHA256 `d93789de29b746d923660bb2e4ccad501412e75303ddf95f7087c85f6c67d6ca`；默认Known validation为3,231条`EXACT_EVAL_CLEAN`。权重、label-map、token 8192、U_final和plan consistency Gate均PASS。

**`READY_FOR_FORMAL_SFT=true`；NEXT ACTION=`START_FORMAL_NEAR_MULTI_TASK_SFT`。** 旧formal launcher继续fail closed，新v2 config才是授权入口。`FORMAL_SFT_STARTED=false`；RL、Unknown、U_final和Agent benchmark仍未运行。
