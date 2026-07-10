# Research Foundations — Measuring Media Lean

tiltmeter descends from two research traditions: the **commercial rating industry**
(AllSides, Ad Fontes, MBFC — structured human judgment behind closed data) and four
decades of **academic measurement** of media bias (open methods, mostly one-off
studies that never became living datasets). This document surveys both, extracts what
is and is not measurable, and records the design implications. It informs
[METHODOLOGY.md](../METHODOLOGY.md); where the two disagree, reconcile deliberately.

All venues verified 2026-07-10. Links in §6.

---

## 1. Lineage

### 1.a The rating industry: balanced panels, closed data

- **AllSides** (2012–) — Blind Bias Surveys™: cross-spectrum respondents rate content
  with branding stripped. Editorial reviews: multipartisan panels of ≥6 (or trios)
  from left/center/right deliberate to consensus. Output: 5-point scale plus a
  numeric meter. Community feedback as a secondary signal.
- **Ad Fontes Media** (2017–) — trios of trained analysts (one self-identified left,
  center, right each; ≥20 hours training) score individual articles on an 8-part
  rubric (veracity, expression, headline/graphics, political position, language,
  comparison…). Article bias −42..+42, aggregated to outlet scores. Methodology
  white paper published 2021.
- **Media Bias/Fact Check** (2015–) — small team applying published criteria
  (wording, sourcing, story choice, endorsements). Widest coverage, least rigorous;
  ironically the most-used ground truth in academic work because it covers the most
  sources.

The industry's shared premise: bias in the rater is unavoidable, so *balance the
raters*. The panels are the method. None of it is reproducible — you cannot rerun a
panel — and the per-rating evidence is not published. That gap, not the ratings
themselves, is what tiltmeter fills: **remove the panel instead of balancing it.**

### 1.b The academic tradition: open methods, dead datasets

Economists and political scientists have measured outlet lean reproducibly since the
1980s, but almost every study was a one-off: a method, a paper, a static replication
archive. Nothing compounds. The methods, however, are exactly what a living open
dataset needs (see §2).

A partial exception and the closest living relative: **Penn's Media Bias Detector**
(CHI 2025) — LLM-annotated articles aggregated into dynamic per-publisher views,
deliberately refusing static outlet labels. It trades reproducibility for coverage by
putting an LLM in the judgment loop (see METHODOLOGY.md D8 for why we refuse that
trade).

### 1.c The adjacent living projects (surveyed 2026-07-10)

- **Media Cloud** (MIT/Northeastern, 2011–) — open-source, open-data media analysis
  infrastructure: 2B+ stories, 60k+ sources, actively maintained. Publishes no lean
  ratings by design. The existence proof that open news-corpus infrastructure can
  live for 15 years; not an instrument.
- **The Factual** (2019–2022) — algorithmic credibility scoring; acquired by Yahoo,
  method proprietary throughout.
