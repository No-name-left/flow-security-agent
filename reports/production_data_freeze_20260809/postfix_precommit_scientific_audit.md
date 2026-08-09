# Post-fix Pre-Commit Scientific Audit

- Verdict: **PASS_WITH_LIMITATIONS**
- Backend identity duplicates removed: 0
- Backend identity label-conflict rows quarantined: 0
- Exact model-view collision groups retained/audited: 6755
- Edge constructed / retained / excluded: 7619032 / 7377181 / 241851
- Identity cross-split overlap: 0
- Exact / near view cross-split collisions: 2283 / 7653
- Class-role support gate: PASS
- Determinism: PASS

## Failed gates

- None

## Limitations

- Exact and near Initial Model View collisions remain in Primary by design and are quantified by evaluation-clean sensitivity variants.
- Primary class imbalance and legitimate repeated attack behavior are retained; future training-size control belongs to a separate reproducible sampler.
- Edge attack classes are mostly single-capture, so no cross-attack-run generalization is claimed.
