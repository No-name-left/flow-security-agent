# Edge Paper-Grade Split Revision v2

Audit date: 2026-08-11

`SPLIT_REVISION_STATUS=PASS_WITH_LIMITATIONS`

This is a pre-model data-protocol revision and audit, not a paper result. No Qwen, SFT, TShark, canonical reconstruction, sessionization, K/U change, or dataset-role change occurred.

## Final Gates

- `LABEL_PROVENANCE_FINAL_GATE=PASS`
- `SPLIT_REVISION_DESIGN=PASS_FOR_REBUILD`
- `PAPER_EVALUATION_READINESS_GATE=PASS_WITH_LIMITATIONS`
- `CLASS_ROLE_SUPPORT_GATE=PASS`
- `IDENTITY_CROSS_SPLIT_LEAKAGE=0`
- `U_FINAL_ISOLATION=PASS`
- `LOW_RESOURCE_STRESS_TEST_STATUS=PLANNED_OPTIONAL_NOT_RUN`
- `PRODUCTION_RUNTIME_ADAPTER_READY=false`
- `QWEN_RUN=false`; `SFT_RUN=false`

## Label provenance final verification

All 24 official Edge captures passed PCAP/CSV identity, source mapping, expected-label and purity checks: 14 attack captures each contain only `1|expected fine label`; 10 Normal captures contain only `0|Normal`; all report purity 1.0 and `session_crosses_capture=false`.

- Direct-evidence sessions: 0
- Verified-capture fallback sessions: 7,619,032
- Conflict quarantine: 0
- Unmatched/provenance quarantine: 0

Formal packet/frame direct matching is unavailable because the official companion CSVs do not expose a stable frame number or absolute frame timestamp. The defensible paper wording is verified single-label capture provenance plus within-capture session reconstruction—not human session-level ground truth.

## Phase A candidate comparison

| Candidate | Train | Validation | Test | Quarantine | ZERO | CRITICAL_LOW | Edge exact cross-split | Edge near cross-split |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `CURRENT_WALL_CLOCK_SPAN_CHRONOLOGICAL` | 5,162,702 | 1,030,853 | 1,183,626 | 241,851 | 1 | 2 | 2,014 | 7,589 |
| `NAIVE_SESSION_START_QUANTILE` | 5,333,310 | 1,142,856 | 1,142,866 | 0 | 0 | 0 | 2,150 | 8,070 |
| `PER_CAPTURE_SESSION_CROSSING_ONLY` | 5,329,148 | 1,140,735 | 1,142,861 | 6,288 | 0 | 1 | 2,150 | 7,936 |
| `PER_CAPTURE_LOCAL_EMBARGO_5S` | 5,293,881 | 1,073,363 | 1,111,053 | 140,735 | 0 | 2 | 2,077 | 7,875 |
| `CONSTRAINED_CHRONOLOGICAL_BOUNDARY_V2` | 5,294,777 | 1,073,539 | 1,110,343 | 140,373 | 0 | 0 | 2,118 | 7,892 |

The selected v2 exactly matches the materialized assignment manifest. Relative to current Production assignment it changes ZERO by -1 and CRITICAL_LOW by -2, while Edge-only exact/near collision groups change by +104/+303. Model-view equality is not backend identity; the combined Edge+IoT selected audit reports exact 2,387, near 7,956, identity leakage 0, 0 FAIL and 3 disclosed limitations.

## OLD/NEW 15-class split and training diversity

| Fine label | Coarse parent | Old T/V/E | New T/V/E | New train exact/near | New val/test status |
| --- | --- | ---: | ---: | ---: | --- |
| Backdoor | Malware | 541/346/470 | 995/211/213 | 568/34 | ADEQUATE/ADEQUATE |
| DDoS_HTTP | Availability | 6,321/1,182/1 | 5,379/162/842 | 5,371/5,106 | ADEQUATE/ADEQUATE |
| DDoS_ICMP | Availability | 1,512,030/348,614/421,101 | 1,674,160/346,229/355,305 | 3,765/1,817 | ADEQUATE/ADEQUATE |
| DDoS_TCP | Availability | 825,440/165,622/164,109 | 818,189/165,437/172,237 | 1,038/46 | ADEQUATE/ADEQUATE |
| DDoS_UDP | Availability | 2,282,536/418,347/427,132 | 2,232,637/442,183/461,556 | 5/5 | ADEQUATE/ADEQUATE |
| MITM | ManInTheMiddle | 192/13/22 | 151/33/31 | 36/36 | LOW/LOW |
| Normal | Benign | 511,023/67,467/99,789 | 475,650/100,720/101,367 | 469,897/16,045 | ADEQUATE/ADEQUATE |
| OS_Fingerprinting | Reconnaissance | 139/30/33 | 144/33/31 | 73/11 | LOW/LOW |
| Password | CredentialAccess | 3,958/26,070/66,029 | 67,237/14,378/14,394 | 66,249/9,384 | ADEQUATE/ADEQUATE |
| Port_Scanning | Reconnaissance | 7,532/1,542/1,591 | 7,632/1,620/1,634 | 231/35 | ADEQUATE/ADEQUATE |
| Ransomware | Malware | 232/0/1,132 | 1,019/200/136 | 419/30 | ADEQUATE/ADEQUATE |
| SQL_injection | Injection | 2,952/666/641 | 3,044/585/669 | 3,014/2,620 | ADEQUATE/ADEQUATE |
| Uploading | FileTransfer | 6,425/352/854 | 5,187/1,031/1,209 | 3,647/283 | ADEQUATE/ADEQUATE |
| Vulnerability_scanner | Reconnaissance | 2,078/300/427 | 2,019/432/433 | 1,867/1,674 | ADEQUATE/ADEQUATE |
| XSS | Injection | 1,303/302/295 | 1,334/285/286 | 859/320 | ADEQUATE/ADEQUATE |

