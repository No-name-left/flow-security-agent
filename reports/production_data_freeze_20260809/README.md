# Production Data Freeze（2026-08-09）

## 最终判定

- `PRODUCTION_DATA_READY=true`
- `POSTFIX_PRECOMMIT_AUDIT=PASS_WITH_LIMITATIONS`
- `CLASS_ROLE_SUPPORT_GATE=PASS`
- `BASE_PRODUCTION_READY=true`
- `FEW_SHOT_VARIANT_READY=true`
- `CAPTURE_PROVENANCE_GATE=PASS`
- `LABEL_PROVENANCE_AUDIT_POSTFIX=PASS_WITH_LIMITATIONS`
- `LEAKAGE_AUDIT_OK=true`
- `DETERMINISM_AUDIT_OK=true`
- `U_FINAL_ISOLATION_PASS=true`
- `DECISION_REQUIRED=false`
- `QWEN_DOWNLOADED=false`
- `TRAINING_STARTED=false`

本目录只保存适合Git的小型复现摘要和关键manifest。原始数据、SQLite catalog、Parquet资产、完整source manifest与大统计文件不进入Git。初版全局model-view过度去重run及其阻断结论只作为历史证据；当前正式run已使用immutable backend identity去重全量重建并完成复审。

## 基线与入口

- 任务基线：`db9e8638bbbe01587db5fa967de00c89e1885d32`
- 配置：`configs/data/production_freeze_v1.yaml`
- 全量CLI：`flowsec-production-data` / `python -m flowsec.production.cli`
- class-role小型refresh：`python tools/refresh_class_role_readiness.py`
- postfix审计：`python tools/audit_production_postfix.py`
- 服务器完整产物：`/root/autodl-tmp/processed/production_data_freeze_v1/`
- 服务器完整报告：`/root/autodl-tmp/experiments/production_data_freeze_20260809/`

## 正式数据结果

| 数据集 | 后台记录 | 保留Canonical记录 | 排除 | 正式split |
| --- | ---: | ---: | ---: | --- |
| Edge-IIoTset | 7,619,032 | 7,377,181 | 241,851 | train 5,162,702；validation 1,030,853；test 1,183,626 |
| IoT-23 | 199,922 | 192,165 | 7,757 | train 10,855；validation 6,494；test 23,251；U_dev 145,597；U_final 5,962；probe 6 |
| 合计 | 7,818,954 | 7,569,346 | 249,608 | — |

PRIMARY只删除immutable backend identity重复或隔离boundary/gap与明确异常；model-view exact/near equality保留在Primary并量化为不修改train的evaluation-clean敏感性变体。identity duplicate及identity label conflict均为0，identity cross-split overlap为0。

Edge完整使用24个PCAP，采用capture-internal连续时间70/15/15块与60秒sessionization。24/24 companion CSV均为100%单标签纯度且与预注册label一致；7,619,032个Edge backend session均以`VERIFIED_CAPTURE_FALLBACK`赋标签，conflict与unmatched/quarantine均为0。此前4个可直接精确时间对齐capture中的112,434个有direct evidence session为100% unanimous。

IoT-23使用8个独立scenario。正式任务层级为原生coarse：`K={Benign, CommandAndControl}`、`U_dev={Reconnaissance}`、`U_final={Exploitation}`；native fine `Attack`只通过冻结映射进入coarse `Exploitation`，不会直接污染Gate。Capture-42的6条FileTransfer恶意flow继续只作probe，不是正式U_final来源。

## Class-role Gate定向修复

旧Gate有两个实现级root cause：

1. `GATE_LOGIC_BUG`：把每个Edge K类在physical train/validation/test均非空，以及全部few-shot变体，都错误耦合为BASE Production硬条件；没有以最终logical training manifest验证K/U visibility。
2. `MANIFEST_GENERATION_BUG`：support sampler先对raw session截断再检查exact evidence多样性，高频重复DDoS_UDP view挤掉其他合法evidence group，虚假产生10-shot只有5条、query为0。

修复后Gate先验证本次全量run的config/source hash、mode、record counts与completion identity，再只重建K/U、training、support/query、class-role和readiness等小型manifest，不重建canonical、不重跑tshark。support sampler先从每个exact evidence group确定性选择代表，再执行容量限制；两次独立小型生成的内容hash一致。

完整class-role matrix共121行：119 `PASS`、2 `LIMITATION`、0 `FAIL`。两个非硬限制均为K_known Ransomware在Near/Far preset中的physical validation记录为0；其train=232、test=1,132，logical K训练/闭集测试合同均成立。这不是BASE真实数据不足，也没有修改physical split、K/U或研究角色。

| 数据集/preset | BASE | U_final隔离 | 正式few-shot |
| --- | --- | --- | --- |
| Edge Near | PASS | PASS | DDoS_UDP、XSS：1/5/10-shot READY |
| Edge Far | PASS | PASS | Password：1/5/10-shot READY |
| Edge Mixed | PASS | PASS | Password、Ransomware：1/5/10-shot READY |
| IoT-23 | PASS | PASS | Exploitation：1/5-shot READY；10-shot NOT_REGISTERED |

Near/DDoS_UDP修复后从完整test数据获得172个exact evidence group：support 1/5/10-shot均READY，shared query为162。XSS query为189，Password query为1,000，Ransomware query为580，IoT-23 Exploitation query为1,000；support/query的sample、exact、reverse重叠均为0。

## 保留限制

- Edge攻击类大多只有单capture，不宣称跨攻击run泛化。
- Ransomware没有per-class physical validation记录；这是validation-by-class变体限制，不是BASE数据Gate blocker。
- DDoS_UDP、XSS与Ransomware的去重后query容量分别低于请求上限1,000，但均非空且结构合法。
- Edge gap只在预注册可用性上限下裁剪，逐capture保留证据。
- Somfy严格匹配81.54%、Capture-42截断尾部/6-flow probe限制保持。
- IoT-23因跨scenario fine标签不充分重叠，正式任务使用原生coarse层。
- service_category不进入PRIMARY_VIEW。

## 验证与下一步

本轮定向与完整测试均通过（完整`pytest`为64 passed），`git diff --check`须在交接前再次确认。最终postfix所有硬Gate通过且无剩余数据blocker。尚未下载或运行Qwen，也未开始SFT；下一步是人工审查当前dirty worktree，并仅在用户明确授权后commit/push，然后再进入模型环境与冒烟阶段。
