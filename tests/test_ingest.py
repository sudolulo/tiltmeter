"""Does the collector store, deduplicate, and fingerprint articles correctly?

Pure unit tests — no network. Feed parsing and article fetching are exercised
by the live cron run; what must never regress silently is the storage
contract: one row per URL, stable fingerprints, accurate per-outlet counts.
"""

from tiltmeter import db


def test_insert_and_dedup_by_url():
    conn = db.connect(":memory:")
    kwargs = dict(
        outlet="example",
        url="https://example.com/a",
        title="Headline",
        published=None,
        fetched_at="2026-07-10T00:00:00+00:00",
        summary=None,
        text="Body text.",
    )
    db.insert_article(conn, **kwargs)
    db.insert_article(conn, **kwargs)  # same URL again: must not duplicate
    assert db.outlet_counts(conn) == [("example", 1)]
    assert db.have_url(conn, "https://example.com/a")
    assert not db.have_url(conn, "https://example.com/b")


def test_content_hash_is_stable_and_content_sensitive():
    a = db.content_hash("Headline", "Body text.")
    assert a == db.content_hash("Headline", "Body text.")  # deterministic
    assert a != db.content_hash("Headline", "Body text!")  # any edit changes it
    assert a != db.content_hash("Headline2", "Body text.")
    # title/text boundary is unambiguous: moving a word across it changes the hash
    assert db.content_hash("A B", "C") != db.content_hash("A", "B C")


def test_counts_group_by_outlet():
    conn = db.connect(":memory:")
    for i, outlet in enumerate(["left-times", "right-post", "left-times"]):
        db.insert_article(
            conn,
            outlet=outlet,
            url=f"https://example.com/{i}",
            title=f"T{i}",
            published=None,
            fetched_at="2026-07-10T00:00:00+00:00",
            summary=None,
            text="x",
        )
    assert db.outlet_counts(conn) == [("left-times", 2), ("right-post", 1)]
