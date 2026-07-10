"""Can a snapshot be frozen, written, reloaded, and trusted?

The manifest is the reproducibility anchor: these tests pin its determinism
(same corpus, same manifest, byte for byte) and its tamper-evidence (any edit
to the article list must be detected on load).
"""

import json

import pytest

from tiltmeter import db, snapshot


def corpus(conn, n=5):
    for i in range(n):
        db.insert_article(
            conn,
            outlet=f"outlet-{i % 2}",
            url=f"https://example.com/{i}",
            title=f"Headline {i}",
            published=None,
            fetched_at=f"2026-07-{10 + i:02d}T12:00:00+00:00",
            summary=None,
            text=f"Body {i}",
        )
    conn.commit()


def test_manifest_is_deterministic(tmp_path):
    conn = db.connect(":memory:")
    corpus(conn)
    m1 = snapshot.create(conn, "2026-07-10", "2026-07-20", "0.2.0")
    m2 = snapshot.create(conn, "2026-07-10", "2026-07-20", "0.2.0")
    p1 = snapshot.write(m1, tmp_path / "a")
    p2 = snapshot.write(m2, tmp_path / "b")
    assert p1.read_bytes() == p2.read_bytes(), "same corpus must give identical manifests"


def test_window_selects_by_fetched_at():
    conn = db.connect(":memory:")
    corpus(conn, n=5)  # fetched 07-10 .. 07-14
    m = snapshot.create(conn, "2026-07-11", "2026-07-13", "0.2.0")
    assert m["n_articles"] == 2
    assert all("2026-07-11" <= a["fetched_at"] < "2026-07-13" for a in m["articles"])


def test_load_detects_tampering(tmp_path):
    conn = db.connect(":memory:")
    corpus(conn)
    path = snapshot.write(snapshot.create(conn, "2026-07-10", "2026-07-20", "0.2.0"), tmp_path)
    assert snapshot.load(path)["n_articles"] == 5  # clean load passes

    tampered = json.loads(path.read_text())
    tampered["articles"][0]["title"] = "Edited headline"
    tampered["articles"][0]["content_hash"] = "0" * 64
    path.write_text(json.dumps(tampered))
    with pytest.raises(ValueError, match="corpus_hash mismatch"):
        snapshot.load(path)


def test_empty_window_refused():
    conn = db.connect(":memory:")
    corpus(conn)
    with pytest.raises(ValueError, match="no articles"):
        snapshot.create(conn, "2025-01-01", "2025-01-02", "0.2.0")