ZERO: 1 → 0; CRITICAL_LOW: 2 → 0.

## Near/Far/Mixed readiness

| Preset | K classes | ZERO | CRITICAL_LOW | LOW | ADEQUATE | Train-insufficient |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Far | 12 | 0 | 0 | 1 | 11 | DDoS_UDP, OS_Fingerprinting |
| Mixed | 11 | 0 | 0 | 1 | 10 | DDoS_UDP, OS_Fingerprinting |
| Near | 11 | 0 | 0 | 1 | 10 | none |

`LOW_RESOURCE_KNOWN=DDoS_UDP,MITM,OS_Fingerprinting`

`STRUCTURALLY_INSUFFICIENT_KNOWN=DDoS_UDP,OS_Fingerprinting`

## SFT PLAN_B materialization

Eligibility is only `K_known ∩ physical train`. Validation, test, U_dev and U_final are forbidden. Selection covers near groups first, exact groups second, then bounded deterministic multiplicity. All selected sample IDs are real and unique; token counts are estimates because the renderer/tokenizer is not frozen.

| Class | Raw train | Selected | Fraction | Exact selected/available | Near selected/available | Compression | Near share | Far share | Mixed share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Backdoor | 995 | 659 | 66.2312% | 568/568 (100.00%) | 34/34 (100.00%) | 1.51× | 3.88% | 4.15% | 4.28% |
| DDoS_HTTP | 5,379 | 2,048 | 38.0740% | 2,048/5,371 (38.13%) | 2,048/5,106 (40.11%) | 2.63× | 12.06% | 12.88% | 13.30% |
| DDoS_ICMP | 1,674,160 | 2,048 | 0.1223% | 2,047/3,765 (54.37%) | 1,817/1,817 (100.00%) | 817.46× | — | 12.88% | 13.30% |
| DDoS_TCP | 818,189 | 2,048 | 0.2503% | 1,038/1,038 (100.00%) | 46/46 (100.00%) | 399.51× | 12.06% | 12.88% | 13.30% |
| DDoS_UDP | 2,232,637 | 49 | 0.0022% | 5/5 (100.00%) | 5/5 (100.00%) | 45564.02× | — | 0.31% | 0.32% |
| MITM | 151 | 105 | 69.5364% | 36/36 (100.00%) | 36/36 (100.00%) | 1.44× | 0.62% | — | — |
| Normal | 475,650 | 2,048 | 0.4306% | 2,048/469,897 (0.44%) | 2,048/16,045 (12.76%) | 232.25× | 12.06% | 12.88% | 13.30% |
| OS_Fingerprinting | 144 | 126 | 87.5000% | 73/73 (100.00%) | 11/11 (100.00%) | 1.14× | — | 0.79% | 0.82% |
| Password | 67,237 | 2,048 | 3.0459% | 2,048/66,249 (3.09%) | 2,048/9,384 (21.82%) | 32.83× | 12.06% | — | — |
| Port_Scanning | 7,632 | 1,530 | 20.0472% | 231/231 (100.00%) | 35/35 (100.00%) | 4.99× | 9.01% | 9.63% | 9.93% |
| Ransomware | 1,019 | 491 | 48.1845% | 419/419 (100.00%) | 30/30 (100.00%) | 2.08× | 2.89% | 3.09% | — |
| SQL_injection | 3,044 | 2,048 | 67.2799% | 2,048/3,014 (67.95%) | 2,048/2,620 (78.17%) | 1.49× | 12.06% | 12.88% | — |
| Uploading | 5,187 | 2,048 | 39.4833% | 2,044/3,647 (56.05%) | 283/283 (100.00%) | 2.53× | 12.06% | — | 13.30% |
| Vulnerability_scanner | 2,019 | 1,906 | 94.4032% | 1,867/1,867 (100.00%) | 1,674/1,674 (100.00%) | 1.06× | 11.23% | 11.99% | 12.37% |
| XSS | 1,334 | 894 | 67.0165% | 859/859 (100.00%) | 320/320 (100.00%) | 1.49× | — | 5.62% | 5.80% |

