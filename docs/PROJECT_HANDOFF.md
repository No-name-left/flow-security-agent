# Flow Security Agent 项目交接指南

> 最近核验：2026-08-11。
>
> 当前文档同步分支：`docs/sync-near-mainline-protocol`，基于`main`已审计提交`e28c3f4806aa56dcdeb9e561cf6201e71f98a2a5`（其父提交`ec191725...`为Qwen部署审计）。本分支不push。
>
> 当前状态：Production、Edge v2 split、PLAN_B、Runtime Safe Adapter、Evidence Fidelity和官方raw Qwen部署smoke已完成；Near Training Protocol v1已在架构/权限层冻结；SFT、RL、Unknown、正式baseline与Agent实验均未运行。

## 1. 权威链与必读顺序

研究语义冲突时依次服从：

1. `docs/research_plan/research_plan_detailed.md`：Canonical / highest research authority，含DEC-0001至DEC-0019；
2. `docs/training/near_mainline_training_protocol_v1.md`：training/Open-world execution authority；
3. `docs/design/agent_architecture_provisional.md`：Agent/Runtime/Supervisor/RAG/Memory design authority，不能覆盖前两者；
4. 本文件：只记录实际完成状态、阻塞和下一步；
5. timeline/brief、audit/manifest与历史报告。

未来涉及training/model/Unknown前先读1、2；涉及Runtime/Supervisor/RAG/Memory再读3；最后用本文件核实实现状态和最新审计。历史报告中的Reviewer、QLoRA default或并行多preset路线不覆盖DEC-0019。

## 2. 当前论文主线

```text
Production Session
→ Runtime Safe Adapter
→ legal Evidence Stage
→ Qwen shared language representation
→ Fine Classification Head + LM Evidence State
→ deterministic fine→coarse mapping
→ Independent Unknown
→ DeepSeek Flash Supervisor
→ one Runtime Evidence action
→ Qwen re-evaluate
→ Known Fine / Coarse / Unknown / Abstain
→ optional human label + Class Memory
```

Qwen是第一分类器，不是LightGBM/XGBoost reviewer。正式trained model使用冻结Qwen base + LoRA + 一个Linear Fine Head + 保留LM Head：Fine Head唯一决定known fine class，coarse由确定性映射得到；LM Head只输出supporting/missing evidence、sufficiency、gap和必要backoff状态。

Unknown不是K+1类。它在primary Qwen冻结后，只用Known validation与U_dev开发独立评分/阈值。Supervisor不是第二分类器，不能覆盖Fine Head，只能请求证据、要求Qwen重评、backoff、reject或abstain。Runtime是权限与执行authority。

## 3. ONE_MAINLINE_FIRST

第一条完整路线固定为Edge Near：

- seed：`20260809`；
- K_known：Backdoor、DDoS_HTTP、DDoS_TCP、MITM、Normal、Password、Port_Scanning、Ransomware、SQL_injection、Uploading、Vulnerability_scanner；
- U_dev：DDoS_ICMP、OS_Fingerprinting；
- U_final：DDoS_UDP、XSS；
- SFT：PLAN_B，16,979个唯一`K_known ∩ physical train`候选。

不得重选K/U、split、seed或PLAN A/B/C。Near必须先完成两次训练、Unknown、Agent、Memory和1/5/10-shot闭环；Far、Mixed、IoT-23、Pure Generative SFT、DPO、Tokenizer/QLoRA/thinking、Low-Resource stress、LearnablePolicy RL和continual LoRA均延后到`NEAR_MAINLINE_COMPLETE=true`之后。

## 4. 数据与Production状态

- `PRODUCTION_DATA_READY=true`；`POSTFIX_PRECOMMIT_AUDIT=PASS_WITH_LIMITATIONS`；
- Edge physical split：`CONSTRAINED_CHRONOLOGICAL_BOUNDARY_V2`；
- train 5,294,777；validation 1,073,539；test 1,110,343；quarantine 140,373；
- 7,619,032 stable Edge identity前后不变；identity cross-split leakage=0；U_final isolation=PASS；
- 24/24 Edge capture label purity=100%；正式7,619,032 session使用`VERIFIED_CAPTURE_FALLBACK`，conflict/unmatched=0；
- 官方CSV不支持稳定frame-exact mapping，论文只能写verified single-label capture provenance + within-capture reconstruction；
- Near/Far/Mixed PLAN_B分别16,979/15,895/15,404；当前只允许推进Near；
- DDoS_UDP与OS_Fingerprinting的structural-diversity limitation仍有效，不改变K/U；
- Edge多数attack class单capture/run，不能声称跨攻击run泛化；IoT-23仍是后续独立scenario外部验证数据集，不与Edge物理合并。

