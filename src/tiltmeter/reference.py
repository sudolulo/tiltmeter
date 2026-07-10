"""What does each party's language actually sound like?

The axis orientation anchor (METHODOLOGY.md D5): floor speeches from the
Congressional Record, each attributed to a speaker and joined to their party
via voteview.com's member data. Party membership is a public record — this
module contains no judgment about anyone's politics, it only records who
said what and which party they belong to.

Sources, both keyless and pinned by URL pattern:
- Daily Congressional Record packages: govinfo.gov/content/pkg/CREC-YYYY-MM-DD.zip
  (US government work, public domain). Recess days simply don't exist; we skip them.
- Member party + DW-NOMINATE: voteview.com HSall-style member CSVs per congress.

Scope choices (documented, revisitable via ADR): House and Senate floor
granules only — Extensions of Remarks are written insertions, not floor
speech; Daily Digest is a summary. Speeches whose speaker can't be matched
unambiguously to one member are dropped, not guessed.
"""

import csv
import io
import logging
import re
import sqlite3
import zipfile
from datetime import date, timedelta

import requests

log = logging.getLogger("tiltmeter.reference")

CREC_URL = "https://www.govinfo.gov/content/pkg/CREC-{day}.zip"
VOTEVIEW_URL = "https://voteview.com/static/data/out/members/{chamber}{congress}_members.csv"
USER_AGENT = "tiltmeter/0.1 (+https://github.com/sudolulo/tiltmeter; reference corpus builder)"
PARTY_CODES = {"100": "D", "200": "R"}  # others (independents etc.) are dropped
MIN_SPEECH_WORDS = 50  # procedural one-liners carry no party language signal

SCHEMA = """
CREATE TABLE IF NOT EXISTS reference_speeches (
    id INTEGER PRIMARY KEY,
    day TEXT NOT NULL,
    granule TEXT NOT NULL,
    chamber TEXT NOT NULL,
    speaker TEXT NOT NULL,
    state TEXT,
    party TEXT NOT NULL,
    text TEXT NOT NULL,
    UNIQUE (granule, speaker, text)
);
"""

# "  Mr. GREEN of Texas. ..." / "  Ms. PELOSI. ..." — surname in caps is what
# distinguishes a speech opening from a prose mention ("Mr. Green of Texas was
# recognized"). McCONNELL-style internal lowercase is allowed; procedural
# roles ("The SPEAKER pro tempore.") never match the Mr/Ms/Mrs prefix.
SPEAKER_RE = re.compile(
    r"^ {1,4}(?:Mr|Ms|Mrs|Miss)\. "
    r"(?P<name>(?:Mc|Mac)?[A-Z][A-Za-z'\-]*[A-Z](?: (?:Mc|Mac)?[A-Z][A-Za-z'\-]*[A-Z])*)"
    r"(?: of (?P<state>[A-Z][a-z]+(?: [A-Z][a-z]+)?))?\. ",
    re.MULTILINE,
)
PAGE_MARKER_RE = re.compile(r"\[\[Page [HSED]?\d+\]\]")
TAG_RE = re.compile(r"<[^>]+>")

STATE_ABBREV = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY",
}


def load_members(congress: int, session: requests.Session | None = None) -> dict:
    """Party lookup from voteview: {(chamber, SURNAME): {(state, party), ...}}."""
    http = session or requests.Session()
    lookup: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for chamber_code, chamber in (("H", "House"), ("S", "Senate")):
        url = VOTEVIEW_URL.format(chamber=chamber_code, congress=congress)
        resp = http.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
        resp.raise_for_status()
        for row in csv.DictReader(io.StringIO(resp.text)):
            if row.get("chamber") == "President":
                continue
            party = PARTY_CODES.get(row["party_code"])
            if party is None:
                continue
            surname = row["bioname"].split(",")[0].strip().upper()
            lookup.setdefault((chamber, surname), set()).add(
                (row["state_abbrev"], party)
            )
    return lookup


