# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[SemVer](https://semver.org). Any change that could alter published ratings
requires a version bump and, if it changes methodology, a decision record in
`docs/decisions/`.

## [Unreleased]

## [0.8.3] - 2026-07-19

### Fixed

- Embedding no longer crashes under CPU contention. torch's multi-threaded
  forward-pass kernel intermittently raised `Illegal instruction` (SIGILL) on
  the deployment host when the collector's 6h cycle overlapped other load,
  which the loop swallowed as non-fatal — so that cycle silently computed no
  new embeddings. Inference is now pinned to one thread
  (`torch.set_num_threads(1)`), which also removes multi-threaded reduction
  nondeterminism, so newly computed vectors are bit-reproducible (D1/D10).
  Cached vectors are untouched; a vector recomputed after this change may
  differ from a pre-0.8.3 one at ~1e-6, which can move a borderline article
  across the cluster threshold and thus shift a rating — hence the version bump.

## [0.8.2] - 2026-07-10

Audit pass 3 (zero-confirmation over the pass-2 diff): 2 findings — one a
regression introduced by pass 2 itself, which is exactly why the loop runs
until zero.

### Fixed

- Batch atomicity restored: Python's sqlite3 opens no transaction for
  SAVEPOINT, so the pass-2 per-entry savepoints silently became outermost
  transactions on the autocommit ingest path and RELEASE committed every
  item individually — recreating the crash window pass 1 closed. Inserts now
  guard with an explicit BEGIN; a rollback before custody_append leaves
  nothing durable (pinned by an empirical test on the real path).
- validate distinguishes thin-sample raters (verified values but <5 shared
  outlets → expand overlap) from missing raters (no verified values → verify
  at source) in both the artifact (raters_thin with reason) and the CLI
  output; the gate fails on either, now for stated reasons.

## [0.8.1] - 2026-07-10

Audit pass 2 (three angles over the pass-1 remediation): 23 findings, all
fixed. The loop converges: pass 1 found 19, pass 2 found progressively
narrower issues, each now pinned by a regression test.

### Fixed

- Entry-level savepoints in insert_article/insert_speech: a failure between
  the content write and the metadata write rolls back both, so a batch
  commit can never durably orphan unchained content.
- cached_embed no longer runs DDL (moved to db.connect) and never commits
  inside a caller's open batch — embedding mid-collection cannot break the
  rows+chain atomicity contract.
- cycle derives its window from UTC (was host-local date.today(): a TZ-ahead
  host would mutate a published release id intra-day) and uses one instant
  for start/end.
- Ratings record the exact reference-corpus state (hash + speech count):
  same manifest + same reference state is the full, checkable
  reproducibility precondition.
- validate: thin-sample raters (1-4 shared outlets) are recorded gate
  failures, not tracebacks; exit codes are automation-safe (0 pass, 2 fail).
- snapshot fails loudly when a manifested article's content row is missing
  (was: silently smaller manifest masking store corruption).
- audit fails on an empty store; emits an append-only custody-heads.jsonl
  history alongside the head file (external anchoring against wholesale
  chain recomputation).
- report regeneration clears stale evidence pages; insert timestamps are
  validated as timezone-aware and normalized to UTC (string-compared
  windows stay chronological); file: URI paths no longer mkdir junk.
- New `tiltmeter repair`: adopts custody-orphaned content (pre-0.8
  interruptions, partial restores) as an explicit, visible 'adopt' chain
  batch.
