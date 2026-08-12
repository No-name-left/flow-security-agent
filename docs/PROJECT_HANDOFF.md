# Flow Security Agent 项目交接指南

> 最近核验：2026-08-13。
>
> 当前长期主线：`main`。Final pre-training acceptance工作以`7225c6ac496e9587a8b1caa2e066379a098d72fc`的线性后代commit按Git policy fast-forward落地；未push。
>
> 当前状态：`TASK_DEFINITION_V2_STATUS=PASS`，`OBSERVABLE_DATASET_V3_STATUS=PASS`，`READY_FOR_FORMAL_SFT=true`，`FORMAL_SFT_STARTED=false`。DEC-0022冻结六类Dataset v3、Evidence-v2、Teacher-v2与14,350-record corpus；旧11类PLAN_B/Teacher V3/V2 corpus及旧formal config继续superseded/fail closed。SFT、RL、Unknown、正式baseline与Agent实验均未运行；当前下一动作是formal Near multi-task SFT。

## 1. 权威链与必读顺序

研究语义冲突时依次服从：

1. `docs/research_plan/research_plan_detailed.md`：Canonical / highest research authority，含DEC-0001至DEC-0021；`docs/research_plan/task_definition_v2.md`是本轮data/Evidence/Teacher详细合同；
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

第一条完整路线仍固定为Edge Near：

- seed：`20260809`；
- 八类pre-model candidate已冻结为六个正式主类：Normal、DDoS_HTTP、DDoS_TCP、Password、SQL_injection、Vulnerability_scanner；MITM与Port_Scanning保留exclusion provenance但不进入主CE；
- U_dev：DDoS_ICMP、OS_Fingerprinting；
- U_final：DDoS_UDP、XSS；
- Backdoor：Long-Horizon Temporal Case Study；Uploading/Ransomware：Observability-Limited/Abstain；三者不进入主classification CE。

verified capture provenance不再作为session observation eligibility。train/validation/test全部使用同一Fine-Class Observation Eligibility Contract；默认保留现有split后逐split过滤。Near后续两次训练、Unknown、Agent、Memory和few-shot主链路不变。

## 4. 数据与Production状态

- `PRODUCTION_DATA_READY=true`；`POSTFIX_PRECOMMIT_AUDIT=PASS_WITH_LIMITATIONS`；
- Edge physical split：`CONSTRAINED_CHRONOLOGICAL_BOUNDARY_V2`；
- train 5,294,777；validation 1,073,539；test 1,110,343；quarantine 140,373；
- 7,619,032 stable Edge identity前后不变；identity cross-split leakage=0；U_final isolation=PASS；
- 24/24 Edge capture label purity=100%；正式7,619,032 session使用`VERIFIED_CAPTURE_FALLBACK`，conflict/unmatched=0；
- 官方CSV不支持稳定frame-exact mapping，论文只能写verified single-label capture provenance + within-capture reconstruction；
- verified capture label不等于每个session具有fine evidence；旧Near/Far/Mixed PLAN_B仅为历史资产；
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
| Basic-v2 | MATERIALIZED / PASS | summary、前1–8 packet metadata、packet-aligned payload、cheap Application |
| Packet expansion | AVAILABLE_PER_SESSION | 已物化packet 9–16，不在Runtime临时读PCAP |
| Temporal-v2 | MATERIALIZED / PASS | 10/60/180/300s strict-past行为统计 |
| Relation-v2 | MATERIALIZED / PASS | session-linked endpoint/MAC ARP/DNS/relation，禁止capture-wide传播 |
| Application-v2 | MATERIALIZED / PASS | 新population真实structured fields |
| Packet-aligned Payload-v2 | MATERIALIZED / PASS | packet index/direction/time/protocol逐条可证 |
| Knowledge RAG | PRETRAINING_INDEX_READY | 30-source generic KB与BM25+dense index已冻结；formal Runtime/Supervisor integration待后续Agent阶段 |

Production identity、paper v2 split、summary、first-16 metadata可直接复用；Evidence-v2需要一次独立、versioned、checkpointed evidence-only PCAP scan，不重新sessionize/canonical。能力缺失仍须fail-closed。

## 6. Qwen部署事实

- `LOCAL_QWEN_DEPLOYMENT_STATUS=PASS`；`LOCAL_QWEN_RAW_SMOKE=PASS`；`RUNTIME_TO_QWEN_REAL_SMOKE=PASS`；
- model：`Qwen/Qwen3.5-9B`；revision `c202236235762e1c871ad0ccb60c8ee5ba337b9a`；
- 16/16 files complete，19,329,393,661 bytes，权重Git-external；
- independent env：`/root/autodl-tmp/conda/qwen35-runtime`；
- vLLM 0.25.1；Torch 2.11.0+cu130；BF16；text-only；8192 context；non-thinking/direct-response；
- audit final health/model service PASS；六类Production、packet 9–16、past-only Temporal和repeated deterministic smoke PASS；GT不进入request；
- deployment audit full pytest：261 passed；CI portability修复后264 passed；Phase B完整server回归：274 passed。

Raw六类smoke没有稳定fine candidate，不是benchmark。vLLM API不暴露hidden states；Fine Head需要Transformers/PEFT training-side harness。

## 7. Training Protocol v1

`TRAINING_PROTOCOL_FROZEN=true`表示架构、权限、阶段和隔离已冻结。Phase B现已冻结`ATTENTION_MASKED_MEAN_V1`、`COMPACT_SAFE_EVIDENCE_V1`、Prompt/schema v2、真实Qwen module inventory与`NEAR_SFT_CONFIG_V1`；这仍不表示正式训练已运行。

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

