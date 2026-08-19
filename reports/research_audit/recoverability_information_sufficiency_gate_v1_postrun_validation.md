# Post-Run Validation — Recoverability Information Sufficiency Gate V1

**Date:** 2026-08-20
**Status:** `PASS`
**Outcome rederived:** `REPRESENTATION_BOTTLENECK_SUPPORTED` (matches the recorded formal outcome)

This is an independent post-run validation performed **only on persisted formal artifacts**. No model was retrained, no fit was recomputed, no protocol/rule was changed, and no FINAL_TEST was used.

---

## 1. Protocol SHA identity — PASS

| Source | SHA256 |
|---|---|
| Frozen constant | `bd614f04…66ee1ce` |
| Protocol file (recomputed) | `bd614f04…66ee1ce` |
| Preregistration JSON | `bd614f04…66ee1ce` |
| aggregate.json | `bd614f04…66ee1ce` |
| run_manifest.json | `bd614f04…66ee1ce` |
| run_state.json | `bd614f04…66ee1ce` |

## 2. Run state — COMPLETE

`run_state.json`: `status=COMPLETE`, `mode=formal`, outcome `REPRESENTATION_BOTTLENECK_SUPPORTED`, matching `aggregate.json`; execution lock reported `match=true`.

## 3. Artifact counts — valid

- Probe A: 18 `scores.npz` + 18 `metrics.json`
- Probe B: 9 `scores.npz` + 9 `metrics.json`
- Bootstrap: 9 JSONs, each with 1000 AUROC-increment replicates
- MLP epoch logs: 9 (6 probe-A + 3 probe-B), 20 epochs each
- Spot-checked `probe_A/Credential/RF/RAW/metrics.json`: all four conditions (BASIC/NULL/REAL/SHUFFLED) with `auroc`/`aupr`/`recall_at_5fur`/`threshold` present.

## 4. Rederived tree inputs (independent replay from bootstrap JSONs)

Reimplemented §10.1–10.3 and §11 directly from the protocol text; compared against `aggregate.json` — **all identical**:

| Input | Rederived | aggregate.json |
|---|---|---|
| `n_A_RAW` | 3 | 3 |
| `n_A_STATE_TRANSITION` | 1 | 1 |
| `n_B_RAW` | 0 | 0 |
| `n_sb_A_RAW` | 3 | 3 |
| `S_A_RAW` | `[RF, LR, MLP]` | `[RF, LR, MLP]` |
| `rotOK_A_RAW` | true | true |
| `rotOK_B_RAW` | false | false |
| `rotOK_sb_A_RAW` | true | true |
| shortcut `B` (`n_sb ≥ 2`) | true | true |
| shortcut `C` (`rotOK_sb`) | true | true |
| shortcut `D` (no REAL-over-SHUFFLED material on A,RAW) | false | false |

## 5. Retention (§10.3) — rederived

`ret_b(f) = inc_b(A,ST,f) / inc_b(A,RAW,f)`, `ret_s(f) = inc_s(A,ST,f) / inc_s(A,RAW,f)` over `f ∈ S(A,RAW)`:

| Family | ret_b | ret_s |
|---|---|---|
| RF | 0.335739 | 0.358503 |
| LR | 0.020151 | 0.025915 |
| MLP | 0.007932 | 0.082691 |

- `median ret_b = 0.020151`; `median ret_s = 0.082691`
- `BOTTLENECK` iff `min(median ret_b, median ret_s) < 0.5` → `min = 0.020151 < 0.5` → **true**
- All per-family points and medians match `aggregate.json` to 1e-12.

## 6. Final decision-tree outcome — rederived and matched

- Inline reimplementation of protocol §11 Steps 1–4 from the protocol text: `REPRESENTATION_BOTTLENECK_SUPPORTED`
- Frozen decision-tree tool (`verify_recoverability_gate_decision_tree.py`): `REPRESENTATION_BOTTLENECK_SUPPORTED`
- `aggregate.json`: `REPRESENTATION_BOTTLENECK_SUPPORTED`

All three agree. The scientific outcome is **not** reinterpreted.

## 7. Commit `121f13a` — implementation-only

- Files changed: **only** `tools/run_recoverability_information_sufficiency_gate_v1.py` (4 insertions, 3 deletions)
- Changes: (a) S6 retention call site passes the view-keyed dict `{"RAW": …, "ST": …}` to `retention()` — the function's documented contract, matching protocol §10.3 `ret(f) = inc(ST,f)/inc(RAW,f)`; (b) S5 log/marker label corrected from "27 keys" to "9 keys" (27 is the fit count; 9 bootstrap keys were always written).
- No protocol file, preregistration, decision-tree tool, threshold, metric formula, or decision rule was modified.

## 8. Boundaries

`FINAL_TEST_USED=false` · `MODELS_RETRAINED=false` · `PROTOCOL_CHANGED=false` · `RESULT_COMMITTED=false` · `RESULT_PUSHED=false`

---

## Verdict

**VALIDATION_STATUS = PASS** — every rederived tree input, retention statistic, and the final outcome match the persisted formal artifacts exactly; the S6 fix is implementation-only.
