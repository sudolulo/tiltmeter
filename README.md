# tiltmeter

**Auditable political-lean ratings for news outlets.** A tiltmeter is an instrument
that measures the tilt of the ground — this one measures the tilt of the news.

Commercial bias raters (AllSides, Ad Fontes, Media Bias/Fact Check) sell outlet
ratings produced by human panels behind closed doors. You can't check their work.
tiltmeter is the opposite bet: ratings computed by open code from open data, where
every number can be re-derived, every methodology choice is cited to published
research, and every score links to the actual headlines that produced it.

**Do not trust us. Check.**

## How it works (one paragraph)

tiltmeter watches which stories each of 20 US outlets chooses to cover, via their
public politics feeds. Outlets making similar coverage choices land near each other
on a map — a seating chart built from the outlets' own behavior, with no one voting
on it. Which side of the map is "left" is decided by public records, not opinion:
one pole's coverage sits closer to Democratic congressional speech, the other to
Republican. Each outlet gets a dated score from −1 to +1 with an honest error range.
Plain-language walkthrough: [docs/how-it-works.md](docs/how-it-works.md). Full
technical spec with sources: [METHODOLOGY.md](METHODOLOGY.md).

## Status

Pre-alpha (v0.1, milestone M1). The corpus collector is running; scoring lands in
M2; the first validated ratings release requires ≥2 weeks of corpus (M3). Nothing
here is a usable rating yet.

## Quickstart

```sh
uv sync                      # install
uv run tiltmeter ingest      # poll all 20 outlet feeds once
uv run tiltmeter status      # article counts per outlet

# freeze a corpus window into a verifiable manifest
uv run tiltmeter snapshot --start 2026-07-10 --end 2026-07-24

# fetch the orientation anchor: congressional floor speeches + party records
uv run tiltmeter reference --end 2026-07-09 --days 10

# compute ratings + evidence pages from a manifest
uv run tiltmeter run --manifest releases/manifest-2026-07-10_2026-07-24.json

# serve the computed releases as a read-only JSON API on :8477
uv run tiltmeter serve
```

Or with Docker (the pinned embedding model is baked into the image, so
recomputation works offline):

```sh
docker compose up -d                        # API on :8477
docker compose run --rm tiltmeter ingest    # any pipeline command as one-shot
```

tiltmeter is a **data layer**: it computes and serves ratings JSON plus evidence
pages. Visualization is deliberately someone else's job — point your news reader
or dashboard at the API.

## The auditability contract

- **Reproducible**: same snapshot + same version ⇒ byte-identical ratings. Anyone
  can verify a release in ≤3 commands.
- **Sourced**: every methodology decision in [METHODOLOGY.md](METHODOLOGY.md) cites
  the research behind it ([literature review](docs/research.md)).
- **Traceable**: every score links to an evidence page of real headlines.
- **Versioned**: methodology changes require a [decision record](docs/decisions/),
  a CHANGELOG entry, and a version bump. The method cannot move quietly.
- **Readable**: the plain-language docs are CI-gated to a grade-10 reading level.
  Jargon must be defined in the [glossary](docs/glossary.md).

## Project layout

| Path | What it is |
|---|---|
| `METHODOLOGY.md` | The product: every design decision, with sources |
| `docs/how-it-works.md` | The same thing, for humans in a hurry |
| `docs/research.md` | The literature this stands on |
| `docs/decisions/` | Numbered methodology decision records (ADRs) |
| `config/outlets.yaml` | The 20 outlets and their feeds |
| `src/tiltmeter/` | The pipeline (each module states its question in plain language) |
| `releases/` | Corpus manifests and ratings, per release |

## License

Code: [MIT](LICENSE). Published ratings data: CC-BY-4.0. See [NOTICE](NOTICE) for
development disclosure.
