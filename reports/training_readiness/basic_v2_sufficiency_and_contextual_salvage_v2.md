# Basic-v2 Sufficiency and Contextual Salvage v2

> Audit version: `BASIC_V2_SUFFICIENCY_AND_CONTEXTUAL_SALVAGE_V2`
>
> Scope: accepted six-class formal corpus plus read-only MITM/Port_Scanning salvage
>
> Result: `PASS`; formal corpus unchanged; no model or external API used
>
> Machine manifest: [`basic_v2_sufficiency_and_contextual_salvage_v2.json`](basic_v2_sufficiency_and_contextual_salvage_v2.json)

## 1. Primary Basic-v2 sufficiency

The audit parsed every formal row as `SFTRecordV2` and selected only rows that
simultaneously satisfy `state_role=primary`, `classification_ce_eligible=true`,
and `stage_type=EvidenceStageV2.BASIC`. It did not infer the primary state from
record ordering or from a historical field name.

The accepted corpus SHA256 remains
`d93789de29b746d923660bb2e4ccad501412e75303ddf95f7087c85f6c67d6ca`.

| Metric | Count | Rate over 11,958 primary Basic states |
| --- | ---: | ---: |
| Evidence sufficient / zero gap | 10,119 | 84.621174% |
| Evidence insufficient | 1,839 | 15.378826% |
| Single gap | 1,431 | 11.966884% |
| Multi gap | 408 | 3.411942% |

In `EvidenceStateV2`, sufficient means an empty `missing_evidence`, null
`primary_gap`, `gap_type=NONE`, and `recoverability=ALREADY_SUFFICIENT`.
Validation of all 11,958 primary rows found zero violations, so zero-gap and
Evidence-sufficient are exactly equivalent in this formal corpus.

The 84.62% rate is suitable for the current Agent question: Basic-v2 resolves a
large easy/clear subset without unnecessary acquisition, while 15.38% retains a
real evidence-acquisition route. The remaining demand is class-conditional,
rather than an artificial uniform mask. Basic-v2 should not be weakened merely
to increase tool use.

## 2. Per-class Basic-v2 sufficiency

| Fine class | Primary Basic N | Sufficient N | Sufficient rate | Insufficient N | Single gap | Multi gap |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Normal | 1,985 | 1,985 | 100.000000% | 0 | 0 | 0 |
| DDoS_HTTP | 2,014 | 1,101 | 54.667329% | 913 | 654 | 259 |
| DDoS_TCP | 2,048 | 1,188 | 58.007812% | 860 | 720 | 140 |
| Password | 2,048 | 2,048 | 100.000000% | 0 | 0 | 0 |
| SQL_injection | 2,048 | 2,048 | 100.000000% | 0 | 0 | 0 |
| Vulnerability_scanner | 1,815 | 1,749 | 96.363636% | 66 | 57 | 9 |

Normal, Password, and SQL_injection are intentionally easy under Basic-v2
because their retained observations already contain real, legal evidence. The
Agent's principal additional-Evidence opportunity is DDoS_HTTP and DDoS_TCP,
with a small residual Vulnerability_scanner tail. This is a property of the
cleaned population, not a reason to hide cheap evidence.

## 3. Missing Evidence distribution

One multi-gap state contributes once to every missing family. Percentages below
use the class's insufficient-primary count as denominator; the parenthesized
percentage uses all primary Basic states in that class.

| Fine class | PACKET_PAYLOAD | APPLICATION | TEMPORAL | RELATION | KNOWLEDGE |
| --- | ---: | ---: | ---: | ---: | ---: |
| DDoS_HTTP | 844; 92.442497% (41.906653%) | 264; 28.915663% (13.108242%) | 154; 16.867470% (7.646475%) | 96; 10.514786% (4.766634%) | 1; 0.109529% (0.049652%) |
| DDoS_TCP | 634; 73.720930% (30.957031%) | 64; 7.441860% (3.125000%) | 334; 38.837209% (16.308594%) | 50; 5.813953% (2.441406%) | 1; 0.116279% (0.048828%) |
| Normal | 0 | 0 | 0 | 0 | 0 |
| Password | 0 | 0 | 0 | 0 | 0 |
| SQL_injection | 0 | 0 | 0 | 0 | 0 |
| Vulnerability_scanner | 60; 90.909091% (3.305785%) | 9; 13.636364% (0.495868%) | 7; 10.606061% (0.385675%) | 12; 18.181818% (0.661157%) | 0 |

`TOP_MISSING_EVIDENCE_BY_CLASS` is therefore:

- DDoS_HTTP: `PACKET_PAYLOAD` (92.44% of insufficient primary states), then
  `APPLICATION` (28.92%).
- DDoS_TCP: `PACKET_PAYLOAD` (73.72%), then `TEMPORAL` (38.84%).
- Vulnerability_scanner: `PACKET_PAYLOAD` (90.91%), then `RELATION` (18.18%).
- Normal, Password, SQL_injection: no missing family among primary Basic states.

The historical Initial/Teacher-V3 percentage is not directly comparable.
`OLD_NEW_DIRECT_COMPARISON=NOT_VALID`: the old population, Evidence schema,
Initial representation, and primary-stage assignment differ materially, so a
numerical before/after claim would compare different estimands.

## 4. MITM contextual salvage

The audit implemented an independent `PAST_ONLY_NETWORK_RELATION_GRAPH_V2`.
Its inputs contain no label, capture filename, split role, or model output. For
each target it uses only ARP claims in the same backend observation scope and
partition, within one of the fixed windows 10/60/180/300 seconds, and strictly
before the target timestamp. Backend locality identifiers and raw addresses do
not appear in the model-safe projection.

