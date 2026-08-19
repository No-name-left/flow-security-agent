# Model B — Recovery-Aware Typed-Evidence Representation V1 — Protocol (FROZEN DESIGN)

**STATUS=FROZEN_DESIGN_NOT_RUN · MODEL_B_V1_STATUS=FROZEN_DESIGN_NOT_RUN**
**FROZEN_DATE=2026-08-20**
**RESEARCHER_REVIEW_COMPLETE=YES (2026-08-20, task
`PREPARE_MODEL_B_V1_FOR_FORMAL_LAUNCH_BUT_DO_NOT_LAUNCH`)**
**PREREGISTRATION_COMMIT_CREATED=YES** (recorded in
`docs/AGENT_CONTEXT.md` and `reports/research_audit/model_b_recovery_aware_representation_v1_preregistration.json`)

**NO FORMAL TRAINING HAS STARTED. NO Model-B scientific metric has been
computed. Formal training is launched ONLY by a separate, explicitly
authorized task (the formal launch command is recorded in §16; it must not
be executed by this task or any task that is not the designated launch
task).** One permitted non-scientific technical smoke was run earlier
(2026-08-20, FINALIZE task); its measurements are quoted in §12. The
correspondence-score definition was changed from an unnormalized dot
product to cosine similarity BEFORE this freeze (§4, §6 — documented
change, not a post-metric revision).

Grounding (frozen, validated): Information Sufficiency Gate V1
`REPRESENTATION_BOTTLENECK_SUPPORTED` — target-specific correspondence
exists in legal RAW Evidence (`n_A_RAW=3`, `rotOK_A_RAW=true`); the
STATE_TRANSITION representation retains only median `ret_b=0.020151` /
`ret_s=0.082691`; generic Evidence-distribution signal exists
(`n_sb_A_RAW=3`, `rotOK_sb_A_RAW=true`); Known-only open-world transfer
unsolved (`n_B_RAW=0`). Model B V1 is justified by that bottleneck
outcome. V1 is NOT the final deployable OSR gate.

## 1. Frozen scientific question

> Does explicitly learning target–Evidence correspondence preserve
> materially more of the validated RAW target-specific recovery signal,
> and improve Known-only transfer to whole-class-held-out Unknown,
> compared with (A) the current STATE_TRANSITION representation and (B)
> the same-size Qwen model trained with CE only?

Deployable OSR metrics are reported only if naturally available
(informational). The Recovery-Aware Novelty Interface is a separate
downstream gate and is NOT part of V1.

## 2. Exact Qwen input contract (FROZEN)

Implementation: `tools/model_b_input_serializer_v1.py`
**SHA256 = `95d159fab5a3c73943fb25153a771d0d8c9d5aab8435642dbd22922036218e6f`**
(recomputed 2026-08-20 immediately before this freeze; the serializer
self-check verifies field-name equality against the frozen dataset
modules). The serialization is **identical** for `QWEN_CE_ONLY`,
`QWEN_CE_PLUS_CORR` and the non-Qwen baseline.

- **Three typed blocks, fixed order:** `<TARGET>` (47 BASIC fields),
  `<TEMPORAL>` (16), `<RELATION>` (18); one line per field
  `<CODE>=<value>`; block close token `</BLOCK>`.
- **Codes (frozen):** `B1..B47`, `T1..T16`, `R1..R18` — deterministic
  mapping to the frozen field names (`MODEL_VISIBLE_FIELDS`,
  `TEMPORAL_FIELDS`, `RELATION_FIELDS`; names verified equal by
  self-check). Codes are feature identifiers; **no natural-language
  descriptions, no GT/attack semantics.**
- **Field ordering:** exact frozen dataset order within each block.
- **Numeric preprocessing:** the same RAW_LEGAL 83-vector values the
  Information Gate consumed; **TRAIN-only standardization** per field
  over positions 0–80: `z=(x−μ)/σ`, μ/σ from the rotation's Known-TRAIN
  rows only (eval rows with `split_role==0` and `is_unknown==0`),
  σ ddof=0, σ=0 → scale 1; clip `[-5,5]`.
- **Precision:** fixed point `%.4f`.
- **Missing values:** non-finite → standardized 0.0 (`0.0000`).
- **Unavailable Evidence:** an unavailable block contains ONLY its header,
  `m=0` and `</BLOCK>`; masks `m_t`/`m_r` (positions 81/82 of the 83-vector)
  are **never standardized** and are rendered `m=1`/`m=0` as the first line
  of each Evidence block.
