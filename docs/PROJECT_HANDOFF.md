# Flow Security Agent 项目交接指南

> 最近核验：2026-08-12。
>
> 当前实现分支：`feat/near-pretraining-readiness-v1`，基于已进入`main`的文档同步提交`ff4eca8fc6e00196666a9a3768679e3ddfefea60`。本分支只提交代码、配置、schema、测试、小型报告和状态文档，不push。
>
> 当前状态：Production、Edge v2 split、PLAN_B、Runtime Safe Adapter、Evidence Fidelity和官方raw Qwen部署smoke保持完成；Near Phase B的非API准备（training harness、Fine Head、pooling/LoRA/serialization、Prompt/schema、Application/Payload sidecar、formal RAG、snapshot universe、RL prompt pool与真实9B两步dry-run）已完成。`DEEPSEEK_API_KEY`缺失是Teacher annotation与最终SFT corpus的唯一blocker；SFT、RL、Unknown、正式baseline与Agent实验均未运行。

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
| Application | TRAINING_SIDECAR_READY | `APPLICATION_EVIDENCE_V1`已从合法K-known TRAIN PCAP materialize；formal Runtime tool wiring待后续Agent阶段 |
| Sanitized Payload | TRAINING_SIDECAR_READY | `SANITIZED_PAYLOAD_V1`有界、脱敏、按需；formal Runtime tool wiring待后续Agent阶段 |
| Knowledge RAG | PRETRAINING_INDEX_READY | 30-source generic KB与BM25+dense index已冻结；formal Runtime/Supervisor integration待后续Agent阶段 |

后三项已从contract-only推进为Git-external预训练资产，但不能误写成正式Agent Runtime已集成。能力缺失仍须fail-closed并显式报告，不能在在线路径临时从PCAP/Payload补造。

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

`TRAINING_PROTOCOL_FROZEN=true`表示架构、权限、阶段和隔离已冻结。Phase B现已冻结`ATTENTION_MASKED_MEAN_V1`、`COMPACT_SAFE_EVIDENCE_V1`、Prompt/schema v1、真实Qwen module inventory与`NEAR_SFT_CONFIG_V1`；这仍不表示正式训练已运行。

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

Payload默认不给，只能on-demand、bounded、protocol-aware、sanitized、untrusted。当前合法Near TRAIN sidecar覆盖11,481/16,979 session（67.619%），Application覆盖7,410/16,979（43.642%）；`PAYLOAD_SHORTCUT_AUDIT=PASS`、risk=LOW。完整sidecar保持Git-external，formal Runtime wiring尚未执行。

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

已实现：Production与split；PLAN_B；Safe Adapter/Fidelity；Runtime foundation；provider-neutral LLM boundary；raw Qwen本地/runtime smoke；Transformers/PEFT training harness、dynamic Linear Fine Head、真实LoRA inventory、pooling/serialization/Prompt/schema v1；Application/Payload Git-external sidecar；generic RAG KB/index；22,957个合法snapshot、6,000条RL prompt pool；真实9B两步可逆dry-run与U_final隔离audit。

未实现/未运行：DeepSeek provider smoke、Teacher pilot/bulk与最终Teacher-grounded SFT corpus（唯一原因是无`DEEPSEEK_API_KEY`）；formal Runtime Application/Payload/RAG tool wiring；正式传统/Raw baseline；SFT；GRPO；Independent Unknown；Agent benchmark；Experience/Class Memory实验；论文结果。

状态：

- `SFT_RUN=false`
- `RL_RUN=false`
- `UNKNOWN_ALGORITHM_FROZEN=false`
- `TOKENIZER_TRAINED=false`
- formal benchmark：NOT RUN

## 11. 下一实施阶段与停止规则

**CURRENT STOP POINT：Phase B provider-blocked finalization。**

只允许在用户提供runtime `DEEPSEEK_API_KEY`后继续以下固定顺序：

1. `provider-status`完成model-list与structured-response smoke；
2. 分层250条Teacher pilot，自动grounding/schema检查并要求零quarantine；
3. bulk Teacher annotation与cache/resume；
4. final SFT corpus join、token gate及分层200条Teacher-target人工审计；
5. 重跑U_final isolation与完整回归。

只有上述全部通过，才可报告`READY_FOR_FORMAL_NEAR_SFT=true`。即使ready，仍不得自动启动正式SFT；Training #1需要用户单独授权。本状态不授权Raw/传统正式baseline、Judge/RL、Unknown、U_final、Agent或few-shot实验。

绝对禁止：修改Production、split、K/U、PLAN_B；用test/U_final调参；把Unknown作为K+1类；让Teacher决定GT；让Supervisor改fine label；让RAG发明Observation；默认每样本RAG；无限raw Payload；把model/data/cache/log/checkpoint提交Git。

## 12. Git与环境提示

当前实现分支基于`ff4eca8`；禁止reset/rebase/clean/force push，本任务不push。Phase B小型审计入口为`reports/training_readiness/near_pretraining_readiness_v1.md`。

数据环境：`/root/autodl-tmp/conda/flow-data`。Qwen training/runtime环境：`/root/autodl-tmp/conda/qwen35-runtime`。Production v2 root通过现有`ARTIFACT_ROOT`约定解析，Phase B Git-external root为`$ARTIFACT_ROOT/near_pretraining_v1`；GitHub CI无外部资产时真实数据测试安全skip。DeepSeek只读runtime环境中的`DEEPSEEK_API_KEY`，不得写入repo/report/log。

## 13. 新接手者自检

阅读权威链后，应能回答：为什么Near先跑；Qwen训练两次分别训练什么；Fine Head/LM Head/coarse mapping如何分工；为什么Fine correctness不是GRPO组内reward；Unknown何时冻结且为何不训练Qwen；U_dev/U_final权限；DeepSeek三个角色与Codex职责；RAG何时调用；Payload为何允许但按需受限；Supervisor为何不能分类；Runtime为何是authority；Experience/Class Memory差异；当前做到哪里；下一阶段是什么；哪些事情不能提前做。
