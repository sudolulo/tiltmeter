"""Where does collected data live, and how do we know nobody changed it?

One SQLite file holds everything. SQLite because the auditable artifact IS a
single file — hashable, copyable, publishable, openable by anyone with
standard tools for decades (it is a US Library of Congress recommended
storage format). No server, no credentials, no operational surface.

Schema v2 is content-addressed and append-only:

- `contents` stores each distinct article/speech text exactly once, keyed by
  its SHA-256 fingerprint, zlib-compressed. Identical wire copy syndicated
  to three outlets is stored once; the fingerprint is the join key
  everywhere (embeddings cache, manifests, custody log).
- `articles` and `reference_speeches` hold metadata and point at contents.
- `custody_log` + `custody_items` form a hash chain over ingestion history:
  every batch of new fingerprints appends an entry whose hash covers the
  previous entry's hash. Editing, deleting, or backdating anything already
  recorded breaks the chain at that point — history cannot be rewritten
  quietly. `tiltmeter audit` walks and re-verifies the whole thing.

Collected rows are never updated or deleted. The embeddings cache is derived
data (recomputable from contents) and is exempt from custody.
"""

import hashlib
import sqlite3
import zlib
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 3
GENESIS = "0" * 64
COMPRESSION_LEVEL = 6  # zlib: ~3x on news text, stdlib, no extra dependency

# v3 (early-development reset; no migration path — recreate and recollect):
# articles is pure reference metadata; ALL captured content (title, body,
# feed summary) lives in the fingerprinted payload. observed_at = when the
# item appeared in its feed (live: fetch time; archive backfill: capture
# time) and is what snapshot windows key on; fetched_at = when we stored it
# and is what custody records.
SCHEMA_V3 = """
CREATE TABLE IF NOT EXISTS contents (
    content_hash TEXT PRIMARY KEY,
    text_z BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS outlets (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    first_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY,
    outlet_id INTEGER NOT NULL REFERENCES outlets (id),
    url TEXT NOT NULL UNIQUE,
    url_original TEXT,
    byline TEXT,
    published TEXT,
    observed_at TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'live',
    content_hash TEXT NOT NULL REFERENCES contents (content_hash)
);
CREATE INDEX IF NOT EXISTS idx_articles_outlet ON articles (outlet_id);
CREATE INDEX IF NOT EXISTS idx_articles_observed ON articles (observed_at);
CREATE INDEX IF NOT EXISTS idx_articles_content ON articles (content_hash);
CREATE TABLE IF NOT EXISTS reference_speeches (
    id INTEGER PRIMARY KEY,
    day TEXT NOT NULL,
    granule TEXT NOT NULL,
    chamber TEXT NOT NULL,
    speaker TEXT NOT NULL,
    state TEXT,
    party TEXT NOT NULL,
    content_hash TEXT NOT NULL REFERENCES contents (content_hash),
    UNIQUE (granule, speaker, content_hash)
);
CREATE TABLE IF NOT EXISTS custody_log (
    seq INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,
    n_items INTEGER NOT NULL,
    items_hash TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    entry_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS custody_items (
    seq INTEGER NOT NULL REFERENCES custody_log (seq),
    content_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_custody_items_seq ON custody_items (seq);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open the database, creating the schema if needed. Pre-v3 stores are
    refused: this is early development and old stores are recollected, not
    migrated (the migration machinery was deleted with them)."""
    if isinstance(db_path, str) and db_path != ":memory:" and not db_path.startswith("file:"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    elif isinstance(db_path, Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    has_tables = conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0] > 0
    if has_tables and version < SCHEMA_VERSION:
        raise RuntimeError(
            f"store is schema v{version}; v{SCHEMA_VERSION} is a clean early-dev reset —"
            " delete the database (and stale releases) and recollect"
        )
    conn.executescript(SCHEMA_V3)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
    return conn


def _article_payload(title: str, text: str, summary: str) -> str:
    """The exact byte content an article fingerprint covers: everything we
    captured about the piece — headline, body, and feed summary."""
    return title + "\x1f" + text + "\x1f" + summary


def content_hash(title: str, text: str, summary: str = "") -> str:
    """Fingerprint an article's full captured content."""
    return hashlib.sha256(_article_payload(title, text, summary).encode("utf-8")).hexdigest()


def _store_content(conn: sqlite3.Connection, chash: str, payload: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO contents (content_hash, text_z) VALUES (?, ?)",
        (chash, zlib.compress(payload.encode("utf-8"), COMPRESSION_LEVEL)),
    )


def get_content(conn: sqlite3.Connection, chash: str) -> str | None:
    row = conn.execute(
        "SELECT text_z FROM contents WHERE content_hash = ?", (chash,)
    ).fetchone()
    return zlib.decompress(row[0]).decode("utf-8") if row else None


def get_article_content(conn: sqlite3.Connection, chash: str) -> tuple[str, str, str] | None:
    """(title, body, summary) for an article fingerprint, or None."""
    payload = get_content(conn, chash)
    if payload is None:
        return None
    parts = payload.split("\x1f", 2)
    while len(parts) < 3:
        parts.append("")
    return parts[0], parts[1], parts[2]


def outlet_id(conn: sqlite3.Connection, name: str, first_seen: str | None = None) -> int:
    """Get-or-create the outlet dimension row; outlet names are stored once."""
    row = conn.execute("SELECT id FROM outlets WHERE name = ?", (name,)).fetchone()
    if row:
        return row[0]
    ts = first_seen or datetime.now(timezone.utc).isoformat()
    cur = conn.execute("INSERT INTO outlets (name, first_seen) VALUES (?, ?)", (name, ts))
    return cur.lastrowid


def have_url(conn: sqlite3.Connection, url: str) -> bool:
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
    url_original: str | None = None,
    byline: str | None = None,
    observed_at: str | None = None,
    source: str = "live",
) -> str | None:
    """Store one newly collected article. Returns its fingerprint, or None
    if the URL was already present."""
    if have_url(conn, url):
        return None
    chash = content_hash(title, text or "", summary or "")
    _store_content(conn, chash, _article_payload(title, text or "", summary or ""))
    conn.execute(
        "INSERT INTO articles"
        " (outlet_id, url, url_original, byline, published, observed_at, fetched_at, source,"
        " content_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (outlet_id(conn, outlet, fetched_at), url, url_original, byline,
         published, observed_at or fetched_at, fetched_at, source, chash),
    )
    return chash


