# Near pre-training preparation

This package prepares the frozen Edge Near mainline without starting formal
training. The legal universe is exactly the 16,979 `PLAN_B` candidates in
`K_known ∩ train`; validation, test, `U_dev`, and `U_final` are rejected by the
typed contracts and audited again across materialized artifacts.

`tools/prepare_near_pretraining.py` exposes separate, explicit phases for
Application/Payload sidecars, generic hybrid RAG, Evidence-State snapshots,
Teacher pilot/bulk annotation, K-known validation materialization, final SFT corpus joining, and isolation audit.
The Teacher phases require `DEEPSEEK_API_KEY` at runtime and reuse the existing
OpenAI-compatible transport. Secrets are never written to requests, logs,
reports, or cache records. Bulk annotation cannot run before a zero-quarantine
pilot manifest exists.

The training architecture is frozen Qwen base weights plus PEFT LoRA and one
Linear Fine Classification Head. Coarse labels remain a deterministic mapping.
LM-supervised forwards require a separate prompt-only classification mask so
Evidence-State target tokens cannot enter the classification representation.
Classification CE is applied only to deterministic legal primary states; Teacher Evidence sufficiency is a separate stopping/acquisition target and never gates classification CE. Controlled lower-evidence states remain masked. Evidence LM loss consumes inverse-states-per-session weights. The original LM head remains frozen but supplies the Evidence-State LM
loss.

Large PCAP-derived sidecars, RAG documents/indexes, Teacher outputs, SFT JSONL,
RL prompt pools, and dry-run checkpoints stay below
`$ARTIFACT_ROOT/near_pretraining_v1` and outside Git. Only source, schemas,
configuration, small manifests/reports, and tests belong in the repository.
`tools/dry_run_near_sft.py` is limited to two optimizer steps, marks its targets
as deterministic schema fixtures, verifies frozen/trainable parameters and
checkpoint reload, then deletes the temporary checkpoint. It is not a formal
SFT launcher.


The formal entrypoint is:

~~~bash
python -m flowsec.training.train_near_sft --config configs/training/near_sft_config_v1.yaml --preflight-only
~~~

Formal execution additionally requires the explicit execute flag. The launcher
refuses overwrite, records immutable digests and saves LoRA, Fine Head,
optimizer, scheduler and RNG state for strict resume.

Final pre-training acceptance is PASS under
`CLASSIFICATION_SUFFICIENCY_DECOUPLED_V1`. The final zero-network validation
reused all 22,957 digest-matched Teacher V3 records; the frozen V2 corpus has
16,979 classification-supervised primary records and 5,978 controlled masked
auxiliaries, with zero quarantine, leakage, label collision or sequence
overflow. The config is `FROZEN_READY`, but no training runs unless the caller
separately supplies the explicit `--execute` flag.
