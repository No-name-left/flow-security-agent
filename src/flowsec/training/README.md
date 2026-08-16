# Near pre-training preparation

> **LEGACY_MODEL_A_TRAINING / COMPLETED / DO_NOT_EXECUTE_FOR_MODEL_B**

This package preserves the completed Edge Model A preparation and training
lineage. The 16,979 `PLAN_B` candidate path, Teacher V3 path, and later
Observable-v3/Teacher-v2 path are not current Model B data or supervision.
Model A formal training/evaluation is complete; do not use this README to
restart Teacher generation, SFT, RLAIF, or a mandatory Supervisor.

For historical reproducibility, `tools/prepare_near_pretraining.py` exposes separate, explicit phases for
Application/Payload sidecars, generic hybrid RAG, Evidence-State snapshots,
Teacher pilot/bulk annotation, K-known validation materialization, final SFT corpus joining, and isolation audit.
Those Teacher phases are `LEGACY_DEPRECATED` and must not be executed for Model
B. They historically required `DEEPSEEK_API_KEY` at runtime and reused the existing
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


The historical Model A formal entrypoint was:

~~~bash
python -m flowsec.training.train_near_sft --config configs/training/near_sft_config_v2.yaml --preflight-only
~~~

The completed config is now fail-closed against accidental relaunch. Its
checkpoint, LoRA, Fine Head, optimizer/scheduler lineage and evaluation report
remain Git-external or tracked as small provenance. This command is shown for
lineage only and is not an instruction to execute.

Model A final acceptance, formal SFT, and evaluation are complete. The retained
Teacher V3 and Teacher-v2 fields (`evidence_sufficient`, `missing_evidence`,
`primary_gap`) are `LEGACY_REFERENCE` only. They cannot become Model B
operational utility, classification, recoverability, or Unknown GT. Current
Model B contracts are in `docs/research_plan/dataset_v4_b1_runtime_contract.md`
and `docs/research_plan/dataset_v4_split_protocol.md`.
