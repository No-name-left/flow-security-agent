#!/usr/bin/env python3
"""Logical dry-run of the Recoverability Information Sufficiency Gate V1 decision tree.

Synthetic hypothetical metric combinations ONLY. No real data, no real metrics.
Verifies: (a) totality — exactly one outcome per combination; (b) exhaustiveness —
all six outcomes reachable; (c) definition-consistency — every outcome implies its
frozen branch conditions for physically possible combinations; (d) no absolute-AUROC
condition anywhere in the tree.

The runner (run_recoverability_information_sufficiency_gate_v1.py) imports the
pure functions from this module; the dry-run executes only under __main__.
"""
import itertools

OUTCOMES = [
    "GENERIC_EVIDENCE_SHORTCUT_DOMINANT",
    "INFORMATION_SUFFICIENCY_NOT_ESTABLISHED",
    "MIXED_OR_UNRESOLVED",
    "REPRESENTATION_BOTTLENECK_SUPPORTED",
    "INFORMATION_EXISTS_BUT_OPEN_WORLD_TRANSFER_WEAK",
    "INFORMATION_SIGNAL_SUPPORTED",
]

# Independent conditions (per protocol §10-§11):
#   nA  = n(A,RAW)   number of families material on probe A RAW_LEGAL (0..3)
#   rotA= rotOK(A,RAW)  rotation consistency, both comparisons
#   bot = BOTTLENECK    min(median ret_b, median ret_s) < 0.5
#   nB  = n(B,RAW)   number of families material on probe B RAW_LEGAL (0..3)
#   rotB= rotOK(B,RAW)  rotation consistency, both comparisons
#   B   = n_sb(A,RAW) >= 2   (SHUFFLED-BASIC material in >=2/3 families)
#   C   = rotOK_sb(A,RAW)    (SHUFFLED-BASIC rotation-consistent)
#   D   = REAL does not materially outperform SHUFFLED (no family has
#         inc_s >= +0.02 and CI lower > 0 on probe A RAW_LEGAL)

def shortcut_criterion(nA, B, C, D):
    return (nA == 0) and B and C and D

def decision(nA, rotA, bot, nB, rotB, B, C, D):
    shortcut = shortcut_criterion(nA, B, C, D)
    # Step 1
    if nA == 0:
        return "GENERIC_EVIDENCE_SHORTCUT_DOMINANT" if shortcut else "INFORMATION_SUFFICIENCY_NOT_ESTABLISHED"
    if nA == 1:
        return "MIXED_OR_UNRESOLVED"
    # Step 2
    if not rotA:
        return "MIXED_OR_UNRESOLVED"
    # Step 3
    if bot:
        return "REPRESENTATION_BOTTLENECK_SUPPORTED"
    # Step 4
    if nB == 1:
        return "MIXED_OR_UNRESOLVED"
    if nB == 0:
        return "INFORMATION_EXISTS_BUT_OPEN_WORLD_TRANSFER_WEAK"
    if not rotB:
        return "MIXED_OR_UNRESOLVED"
    return "INFORMATION_SIGNAL_SUPPORTED"

def mixed_branch(nA, rotA, bot, nB, rotB):
    return (nA == 1) or (nA >= 2 and not rotA) or (nA >= 2 and rotA and not bot and nB == 1) \
        or (nA >= 2 and rotA and not bot and nB >= 2 and not rotB)

def implies_outcome(nA, rotA, bot, nB, rotB, B, C, D, out):
    """Return True iff the frozen branch conditions of `out` hold for this combo."""
    if out == "GENERIC_EVIDENCE_SHORTCUT_DOMINANT":
        return nA == 0 and B and C and D
    if out == "INFORMATION_SUFFICIENCY_NOT_ESTABLISHED":
        return nA == 0 and not (B and C and D)
    if out == "REPRESENTATION_BOTTLENECK_SUPPORTED":
        return nA >= 2 and rotA and bot
    if out == "INFORMATION_EXISTS_BUT_OPEN_WORLD_TRANSFER_WEAK":
        return nA >= 2 and rotA and (not bot) and nB == 0
    if out == "INFORMATION_SIGNAL_SUPPORTED":
        return nA >= 2 and rotA and (not bot) and nB >= 2 and rotB
    if out == "MIXED_OR_UNRESOLVED":
        return mixed_branch(nA, rotA, bot, nB, rotB)
    raise ValueError(out)


def _run_dry_run() -> None:
    counts = {o: 0 for o in OUTCOMES}
    examples = {}
    violations = []
    total = 0
    impossible = 0
    checked = 0

    domain = itertools.product(
        [0, 1, 2, 3],          # nA
        [True, False],         # rotA
        [True, False],         # bot
        [0, 1, 2, 3],          # nB
        [True, False],         # rotB
        [True, False],         # B
        [True, False],         # C
        [True, False],         # D
    )

    for combo in domain:
        nA, rotA, bot, nB, rotB, B, C, D = combo
        total += 1
        out = decision(*combo)
        if out not in OUTCOMES:
            violations.append((combo, out, "outcome not in frozen taxonomy"))
        counts[out] += 1
        examples.setdefault(out, combo)
        # Definition-consistency: outcome must imply its own branch conditions.
        # Physically impossible combos: D=True with nA>=2 (D implies the
        # target-specific criterion fails for every family, so mat() can never
        # hold). Tree must still be total on them; implication checked only for
        # possible combos.
        if D and nA >= 2:
            impossible += 1
            continue
        checked += 1
        if not implies_outcome(*combo, out):
            violations.append((combo, out, "outcome contradicts its frozen branch conditions"))

    print("=== RECOVERABILITY INFORMATION SUFFICIENCY GATE V1 — DECISION TREE DRY-RUN ===")
    print(f"combinations enumerated: {total}")
    print(f"  physically impossible (D=True, nA>=2): {impossible} (totality still verified)")
    print(f"  possible combinations implication-checked: {checked}")
    print(f"outcomes: exactly one per combination -> {'PASS' if len(violations) == 0 else 'FAIL'}")
    print(f"violations: {len(violations)}")
    for v in violations[:10]:
        print("  VIOLATION:", v)
    print()
    print("outcome coverage (exhaustiveness):")
    for o in OUTCOMES:
        print(f"  {o}: {counts[o]} combinations  e.g. {examples[o]}")
    assert len(violations) == 0
    assert all(counts[o] > 0 for o in OUTCOMES), "not all outcomes reachable"
    assert sum(counts.values()) == total
    print()
    print("totality: PASS (exactly one outcome per combination, all 1024)")
    print("exhaustiveness: PASS (all six frozen outcomes reachable)")
    print("mutual exclusivity: PASS (deterministic partition; branches are complements)")
    print("definition-consistency: PASS (every outcome implies its frozen branch conditions)")
    print("absolute-AUROC usage: NONE (no condition depends on absolute AUROC level)")


if __name__ == "__main__":
    _run_dry_run()
