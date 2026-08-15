# Open-World Continually Evolving LLM Traffic Agent（导师简版）

> 2026-08-15，DEC-0024。详细语义以`research_plan_detailed.md`和`open_world_continual_agent_design.md`为准。

## 一、为什么调整主线

Model A已完成：Edge六类closed-set Macro-F1为`0.998483`，但3,600个平衡TRAIN样本上的Frozen-Qwen Linear Probe已达`0.981563`。这说明当前closed-set任务上的pretrained representation已经很强，不能把分类本身或约1.7个百分点差距全部归因于LoRA，也不能把它继续作为主要创新。

Model A的generative Evidence State则明确失败：Basic-insufficient sufficiency F1=`0`，gap micro-F1=`0`，532/537个Basic-insufficient样本被判为sufficient；同时该subset分类Macro-F1仍为`0.997354`。因此：

```text
Semantic Sufficiency != demonstrated Operational Utility
MODEL_A_EVIDENCE_STATE=FAIL
```

Active Evidence必须先用低成本OOF实验证明“额外Evidence真的改善未见样本”，不能再默认成为主线。

## 二、新主线

```text
Open-World Continually Evolving LLM Traffic Agent
```

三个核心RQ：

1. LLM shared representation是否在multi-domain、cross-domain和open-set上优于强structured与Frozen-Qwen baseline；
2. 系统能否Unknown detection → verified feedback → new-class registration → replay adaptation → regression-gated release，并减少遗忘；
3. learned Agent policy是否比强Heuristic更好地平衡accuracy、Unknown、query/Evidence cost、adaptation timing与forgetting。

## 三、三Plane架构

```text
Plane A — Perception
Qwen3.5-9B frozen base + LoRA → shared h
├─ Family Head
├─ Fine Head
├─ MSP / Energy / Prototype Unknown
├─ optional Evidence Decision Head [Utility Gate后]
└─ LM Head: explanation/description only

Plane B — Control
Known classify / Unknown reject / defer buffer
+ knowledge / verified-feedback actions
+ optional Evidence actions [Gate后]
Runtime拥有执行、budget、strict-past、GT隔离和release authority

Plane C — Evolution
Unknown Buffer → verified feedback → class confirmation
→ continual adaptation + old replay → regression gate
→ Model B_t → Model B_{t+1}，失败则rollback
```

总体workflow：

```text
Traffic Stream
→ Canonical Evidence
→ Qwen Representation
→ Known Classifier + Unknown Detector
→ Known ─────────────────────────────→ classify
→ Unknown / uncertain
   → optional Evidence / Knowledge
   → Unknown Buffer
   → verified feedback
   → new-class confirmation
   → continual adaptation + replay
   → regression gate
   → Model B_t → Model B_{t+1}
```

RL Policy只包围runtime decisions，不直接生成新攻击GT。

## 四、Dataset-v4与Model B0

Source preflight优先为CICIDS2017、CSE-CIC-IDS2018、ToN-IoT；Edge-IIoTset-clean降为legacy controlled baseline/optional replay。Bot-IoT、UNSW-NB15、DoHBrw和USTC-TFC2016为fallback。最终Dataset-v4组成和taxonomy均为`PROVISIONAL`。

每个source先用少量capture/run和几百sessions检查raw/GT、session mapping、granularity、observability、leakage、split和Evidence availability；通过才允许全量构建。统一单位是CanonicalSession，不是CSV拼接。Fine loss只使用`EXACT` mapping；`FAMILY_ONLY`只训练Family Head。

在训练前按canonical semantic class冻结`K0/U_dev/U_final/U_inc`，防止同义类跨dataset泄漏。Dataset-v4同时包含static split和隐藏future GT的continual stream。

Model B0结构：

```text
Qwen3.5-9B frozen base + LoRA → shared h
h → Family Head
h → Fine Head
h/logits → Energy / Prototype / MSP Unknown
```

Model A warm-start不再默认；必须与fresh LoRA做same-data/same-step短训ablation。

## 五、Evidence、DeepSeek与RL

Evidence Utility Pilot使用Frozen-Qwen representations与stratified OOF probes比较Basic和Basic+单一Evidence。只有稳定、可重复的困难subset增益，且bootstrap/第二seed或reference model支持，才实现Evidence Decision Head和Evidence RL。

DeepSeek降为offline Teacher、policy demonstration source、semantic reviewer和optional Supervisor baseline，不是最终系统不可替代的online controller。

RL分级为：

1. RL-0强Heuristic；
2. RL-1 frozen-Qwen + small policy，与Heuristic比较长期收益；
3. RL-2 Qwen policy LoRA仅在RL-1 PASS、reward/trajectory/GPU条件具备且导师确认后考虑。

新攻击语义由verified-label supervised continual learning学习，不由confidence或RL自我确认。

## 六、正式阶段

```text
0. Model A freeze [COMPLETE]
1. Source Compatibility Preflight
2. Evidence Utility Pilot / Active Evidence Go-No-Go
3. Dataset-v4 full build
4. Model B0 + Unknown + LLM value/warm-start ablations
5. Open-world continual baseline with replay and Release Gate
6. RL-1 Heuristic comparison
7. only gated Evidence/RAG/RL-2 enhancements
8. sealed final evaluation and writing
```

当前不下载大型数据、不处理全量PCAP、不训练Model B、不调用bulk Teacher、不运行RL、不访问U_final。Few-shot=`OUT_OF_SCOPE`；旧Evidence-only RLAIF=`DOWNGRADED`；`ADVISOR_CONFIRMATION_REQUIRED=true`用于确认RL是控制策略学习还是必须直接更新Qwen表示。