- Cleanup sweep: shared _publish_release (run and cycle can't diverge),
  README quickstart/status drift fixed, dead helpers and a vacuous test
  assertion removed, remaining unpinned-encoding I/O fixed.

## [0.8.0] - 2026-07-10

Full-codebase audit (8 finder angles, 42 candidates, 19 verified findings)
and the refactor to zero. The fingerprinted store is untouched; the
embeddings cache (derived data) rebuilds itself once.

### Fixed

- Custody integrity: collected rows and their chain entry now commit in ONE
  transaction per outlet/day batch — no crash or malformed feed entry can
  leave content outside the chain; malformed entries are skipped, batches
  roll back whole. `audit` gained the reverse check (content outside the
  chain fails) and now opens the store strictly read-only, refusing missing
  paths instead of creating an empty store and passing.
- Gate math: Spearman now uses tie-averaged ranks (was order-dependent on
  tied data — could flip the 0.7 gate by alphabetization; verified
  numerically). Gate requires BOTH raters present and passing; peeking with
  --allow-unverified is recorded in the artifact, written to an unservable
  validation-peek-* file, and can never pass.
- Manifest integrity: corpus_hash now covers every field of every article
  record (outlet attribution, URLs, byline, timestamps), not just content
  fingerprints — metadata edits in published manifests are detected
  (manifest_version 2; v1 manifests refused).
- Embedding cache is self-invalidating: keyed by hash of the exact embedded
  text plus model@revision, so pin or recipe changes can never serve stale
  vectors; one shared implementation for articles and speeches; lookups are
  chunked (no more whole-table scans that grow with the corpus).
- /health survives bad timestamps (marks the outlet stale instead of dying);
  serve gained --config so health scoping and /outlets work from any cwd.
- Evidence pages: pole story lists are disjoint by construction.
- Deleted src/tiltmeter/congress.py — an abandoned pre-reference.py draft
  (swept in by git add -A at v0.2.0) that bypassed the content store and
  custody chain with unverifiable fingerprints. Never imported; now gone.

### Added

- `tiltmeter cycle`: the deployment unit — ingest, reference top-up, rolling
  14-day snapshot + run, audit — so window policy and orchestration live in
  tested Python; compose now ships the collector service with only a sleep
  loop in shell.
- artifacts.py: one deterministic writer (UTF-8, sorted keys, no ASCII
  escaping) and one naming table for every release artifact; the API's
  routes are generated from it. All writers/readers migrated (three had
  drifted; several were locale-dependent).
- stats.py: the tie-averaged Spearman, tiny and textbook-checkable.
- tests/test_hardening.py: one regression test per audit finding family,
  plus Dockerfile↔code model-pin consistency and byte-determinism checks.

### Changed

- Dockerfile bakes the model before copying source (code changes no longer
  re-download it); pins declared as ARGs, drift-gated by test.
- score.compute returns the full pipeline result; ratings, stories artifact,
  and evidence pages are one computation by identity, and the sweep shares
  the same orientation-proxy helper.

## [0.7.0] - 2026-07-10

Early-development reset (ADR-0005): with a one-day corpus, compatibility debt
was deleted instead of carried. Databases and release artifacts were wiped on
all deployments; collection restarted clean. This is the last reset — from
v3 on, fingerprint changes require a migration ADR.

### Changed

- Fingerprint payload v3 covers title + body + feed summary. Fixes a real
  v2 defect: paywalled articles sharing a headline but differing in summary
  shared a fingerprint and could share one cached embedding (now pinned by
  test).
- `articles` is pure reference metadata — title/summary columns removed;
  content lives in exactly one place, the fingerprinted payload.
- New `observed_at` (feed appearance time; snapshot window key) vs
  `fetched_at` (storage time; custody record), plus `source` provenance.
- v1/v2 migration machinery deleted; pre-v3 stores are refused with a clear
  error.

### Investigated and rejected

- Historical backfill via Wayback Machine feed replay: CDX probe shows our
  feed URLs captured 0-4 days per 60 for nearly all outlets. Per-outlet
  coverage that uneven would make missingness read as editorial choice.
  The corpus remains forward-only; observed_at/source stay for any future
  archival source that survives scrutiny.

## [0.6.0] - 2026-07-10

Storage architecture for the long haul (METHODOLOGY D11, ADR-0004): the
dataset must stay one verifiable file as it grows for years.

### Added

- Content-addressed storage: every distinct text stored once,
  zlib-compressed, keyed by its SHA-256 fingerprint. Wire copy syndicated
  across outlets stores once. Measured on the real corpus: 12.2 MB → 6.3 MB.
- Append-only custody chain: every ingest/reference batch appends a
  hash-chained entry covering its item fingerprints; the v1→v2 migration
  chains the entire backlog as a genesis batch. History cannot be rewritten
  without breaking the chain.
- `tiltmeter audit`: re-hashes every stored text, checks all references,
  walks the chain; `--emit` writes a head summary. Chain head served at
  `/custody`. Tamper scenarios (content edits, deletions, history rewrites,
  log manipulation) covered by tests through a raw non-FK connection — the
  realistic attacker path.
- Outlet dimension table (provider data stored once), verbatim byline
  capture (unrecoverable later; no signal uses them yet), HTML-stripped feed
  summaries, URL canonicalization (tracking parameters removed; original
  kept when it differed).

### Changed

- Automatic, transactional v1→v2 migration on first connect. Content
  fingerprints preserved verbatim: every previously published manifest
  remains verifiable against the migrated store. WAL journal mode enabled.

## [0.5.0] - 2026-07-10

The M3 gate as code: on gate day the validation is one command.

### Added

- `tiltmeter validate` (D7): Spearman rank correlation of a ratings release
  against AllSides and Ad Fontes over shared outlets, with fixed-seed
  permutation p-values and the pre-declared pass bar (rho >= 0.7 against
  both AND reliable orientation). Refuses reference values not verified at
  source unless `--allow-unverified` (peeking only). Emits
  validation-{snapshot}.json, served at /validation/{id}.
- `tiltmeter sweep` (D7): rescoring across the clustering-threshold grid
  (0.35-0.55) with rank-correlation-vs-default stability figures. Emits
  sweep-{snapshot}.json, served at /sweeps/{id}.
- Day-one diagnostics recorded honestly: validation fails (orientation
  unreliable; rho meaningless with an arbitrary sign) and threshold
  stability is low - the instruments agree one day of corpus is not enough,
  which is what they are for.

## [0.4.1] - 2026-07-10

### Fixed

- `/health` staleness is now computed against the *configured* outlet list:
  outlets retired from config no longer alarm forever, and configured
  outlets with no articles at all (the bootstrap dead-feed case) are
  reported stale with null hours instead of being invisible.

## [0.4.0] - 2026-07-10

Unattended-operation hardening: the deployment must run two weeks with no
human attention and produce trustworthy corpus + fresh dry-run ratings.

### Added

- `/health` now reports per-outlet hours since the last collected article and
  a `stale_outlets` list (>36h = two missed collection cycles); status flips
  to `degraded` so one HTTP request reveals a silently dead feed.
- CI publishes version-tagged images (`ghcr.io/sudolulo/tiltmeter:<version>`)
  alongside `latest`, version read from pyproject.

### Changed

- Outlet swaps after the pre-wait feed audit (both recorded per D4 policy):
  **CNN → CBS News** (CNN's legacy RSS serves 2022–2024 articles) and
  **WSJ → Newsweek** (Dow Jones froze all public feeds Jan 2025). Both
  replacements preserve the vacated spectrum slot per AllSides
  (Lean Left / Center). Reference ratings and ownership entries updated.
- Embedding model cache baked at `HF_HOME=/opt/hf-cache`, world-readable, so
  the pipeline runs offline under any uid (deployments run as non-root).

### Fixed

- `/outlets` crashed on YAML date fields (json.dumps on date objects killed
  the response mid-flight); serialized with default=str and pinned by test.

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

[Unreleased]: https://github.com/sudolulo/tiltmeter/compare/v0.8.2...HEAD
[0.8.2]: https://github.com/sudolulo/tiltmeter/compare/v0.8.1...v0.8.2
[0.8.1]: https://github.com/sudolulo/tiltmeter/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/sudolulo/tiltmeter/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/sudolulo/tiltmeter/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/sudolulo/tiltmeter/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/sudolulo/tiltmeter/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/sudolulo/tiltmeter/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/sudolulo/tiltmeter/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/sudolulo/tiltmeter/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/sudolulo/tiltmeter/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/sudolulo/tiltmeter/releases/tag/v0.1.0
