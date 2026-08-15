# Model B：Evidence-Conditioned Open-World Design

> 状态：DEC-0025 canonical architecture design
>
> 日期：2026-08-15
>
> 本文冻结问题定义、接口、实验Gate与安全边界，不冻结最终超参数或算法选择。实现与训练尚未开始。

## 1. 目标与非目标

Model B研究的问题不是普通closed-set分类，也不是“用了Qwen”本身。它研究：当Basic Evidence不足时，系统能否先预测哪类合法Evidence值得付费获取，恢复被低观测掩盖的Known，再仅对recovery后仍不像Known的样本执行novelty detection。

```text
Evidence-Conditioned Open-World Traffic Recognition
+ Empirically Grounded Typed-Evidence Acquisition
+ Evidence-Gated Continual Evolution
```

当前非目标包括：启动正式Model B训练、在线DeepSeek控制、LLM级RL、raw PCAP重处理、把多源弱泛化强行做成核心结论，以及在无verified label时自更新模型。

## 2. 数据与三种状态

核心优先数据是官方NF3-ToN-IoT final processed artifact：

```text
SHA256=53ec8f468a43ede9b1536fabc0390af2fa33ab4312b23ce4d864f186a4651f78
```

候选taxonomy为Benign、Backdoor、Credential、DDoS、DoS、Recon_Scanning和Web_Injection；它需在formal split、support和robustness Gate后才冻结。

每个正式样本只属于下列evaluation state之一：

| State | 定义 | 正确路径 |
| --- | --- | --- |
| `BASIC_SUFFICIENT_KNOWN` | Basic已足够可靠预测Known | `STOP_AND_CLASSIFY` |
| `RECOVERABLE_KNOWN` | Basic不可靠，合法额外Evidence可恢复Known | `ACQUIRE_EVIDENCE`后分类 |
| `TRUE_UNKNOWN` | whole class未参与训练/threshold tuning，Full合法Evidence可观测 | recovery exhausted/not worthwhile后进入novelty |

`OBSERVABILITY_LIMITED`、GT不可解释或Full Evidence仍无法承载标签的样本不能当True Unknown。

## 3. 输入与Evidence接口

### 3.1 Semantic Admissibility

每个Evidence family必须label-free、test-time available、causal/past-only且具有合法网络语义。admissibility由deterministic protocol与必要的offline expert/DeepSeek review决定，只说明“可以看”，不说明“值得看”。

### 3.2 Operational Utility

utility target必须由OOF/cross-fitted模型结果产生。对family `E_j`比较同一sample的Basic与Basic+`E_j`，候选target包括`ΔNLL`和correctness recovery；任何target都不能由训练过该sample的probe产生。后续cost-aware score可以写作：

```text
U(E_j | x) = predicted decision improvement - λ × acquisition cost
```

具体loss、λ、threshold和标定方法由pilot预注册，不在设计文档中猜定。

### 3.3 Families

第一轮核心输入只包括：

- `Basic`：当前可直接取得的合法基础流量表示；
- `Temporal`：bounded、causal/past-only统计；
- `Relation`：sample-local或合法历史关系结构。

Application、Payload和Knowledge为optional extension，只有数据存在、语义合法且OOF utility为正时才进入正式action space。当前pilot的“Full”仅为bounded sample-local Temporal+Relation，不代表最终Runtime Full。

## 4. 候选模型结构

```text
Current Evidence
      ↓
Qwen traffic backbone + trainable adaptation
      ↓
shared representation h
      ├── Fine Classification Head → Known logits
      └── optional small Utility Head → utility per available family

h / Known logits / confidence / recovery state
      ↓
independent Novelty Detector
```

Fine Head只预测Known classes。Unknown不是普通`K+1`类别；novelty detector在Evidence gate之后读取representation/logits与recovery state。第一轮候选仅为MSP、margin、energy与prototype distance。

Utility有两种等价候选接口：

1. `h → small Utility Head`；
2. `Basic h/logits/confidence → external small utility selector`。

先采用满足科学问题的最简单实现；只有joint/shared utility learning经matched comparison获益，才进一步绑定Qwen内部表示。

## 5. 冻结与可训练边界

第一轮候选保留Qwen backbone、parameter-efficient adaptation和linear Fine Head，但exact trainable modules由B2 pilot决定。Model A LoRA不是默认初始化；fresh与Model-A warm-start必须使用相同样本、steps、optimizer budget、heads和评估。

