# ADR-0005: Early-development reset — fingerprint v3, pure-metadata articles

- **Status**: accepted
- **Date**: 2026-07-10
- **Supersedes**: the "kept redundancy" clauses of ADR-0004 (title duplication,
  v1 payload compatibility, migration machinery)

## Decision

While the project is pre-1.0 with a one-day corpus, reset the store instead of
carrying compatibility debt:

1. **Fingerprint payload v3**: `title \x1f text \x1f summary` — everything
   captured about a piece is inside the fingerprinted content. The embedding
   passage reads only from the payload, so identical passages ⇔ identical
   fingerprints, always.
2. **`articles` is pure reference metadata**: outlet, URLs, byline, published,
   observed_at, fetched_at, source, fingerprint. Title and summary columns are
   gone — content lives in exactly one place.
3. **`observed_at` vs `fetched_at`**: when the item appeared in its feed vs.
   when we stored it. Snapshot windows key on observed_at; custody records
   fetched_at. `source` marks provenance (`live` today).
4. **Migration machinery deleted**: pre-v3 stores are refused with a clear
   error; existing day-one data is recollected, not migrated. Databases and
   stale release artifacts were wiped on all deployments as part of this reset.

## Rationale (sources)

- The v2 payload (title+text only, kept for v1 fingerprint compatibility) had a
  real defect: two paywalled articles with the same headline and different feed
  summaries shared a fingerprint — and therefore could share one cached
  embedding computed from whichever arrived first. v3 closes this by
  construction (pinned by test).
- A reset costs ~1 day of articles; congressional speeches refetch exactly
  (the Record is static). Carrying migration code forever to save one day of
  a two-week ramp is a bad trade the project would never get to unmake.
- **Backfill investigated and rejected** (probe 2026-07-10): Wayback Machine
  CDX shows our feed URLs captured 0–4 days out of 60 for nearly all outlets
  (CBS: 12). Archive replay would recover a few percent of history with
  per-outlet coverage so uneven that missingness would read as editorial
  choice — poison for a coverage-comparison instrument. Sitemaps/GDELT change
  the selection function (D9). The corpus is forward-only; `observed_at` and
  `source` remain for any future archival source that survives scrutiny.

## Alternatives considered

- Keep v1-compatible fingerprints forever — rejected: the compatibility served
  exactly one day of published manifests, all regenerated after the reset.
- Migrate v2→v3 — rejected: migration code is permanent complexity; the data
  it would save is one day old and mostly refetchable.

## Failure modes / risks accepted

- Anyone holding a pre-reset manifest cannot verify it against the new store
  (accepted: pre-1.0, no external consumers yet; the reset is the last one —
  from v3 on, fingerprint format changes require a migration ADR).
- ~Dozens of articles that rolled out of feeds during the gap are permanently
  lost; measured against a corpus that will hold hundreds of thousands, noise.
