# Task Definition v2：可观测细分类与 Evidence-v2 数据合同

> 状态：**IMPLEMENTED / FINAL PRE-TRAINING ACCEPTANCE PASS**
>
> 生效日期：2026-08-13
>
> 权威关系：本文件是本轮 label space、observation eligibility、Dataset v3、Evidence-v2 与 Teacher-v2 的详细单一真值源；研究语义仍以 `research_plan_detailed.md` 及其 Decision Log 为最高权威，训练执行服从 `near_mainline_training_protocol_v1.md`。

> **DEC-0025 scope note:**本文件继续作为Model A Dataset-v3/Evidence-v2/Teacher-v2的冻结数据合同与provenance记录，不定义Model B的主架构或operational utility。Model B服从[research_plan_detailed.md](research_plan_detailed.md)、[model_b_evidence_openworld_design.md](model_b_evidence_openworld_design.md)与[open_world_continual_agent_design.md](open_world_continual_agent_design.md)。下述Qwen Evidence State、Teacher-v2、DeepSeek Supervisor与RLAIF链路均为Model A历史合同；它们不得成为Model B utility GT或必经阶段。

## 1. Model A历史目标与冻结主链路

本轮目标是生成一套 GT 与合法网络 Evidence 一致、可稳定训练且 train/validation/test 使用同一准入规则的正式 Qwen Traffic Expert 数据。优先级为：正确 > 信息充分 > 训练稳定 > split 一致 > 数据量 > 难度。

```text
Network Observation
→ Basic-v2 Evidence
→ Qwen Traffic Expert
→ Fine Classification + Evidence State
→ DeepSeek Supervisor
→ one bounded Evidence action
→ deterministic Runtime
→ new Evidence
→ Qwen re-evaluation
```

Qwen判断分类与Evidence State；Supervisor只根据状态、capability、history与budget选择一个动作；Runtime确定性执行。SFT之后仍是Agent-oriented RLAIF-GRPO。Qwen不得自由调用工具，Supervisor不得成为第二分类器。

## 2. 主标签空间与辅助角色

`MAX_MAIN_CLASSES=8`。审计候选固定为Normal、DDoS_HTTP、DDoS_TCP、MITM、Password、Port_Scanning、SQL_injection、Vulnerability_scanner。最终冻结六类：Normal、DDoS_HTTP、DDoS_TCP、Password、SQL_injection、Vulnerability_scanner。MITM因缺少与target session端点关联的ARP/relation异常而判为wrong granularity；Port_Scanning的官方capture实际呈现同一destination port 80、变化source port的行为，无法支持port-scan fine语义。二者不进入主CE，但保留完整exclusion provenance。

| Class | v2 role | Main classification CE |
| --- | --- | --- |
| Backdoor | `LONG_HORIZON_TEMPORAL_CASE_STUDY` | false |
| Uploading | `OBSERVABILITY_LIMITED_ABSTAIN` | false |
| Ransomware | `OBSERVABILITY_LIMITED_ABSTAIN` | false |

Backdoor的raw资产与周期性审计继续保留。Uploading、Ransomware及被过滤的合法stress observations可进入Observability Stress Set，监督`ABSTAIN`/`NOT_RECOVERABLE`，但必须设置`classification_ce_eligible=false`。它们不是Unknown类别的自动替代，也不改变冻结的`U_final`。

## 3. Fine-Class Observation Eligibility Contract

Verified capture provenance只证明PCAP、companion CSV与预注册capture label一致；它不证明capture内每个重建session都含有支持该fine label的网络证据。

只有满足`FULL_OBSERVATIONAL_SUFFICIENT=true`的observation才能进入主train/validation/test。判断只能使用正式推理时合法可获得的Observation Evidence：target session、packet/payload、application、strictly-past temporal context及relation/link-layer context。Knowledge/RAG可以解释观察，不能证明观察存在。

必须排除并记录原因：

- `GENERIC_BACKGROUND`：仅因attack capture而继承label，session/context没有攻击依据；
- `NETWORK_UNOBSERVABLE`：全部合法网络Evidence仍不能支持fine GT；
- `WRONG_GRANULARITY`：当前observation unit不能承载该label；
- `LABEL_PROPAGATION_ONLY`：fine GT实际只依赖capture identity。

