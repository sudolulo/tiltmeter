"""Do the docs keep the promises the README makes?

These tests are the enforcement arm of the auditability contract:
- the plain-language walkthrough stays at or below a grade-10 reading level
- every required jargon term has a glossary entry, and no glossary entry is dead
- every METHODOLOGY decision block carries its four mandatory fields
- decision records (ADRs) are sequential and complete
- the generated outlets table matches the config it is generated from
"""

import re
from pathlib import Path

import textstat

ROOT = Path(__file__).resolve().parent.parent
HOW_IT_WORKS = ROOT / "docs" / "how-it-works.md"
GLOSSARY = ROOT / "docs" / "glossary.md"
METHODOLOGY = ROOT / "METHODOLOGY.md"
DECISIONS = ROOT / "docs" / "decisions"

MAX_GRADE = 10.0


def strip_markdown(text: str) -> str:
    text = re.sub(r"\]\([^)]*\)", "]", text)  # link targets are not prose
    text = re.sub(r"<https?://[^>]*>", "", text)
    return re.sub(r"[#*`>\[\]]", "", text)


def test_how_it_works_readability():
    grade = textstat.flesch_kincaid_grade(strip_markdown(HOW_IT_WORKS.read_text()))
    assert grade <= MAX_GRADE, (
        f"docs/how-it-works.md reads at grade {grade:.1f}, above the promised "
        f"grade-{MAX_GRADE:.0f} ceiling. Shorten sentences, use simpler words."
    )


# Jargon that project docs are allowed to use only because the glossary defines it.
# Add a term here whenever a new one enters the docs.
REQUIRED_GLOSSARY_TERMS = [
    "RSS feed",
    "Corpus",
    "Snapshot",
    "Fingerprint (hash)",
    "Manifest",
    "Embedding",
    "Clustering",
    "Story cluster",
    "Coverage matrix",
    "Correspondence analysis",
    "Principal axis",
    "Anchor",
    "DW-NOMINATE",
    "Bootstrap",
    "Confidence interval",
    "Spearman rank correlation",
    "Sensitivity analysis",
    "Tunable",
    "ADR (decision record)",
    "SemVer (semantic versioning)",
    "Reproducibility",
    "Ideal-point estimation",
    "Lede",
    "Content-addressed storage",
    "Custody chain",
    "Append-only",
    "Byline",
]


def test_glossary_has_no_duplicate_entries():
    terms = glossary_terms()
    dupes = {t for t in terms if terms.count(t) > 1}
    assert not dupes, f"glossary defines these more than once: {sorted(dupes)}"


def glossary_terms() -> list[str]:
    return re.findall(r"^### (.+)$", GLOSSARY.read_text(), flags=re.MULTILINE)


def test_glossary_covers_required_terms():
    missing = set(REQUIRED_GLOSSARY_TERMS) - set(glossary_terms())
    assert not missing, f"glossary is missing required terms: {sorted(missing)}"


def test_glossary_has_no_dead_entries():
    """Every glossary entry must actually be used somewhere in the docs."""
    docs_text = " ".join(
        p.read_text().lower()
        for p in [
            HOW_IT_WORKS,
            METHODOLOGY,
            ROOT / "README.md",
            ROOT / "CHANGELOG.md",
            ROOT / "docs" / "research.md",
        ]
    )
    dead = []
    for term in glossary_terms():
        # match on the head word(s) before any parenthetical, e.g. "Fingerprint (hash)"
        head = re.sub(r"\s*\(.*\)$", "", term).lower()
        stem = head[:-1] if head.endswith("y") else head  # reproducibility/reproducible
        if stem not in docs_text:
            dead.append(term)
    assert not dead, f"glossary entries never used in any doc: {dead}"


DECISION_FIELDS = ["**Decision**", "**Rationale**", "**Alternatives considered**",
                   "**Failure modes**"]


def test_methodology_decision_blocks_complete():
    text = METHODOLOGY.read_text()
    blocks = re.split(r"^## D(\d+)\. ", text, flags=re.MULTILINE)
    assert len(blocks) > 1, "METHODOLOGY.md contains no decision blocks"
    numbers = [int(n) for n in blocks[1::2]]
    assert numbers == list(range(1, len(numbers) + 1)), (
        f"decision blocks must be numbered sequentially from D1, got {numbers}"
    )
    for number, body in zip(blocks[1::2], blocks[2::2]):
        missing = [f for f in DECISION_FIELDS if f not in body]
        assert not missing, f"METHODOLOGY.md D{number} is missing fields: {missing}"


ADR_SECTIONS = ["## Decision", "## Rationale", "## Alternatives considered", "## Failure modes"]
ADR_METADATA = ["**Status**", "**Date**", "**Supersedes**"]


def test_adrs_sequential_and_complete():
    adrs = sorted(DECISIONS.glob("*.md"))
    assert adrs, "docs/decisions/ contains no decision records"
    numbers = []
    for path in adrs:
        m = re.match(r"^(\d{4})-[a-z0-9-]+\.md$", path.name)
        assert m, f"ADR filename must be NNNN-kebab-title.md, got {path.name}"
        numbers.append(int(m.group(1)))
        text = path.read_text()
        for section in ADR_SECTIONS:
            assert re.search(f"^{re.escape(section)}", text, flags=re.MULTILINE), (
                f"{path.name} is missing a section starting with '{section}'"
            )
        for field in ADR_METADATA:
            assert field in text, f"{path.name} is missing metadata field {field}"
    assert numbers == list(range(1, len(numbers) + 1)), (
        f"ADRs must be numbered sequentially from 0001, got {numbers}"
    )


def test_outlets_doc_in_sync_with_config():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "gen_outlets_doc", ROOT / "scripts" / "gen_outlets_doc.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    committed = (ROOT / "docs" / "outlets.md").read_text()
    assert committed == mod.render(), (
        "docs/outlets.md is stale. Regenerate: uv run python scripts/gen_outlets_doc.py"
    )
