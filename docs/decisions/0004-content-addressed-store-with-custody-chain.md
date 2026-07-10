# ADR-0004: Content-addressed SQLite store with an append-only custody chain

- **Status**: accepted
- **Date**: 2026-07-10
- **Supersedes**: none (implements METHODOLOGY D11; extends D1/D9)

## Decision

Schema v2, migrated in place (fingerprints preserved verbatim, so all previously
published manifests remain verifiable):

1. **SQLite stays.** One file is the dataset; the file is the audit artifact.
2. **Content-addressed `contents` table**: each distinct text stored once,
   zlib-compressed (level 6, stdlib), keyed by SHA-256. Articles and speeches
   reference fingerprints. Syndicated wire copy across outlets stores once.
3. **URL canonicalization** at ingest (strip fragments + tracking parameters);
   original URL retained when it differed. Dedup key = canonical URL.
3b. **Provider-level normalization**: outlets are a dimension table (name stored
   once, integer references); feed summaries are HTML-stripped to prose;
   bylines captured verbatim as published (feeds expire — uncollected bylines
   are unrecoverable; no signal consumes them yet, and an authors dimension
   waits for an actual consumer). Kept redundancy, documented: title exists in
   both metadata and the fingerprinted payload for v1 fingerprint
   compatibility; per-row `fetched_at` strings repeat per batch (~10 KB/day,
   normalization rejected as complexity for trivia).
4. **Append-only custody chain**: every non-empty ingest/reference batch appends
   `entry_hash = H(prev_hash | items_hash | kind | ts | n)` plus the item
   fingerprints. Migration chains the entire backlog as a genesis batch.
5. **`tiltmeter audit`**: re-hashes every stored text against its key, checks all
   references, walks the chain; `--emit` writes a head summary. `/custody` serves
   the live chain head. WAL journal mode for reader/writer concurrency.

## Rationale (sources)

- Growth math: ~400 articles/day ≈ 1.2–1.5 GB/year raw at 20 outlets; v2 halves it
  (measured: 12.2 MB → 6.3 MB on the real day-one corpus). SQLite is comfortable
  to hundreds of GB with a single writer — years of headroom even at 100 outlets.
- Content addressing = git's storage model: integrity check and dedup are the same
  operation because the key is the checksum.
- The custody chain is the certificate-transparency idea (RFC 6962) applied to a
  research corpus: an append-only log whose heads, once seen externally, make
  history rewrites detectable. SQLite is a Library of Congress recommended
  storage format — the longevity half of "auditable for years."

## Alternatives considered

- PostgreSQL / DuckDB / flat files / zstd / float16 embeddings — evaluated and
  rejected in METHODOLOGY D11 with reasons; headline: nothing beats "the dataset
  is one verifiable file" for this project's core value at this write rate.
- Chaining every article individually (one entry per item) — finer granularity,
  ~100× more chain rows for no added tamper-evidence; batch-level chaining with
  item lists gives identical guarantees.
- Signing chain heads (age/minisign) — real upgrade over bare hashes, deferred:
  key management questions (whose key, where) deserve their own decision when
  the dataset gains external consumers.

## Failure modes / risks accepted

- FK constraints are per-connection; audit therefore trusts only re-hashing.
- Chain timestamps are self-reported between externally published heads.
- In-db compression partially duplicates ZFS compression on the NAS — accepted
  because the *file* is the portable artifact; its internal compression travels
  with it off-pool.
