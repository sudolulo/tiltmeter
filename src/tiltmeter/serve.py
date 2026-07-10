"""How does other software get the numbers?

tiltmeter is a data layer: it computes ratings; separate software visualizes
them. This module is the delivery end — a small, read-only HTTP API over the
releases directory. No framework, no state, no writes: every response is a
file the pipeline already produced, so serving adds nothing to audit.

  GET /health                      liveness + what's available
  GET /outlets                     outlet list incl. sourced ownership data
  GET /ratings                     list of snapshot ids with ratings
  GET /ratings/latest              newest ratings.json
  GET /ratings/{snapshot_id}       specific ratings.json
  GET /stories/{snapshot_id}       story clusters: who covered what, headlines
  GET /manifests/{snapshot_id}     corpus manifest (for verifiers)
  GET /evidence/{snapshot_id}/     evidence index + per-outlet pages

CORS is wide open: the data is public and consumers are other people's
frontends. Snapshot ids sort lexicographically by date, so "latest" is just
the maximum.
"""

import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

log = logging.getLogger("tiltmeter.serve")

SNAPSHOT_ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{4}-\d{2}-\d{2}$")
OUTLET_PAGE_RE = re.compile(r"^[a-z0-9-]+\.md$|^index\.md$")
DEFAULT_PORT = 8477
STALE_AFTER_HOURS = 36.0  # two missed 6h collection cycles plus slack


def collection_health(db_path: Path, configured: list[str] | None = None) -> dict | None:
    """Hours since each outlet last yielded an article — the monitoring hook.

    A silently dead feed is the main way two unattended weeks go wrong; this
    makes it one HTTP request to notice. Only *configured* outlets count:
    outlets retired from config must not alarm forever, and configured
    outlets with no articles at all are exactly the dead-feed case (reported
    as null hours and stale). Returns None when no corpus exists.
    """
    if not db_path.is_file():
        return None
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT outlet, MAX(fetched_at) FROM articles GROUP BY outlet"
        ).fetchall()
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()
    now = datetime.now(timezone.utc)
    hours: dict[str, float | None] = {
        outlet: round((now - datetime.fromisoformat(ts)).total_seconds() / 3600, 1)
        for outlet, ts in rows
        if ts
    }
    if configured is not None:
        hours = {o: hours.get(o) for o in configured}
    return {
        "hours_since_last_article": dict(sorted(hours.items())),
        "stale_outlets": sorted(
            o for o, h in hours.items() if h is None or h > STALE_AFTER_HOURS
        ),
    }


def _ratings_ids(releases: Path) -> list[str]:
    return sorted(
        p.stem.removeprefix("ratings-") for p in releases.glob("ratings-*.json")
    )


def make_handler(releases: Path, outlets_config: Path | None = None, db_path: Path | None = None):
    outlets_payload = None
    configured_names: list[str] | None = None
    if outlets_config and outlets_config.is_file():
        import yaml

        outlets_payload = {"outlets": yaml.safe_load(outlets_config.read_text())["outlets"]}
        configured_names = [o["name"] for o in outlets_payload["outlets"]]

    class Handler(BaseHTTPRequestHandler):
        server_version = "tiltmeter"

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "public, max-age=300")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, payload) -> None:
            # default=str: YAML loads unquoted dates as date objects; a payload
            # must never be able to crash the response mid-flight
            self._send(code, json.dumps(payload, default=str).encode(), "application/json")

        def _file(self, path: Path, content_type: str) -> None:
            if path.is_file():
                self._send(200, path.read_bytes(), content_type)
            else:
                self._json(404, {"error": "not found"})

        def do_GET(self) -> None:  # noqa: N802 - stdlib API
            parts = [p for p in self.path.split("?")[0].split("/") if p]
            ids = _ratings_ids(releases)
            match parts:
                case ["health"]:
                    payload = {"status": "ok", "ratings": ids}
                    if db_path is not None:
                        payload["collection"] = collection_health(db_path, configured_names)
                        if payload["collection"] and payload["collection"]["stale_outlets"]:
                            payload["status"] = "degraded"
                    self._json(200, payload)
                case ["ratings"]:
                    self._json(200, {"snapshots": ids})
                case ["ratings", "latest"] if ids:
                    self._file(releases / f"ratings-{ids[-1]}.json", "application/json")
                case ["ratings", sid] if SNAPSHOT_ID_RE.match(sid):
                    self._file(releases / f"ratings-{sid}.json", "application/json")
                case ["outlets"] if outlets_payload:
                    self._json(200, outlets_payload)
                case ["stories", sid] if SNAPSHOT_ID_RE.match(sid):
                    self._file(releases / f"stories-{sid}.json", "application/json")
                case ["validation", sid] if SNAPSHOT_ID_RE.match(sid):
                    self._file(releases / f"validation-{sid}.json", "application/json")
                case ["sweeps", sid] if SNAPSHOT_ID_RE.match(sid):
                    self._file(releases / f"sweep-{sid}.json", "application/json")
                case ["manifests", sid] if SNAPSHOT_ID_RE.match(sid):
                    self._file(releases / f"manifest-{sid}.json", "application/json")
                case ["evidence", sid] if SNAPSHOT_ID_RE.match(sid):
                    self._file(releases / f"report-{sid}" / "index.md", "text/markdown")
                case ["evidence", sid, page] if (
                    SNAPSHOT_ID_RE.match(sid) and OUTLET_PAGE_RE.match(page)
                ):
                    self._file(releases / f"report-{sid}" / page, "text/markdown")
                case _:
                    self._json(404, {"error": "not found"})

        def log_message(self, fmt: str, *args) -> None:
            log.info("%s %s", self.address_string(), fmt % args)

    return Handler


def run(
    releases_dir: str | Path,
    host: str = "0.0.0.0",
    port: int = DEFAULT_PORT,
    outlets_config: str | Path = "config/outlets.yaml",
    db_path: str | Path = "data/tiltmeter.db",
) -> None:
    releases = Path(releases_dir)
    server = ThreadingHTTPServer(
        (host, port), make_handler(releases, Path(outlets_config), Path(db_path))
    )
    log.info("serving %s on %s:%d", releases, host, port)
    server.serve_forever()
