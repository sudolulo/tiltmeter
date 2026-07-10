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
    outlets.write_text(
        "outlets:\n"
        "  - name: fox-news\n"
        "    homepage: https://www.foxnews.com\n"
        "    feed: https://example.com/feed\n"
        "    ownership: {owner: Fox Corporation, type: public-company}\n"
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
