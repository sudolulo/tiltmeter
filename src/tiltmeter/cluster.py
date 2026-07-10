"""Which articles, across outlets, are about the same news event?

Articles are grouped into story clusters by agglomerative clustering on
cosine distance between their embeddings: start with every article alone,
repeatedly merge the closest groups, stop when the closest remaining pair is
farther apart than a threshold. Deterministic: same vectors in, same clusters
out — there is no randomness to seed.

The distance threshold is a tunable (METHODOLOGY.md D3), covered by the
sensitivity sweep (D7). Only clusters spanning ≥2 outlets count as stories
for scoring: a story only one outlet ran tells us nothing about *choice*
relative to peers until someone else could have run it too.
"""

from dataclasses import dataclass

import numpy as np

# Tunable (D3/D7): cosine distance below which two articles are "the same story".
DISTANCE_THRESHOLD = 0.45
MIN_OUTLETS_PER_STORY = 2


@dataclass(frozen=True)
class Story:
    """One cross-outlet news event: which articles, from which outlets."""

    story_id: int
    article_indices: tuple[int, ...]
    outlets: frozenset[str]


def cluster_articles(
    vectors: np.ndarray,
    outlets: list[str],
    threshold: float = DISTANCE_THRESHOLD,
) -> list[Story]:
    """Group article vectors into stories; keep only cross-outlet ones."""
    from sklearn.cluster import AgglomerativeClustering

    if len(vectors) < 2:
        return []
    labels = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=threshold,
        metric="cosine",
        linkage="average",
    ).fit_predict(vectors)

    by_label: dict[int, list[int]] = {}
    for idx, label in enumerate(labels):
        by_label.setdefault(int(label), []).append(idx)

    stories = []
    for indices in by_label.values():
        outlet_set = frozenset(outlets[i] for i in indices)
        if len(outlet_set) >= MIN_OUTLETS_PER_STORY:
            stories.append((tuple(sorted(indices)), outlet_set))
    # deterministic story ids: order by first article index
    stories.sort(key=lambda s: s[0])
    return [
        Story(story_id=sid, article_indices=idxs, outlets=outs)
        for sid, (idxs, outs) in enumerate(stories)
    ]


def coverage_matrix(stories: list[Story], outlet_order: list[str]) -> np.ndarray:
    """The grid scoring reads: outlets × stories, 1 = covered, 0 = skipped."""
    matrix = np.zeros((len(outlet_order), len(stories)), dtype=np.float64)
    outlet_row = {name: i for i, name in enumerate(outlet_order)}
    for story in stories:
        for outlet in story.outlets:
            if outlet in outlet_row:
                matrix[outlet_row[outlet], story.story_id] = 1.0
    return matrix