def match_party(
    lookup: dict, chamber: str, surname: str, state_name: str | None
) -> str | None:
    """One unambiguous member ⇒ their party; anything else ⇒ None (drop)."""
    candidates = lookup.get((chamber, surname.upper()), set())
    if state_name is not None:
        abbrev = STATE_ABBREV.get(state_name)
        candidates = {(s, p) for s, p in candidates if s == abbrev}
    parties = {p for _, p in candidates}
    if len(candidates) == 1 or len(parties) == 1 and candidates:
        return parties.pop()
    return None


def parse_granule(html: str) -> list[dict]:
    """Split one floor granule into speeches: speaker, state, text."""
    body = TAG_RE.sub("", html)
    body = PAGE_MARKER_RE.sub("", body)
    matches = list(SPEAKER_RE.finditer(body))
    speeches = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        text = " ".join(body[m.end():end].split())
        if len(text.split()) >= MIN_SPEECH_WORDS:
            speeches.append(
                {"speaker": m.group("name"), "state": m.group("state"), "text": text}
            )
    return speeches


def fetch_day(day: str, session: requests.Session | None = None) -> bytes | None:
    """One day's CREC zip, or None on recess/missing days."""
    http = session or requests.Session()
    resp = http.get(
        CREC_URL.format(day=day),
        headers={"User-Agent": USER_AGENT},
        timeout=120,
        allow_redirects=True,
    )
    if resp.status_code != 200 or "zip" not in resp.headers.get("content-type", ""):
        return None
    return resp.content


def ingest_day(conn: sqlite3.Connection, day: str, zip_bytes: bytes, members: dict) -> dict:
    """Parse one day's floor granules into reference_speeches. Returns counts."""
    conn.executescript(SCHEMA)
    counts = {"speeches": 0, "unmatched": 0}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in sorted(zf.namelist()):
            m = re.search(r"-Pg([HS])", name)
            if not name.endswith(".htm") or not m:
                continue  # Daily Digest, Extensions, front matter
            chamber = "House" if m.group(1) == "H" else "Senate"
            html = zf.read(name).decode("utf-8", errors="replace")
            for speech in parse_granule(html):
                party = match_party(members, chamber, speech["speaker"], speech["state"])
                if party is None:
                    counts["unmatched"] += 1
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO reference_speeches"
                    " (day, granule, chamber, speaker, state, party, text)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (day, name.rsplit("/", 1)[-1], chamber, speech["speaker"],
                     speech["state"], party, speech["text"]),
                )
                counts["speeches"] += 1
    conn.commit()
    return counts


def fetch_range(conn: sqlite3.Connection, end_day: str, session_days: int, congress: int) -> dict:
    """Walk back from end_day until `session_days` days with a Record are ingested."""
    members = load_members(congress)
    http = requests.Session()
    totals = {"days": 0, "speeches": 0, "unmatched": 0, "skipped": 0}
    cursor = date.fromisoformat(end_day)
    attempts = 0
    while totals["days"] < session_days and attempts < session_days * 5:
        attempts += 1
        day = cursor.isoformat()
        cursor -= timedelta(days=1)
        already = conn.execute(
            "SELECT 1 FROM reference_speeches WHERE day = ? LIMIT 1", (day,)
        ).fetchone() if conn.execute(
            "SELECT name FROM sqlite_master WHERE name='reference_speeches'"
        ).fetchone() else None
        if already:
            totals["days"] += 1
            continue
        zip_bytes = fetch_day(day, http)
        if zip_bytes is None:
            totals["skipped"] += 1
            log.info("%s: no Record (recess/weekend)", day)
            continue
        counts = ingest_day(conn, day, zip_bytes, members)
        totals["days"] += 1
        totals["speeches"] += counts["speeches"]
        totals["unmatched"] += counts["unmatched"]
        log.info("%s: %d speeches (%d unmatched)", day, counts["speeches"], counts["unmatched"])
    return totals
