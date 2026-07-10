"""Does our ordering of outlets agree with the incumbent raters'?

The M3 gate (METHODOLOGY.md D7), as code: Spearman rank correlation between
tiltmeter's scores and each incumbent rater's published ratings, with the
pre-declared pass bar ρ ≥ 0.7 against **both** raters — a gate that can pass
with a rater missing is not the declared gate, so a missing or empty rater
fails it outright. This is validation only: rater values never touch scoring.

Reference values that haven't been verified at the source are refused by
default. Peeking past that (--allow-unverified) is allowed for watching the
instrument converge, but a peek can never pass the gate, is labeled
`peek: true` inside the artifact, and is written to a `validation-peek-*`
file that the public API does not serve.

A permutation p-value (fixed seed) accompanies each ρ: the probability of a
correlation at least this strong if outlet order were random. With n = 20 it
is honest about how much — and how little — the sample can say.
"""

from dataclasses import dataclass

import numpy as np
import yaml

from tiltmeter.stats import spearman

GATE_RHO = 0.7
REQUIRED_RATERS = ("allsides", "ad_fontes")
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


@dataclass(frozen=True)
class Reference:
    by_rater: dict[str, dict[str, float]]
    unverified_used: list[str]  # entries folded into the math while peeking
    unverified_skipped: list[str]  # entries excluded in strict mode


def load_reference(path: str, *, allow_unverified: bool = False) -> Reference:
    """Reference ratings; unverified entries are excluded unless peeking, and
    are always reported either way."""
    with open(path, encoding="utf-8") as f:
        ratings = yaml.safe_load(f)["ratings"]
    by_rater: dict[str, dict[str, float]] = {r: {} for r in REQUIRED_RATERS}
    used: list[str] = []
    skipped: list[str] = []
    for outlet, raters in ratings.items():
        for rater in REQUIRED_RATERS:
            entry = raters.get(rater) or {}
            value = entry.get("value")
            if value is None:
                continue
            if not entry.get("verified", False):
                if not allow_unverified:
                    skipped.append(f"{outlet}/{rater}")
                    continue
                used.append(f"{outlet}/{rater}")
            by_rater[rater][outlet] = (
                float(ALLSIDES_SCALE[value]) if rater == "allsides" else float(value)
            )
    return Reference(by_rater=by_rater, unverified_used=sorted(used),
                     unverified_skipped=sorted(skipped))


def _permutation_p(scores: np.ndarray, reference: np.ndarray, observed: float) -> float:
    rng = np.random.default_rng(PERMUTATION_SEED)
    hits = sum(
        abs(spearman(scores, rng.permutation(reference))) >= abs(observed)
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
    rho = spearman(a, b)
    return RaterResult(
        rater=rater,
        n=len(common),
        rho=round(rho, 4),
        p_value=round(_permutation_p(a, b, rho), 5),
        passes_gate=rho >= GATE_RHO,
        outlets_used=tuple(common),
    )


def report(ratings: dict, reference: Reference) -> dict:
    """The full validation artifact for a ratings release.

    The gate requires every declared rater to be present with a real sample
    AND to pass — and can never pass while peeking at unverified data.
    """
    results: dict[str, RaterResult] = {}
    missing: list[str] = []
    for rater in REQUIRED_RATERS:
        values = reference.by_rater.get(rater) or {}
        if not values:
            missing.append(rater)
            continue
        results[rater] = against_rater(ratings, values, rater)
    peeking = bool(reference.unverified_used)
    gate_passed = (
        not missing
        and not peeking
        and all(r.passes_gate for r in results.values())
        and ratings["orientation"]["reliable"]
    )
    return {
        "snapshot_id": ratings["snapshot_id"],
        "corpus_hash": ratings["corpus_hash"],
        "pipeline_version": ratings["pipeline_version"],
        "gate_rho": GATE_RHO,
        "orientation_reliable": ratings["orientation"]["reliable"],
        "peek": peeking,
        "unverified_used": reference.unverified_used,
        "skipped_unverified": reference.unverified_skipped,
        "raters_missing": missing,
        "raters": {
            name: {
                "n": r.n,
                "rho": r.rho,
                "permutation_p": r.p_value,
                "passes_gate": r.passes_gate,
            }
            for name, r in results.items()
        },
        "gate_passed": gate_passed,
    }
