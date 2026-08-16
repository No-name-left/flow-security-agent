# Open-World Continually Evolving LLM Traffic Agent

> 状态：DEC-0025 architecture + DEC-0027 experiment/control freeze
>
> 日期：2026-08-15
>
> Model B representation与objectives见[model_b_evidence_openworld_design.md](model_b_evidence_openworld_design.md)，最高研究语义见[research_plan_detailed.md](research_plan_detailed.md)。

## 1. Architecture reframe

系统不把“Basic下难分类”直接等同Unknown，也不让Teacher主观sufficiency直接控制取证。正式链路是：

```text
Traffic Evidence
→ Known classification + empirically learned Evidence utility
→ selective typed-Evidence recovery
→ independent novelty detection
→ residual Unknown handling
→ verified-feedback continual evolution
```

这对应三个互相依赖但可独立评测的层：Evidence-conditioned recognition、OOF utility-grounded acquisition、Evidence-gated continual evolution。

## 2. Status registry

### CONFIRMED

- Model A closed-set classification成功，Evidence-State branch对目标用途失败；
- official NF3-ToN final artifact reconciliation/schema/labels通过，raw reprocessing不需要；
- 24k pilot中recoverable Known存在，utility prediction有clear signal；
- aggregate Evidence-conditioned novelty降低recoverable-Known FURK；
- verified feedback先于semantic class registration与model adaptation；
- Unknown不作为Fine Head中的普通K+1类。

### PROVISIONAL

- Qwen内Utility Head或external selector；
- fresh或Model-A warm start；
- exact trainable modules、loss、cost coefficient与threshold；
- MSP、margin、energy、prototype distance中的最终novelty方法；
- clustering、continual update cadence与release thresholds。

### DEPRECATED / NOT AUTHORIZED

- Teacher-v2 semantic Evidence State作为Model B operational utility GT；
- permanent online DeepSeek Supervisor作为必需组件；
- Model A LM Evidence-State作为正式acquisition controller；
- 默认warm-start、Evidence-only RLAIF或LLM-level RL；
- self-label或confidence驱动class registration；
- 把observability-limited样本当True Unknown；
- 为core下载CICIoT2023或重处理raw CIC/ToN。

## 3. Three-plane architecture

### Plane A — Perception and recovery

```text
Current Evidence
→ Qwen traffic representation h
→ Fine Head / Known logits
→ utility estimate for available Evidence families
→ optional evidence acquisition and re-evaluation
→ independent novelty score
```

Core families是Basic、Temporal和Relation。Semantic Admissibility由deterministic network contract保证；Operational Utility由OOF/cross-fitted prediction improvement监督。Application、Payload和Knowledge只有在数据/utility Gate通过后加入。

### Plane B — Agent control

Controller拥有classification state、utility state、available Evidence、novelty score、budget和history，但没有GT或hidden oracle权限。它一次只执行一个动作：

```text
STOP_AND_CLASSIFY
ACQUIRE_TEMPORAL
ACQUIRE_RELATION
ENTER_NOVELTY_DETECTION
```

`BUFFER_UNKNOWN`、`REQUEST_LABEL`、`REGISTER_NEW_CLASS`和`TRIGGER_CONTINUAL_ADAPTATION`属于Plane C的slow control。Runtime负责capability、past-only/causal boundary、cost、budget、dedup、trace和permission enforcement。强基线policy是deterministic/supervised utility-driven；正式协议还计划一个低成本fast RL Gate。RL不构成recognition入口依赖，也不更新Qwen。

### Plane C — Evolution

```text
Residual Unknown
→ Unknown Buffer
→ optional clustering
→ verified feedback
→ Class Registry update
→ supervised adaptation + old replay
→ release gate / rollback
```

Plane C维护Unknown Buffer、Verified Feedback Store、Replay Buffer、Class Registry和Model Version Registry。只有verified-label supervised update后通过old/new/Unknown/domain-stress Gate的`B_t → B_t+1`才是continual evolution；Memory或RAG更新不等于参数进化。

## 4. State machine

### 4.1 Formal states

| Evaluation state | Recognition meaning | Preferred control path |
| --- | --- | --- |
| `BASIC_SUFFICIENT_KNOWN` | Basic已足够正确识别Known | stop/classify |
| `RECOVERABLE_KNOWN` | Basic不可靠，额外合法Evidence恢复Known | acquire/re-evaluate/classify |
| `TRUE_UNKNOWN` | whole class held out且Full可观测 | recover if worthwhile, then novelty |

### 4.2 Unknown-after-Evidence invariant

`ENTER_NOVELTY_DETECTION`必须发生在以下任一条件后：有价值且可用的Evidence已获取；没有admissible family；utility低于预注册cost-aware条件；或budget耗尽。系统不得因一次Basic uncertainty直接buffer Unknown。

