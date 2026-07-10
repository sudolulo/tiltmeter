"""Where does each outlet sit, judging only by what it chooses to cover?

Correspondence analysis of the outlet×story coverage grid: the same family of
math that places legislators on a left-right scale from their votes
(ideal-point estimation) places outlets on a scale from their coverage
choices. The first principal axis is the direction along which outlets'
choices differ most — whether that direction *is* political lean is exactly
what validation tests (METHODOLOGY.md D3, D7), and which end is "left" is
decided externally by congressional language (D5), never assumed here.

Uncertainty is part of the result: bootstrap resampling over stories yields a
95% confidence interval per outlet (D6). Deterministic given the matrix and
the fixed seed.
"""

from dataclasses import dataclass

import numpy as np

BOOTSTRAP_ROUNDS = 1000
BOOTSTRAP_SEED = 20260710  # fixed: reproducibility over cleverness


@dataclass(frozen=True)
class AxisResult:
    """Per-outlet positions on the first principal axis, with uncertainty."""

    outlets: tuple[str, ...]
    positions: tuple[float, ...]  # unit-scaled, sign NOT yet oriented
    ci_low: tuple[float, ...]
    ci_high: tuple[float, ...]
    inertia_share: float  # how much of total variation the axis explains


def _first_axis(matrix: np.ndarray) -> np.ndarray:
    """Row (outlet) coordinates on the first correspondence-analysis axis."""
    total = matrix.sum()
    if total == 0:
        raise ValueError("empty coverage matrix")
    correspondence = matrix / total
    row_mass = correspondence.sum(axis=1)
    col_mass = correspondence.sum(axis=0)
    # standardized residuals: what coverage deviates from independence
    expected = np.outer(row_mass, col_mass)
    with np.errstate(divide="ignore", invalid="ignore"):
        residuals = np.where(
            expected > 0, (correspondence - expected) / np.sqrt(expected), 0.0
        )
    u, s, _ = np.linalg.svd(residuals, full_matrices=False)
    with np.errstate(divide="ignore", invalid="ignore"):
        row_coords = np.where(row_mass[:, None] > 0, u / np.sqrt(row_mass[:, None]), 0.0)
    axis = row_coords[:, 0] * s[0]
    # sign convention within a run: fix an arbitrary but deterministic sign so
    # bootstrap rounds are comparable; real orientation happens in orient.py
    if axis[np.argmax(np.abs(axis))] < 0:
        axis = -axis
    return axis


def _unit_scale(axis: np.ndarray) -> np.ndarray:
    peak = np.max(np.abs(axis))
    return axis / peak if peak > 0 else axis


def compute(matrix: np.ndarray, outlet_order: list[str]) -> AxisResult:
    """First-axis positions with bootstrap 95% CIs. Sign is unoriented."""
    n_outlets, n_stories = matrix.shape
    if n_stories < n_outlets:
        raise ValueError(
            f"only {n_stories} cross-outlet stories for {n_outlets} outlets; "
            "axis would be unstable — collect more corpus"
        )
    point = _unit_scale(_first_axis(matrix))

    rng = np.random.default_rng(BOOTSTRAP_SEED)
    samples = np.zeros((BOOTSTRAP_ROUNDS, n_outlets))
    for i in range(BOOTSTRAP_ROUNDS):
        cols = rng.integers(0, n_stories, size=n_stories)
        resampled = matrix[:, cols]
        try:
            axis = _unit_scale(_first_axis(resampled))
        except ValueError:
            axis = point  # degenerate resample: fall back, contributes no spread
        # bootstrap axes have arbitrary sign; align each to the point estimate
        if np.dot(axis, point) < 0:
            axis = -axis
        samples[i] = axis
    low, high = np.percentile(samples, [2.5, 97.5], axis=0)

    # share of total inertia explained by axis 1, from the point estimate
    total = matrix / matrix.sum()
    expected = np.outer(total.sum(axis=1), total.sum(axis=0))
    with np.errstate(divide="ignore", invalid="ignore"):
        residuals = np.where(expected > 0, (total - expected) / np.sqrt(expected), 0.0)
    eigen = np.linalg.svd(residuals, compute_uv=False) ** 2
    share = float(eigen[0] / eigen.sum()) if eigen.sum() > 0 else 0.0

    return AxisResult(
        outlets=tuple(outlet_order),
        positions=tuple(float(x) for x in point),
        ci_low=tuple(float(x) for x in low),
        ci_high=tuple(float(x) for x in high),
        inertia_share=share,
    )