- **Max sequence length:** 1536 tokens (measured: full BTR template = 902
  tokenizer ids max, B = 546; cap never triggers truncation in practice,
  but the truncation rule is frozen: drop RELATION fields, then TEMPORAL
  fields, then TARGET tail).
- Tokenization: Qwen3.5 tokenizer, `add_special_tokens=True`, pad to
  in-batch max with pad token at train time.

## 3. Primary backbone / adaptation (FROZEN)

- **Backbone:** the audited local `Qwen3.5-9B`
  (`/root/autodl-tmp/models/Qwen3.5-9B`); smoke-verified: bf16 decoder
  = **7.94B params**, load 8.3 s, resident ~16.8 GB. **No model-size
  search in V1; no larger Qwen as rescue.**
- **Adaptation:** LoRA **r=16**, alpha=32, dropout 0.05, bias=none
  (repository audit found no objective implementation mismatch; r=16
  stands).
- **Exact target-module list (smoke-verified present):**
  `q_proj, k_proj, v_proj, o_proj` (8 full-attention layers),
  `gate_proj, up_proj, down_proj` (all 32 layers),
  `in_proj_qkv, out_proj` (24 linear-attention layers).
  `in_proj_z/b/a` are NOT adapted (small aux projections; documented).
- **Frozen base weights; trainable = LoRA adapters + task heads only**
  (≈42 M LoRA params, ≈0.5 % of the decoder, plus the interaction
  projections and classification head).
- Model construction is seeded (`torch.manual_seed(fit_seed)`) so LoRA
  and head initialization are deterministic.

## 4. One interaction mechanism / readout (FROZEN)

Qwen contextualization over the typed segments **plus exactly ONE
lightweight target–Evidence interaction/readout** (no stacking):

1. Hidden states of the **last decoder layer** (`hidden_states[-1]`,
   pre-lm_head), `output_hidden_states=True`.
2. `h_t` = mean-pool of TARGET-block **content-token** hidden states
   (4096); `h_e` = mean-pool of all **available** Evidence-block
   content-token hidden states (4096). Content tokens = tokens whose
   character offsets (tokenizer `return_offsets_mapping=True`) fall
   inside value lines (`<CODE>=<value>`) of a block; header, `m=` and
   close lines are excluded. **If no Evidence block is available (state
   B), `h_e = 0` (frozen).** Token spans are computed once at data prep
   and cached (deterministic).
3. `u = W_u h_t`, `v = W_v h_e` (4096 → 256 each).
4. **Correspondence score (frozen definition):** cosine similarity with
   numerically safe L2 normalization —
   `s(u,v) = dot(u,v) / (||u||₂·||v||₂)`, norms computed as
   `sqrt(sum(sq)) + 1e-8`. At state B (`v=0`) the score is 0.
   **Score-definition change (documented): the draft (Rev 3) used the
   unnormalized dot product; the score is frozen as cosine similarity
   BEFORE this preregistration and BEFORE any formal metric. NO
   temperature, NO margin, NO extra norm loss, NO other contrastive
   objective may be added later.**
5. **Exported representation** `e = concat(u, v) ∈ R^512` — the ONLY
   representation exported for probing; **frozen before metrics; NO
   layer/representation selection after metrics.** `e` uses the raw
   (unnormalized) `u`, `v`; probing families standardize at fit time.
6. Classification head: `Linear(512 → K)` on `e`; **K = 6** (seven-class
   canonical taxonomy, one class held out per rotation). The head emits
   **RAW LOGITS; NO explicit softmax before CrossEntropyLoss.**

The mechanism is **identical in `QWEN_CE_ONLY` and `QWEN_CE_PLUS_CORR`** —
the only primary objective difference is `L_CORR`. Export runs in eval
mode, no gradient, batch 16 (frozen export batching).

## 5. Heads (FROZEN — exactly two trainable)

1. Known classification head (`L_CE`);
2. target–Evidence correspondence/reliability head (score `s`, used only
   in `L_CORR`).

**No trainable EDL head in V1; no additional novelty head.** The validated
EDL readout may be reused later as a fixed downstream diagnostic/interface
where scientifically valid.

