# Near Pre-training Readiness v1

> 审计日期：2026-08-12
>
> 分支：`feat/near-pretraining-readiness-v1`
>
> 基线：`ff4eca8fc6e00196666a9a3768679e3ddfefea60`
>
> 本报告所在提交即实现提交；大型模型、PCAP、Parquet、RAG index、snapshot/Teacher输出和checkpoint均不进入Git。

## 结论

`PRETRAINING_READINESS_STATUS=BLOCKED`

`READY_FOR_FORMAL_NEAR_SFT=false`

`SOLE_REMAINING_BLOCKER=DEEPSEEK_API_KEY`

所有不依赖外部API的Near预训练准备已经完成并通过审计。当前环境没有`DEEPSEEK_API_KEY`，因此未发起任何DeepSeek请求，也没有伪造Teacher输出、成本或最终SFT corpus。待key以runtime environment提供后，必须依次通过provider preflight、250条Teacher pilot（零quarantine）、bulk annotation、最终corpus join/token/manual gate；随后仍须由用户另行授权正式SFT。

## Gate

| Gate | 结果 |
| --- | --- |
| `TRAINING_HARNESS_READY` | true |
| `FINE_CLASSIFICATION_HEAD_READY` | true；Linear 4096→dynamic 11 |
| `CLASSIFICATION_POOLING_V1` | `ATTENTION_MASKED_MEAN_V1` |
| `LORA_TARGET_MODULES_V1` | q/k/v/o、DeltaNet in_proj_qkv/z/a/b + out_proj、FFN gate/up/down；248 modules |
| `SERIALIZATION_V1` | `COMPACT_SAFE_EVIDENCE_V1`，digest `66af2ccb...` |
| `TRAFFIC_EXPERT_PROMPT_V1` | frozen，digest `a5506044...` |
| `EVIDENCE_STATE_SCHEMA_V1` | frozen |
| `APPLICATION_EVIDENCE_V1_READY` | true |
| `SANITIZED_PAYLOAD_V1_READY` | true |
| `PAYLOAD_SHORTCUT_AUDIT` | PASS；risk=LOW |
| `RAG_KB_V1_READY` / `RAG_INDEX_V1_READY` | true / true |
| `RAG_EVIDENCE_SCHEMA_V1_READY` | true |
| `DEEPSEEK_FLASH_PROVIDER_READY` | false；`NO_API_KEY` |
| `TEACHER_PROMPT_V1_READY` | true |
| `TEACHER_ANNOTATION_READY` | false；0 API requests |
| `JUDGE_PROMPT_V1_READY` | true |
| `SUPERVISOR_PROMPT_CONTRACT_V1_READY` | true |
| `NEAR_SFT_CORPUS_V1_READY` | false；final record count=0 |
| `RL_PROMPT_POOL_V1_READY` | true；6,000 prompts |
| `TRAINING_DRY_RUN_PASS` | true；exactly 2 optimizer steps |
| `TRAINABLE_PARAMETER_AUDIT` | PASS |
| `U_FINAL_PRETRAINING_ISOLATION_GATE` | PASS |
| `SFT_RUN` / `RL_RUN` | false / false |

## Training harness与冻结配置

真实Qwen3.5-9B module inventory得到248个LoRA targets：Gated Attention 32、Gated DeltaNet 120、FFN 96。BF16 LoRA参数为rank 8、alpha 16、dropout 0.05；总参数9,431,497,979，可训练21,684,235（0.2299%），其中LoRA 21,639,168、Fine Head 45,067、其他0。base、vision、embedding和原始LM Head均冻结。classification pooling在22个合法Near K-known TRAIN representation上比较三种候选后冻结为`ATTENTION_MASKED_MEAN_V1`；未修改tokenizer或embedding。

`near_sft_config_v1`冻结micro-batch 1、gradient accumulation 16、max length 3,072、2 epochs、LR 2e-4、gradient checkpointing；这些训练数值仍标记`VALIDATION_TUNABLE`。Classification representation只读prompt token mask，不能看到LM target；`classification_supervision_valid=false`时仅mask Fine CE，LM Evidence-State loss仍保留。

## Serialization、Evidence与RAG

