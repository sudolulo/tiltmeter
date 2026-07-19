"""Does every defect the first full audit found stay fixed?

One regression test per finding family from the 2026-07-10 codebase audit.
If any of these fail, a promise the audit restored has been re-broken.
"""

import re
from pathlib import Path

import numpy as np
import pytest

import tiltmeter
from tiltmeter import artifacts, db, embed, serve
from tiltmeter.stats import spearman

ROOT = Path(__file__).resolve().parent.parent


def test_spearman_is_order_invariant_on_ties():
    """The gate statistic must not depend on outlet alphabetization."""
    scores = np.array([0.9, 0.5, 0.1, -0.1, -0.5, -0.9])
    tied_ref = np.array([2, 1, 1, -1, -1, -2])  # 5-point-scale ties
    base = spearman(scores, tied_ref)
    for perm_seed in range(5):
        rng = np.random.default_rng(perm_seed)
        order = rng.permutation(len(scores))
        assert spearman(scores[order], tied_ref[order]) == pytest.approx(base)
    # textbook value for this configuration (tie-averaged ranks)
    assert base == pytest.approx(0.9711, abs=1e-3)


def test_audit_detects_unchained_content():
    """Rows committed around the chain must fail the audit, not pass it."""
    conn = db.connect(":memory:")
    db.insert_article(
        conn, outlet="x", url="https://x.com/1", title="T", published=None,
        fetched_at="2026-07-10T00:00:00+00:00", summary=None, text="b",
    )
    conn.commit()  # committed, never chained — the orphan case
    problems = db.verify_contents(conn)
    assert any("outside the custody chain" in p for p in problems)


def test_audit_refuses_missing_store(tmp_path):
    with pytest.raises(FileNotFoundError, match="refusing to audit"):
        db.connect_readonly(tmp_path / "nope.db")
    assert not (tmp_path / "nope.db").exists(), "refusal must not create a store"


def test_insert_rejects_naive_timestamps():
    """Windowing compares strings, so UTC-awareness is enforced at the door."""
    conn = db.connect(":memory:")
    with pytest.raises(ValueError, match="timezone-aware"):
        db.insert_article(
            conn, outlet="x", url="https://x.com/1", title="T", published=None,
            fetched_at="2026-07-01", summary=None, text="b",
        )
    # offsets are normalized to UTC so string comparison stays chronological
    h = db.insert_article(
        conn, outlet="x", url="https://x.com/2", title="T", published=None,
        fetched_at="2026-07-09T23:00:00-04:00", summary=None, text="b",
    )
    assert h
    row = conn.execute("SELECT observed_at FROM articles").fetchone()[0]
    assert row == "2026-07-10T03:00:00+00:00"


def test_health_marks_bad_timestamps_stale_instead_of_crashing(tmp_path):
    """Legacy or tampered rows can still hold junk timestamps; the monitoring
    endpoint must mark them stale, never die."""
    conn = db.connect(tmp_path / "c.db")
    h = db.insert_article(
        conn, outlet="weird", url="https://w.com/1", title="T", published=None,
        fetched_at="2026-07-01T00:00:00+00:00", summary=None, text="b",
    )
    db.custody_append(conn, "ingest", [h])
    # simulate legacy/tampered data: junk timestamp written around the API
    conn.execute("UPDATE articles SET fetched_at = '2026-07-01' WHERE content_hash = ?", (h,))
    conn.commit()
    conn.close()
    health = serve.collection_health(tmp_path / "c.db", configured=["weird"])
    assert health["hours_since_last_article"]["weird"] is None
    assert health["stale_outlets"] == ["weird"]


def test_peek_validation_writes_unservable_filename(tmp_path):
    """A peek artifact must not be publishable as the gate."""
    from tiltmeter.cli import main

    ratings = {
        "snapshot_id": "2026-07-01_2026-07-15", "corpus_hash": "x" * 64,
        "pipeline_version": "t", "orientation": {"reliable": True},
        "outlets": [{"outlet": o, "score": s} for o, s in
                    [("a", -0.5), ("b", -0.2), ("c", 0.0), ("d", 0.2), ("e", 0.5)]],
    }
    artifacts.write_json(tmp_path / "ratings-2026-07-01_2026-07-15.json", ratings)
    ref = tmp_path / "ref.yaml"
    ref.write_text(
        "ratings:\n" + "".join(
            f"  {o}:\n"
            f"    allsides: {{value: Center, verified: false}}\n"
            f"    ad_fontes: {{value: {i - 2}.0, verified: false}}\n"
            for i, o in enumerate("abcde")
        ), encoding="utf-8",
    )
    rc = main(["validate", "--ratings", str(tmp_path / "ratings-2026-07-01_2026-07-15.json"),
               "--reference", str(ref), "--allow-unverified"])
    assert rc == 2, "a peek is by definition not a passed gate: exit 2"
    peek = tmp_path / "validation-peek-2026-07-01_2026-07-15.json"
    assert peek.exists(), "peek must write the peek-prefixed file"
    assert not (tmp_path / "validation-2026-07-01_2026-07-15.json").exists()
    payload = artifacts.read_json(peek)
    assert payload["peek"] is True and not payload["gate_passed"]
    # and the API cannot serve it: the peek prefix is not an artifact kind
    assert "validation-peek" not in {v for v in artifacts.KINDS.values()}


