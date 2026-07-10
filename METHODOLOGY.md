# Methodology

This document is the technical specification of how tiltmeter computes political-lean
ratings. It is the product: the numbers are only as good as this document is honest.

Every design choice below is a numbered decision block with four mandatory fields —
**Decision**, **Rationale** (with sources), **Alternatives considered**, and **Failure
modes**. This format is machine-checked by `tests/test_docs.py`. Changing any decision
requires a new record in `docs/decisions/`, a CHANGELOG entry, and a version bump — the
methodology cannot move quietly.

Plain-language version: [docs/how-it-works.md](docs/how-it-works.md).
Literature foundations: [docs/research.md](docs/research.md).
Term definitions: [docs/glossary.md](docs/glossary.md).

Choices that are pragmatic rather than literature-backed are explicitly labeled
**Tunable** and are covered by the published parameter sensitivity analysis (D7)
rather than dressed up as principled.

---

## D1. Ratings come from a reproducible pipeline, not editorial judgment

**Decision**: Every rating is computed by open code running on an open, content-hashed
corpus snapshot, with pinned dependencies and fixed random seeds. Anyone can rerun the
pipeline and obtain the identical output. No human judgment enters the scoring path.

**Rationale**: The incumbent raters (AllSides, Ad Fontes, MBFC) all rest on structured
human judgment — balanced panels, blind surveys, rubrics (see
[docs/research.md §2](docs/research.md)). Their answer to bias is balancing the panel;
ours is removing it. A reproducible method shifts disputes from "you are biased" to
"here is the code and data" — the dispute becomes checkable. Validation discipline for
text-based measures follows Grimmer & Stewart (2013), *Text as Data*, Political
Analysis.

**Alternatives considered**: Human ratings with published evidence worksheets
(AllSides-style transparency) — scales poorly and invites governance brigading. Hybrid
algorithmic-plus-override — inherits the governance problem the moment the first
override lands.

**Failure modes**: Reproducible is not the same as correct — a deterministic pipeline
can be deterministically wrong, which is why validation (D7) is a gate, not a
formality. Method choices themselves can encode bias; that risk is handled by
citing each choice to prior literature and publishing sensitivity analyses.

## D2. Version 1 rates political lean only

**Decision**: One axis: political lean, expressed on a [-1, +1] scale. Reliability
and factuality are out of scope for v1.

**Rationale**: Lean is the axis with the strongest measurement tradition (Puglisi &
Snyder 2015, *Empirical Studies of Media Bias*, Handbook of Media Economics) and the
best available validation targets (both AllSides and Ad Fontes publish lean ratings).
Reliability requires corrections tracking and fact-check cross-referencing — a
different, harder pipeline.

**Alternatives considered**: Two-axis lean+reliability (Ad Fontes chart) — doubles v1
scope. Reliability only — less contentious but hardest to compute and not what
blindspot-style analysis needs.

**Failure modes**: A lean-only score can be misread as a quality score. Every published
artifact states that lean ≠ reliability.

## D3. The v1 signal is story selection, framed as ideal-point estimation

**Decision**: Measure *what outlets choose to cover*. Articles from all outlets are
embedded (all-MiniLM-L6-v2 sentence embeddings of headline + lede) and grouped into
cross-outlet story clusters. The outlet×story coverage matrix is scaled by
correspondence analysis; the first principal axis is the candidate lean dimension.
Framing: this is roll-call analysis where outlets are legislators and coverage
decisions are votes.

**Rationale**: Selection (gatekeeping) bias is a real and measurable channel:
D'Alessio & Allen (2000, J. Communication) meta-analytic taxonomy; Budak, Goel & Rao
(2016, Public Opinion Quarterly) found outlet bias manifests largely through issue
selection; Rönnback, Emmery & Brighton (2025, PLOS One) found coverage features the
most informative for outlet-level bias prediction. The scaling method sits in the
ideal-point tradition (Poole & Rosenthal 1985, AJPS; unsupervised text scaling:
Slapin & Proksch 2008, AJPS "Wordfish"). It requires no training data, no lexicon,
and no LLM judgment.

