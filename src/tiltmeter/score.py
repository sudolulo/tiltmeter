"""How does a snapshot become ratings.json?

The assembly line, end to end: manifest → embeddings → story clusters →
coverage matrix → selection axis with confidence intervals → orientation by
congressional language → one deterministic JSON file. No timestamps, no
randomness outside the fixed bootstrap seed: rerunning on the same snapshot
must produce the same bytes (METHODOLOGY.md D1, D10).
"""

import json
import sqlite3
from pathlib import Path

import numpy as np

from tiltmeter import embed, orient
from tiltmeter.cluster import cluster_articles, coverage_matrix
from tiltmeter.signals import selection

RATINGS_SCHEMA_VERSION = 1
REFERENCE_FRAME = (
    "lean relative to contemporary US congressional party discourse; "
    "negative = left, positive = right"
)


def compute(conn: sqlite3.Connection, manifest: dict, pipeline_version: str) -> dict:
    """Run the full pipeline on a loaded manifest; return the ratings dict."""
    articles = manifest["articles"]
    outlet_order = manifest["outlets"]

    vectors = embed.embed_hashes(conn, [a["content_hash"] for a in articles])
    stories = cluster_articles(vectors, [a["outlet"] for a in articles])
    matrix = coverage_matrix(stories, outlet_order)
    axis = selection.compute(matrix, outlet_order)

    outlet_vectors = {}
    for name in outlet_order:
        rows = [i for i, a in enumerate(articles) if a["outlet"] == name]
        outlet_vectors[name] = vectors[rows].mean(axis=0)
    party = orient.party_means(conn)
    proxy = orient.outlet_proxy(outlet_vectors, party)
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

    return {
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


def write(ratings: dict, out_dir: str | Path) -> Path:
    """Deterministic serialization: same ratings dict, same bytes."""
    path = Path(out_dir) / f"ratings-{ratings['snapshot_id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ratings, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    return path


def story_details(conn: sqlite3.Connection, manifest: dict) -> tuple[list, np.ndarray, list]:
    """Recompute stories + matrix + story axis coords for evidence pages."""
    articles = manifest["articles"]
    vectors = embed.embed_hashes(conn, [a["content_hash"] for a in articles])
    stories = cluster_articles(vectors, [a["outlet"] for a in articles])
    matrix = coverage_matrix(stories, manifest["outlets"])
    return stories, matrix, articles


def stories_json(stories: list, articles: list, manifest: dict) -> dict:
    """The side-by-side primitive for consumers: who covered each story, how
    each headlined it. Deterministic; same clusters the scores were built on."""
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
                        "outlet": articles[i]["outlet"],
                        "title": articles[i]["title"],
                        "url": articles[i]["url"],
                        "published": articles[i]["published"],
                    }
                    for i in s.article_indices
                ],
            }
            for s in stories
        ],
    }


def write_stories(payload: dict, out_dir: str | Path) -> Path:
    path = Path(out_dir) / f"stories-{payload['snapshot_id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    return path
