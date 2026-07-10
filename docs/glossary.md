# Glossary

Plain definitions of every technical term used in this project's docs. If you
hit a term anywhere in tiltmeter that isn't here, that's a bug — file it.

### RSS feed
A machine-readable list an outlet publishes of its latest articles: headline,
link, timestamp. It's how tiltmeter knows what each outlet published without
scraping their whole site.

### Corpus
The full collection of articles tiltmeter has gathered. Scores are always
computed from a stated slice of it, never from "the web" loosely.

### Snapshot
A frozen slice of the corpus: all articles from a stated time window, pinned
by their fingerprints. Ratings are computed from snapshots so results can be
checked and re-run later.

### Fingerprint (hash)
A short code (SHA-256) computed from an article's exact text. Change one
character of the article and the code changes completely. Fingerprints prove
that a rating was computed from exactly these articles and no others.

### Manifest
The published list of what's in a snapshot: each article's link, headline,
outlet, timestamp, and fingerprint — but not its full text (which stays with
the outlet). Anyone can re-download the articles and verify the fingerprints.

### Embedding
A way of turning a piece of text into a list of numbers so that similar texts
get similar numbers. tiltmeter uses embeddings only to spot when two articles
cover the same story — never to judge them.

### Clustering
Automatically grouping similar things. Here: grouping all outlets' articles
about the same news event into one "story."

### Story cluster
One news event and all the articles about it, across outlets. The unit of
tiltmeter's analysis: for each story, which outlets covered it?

### Coverage matrix
A big grid: one row per outlet, one column per story, marking who covered
what. All of tiltmeter's scoring reads off this grid.

### Correspondence analysis
A standard statistical method that turns a grid like the coverage matrix into
a map: things with similar patterns end up near each other. The "seating
chart" in the plain-language docs.

### Principal axis
The single strongest direction of difference in that map — the line along
which outlets' coverage choices differ most. tiltmeter checks whether that
line matches political lean, rather than assuming it.

### Anchor
The external reference that tells the map which end is politically left and
which is right. tiltmeter's anchor is language from congressional speeches —
public records, not anyone's opinion of an outlet.

### DW-NOMINATE
A long-running political science measure that places members of Congress on
a left–right scale using their actual voting records. Public data, published
at voteview.com.

### Bootstrap
A standard way to measure how sure we are of a number: recompute it many
times on random re-samples of the data and watch how much it wobbles.

### Confidence interval
The honest error range around a score, produced by the bootstrap. "−0.3 ± 0.1"
means: don't read anything into differences smaller than that.

### Spearman rank correlation
A statistic (written ρ, "rho") measuring how similarly two lists rank the same
items, from −1 to +1. We use it to compare our outlet ordering with the
commercial raters' ordering.

### Sensitivity analysis
Re-running the pipeline with the judgment-call settings changed (time window,
grouping threshold) and publishing how much the scores move. If a small
setting change swings the results, that's disclosed, not hidden.

### Tunable
A pipeline setting that is a practical judgment call rather than something the
research literature dictates. Every tunable is labeled as such in
METHODOLOGY.md and covered by the sensitivity analysis.

### ADR (decision record)
A short numbered document recording one methodology decision: what was
decided, why, what the alternatives were, and what could go wrong. Decisions
are never edited in place — a new record supersedes an old one, so the
method's history stays visible.

### SemVer (semantic versioning)
Version numbers with meaning (MAJOR.MINOR.PATCH). Any change that could alter
published ratings bumps the version, so every ratings file names the exact
method that produced it.

### Reproducibility
The property that anyone can re-run the pipeline on the same snapshot and get
the same output, byte for byte. The project's core promise.

### Ideal-point estimation
The political science technique of placing actors on a scale from their
observed choices — classically, placing legislators by their votes. tiltmeter
places outlets by their coverage choices: outlets are the legislators, stories
are the votes.

### Lede
The opening sentences of a news article, summarizing the story. tiltmeter
embeds headline + lede to group articles into story clusters.

### Content-addressed storage
Storing each piece of text under its own fingerprint. The fingerprint is both
the address and the integrity check: if the text changes, it no longer
matches its address. Identical texts are stored exactly once.

### Custody chain
The dataset's tamper-evident logbook. Every batch of newly collected items
adds a line, and each line is locked to the line before it by a fingerprint.
Changing or removing any old line breaks every line after it — so the
collection's history cannot be rewritten quietly. `tiltmeter audit` checks
the whole chain.

### Append-only
Data is added, never edited or deleted. Collected articles and speeches are
append-only in tiltmeter; only derived caches (like embeddings) may be
rebuilt.

### Byline
The author credit on an article, stored exactly as the outlet published it.
Collected because it cannot be backfilled later; not yet used by any signal.

### Content-addressed storage
Storing each piece of text under its own fingerprint. The fingerprint is both
the address and the integrity check: if the text changes, it no longer
matches its address. Identical texts are stored exactly once.

### Custody chain
The dataset's tamper-evident logbook. Every batch of newly collected items
adds a line, and each line is locked to the line before it by a fingerprint.
Changing or removing any old line breaks every line after it — so the
collection's history cannot be rewritten quietly. `tiltmeter audit` checks
the whole chain.

### Append-only
Data is added, never edited or deleted. Collected articles and speeches are
append-only in tiltmeter; only derived caches (like embeddings) may be
rebuilt.