**Alternatives considered**: Language/framing similarity to congressional speech
(Gentzkow & Shapiro 2010, Econometrica) — planned as signal S2 in v0.2, not v1,
because it requires the corrected high-dimensional estimator of Gentzkow, Shapiro &
Taddy (2019, Econometrica) to avoid severe finite-sample bias. Audience-based scores
(Bakshy, Messing & Adamic 2015, Science; Barberá 2015) — platform data access is now
gated. LLM-as-judge — excluded by D8.

**Failure modes**: The first principal axis may capture topic mix (business vs.
lifestyle) rather than politics — mitigated by politics-section feeds (D9) and by
publishing the story clusters behind every score so the axis is inspectable. Small
outlet samples make the axis unstable — mitigated by the snapshot window length and
bootstrap confidence intervals (D6). **Tunable**: embedding model, clustering
threshold — both in the sensitivity sweep (D7).

## D4. Twenty outlets, deliberately spread, chosen once and openly

**Decision**: v1 covers the 20 US outlets in `config/outlets.yaml`, selected to span
the spectrum from Mother Jones/The Nation to Breitbart/Newsmax, with
politics-section RSS feeds. Incumbent-rater ratings were consulted for *sample
selection only* — they are never an input to scoring.

**Rationale**: A proof of concept needs a sample where the expected ordering is
uncontroversial enough that failure to recover it falsifies the method. Feed
availability was verified 2026-07-10; two swaps from the original list (AP → CS
Monitor, dead feed; WSJ politics → WSJ world news feed) are recorded in CHANGELOG.md.

**Alternatives considered**: ~100-outlet US national coverage — more infrastructure
before the method is proven. Including international outlets — the left-right axis is
US-calibrated and ground truth thins out.

**Failure modes**: Sample selection is itself a choice with bias potential; the
selection criteria are stated in `config/outlets.yaml` comments, and the sample is
frozen for v1 so results cannot be cherry-picked by adding/removing outlets
post hoc.

## D5. The axis is oriented by congressional language, not by assumed outlet leans

**Decision**: No outlet's lean is assumed anywhere in the pipeline. The unsupervised
axis from D3 gets its sign (which end is "left") from an external reference corpus:
recent Congressional Record speeches (govinfo.gov bulk data), with party membership
and DW-NOMINATE scores from voteview.com. Whichever axis pole is closer to Democratic
vs. Republican language determines orientation. The published reference frame is
explicit: *lean relative to contemporary US congressional party discourse*.

**Rationale**: Lean is relational — every method in the literature defines it against
a reference population. Politicians are the standard anchor because their ideology is
a matter of public record (roll-call votes), not a rating: Gentzkow & Shapiro (2010,
Econometrica); Poole & Rosenthal's DW-NOMINATE. Anchoring to politicians also keeps
validation (D7) non-circular: no rater data enters the pipeline.

**Alternatives considered**: Declared anchor outlets ("Mother Jones = left") — one
editorial bit, but exactly the kind of judgment this project exists to remove.
Audience-based orientation — gated platform data.

**Failure modes**: Congressional discourse defines the center as the US two-party
midpoint; positions outside that frame (or drift of the frame itself over time) are
invisible to the measure. This is stated, not hidden: the frame is part of every
release's metadata.

## D6. Scores are time series with uncertainty, never permanent labels

**Decision**: Every published score is attached to a corpus snapshot window and
carries a 95% bootstrap confidence interval (resampling over story clusters).
tiltmeter publishes no undated, uncertainty-free outlet labels.

**Rationale**: Outlet lean drifts, and even incumbent raters disagree with each other
sharply — MBFC vs. audience-derived labels agree only 46%, two human-annotated
sources 57% (Rönnback et al. 2025, PLOS One). Penn's Media Bias Detector (CHI 2025)
adopts the same dynamic-view stance. Publishing uncertainty is what distinguishes a
measurement from a verdict.

**Alternatives considered**: Static labels (the incumbent-rater product shape) —
misrepresents both drift and measurement error.

**Failure modes**: Time series with CIs are harder for laymen to read than a single
label — mitigated by the evidence pages (D10) and the plain-language docs layer.

## D7. Validation against incumbent raters is a gate, with published sensitivity

**Decision**: `config/reference_ratings.yaml` holds published AllSides (5-point,
mapped to −2..+2) and Ad Fontes (numeric) ratings with retrieval dates, used for
validation only. The v1 gate: Spearman rank correlation ρ ≥ 0.7 against both raters
over the 20-outlet sample. Every release also publishes a parameter sensitivity
sweep: how much ratings move under alternative tunables (clustering threshold,
embedding model, window length).