### 4.3 Hidden oracle boundary

held-out official label仅用于离线评价。Runtime只有在显式`REQUEST_LABEL`并模拟/接收verified feedback后，才向continual subsystem暴露label；该label永远不回流到同一时刻的selector或novelty decision。

## 5. Utility selector interface

输入可包括representation、Known probability distribution、confidence、margin、entropy、current Evidence families、availability、cost和history。禁止使用GT class、source identity或future information。

输出应至少支持每个available family的predicted utility和stop/acquire comparison。允许class-/hypothesis-conditioned行为，但只能使用predicted distribution而非真实类。当前pilot显示Recon_Scanning、Web_Injection和Credential方向不一致，因此formal evaluation必须per-class，不得只报告aggregate。

## 6. Novelty detector interface

novelty detector读取Known representation/logits与recovery state，不改写Fine Head为K+1。threshold只用Known development与预注册U_dev/held-out development classes选择；final whole-class Unknown不得参与threshold tuning。

第一轮保持简单：MSP、margin、energy、prototype distance。只有互补性和robustness得到证明后才考虑fusion。报告AUROC/AUPR、OSCR、FPR/recall operating points及Known performance。

## 7. DeepSeek, explanation and RAG

DeepSeek仅允许：offline semantic reviewer、optional policy demonstrations、optional explanation generator、optional supervisor baseline。它不产生Model B utility GT、不接收runtime GT、不替代Fine Head。

Structured Evidence State若保留，只作解释层，不控制正式runtime。RAG与Observation分离并做stage-aware future-knowledge exclusion；未verified的新类名称/signature不能提前进入KB。

## 8. Continual protocol

1. Buffer residual novelty并记录recovery trace；
2. 可选clustering只帮助组织query，不自动赋semantic class；
3. analyst/external oracle提供verified labels；
4. 多条一致证据满足registration rule后更新Class Registry；
5. 使用new-class samples与balanced old replay进行supervised adaptation；
6. 比较head-only与parameter-efficient update；
7. old Known、新类、Unknown和domain stress回归均通过才release，否则rollback。

后续指标包括Unknown Buffer purity、ARI/NMI（若clustering）、new-class learning、old-class forgetting、query count和release failure。当前实现状态是`LITERATURE_SUPPORTED_IMPLEMENTATION_PENDING`。

## 9. Fast RL boundary

RL只优化已定义四动作空间中的sequential cost-quality tradeoff，不负责学习攻击语义。强utility heuristic/supervised policy仍是必须击败的基线；首个学习算法为Double DQN，可选Dueling/PER。若RL不显著改善效果或成本，它作为negative result退出突出贡献，不改变核心方法。

```text
RL_STATUS=PLANNED_LOW_COST_AGENT_POLICY_COMPONENT_PENDING_FORMAL_GATE
LLM_LEVEL_RL=NOT_PLANNED_FOR_CORE
```

fast policy state只含合法representation/logits/confidence/margin/entropy、OOF utility estimates、novelty/evidence mask、availability与budget。离线环境可用GT计算reward，但policy observation不得看到GT。完整P0–P4 baseline、reward边界、seeds和Gate见[experiment_protocol_v1.md](experiment_protocol_v1.md)。PPO、GRPO、RLAIF和direct Qwen RL均不属于core。

## 10. Required comparisons and metrics

Controller/novelty必须比较Direct novelty、Always acquire Full和Utility-conditioned acquisition。关键方法指标为FURK、Evidence Recovery Rate、Acquisition Rate、Average Acquisition Cost和Known accuracy after recovery；结合Macro-F1、Unknown AUROC/AUPR与OSCR。

continual阶段必须与no-adaptation、new-only、replay adaptation等合理基线比较。不得通过削弱Always-Full、heuristic或small-model baseline制造优势。

## 11. Current data roles

`NF3-ToN-IoT`是Dataset-v4 core priority。`NF3-UNSW-NB15`、`NF3-BoT-IoT`、`NF3-CSE-CIC-IDS2018`是secondary external-domain stress/replication candidates；weak/domain-dependent cross-source result如实保留但不阻塞core。Edge Model A是legacy controlled baseline和optional replay source。

## 12. Immediate stop point

Dataset-v4 B1与formal experiment design已冻结；pre-price Teacher cache v1（2,000）与semantic reference v1（63）已于2026-08-17生成完毕（`TEACHER_CACHE_STATUS=FROZEN_COMPLETE_2000_VALID`、`SEMANTIC_REFERENCE_STATUS=FROZEN_COMPLETE_63_VALID`）。下一步是准备duplicate-aware views和Model B low-cost Gates。本文不授权启动Qwen、continual、RL、新下载或raw PCAP处理。
