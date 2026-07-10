"""How does a snapshot become ratings.json?

The assembly line, end to end: manifest → embeddings → story clusters →
coverage matrix → selection axis with confidence intervals → orientation by
congressional language → one deterministic JSON file. Everything is computed
exactly once per run — the scores, the evidence pages, and the stories
artifact all describe the same clustering because they are handed the same
objects, never a recomputation.

No timestamps, no randomness outside the fixed bootstrap seed: rerunning on
the same snapshot must produce the same bytes (METHODOLOGY.md D1, D10).
"""

import sqlite3
from dataclasses import dataclass

import numpy as np

from tiltmeter import embed, orient
from tiltmeter.cluster import Story, cluster_articles, coverage_matrix
from tiltmeter.signals import selection

RATINGS_SCHEMA_VERSION = 1
REFERENCE_FRAME = (
    "lean relative to contemporary US congressional party discourse; "
    "negative = left, positive = right"
)


@dataclass(frozen=True)
class PipelineResult:
    """One run's complete output: the ratings and the objects behind them."""

    ratings: dict
    stories: list[Story]
    matrix: np.ndarray
    articles: list[dict]


def outlet_mean_vectors(
    articles: list[dict], vectors: np.ndarray, outlet_order: list[str]
) -> dict[str, np.ndarray]:
    """Each outlet's average article embedding — the orientation proxy input,
    shared by scoring and the sensitivity sweep so they can never diverge."""
    return {
        name: vectors[[i for i, a in enumerate(articles) if a["outlet"] == name]].mean(axis=0)
        for name in outlet_order
    }


def compute(conn: sqlite3.Connection, manifest: dict, pipeline_version: str) -> PipelineResult:
    """Run the full pipeline on a loaded manifest, once."""
    articles = manifest["articles"]
    outlet_order = manifest["outlets"]

    vectors = embed.embed_hashes(conn, [a["content_hash"] for a in articles])
    stories = cluster_articles(vectors, [a["outlet"] for a in articles])
    matrix = coverage_matrix(stories, outlet_order)
    axis = selection.compute(matrix, outlet_order)

    party = orient.party_means(conn)
    proxy = orient.outlet_proxy(outlet_mean_vectors(articles, vectors, outlet_order), party)
    orientation = orient.orient_sign(
        list(axis.positions), [proxy[name] for name in axis.outlets]
    )
    s = orientation.sign

    covered_counts = matrix.sum(axis=1)
    outlets_out = [
        {
            "outlet": name,
            "score": round(s * pos, 6),
            "ci_low": round(min(s * lo, s * hi), 6),
            "ci_high": round(max(s * lo, s * hi), 6),
            "stories_covered": int(covered_counts[i]),
        }
        for i, (name, pos, lo, hi) in enumerate(
            zip(axis.outlets, axis.positions, axis.ci_low, axis.ci_high)
        )
    ]
    outlets_out.sort(key=lambda o: o["score"])

    ratings = {
        "schema_version": RATINGS_SCHEMA_VERSION,
        "pipeline_version": pipeline_version,
        "snapshot_id": manifest["snapshot_id"],
        "corpus_hash": manifest["corpus_hash"],
        "reference_frame": REFERENCE_FRAME,
        "n_articles": len(articles),
        "n_stories": len(stories),
        "axis_inertia_share": round(axis.inertia_share, 6),
        "orientation": {
            "method": "party-mean speech embeddings (ADR-0003)",
            "correlation": round(orientation.correlation, 6),
            "reliable": orientation.reliable,
        },
        "outlets": outlets_out,
    }
    return PipelineResult(ratings=ratings, stories=stories, matrix=matrix, articles=articles)


def stories_json(result: PipelineResult, manifest: dict) -> dict:
    """The side-by-side primitive for consumers: who covered each story, how
    each headlined it. Same clusters the scores were built on, by identity."""
    return {
        "schema_version": RATINGS_SCHEMA_VERSION,
        "snapshot_id": manifest["snapshot_id"],
        "corpus_hash": manifest["corpus_hash"],
        "stories": [
            {
                "story_id": s.story_id,
                "n_outlets": len(s.outlets),
                "articles": [
                    {
                        "outlet": result.articles[i]["outlet"],
                        "title": result.articles[i]["title"],
                        "url": result.articles[i]["url"],
                        "published": result.articles[i]["published"],
                    }
                    for i in s.article_indices
                ],
            }
            for s in result.stories
        ],
    }
