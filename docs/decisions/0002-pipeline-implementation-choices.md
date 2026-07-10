# ADR-0002: v0.2 pipeline implementation choices

- **Status**: accepted
- **Date**: 2026-07-10
- **Supersedes**: none (implements ADR-0001 / METHODOLOGY D3, D5, D6)

## Decision

Concrete choices for the first working pipeline:

1. **Embeddings**: `sentence-transformers/all-MiniLM-L6-v2`, pinned by git revision,
   CPU-only torch. Passage = headline + first 40 words of body (≈ the lede), or feed
   summary when body text is unavailable (paywalled outlets). Vectors cached by
   content fingerprint — computed once, ever.
2. **Story clustering**: agglomerative clustering, cosine distance, average linkage,
   distance threshold **0.45** (tunable). Only clusters spanning ≥2 outlets count as
   stories.
3. **Axis**: correspondence analysis implemented directly as SVD of standardized
   residuals of the coverage matrix (no extra dependency). Refuses to run with fewer
   cross-outlet stories than outlets.
4. **Uncertainty**: bootstrap over stories, 1,000 rounds, fixed seed `20260710`;
   bootstrap axes sign-aligned to the point estimate before taking percentiles.
5. **Reference corpus**: daily Congressional Record zips from govinfo.gov (public
   domain, keyless); House/Senate **floor granules only** — Extensions of Remarks
   are written insertions, not speech; Daily Digest is a summary. Speaker→party via
   voteview member CSVs; speeches whose speaker cannot be matched to exactly one
   member (or one party) are **dropped, never guessed** (~2% in practice). Speeches
   under 50 words are dropped as procedural.

## Rationale (sources)

- MiniLM-class sentence embeddings are the standard cheap-and-good choice for
  semantic similarity (Reimers & Gurevych 2019, Sentence-BERT, EMNLP); pinning model
  + revision + CPU keeps runs reproducible across machines (METHODOLOGY D1).
- Average-linkage agglomerative clustering is deterministic — no seed dependence at
  all — unlike centroid-initialization methods; determinism outranks marginal
  cluster-quality gains here (D1).
- CA-as-SVD-of-residuals is the textbook formulation (Greenacre, *Correspondence
  Analysis in Practice*); implementing it directly keeps the math inspectable in
  ~30 lines rather than behind a dependency.
- Bootstrap-over-stories treats the news cycle as the sampling unit, which is the
  claim being made: "given a different draw of stories, where would this outlet
  sit?" (D6).
- Floor-speech-only scope follows the Gentzkow & Shapiro (2010) tradition of using
  spoken congressional language as the party-language reference.

## Alternatives considered

- Larger embedding models (mpnet, bge, LLM embeddings) — better similarity at 5–20×
  the compute; revisit in the D7 sensitivity sweep, where the embedding model is an
  explicit tunable.
- HDBSCAN for clustering — handles noise points elegantly but introduces more
  tunables; agglomerative + threshold is easier to explain in the plain-language
  docs ("merge anything closer than X").
- The `prince` CA library — fine, but 30 transparent lines beat a dependency for
  the single most scrutinized computation in the project.
- Including Extensions of Remarks — more D/R text volume, but written-for-the-record
  language differs systematically from floor debate; excluded for v0.2, revisitable.

## Failure modes / risks accepted

- Paywalled outlets (WaPo) embed headline+feed-summary rather than headline+lede —
  slightly less signal per article for those outlets; per-outlet text coverage is
  reported so the asymmetry is visible, not hidden.
- Threshold 0.45 is a judgment call: too tight splits one event into several
  stories, too loose merges distinct events. It is the first parameter in the D7
  sensitivity sweep, and evidence pages make bad merges visible to any reader.
- Surname-based speaker matching drops ~2% of speeches and could drop more in
  chambers with many shared surnames; drops are counted and reported per run.