**Rationale**: Agreement with independent human raters is the standard external check
for text-based measures (Grimmer & Stewart 2013). The bar is deliberately below
perfect: given 46–57% inter-rater agreement in adjacent work, near-perfect
correlation with any one rater would indicate overfitting to that rater, not truth.
This is also why tiltmeter does not *train* on rater labels, unlike most open-source
attempts (see docs/research.md §1.c): a model whose loss function is agreement with
AllSides can never meaningfully disagree with AllSides — it is a copy of the panel,
not an independent instrument. Validation-only use keeps disagreement informative.
Fair-use note: reference ratings are facts (a rating value on a date), stored with
retrieval dates, used only for validation.

**Alternatives considered**: No external validation ("the method is principled,
trust it") — indistinguishable from the incumbents' posture. Validating against
audience data — gated.

**Failure modes**: ρ ≥ 0.7 on 20 outlets has wide confidence bounds itself; the
validation report states the n and the CI on ρ. Failing the gate stops scaling — the
documented response is to iterate the method, not the sample.

## D8. No LLM judgment in the scoring path

**Decision**: Large language models are never asked to judge bias, lean, framing, or
quality anywhere in the pipeline. Embedding models are permitted for similarity
computation only (D3), pinned by exact version.

**Rationale**: LLMs carry measurable political lean themselves: Rozado (2024, PLOS
One, "The political preferences of LLMs" — 11 orientation tests × 24 models);
Santurkar et al. (2023, ICML, "Whose Opinions Do Language Models Reflect?").
Piping the news through a judge with its own lean would relocate the bias problem,
not solve it. Small pinned embedding models keep runs reproducible in a way
API-served LLM judgments are not.

**Alternatives considered**: LLM-as-judge with audited prompts — cheaper per article
than any alternative, but unreproducible across model versions and lean-contaminated.
Penn's Media Bias Detector accepts this trade; we don't.

**Failure modes**: Embeddings are not judgment-free either — they encode training
distribution biases. The mitigation is that embeddings only *group similar text*
here; the lean axis and its orientation come from coverage structure and public
political records, and the embedding model is a published tunable in the
sensitivity sweep (D7).

## D9. The corpus is politics-section RSS, stored locally, published as manifests

**Decision**: Ingestion polls each outlet's politics-section RSS feed (general feed
where none exists), fetches full article text once per URL, and stores it locally.
Published corpus artifacts are manifests — URL, headline, outlet, timestamp, SHA-256
content hash per article — not full text.

**Rationale**: Politics-section feeds reduce the topic-mix confound in D3. Manifests
let anyone re-fetch and hash-verify the exact corpus without tiltmeter
redistributing copyrighted article text. Headline+link is the same posture
aggregators take, and readers are always sent to the source.

**Alternatives considered**: Redistributing full text (clean reproducibility, clear
copyright violation). Third-party corpora like GDELT (Rönnback et al. 2025 use it) —
convenient but inserts an unauditable dependency between the outlet and our data.

**Failure modes**: Articles edited after our fetch won't match our stored hash —
manifests carry the fetch timestamp, and hash mismatches on re-fetch are reported as
exactly that. Feeds die (two already did, see D4) — per-outlet ingest counts are
monitored and chronic failures trigger a documented swap.

## D10. Every number is traceable to evidence a layman can read

**Decision**: Every published score links to an evidence page: the story clusters
that drove the outlet's position with example headlines side by side, its
nearest-neighbor outlets, the confidence interval, the corpus snapshot ID, and the
pipeline version. Reproducing any release must be a documented ≤3-command path ending
in a hash-verified `ratings.json`.

**Rationale**: This is the project's core value made concrete (see README). A layman
asking "why is this outlet here?" should see actual headlines, not eigenvectors.
Auditability that requires a statistics degree is not auditability for the public
this project serves.

**Alternatives considered**: Publishing scores + code only — auditable in principle,
by almost nobody in practice.

**Failure modes**: Evidence pages could be cherry-picked — they are generated by the
same deterministic pipeline as the scores (`report` module), never hand-edited, and
regenerating them is part of the ≤3-command reproduction path.
