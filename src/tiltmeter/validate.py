"""Does our ordering of outlets agree with the incumbent raters'?

The M3 gate (METHODOLOGY.md D7), as code: Spearman rank correlation between
tiltmeter's scores and each incumbent rater's published ratings, with the
pre-declared pass bar ρ ≥ 0.7 against both. This is validation only — rater
values never touch scoring — and it refuses to report against reference
entries that haven't been verified at the source, because a gate checked
against sloppy data isn't a gate.

A permutation p-value (fixed seed) accompanies each ρ: the probability of a
correlation at least this strong if outlet order were random. With n = 20 it
is honest about how much — and how little — the sample can say.
"""

from dataclasses import dataclass

import numpy as np
import yaml

from tiltmeter.orient import _spearman

GATE_RHO = 0.7
PERMUTATIONS = 10_000
PERMUTATION_SEED = 20260724  # gate day
ALLSIDES_SCALE = {"Left": -2, "Lean Left": -1, "Center": 0, "Lean Right": 1, "Right": 2}


@dataclass(frozen=True)
class RaterResult:
    rater: str
    n: int
    rho: float
    p_value: float
    passes_gate: bool
    outlets_used: tuple[str, ...]


def load_reference(path: str, *, allow_unverified: bool = False) -> dict:
    """Reference ratings, refusing unverified entries unless explicitly peeking."""
    with open(path) as f:
        ratings = yaml.safe_load(f)["ratings"]
    out: dict[str, dict[str, float]] = {"allsides": {}, "ad_fontes": {}}
    unverified: list[str] = []
    for outlet, raters in ratings.items():
        for rater in ("allsides", "ad_fontes"):
            entry = raters.get(rater) or {}
            value = entry.get("value")
            if value is None:
                continue
            if not entry.get("verified", False):
                unverified.append(f"{outlet}/{rater}")
                if not allow_unverified:
                    continue
            out[rater][outlet] = (
                float(ALLSIDES_SCALE[value]) if rater == "allsides" else float(value)
            )
    if unverified and not allow_unverified:
        out["skipped_unverified"] = sorted(unverified)
    return out


def _permutation_p(scores: np.ndarray, reference: np.ndarray, observed: float) -> float:
    rng = np.random.default_rng(PERMUTATION_SEED)
    hits = sum(
        abs(_spearman(scores, rng.permutation(reference))) >= abs(observed)
        for _ in range(PERMUTATIONS)
    )
    return (hits + 1) / (PERMUTATIONS + 1)


def against_rater(ratings: dict, reference_values: dict[str, float], rater: str) -> RaterResult:
    """One rater's gate check over the outlets both sides cover."""
    ours = {o["outlet"]: o["score"] for o in ratings["outlets"]}
    common = sorted(set(ours) & set(reference_values))
    if len(common) < 5:
        raise ValueError(
            f"only {len(common)} outlets shared with {rater}; gate needs a real sample"
        )
    a = np.array([ours[o] for o in common])
    b = np.array([reference_values[o] for o in common])
    rho = _spearman(a, b)
    return RaterResult(
        rater=rater,
        n=len(common),
        rho=round(rho, 4),
        p_value=round(_permutation_p(a, b, rho), 5),
        passes_gate=rho >= GATE_RHO,
        outlets_used=tuple(common),
    )


def report(ratings: dict, reference: dict) -> dict:
    """The full validation artifact for a ratings release."""
    results = {}
    for rater in ("allsides", "ad_fontes"):
        if reference.get(rater):
            results[rater] = against_rater(ratings, reference[rater], rater)
    return {
        "snapshot_id": ratings["snapshot_id"],
        "corpus_hash": ratings["corpus_hash"],
        "pipeline_version": ratings["pipeline_version"],
        "gate_rho": GATE_RHO,
        "orientation_reliable": ratings["orientation"]["reliable"],
        "skipped_unverified": reference.get("skipped_unverified", []),
        "raters": {
            name: {
                "n": r.n,
                "rho": r.rho,
                "permutation_p": r.p_value,
                "passes_gate": r.passes_gate,
            }
            for name, r in results.items()
        },
        "gate_passed": bool(results)
        and all(r.passes_gate for r in results.values())
        and ratings["orientation"]["reliable"],
    }
