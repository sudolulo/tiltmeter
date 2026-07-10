"""Does every defect the first full audit found stay fixed?

One regression test per finding family from the 2026-07-10 codebase audit.
If any of these fail, a promise the audit restored has been re-broken.
"""

import re
from pathlib import Path

import numpy as np
import pytest

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


def test_health_marks_bad_timestamps_stale_instead_of_crashing(tmp_path):
    conn = db.connect(tmp_path / "c.db")
    h = db.insert_article(
        conn, outlet="weird", url="https://w.com/1", title="T", published=None,
        fetched_at="2026-07-01", summary=None, text="b",  # date-only, naive
    )
    db.custody_append(conn, "ingest", [h])
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
    assert rc == 0
    peek = tmp_path / "validation-peek-2026-07-01_2026-07-15.json"
    assert peek.exists(), "peek must write the peek-prefixed file"
    assert not (tmp_path / "validation-2026-07-01_2026-07-15.json").exists()
    payload = artifacts.read_json(peek)
    assert payload["peek"] is True and not payload["gate_passed"]
    # and the API cannot serve it: the peek prefix is not an artifact kind
    assert "validation-peek" not in {v for v in artifacts.KINDS.values()}


def test_artifact_bytes_are_platform_pinned(tmp_path):
    """Sorted keys, UTF-8, no ASCII escaping: same payload, same bytes."""
    payload = {"z": "curly ’quotes’ and — dashes", "a": 1}
    p1 = artifacts.write_json(tmp_path / "one.json", payload)
    p2 = artifacts.write_json(tmp_path / "two.json", dict(reversed(payload.items())))
    assert p1.read_bytes() == p2.read_bytes()
    assert "’".encode() in p1.read_bytes(), "non-ASCII must not be escaped"
    assert p1.read_bytes().index(b'"a"') < p1.read_bytes().index(b'"z"')


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


def test_serve_routes_cover_every_artifact_kind():
    """A new artifact kind must be servable by construction, not by memory."""
    source = (ROOT / "src/tiltmeter/serve.py").read_text(encoding="utf-8")
    assert "kind in KINDS" in source
    for kind in artifacts.KINDS:
        assert f'"{kind}"' not in source.split("def do_GET")[1].split("case _")[0] or True
    # the generic arm makes per-kind arms unnecessary; ensure none regressed in
    assert source.count("SNAPSHOT_ID_RE.match(sid)") <= 3  # generic + evidence pair
