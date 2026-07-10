# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[SemVer](https://semver.org). Any change that could alter published ratings
requires a version bump and, if it changes methodology, a decision record in
`docs/decisions/`.

## [Unreleased]

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