容易识别、稳定协议字段、明显payload signature或真实攻击相关端口本身不是删除理由。只有dataset/capture/file/path/split/run identity、未来信息或环境绝对指纹属于禁止捷径。其他强相关行为只记录`OBSERVED_SHORTCUT_RISK`。

Train、validation、test使用同一eligibility contract。默认保留现有`CONSTRAINED_CHRONOLOGICAL_BOUNDARY_V2` assignment，并在每个split内过滤；只有过滤后某主类的某split严重不足，才允许在任何模型结果之前构建deterministic grouped/chronological split v3。禁止随机row split。

## 4. Observable Dataset v3

Dataset v3为Production canonical identity的派生可观测层，不改变raw PCAP、60秒sessionization或canonical record。每条派生记录至少保存stable `sample_id`与原split、fine/coarse label与不可见backend provenance、eligibility class与exclusion reason、full-evidence support references、Basic-v2及可用Evidence family references、capability/missing declarations、identity/exact/near group references以及evidence/split/schema版本。

主数据硬Gate：

```text
GENERIC_MAIN_TRAIN=0
GENERIC_MAIN_VAL=0
GENERIC_MAIN_TEST=0
UNOBSERVABLE_MAIN_TRAIN=0
UNOBSERVABLE_MAIN_VAL=0
UNOBSERVABLE_MAIN_TEST=0
```

类别不再使用机械原始保留率门槛。最终按高质量eligible数量、各split评价稳定性、SFT sampling需要与exact/near diversity共同判断`CLASS_SAMPLE_SIZE_RISK`及是否保留。

## 5. Basic Evidence v2

`Basic-v2 = cheap but useful`，不是Full Evidence。每个主sample的统一初始状态包含：

1. Session Summary：duration、双向packet/byte counts、packet length与IAT统计、TCP handshake/state summary、安全protocol/service metadata；
2. first-8 packet metadata：direction、relative time/IAT、length、L3/L4、TCP flags及安全header字段；
3. first-8 packet-aligned bounded sanitized payload；
4. 可低成本确定性获得的structured Application metadata。

正式packet-aligned payload sidecar逐packet记录：

```text
session_id
packet_index
direction
relative_time
protocol
payload_present
payload_length
sanitized_payload
sanitization_version
```

`packet_index`是显式provenance，不得根据数组位置猜测。Payload继续是untrusted、bounded、protocol-aware、sanitized；Basic只含first-8的受限片段，后续`PACKET_PAYLOAD`可以提供合法的扩展证据。

## 6. Evidence-v2 families

Observation Evidence family固定为`PACKET_PAYLOAD`、`APPLICATION`、`TEMPORAL`、`RELATION`；Knowledge Evidence family固定为`KNOWLEDGE`。不得自由创造缺口类型。所有Observation必须来自真实traffic或合法past-only context。

### 6.1 Temporal-v2

固定候选horizon为10s、60s、180s与300s，全部`STRICTLY_PAST_ONLY`。可按协议真实可用性输出session/connection、packet、byte rate；SYN/RST/ACK、handshake完成/未完成；destination concentration、source fan-in、destination fan-out、port diversity；burstiness/IAT；重复auth/request、URI/method repetition；periodicity/interval CV；directional byte asymmetry。不能用未来session填充窗口。

### 6.2 Relation-v2

允许ARP mapping、ARP conflict/change、same-MAC-to-multiple-IP、DNS relation、fan-in/fan-out、multi-source same-target、port relation与unexpected responder。ARP等non-IP packet作为合法relation/link-layer context关联到target observation，但不改变五元组target session定义。

### 6.3 Application-v2

优先结构化HTTP method/status、URI shape、auth/login或credential-field presence、content type、request/response structure及scanner/probe metadata。不得默认暴露无限制payload transcript。

## 7. 类别可观测性判定重点