## 6. Correspondence objective (FROZEN)

```
L = L_CE + L_CORR          (lambda_corr = 1.0, fixed; equal scale)
L_CORR = softplus(-(s_real - s_matched_shuffled))
s_real = cosine(target_i, Evidence_i)
s_matched_shuffled = cosine(target_i, Evidence_j)   (MATCHED_SHUFFLED_TRAIN)
```

`L_CE` = standard cross-entropy on the raw head logits (softmax implied
by the loss). One pairwise logistic ranking term; **no margin
hyperparameter; no contrastive/triplet/InfoNCE alternative may be
substituted after metrics.** No gradient clipping (frozen).

## 7. MATCHED_SHUFFLED negatives (FROZEN)

**Training negative: `MATCHED_SHUFFLED_TRAIN`** — Known-TRAIN rows only.
Every negative `j` for positive `i` must satisfy: same canonical Known
class; same Evidence availability/type state (`B/BT/BR/BTR`); different
underlying activity group (`activity_group_digest`); different target
row; no self or near-duplicate correspondence (mechanical rule: exclude
any pair whose serialized inputs are bit-identical).

- **Construction (frozen):** a single deterministic permutation of the
  rotation's Known-TRAIN row indices, generated from the rotation's fit
  seed; for each row `i`, `j` = first index in the permutation's cyclic
  order (starting after `i`) satisfying all constraints. **Exactly one
  negative per positive.** The pair file is written once per rotation to
  disk (`pairs.npz`) and reused identically by all three objectives of
  that rotation (B and C share data).
- **COARSE_BUCKET_MATCHING=OMIT (frozen):** the required
  (class, availability-state) matching is deterministic and tuning-free;
  any additional bucketing of continuous Evidence statistics would
  require choosing bin definitions, i.e. empirical tuning — therefore
  omitted, not a run-time scientific choice.
- **True Unknown is NEVER a training negative.**

**Evaluation diagnostic control (frozen, distinct name):
`UNRESTRICTED_SHUFFLED_EVAL`** — the earlier unrestricted SHUFFLED
condition, retained **for evaluation only** (permutation seeded, saved,
evaluation-only). The two names remain distinct in code, artifacts,
reports, protocol and metrics; **never label both simply "SHUFFLED".**

## 8. Attribution controls (FROZEN)

- **A.** `CURRENT_STATE_TRANSITION` — frozen Information Gate results,
  not rerun (denominators read from the frozen gate artifacts).
- **B.** `QWEN_CE_ONLY` (λ=0) and **C.** `QWEN_CE_PLUS_CORR` (λ=1).
- **D.** exactly ONE lightweight typed non-Qwen baseline (§11).

B and C are **identical** in: Qwen checkpoint, serialization, LoRA config,
interaction module, heads, data (rows, pair file), epochs/steps,
optimizer (AdamW lr=1e-4, weight decay 0.01, linear warmup 100 steps,
constant lr after warmup), seed set (per rotation
`20260817 + 100*r_index`, r_index 0..2 in the frozen ROTATIONS order —
the SAME seed for B, C and D of a rotation), batch construction
(deterministic epoch permutations from the fit seed, batch 2, gradient
accumulation 4 → effective batch 8). Their only scientific difference is
`lambda_corr = 0` vs `1`.

## 9. Training recipe (FROZEN)

- **Training population (per rotation, frozen):** the rotation's eval
  rows with `split_role==0` and `is_unknown==0` (Known TRAIN) — measured
  counts Credential 27,009 / Recon_Scanning 28,031 / Web_Injection
  27,357. Each row serializes at its own frozen acquired state
  (`action_P6_UTILITY_TYPED`) with its canonical label (6 classes).
  FULL frozen population, no subsetting.
- **Epochs: 2, per rotation, fixed terminal epoch.** No early stopping;
  **no checkpoint/model selection using any held-out Unknown**; no
  validation-based selection of any kind. Checkpoints exist ONLY for
  resume (every 500 steps + epoch end; resume restores epoch, global
  step, optimizer state, torch/cuda RNG states and the epoch-permutation
  position — exact continuation, no re-training loss beyond ≤500 steps).