以下不在本阶段冻结：LoRA rank、learning rate、loss权重、utility architecture、cost coefficient、novelty算法、threshold、held-out rotations及最终Evidence窗口。Model B不得继承Model A失败的generative Evidence-State目标作为operational utility supervision。

## 6. Objectives

### 6.1 Classification objective

只在Known training classes上优化Fine classification。class/sample weighting、taxonomy和split在Dataset-v4 formalization时冻结；whole-class Unknown不进入该objective。

### 6.2 Utility objective

以OOF/cross-fitted marginal utility target训练小型selector/head，目标是预测当前sample获取哪个admissible family会改善决策。必须记录无效获取、acquisition cost和family availability；不得使用GT class作为runtime selector输入。

### 6.3 Novelty objective/interface

U_dev或等价development-only Unknown用于算法与threshold选择；final held-out Unknown不参与训练或调参。novelty只在controller决定recovery exhausted/not worthwhile后运行。

## 7. Runtime controller

Controller读取Known logits/representation、utility estimates、available Evidence、novelty score、budget与history，输出一个受约束动作：

```text
STOP_AND_CLASSIFY
ACQUIRE_EVIDENCE(E_j)
ENTER_NOVELTY_DETECTION
BUFFER_UNKNOWN
REQUEST_LABEL
TRIGGER_CONTINUAL_ADAPTATION
```

首版是deterministic或supervised utility-driven policy。Runtime验证family availability、causality、预算、重复请求与trace。DeepSeek可做offline semantic reviewer、policy demo、explanation或optional supervisor baseline，但不是utility oracle。

## 8. Training stages

1. **B1 Dataset-v4 formalization：**冻结artifact identity、taxonomy、grouped/temporal split、Known/Unknown rotations、Evidence availability与leakage contract。
2. **B2 Static Model B：**完成fresh-vs-warm、Qwen-vs-small、structured/Frozen-Qwen baseline和简单novelty comparison。
3. **B3 Typed-Evidence utility：**单family/combined OOF targets、selector、second seed/bootstrap与cost sensitivity。
4. **B4 Open-world evaluation：**Direct、Always Full和Utility-conditioned三路matched comparison。
5. **B5 Continual evolution：**verified feedback、supervised adaptation+replay和regression-gated release。
6. **B6 Optional RL：**只有supervised/heuristic controller留下明确、可重复的策略改进空间时比较small RL；LLM RL未授权。

## 9. 必需低成本消融

- fresh Model B vs Model-A warm start；
- Qwen vs smaller traffic encoder/strong structured baseline；
- Basic、Basic+Temporal、Basic+Relation、Basic+Temporal+Relation；
- first seed结论的second-seed/bootstrap robustness；
- MSP、margin、energy、prototype distance的development-only comparison；
- Direct novelty、Always acquire Full、Utility-conditioned acquisition。

不得用当前24k pilot替代这些formal gates。

## 10. Metrics与class-conditional报告

分类/开放集指标至少包括Macro-F1、Unknown AUROC/AUPR与OSCR。方法特定指标至少包括：

- False Unknown on Recoverable Known（FURK）；
- Evidence Recovery Rate；
- Evidence Acquisition Rate；
- Average Acquisition Cost；
- Known accuracy after recovery。

所有指标必须overall和per-class报告。当前Recon_Scanning、Web_Injection和Credential的相反收益方向证明统一policy未必成立；selector可用predicted class distribution、representation、confidence、margin、entropy和current evidence做sample-/hypothesis-conditioning，但不能看GT。

## 11. Continual interface

```text
Residual Unknown → Unknown Buffer → optional clustering
→ verified feedback → REGISTER_NEW_CLASS
→ supervised adaptation + old replay
→ old/new/Unknown/domain-stress release gate
→ Model B_t+1 or rollback
```

Memory增长、聚类紧致度或self-confidence不是模型进化。只有verified labels驱动参数更新且通过release gate才算continual evolution。当前状态为`LITERATURE_SUPPORTED_IMPLEMENTATION_PENDING`。

## 12. Acceptance边界

概念可行性为`PASS_WITH_LIMITATIONS`。正式实现前仍须通过Dataset-v4 formalization、low-cost architecture gates、single-family/combined utility、多seed/bootstrap、whole-class Unknown protocol和class-conditional limitation审查。当前文档不授权Model B训练、continual、RL、DeepSeek调用、数据下载或raw PCAP处理。
