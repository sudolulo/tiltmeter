"""What does each party's language actually sound like?

The axis orientation anchor (METHODOLOGY.md D5): floor speeches from the
Congressional Record, tagged by the speaker's party. Party membership comes
from voteview.com member data — public records, not ratings.

Sources, both fetchable without keys or accounts:
- govinfo.gov daily-issue zips: CREC-YYYY-MM-DD.zip (HTM granules inside).
  Days Congress wasn't in session return an HTML page, not a zip — skipped.
- voteview HSall members CSV: bioname, state, chamber, party per congress.

Speaker attribution is heuristic (surname headers like "Mr. THUNE." or
"Ms. DELBENE of Washington.") and deliberately conservative: a speech whose
speaker can't be matched to exactly one party is dropped. We need bulk party
language, not a perfect transcript.
"""

import csv
import io
import logging
import re
import sqlite3
import zipfile
from datetime import date, timedelta

import requests

from tiltmeter import db

log = logging.getLogger("tiltmeter.congress")

CREC_URL = "https://www.govinfo.gov/content/pkg/CREC-{day}.zip"
MEMBERS_URL = "https://voteview.com/static/data/out/members/HSall_members.csv"
PARTY_CODES = {"100": "D", "200": "R"}  # others (independents etc.) dropped
MIN_SPEECH_WORDS = 50  # ignore procedural one-liners

SCHEMA = """
CREATE TABLE IF NOT EXISTS ref_speeches (
    id INTEGER PRIMARY KEY,
    day TEXT NOT NULL,
    granule TEXT NOT NULL,
    speaker TEXT NOT NULL,
    party TEXT NOT NULL,
    text TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE
);
"""

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
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI",
    "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX",
    "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}

# "  Mr. THUNE." / "  Ms. DELBENE of Washington." / "  Mr. VAN HOLLEN. Mr. President,"
SPEAKER_RE = re.compile(
    r"^\s{1,4}(?:Mr|Mrs|Ms|Miss)\.\s+([A-Z][A-Z'\- ]{1,30}?)"
    r"(?:\s+of\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)?))?\.\s",
    re.MULTILINE,
)


def fetch_members(congress: int, session=None) -> dict:
    """Surname → chamber → set of (party, state) for one congress, from voteview."""
    http = session or requests
    text = http.get(MEMBERS_URL, timeout=120).text
    members: dict[str, dict[str, set[tuple[str, str]]]] = {}
    for row in csv.DictReader(io.StringIO(text)):
        if int(row["congress"]) != congress:
            continue
        party = PARTY_CODES.get(row["party_code"])
        if party is None:
            continue
        chamber = {"House": "H", "Senate": "S"}.get(row["chamber"])
        if chamber is None:
            continue
        surname = row["bioname"].split(",")[0].strip().upper()
        members.setdefault(surname, {}).setdefault(chamber, set()).add(
            (party, row["state_abbrev"])
        )
    return members


def resolve_party(
    members: dict, surname: str, chamber: str, state_name: str | None
) -> str | None:
    """One unambiguous party for this speaker, or None (dropped)."""
    candidates = members.get(surname, {}).get(chamber, set())
    if state_name:
        abbrev = STATE_ABBREV.get(state_name)
        candidates = {(p, s) for p, s in candidates if s == abbrev}
    parties = {p for p, _ in candidates}
    return parties.pop() if len(parties) == 1 else None


def _granule_chamber(name: str) -> str | None:
    """Floor granules only: PgH = House, PgS = Senate, PgE = Extensions (House)."""
    m = re.search(r"-Pg([HSE])", name)
    if m is None:
        return None
    return {"H": "H", "S": "S", "E": "H"}[m.group(1)]


def split_speeches(granule_text: str) -> list[tuple[str, str | None, str]]:
    """(surname, state or None, speech text) for each speaker turn in a granule."""
    text = re.sub(r"<[^>]+>", "", granule_text)  # granule HTM is text in <pre>
    hits = list(SPEAKER_RE.finditer(text))
    speeches = []
    for i, m in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(text)
        body = " ".join(text[m.end(): end].split())
        if len(body.split()) >= MIN_SPEECH_WORDS:
            speeches.append((m.group(1).strip(), m.group(2), body))
    return speeches


def fetch_day(day: str, session=None) -> bytes | None:
    """One day's CREC zip, or None if Congress wasn't in session."""
    http = session or requests
    resp = http.get(CREC_URL.format(day=day), timeout=300, allow_redirects=True)
    if resp.status_code != 200 or not resp.content.startswith(b"PK"):
        return None
    return resp.content


def ingest_range(
    conn: sqlite3.Connection, start: str, end: str, congress: int, session=None
) -> dict:
    """Fetch and store party-tagged speeches for [start, end]. Returns counts."""
    conn.executescript(SCHEMA)
    members = fetch_members(congress, session=session)
    counts = {"days_in_session": 0, "speeches": 0, "dropped_ambiguous": 0}
    day = date.fromisoformat(start)
    last = date.fromisoformat(end)
    while day <= last:
        blob = fetch_day(day.isoformat(), session=session)
        if blob is not None:
            counts["days_in_session"] += 1
            with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                for name in sorted(zf.namelist()):
                    chamber = _granule_chamber(name)
                    if chamber is None or not name.endswith(".htm"):
                        continue
                    for surname, state, body in split_speeches(
                        zf.read(name).decode("utf-8", errors="replace")
                    ):
                        party = resolve_party(members, surname, chamber, state)
                        if party is None:
                            counts["dropped_ambiguous"] += 1
                            continue
                        conn.execute(
                            "INSERT OR IGNORE INTO ref_speeches"
                            " (day, granule, speaker, party, text, content_hash)"
                            " VALUES (?, ?, ?, ?, ?, ?)",
                            (
                                day.isoformat(),
                                name.rsplit("/", 1)[-1],
                                surname,
                                party,
                                body,
                                db.content_hash(f"{day}|{surname}", body),
                            ),
                        )
                        counts["speeches"] += 1
            conn.commit()
            log.info("%s: in session, %d speeches so far", day, counts["speeches"])
        day += timedelta(days=1)
    return counts


def party_counts(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    """How much D vs R language do we hold? (Health check.)"""
    conn.executescript(SCHEMA)
    return conn.execute(
        "SELECT party, COUNT(*) FROM ref_speeches GROUP BY party ORDER BY party"
    ).fetchall()