- **Micro-batches = pairs (frozen semantics):** each micro-batch contains
  exactly ONE MATCHED_SHUFFLED_TRAIN pair — positive row `i` and its
  deterministic negative `j` — so the negative's forward runs in-batch
  and `L_CORR`'s `s_matched_shuffled = cosine(target_i, Evidence_j)`
  (§6) contributes gradients through both rows. With ~27.5 k training
  rows (one pair per row) and 2 epochs, each fit processes ~55 k pair
  micro-batches; grad accumulation 4 → ~13.7 k optimizer steps per fit.
  **Epoch permutation (frozen):** `permutation(n_pairs)` from
  `np.random.default_rng(fit_seed + 7919*(epoch+1))` — deterministic
  across resume (the checkpoint stores the position inside it, not the
  permutation itself).
- **Recipe:** AdamW lr=1e-4, weight_decay=0.01, warmup 100 steps
  (linear), constant thereafter; batch 2, gradient accumulation 4
  (effective 8); bf16 (model params bf16 + autocast); gradient
  checkpointing enabled; `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:
  True`; determinism as the frozen gates (PYTHONHASHSEED=0, cudnn
  deterministic).
- **Qwen fits = 3 rotations × {QWEN_CE_ONLY, QWEN_CE_PLUS_CORR} = 6.**
- **No hyperparameter rescue after metrics; no extra epochs after
  viewing results.**

## 10. Representation Retention Gate (FROZEN)

