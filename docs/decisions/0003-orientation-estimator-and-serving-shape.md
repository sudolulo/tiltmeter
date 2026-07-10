# ADR-0003: Orientation estimator; tiltmeter stays a data layer

- **Status**: accepted
- **Date**: 2026-07-10
- **Supersedes**: none (implements METHODOLOGY D5; scopes D10's delivery)

## Decision

1. **Orientation estimator**: each party's floor speeches (first 200 words each)
   are embedded with the same pinned model as articles and averaged into a D-mean
   and an R-mean vector. Each outlet's mean article embedding yields a proxy:
   cosine-to-R minus cosine-to-D. The Spearman correlation between the unoriented
   selection axis and this proxy decides the sign (negative correlation ⇒ flip),
   with the convention **negative = left, positive = right**. If |ρ| < 0.3 the
   orientation is marked `reliable: false` in ratings.json and the CLI prints
   "UNRELIABLE — do not interpret".
2. **Product shape**: tiltmeter is a data layer — a pipeline plus a read-only HTTP
   API (`tiltmeter serve`, stdlib only, CORS `*`) over the releases directory.
   Visualization belongs to separate consumer software. tiltmeter never grows a UI;
   outputs stay machine-consumable with versioned JSON schemas
   (`schema_version` in ratings.json).

## Rationale (sources)

- Embedding-similarity to party language is the modern, cheap analog of
  Gentzkow & Shapiro (2010) phrase-frequency slant; used here only for a **single
  sign bit + a diagnostic**, not for scoring, which keeps the heavy lifting in the
  transparent coverage signal (ADR-0001).
- Publishing the axis↔party-language correlation makes orientation failure visible
  instead of silent — on day-one dry-run data it correctly reported ρ = +0.18,
  UNRELIABLE (D6's honesty requirement working as intended).
- Serving files the pipeline already wrote means the API adds zero audit surface:
  what you GET is byte-identical to what the pipeline produced and hash-pinned.

## Alternatives considered

- Full Gentzkow–Shapiro phrase-based slant as the orientation source — planned as
  signal S2 (v0.4+); requires the Gentzkow, Shapiro & Taddy (2019) estimator.
- Orienting via declared anchor outlets — rejected in ADR-0001.
- A web framework (FastAPI/Flask) for serving — more ergonomic, but a dependency
  and an attack surface for what is, by design, static-file delivery. Revisit only
  if the API grows beyond read-only.

## Failure modes / risks accepted

- Party-mean embeddings compress each party to one point; intra-party variation is
  ignored. Acceptable for one sign bit; unacceptable for scoring — which is why it
  doesn't score.
- With thin reference or news corpora the proxy correlation will hover near zero
  and orientation will stay flagged unreliable; ratings remain publishable only as
  explicitly-unreliable dry runs.
- An unoriented-but-strong axis with a weak proxy correlation likely means the
  axis captured something other than politics (topic mix); the D7 gate would catch
  this as low ρ against reference ratings.