def test_failed_insert_cannot_strand_unchained_content(monkeypatch):
    """A failure between the content write and the metadata write must roll
    back both — otherwise the batch commit would durably orphan content."""
    conn = db.connect(":memory:")

    def boom(*a, **k):
        raise RuntimeError("simulated failure after content write")

    monkeypatch.setattr(db, "outlet_id", boom)
    with pytest.raises(RuntimeError, match="simulated"):
        db.insert_article(
            conn, outlet="x", url="https://x.com/1", title="T", published=None,
            fetched_at="2026-07-10T00:00:00+00:00", summary=None, text="b",
        )
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM contents").fetchone()[0] == 0


def test_batch_atomicity_on_autocommit_connection():
    """The pass-3 regression, pinned: on a fresh (autocommit) connection —
    the real ingest path — inserts must ride ONE batch transaction, so a
    rollback before custody_append leaves nothing durable. Python sqlite3
    opens no transaction for SAVEPOINT; without the explicit BEGIN guard,
    RELEASE was committing every item individually."""
    conn = db.connect(":memory:")
    for i in range(2):
        db.insert_article(
            conn, outlet="x", url=f"https://x.com/{i}", title=f"T{i}", published=None,
            fetched_at="2026-07-10T00:00:00+00:00", summary=None, text=f"b{i}",
        )
    assert conn.in_transaction, "inserts must remain uncommitted until the caller commits"
    conn.rollback()  # ingest_all's bad-feed path / crash before custody_append
    assert conn.execute("SELECT COUNT(*) FROM contents").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 0


def test_thin_rater_recorded_distinctly_from_missing():
    """Too-few-shared-outlets and no-verified-values demand different fixes;
    the artifact must say which one happened."""
    from tiltmeter import validate

    thin_ref = validate.Reference(
        by_rater={"allsides": {o: round(s * 2) for o, s in
                               [("left-a", -0.9), ("left-b", -0.5), ("mid-c", -0.1),
                                ("mid-d", 0.1), ("right-e", 0.5), ("right-f", 0.9)]},
                  "ad_fontes": {"left-a": -15.0, "mid-c": 0.0, "right-e": 12.0}},
        unverified_used=[], unverified_skipped=[],
    )
    scores = dict([("left-a", -0.9), ("left-b", -0.5), ("mid-c", -0.1),
                   ("mid-d", 0.1), ("right-e", 0.5), ("right-f", 0.9)])
    ratings_doc = {
        "snapshot_id": "s", "corpus_hash": "x" * 64, "pipeline_version": "t",
        "orientation": {"reliable": True},
        "outlets": [{"outlet": o, "score": v} for o, v in scores.items()],
    }
    result = validate.report(ratings_doc, thin_ref)
    assert result["raters_missing"] == []
    assert "ad_fontes" in result["raters_thin"]
    assert "3 outlets shared" in result["raters_thin"]["ad_fontes"]
    assert not result["gate_passed"]


def test_repair_adopts_orphans_visibly():
    conn = db.connect(":memory:")
    db.insert_article(
        conn, outlet="x", url="https://x.com/1", title="T", published=None,
        fetched_at="2026-07-10T00:00:00+00:00", summary=None, text="b",
    )
    conn.commit()  # committed around the chain: the orphan case
    assert any("outside the custody chain" in p for p in db.verify_contents(conn))
    entry = db.custody_adopt_orphans(conn)
    assert entry["n_items"] == 1
    kind = conn.execute("SELECT kind FROM custody_log WHERE seq = ?", (entry["seq"],))
    assert kind.fetchone()[0] == "adopt", "adoption must be visible in the chain"
    assert db.verify_contents(conn) == []
    assert db.custody_verify(conn) == []


