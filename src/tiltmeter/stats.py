"""How do we compare two orderings without our own math betraying us?

The one statistic the whole project leans on: Spearman rank correlation,
with proper tie handling (tied values share the average of the ranks they
occupy — the textbook definition). The naive argsort-of-argsort version
gives answers that depend on input *ordering* whenever values tie, and the
reference ratings are a 5-point scale over 20 outlets, so ties are
guaranteed. A gate that changes verdict when outlets are alphabetized
differently is not a gate.

Kept dependency-free (numpy only) and tiny so it can be read and checked
against any statistics textbook in a minute.
"""

import numpy as np


def rankdata_average(values: np.ndarray) -> np.ndarray:
    """Ranks 1..n with ties sharing the average of their occupied ranks."""
    values = np.asarray(values, dtype=np.float64)
    order = np.argsort(values, kind="stable")
    ranks = np.empty(len(values), dtype=np.float64)
    i = 0
    while i < len(values):
        j = i
        while j + 1 < len(values) and values[order[j + 1]] == values[order[i]]:
            j += 1
        ranks[order[i : j + 1]] = (i + j) / 2 + 1  # average of ranks i+1 .. j+1
        i = j + 1
    return ranks


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    """Spearman's ρ with tie-averaged ranks; order-invariant on tied data."""
    ra = rankdata_average(np.asarray(a))
    rb = rankdata_average(np.asarray(b))
    ra -= ra.mean()
    rb -= rb.mean()
    denom = np.sqrt((ra**2).sum() * (rb**2).sum())
    return float((ra * rb).sum() / denom) if denom > 0 else 0.0
