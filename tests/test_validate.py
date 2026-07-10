"""Is the gate math right, and does the gate refuse sloppy inputs?

Synthetic fixtures with known correlations. The two properties that must
never regress: perfect agreement and perfect disagreement produce ±1 with
tiny p-values, and unverified reference values are excluded by default —
a gate checked against unchecked data isn't a gate.
"""

import pytest

from tiltmeter import validate


def ratings(scores: dict[str, float], reliable: bool = True) -> dict:
    return {
        "snapshot_id": "2026-07-10_2026-07-24",
        "corpus_hash": "x" * 64,
        "pipeline_version": "0.5.0",
        "orientation": {"reliable": reliable},
        "outlets": [{"outlet": k, "score": v} for k, v in scores.items()],
    }


OUTLETS = ["left-a", "left-b", "mid-c", "mid-d", "right-e", "right-f"]
SCORES = dict(zip(OUTLETS, [-0.9, -0.5, -0.1, 0.1, 0.5, 0.9]))


def test_perfect_agreement_passes_gate():
    reference = {o: s * 40 for o, s in SCORES.items()}  # same order, different scale
    result = validate.against_rater(ratings(SCORES), reference, "ad_fontes")
    assert result.rho == 1.0
    assert result.p_value < 0.01
    assert result.passes_gate


def test_reversed_order_fails_gate():
    reference = {o: -s for o, s in SCORES.items()}
    result = validate.against_rater(ratings(SCORES), reference, "ad_fontes")
    assert result.rho == -1.0
    assert not result.passes_gate


def test_gate_requires_reliable_orientation():
    reference = {"ad_fontes": {o: s for o, s in SCORES.items()}}
    result = validate.report(ratings(SCORES, reliable=False), reference)
    assert result["raters"]["ad_fontes"]["passes_gate"]
    assert not result["gate_passed"], "unreliable orientation must block the gate"


def test_too_few_shared_outlets_refused():
    with pytest.raises(ValueError, match="real sample"):
        validate.against_rater(ratings(SCORES), {"left-a": -1.0}, "allsides")


def test_unverified_reference_excluded_by_default(tmp_path):
    ref = tmp_path / "ref.yaml"
    ref.write_text(
        "ratings:\n"
        "  left-a:\n"
        "    allsides: {value: Left, verified: true}\n"
        "    ad_fontes: {value: -15.0, verified: true}\n"
        "  right-e:\n"
        "    allsides: {value: Right, verified: false}\n"
        "    ad_fontes: {value: 12.0, verified: true}\n"
    )
    strict = validate.load_reference(ref)
    assert "right-e" not in strict["allsides"], "unverified value must be excluded"
    assert "right-e" in strict["ad_fontes"]
    assert strict["skipped_unverified"] == ["right-e/allsides"]
    assert strict["allsides"]["left-a"] == -2.0  # scale mapping

    peeking = validate.load_reference(ref, allow_unverified=True)
    assert peeking["allsides"]["right-e"] == 2.0