大数据、PCAP、Parquet、checkpoint和完整报告保持Git-external，不得进入Git。

## 5. Runtime与Evidence实现状态

`PRODUCTION_RUNTIME_ADAPTER_STATUS=PASS`；`PRODUCTION_RUNTIME_ADAPTER_READY=true`。

- Adapter：`production_runtime_adapter_v1`；
- Evidence schema：`production_runtime_evidence_v1`；
- `ADAPTER_EVIDENCE_FIDELITY_GATE=PASS`；
- backend sample ID、dataset/split/K-U、GT、source/capture hash与定位不进入Qwen/Supervisor。

| Capability | 当前工程状态 | 含义 |
| --- | --- | --- |
| Initial Evidence | AVAILABLE | 前1–8 packet metadata + whole-session safe summary |
| Packet expansion | AVAILABLE_PER_SESSION | 已物化packet 9–16，不在Runtime临时读PCAP |
| Temporal | AVAILABLE | strict past-only |
| Graph/Relation | AVAILABLE_WITH_LIMITATION | 匿名角色与真实repeated relation |
| Application | UNAVAILABLE | 最终Near需实现真实结构化应用字段 |
| Sanitized Payload | UNAVAILABLE | 最终Near需实现有界按需sanitizer |
| Production RAG | UNAVAILABLE | 最终Near需实现冻结KB/retriever/tool |

后三项UNAVAILABLE是当前工程事实，不是永久禁用。任何能力缺失必须fail-closed并显式报告，不能临时从PCAP/Payload补造。

## 6. Qwen部署事实

- `LOCAL_QWEN_DEPLOYMENT_STATUS=PASS`；`LOCAL_QWEN_RAW_SMOKE=PASS`；`RUNTIME_TO_QWEN_REAL_SMOKE=PASS`；
- model：`Qwen/Qwen3.5-9B`；revision `c202236235762e1c871ad0ccb60c8ee5ba337b9a`；
- 16/16 files complete，19,329,393,661 bytes，权重Git-external；
- independent env：`/root/autodl-tmp/conda/qwen35-runtime`；
- vLLM 0.25.1；Torch 2.11.0+cu130；BF16；text-only；8192 context；non-thinking/direct-response；
- audit final health/model service PASS；六类Production、packet 9–16、past-only Temporal和repeated deterministic smoke PASS；GT不进入request；
- deployment audit full pytest：261 passed；当前仓库在后续CI portability修复后完整server回归：264 passed。

Raw六类smoke没有稳定fine candidate，不是benchmark。vLLM API不暴露hidden states；Fine Head需要Transformers/PEFT training-side harness。

## 7. Training Protocol v1

`TRAINING_PROTOCOL_FROZEN=true`表示架构、权限、阶段和隔离已冻结，不表示训练已运行或数值已选。

Training #1：classification-first Multi-task SFT。

```text
L_SFT = lambda_cls * Fine Head CE + lambda_ev * Evidence generation
```

Official/verified GT只监督分类；Evidence targets来自规则、controlled masking/stages、DeepSeek Flash Teacher、consistency filtering和bounded human audit。Teacher不能决定标签或创造Observation。

Training #2：从独立保存的SFT checkpoint继续`RLAIF-GRPO + classification CE preservation`。GRPO优化grounding、sufficiency、missing evidence、gap、backoff/abstention、幻觉与schema；Fine correctness在同input rollout group中不变化，所以不是主要group-relative reward。分类由独立CE保持。

Checkpoint lineage：

```text
Official Base @ c202236...
→ Checkpoint A: Near Multi-task SFT LoRA + Fine Head
→ clone/reference A
→ Checkpoint B: Near SFT + RLAIF-GRPO LoRA + Fine Head
→ freeze Qwen → Independent Unknown → Agent integration
```

不得覆盖Checkpoint A；base、adapter、Fine Head、config、data digest、Prompt/serialization、class map、seed和software versions全部记录。

## 8. DeepSeek、RAG、Payload与Memory

当前可配置外部高能力default是DeepSeek Flash，分为三个逻辑隔离角色：

