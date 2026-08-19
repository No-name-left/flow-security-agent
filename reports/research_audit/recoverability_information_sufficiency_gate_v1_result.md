# Formal Result — Recoverability Information Sufficiency Gate V1

**Date:** 2026-08-20
**Status:** `COMPLETE` (post-run validation `PASS`)
**Outcome:** `REPRESENTATION_BOTTLENECK_SUPPORTED`

Protocol frozen at SHA256 `bd614f04…66ee1ce` (preregistration commit `28e7053`). Post-run validation independently rederived every tree input, retention statistic, and the final outcome from persisted bootstrap artifacts only — see `recoverability_information_sufficiency_gate_v1_postrun_validation.md`. The scientific outcome is **not** reinterpreted; the two implementation fixes (`a771eb6`, `121f13a`) were verified implementation-only.

---

## 1. Decision-tree inputs (all validated)

| Input | Value |
|---|---|
| `n_A_RAW` | 3 |
| `n_A_STATE_TRANSITION` | 1 |
| `n_B_RAW` | 0 |
| `n_sb_A_RAW` | 3 |
| `S_A_RAW` | `[RF, LR, MLP]` |
| `S_A_STATE_TRANSITION` | `[RF]` |
| `rotOK_A_RAW` | true |
| `rotOK_B_RAW` | false |
| `rotOK_sb_A_RAW` | true |
| Shortcut B (`n_sb_A_RAW ≥ 2`) | true |
| Shortcut C (`rotOK_sb_A_RAW`) | true |
| Shortcut D (no REAL-over-SHUFFLED material on A,RAW) | false |
| Retention bottleneck (§10.3) | true |

**Tree path (§11):** `nA=3 → rotA=true → bottleneck=true` → `REPRESENTATION_BOTTLENECK_SUPPORTED`.

## 2. Retention (§10.3) — the central statistic

`ret_b(f) = inc_b(A,ST,f) / inc_b(A,RAW,f)`, `ret_s(f) = inc_s(A,ST,f) / inc_s(A,RAW,f)`, over `f ∈ S(A,RAW)`:

| Family | ret_b | ret_s |
|---|---|---|
| RF | 0.335739 | 0.358503 |
| LR | 0.020151 | 0.025915 |
| MLP | 0.007932 | 0.082691 |

`median ret_b = 0.020151`, `median ret_s = 0.082691`, `min = 0.020151 < 0.5` → **bottleneck** (all verified to 1e-12 against `aggregate.json`).

## 3. Condition AUROC context

**RAW view** — target-specific increments are material across all three families:

| Condition | RF | LR | MLP |
|---|---|---|---|
| REAL | 0.600 | 0.737 | 0.674 |
| SHUFFLED | 0.537 | 0.592 | 0.622 |
| BASIC | 0.210 | 0.410 | 0.435 |
| NULL | 0.311 | 0.526 | 0.485 |

**STATE_TRANSITION view** — absolute AUROC is high but incremental target-specific signal is nearly gone:

| Condition | RF | LR | MLP |
|---|---|---|---|
| REAL | 0.912 | 0.961 | 0.969 |
| SHUFFLED | 0.889 | 0.958 | 0.965 |
| BASIC | 0.781 | 0.955 | 0.967 |
| NULL | 0.799 | 0.956 | 0.968 |

Per protocol §8.5, high absolute AUROC (including high BASIC-only AUROC) must **not** be read as Evidence sufficiency — the ST view has high absolute AUROC while losing the incremental REAL-over-BASIC / REAL-over-SHUFFLED signal (`n_A_ST = 1` vs `n_A_RAW = 3`; medians of the incremental signal retain only ~2–8%).

## 4. Interpretation (validated facts)

- **Target-specific information exists in legal RAW Evidence:** RAW REAL Evidence materially exceeds BOTH BASIC and SHUFFLED with cross-rotation consistency (`n_A_RAW=3`, `rotOK_A_RAW=true`).
- **A generic Evidence-distribution signal exists independently:** SHUFFLED-over-BASIC is material 3/3 with `rotOK_sb_A_RAW=true` — the model can partially guess "Evidence is present" without knowing *which* target.
- **Target-specific REAL-over-SHUFFLED remains material:** 3/3 families (`D=false`), so the RAW signal is not reducible to generic Evidence-induced Knownness.
- **The current STATE_TRANSITION abstraction loses most of it:** only RF remains material on ST (`n_A_ST=1`); median retention 0.020 (basic-over) / 0.083 (shuffled-over).
- **Known-only open-world transfer remains unsolved:** `n_B_RAW=0`, `rotOK_B_RAW=false` — no family transfers material Evidence signal from Known-only training to whole-class-held-out Unknown.

**Conclusion:** target-specific information exists in legal RAW Evidence while the current state abstraction loses much of it, and Known-only open-world transfer remains unsolved → **REPRESENTATION_BOTTLENECK_SUPPORTED**.

## 5. What this does NOT establish

- No Evidence-availability *policy* (acquisition) was tested — that is a separate gate.
- No claim about optimal Evidence volume/type composition.
- `n_B_RAW=0` does not rule out transfer by a stronger representation; it establishes that the current abstraction + these three families do not transfer.

## 6. Boundaries

`FINAL_TEST_USED=false` · `MODELS_RETRAINED=false` · `PROTOCOL_CHANGED=false` · `RESULT_COMMITTED=false` · `RESULT_PUSHED=false`

## 7. Artifacts

Run root: `processed/dataset_v4_nf3_ton_v1/recoverability_information_sufficiency_gate_v1/` — `formal/aggregate.json`, `formal/run_manifest.json`, `formal/bootstrap/` (9 × 1000-rep), `formal/probe_A/` (18 fits), `formal/probe_B/` (9 fits), `formal/mlp_epochs/` (9 × 20 epochs).

## 8. Next step (not yet authorized)

`MODEL_B_DESIGN_JUSTIFIED=true` — the bottleneck outcome is the scientific justification for designing a stronger typed-Evidence representation (Model B). `MODEL_B_TRAINING_STARTED=false`. Draft protocol under researcher review (see `docs/research_plan/model_b_recovery_aware_representation_v1_protocol.md`).
