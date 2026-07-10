"""Which articles did each outlet publish today?

This module polls each outlet's RSS feed (a machine-readable list of its
latest articles), fetches the full text of any article we haven't seen
before, and stores it. It never rates anything — it only collects, so that
every later step works from the same recorded evidence.

Politeness rules: we identify ourselves with an honest User-Agent, fetch each
article at most once ever (URLs are deduplicated), and pause between fetches.
"""

import logging
import time
from datetime import datetime, timezone

import feedparser
import trafilatura
import yaml
from trafilatura.settings import use_config

from tiltmeter import db

log = logging.getLogger("tiltmeter.ingest")

USER_AGENT = "tiltmeter/0.1 (+https://github.com/sudolulo/tiltmeter; research corpus builder)"
# Floor chosen to stay under WAF/rate-limit radar on a single domain; a block
# would cost us corpus coverage, which is worth more than ingest speed.
FETCH_DELAY_SECONDS = 0.2
# Outlets that block us (e.g. paywalled WaPo) time out; cap the wait so one
# blocked outlet can't stall a whole ingest run. Headline+summary still land.
FETCH_TIMEOUT_SECONDS = 10

_FETCH_CONFIG = use_config()
_FETCH_CONFIG.set("DEFAULT", "DOWNLOAD_TIMEOUT", str(FETCH_TIMEOUT_SECONDS))
_FETCH_CONFIG.set("DEFAULT", "USER_AGENTS", USER_AGENT)


def load_outlets(config_path: str) -> list[dict]:
    """Read the outlet list (name, feed URL) from config/outlets.yaml."""
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    return cfg["outlets"]


def fetch_article_text(url: str) -> str | None:
    """Download one article page and extract its readable text."""
    html = trafilatura.fetch_url(url, config=_FETCH_CONFIG)
    if html is None:
        return None
    return trafilatura.extract(html, include_comments=False, include_tables=False)


def ingest_outlet(conn, outlet: dict, *, fetch_text: bool = True) -> tuple[int, int]:
    """Poll one outlet's feed; store unseen articles. Returns (seen, new)."""
    parsed = feedparser.parse(outlet["feed"], agent=USER_AGENT)
    now = datetime.now(timezone.utc).isoformat()
    seen, new = 0, 0
    for entry in parsed.entries:
        url = entry.get("link")
        title = (entry.get("title") or "").strip()
        if not url or not title:
            continue
        seen += 1
        if db.have_url(conn, url):
            continue
        text = None
        if fetch_text:
            try:
                text = fetch_article_text(url)
            except Exception as exc:  # noqa: BLE001 - one bad page must not stop the run
                log.warning("text fetch failed for %s: %s", url, exc)
            time.sleep(FETCH_DELAY_SECONDS)
        db.insert_article(
            conn,
            outlet=outlet["name"],
            url=url,
            title=title,
            published=entry.get("published") or entry.get("updated"),
            fetched_at=now,
            summary=(entry.get("summary") or "").strip() or None,
            text=text,
        )
        new += 1
    conn.commit()
    return seen, new


def ingest_all(config_path: str, db_path: str, *, fetch_text: bool = True) -> list[dict]:
    """Poll every configured outlet once. Returns a per-outlet result report."""
    conn = db.connect(db_path)
    results = []
    for outlet in load_outlets(config_path):
        try:
            seen, new = ingest_outlet(conn, outlet, fetch_text=fetch_text)
            results.append({"outlet": outlet["name"], "seen": seen, "new": new})
            log.info("%s: %d entries in feed, %d new", outlet["name"], seen, new)
        except Exception as exc:  # noqa: BLE001 - one bad feed must not stop the run
            results.append({"outlet": outlet["name"], "error": str(exc)})
            log.error("%s: feed failed: %s", outlet["name"], exc)
    conn.close()
    return results
