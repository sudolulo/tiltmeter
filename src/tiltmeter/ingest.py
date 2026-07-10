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
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import trafilatura
import yaml
from trafilatura.settings import use_config

from tiltmeter import db

# Query parameters that vary per-reader without changing the article: keeping
# them would store the same piece many times under different URLs and muddy
# the custody trail.
TRACKING_PARAMS = ("utm_", "fbclid", "gclid", "mc_cid", "mc_eid", "cmpid", "ref")
_TAG_RE = None  # compiled lazily


def strip_html(value: str | None) -> str | None:
    """Feed summaries arrive full of outlet boilerplate markup; store prose."""
    global _TAG_RE
    if not value:
        return None
    if _TAG_RE is None:
        import re

        _TAG_RE = re.compile(r"<[^>]+>")
    plain = " ".join(_TAG_RE.sub(" ", value).split())
    return plain or None


def canonical_url(url: str) -> str:
    """Strip fragments and tracking parameters; the dedup and custody key."""
    parts = urlsplit(url)
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.startswith(TRACKING_PARAMS[0]) and k not in TRACKING_PARAMS[1:]
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))

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


def ingest_outlet(conn, outlet: dict, *, fetch_text: bool = True) -> tuple[int, list[str]]:
    """Poll one outlet's feed; store unseen articles. Returns (seen, new hashes)."""
    parsed = feedparser.parse(outlet["feed"], agent=USER_AGENT)
    now = datetime.now(timezone.utc).isoformat()
    seen, new_hashes = 0, []
    for entry in parsed.entries:
        raw_url = entry.get("link")
        title = (entry.get("title") or "").strip()
        if not raw_url or not title:
            continue
        seen += 1
        url = canonical_url(raw_url)
        if db.have_url(conn, url):
            continue
        text = None
        if fetch_text:
            try:
                text = fetch_article_text(raw_url)
            except Exception as exc:  # noqa: BLE001 - one bad page must not stop the run
                log.warning("text fetch failed for %s: %s", raw_url, exc)
            time.sleep(FETCH_DELAY_SECONDS)
        chash = db.insert_article(
            conn,
            outlet=outlet["name"],
            url=url,
            url_original=raw_url if raw_url != url else None,
            title=title,
            byline=(entry.get("author") or "").strip() or None,
            published=entry.get("published") or entry.get("updated"),
            fetched_at=now,
            summary=strip_html(entry.get("summary")),
            text=text,
        )
        if chash:
            new_hashes.append(chash)
    conn.commit()
    return seen, new_hashes


def ingest_all(config_path: str, db_path: str, *, fetch_text: bool = True) -> list[dict]:
    """Poll every configured outlet once; chain the batch into the custody
    log. Returns a per-outlet result report."""
    conn = db.connect(db_path)
    results = []
    run_hashes: list[str] = []
    for outlet in load_outlets(config_path):
        try:
            seen, new_hashes = ingest_outlet(conn, outlet, fetch_text=fetch_text)
            run_hashes.extend(new_hashes)
            results.append({"outlet": outlet["name"], "seen": seen, "new": len(new_hashes)})
            log.info("%s: %d entries in feed, %d new", outlet["name"], seen, len(new_hashes))
        except Exception as exc:  # noqa: BLE001 - one bad feed must not stop the run
            results.append({"outlet": outlet["name"], "error": str(exc)})
            log.error("%s: feed failed: %s", outlet["name"], exc)
    entry = db.custody_append(conn, "ingest", run_hashes)
    if entry:
        log.info("custody: seq %d chains %d new items", entry["seq"], entry["n_items"])
    conn.close()
    return results