def test_snapshot_fails_loudly_on_missing_content(tmp_path):
    from tiltmeter import snapshot

    conn = db.connect(tmp_path / "s.db")
    h = db.insert_article(
        conn, outlet="x", url="https://x.com/1", title="T", published=None,
        fetched_at="2026-07-10T00:00:00+00:00", summary=None, text="b",
    )
    db.custody_append(conn, "ingest", [h])
    conn.commit()
    conn.close()
    raw = __import__("sqlite3").connect(tmp_path / "s.db")  # tamperer: no FK pragma
    raw.execute("DELETE FROM contents WHERE content_hash = ?", (h,))
    raw.commit()
    raw.close()
    with pytest.raises(RuntimeError, match="store is"):
        snapshot.create(db.connect(tmp_path / "s.db"), "2026-07-10", "2026-07-11", "x")


def test_cached_embed_never_commits_inside_a_callers_batch(monkeypatch):
    """Embedding mid-collection must not commit the half-collected batch."""
    conn = db.connect(":memory:")
    monkeypatch.setattr(embed, "embed_texts",
                        lambda texts: np.zeros((len(texts), 4), dtype=np.float32))
    conn.execute("BEGIN")
    conn.execute("INSERT INTO outlets (name, first_seen) VALUES ('x', 't')")
    embed.cached_embed(conn, ["some text"])
    assert conn.in_transaction, "cached_embed must not have committed the batch"
    conn.rollback()
    assert conn.execute("SELECT COUNT(*) FROM outlets").fetchone()[0] == 0


def test_artifact_bytes_are_platform_pinned(tmp_path):
    """Sorted keys, UTF-8, no ASCII escaping: same payload, same bytes."""
    payload = {"z": "curly ’quotes’ and — dashes", "a": 1}
    p1 = artifacts.write_json(tmp_path / "one.json", payload)
    p2 = artifacts.write_json(tmp_path / "two.json", dict(reversed(payload.items())))
    assert p1.read_bytes() == p2.read_bytes()
    assert "’".encode() in p1.read_bytes(), "non-ASCII must not be escaped"
    assert p1.read_bytes().index(b'"a"') < p1.read_bytes().index(b'"z"')


def test_write_json_atomic_never_leaves_a_partial_target(tmp_path, monkeypatch):
    """A crash mid-write must never truncate the previous artifact in place —
    serve.py reads this same file from a separate process, concurrently."""
    target = tmp_path / "ratings-x.json"
    artifacts.write_json(target, {"a": 1})
    original = target.read_bytes()

    def boom(*a, **k):
        raise RuntimeError("simulated crash mid-write")

    monkeypatch.setattr(artifacts.os, "replace", boom)
    with pytest.raises(RuntimeError, match="simulated"):
        artifacts.write_json(target, {"a": 2, "b": "x" * 1000})
    assert target.read_bytes() == original, "target must be untouched until the atomic swap"
    assert list(tmp_path.iterdir()) == [target], "a failed write must not leak a temp file"


def test_embedding_cache_key_carries_model_revision():
    """A revision bump must miss the cache, never serve stale vectors."""
    assert embed.MODEL_REVISION in embed.CACHE_MODEL_KEY
    assert embed.MODEL_NAME in embed.CACHE_MODEL_KEY


def test_dockerfile_model_pins_match_code():
    """The baked-model ARGs must track embed.py or offline runs use the wrong pin."""
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    name = re.search(r"ARG EMBED_MODEL=(\S+)", dockerfile).group(1)
    revision = re.search(r"ARG EMBED_REVISION=(\S+)", dockerfile).group(1)
    assert name == embed.MODEL_NAME
    assert revision == embed.MODEL_REVISION


def test_version_matches_pyproject():
    """__version__ is stamped into every ratings/manifest as pipeline_version;
    a pyproject bump that leaves it behind ships artifacts under the wrong
    version."""
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    version = re.search(r'(?m)^version = "([^"]+)"', pyproject).group(1)
    assert tiltmeter.__version__ == version


def test_serve_routes_cover_every_artifact_kind():
    """A new artifact kind must be servable by construction, not by memory."""
    source = (ROOT / "src/tiltmeter/serve.py").read_text(encoding="utf-8")
    assert "kind in KINDS" in source, "artifact routes must come from artifacts.KINDS"
    # the generic arm makes per-kind arms unnecessary; ensure none regressed in
    assert source.count("SNAPSHOT_ID_RE.match(sid)") <= 3  # generic + evidence pair
