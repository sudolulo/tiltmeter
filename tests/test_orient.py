"""Does orientation flip the axis when — and only when — it should?

Pure-function tests: no model, no network. The embedding-dependent parts
(party means from real speeches) are exercised by the live `tiltmeter run`;
what must never regress silently is the flip decision and its honesty about
weak agreement.
"""

import numpy as np

from tiltmeter import orient


def test_correctly_oriented_axis_is_kept():
    axis = [-0.9, -0.5, 0.0, 0.4, 0.8]  # already: left negative
    proxy = [-0.10, -0.06, 0.01, 0.05, 0.09]  # closer to R language as we go right
    result = orient.orient_sign(axis, proxy)
    assert result.sign == 1
    assert result.correlation > 0.9
    assert result.reliable


def test_backwards_axis_is_flipped():
    axis = [0.9, 0.5, 0.0, -0.4, -0.8]  # backwards: left ended up positive
    proxy = [-0.10, -0.06, 0.01, 0.05, 0.09]
    result = orient.orient_sign(axis, proxy)
    assert result.sign == -1
    assert result.correlation < -0.9


def test_weak_agreement_is_flagged_unreliable():
    rng = np.random.default_rng(3)
    axis = list(rng.normal(size=12))
    proxy = list(rng.normal(size=12))  # unrelated
    result = orient.orient_sign(axis, proxy)
    assert not result.reliable


def test_spearman_matches_known_value():
    # perfect monotone but nonlinear relation: rank correlation must be 1
    a = np.array([1.0, 2.0, 3.0, 4.0])
    assert orient._spearman(a, a**3) == 1.0
    assert orient._spearman(a, -(a**3)) == -1.0