def insert_speech(
    conn: sqlite3.Connection,
    *,
    day: str,
    granule: str,
    chamber: str,
    speaker: str,
    state: str | None,
    party: str,
    text: str,
) -> str | None:
    """Store one attributed floor speech. Returns its fingerprint, or None
    if this (granule, speaker, content) was already present."""
    chash = hashlib.sha256(text.encode()).hexdigest()
    existing = conn.execute(
        "SELECT 1 FROM reference_speeches WHERE granule=? AND speaker=? AND content_hash=?",
        (granule, speaker, chash),
    ).fetchone()
    if existing:
        return None
    _store_content(conn, chash, text)
    conn.execute(
        "INSERT INTO reference_speeches"
        " (day, granule, chamber, speaker, state, party, content_hash)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (day, granule, chamber, speaker, state, party, chash),
    )
    return chash


def outlet_counts(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    return conn.execute(
        "SELECT o.name, COUNT(*) FROM articles a JOIN outlets o ON o.id = a.outlet_id"
        " GROUP BY o.name ORDER BY o.name"
    ).fetchall()


# --- custody chain -----------------------------------------------------------


def _entry_hash(prev_hash: str, items_hash: str, kind: str, ts: str, n: int) -> str:
    return hashlib.sha256(f"{prev_hash}|{items_hash}|{kind}|{ts}|{n}".encode()).hexdigest()


def items_hash(hashes: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(hashes)).encode()).hexdigest()


def custody_head(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        "SELECT seq, ts, entry_hash FROM custody_log ORDER BY seq DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return {"seq": 0, "ts": None, "entry_hash": GENESIS}
    return {"seq": row[0], "ts": row[1], "entry_hash": row[2]}


def custody_append(conn: sqlite3.Connection, kind: str, new_hashes: list[str]) -> dict | None:
    """Chain one batch of newly collected fingerprints. Empty batches are not
    recorded — the chain logs data arrival, not polling."""
    if not new_hashes:
        return None
    head = custody_head(conn)
    ts = datetime.now(timezone.utc).isoformat()
    batch = items_hash(new_hashes)
    entry = _entry_hash(head["entry_hash"], batch, kind, ts, len(new_hashes))
    seq = head["seq"] + 1
    conn.execute(
        "INSERT INTO custody_log (seq, ts, kind, n_items, items_hash, prev_hash, entry_hash)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (seq, ts, kind, len(new_hashes), batch, head["entry_hash"], entry),
    )
    conn.executemany(
        "INSERT INTO custody_items (seq, content_hash) VALUES (?, ?)",
        [(seq, h) for h in new_hashes],
    )
    conn.commit()
    return {"seq": seq, "entry_hash": entry, "n_items": len(new_hashes)}


def verify_contents(conn: sqlite3.Connection) -> list[str]:
    """Re-hash every stored content blob; return problems (empty = intact).

    Every contents row must decompress to bytes whose SHA-256 equals its key,
    every metadata row must point at a content row that exists, and every
    custody item must still be present. Together with custody_verify this is
    the full tamper check: text edits, deletions, and history rewrites all
    surface here.
    """
    problems = []
    for chash, blob in conn.execute("SELECT content_hash, text_z FROM contents"):
        if hashlib.sha256(zlib.decompress(blob)).hexdigest() != chash:
            problems.append(f"content altered: {chash[:12]}…")
    for table in ("articles", "reference_speeches"):
        for (chash,) in conn.execute(
            f"SELECT content_hash FROM {table}"
            " WHERE content_hash NOT IN (SELECT content_hash FROM contents)"
        ):
            problems.append(f"{table} row points at missing content {chash[:12]}…")
    for (chash,) in conn.execute(
        "SELECT DISTINCT content_hash FROM custody_items"
        " WHERE content_hash NOT IN (SELECT content_hash FROM contents)"
    ):
        problems.append(f"custody-chained content deleted: {chash[:12]}…")
    return problems


def custody_verify(conn: sqlite3.Connection) -> list[str]:
    """Walk the whole chain; return problems (empty list = intact)."""
    problems = []
    prev = GENESIS
    for seq, ts, kind, n, batch, prev_recorded, entry in conn.execute(
        "SELECT seq, ts, kind, n_items, items_hash, prev_hash, entry_hash"
        " FROM custody_log ORDER BY seq"
    ):
        if prev_recorded != prev:
            problems.append(f"chain break at seq {seq}: prev_hash mismatch")
        item_rows = [
            r[0] for r in conn.execute(
                "SELECT content_hash FROM custody_items WHERE seq = ?", (seq,)
            )
        ]
        if len(item_rows) != n:
            problems.append(f"seq {seq}: {len(item_rows)} items recorded, entry says {n}")
        if items_hash(item_rows) != batch:
            problems.append(f"seq {seq}: items_hash mismatch (items altered)")
        if _entry_hash(prev_recorded, batch, kind, ts, n) != entry:
            problems.append(f"seq {seq}: entry_hash mismatch (entry altered)")
        prev = entry
    return problems