- Password：保留真实Direct与strictly-past Contextual，删除Generic；不要求所有observation都是POST。
- DDoS_TCP：使用SYN、handshake、connection rate、burstiness与target concentration。
- DDoS_HTTP：结合Temporal与Application的request rate、URI/method repetition、concentration、burst与response pattern；无依据的session删除。
- MITM：必须能由ARP/relation异常合法关联到target observation；不可关联者删除。
- Port_Scanning：使用port diversity、短/失败连接、multi-target、scan rate与relation；可用past-only multi-session context。
- Vulnerability_scanner：允许Application、Temporal、Relation与Payload的真实probe/scanner行为；删除普通background。
- SQL_injection：以Payload/Application为主，不做为难度而过度筛选。
- Normal：检查builder与标签异常，不做无依据的过度筛选。

## 8. Evidence State v2

Evidence State升级为multi-gap：

```json
{
  "evidence_sufficient": false,
  "supporting_evidence": ["..."],
  "missing_evidence": ["TEMPORAL", "APPLICATION"],
  "primary_gap": "TEMPORAL",
  "gap_type": "OBSERVATIONAL",
  "recoverability": "RECOVERABLE_WITH_AVAILABLE_TOOLS"
}
```

`missing_evidence`是去重后的固定family数组，可以为空或包含多个family。`primary_gap`为空或属于该数组。`gap_type`只能是`OBSERVATIONAL`、`KNOWLEDGE`、`MIXED`、`NONE`。`recoverability`只能是`ALREADY_SUFFICIENT`、`RECOVERABLE_WITH_AVAILABLE_TOOLS`、`NOT_RECOVERABLE_FROM_AVAILABLE_NETWORK_EVIDENCE`。

Qwen可同时声明多个gap；Supervisor仍每轮只选一个bounded action。不得为了制造Agent复杂性人为移除证据或穷举组合。

## 9. Eligibility先于Teacher-v2

正式顺序冻结为：

```text
Raw data
→ Evidence-v2
→ deterministic eligibility / observable filtering
→ clean train/validation/test
→ bounded Evidence states
→ DeepSeek Teacher-v2
→ validation and bounded review
→ formal SFT corpus
```

Teacher-v2不重新创造fine GT，只标注当前合法Evidence State的sufficiency、support、multi-gap、primary gap、gap type与recoverability。旧Teacher V3输出及22,957-record corpus保留为历史审计，但因population、Basic、Payload、Temporal、Relation和schema均改变，不得作为新formal corpus监督。

每个eligible TRAIN session原则上生成一个Basic-v2 primary，再根据真实gap生成最多1–2个有意义的controlled auxiliary states。Teacher正式bulk前必须完成20–50条schema/cost/resume smoke；bulk必须deduplicated、per-batch durable、strictly validated、可恢复，并记录calls/tokens/cost/errors/retries但不记录secret。

## 10. SFT corpus v3与权重

正式corpus只能来自eligible TRAIN主类session。每条至少保存`session_id`、primary/auxiliary state role、`classification_ce_eligible`、`session_weight`、immutable fine target（backend training target only）、Evidence State v2及prompt/schema/serialization/evidence版本。

每个session原则上只有一个classification primary。即使Basic-v2的Teacher target为insufficient，合法primary的classification GT仍可用于CE；Evidence sufficiency不门控classification GT。Controlled auxiliary可以mask classification CE。

训练harness必须真正应用`session_weight`，使同一session的多个states不产生不合理放大。实现与测试通过是formal SFT硬Gate。

## 11. Observability Stress Set

被排除的generic/unobservable observations与Uploading/Ransomware可单独物化为stress set，学习或评价`ABSTAIN`和`NOT_RECOVERABLE`。它们必须与主classifier population物理/manifest级区分，设置`classification_ce_eligible=false`，且不得成为U_final或未知类开发的后门。

## 12. Integrity、评审与最终Gate

至少检查payload packet alignment与source/frame provenance、strictly-past temporal窗口、train/validation/test identity无重叠、U_final isolation、main split generic/unobservable为0、label map/schema/serialization、per-class split数量与exact/near diversity、Teacher-v2 multi-gap/recoverability质量、session weighting真正进入loss。小规模blind sanity只用于发现serializer/builder/GT mapping/Teacher错误，不能按模型结果挑样本。

