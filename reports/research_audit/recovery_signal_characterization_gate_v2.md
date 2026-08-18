# Recovery-Signal Characterization and Open-World Transfer Gate V2 — Report

Date: 2026-08-17  |  Head: 22c92c7
Protocol: FROZEN_BEFORE_EVALUATION (sha256 b1d01629215470ba425c52f76dc5547c8bf4cb8e810a1ebcad30a853be2a5b7b)

Frozen context: Gate 1 YELLOW, Gate 1B PASS, Open-World V1 FAIL (unchanged), V1 failure attribution COMPLETE.

## Signal characterization
- LINEAR_SIGNAL = NOT_ESTABLISHED
- NONLINEAR_SIGNAL = NOT_ESTABLISHED
- RECOVERY_TRAJECTORY_SIGNAL = WEAK

| rotation | linear ΔAUROC | nonlinear ΔAUROC |
|---|---|---|
| Credential | -0.0029 | -0.0028 |
| Recon_Scanning | +0.0058 | +0.0053 |
| Web_Injection | +0.0031 | -0.0005 |

## Open-world trajectory transfer
T1=False T2=True T3=True T4=True T5=False -> OPEN_WORLD_TRAJECTORY_TRANSFER = NOT_ESTABLISHED

## End-to-end
E1=False E2=False E3=False E4=False -> END_TO_END_OPEN_WORLD_GAIN = NOT_ESTABLISHED

## Interpretation
CASE D
C1_STATUS = RECOVERY_SIGNAL_INCONCLUSIVE
NEXT_PROPOSED_ACTION = RESEARCHER_REASSESS_COST_BENEFIT_BEFORE_MODEL_B

## Pooled FURK (weighted)

| method | numerator | denominator | rate |
|---|---|---|---|
| B0_BASIC_MSP | 2770 | 9483 | 0.2921 |
| B1_UTILITY_POST_MSP | 5000 | 9483 | 0.5273 |
| L_POST | 5439 | 9483 | 0.5736 |
| L_TRAJ | 5517 | 9483 | 0.5818 |
| N_POST | 4899 | 9483 | 0.5166 |
| N_TRAJ | 4743 | 9483 | 0.5002 |

## Safety ledger

All entries false / zero (see JSON report for the full ledger).

V2_RESULT_COMMITTED=false | V2_RESULT_PUSHED=false | CURRENT_AUTHORIZED_TASK=NONE_WAITING_RESEARCHER | NEXT_ACTION_AUTHORIZED=false