# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[SemVer](https://semver.org). Any change that could alter published ratings
requires a version bump and, if it changes methodology, a decision record in
`docs/decisions/`.

## [Unreleased]

## [0.3.0] - 2026-07-10

### Added

- Axis orientation (`orient.py`): party-mean speech embeddings decide the
  axis sign (negative = left, positive = right); agreement strength is
  published and weak orientation is flagged `reliable: false` (ADR-0003).
- Scoring assembly (`tiltmeter run`): manifest → deterministic ratings.json
  (schema_version 1, no timestamps — reruns are byte-identical) + per-outlet
  evidence pages with the axis-distinguishing stories, real headlines,
  covered/skipped marks, neighbors, and CIs.
- Read-only HTTP API (`tiltmeter serve`, stdlib, CORS enabled): /health,
  /ratings, /ratings/latest, /ratings/{id}, /manifests/{id},
  /evidence/{id}/… — tiltmeter is a data layer; visualization is a separate
  consumer's job (ADR-0003).
- Docker: reproducible image with the pinned embedding model baked in
  (offline recomputation), compose file serving the API on :8477; CI builds
  the image on every push and publishes ghcr.io/sudolulo/tiltmeter from main.
- First dry run on a one-day snapshot: pipeline exercised end to end; output
  correctly self-flagged orientation as unreliable (ρ = +0.18, 63 stories).
- Outlet ownership data in `config/outlets.yaml`: owner, structure type, and
  control notes per outlet, each entry carrying source URL, retrieval date,
  and verified flag (same integrity rules as reference ratings). Served at
  `/outlets`; shown in the generated outlets table. Context only — never a
  scoring input.
- Story-cluster artifact (`stories-{snapshot}.json`) and `/stories/{id}`
  endpoint: the side-by-side coverage primitive for consumer apps — who
  covered each story and how each outlet headlined it.
- Factuality feasibility study (`docs/feasibility-factuality.md`): the anchor
  problem, five candidate anchors evaluated, proposed F1/F2/F3 architecture
  (process reliability / corroboration / resolvable claims), naming rule, and
  validation gate. Planning only; no factuality signal is implemented.

### Fixed

- Docker image pulled CUDA torch via the transitive dependency (6.7GB image);
  torch is now a direct dependency pinned to the CPU wheel index — image is
  1.23GB and runs anywhere.

## [0.2.0] - 2026-07-10

### Added

- Snapshot machinery (`tiltmeter snapshot`): freezes a corpus window into a
  deterministic, tamper-evident manifest (URL + headline + fingerprint per
  article; no text). Manifests verify their corpus hash on load.
- Embedding module: pinned all-MiniLM-L6-v2 (CPU), headline+lede passages,
  vectors cached by content fingerprint.
- Story clustering: agglomerative/cosine grouping into cross-outlet stories;
  coverage matrix construction.
- Selection signal: correspondence-analysis first axis over the coverage
  matrix with bootstrap 95% confidence intervals (1,000 rounds, fixed seed).
  Synthetic-fixture tests pin bloc separation, determinism, CI behavior.
- Congressional reference corpus (`tiltmeter reference`): daily Congressional
  Record floor speeches from govinfo.gov, speaker→party attribution via
  voteview member data; ambiguous speakers dropped, never guessed.
- `config/reference_ratings.yaml`: incumbent-rater values for validation
  only, each entry carrying source, retrieval date, and a verified flag;
  unverified entries are barred from gate reporting.
- ADR-0002: pipeline implementation choices (model pins, clustering
  threshold, CA formulation, bootstrap design, Record parsing scope).
- Prior-art survey of adjacent living projects (docs/research.md §1.c) and
  the train-on-raters circularity note (METHODOLOGY D7).

### Changed

- Per-article fetch timeout capped at 10s so blocked outlets (e.g. WaPo)
  cannot stall ingest runs; headline+summary still collected for them.

## [0.1.0] - 2026-07-10

### Added

- Project scaffold: uv-managed Python 3.13 package, MIT license, CI.
- Corpus collector (`tiltmeter ingest`): polls 20 US outlets' politics RSS
  feeds, fetches full article text once per URL, stores to SQLite with SHA-256
  content fingerprints. `tiltmeter status` reports per-outlet counts.
- Methodology specification (`METHODOLOGY.md`): ten decision blocks
  (D1–D10), each with decision, sourced rationale, alternatives, and failure
  modes; format machine-checked in CI.
- Foundational literature review (`docs/research.md`), venue-verified.
- Plain-language walkthrough (`docs/how-it-works.md`), CI-gated to ≤ grade-10
  reading level; glossary (`docs/glossary.md`).
- ADR-0001: story-selection ideal points with congressional-language anchor.
- Docs enforcement in CI: readability gate, glossary coverage, decision-block
  and ADR format lint, generated outlets table freshness, code/docs sync gate.

### Changed

- Outlet sample swaps against the planned list (feed availability,
  2026-07-10): AP → Christian Science Monitor (AP has no public RSS; 401),
  WSJ politics feed → WSJ world news feed (politics feed dead; Opinion feed
  deliberately not used — news and opinion are rated separately by every
  incumbent rater).