22,957个合法snapshot完成lossless equivalence：compact平均870.123 tokens，P50/P90/P95/P99/max为868/1,260/1,453/1,675/2,746，比current平均减少2.089%，semantic failure=0。

Application/Payload sidecar只覆盖20个Near K-known TRAIN capture和16,979个PLAN_B session：Application 7,410（43.642%，HTTP 7,240、DNS 149、Modbus 13、TLS 8）；可解释且脱敏的Payload 11,481（67.619%）。sanitizer保留SQL/HTTP/script/command语义，删除IP、host、cookie/authorization、UUID/长token、绝对时间、固定实验路径、automation tool marker和设备/会话/用户标识。shortcut risk为LOW；`include`/`open`仅作为通用语义保留并记录。

RAG V1包含30个权威generic sources、2,263 chunks，使用BM25 + pinned `sentence-transformers/all-MiniLM-L6-v2@c9745ed1...` dense hybrid；index digest为`91ab9c70...`。query不得含GT、K/U、dataset/capture identity；Knowledge保持`UNTRUSTED_KNOWLEDGE`，不能冒充Observation。SFT snapshot中的RAG exposure为5.075%。

## Snapshot、RL pool与Teacher blocker

候选层共有22,957个Evidence State snapshots、16,979个唯一session：16,979 primary classification-supervised states + 5,978 controlled lower-evidence CE-masked states；11,001个session有1 state，5,978个有2 states；exact serialized duplicate groups=0。分层200条snapshot结构化审查failure=0。RL Prompt Pool固定为6,000条，覆盖全部11类、全部stage以及sufficient/insufficient state，digest `042003c1...`；没有运行RL。

DeepSeek provider代码复用`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`和`DEEPSEEK_API_KEY`。provider-status在有key时执行model-list和non-thinking structured JSON smoke；Teacher有cache/concurrency/transport retry、严格grounding检查、每条最多一次repair和quarantine。当前key缺失，所以pilot=0、bulk=0、formal SFT records=0，Teacher和未来Judge成本均不能基于真实usage估算。

## 真实9B dry-run与资源计划

真实Qwen3.5-9B完成两步可逆dry-run：一个最长supervised record（2,830 tokens）与一个最长masked record（609 tokens），BF16、micro-batch 1；两步总计5.5103秒、624.106 tokens/s、峰值27.57 GiB。LoRA和Fine Head确实变化；采样frozen digest不变；adapter+head checkpoint reload PASS，大小82.71 MiB，临时checkpoint已删除。

按compact平均输入加dry-run schema target代理，约21.70M tokens/epoch，实测代理为9.66 h/epoch。正式计划保守取10–12 h/epoch、两轮20–24 h；建议至少32 GiB VRAM，当前48 GiB RTX 4090满足。adapter/head + optimizer/save overhead建议预留2 GiB新checkpoint空间。真实Teacher target长度会改变该估算。

## 隔离与限制

正式隔离audit digest为`1cae7b9e...`：candidate、sidecar、snapshot、RL pool、RAG design和dry-run中的U_final计数全部为0；validation/test/U_dev也未进入训练targets。没有运行正式SFT、RL、Unknown、U_final、test benchmark、Far/Mixed或Agent实验。

IMPLEMENTATION LIMITATIONS：Vulnerability_scanner PCAP尾部有损坏包，解析严格限制到候选所需最高frame，合法候选frame覆盖完整；Application覆盖取决于真实协议且不补造；当前200条审计只验证snapshot/evidence结构，Teacher target人工抽查必须在annotation后完成；API价格与真实token usage未产生，因此成本估算保持blocked而非猜测。

## 验证与路径

- targeted pytest：10 passed；full pytest：274 passed。
- Git-external root：`/root/autodl-tmp/processed/near_pretraining_v1`（约85 MB）。
- Qwen：`/root/autodl-tmp/models/Qwen3.5-9B`；embedding：`/root/autodl-tmp/models/all-MiniLM-L6-v2`。
- 完整数值与digest见`near_pretraining_readiness_v1_manifest.json`。
- `compileall=PASS`；`git diff --check=PASS`；conflict scan=PASS；无Git-external资产时real-asset tests为2个safe skip。
