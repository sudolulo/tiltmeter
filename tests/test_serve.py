"""Does the API serve exactly what the pipeline produced — and nothing else?

Spins the real server on an ephemeral port over a fixture releases dir.
The contract: pipeline outputs are served verbatim, unknown paths 404,
path traversal is impossible by construction (strict id/page regexes).
"""

import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from tiltmeter import serve


@pytest.fixture()
def api(tmp_path):
    (tmp_path / "ratings-2026-07-01_2026-07-15.json").write_text('{"snapshot_id": "old"}')
    (tmp_path / "ratings-2026-07-10_2026-07-24.json").write_text('{"snapshot_id": "new"}')
    (tmp_path / "manifest-2026-07-10_2026-07-24.json").write_text('{"articles": []}')
    (tmp_path / "stories-2026-07-10_2026-07-24.json").write_text('{"stories": []}')
    report = tmp_path / "report-2026-07-10_2026-07-24"
    report.mkdir()
    (report / "index.md").write_text("# Evidence index")
    (report / "fox-news.md").write_text("# Evidence: fox-news")
    outlets = tmp_path / "outlets.yaml"
    # retrieved is deliberately an unquoted YAML date: it loads as a Python
    # date object, and serialization must survive that (it once didn't)
    outlets.write_text(
        "outlets:\n"
        "  - name: fox-news\n"
        "    homepage: https://www.foxnews.com\n"
        "    feed: https://example.com/feed\n"
        "    ownership: {owner: Fox Corporation, type: public-company,\n"
        "                retrieved: 2026-07-10, verified: true}\n"
    )

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), serve.make_handler(tmp_path, outlets)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()


def get(port, path):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", path)
    resp = conn.getresponse()
    return resp.status, resp.read(), dict(resp.getheaders())


def test_health_and_listing(api):
    status, body, headers = get(api, "/health")
    assert status == 200
    assert json.loads(body)["ratings"] == [
        "2026-07-01_2026-07-15",
        "2026-07-10_2026-07-24",
    ]
    assert headers["Access-Control-Allow-Origin"] == "*"


def test_health_reports_stale_outlets(tmp_path):
    """A feed that quietly dies must show up as degraded within one request."""
    from datetime import datetime, timedelta, timezone

    from tiltmeter import db as tdb

    conn = tdb.connect(tmp_path / "corpus.db")
    now = datetime.now(timezone.utc)
    for outlet, age_hours in (("fresh-news", 2), ("dead-feed", 90)):
        tdb.insert_article(
            conn,
            outlet=outlet,
            url=f"https://example.com/{outlet}",
            title="T",
            published=None,
            fetched_at=(now - timedelta(hours=age_hours)).isoformat(),
            summary=None,
            text="x",
        )
    conn.commit()

    health = serve.collection_health(tmp_path / "corpus.db")
    assert health["stale_outlets"] == ["dead-feed"]
    assert health["hours_since_last_article"]["fresh-news"] < 3

    # retired outlets must not alarm forever; configured-but-never-collected
    # outlets are the bootstrap dead-feed case and must alarm immediately
    scoped = serve.collection_health(
        tmp_path / "corpus.db", configured=["fresh-news", "brand-new"]
    )
    assert scoped["stale_outlets"] == ["brand-new"]
    assert "dead-feed" not in scoped["hours_since_last_article"]
    assert scoped["hours_since_last_article"]["brand-new"] is None

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        serve.make_handler(tmp_path, None, tmp_path / "corpus.db"),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, body, _ = get(server.server_address[1], "/health")
        payload = json.loads(body)
        assert payload["status"] == "degraded"
        assert payload["collection"]["stale_outlets"] == ["dead-feed"]
    finally:
        server.shutdown()


def test_latest_is_newest_snapshot(api):
    status, body, _ = get(api, "/ratings/latest")
    assert status == 200
    assert json.loads(body)["snapshot_id"] == "new"


def test_specific_ratings_manifest_and_evidence(api):
    assert json.loads(get(api, "/ratings/2026-07-01_2026-07-15")[1])["snapshot_id"] == "old"
    assert get(api, "/manifests/2026-07-10_2026-07-24")[0] == 200
    assert b"Evidence index" in get(api, "/evidence/2026-07-10_2026-07-24")[1]
    assert b"fox-news" in get(api, "/evidence/2026-07-10_2026-07-24/fox-news.md")[1]


def test_outlets_and_stories_endpoints(api):
    status, body, _ = get(api, "/outlets")
    assert status == 200
    outlet = json.loads(body)["outlets"][0]
    assert outlet["ownership"]["owner"] == "Fox Corporation"
    assert json.loads(get(api, "/stories/2026-07-10_2026-07-24")[1]) == {"stories": []}
    assert get(api, "/stories/nonsense")[0] == 404


def test_unknown_and_hostile_paths_404(api):
    assert get(api, "/ratings/nonsense")[0] == 404
    assert get(api, "/evidence/2026-07-10_2026-07-24/../../etc/passwd")[0] == 404
    assert get(api, "/evidence/2026-07-10_2026-07-24/%2e%2e%2fsecrets.md")[0] == 404
    assert get(api, "/")[0] == 404
