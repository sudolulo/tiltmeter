"""Where do collected articles live?

One SQLite file holds every article we have ever collected: which outlet
published it, when we saw it, its headline, its text, and a fingerprint (hash)
of its content. The fingerprint is what later lets anyone verify that a
published rating was computed from exactly these articles and no others.
"""

import hashlib
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY,
    outlet TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    published TEXT,
    fetched_at TEXT NOT NULL,
    summary TEXT,
    text TEXT,
    content_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_articles_outlet ON articles (outlet);
CREATE INDEX IF NOT EXISTS idx_articles_fetched ON articles (fetched_at);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open (creating if needed) the article database."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def content_hash(title: str, text: str) -> str:
    """Fingerprint an article's content.

    SHA-256 over headline + body. Two articles with the same fingerprint have
    identical content; a snapshot manifest of fingerprints pins a corpus.
    """
    return hashlib.sha256((title + "\x1f" + text).encode("utf-8")).hexdigest()


def have_url(conn: sqlite3.Connection, url: str) -> bool:
    """Have we already collected this article? (Dedup key is the URL.)"""
    row = conn.execute("SELECT 1 FROM articles WHERE url = ? LIMIT 1", (url,)).fetchone()
    return row is not None


def insert_article(
    conn: sqlite3.Connection,
    *,
    outlet: str,
    url: str,
    title: str,
    published: str | None,
    fetched_at: str,
    summary: str | None,
    text: str | None,
) -> None:
    """Store one newly collected article."""
    conn.execute(
        "INSERT OR IGNORE INTO articles"
        " (outlet, url, title, published, fetched_at, summary, text, content_hash)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (outlet, url, title, published, fetched_at, summary, text, content_hash(title, text or "")),
    )


def outlet_counts(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    """How many articles do we have per outlet? (The health check for ingestion.)"""
    return conn.execute(
        "SELECT outlet, COUNT(*) FROM articles GROUP BY outlet ORDER BY outlet"
    ).fetchall()
