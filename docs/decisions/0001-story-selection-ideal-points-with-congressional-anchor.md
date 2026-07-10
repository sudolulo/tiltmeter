# ADR-0001: Story-selection ideal points, anchored to congressional language

- **Status**: accepted
- **Date**: 2026-07-10
- **Supersedes**: none

## Decision

tiltmeter v0.1 measures outlet political lean from **story selection**: outlets are
placed on a latent axis by correspondence analysis of the outlet×story coverage
matrix (ideal-point estimation — outlets as legislators, coverage decisions as
votes). The axis is **oriented by an external political reference** — similarity of
each pole to Democratic vs. Republican language in recent Congressional Record
speeches — so no outlet's lean is assumed anywhere in the pipeline. Scores are
per-window time series with bootstrap confidence intervals. No editorial or LLM
judgment exists in the scoring path.

## Rationale (sources)

- Selection is a real, strong bias channel: D'Alessio & Allen 2000 (taxonomy);
  Budak, Goel & Rao 2016 (bias operates largely via issue selection); Rönnback,
  Emmery & Brighton 2025 (coverage features most informative at outlet level).
- The estimation tradition is proven: Poole & Rosenthal 1985 (ideal points);
  Slapin & Proksch 2008 (unsupervised political scaling from text).
- Anchoring to politicians keeps the reference frame factual and the validation
  non-circular: Gentzkow & Shapiro 2010; DW-NOMINATE (voteview.com).
- No judge in the loop: LLMs measurably lean (Rozado 2024; Santurkar et al. 2023);
  human panels are the incumbents' admission of the same problem.

Full citations: [docs/research.md](../research.md) §6.

## Alternatives considered

1. **Declared anchor outlets** ("Mother Jones = left, Breitbart = right") — one
   editorial bit, but precisely the judgment this project exists to remove. Rejected
   after methodology review, 2026-07-10.
2. **Language-similarity scoring as the primary signal** (Gentzkow–Shapiro style) —
   deferred to v0.2 (S2); requires the Gentzkow, Shapiro & Taddy 2019 estimator to
   avoid finite-sample bias. In v0.1 congressional language is used only to orient
   the axis sign.
3. **Audience-based scoring** — platform data access is gated; dead end since ~2018.
4. **LLM-as-judge** — unreproducible across model versions and lean-contaminated;
   rejected on principle (METHODOLOGY.md D8).
5. **Human panels with published worksheets** — transparent but unscalable and
   governance-fragile; this is the incumbents' territory anyway.

## Failure modes / risks accepted

- The first principal axis may capture topic mix rather than politics; mitigated by
  politics-section feeds and published evidence pages; checked by the D7 validation
  gate (Spearman ρ ≥ 0.7 vs. AllSides and Ad Fontes orderings).
- 20 outlets over a 2–4 week window may yield an unstable axis; bootstrap CIs make
  the instability visible rather than hidden.
- The congressional reference frame defines "center" as the US two-party midpoint;
  drift or positions outside that frame are invisible. Stated in every release.