| Preset | Sessions/cards | Estimated tokens @768 | Relative compute vs raw train | Largest/smallest class | Duplicate IDs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Far | 15,895 | 12,207,360 | 0.003044 | 41.80 | 0 |
| Mixed | 15,404 | 11,830,272 | 0.002949 | 41.80 | 0 |
| Near | 16,979 | 13,039,872 | 0.012246 | 19.50 | 0 |

### DDoS structural-redundancy audit

| Class | Raw train | Selected | Exact available | Near available | Compression | Average selected/exact group | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| DDoS_UDP | 2,232,637 | 49 | 5 | 5 | 45564.02× | 9.80 | STRUCTURAL_EVIDENCE_REDUNDANCY |
| DDoS_ICMP | 1,674,160 | 2,048 | 3,765 | 1,817 | 817.46× | 0.54 | HIGH_RAW_REDUNDANCY_COMPRESSED |
| DDoS_TCP | 818,189 | 2,048 | 1,038 | 46 | 399.51× | 1.97 | HIGH_RAW_REDUNDANCY_COMPRESSED |

## Low-resource optional candidate pool

| Class | Parent | Sessions | Train | Exact | Near | Shared parent possible | Rationale |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| Backdoor | Malware | 1,424 | 995 | 568 | 34 | YES | raw_session_scarcity |
| DDoS_UDP | Availability | 3,215,242 | 2,232,637 | 5 | 5 | YES | train_exact_diversity_scarcity, train_near_diversity_scarcity |
| MITM | ManInTheMiddle | 227 | 151 | 36 | 36 | NO | raw_session_scarcity |
| OS_Fingerprinting | Reconnaissance | 214 | 144 | 73 | 11 | YES | raw_session_scarcity, train_near_diversity_scarcity |
| Ransomware | Malware | 1,364 | 1,019 | 419 | 30 | YES | raw_session_scarcity |
| XSS | Injection | 1,913 | 1,334 | 859 | 320 | YES | raw_session_scarcity |

This pool is selected only from pre-model metadata/diversity. It is not a frozen held-out set, does not change Near/Far/Mixed, and has not been executed.

## Identity, split-dependent assets and context

- Edge identity universe before/after: 7,619,032/7,619,032; distinct 7,619,032; ordered SHA256 `bf1d1f554b62bdec977e17554d9cbd3b2f3fc6a9592245cd1e981fe3caa83ce3`; unchanged=true.
- Formal v2 counts: train 5,294,777; validation 1,073,539; test 1,110,343; quarantine 140,373.
- Temporal, relation and sample-ID indexes were rebuilt as split-dependent assets; each contains 7,670,824 rows including unchanged IoT-23 assets. Future-context violations are 0 and context resets at capture/scenario + split.
- One reconstructed session remains one primary result. DDoS/scanning/reconnaissance cross-flow evidence remains past-only Temporal Context plus optional Graph Context; sessions are not permanently merged.
- Initial packets 1–8 and expandable packets 9–16 remain implemented. Application evidence and sanitized payload stores remain unimplemented; raw PCAP remains the source of truth.

## Sensitivity and limitations

- `EXACT_EVAL_CLEAN` and `NEAR_EVAL_CLEAN` keep training unchanged and remove collided evaluation identities only; Primary remains the real chronological distribution.
- Edge attack labels are strongly capture-coupled and usually have one capture per fine class. Results cannot claim cross-attack-run generalization.
- MITM and OS_Fingerprinting evaluation support remains LOW; DDoS_UDP and OS_Fingerprinting training diversity is structurally insufficient under the 30-group reference.
- Official Edge CSVs do not support formal frame-exact direct label mapping; verified capture fallback is valid but is not manual session-level truth.
- Token totals are estimates until the Evidence Card renderer and tokenizer contract are frozen.
- Optional Low-Resource Unknown Stress Test remains `PLANNED_OPTIONAL_NOT_RUN`.

## Synchronization and verification

- Updated: canonical detailed plan and DEC-0013 through DEC-0016, timeline, brief, PROJECT_HANDOFF, README, SERVER_MIGRATION and AGENTS.
- Reviewed unchanged: `docs/design/agent_architecture_provisional.md`; this revision adds no new Agent and changes no Runtime semantics.
- Focused split tests: 6 passed.
- Full regression: 240 passed.
- Syntax/compile check: PASS.
- `git diff --check`: PASS before staging; staged check is required before commit.
- Complete data assets remain Git-external under `/root/autodl-tmp/processed/edge_split_revision_v2/`; only code, tests, tools and small reports/docs enter Git.
