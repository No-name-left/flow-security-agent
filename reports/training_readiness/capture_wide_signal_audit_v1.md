# Capture-Wide Attack Signal and Label-Propagation Audit v1

Status: `PASS_WITH_LIMITATIONS`

## Scope and safeguards

This is a deterministic backend-only forensic audit of the four verified official Edge-IIoTset attack captures. Mechanism/protocol features were extracted without a class or capture filename in the detector input; the verified fine label was consulted only for the final backend categorization. Context is strict past-only over the same anonymized source-to-target service (excluding the client's ephemeral port). No future packets, whole-capture identity, filename, run label, model call, synthetic evidence, corpus edit, split/K-U edit, or U_final content was used.

`FORMAL_CORPUS_MODIFIED=false`

`FORMAL_SFT_STARTED=false`

`DEEPSEEK_NEW_API_CALLS=0`
`QWEN_NEW_RUNS=0`

## Capture/run structure

Each target fine class has exactly one verified official source PCAP and one companion CSV. Consequently this audit can measure within-capture signal and label propagation, but **cannot validate cross-run stability**. All four captures have 100% companion-label purity and current sessions use `VERIFIED_CAPTURE_FALLBACK`; official CSV rows do not provide a stable formal frame mapping.

The backend-only external aggregate records PCAP paths, hashes, packet/duration/protocol distributions and per-capture timeline locations. Paths and capture identities are not model Evidence.

| class | capture ID (backend only) | PCAP path (backend only) | size | packets | duration s | sessions/IP sessions | non-IP packets | protocol distribution |
|---|---|---|---:|---:|---:|---:|---:|---|
| Backdoor | `Attack_Backdoor` | `/root/autodl-tmp/datasets/edge_iiotset/raw/Edge-IIoTset dataset/Attack traffic/Backdoor_attack.pcap` | 6,694,092 | 24,914 | 11317.968 | 1,424/1,424 | 324 | `{"ICMP":1,"IP_2":137,"IP_OTHER":365,"TCP":24035,"UDP":52,"arp":324}` |
| Password | `Attack_Password` | `/root/autodl-tmp/datasets/edge_iiotset/raw/Edge-IIoTset dataset/Attack traffic/Password attacks.pcap` | 194,557,494 | 1,053,893 | 68505.644 | 96,081/96,081 | 408 | `{"ICMP":31,"IP_2":354,"IP_OTHER":968,"TCP":1051624,"UDP":508,"arp":408}` |
| Uploading | `Attack_Uploading` | `/root/autodl-tmp/datasets/edge_iiotset/raw/Edge-IIoTset dataset/Attack traffic/Uploading attack.pcap` | 5,488,666 | 37,644 | 505.318 | 7,635/7,635 | 8 | `{"ICMP":8,"IP_2":12,"IP_OTHER":33,"TCP":37573,"UDP":10,"arp":8}` |
| Ransomware | `Attack_Ransomware` | `/root/autodl-tmp/datasets/edge_iiotset/raw/Edge-IIoTset dataset/Attack traffic/Ransomware attack.pcap` | 2,842,688 | 11,030 | 116550.444 | 1,364/1,364 | 505 | `{"ICMP":5,"IP_2":195,"IP_OTHER":529,"TCP":9691,"UDP":105,"arp":505}` |

The corresponding full session timelines and non-session ARP/control events are Git-external and digest-bound in the manifest. All four captures are single-run assets; there is no second independent run for cross-run stability validation.

## Capture-Wide Label Semantics Table

| class | sessions | direct | contextual | generic/background | past 10s | past 60s | payload | application | temporal | relation | risk | observation unit | retain |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| Backdoor | 1,424 | 0 (0.00%) | 39 (2.74%) | 1,385 (97.26%) | 0 (0.00%) | 0 (0.00%) | 0 (0.00%) | 0 (0.00%) | 39 (2.74%) | 39 (2.74%) | HIGH | SESSION_PLUS_TEMPORAL | true |
| Password | 96,081 | 23,650 (24.61%) | 47,298 (49.23%) | 25,133 (26.16%) | 47,298 (49.23%) | 47,298 (49.23%) | 23,650 (24.61%) | 0 (0.00%) | 47,298 (49.23%) | 47,298 (49.23%) | MEDIUM | SESSION_PLUS_PAYLOAD | true |
| Uploading | 7,635 | 0 (0.00%) | 0 (0.00%) | 7,635 (100.00%) | 0 (0.00%) | 0 (0.00%) | 20 (0.26%) | 0 (0.00%) | 0 (0.00%) | 0 (0.00%) | HIGH | NOT_RECOVERABLE_FROM_NETWORK | false |
| Ransomware | 1,364 | 0 (0.00%) | 0 (0.00%) | 1,364 (100.00%) | 0 (0.00%) | 0 (0.00%) | 0 (0.00%) | 0 (0.00%) | 0 (0.00%) | 0 (0.00%) | HIGH | NOT_RECOVERABLE_FROM_NETWORK | false |

Rates use all reconstructed Production sessions, including chronological quarantine rows, because capture-label propagation applies before split role. `generic/background` is the direct estimate of capture-to-session over-propagation; capture membership alone never makes a session attack-informative.

## Class findings

### Backdoor

The full capture has 1,424 sessions. The dominant candidate service contributes 827 incomplete SYN→RST sessions, which are not C2 evidence. Separately, one stable relation contains 42 identical-shape, three-packet, small established binary exchanges at a mean interval of 60.284s with CV 0.0015. No decoded command string is required for this timing/size/direction signal. After three prior exchanges, 39 sessions become contextually informative under strict past-only history; however, previous 10s and 60s both recover 0 because every recurrence is just over 60s. Thus the earlier sampled 0% missed the small beacon-like subset, while the current 60s Temporal contract also misses it.

Conclusion: `PAST_CONTEXT_RECOVERABLE`; minimum observation `SESSION_PLUS_TEMPORAL`.

### Password

The observable attack behavior is HTTP form authentication, not an inferred class-name shortcut. Across 96,081 sessions, 23,650 credential-bearing POST sessions are direct; their observed response distribution is `{"302":23650}` (redirects are observable, success/failure semantics are not asserted). These attempts span 68504.451s at 0.345 attempts/s, and the maximum strict 10-second repeated-auth burst is 22676. A further 47,298 GET/HTTP sessions are supported by an already observed past authentication attempt on the same anonymized source→target service. The remaining 25,133 sessions (26.16%) are generic/background. Thus the former 26.67% sample rate was selecting real auth sessions, while capture fallback propagates Password to a materially larger run.

Conclusion: `MIXED`; minimum observation `SESSION_PLUS_PAYLOAD`.

### Uploading

Across 7,635 sessions, 1,904 are HTTP GET sessions and 1,904 receive HTTP 200; none is POST/PUT/multipart/FTP upload. The 20 script-shaped binary sessions contain 41,540 initiator versus 1,836,356 responder payload bytes, i.e. the observed direction is not proof of client upload. Therefore 0 sessions contain explicit upload semantics and 0 are recoverable after a prior observed upload. `ENCRYPTED_APPLICATION_SEMANTICS=false`. The generic/background fraction is 100.00%; the previous 6.67% reflected suspicious content in a small subset, not a defensible per-session Uploading label.

Conclusion: `NETWORK_OBSERVABILITY_LIMITED`; minimum observation `NOT_RECOVERABLE_FROM_NETWORK`.

### Ransomware

The full capture has 1,364 sessions, including 570 incomplete handshakes and 582 bidirectional exchanges. It exposes no network-observed ransomware-specific key/encryption workflow, command/control chain, malware transfer, or other signal that distinguishes `Ransomware` from generic suspicious/malware traffic. Host-side encryption is outside the PCAP and is never inferred. The result is `NETWORK_FINE_LABEL_NOT_OBSERVABLE_FROM_AVAILABLE_PCAP`.

Conclusion: `NETWORK_OBSERVABILITY_LIMITED`; minimum observation `NOT_RECOVERABLE_FROM_NETWORK`.

## Label propagation and context

The pipeline behavior is confirmed as `attack-labeled capture → every reconstructed within-capture session → VERIFIED_CAPTURE_FALLBACK fine label` for all 106,504 audited sessions. The generic/background fraction is therefore a concrete capture-to-session label-propagation estimate, not a classifier metric. Overall risk is `HIGH`.

Strict past-only context helps only when an earlier real mechanism anchor exists on the same source→target service. It recovers 47,298 sessions at 10 seconds and 47,298 at 60 seconds, almost entirely Password. Backdoor requires a history longer than 60s; Uploading/Ransomware have no direct anchor. The class-balanced salvageability rating is `MEDIUM`; future traffic, run identity and capture labels remain forbidden.

## Parser/extractor loss

The raw scan records HTTP/application shapes and decoded bounded payload semantics that are absent from Initial Evidence, so Password has `PAYLOAD_NOT_ALIGNED`/`APPLICATION_NOT_PARSED` and missing auth-aware Temporal features. Uploading has application/payload observations, but GET-delivered script content does not establish upload; this is primarily label granularity rather than silent parser loss. Backdoor/Ransomware do not reveal a hidden decisive payload/application signal; their dominant finding is network observability/label granularity, not extractor failure. Non-IP/control events are retained in the external event timelines.

## Direct answers

1. **Backdoor 0%:** the sample missed a 42-session, ~60.28s periodic small established binary relation. It is real network behavior, but current 10/60s context cannot recover it and 1,385/1,424 sessions remain non-informative.
2. **Password remainder:** beyond 23,650 direct credential POSTs, 47,298 GET/HTTP sessions have a strict prior-10s auth anchor and 25,133 sessions remain generic/background; only 302 redirects, not success/failure semantics, are observable.
3. **Uploading 6.67%:** the full scan does not support broad per-session Uploading semantics; GET/script delivery must not be reinterpreted as upload merely because of the capture label.
4. **Ransomware:** no available network evidence distinguishes Ransomware from generic suspicious/malware traffic.
5. **Over-propagation:** yes; quantified per class by `generic_background_rate`.
6. **Past-only salvage:** strong for Password at 10s, possible for Backdoor only with a longer (>60s) past window, and absent for Uploading/Ransomware.

## Limitations

- One official attack capture per class prevents independent-run stability claims.
- These are conservative deterministic signal-coverage statistics, not trained-model accuracy or formal paper results.
- Capture CSV purity proves provenance but not per-session fine semantics.
- Fine-class retention/observation-unit recommendations are audit findings; this task does not change data, K/U, corpus, training, or the canonical plan.

## Final fields

```text
CAPTURE_WIDE_AUDIT_STATUS=PASS_WITH_LIMITATIONS
BACKDOOR_FINE_CLASS_VIABILITY=CONDITIONAL_ON_STRICT_PAST_CONTEXT_GT_60S
PASSWORD_FINE_CLASS_VIABILITY=VIABLE_WITH_SESSION_PAYLOAD_AND_PAST_CONTEXT
UPLOADING_FINE_CLASS_VIABILITY=NOT_VIABLE_FROM_AVAILABLE_PCAP
RANSOMWARE_FINE_CLASS_VIABILITY=NOT_VIABLE_FROM_AVAILABLE_PCAP
CAPTURE_TO_SESSION_LABEL_PROPAGATION_RISK=HIGH
PAST_ONLY_CONTEXT_SALVAGEABILITY=MEDIUM
TASK_REDEFINITION_REQUIRED=true
FORMAL_CORPUS_MODIFIED=false
FORMAL_SFT_STARTED=false
DEEPSEEK_NEW_API_CALLS=0
QWEN_NEW_RUNS=0
```