- **Improve the News → Verity** (Tegmark's ITN Foundation, 2020–) — ML article
  aggregation with bias classification; nonprofit, but methodology not open or
  reproducible.
- **Open-source classifier repos** (Baly et al.'s News-Media-Reliability and
  Article-Bias-Prediction; assorted GitHub projects) — nearly all share one
  structural flaw: they *train on incumbent-rater labels* (MBFC, AllSides). Their
  ground truth is the panels, so at best they produce a cheaper copy of the panels —
  they can never meaningfully disagree, because agreement is their loss function.
  See METHODOLOGY.md D7 for how tiltmeter avoids this circularity.
- **Wikipedia's perennial-sources list** — transparent *deliberation* about source
  reliability, but human judgment all the way down.

The empty spot in this landscape: independent measurement + no judge in the loop +
versioned living dataset + layman-traceable evidence. tiltmeter is an attempt to
occupy exactly that intersection.

### 1.d Why re-run the experiment now

Three things changed. Sentence embeddings made cross-outlet story clustering cheap
and good — the expensive part of selection-bias measurement is now a commodity.
Congressional text and ideology data (govinfo.gov bulk data, voteview.com) are
freely downloadable, so the classic anchoring strategy no longer requires
institutional data access. And the incumbent raters have demonstrated durable demand
for outlet-lean ratings while leaving methodology transparency entirely unserved.

## 2. Measurement traditions

The canonical survey — **Puglisi & Snyder, "Empirical Studies of Media Bias"
(Handbook of Media Economics 1B, 2015)** — divides implicit-bias measures into three
families. They map onto tiltmeter's roadmap directly:

| Family (Puglisi & Snyder) | Canonical works | tiltmeter |
|---|---|---|
| Intensity of coverage (what gets covered, how much) | D'Alessio & Allen 2000 (gatekeeping); Larcinese, Puglisi & Snyder 2011; Budak, Goel & Rao 2016 | **S1, v0.1** — story-selection ideal points |
| Comparison with other political actors | Groseclose & Milyo 2005 (contested); **Gentzkow & Shapiro 2010**; Gentzkow, Shapiro & Taddy 2019 | **S2, v0.2** — congressional-language similarity; v0.1 uses it for axis orientation only |
| Tone | sentiment/valence studies; BABE dataset (EMNLP Findings 2021) for sentence-level bias | future work |

Supporting traditions:

- **Ideal-point estimation** (Poole & Rosenthal 1985 → DW-NOMINATE): place actors on
  a latent dimension from their observed choices. tiltmeter's outlet×story
  correspondence analysis is roll-call analysis where outlets are legislators and
  coverage decisions are votes. Ho & Quinn (2008) already placed outlets by ideal
  points, using editorial positions.
- **Unsupervised text scaling** (Slapin & Proksch 2008, "Wordfish"; supervised
  variant: Laver, Benoit & Garry 2003, "Wordscores"): latent political dimensions
  recovered from text without labeled outlets. S1's closest methodological cousin.
- **Audience-based scores** (Bakshy, Messing & Adamic 2015, Science; Barberá 2015):
  infer outlet lean from who consumes/shares it. Methodologically attractive,
  practically dead — platform data access is gated. Included here because its logic
  (lean is relational, anchored in an external population) survives in our
  congressional anchoring.
- **Theory of selection** — why S1 measures something real: White 1950
  (gatekeeping), Galtung & Ruge 1965 (news values), McCombs & Shaw 1972
  (agenda-setting: media tell you what to think *about*), Entman 1993 (framing).
  Political economy — why outlets lean at all: Mullainathan & Shleifer 2005 (AER,
  demand-side); Gentzkow & Shapiro 2006 (JPE, reputation); DellaVigna & Kaplan 2007
  (QJE, the Fox News effect — why any of this matters).

## 3. What is and is not measurable

Lessons the literature forces on us:

1. **Lean is relational.** Every credible measure anchors to an external population
   with independently known politics — Congress (roll-call votes), voters, audiences.
   A "view from nowhere" rating is an unstated anchor, not a neutral one.
2. **The method chosen shapes the structure found.** MBFC labels vs. audience-derived
   labels agree only 46%; two human-annotated label sources agree 57% (Rönnback,
   Emmery & Brighton 2025, PLOS One). Measurement choice is itself a finding — which
   is the argument for publishing the method, not just the numbers.
3. **Selection carries signal.** Budak, Goel & Rao (2016) found outlet bias operates
   largely through issue selection rather than explicit slant; Rönnback et al. (2025)
   found coverage features the most informative outlet-level predictors. The cheapest
   honest signal is *what outlets choose to cover*.
4. **Judges have lean too.** LLMs measurably lean (Rozado 2024, PLOS One; Santurkar
   et al. 2023, ICML); so do human panels — the industry's entire architecture is an
   admission of that. Any judgment component relocates the bias problem.
5. **Perfect agreement with any one rater would be a bug.** Given 46–57% inter-rater
   agreement, a method that matched AllSides at ρ ≈ 1 would have learned AllSides,
   not lean.

## 4. Design implications

| Lesson (§3) | Design response (METHODOLOGY.md) |
|---|---|
| Lean is relational | D5: explicit anchor — congressional party discourse; frame stated in every release |
| Method shapes findings | D1: open reproducible pipeline; D7: published sensitivity sweeps |
| Selection carries signal | D3: story-selection ideal points as the v1 signal |
| Judges have lean | D1: no editorial judgment; D8: no LLM judgment |
| Perfect agreement = overfit | D7: validation gate at ρ ≥ 0.7, not ρ → 1 |
| Raters disagree; lean drifts | D6: time series with confidence intervals, never static labels |
| One-off studies don't compound | Corpus manifests + versioned releases: a living dataset others can extend |

## 5. Reading list (in argument order)

1. Puglisi & Snyder 2015 — the map of the field; read first.
2. D'Alessio & Allen 2000 — the bias taxonomy (gatekeeping / coverage / statement).
3. McCombs & Shaw 1972 — agenda-setting; the theoretical charter for selection bias.
4. Poole & Rosenthal 1985 — ideal points; the estimation tradition S1 sits in.
5. Slapin & Proksch 2008 — unsupervised political scaling from text.
6. Gentzkow & Shapiro 2010 — congressional-language anchoring; our D5 and future S2.
7. Gentzkow, Shapiro & Taddy 2019 — read before implementing S2; the naive estimator
   is severely biased in finite samples.
8. Budak, Goel & Rao 2016 — selection is where the bias lives.
9. Grimmer & Stewart 2013 — validation discipline for all of the above.
10. Rönnback, Emmery & Brighton 2025 — the modern end-to-end attempt; ground-truth
    disagreement numbers.
11. Rozado 2024; Santurkar et al. 2023 — why no LLM judges.
12. Spinde et al., ACM Computing Surveys 2023 — the NLP field map (3,140 papers).

## 6. Sources

- Puglisi & Snyder 2015: <https://www.sciencedirect.com/science/article/abs/pii/B9780444636850000152>
- Gentzkow & Shapiro 2010: <https://onlinelibrary.wiley.com/doi/abs/10.3982/ECTA7195>
- Gentzkow, Shapiro & Taddy 2019: <https://onlinelibrary.wiley.com/doi/abs/10.3982/ECTA16566>
- Budak, Goel & Rao 2016: <https://doi.org/10.1093/poq/nfw007>
- Rönnback, Emmery & Brighton 2025: <https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0321418>
- Media Bias Detector (CHI 2025): <https://dl.acm.org/doi/10.1145/3706598.3713716>
- Rozado 2024: <https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0306621>
- Spinde et al. 2023 (ACM CS): <https://arxiv.org/abs/2312.16148>
- BABE (Findings of EMNLP 2021): <https://aclanthology.org/2021.findings-emnlp.101/>
- AllSides methodology: <https://www.allsides.com/about/media-bias-rating-methods>
- Ad Fontes white paper: <https://adfontesmedia.com/white-paper-2021/>
- DW-NOMINATE / voteview: <https://voteview.com>
- Congressional Record bulk data: <https://www.govinfo.gov/bulkdata>
