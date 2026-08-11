# Near Final Pre-training Acceptance

Status: **BLOCKED**
Audit date: 2026-08-12
Formal SFT run: **false**
RLAIF/GRPO run: **false**

## Gate result

The provider, typed role boundaries, V2 prompts, serialization, training harness,
validation asset, evidence sidecars/RAG, resource capacity and regression suite
are operational. Formal SFT is nevertheless blocked by one scientific contract
failure discovered by the real Teacher pilot.

The 250-record stratified pilot is structurally excellent: 250/250 validated,
98.8% first-pass, 1.2% repaired, zero quarantine, zero unsupported Evidence IDs,
and all 11 known classes plus all eight stages are represented. However, the
Teacher marks only 2/250 states Evidence-sufficient, and those two states cover
only Normal and Port_Scanning. The partial bulk independently confirms the
pattern: 66 sufficient among 12,251 currently valid annotations.

The frozen rule says classification CE must not force backend GT on an
insufficient state. Applying that rule would leave the Fine Head without viable
supervision for most known classes. Ignoring Teacher sufficiency and restoring
bare backend-label CE would contradict the acceptance requirement. Therefore
bulk was stopped at a resumable checkpoint, the final SFT corpus was not
rendered, config authorization remains false, and no formal training was
started.

## Completed evidence

- DeepSeek V4 Flash project-provider preflight: model discovery, text and JSON
  completion PASS through the formal transport, explicit non-thinking mode,
  request IDs/token usage/latency recorded, secret redaction PASS.
- Prompt V2: all Evidence/Payload/RAG/rollout content is untrusted data; no tool
  choice or competing fine label in the Qwen Evidence-State contract.
- Separate build_teacher_request, build_judge_request and
  build_supervisor_request allowlists are implemented and tested.
- Safe-query correction: only fixed semantics extracted from already sanitized
  TRAIN Payload; RAG audit now retrieves relevant authoritative sources for TCP,
  scanning, DDoS, credential, malware/ransomware, SQL injection, upload and
  vulnerability-scanning themes.
- V2 pre-Teacher universe: 22,957 states / 16,979 sessions; Application 1,120,
  Payload 1,697, RAG 1,165; RL pool 6,000; U_final 0.
- Known validation asset: 1,033 records across all 11 classes, exact diversity
  1,033, test/U_dev/U_final 0.
- V2 input token lengths: P50 877, P90 1,269, P95 1,463, P99 1,684, max 2,755.
  The 11,296 annotated combined sequences inspected have max 2,079 and zero
  overflow at 3,072.
- Formal launcher/config implementation includes digest preflight, overwrite
  refusal, deterministic shuffle, Macro-F1 validation, step/epoch checkpoints,
  LoRA/Fine Head/optimizer/scheduler/RNG persistence and strict resume. It is
  not launch-ready until final corpus gates pass.
- Resource check: RTX 4090 49,140 MiB total / 48,509 MiB free; 693 GiB RAM
  available; 505 GiB data disk free; no compute process occupied VRAM.
- Verification: 279 pytest passed; compileall, git diff check, conflict scan and
  secret-value scan PASS.

## Exact acceptance fields

~~~text
FINAL_PRETRAINING_ACCEPTANCE_STATUS=BLOCKED
DEEPSEEK_PROVIDER_READY=true
TEACHER_PILOT_PASS=false
TEACHER_BULK_COMPLETE=false
TEACHER_VALID_RATE=0.5336498671 (partial 12251/22957)
FINAL_SFT_CORPUS_READY=false
FINAL_SFT_RECORD_COUNT=0
FINAL_UNIQUE_SESSIONS=0
CLASSIFICATION_SUPERVISED_RECORDS=0
CLASSIFICATION_MASKED_RECORDS=0
APPLICATION_RECORDS=0
PAYLOAD_RECORDS=0
RAG_RECORDS=0
PROMPT_FINAL_AUDIT=PASS
SERIALIZATION_FINAL_AUDIT=PASS_PRETEACHER_INPUT_ONLY
PAYLOAD_FINAL_AUDIT=PASS_WITH_LIMITATIONS
RAG_FINAL_AUDIT=PASS
DEEPSEEK_ROLE_ISOLATION_AUDIT=PASS
TRAINING_HARNESS_FINAL_AUDIT=PASS
FORMAL_SFT_CONFIG_READY=false
FORMAL_SFT_LAUNCHER_READY=false
CHECKPOINT_RESUME_READY=true
RL_COMPATIBILITY_PRECHECK=PASS_WITH_LIMITATIONS
U_FINAL_ISOLATION_GATE=PASS
FULL_PYTEST=279 passed
FORMAL_SFT_ESTIMATED_TIME=10-12h/epoch
FORMAL_SFT_ESTIMATED_VRAM=27.57 GiB measured; 32 GiB recommended
SFT_RUN=false
RL_RUN=false
READY_TO_START_FORMAL_NEAR_SFT=false
NEXT_ACTION=Resolve and freeze classification-sufficiency supervision contract before resuming bulk; do not start SFT.
~~~

## Git disposition

The work remains on feat/near-final-pretraining-acceptance with a dirty worktree.
Because the task is blocked, no commit, fast-forward landing, branch deletion or
push was performed. Git-external Teacher caches and manifests are preserved for
resume.