- Denominator: the validated Information-Gate RAW target-specific
  increments (frozen bootstrap, read from the frozen gate artifacts
  `processed/dataset_v4_nf3_ton_v1/recoverability_information_sufficiency_gate_v1/formal/aggregate.json` —
  identity-locked: `outcome==REPRESENTATION_BOTTLENECK_SUPPORTED` and
  protocol sha match; the Model B manifest records that file's sha).
- Statistic: `MODEL_B_RET_B = median_f inc_b(e,f)/inc_b(RAW,f)`,
  `MODEL_B_RET_S = median_f inc_s(e,f)/inc_s(RAW,f)` over the frozen
  families `f ∈ S(A,RAW)={RF,LR,MLP}`; per-family point ratio plus
  replicate ratios (denominator replicate > 0, same draws convention).
- **Probes (frozen):** the same diagnostic families (RF: 80 trees,
  max_depth 20, min_samples_leaf 2, balanced_subsample; LR: C=1 lbfgs;
  fixed 2-layer MLP hidden 64, AdamW 3e-4, batch 1024, max 20 epochs,
  deterministic 90/10 early-stop split — exact gate §8 recipes) applied
  to the exported `e` (512-dim). Probe A rows mirror the gate: fit on
  the two dev rotations' role-0 (recoverable|unknown) rows under REAL;
  test on the fold rotation's role-1 (recoverable|unknown) rows under
  REAL / BASIC / UNRESTRICTED_SHUFFLED_EVAL; threshold rows = the test
  recoverable-Known rows per condition (95th percentile of the fitted
  model's scores over each condition's threshold rows → Recall@5%FUR;
  mirror of the gate's per-condition probe-A convention). All
  extraction is deterministic (eval mode, batch 16). `STOP_NEEDS_REVIEW`
  if probing is mathematically invalid on the 512-dim `e`.
- **Success rule:** `MODEL_B_RET_B >= 0.50` **AND** `MODEL_B_RET_S >=
  0.50` (median over the frozen families), plus cross-rotation
  consistency (≥2/3 rotations with per-rotation median-over-families
  increments ≥ +0.02 on BOTH target-specific comparisons, and no
  rotation with median CI upper < 0 — the frozen `rotOK` shape), same
  group-atomic bootstrap framework (1000 reps, RNG 162600), no
  held-out-Unknown tuning. **If the exact statistic makes 0.50
  mathematically inappropriate (e.g. denominator ≈ 0 or negative),
  report `STOP_NEEDS_REVIEW` — never silently reuse the threshold.**
- **Primary attribution:** CURRENT_STATE_TRANSITION (A, frozen values)
  vs QWEN_CE_ONLY (B) vs QWEN_CE_PLUS_CORR (C). Closed-set Macro-F1 is
  NOT the primary Model B success criterion. The non-Qwen baseline (D)
  runs the identical probe machinery; its numbers are reported in the
  same tables, and the success rule is applied to the Qwen fits (B, C).

## 11. Known-only transfer gate (FROZEN)

- Held-out Unknown rotations are **evaluation-only**; never used for
  training, threshold selection, checkpoint selection, loss weighting,
  or early stopping.
- **Target semantics (frozen, Probe-B lineage):** `y = 1` iff the
  model's Known classification (head-logit argmax) of the row at its
  acquired Evidence state equals the canonical label — computed once at
  the acquired (REAL) state, the SAME `y` across the three test
  conditions. Fit rows = the rotation's role-0 Known rows; threshold
  rows = the same role-0 Known rows per condition (Known-only
  thresholding, 95th percentile of the fitted model's scores over each
  condition's threshold rows → Recall@5%FUR; the same physical rows as
  the fit rows, exported under all three conditions); test rows = the
  fold rotation's role-1 (recoverable|unknown) rows under
  REAL / BASIC / UNRESTRICTED_SHUFFLED_EVAL.
- **Primary metric:** pooled REAL-over-BASIC AUROC increment on held-out
  Unknown, group-atomic bootstrap (1000 reps, RNG 162600), per family.
  **Secondary:** pooled REAL-over-UNRESTRICTED_SHUFFLED_EVAL AUROC
  increment (same machinery).
- **Materiality (frozen):** point ≥ +0.02 AND 95% CI lower > 0 per
  family on the pooled increment.
- **Family aggregation (frozen):** median-over-families point ≥ +0.02
  AND **at least 2 of the 3 frozen families** pass materiality on BOTH
  comparisons — majority rule consistent with the Information Gate's
  2/3 logic; **no single family can veto** an otherwise consistent
  result.
- **Rotation consistency (frozen):** ≥ 2/3 rotations with
  median-over-families per-rotation increments ≥ +0.02 on both
  comparisons, no reversed rotation (median CI upper < 0).
- Success = material positive Known-only transfer where the frozen Probe
  B was empty (`n_B_RAW=0`).

## 12. Non-Qwen baseline (FROZEN)

Exactly one: **6-layer transformer encoder, hidden 512, 8 heads, GELU**,
consuming the SAME serialized text (identical serializer output) through
a frozen **char-level tokenizer** (deterministic charset table of the
template's ASCII alphabet — **31 distinct symbols, computed 2026-08-20
from the frozen serializer output: `'\n./0123456789<=>ABCEGIKLMNOPRTm'`**,
ids 0..30, pad id 31 — fixed mapping, no learned tokenizer), learned
position embeddings (max 1536), the same
interaction/readout module (hidden 512 → 128 projections, `e ∈ R^256`),
the same two heads (raw-logit K-way + cosine correspondence score), the
same objective `L = L_CE + L_CORR` (λ=1), the same pair file, epochs,
steps, seeds and batch construction (batch 2, accum 4). AdamW lr=1e-4,
wd=0.01, warmup 100; fp32. Params ≈ 19 M (6 × (attention 4·512² + MLP
2·512·2048) + char/position embeddings + heads — computed from the frozen
formula; **no architecture search, no baseline search**). The baseline
runs the same probe/transfer machinery (§10–§11) on its `e`; its primary
role is the attribution control for "does the Qwen backbone and scale
matter", not a gate success criterion.

## 13. Memory / runtime (measured + planned, 2026-08-20)

- GPU: RTX 4090, **48508 MiB total** (torch), 48113 MiB free before load.
- Model: load 8.3 s; decoder 7.94 B params bf16, ~16.8 GB resident.
- Sequence lengths (real TRAIN rows, Qwen tokenizer): BTR 902 max,
  BT 713, BR 735, B 546 tokens — all < 1536 cap.
- **Training measurement** (gradient checkpointing on,
  `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`):
  batch 2, seq 902 → **1801 ms/step, peak 38.4 GB allocated**
  (8.6 GB headroom), **≈1.1 rows/s**; batch 4 → 3204 ms/step,
  peak 42.1 GB, ≈1.2 rows/s. **Batch 2 + accumulation is the frozen
  scheme.**
- **Runtime estimate (corrected 2026-08-20 before freeze):** with batch 2
  and `L_CORR`'s in-batch negative, **each micro-batch is one
  MATCHED_SHUFFLED_TRAIN pair (i, j)** (§9), so 2 epochs × ~27.5 k pairs
  ≈ **55 k micro-batches ≈ 27.5 h per Qwen fit (measured 1801 ms/step at
  batch-2/seq-902, including the matched-negative forward)** →
  **~165 h for the 6 Qwen fits.** (An earlier draft estimated ~14 h/fit
  ≈ 83 h total from 27.5 k steps; that count omitted the negative
  forwards — **corrected here, before any formal metric**.) Non-Qwen
  baseline fits ~7 h (smaller model, fp32, same 55 k pair micro-batches
  ≈ 12× faster than Qwen); exported representation extraction for ALL
  probe rows — role-0 Known × 3 conditions, role-1 (rec|unk) test rows ×
  3 conditions, and the two dev rotations' probe-A fit rows under REAL,
  ≈ 120 k rows per fit × 9 fits, eval mode, batch 16, planned ≈6–8
  rows/s — ≈ **35–45 h**; probe fits + 1000-rep bootstrap + aggregation
  ≈ 10 h + 2 h; **total ≈ 215–225 h GPU wall on the single 4090.** The
  27.5 h/fit cost is measured; export throughput is the only planning
  estimate and is measured at launch before the formal export stage.

## 14. Literature / novelty boundary (CANDIDATE)

Candidate boundary (kept, CANDIDATE until researcher sign-off on final
claims): *learning and preserving target-specific recovery correspondence
under dynamic Evidence acquisition while separating it from generic
Evidence-distribution-induced Knownness.*

**No novelty claimed for:** Evidence helping Known/Unknown; EDL;
contrastive learning; AFA; Qwen traffic classification; generic
open-world continual learning. ACO ICML 2024 remains recorded as
prior-art context (reviewed 2026-08-20 at scope/objective level —
acquisition-policy method, no open-world content; see
`literature_novelty_reassessment_v1.md` §5). **No "first" claims.**

## 15. Remaining scientific ambiguities (RESOLVED AT FREEZE — NONE REMAIN)

All items carried from the design review are resolved prospectively;
**REMAINING_SCIENTIFIC_AMBIGUITIES=NONE**:

1. Training budget → FROZEN: full population, 2 epochs/rotation
   (≈ 165 h Qwen GPU wall for the 6 Qwen fits, ≈ 27.5 h/fit with the
   in-batch matched negatives; corrected from the earlier ~83 h draft
   estimate that omitted negative forwards — §13).
2. Optimizer hyperparameters → FROZEN: AdamW lr=1e-4, wd=0.01, warmup
   100 steps, constant after warmup (§9).
3. Head output details → FROZEN: `K=6` per rotation, raw logits, no
   softmax before CE (§4, §5).
4. Negative/condition labeling → FROZEN: `MATCHED_SHUFFLED_TRAIN`
   (training) vs `UNRESTRICTED_SHUFFLED_EVAL` (evaluation) are distinct
   in code, artifacts, reports, protocol and metrics (§7).
5. Correspondence score → FROZEN: cosine similarity, no temperature /
   margin / norm loss (§4, §6).

## 16. Hard boundaries + launch contract (standing)

- **NO formal training has started; NO Model-B scientific metric has
  been computed.** Formal launch is a SEPARATE future task:
  `SEPARATE_FORMAL_MODEL_B_LAUNCH_TASK`. The recorded formal launch
  command is:
  `PYTHONHASHSEED=0 python tools/run_model_b_recovery_aware_representation_v1.py --all --resume`
  (run from the repo root with the qwen35-runtime python;
  `PYTHONHASHSEED=0` is hard-asserted by the runner (frozen determinism,
  §9); `--all` = 6 Qwen fits + 3 non-Qwen baseline fits, skipping
  completed fits via `run_state.json`; `--dry-run` performs static
  validation only). **This command must NOT be executed by this task.**
- NO downloading or modifying model weights; NO larger-model rescue in V1.
- NO FINAL_TEST; NO held-out Unknown in fitting, threshold, checkpoint,
  loss-weighting, or early-stopping decisions.
- NO Recovery-Aware Novelty Interface training; NO RL/RLAIF; NO continual
  learning; NO self-evolution experiments.
- NO modification of any prior gate result; NO protocol changes after
  this freeze; NO post-metric substitution of any loss, score, probe,
  threshold or selection rule.

**NEXT_ACTION=SEPARATE_FORMAL_MODEL_B_LAUNCH_TASK ·
NEXT_ACTION_AUTHORIZED=false**
