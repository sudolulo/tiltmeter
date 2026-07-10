"""Can anyone verify the dataset — and does every kind of tampering surface?

The chain-of-custody promise, made executable: content edits, deletions,
history rewrites, and silent schema drift must all be caught by
`tiltmeter audit`'s two checks (custody_verify + verify_contents). Plus the
v1→v2 migration must preserve every fingerprint, or every manifest published
before the migration would become unverifiable.
"""

import sqlite3
import zlib

from tiltmeter import db
from tiltmeter.ingest import canonical_url


def seeded(conn=None):
    conn = conn or db.connect(":memory:")
    hashes = []
    for i in range(4):
        h = db.insert_article(
            conn, outlet=f"o{i % 2}", url=f"https://example.com/{i}",
            title=f"T{i}", published=None, fetched_at=f"2026-07-1{i}T00:00:00+00:00",
            summary=None, text=f"Body {i}",
        )
        hashes.append(h)
    db.custody_append(conn, "ingest", hashes[:2])
    db.custody_append(conn, "ingest", hashes[2:])
    return conn, hashes


def test_intact_dataset_passes_audit():
    conn, _ = seeded()
    assert db.custody_verify(conn) == []
    assert db.verify_contents(conn) == []
    assert db.custody_head(conn)["seq"] == 2


def test_content_edit_is_caught():
    conn, hashes = seeded()
    conn.execute(
        "UPDATE contents SET text_z = ? WHERE content_hash = ?",
        (zlib.compress("T0\x1fEdited body".encode()), hashes[0]),
    )
    problems = db.verify_contents(conn)
    assert any("content altered" in p for p in problems)


def test_deletion_of_chained_content_is_caught(tmp_path):
    # foreign keys are per-connection in SQLite: a tamperer's own connection
    # simply wouldn't enable them, so the audit must not rely on them
    conn, hashes = seeded(db.connect(tmp_path / "c.db"))
    conn.close()
    raw = sqlite3.connect(tmp_path / "c.db")  # no FK pragma: the attacker's view
    raw.execute("DELETE FROM contents WHERE content_hash = ?", (hashes[3],))
    raw.commit()
    raw.close()
    problems = db.verify_contents(db.connect(tmp_path / "c.db"))
    assert any("deleted" in p or "missing" in p for p in problems)


def test_history_rewrite_breaks_chain(tmp_path):
    conn, _ = seeded(db.connect(tmp_path / "h.db"))
    conn.close()
    raw = sqlite3.connect(tmp_path / "h.db")
    raw.execute("DELETE FROM custody_log WHERE seq = 1")  # erase batch 1 from history
    raw.execute("DELETE FROM custody_items WHERE seq = 1")
    raw.commit()
    raw.close()
    problems = db.custody_verify(db.connect(tmp_path / "h.db"))
    assert any("chain break" in p for p in problems)


def test_item_tampering_in_log_is_caught():
    conn, hashes = seeded()
    conn.execute(
        "UPDATE custody_items SET content_hash = ? WHERE content_hash = ?",
        ("f" * 64, hashes[0]),
    )
    problems = db.custody_verify(conn)
    assert any("items_hash mismatch" in p for p in problems)


def test_content_dedup_stores_wire_copy_once():
    conn = db.connect(":memory:")
    kwargs = dict(title="Wire headline", published=None,
                  fetched_at="2026-07-10T00:00:00+00:00", summary=None,
                  text="Same syndicated body.")
    h1 = db.insert_article(conn, outlet="a", url="https://a.com/x", **kwargs)
    h2 = db.insert_article(conn, outlet="b", url="https://b.com/y", **kwargs)
    assert h1 == h2
    assert conn.execute("SELECT COUNT(*) FROM contents").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 2


def test_url_canonicalization():
    assert canonical_url(
        "https://ex.com/story?utm_source=rss&utm_medium=feed&id=7&fbclid=abc#frag"
    ) == "https://ex.com/story?id=7"
    assert canonical_url("https://ex.com/story") == "https://ex.com/story"


def test_v1_migration_preserves_fingerprints(tmp_path):
    """Manifests published against v1 must verify against the migrated store."""
    path = tmp_path / "old.db"
    raw = sqlite3.connect(path)
    raw.executescript("""
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY, outlet TEXT NOT NULL, url TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL, published TEXT, fetched_at TEXT NOT NULL,
            summary TEXT, text TEXT, content_hash TEXT NOT NULL);
        CREATE TABLE reference_speeches (
            id INTEGER PRIMARY KEY, day TEXT NOT NULL, granule TEXT NOT NULL,
            chamber TEXT NOT NULL, speaker TEXT NOT NULL, state TEXT,
            party TEXT NOT NULL, text TEXT NOT NULL, UNIQUE (granule, speaker, text));
    """)
    old_hash = db.content_hash("Old title", "Old body text.")
    raw.execute(
        "INSERT INTO articles (outlet, url, title, published, fetched_at, summary, text,"
        " content_hash) VALUES ('npr', 'https://npr.org/1', 'Old title', NULL,"
        " '2026-07-01T00:00:00+00:00', 'sum', 'Old body text.', ?)", (old_hash,))
    raw.execute(
        "INSERT INTO reference_speeches (day, granule, chamber, speaker, state, party, text)"
        " VALUES ('2026-06-25', 'g.htm', 'House', 'GREEN', 'Texas', 'D', 'A speech text.')")
    raw.commit()
    raw.close()

    conn = db.connect(path)  # triggers migration
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    assert db.get_article_text(conn, old_hash) == ("Old title", "Old body text.")
    row = conn.execute("SELECT summary FROM articles WHERE content_hash=?", (old_hash,)).fetchone()
    assert row == ("sum",)
    speech = conn.execute(
        "SELECT party, content_hash FROM reference_speeches").fetchone()
    assert speech[0] == "D"
    assert db.get_content(conn, speech[1]) == "A speech text."
    assert db.verify_contents(conn) == []
    # migrating again is a no-op
    conn.close()
    conn2 = db.connect(path)
    assert conn2.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 1