RAG不是always-on。Observation gap只能由真实packet/Temporal/Graph/Application/Payload回答；knowledge gap才请求Knowledge RAG。第一版已物化30个generic权威源、2,263 chunks与pinned MiniLM BM25+dense hybrid index；SFT snapshot中Knowledge exposure为5.075%，未含dataset/capture/U_final shortcut。

历史PLAN_B Payload/Application sidecar曾覆盖11,481/16,979与7,410/16,979 session；这些数字已superseded，不是v3 formal输入。当前v3 Basic payload为first-8 packet-aligned、bounded、sanitized、untrusted，扩展Evidence为on-demand；完整sidecar保持Git-external，formal online Runtime wiring尚未执行。

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

已实现：Production与split；Safe Adapter/Fidelity；Runtime foundation；provider-neutral LLM boundary；raw Qwen本地/runtime smoke；Transformers/PEFT training harness、dynamic Linear Fine Head、真实LoRA inventory；Dataset v3/Evidence-v2；Teacher-v2与corpus-v3；generic RAG KB/index；正式训练代码路径的真实9B BF16 LoRA四步disposable runtime smoke、checkpoint完整恢复与U_final隔离audit。旧PLAN_B/22,957 snapshot/6,000 RL pool仅为historical。

历史DEC-0020 acceptance曾验证Teacher V3 22,957/22,957及V2 corpus 22,957 records / 16,979 sessions，现已superseded。当前DEC-0022 acceptance验证Teacher-v2 20,807/20,807、formal corpus 14,350 records / 11,958 sessions、3,231 EXACT_EVAL_CLEAN validation、token/weight/label/isolation/plan Gates。未完成/未运行：formal online Runtime Application/Payload/RAG tool wiring、正式传统/Raw baseline、SFT、GRPO、Independent Unknown、Agent benchmark、Experience/Class Memory实验与论文结果。

状态：

- `SFT_RUN=false`
- `RL_RUN=false`
- `UNKNOWN_ALGORITHM_FROZEN=false`
- `TOKENIZER_TRAINED=false`
- formal benchmark：NOT RUN

## 11. 下一实施阶段与停止规则

**CURRENT STOP POINT：FORMAL_NEAR_SFT_RUNTIME_PREFLIGHT_PASS。**

`CLASSIFICATION_SUFFICIENCY_DECOUPLED_MULTI_GAP_V2`已冻结：每个formal TRAIN session恰有一个Basic-v2 primary计算classification CE，无论Teacher `evidence_sufficient`；2,392个controlled richer auxiliary仅训练Evidence LM并mask CE。GT保持backend-only，不进入serialized input、Prompt、RAG query、Payload或model-visible metadata。

历史Teacher V3/V2 corpus统计为250 pilot、22,957 bulk、16,979 sessions及11类，明确只作superseded审计证据。正式Teacher-v2为40-state pilot与20,807/20,807 bulk、quarantine 0；formal trajectory为14,350 records / 11,958 sessions / 6类，token max 4,794<8,192，overflow/label collision/backend identity/GT-key/U_final均为0，120-record分层可读审计PASS。

旧`NEAR_SFT_CONFIG_V1`保持`formal_run_authorized=false`。新`NEAR_SFT_CONFIG_V2`指向六类corpus与EXACT_EVAL_CLEAN validation；全部硬Gate和plan consistency已通过。2026-08-13真实runtime preflight确认base/LM Head冻结、LoRA/Fine Head梯度与optimizer边界、session weighting、多任务loss、BF16显存、checkpoint恢复和validation路径均PASS；formal output仍未创建，`FORMAL_SFT_STARTED=false`。报告为`reports/training_readiness/formal_near_multitask_sft_runtime_preflight.md`。下一任务是`START_FORMAL_NEAR_MULTI_TASK_SFT`；仍禁止提前运行GRPO、Unknown、U_final、Agent、Far/Mixed/IoT-23或few-shot实验。

## 12. Git与环境提示

本轮实现通过`feat/task-v2-clean-dataset`完成完整回归、secret/large-file审查及最终preflight后显式commit，并按仓库策略`--ff-only`落地local main；未push。最终报告入口为`reports/training_readiness/observable_dataset_v3_final_pretraining_acceptance.md`；旧acceptance报告作为历史审计记录保留。

数据环境：`/root/autodl-tmp/conda/flow-data`。Qwen training/runtime环境：`/root/autodl-tmp/conda/qwen35-runtime`。Production v2 root通过现有`ARTIFACT_ROOT`约定解析，正式v3 Git-external root为`$ARTIFACT_ROOT/near_pretraining_v3`；GitHub CI无外部资产时真实数据测试安全skip。DeepSeek只读runtime环境中的`DEEPSEEK_API_KEY`，不得写入repo/report/log。

## 13. 新接手者自检

阅读权威链后，应能回答：为什么Near先跑；Qwen训练两次分别训练什么；Fine Head/LM Head/coarse mapping如何分工；为什么Fine correctness不是GRPO组内reward；Unknown何时冻结且为何不训练Qwen；U_dev/U_final权限；DeepSeek三个角色与Codex职责；RAG何时调用；Payload为何允许但按需受限；Supervisor为何不能分类；Runtime为何是authority；Experience/Class Memory差异；当前做到哪里；下一阶段是什么；哪些事情不能提前做。
