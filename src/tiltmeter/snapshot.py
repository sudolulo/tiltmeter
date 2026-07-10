"""Which exact articles is a rating computed from?

A snapshot freezes a time window of the corpus into a pinned, verifiable set,
listed in a manifest anyone can publish, re-fetch, and check. Ratings are
computed from snapshots — never from the live, shifting corpus — so a rating
and its evidence can be re-derived long after the news cycle moved on.

The manifest deliberately contains no article text (METHODOLOGY.md D9), and
its corpus_hash covers **every field of every article record** — outlet
attribution, URLs, byline, timestamps, and the content fingerprint — not just
the fingerprints. Editing any metadata in a published manifest breaks the
hash: attribution is evidence too.
"""

import hashlib
import json
import sqlite3
from pathlib import Path

from tiltmeter.artifacts import read_json, write_json

MANIFEST_VERSION = 2  # v2: corpus_hash covers full article records


def _rows_in_window(conn: sqlite3.Connection, start: str, end: str) -> list[dict]:
    """All articles observed in their feeds within [start, end), ordered
    deterministically. Keyed on observed_at so archive-backfilled items land
    in the window where they appeared, not the day we retrieved them."""
    import zlib

    from tiltmeter import db

    cur = conn.execute(
        "SELECT o.name AS outlet, a.url, a.byline, a.published, a.observed_at,"
        " a.fetched_at, a.source, a.content_hash, c.text_z"
        " FROM articles a JOIN outlets o ON o.id = a.outlet_id"
        " LEFT JOIN contents c ON c.content_hash = a.content_hash"
        " WHERE a.observed_at >= ? AND a.observed_at < ?"
        " ORDER BY a.content_hash, a.url",
        (start, end),
    )
    rows = []
    titles: dict[str, str] = {}  # decompress each distinct payload once
    for outlet, url, byline, published, observed, fetched, source, chash, blob in cur:
        if blob is None:
            # a manifested article whose content is gone is store corruption;
            # a silently smaller manifest would mask it — fail loudly instead
            raise RuntimeError(
                f"article {url} has no content row ({chash[:12]}…) — store is"
                " corrupt; run tiltmeter audit"
            )
        if chash not in titles:
            payload = zlib.decompress(blob).decode("utf-8")
            titles[chash] = db.split_article_payload(payload)[0]
        rows.append({
            "outlet": outlet, "url": url, "byline": byline, "published": published,
            "observed_at": observed, "fetched_at": fetched, "source": source,
            "content_hash": chash, "title": titles[chash],
        })
    return rows


def corpus_hash(articles: list[dict]) -> str:
    """One fingerprint for the whole snapshot, covering every field of every
    record: canonical (sorted-key, UTF-8) serialization of each article,
    hashed in sorted order."""
    lines = sorted(
        json.dumps(a, sort_keys=True, ensure_ascii=False) for a in articles
    )
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


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
        "corpus_hash": corpus_hash(articles),
        "articles": articles,
    }


def write(manifest: dict, releases_dir: str | Path) -> Path:
    return write_json(
        Path(releases_dir) / f"manifest-{manifest['snapshot_id']}.json", manifest
    )


def load(path: str | Path) -> dict:
    """Read a manifest back; verify its corpus hash before trusting it."""
    manifest = read_json(path)
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        raise ValueError(f"manifest version {manifest.get('manifest_version')} unsupported")
    if manifest["corpus_hash"] != corpus_hash(manifest["articles"]):
        raise ValueError(f"corpus_hash mismatch in {path}: manifest is corrupt or edited")
    return manifest
