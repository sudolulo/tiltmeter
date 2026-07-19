"""Does the collector store, deduplicate, and fingerprint articles correctly?

Pure unit tests — no network. Feed parsing and article fetching are exercised
by the live cron run; what must never regress silently is the storage
contract: one row per URL, stable fingerprints, accurate per-outlet counts.
"""

import pytest

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


def test_outlet_dimension_and_byline():
    from tiltmeter.ingest import strip_html

    conn = db.connect(":memory:")
    for i in range(3):
        db.insert_article(
            conn, outlet="nytimes", url=f"https://nytimes.com/{i}", title=f"T{i}",
            published=None, fetched_at="2026-07-10T00:00:00+00:00",
            summary=None, text="x", byline="By Jane Doe" if i == 0 else None,
        )
    # outlet name stored once, referenced thrice
    assert conn.execute("SELECT COUNT(*) FROM outlets").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 3
    assert conn.execute(
        "SELECT byline FROM articles WHERE url LIKE '%/0'"
    ).fetchone()[0] == "By Jane Doe"
    # summaries are stored as prose, not markup
    assert strip_html('<p>Real <b>text</b></p><img src="pixel.gif"/>') == "Real text"
    assert strip_html("") is None


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


def test_reject_unroutable_host_blocks_private_and_link_local_ranges():
    from tiltmeter.ingest import _reject_unroutable_host

    # RFC1918, loopback, link-local (incl. the cloud metadata address), and
    # their IPv6 equivalents — a compromised feed pointing <link> here must
    # never be fetched.
    for host in (
        "127.0.0.1", "169.254.169.254", "10.1.2.3", "192.168.1.1", "172.16.0.5",
        "::1", "fc00::1", "fe80::1",
    ):
        with pytest.raises(ValueError, match="non-public"):
            _reject_unroutable_host(host)


def test_reject_unroutable_host_allows_public_addresses():
    from tiltmeter.ingest import _reject_unroutable_host

    _reject_unroutable_host("8.8.8.8")  # a literal IP needs no DNS lookup


def test_fetch_article_text_refuses_private_target_before_any_request(monkeypatch):
    """The host check must run before the network call, not after."""
    from tiltmeter import ingest

    def fail_if_called(*args, **kwargs):
        raise AssertionError("must not contact the network for a private-IP link")

    monkeypatch.setattr(ingest.requests, "get", fail_if_called)
    with pytest.raises(ValueError, match="non-public"):
        ingest.fetch_article_text("http://127.0.0.1:9/admin")


def test_fetch_article_text_revalidates_host_on_redirect(monkeypatch):
    """A redirect to a private address must be rejected, not followed."""
    from tiltmeter import ingest

    class FakeResponse:
        status_code = 302
        is_redirect = True
        headers = {"Location": "http://169.254.169.254/latest/meta-data/"}

    monkeypatch.setattr(ingest.requests, "get", lambda *a, **k: FakeResponse())
    with pytest.raises(ValueError, match="non-public"):
        ingest.fetch_article_text("https://example.com/story")
