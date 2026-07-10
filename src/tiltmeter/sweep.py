"""How much do the ratings depend on our judgment calls?

The sensitivity sweep (METHODOLOGY.md D7): rerun scoring across a grid of
values for the main tunable — the story-clustering distance threshold — and
publish how much the outlet ordering moves. If a small settings change
reshuffles the outlets, readers deserve to see that; if the ordering is
stable, that stability is evidence the axis is real rather than an artifact
of one parameter choice.

Published per release as sweep-{snapshot}.json: per-threshold scores plus
the pairwise rank correlation between every threshold's ordering and the
default's.
"""

import sqlite3
from pathlib import Path

from tiltmeter import embed, orient
from tiltmeter.artifacts import write as write_artifact
from tiltmeter.score import outlet_mean_vectors
from tiltmeter.cluster import DISTANCE_THRESHOLD, cluster_articles, coverage_matrix
from tiltmeter.stats import spearman
from tiltmeter.signals import selection

THRESHOLD_GRID = (0.35, 0.40, 0.45, 0.50, 0.55)


def run_sweep(conn: sqlite3.Connection, manifest: dict) -> dict:
    """Score the same snapshot at every threshold; report ordering stability."""
    articles = manifest["articles"]
    outlet_order = manifest["outlets"]
    vectors = embed.embed_hashes(conn, [a["content_hash"] for a in articles])
    outlets = [a["outlet"] for a in articles]

    party = orient.party_means(conn)
    proxy = orient.outlet_proxy(outlet_mean_vectors(articles, vectors, outlet_order), party)

    per_threshold: dict[str, dict] = {}
    for threshold in THRESHOLD_GRID:
        stories = cluster_articles(vectors, outlets, threshold=threshold)
        matrix = coverage_matrix(stories, outlet_order)
        try:
            axis = selection.compute(matrix, outlet_order)
        except ValueError as exc:
            per_threshold[f"{threshold:.2f}"] = {"error": str(exc), "n_stories": len(stories)}
            continue
        orientation = orient.orient_sign(
            list(axis.positions), [proxy[n] for n in axis.outlets]
        )
        per_threshold[f"{threshold:.2f}"] = {
            "n_stories": len(stories),
            "orientation_rho": round(orientation.correlation, 4),
            "scores": {
                name: round(orientation.sign * pos, 6)
                for name, pos in zip(axis.outlets, axis.positions)
            },
        }

    default_key = f"{DISTANCE_THRESHOLD:.2f}"
    default_scores = per_threshold.get(default_key, {}).get("scores")
    stability = {}
    if default_scores:
        base = [default_scores[n] for n in outlet_order]
        for key, entry in per_threshold.items():
            if "scores" in entry:
                other = [entry["scores"][n] for n in outlet_order]
                stability[key] = round(spearman(base, other), 4)

    return {
        "snapshot_id": manifest["snapshot_id"],
        "corpus_hash": manifest["corpus_hash"],
        "default_threshold": DISTANCE_THRESHOLD,
        "thresholds": per_threshold,
        "rank_correlation_vs_default": stability,
    }


def write(sweep: dict, out_dir: str | Path) -> Path:
    return write_artifact(out_dir, "sweeps", sweep["snapshot_id"], sweep)