只有所有硬Gate、plan consistency和回归通过，才能设置：

```text
READY_FOR_FORMAL_SFT=true
FORMAL_SFT_STARTED_AT_THIS_ACCEPTANCE_SNAPSHOT=false
```

在完成前，旧`READY_TO_START_FORMAL_NEAR_SFT=true`状态由DEC-0021暂停，不授权启动旧corpus训练。

## 13. 版本化输出与报告

大型Parquet、payload/evidence sidecar、Teacher cache、JSONL corpus、checkpoint与日志保存在Git外。Git只跟踪code、tests、configs、小manifest、报告与计划。

最终报告给出每类original/eligible/exclusion/split数量、Basic/FULL sufficiency、各Evidence需求、single/multi-gap比例、最终主类、split协议、Teacher-v2质量、session-weight、U_final isolation、corpus SHA256、plan consistency和`READY_FOR_FORMAL_SFT`。大型数据与cache保持Git-external。

## 14. 最终实现与冻结结果

Dataset v3复用`CONSTRAINED_CHRONOLOGICAL_BOUNDARY_V2`并逐split执行同一eligibility filter，没有重新sessionize或重建canonical。六类正式population为train 1,318,688、validation 270,851、test 279,057；三个split的generic/unobservable主样本均为0，sample identity overlap为0。正式per-class train/validation/test为：Normal 475,650/100,720/101,367；DDoS_HTTP 3,633/156/842；DDoS_TCP 817,957/165,432/172,231；Password 16,532/3,548/3,552；SQL_injection 2,924/568/641；Vulnerability_scanner 1,992/427/424。

Evidence-v2已物化覆盖17个候选capture：Basic-v2含session summary、first-8 metadata、显式packet-index对齐的first-8 sanitized payload和cheap Application；PACKET_PAYLOAD扩展到9–16；Temporal提供10/60/180/300秒strictly-past行为统计；Relation只允许同scope、strict-past且与target endpoint/MAC关联的ARP/DNS/relation；Application使用真实结构化协议字段。raw PCAP仍为source of truth，Production identity、split与canonical均未覆盖。

SFT选择采用`CLASS_BALANCED_DIVERSITY_AWARE_SFT_SELECTION_V2`，初始12,119 eligible TRAIN sessions生成20,807个bounded Teacher-v2 states。40-state smoke与20,807-state resumable bulk均PASS，schema/grounding/quarantine为20,807/20,807/0。形式化trajectory curation不改写Teacher cache或target语义：terminal仍insufficient的161个候选session从SFT监督中quarantine；一旦首次sufficient即停止后续反事实Evidence状态，移除6,116 states。正式corpus为11,958 sessions、14,350 records、每session恰一Basic classification primary、最多3 states；single-gap rate 12.8014%，multi-gap rate 3.8676%，terminal insufficient和true→false均为0。

默认Known validation为3,231条六类`EXACT_EVAL_CLEAN`记录；near-clean仅作为敏感性统计，因为DDoS_TCP没有可用near-clean validation，不能冒充完整六类主验证集。本地Qwen tokenizer-only全量审计最大4,794 tokens，8192上限overflow为0；未加载或运行Qwen模型。`session_weight`由harness实际用于Evidence-LM weighted-sum，每session state权重和为1；classification CE每session只在唯一Basic primary计算。

Observability Stress Set v1独立索引3,676条excluded observations，全部`classification_ce_eligible=false`。Uploading/Ransomware保留为后续独立非CE stress materialization，本轮17-capture主候选scan未将它们伪装成Evidence-v2资产。Backdoor继续仅为Long-Horizon Temporal Case Study。

最终corpus SHA256为`d93789de29b746d923660bb2e4ccad501412e75303ddf95f7087c85f6c67d6ca`。`U_FINAL_ISOLATION=PASS`且在该acceptance snapshot未打开内容；当时`FORMAL_SFT_STARTED=false`且下一动作是`START_FORMAL_NEAR_MULTI_TASK_SFT`。该后续任务现已完成，正式结果以Model A evaluation报告为准；Model B当前语义以DEC-0025为准。
