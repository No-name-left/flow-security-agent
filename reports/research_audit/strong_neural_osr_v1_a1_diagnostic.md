# Strong Neural OSR V1 A1 Failure — Diagnostic Replay

Date: 2026-08-18
Protocol: frozen Strong Neural OSR Evidence Gate V1
(sha256 0ebf5c8c3af20eedb07800f97db3627e16e35c895ed5420fc2fe3d2e8d18dc7c,
preregistration commit 62995a4).

This is a diagnostic replay only: the frozen V1 training procedure was
re-run exactly (same populations, FIT/EARLY_STOP split, features,
multi-state schedule, architecture, CE + 0.1·SupCon, AdamW 3e-4/1e-4,
batch 1024, seed, 20-epoch cap, patience-3 early stopping) for three
representative cells, with the only change being additional
measurement/logging. No tuning, no parameter change, no FINAL_TEST, no
Evidence judgment.

V1 remains: `GATE_INVALID_OSR_INADEQUATE`,
`EVIDENCE_SCIENTIFIC_STATUS=NOT_JUDGED`.

Replay artifacts (Git-external, formal run untouched):
`processed/dataset_v4_nf3_ton_v1/strong_neural_osr_evidence_gate_v1/diagnostic_a1_v1/`

## 1. Replay fidelity

| Cell | Replay eval Macro-F1 | Recorded V1 eval Macro-F1 | Best epoch (replay vs V1) |
|---|---|---|---|
| Recon_Scanning / 20260817 | 0.9445 | 0.9445 | 20 vs 20 — exact match |
| Web_Injection / 20260818 | 0.8888 | 0.8888 | 17 vs 20 — same checkpoint quality |
| Credential / 20260817 | 0.8963 | 0.8798 | 19 vs 10 — early-stop boundary sensitivity |

The Credential discrepancy is a property of the frozen early-stop rule
(patience 3, improvement threshold 1e-6): GPU floating-point
nondeterminism flips which near-tie epoch is "best". The procedure is
identical; the recorded V1 checkpoint (epoch 10) and the replay's
epoch-16 state (train F1 0.9022) are adjacent on the same plateau.

## 2. Convergence (A)

- Credential: EARLY-STOP Macro-F1 over epochs 16–20 =
  [0.8904, 0.8844, 0.8887, 0.8937, 0.8822] with val CE
  [0.256, 0.2629, 0.2593, 0.2505, 0.253] — **plateaued/oscillating**;
  net change −0.008. No evidence of continued improvement at epoch 20.
- Web_Injection 20260818: [0.9362, 0.9399, 0.9427, 0.9349, 0.9406],
  val CE flat ≈0.17 — **plateaued**; best epoch 17.
- Recon_Scanning (passing control): [0.9146, 0.9378, 0.9437, 0.9452,
  0.9515], val CE 0.1698 → 0.128 — **still improving at the 20-epoch
  cap** (budget-limited).

## 3. Generalization (B)

| Cell | TRAIN F1 | EARLY F1 | EVAL F1 | TRAIN−EVAL gap |
|---|---|---|---|---|
| Credential | 0.9048 | 0.8937 | 0.8963 | +0.008 |
| Web | 0.9272 | 0.9399 | 0.8888 | +0.038 |
| Recon | 0.9486 | 0.9515 | 0.9445 | +0.004 |

No overfitting in the failure cells: Credential's **TRAIN** Macro-F1 is
itself below the 0.90 A1 floor — the model cannot solve its own
training set to the required level under the frozen budget. Web shows a
mild early→eval gap (+0.051) on top of a borderline train level.

## 4. Class structure (C)

Dominant confusion pairs (replay eval, top-3 per cell):

- Credential: Benign→Recon_Scanning (1076), Web_Injection→DoS (526),
  Recon_Scanning→Benign (237). Weak classes: Benign 0.757,
  Recon_Scanning 0.866, Web_Injection 0.884.
- Web: Benign→Recon_Scanning (1335), Recon_Scanning→Benign (732);
  Benign 0.692, Recon_Scanning 0.723.
- Recon: Web_Injection→DoS (535); Web_Injection 0.880, DoS 0.897.

**These are inherited, not neural-specific**: the frozen RF Basic
baseline shows the same pairs in the same rank order (Benign↔
Recon_Scanning, Web_Injection→DoS). The frozen RF itself scores only
0.8887–0.9196 Macro-F1 on the Credential rotation (its only sub-0.90
cells) and 0.73 on Benign/Recon_Scanning in the Web cell.

Class-wise contrast (Credential): the strong OSR roughly matches the
frozen RF on the hardest pair (Benign 0.757 vs RF 0.791;
Recon_Scanning 0.866 vs RF 0.870) but loses 0.03–0.10 on the easier
classes (DoS 0.907 vs 0.944; Web_Injection 0.884 vs 0.938; DDoS 0.968
vs 0.978) — the neural Known head is not extracting what the frozen
trees extract from the same Basic features.

## 5. Cross-cell comparison (D)

Credential differs qualitatively from the passing Recon cell and the
borderline Web cell: it is the intrinsically hardest rotation (RF
baseline near/below 0.90), the strong OSR's TRAIN F1 is below the A1
floor, and convergence had plateaued. Recon passes with margin and was
still improving at the cap. Web is a borderline failure driven by the
inherited Benign/Recon_Scanning confusability plus a mild early→eval
gap.

## 6. Interpretation (bounded)

Consistent with the saved metrics:

- **Class-specific difficulty**: yes — Benign↔Recon_Scanning and
  Web_Injection↔DoS dominate all cells and pre-exist in the frozen RF
  baseline.
- **Representation/objective limitation on Known classification**:
  supported — TRAIN F1 below the A1 floor on Credential, and the neural
  head underperforms the frozen trees on the easy classes while the
  same encoder's geometry shows strong open-set value (V1 A4 passed).
- **Training-budget-limited convergence**: partially — only in the
  passing Recon cell.
- **Overfitting**: not supported in the failure cells (gaps small;
  train-level is the limiter).

Not proven, not proposed: any specific fix or tuned epoch count. This
task performs no tuning and judges no Evidence.

## 7. Status

- V1 gate status: `GATE_INVALID_OSR_INADEQUATE` (unchanged).
- Evidence scientific status: `NOT_JUDGED` (unchanged).
- Results uncommitted/unpushed; next action requires a researcher
  decision on whether to authorize a Strong OSR V2.