- Teacher：train/development Evidence target；
- Judge：current-policy GRPO rollout semantic reward；
- Supervisor：formal inference action selection，永远无GT。

三者必须独立Prompt、Schema、permissions、cache和logs。Codex负责provider abstraction、调用、retry/rate-limit/batch/cache、验证、实验和审计，不是正式Teacher/Judge。

RAG不是always-on。Observation gap只能由真实packet/Temporal/Graph/Application/Payload回答；knowledge gap才请求Knowledge RAG。第一版KB只含generic protocol/RFC、attack、CVE/security与threat knowledge，不得含dataset/capture/U_final shortcut。

Payload默认不给，只能on-demand、bounded、protocol-aware、sanitized、untrusted，并在TRAIN/legal validation上完成`PAYLOAD_SHORTCUT_RISK` audit。

Experience Memory只存externally verified TRAIN `State→Action→Outcome`，validation/test/U_final只读。Class Memory单独保存人工/oracle 1/5/10-shot新类support与prototype；第一版不continual LoRA。

## 9. U_final与评测隔离

在第一次打开Near U_final前，必须冻结所有会影响该route的：

- Prompt、serialization、pooling、LoRA和训练超参；
- Teacher/Judge rubric；
- Unknown算法与threshold；
- Payload sanitizer；
- KB/RAG/top-k/query policy；
- Supervisor prompt/budget/policy；
- Memory retrieval settings。

打开后不得反向调任何开发参数。涉及Temporal/Graph/Memory的formal evaluation按capture/scenario chronological order；一个reconstructed session对应一个primary result。

## 10. 已实现与未实现

已实现：Production与split；PLAN_B；Safe Adapter/Fidelity；Runtime foundation；provider-neutral LLM boundary；raw Qwen本地/runtime smoke；通用cache/resume/trace和RAG ingestion foundation。

未实现：training-side Fine Head/harness；正式Prompt/schema/serialization；Application/Payload/Production RAG；DeepSeek Teacher/Judge/Supervisor formal calls；正式传统/Raw baseline；SFT；GRPO；Independent Unknown；Agent benchmark；Experience/Class Memory实验；论文结果。

状态：

- `SFT_RUN=false`
- `RL_RUN=false`
- `UNKNOWN_ALGORITHM_FROZEN=false`
- `TOKENIZER_TRAINED=false`
- formal benchmark：NOT RUN

## 11. 下一实施阶段与停止规则

**NEXT IMPLEMENTATION PHASE：Phase B — Training Protocol Readiness。**

只应实现：

1. Transformers/PEFT training-side harness与Linear Fine Head；
2. classification pooling小规模validation-safe选择；
3. Qwen3.5 real module inventory LoRA assertion；
4. current vs compact safe serialization并冻结`SERIALIZATION_V1`；
5. Traffic Expert Prompt/response schema v1；
6. Application/Payload contracts；
7. RAG Evidence Contract。

本次文档任务不授权启动Raw benchmark、传统正式baseline、DeepSeek批量Teacher/Judge、SFT、GRPO、Unknown、U_final、Agent或few-shot实验。

绝对禁止：修改Production、split、K/U、PLAN_B；用test/U_final调参；把Unknown作为K+1类；让Teacher决定GT；让Supervisor改fine label；让RAG发明Observation；默认每样本RAG；无限raw Payload；把model/data/cache/log/checkpoint提交Git。

## 12. Git与环境提示

当前docs分支基于`e28c3f4`，包含Qwen部署提交`ec19172`和CI portability修复。不要假设历史短期分支仍是唯一最新状态。禁止reset/rebase/clean/force push；本任务不push。

数据环境：`/root/autodl-tmp/conda/flow-data`。Qwen inference环境：`/root/autodl-tmp/conda/qwen35-runtime`。Production v2 root通过现有`ARTIFACT_ROOT`约定解析，GitHub CI无Git-external资产时真实数据测试应安全skip。

## 13. 新接手者自检

阅读权威链后，应能回答：为什么Near先跑；Qwen训练两次分别训练什么；Fine Head/LM Head/coarse mapping如何分工；为什么Fine correctness不是GRPO组内reward；Unknown何时冻结且为何不训练Qwen；U_dev/U_final权限；DeepSeek三个角色与Codex职责；RAG何时调用；Payload为何允许但按需受限；Supervisor为何不能分类；Runtime为何是authority；Experience/Class Memory差异；当前做到哪里；下一阶段是什么；哪些事情不能提前做。