The fixed mechanism requires either a repeated same-IP/multiple-MAC conflict or
one MAC making at least two repeated source-IP claims toward one common target.
Each of the two source-IP claims must occur at least twice. This reliability
floor is protocol-semantic and was not fit to a class or capture.

The MITM source contains a persistent repeated dual-IP/common-target ARP
pattern. The shortest supporting horizon is 60 seconds for all supported
targets. Results:

| Metric | Value |
| --- | ---: |
| Total reconstructed sessions | 227 |
| Contextually / fully observationally supported | 204 (89.867841%) |
| Entity-linked Level A | 64 |
| Bounded local-network Level B | 140 |
| Supported train | 150 / 151 |
| Supported validation | 25 / 33 |
| Supported test | 24 / 31 |
| Supported quarantine | 5 / 12 |

The evidence itself is sufficient to establish an MITM-like shared L2 state,
so `MITM_CAPTURE_LABEL_REQUIRED=false`. It does not automatically make MITM a
stable main training class. Only 150/25/24 supported train/validation/test
sessions remain, 68.63% of supported sessions rely on shared Level-B context,
and all observations come from one capture/run. That is too narrow for a stable
primary-class training and Macro-F1 estimate relative to the approximately
2,000-session formal classes. The scientific verdict is therefore
`MITM_SALVAGE_STATUS=PASS_CASE_STUDY_ONLY`, consistent with retaining MITM as a
bounded Relation/ARP audit case rather than formal classification CE. This is
an experimental audit verdict, not a formal reassignment of MITM's frozen role.

## 5. Port_Scanning contextual salvage

The scan builder is likewise label-free and partition-local. For each session
it aggregates only same-source sessions whose end timestamp is strictly before
the target start, under all four fixed horizons. It records connection/packet
rate, destination and destination-port diversity, SYN/RST/response behavior,
short/incomplete ratio, target concentration, and IAT/burstiness.

The fixed vertical mechanism requires a probe-like current session, at least
eight past same-source sessions, at least eight destination ports, at most
three destinations, and past probe ratio at least 0.5. The horizontal mechanism
uses at least eight destinations and at most three destination ports under the
same other constraints.

No one of 10,908 official Port_Scanning sessions satisfies either mechanism.
Across all contexts, the observed maxima are six destinations and four
destination ports; the dominant 9,987-session source/destination/service
triplet repeatedly uses one destination and destination port 80. High rate,
SYN, and RST repetition alone does not establish either a vertical port sweep
or horizontal host/service sweep.

| Metric | Value |
| --- | ---: |
| Total reconstructed sessions | 10,908 |
| Contextually / fully observationally supported | 0 |
| Supported train / validation / test | 0 / 0 / 0 |
| Vertical scan supported | false |
| Horizontal scan supported | false |
| Formal reinterpretation | `UNRESOLVED_PORT_SCANNING_NOT_OBSERVED` |

Renaming the class to `Scanning` or `Host_Service_Scanning` would therefore not
be a taxonomy refinement grounded in the observed traffic. The original label
would still require capture identity, so `SCANNING_CAPTURE_LABEL_REQUIRED=true`
and `SCANNING_SALVAGE_STATUS=FAIL`.

## 6. Control comparison

The identical builders were applied to all ten Normal captures, not a handpicked
sample: 680,504 sessions produced zero relation support and zero vertical or
horizontal scan support. This includes Normal_Modbus, the hardest negative with
multi-address observations separated in time; bounded windows correctly avoid
turning those historical changes into a simultaneous relation anomaly.

As an additional cross-attack control, the Port_Scanning capture contains 474
sessions with a bounded ARP relation anomaly, while MITM has 204/227. This is
important rather than inconvenient: the builder exposes a real observation and
does not pretend that an ARP anomaly is an exclusive class identifier. Those
474 sessions still have no scanning evidence and cannot be retained under the
Port_Scanning GT. Conversely, the MITM verdict is based on its persistent
relation state, not the capture name.

Both builders report `future_context_used=false` and model-safe identity
leakage zero. Unit tests cover exact-time exclusion, future exclusion,
partition locality, label-free contracts, vertical/horizontal semantics, and
absence of backend identity from the model-safe projection.

## 7. Final salvage verdict

- MITM: `PASS_CASE_STUDY_ONLY`; real causal Relation evidence exists, but
  support/diversity is insufficient for a stable formal main class.
- Port_Scanning: `FAIL`; neither the original vertical semantics nor a proposed
  horizontal/scanning reinterpretation is supported.
- Proposed formal main classes remain Normal, DDoS_HTTP, DDoS_TCP, Password,
  SQL_injection, and Vulnerability_scanner.
- `SALVAGE_INTEGRATION_REQUIRED=false`; no formal population, Teacher-v2, split,
  or corpus rebuild is warranted.

## 8. Consequence for formal SFT

The accepted six-class corpus was read but not modified. Its class definition,
Teacher-v2 supervision, session weights, SHA256, and readiness Gates remain
valid. No plan document changed because the formal Task Definition did not
change.

```text
CURRENT_6_CLASS_CORPUS_STILL_VALID=true
FORMAL_SFT_STARTED=false
READY_FOR_FORMAL_SFT=true
NEXT_ACTION=START_FORMAL_NEAR_MULTI_TASK_SFT
```

Large per-session support tables are Git-external under
`/root/autodl-tmp/experiments/contextual_evidence_salvage_v2/`; the tracked JSON
records their paths, row counts, source hashes, and artifact SHA256 values.
