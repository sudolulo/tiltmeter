"""Can anyone verify the dataset — and does every kind of tampering surface?

The chain-of-custody promise, made executable: content edits, deletions,
history rewrites, and silent schema drift must all be caught by
`tiltmeter audit`'s two checks (custody_verify + verify_contents). Pre-v3
stores are refused outright — early-development stores are recollected,
never migrated — and that refusal is pinned here too.
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
    conn.commit()  # callers own the transaction; collectors commit rows+chain together
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


def test_pre_v3_store_is_refused(tmp_path):
    """Old stores are recollected, never half-migrated: refuse loudly."""
    import pytest

    path = tmp_path / "old.db"
    raw = sqlite3.connect(path)
    raw.execute("CREATE TABLE articles (id INTEGER PRIMARY KEY, text TEXT)")
    raw.execute("PRAGMA user_version = 2")
    raw.commit()
    raw.close()
    with pytest.raises(RuntimeError, match="early-dev reset"):
        db.connect(path)


def test_fingerprint_covers_summary():
    """Two paywalled articles (no body) with the same headline but different
    feed summaries must NOT share a fingerprint — under the v2 payload they
    collided and could share one embedding."""
    conn = db.connect(":memory:")
    common = dict(outlet="wapo", title="Same headline", published=None,
                  fetched_at="2026-07-10T00:00:00+00:00", text=None)
    h1 = db.insert_article(conn, url="https://w.po/1", summary="First framing.", **common)
    h2 = db.insert_article(conn, url="https://w.po/2", summary="Other framing.", **common)
    db.custody_append(conn, "ingest", [h1, h2])
    conn.commit()
    assert h1 != h2
    assert db.split_article_payload(
        db.get_contents(conn, [h1])[h1]
    ) == ("Same headline", "", "First framing.")
    assert db.verify_contents(conn) == []


def test_observed_at_defaults_to_fetched_and_accepts_backfill():
    conn = db.connect(":memory:")
    live = db.insert_article(
        conn, outlet="npr", url="https://npr.org/live", title="Live", published=None,
        fetched_at="2026-07-10T06:00:00+00:00", summary=None, text="x")
    back = db.insert_article(
        conn, outlet="npr", url="https://npr.org/old", title="Old", published=None,
        fetched_at="2026-07-10T06:00:00+00:00", summary=None, text="y",
        observed_at="2026-06-01T12:00:00+00:00", source="wayback")
    db.custody_append(conn, "ingest", [live, back])
    conn.commit()
    assert live and back
    rows = dict(conn.execute("SELECT url, observed_at FROM articles").fetchall())
    assert rows["https://npr.org/live"] == "2026-07-10T06:00:00+00:00"
    assert rows["https://npr.org/old"] == "2026-06-01T12:00:00+00:00"
