"""Does the Congressional Record parser attribute speech to the right people?

Fixture built from real Record formatting (US government work, public
domain). No network: fetching is exercised by the live reference run; what
must never regress silently is attribution — text credited to the wrong
speaker or party would poison the orientation anchor.
"""

from tiltmeter import reference

FILLER = "policy " * 60  # parser drops speeches under MIN_SPEECH_WORDS words

GRANULE = f"""
<html><body><pre>
                          A DEBATE OF SOME KIND

  (Under the Speaker's announced policy of January 3, 2025, Mr. Green
of Texas was recognized for 60 minutes as the designee of the minority
leader.)
  Mr. GREEN of Texas. Mr. Speaker, I rise to speak about housing
{FILLER}
[[Page H4255]]
and that concludes the first point.
  Mr. McCONNELL. I thank the gentleman. On the matter of appropriations
{FILLER}
  Mr. SHORT. One sentence only.
  Ms. VAN DUYNE. Madam Speaker, on the subject of small business
{FILLER}
</pre></body></html>
"""


def members():
    # keys as load_members() builds them: chamber + fully-uppercased surname
    return {
        ("House", "GREEN"): {("TX", "D"), ("TN", "R")},  # two Greens: state required
        ("Senate", "MCCONNELL"): {("KY", "R")},
        ("House", "VAN DUYNE"): {("TX", "R")},
    }


def test_parse_extracts_speeches_and_speakers():
    speeches = reference.parse_granule(GRANULE)
    speakers = [(s["speaker"], s["state"]) for s in speeches]
    assert speakers == [
        ("GREEN", "Texas"),
        ("McCONNELL", None),
        ("VAN DUYNE", None),
    ]
    # prose mention "Mr. Green of Texas was recognized" must NOT open a speech
    assert all("was recognized" not in s["text"][:60] for s in speeches)
    # page markers stripped, short procedural interjections dropped
    assert all("[[Page" not in s["text"] for s in speeches)
    assert all(s["speaker"] != "SHORT" for s in speeches)


def test_party_match_requires_disambiguation():
    lookup = members()
    # two GREENs in the House with different parties: no state ⇒ drop
    assert reference.match_party(lookup, "House", "GREEN", None) is None
    assert reference.match_party(lookup, "House", "GREEN", "Texas") == "D"
    assert reference.match_party(lookup, "House", "GREEN", "Tennessee") == "R"
    assert reference.match_party(lookup, "Senate", "McCONNELL", None) == "R"
    # multi-word caps surname resolves
    assert reference.match_party(lookup, "House", "VAN DUYNE", None) == "R"
    # unknown speaker ⇒ drop, never guess
    assert reference.match_party(lookup, "House", "NOBODY", None) is None
