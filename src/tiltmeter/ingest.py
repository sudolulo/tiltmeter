"""Which articles did each outlet publish today?

This module polls each outlet's RSS feed (a machine-readable list of its
latest articles), fetches the full text of any article we haven't seen
before, and stores it. It never rates anything — it only collects, so that
every later step works from the same recorded evidence.

Politeness rules: we identify ourselves with an honest User-Agent, fetch each
article at most once ever (URLs are deduplicated), and pause between fetches.
"""

import ipaddress
import logging
import socket
import time
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import feedparser
import requests
import trafilatura
import yaml

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
# A feed entry's <link> is untrusted input. Cap manual redirect-following so a
# chain can't loop forever, and re-check the host at each hop (see below).
MAX_ARTICLE_REDIRECTS = 5


def load_outlets(config_path: str) -> list[dict]:
    """Read the outlet list (name, feed URL) from config/outlets.yaml."""
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    return cfg["outlets"]


def _reject_unroutable_host(host: str) -> None:
    """Refuse a host that resolves anywhere non-public.

    A feed is an outside party's input; its <link> could point at an
    internal address (cloud metadata, LAN service) to make us fetch it on
    the feed owner's behalf. Reject by resolved address, not by hostname
    pattern, since e.g. "localhost" is only one of many spellings.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ValueError(f"cannot resolve {host!r}: {exc}") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise ValueError(f"refusing to fetch {host!r}: resolves to {ip} (non-public)")


def fetch_article_text(url: str) -> str | None:
    """Download one article page and extract its readable text.

    Redirects are followed by hand, capped, and re-validated one hop at a
    time: an automatic redirect follower (trafilatura's, requests', any
    HTTP client's) would let a feed entry pass the host check and then
    bounce us to a private address on the next hop.
    """
    for _ in range(MAX_ARTICLE_REDIRECTS + 1):
        host = urlsplit(url).hostname
        if not host:
            return None
        _reject_unroutable_host(host)
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=FETCH_TIMEOUT_SECONDS,
            allow_redirects=False,
        )
        if resp.is_redirect:
            location = resp.headers.get("Location")
            if not location:
                return None
            url = urljoin(url, location)
            continue
        if resp.status_code != 200:
            return None
        return trafilatura.extract(resp.content, include_comments=False, include_tables=False)
    log.warning("too many redirects fetching %s", url)
    return None


def ingest_outlet(conn, outlet: dict, *, fetch_text: bool = True) -> tuple[int, list[str]]:
    """Poll one outlet's feed; store unseen articles and chain them, in one
    transaction. Returns (seen, new hashes).

    Rows and their custody entry become durable together or not at all: no
    commit happens between insert and chain, so no crash or bad feed entry
    can leave collected content outside the chain. A malformed entry is
    skipped, never allowed to abort the batch.
    """
    parsed = feedparser.parse(outlet["feed"], agent=USER_AGENT)
    now = datetime.now(timezone.utc).isoformat()
    seen, new_hashes = 0, []
    for entry in parsed.entries:
        try:
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
        except Exception as exc:  # noqa: BLE001 - one malformed entry must not orphan a batch
            log.warning("%s: skipping malformed feed entry: %s", outlet["name"], exc)
    entry = db.custody_append(conn, "ingest", new_hashes)
    conn.commit()
    if entry:
        log.info("%s: custody seq %d chains %d items", outlet["name"], entry["seq"],
                 entry["n_items"])
    return seen, new_hashes


def ingest_all(config_path: str, db_path: str, *, fetch_text: bool = True) -> list[dict]:
    """Poll every configured outlet once; each outlet's articles are chained
    and committed atomically. Returns a per-outlet result report."""
    conn = db.connect(db_path)
    results = []
    for outlet in load_outlets(config_path):
        try:
            seen, new_hashes = ingest_outlet(conn, outlet, fetch_text=fetch_text)
            results.append({"outlet": outlet["name"], "seen": seen, "new": len(new_hashes)})
            log.info("%s: %d entries in feed, %d new", outlet["name"], seen, len(new_hashes))
        except Exception as exc:  # noqa: BLE001 - one bad feed must not stop the run
            conn.rollback()  # nothing half-collected may leak into the next batch
            results.append({"outlet": outlet["name"], "error": str(exc)})
            log.error("%s: feed failed: %s", outlet["name"], exc)
    conn.close()
    return results
