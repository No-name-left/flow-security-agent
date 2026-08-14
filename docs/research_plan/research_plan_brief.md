# 成本感知主动证据获取研究计划（导师简版）

> 2026-08-14同步；详细语义以`research_plan_detailed.md`和`task_definition_v2.md`为准，训练/Open-world执行以`../training/near_mainline_training_protocol_v1.md`为准。

## 一、核心研究问题

论文研究的不是“LLM能否做流量分类”或“Agent/few-shot是否可用”本身，而是：面对一个target session，系统能否先用廉价Basic-v2完成分类与Evidence sufficiency判断，仅在Observation不足时选择性取得下一类证据，并在Accuracy/Macro-F1与evidence calls、tokens、latency、cost之间优于固定完整表示。

TrafficLLM、ETooL、MalRAG、TrafficGPT/open-set TrafficLLM、NIDS-GPT和ICT-META已经覆盖通用traffic representation、multi-flow OOD、retrieval、open-set及few-shot adaptation。我们的边界是`cost-aware active / sequential observation-evidence acquisition`：还要观察什么、何时停止，以及该机制能否跨domain成立。

## 二、冻结架构

Qwen3.5-9B继续使用冻结base + 可训练LoRA + Linear Fine Classification Head + 冻结原始LM Head。Fine Head是唯一Known fine决策源；coarse由确定性映射得到；LM Head生成structured Evidence State。DeepSeek Supervisor不分类、不覆盖fine label，只选择一个bounded action；Runtime拥有执行、合法性、strict-past、去重、预算与失败处理authority。

### Training flow

```text
Eligible model-safe sessions
→ Basic-v2 primary + limited meaningful auxiliary states
→ Fine Head CE + LM Evidence-State loss
→ Model A Edge SFT
→ Model B multi-domain continuation SFT
→ Agent baselines stabilize
→ optional mixed-domain RLAIF + classification CE
```

### Qwen multi-task internal structure

```text
Session Evidence → Qwen3.5-9B shared representation
├─ Linear Fine Head → Known fine logits → deterministic coarse mapping
└─ frozen LM Head → sufficiency + supporting evidence
                    + missing_evidence[] + primary_gap
                    + gap_type + recoverability
```

### Inference Agent loop

```text
Basic-v2 → Qwen classification + Evidence State
→ sufficient? YES → STOP_AND_CLASSIFY
→ NO → DeepSeek Supervisor selects ONE bounded Evidence action
→ deterministic Runtime executes Packet/Payload | Application | Temporal | Relation
→ Qwen re-evaluates → classify / continue / backoff / abstain
```

Observation Evidence为Basic、Packet/Payload、Application、Temporal与Relation；Knowledge RAG严格独立，不能发明当前session observation。Unknown也独立于Evidence Insufficient：不足应继续观察；Observation充分但不属于Known taxonomy才进入Unknown rejection。Unknown不是low confidence或Abstain。

## 三、Model A → Model B

Model A是当前Edge-IIoTset single-domain controlled benchmark：六类Known为Normal、DDoS_HTTP、DDoS_TCP、Password、SQL_injection、Vulnerability_scanner。Dataset v3、Evidence-v2、Teacher-v2和corpus v3已冻结，Formal Near Multi-task SFT正在运行；该run/checkpoint必须完成、验证并保留，作为论文baseline和Model B warm start。

Model B正式增加多数据集：CICIDS2017与ToN-IoT为第一优先，兼容性和时间允许时增加CSE-CIC-IDS2018。统一pipeline为：

```text
Raw dataset → dataset-specific GT/provenance adapter
→ common session reconstruction
→ canonical label + common Evidence contracts
→ leakage-safe grouped/run-aware split
→ multi-domain corpus
```

Canonical label保留`source_label / canonical_family / canonical_fine_label / mapping_quality`；`FAMILY_ONLY`不得强行映射为错误fine subtype。Model B从Model A warm-start，Fine Head按6→K扩展，使用Edge replay与dataset/class-balanced sampling。新增clean external data以classification-only为主，只对少量代表性sessions生成高质量Evidence-State supervision。

## 四、核心实验与贡献边界

正式实验为：

1. Model A Edge-only controlled SFT与validation；
2. Basic-only、Full-Evidence One-Shot及可复现的TrafficLLM/ETooL式固定表示baseline；
3. Strong Static、RulePolicy、DeepSeek Supervisor/Agent的budget-matched active acquisition；
4. Edge + CICIDS2017 + ToN-IoT Model B的in-domain、cross-run/capture与cross-dataset evaluation；
5. Independent OOD/Unknown rejection。

贡献聚焦于序贯Observation-Evidence问题、Fine Classification/Evidence State分离、bounded Supervisor + deterministic Runtime、accuracy-cost权衡和多域验证。RLAIF只优化trajectory policy，不单独夸大为创新；Unknown是鲁棒性扩展。Few-shot novel-class registration不再属于核心实验、关键路径或贡献，只保留为Future Work/Optional Extension。

## 五、当前状态与下一步

Model A数据与训练输入保持：六类Dataset v3 train/validation/test为1,318,688/270,851/279,057；formal corpus为14,350 records / 11,958 sessions，SHA256 `d93789de29b746d923660bb2e4ccad501412e75303ddf95f7087c85f6c67d6ca`。Backdoor仍为Long-Horizon Temporal Case Study；Uploading/Ransomware仍为Observability-Limited auxiliaries。U_final继续sealed。

当前Formal SFT为`IN_PROGRESS`。下一步是安全完成并验证Model A，然后依次执行CICIDS2017与ToN-IoT `MULTI_DATASET_COMPATIBILITY_GATE`。不得因计划同步停止/重启当前训练；RLAIF、Unknown、U_final和正式Agent实验均未启动。
