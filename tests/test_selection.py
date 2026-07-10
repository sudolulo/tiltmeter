"""Does the selection signal recover structure we planted, deterministically?

Synthetic fixtures, no network, no embeddings: we build coverage matrices
where the right answer is known by construction, and assert the axis finds
it. This is the reproducibility promise made executable — if any of these
fail, published numbers can't be trusted, whatever validation says.
"""

import numpy as np

from tiltmeter.cluster import Story, coverage_matrix
from tiltmeter.signals import selection


def planted_two_bloc_matrix(
    n_bloc: int = 4, n_shared: int = 30, n_partisan: int = 25, flip_noise: float = 0.1
) -> tuple[np.ndarray, list[str]]:
    """Two blocs of outlets: everyone covers shared stories; each bloc has its
    own stories the other mostly skips. flip_noise = fraction of cells flipped."""
    outlets = [f"blue-{i}" for i in range(n_bloc)] + [f"red-{i}" for i in range(n_bloc)]
    n_outlets = 2 * n_bloc
    rng = np.random.default_rng(7)
    shared = np.ones((n_outlets, n_shared))
    blue_only = np.vstack(
        [np.ones((n_bloc, n_partisan)), np.zeros((n_bloc, n_partisan))]
    )
    red_only = np.vstack(
        [np.zeros((n_bloc, n_partisan)), np.ones((n_bloc, n_partisan))]
    )
    matrix = np.hstack([shared, blue_only, red_only])
    noise = rng.random(matrix.shape) < flip_noise
    matrix = np.abs(matrix - noise)
    return matrix, outlets


def test_axis_separates_planted_blocs():
    matrix, outlets = planted_two_bloc_matrix()
    result = selection.compute(matrix, outlets)
    blue = [p for o, p in zip(result.outlets, result.positions) if o.startswith("blue")]
    red = [p for o, p in zip(result.outlets, result.positions) if o.startswith("red")]
    # every blue outlet on one side of every red outlet (sign arbitrary pre-orientation)
    assert max(blue) < min(red) or max(red) < min(blue), (
        f"axis failed to separate planted blocs: blue={blue}, red={red}"
    )


def test_axis_is_deterministic():
    matrix, outlets = planted_two_bloc_matrix()
    a = selection.compute(matrix, outlets)
    b = selection.compute(matrix, outlets)
    assert a == b, "same matrix must produce identical results, bit for bit"


def test_cis_bracket_positions_and_widen_with_noise():
    quiet, outlets = planted_two_bloc_matrix(flip_noise=0.02)
    noisy, _ = planted_two_bloc_matrix(flip_noise=0.30)
    r_quiet = selection.compute(quiet, outlets)
    r_noisy = selection.compute(noisy, outlets)
    for pos, low, high in zip(r_quiet.positions, r_quiet.ci_low, r_quiet.ci_high):
        assert low <= pos <= high
    width = lambda r: float(np.mean(np.array(r.ci_high) - np.array(r.ci_low)))  # noqa: E731
    assert width(r_noisy) > width(r_quiet), "more noise must mean wider intervals"


def test_refuses_underdetermined_matrix():
    matrix = np.ones((10, 5))  # more outlets than stories
    try:
        selection.compute(matrix, [f"o{i}" for i in range(10)])
        raise AssertionError("should refuse: fewer stories than outlets")
    except ValueError as e:
        assert "unstable" in str(e)


def test_coverage_matrix_from_stories():
    stories = [
        Story(story_id=0, article_indices=(0, 1), outlets=frozenset({"a", "b"})),
        Story(story_id=1, article_indices=(2, 3), outlets=frozenset({"b", "c"})),
    ]
    matrix = coverage_matrix(stories, ["a", "b", "c"])
    assert matrix.tolist() == [[1, 0], [1, 1], [0, 1]]
