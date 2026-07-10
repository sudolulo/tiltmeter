"""Which exact articles is a rating computed from?

A snapshot freezes a time window of the corpus into a pinned, verifiable set:
every article in the window, identified by its content fingerprint, listed in
a manifest anyone can publish, re-fetch, and check. Ratings are computed from
snapshots — never from the live, shifting corpus — so a rating and its
evidence can be re-derived long after the news cycle moved on.

The manifest deliberately contains no article text (see METHODOLOGY.md D9):
URL, outlet, headline, timestamps, and fingerprint only.
"""

import hashlib
import json
import sqlite3
from pathlib import Path

MANIFEST_VERSION = 1


def _rows_in_window(conn: sqlite3.Connection, start: str, end: str) -> list[dict]:
    """All articles observed in their feeds within [start, end), ordered
    deterministically. Keyed on observed_at so archive-backfilled items land
    in the window where they appeared, not the day we retrieved them."""
    from tiltmeter import db

    cur = conn.execute(
        "SELECT o.name AS outlet, a.url, a.byline, a.published, a.observed_at,"
        " a.fetched_at, a.source, a.content_hash"
        " FROM articles a JOIN outlets o ON o.id = a.outlet_id"
        " WHERE a.observed_at >= ? AND a.observed_at < ?"
        " ORDER BY a.content_hash, a.url",
        (start, end),
    )
    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    for row in rows:
        content = db.get_article_content(conn, row["content_hash"])
        row["title"] = content[0] if content else ""
    return rows


def corpus_hash(article_hashes: list[str]) -> str:
    """One fingerprint for the whole snapshot: hash of the sorted article hashes."""
    return hashlib.sha256("\n".join(sorted(article_hashes)).encode()).hexdigest()


def create(conn: sqlite3.Connection, start: str, end: str, pipeline_version: str) -> dict:
    """Freeze the window [start, end) into a manifest dict."""
    articles = _rows_in_window(conn, start, end)
    if not articles:
        raise ValueError(f"no articles in window {start}..{end}")
    snapshot_id = f"{start[:10]}_{end[:10]}"
    return {
        "manifest_version": MANIFEST_VERSION,
        "snapshot_id": snapshot_id,
        "window": {"start": start, "end": end, "key": "observed_at"},
        "pipeline_version": pipeline_version,
        "n_articles": len(articles),
        "outlets": sorted({a["outlet"] for a in articles}),
        "corpus_hash": corpus_hash([a["content_hash"] for a in articles]),
        "articles": articles,
    }


def write(manifest: dict, releases_dir: str | Path) -> Path:
    """Write a manifest to releases/, stable formatting for byte-identical re-runs."""
    path = Path(releases_dir) / f"manifest-{manifest['snapshot_id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    return path


def load(path: str | Path) -> dict:
    """Read a manifest back; verify its corpus hash before trusting it."""
    manifest = json.loads(Path(path).read_text())
    expected = corpus_hash([a["content_hash"] for a in manifest["articles"]])
    if manifest["corpus_hash"] != expected:
        raise ValueError(f"corpus_hash mismatch in {path}: manifest is corrupt or edited")
    return manifest
