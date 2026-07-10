# Feasibility: reproducible factuality measurement

Status: **planning document** — no factuality signal is implemented. This is the
feasibility analysis for whether tiltmeter can ever rate reliability the way it
rates lean: reproducibly, with no panel and no judge. Sources surveyed 2026-07-10.

## 1. The anchor problem

The lean pipeline works because ideology is **relational** and has a behavioral
public record: politicians reveal their positions by voting, DW-NOMINATE turns
roll calls into coordinates, and the Congressional Record ties party to language.
The anchor is (a) a public record, (b) behavior rather than anyone's rating,
(c) attributable to known actors, and (d) enormous.

Factuality is different in kind: it is **correspondence to world-states**, not
position among positions. There is no roll call for truth. Any feasible design
must either find data with the four anchor properties above, or honestly rename
what it measures. This document evaluates every candidate anchor we could find.

## 2. Candidate anchors, evaluated

| Anchor | Public record? | Judgment-free? | Outlet-attributable? | Coverage | Verdict |
|---|---|---|---|---|---|
| A. Court-adjudicated falsehoods (defamation judgments) | yes | yes (adjudicated) | yes | ~zero per outlet-year | footnote, not a signal |
| B. Resolvable claims vs. official statistics & event outcomes | yes | comparison is mechanical | yes | narrow slice of articles | **the structural twin — research-grade effort** |
| C. Revision/correction behavior (outlet's own edit history) | self-generated, capturable | yes | yes | every article | **cheapest honest signal — measures process, not truth** |
| D. Cross-outlet corroboration structure (our own clusters) | our corpus | mostly (alignment via embeddings) | yes | every story | **free by-product — measures isolation, not falsity** |
| E. Fact-checker verdicts (ClaimReview corpus) | published | no — human judgments | weakly (checks target claims/politicians) | sparse per outlet | validation target only, like AllSides for lean |

### B. Resolvable claims — the Congress-method equivalent

Some published claims resolve against public records with no judgment involved:
economic figures (BLS/BEA/FRED releases), election results (state returns, FEC),
census numbers, court outcomes (PACER/CourtListener), weather/disaster tolls
(official counts). "The unemployment rate fell to 3.9%" is checkable the way a
roll-call vote is checkable. Prior art exists and is active: the QuanTemp
benchmark for numerical claim verification (arXiv 2403.17169), Full Fact's
prototype Stats Checker verifying claims against official statistics, and the
CLEF CheckThat! lab series.

The costs, honestly: (1) **claim extraction requires an NLP model**, which
collides with METHODOLOGY D8 — resolvable only via a documented carve-out where
models may *extract and align* claims but never *evaluate* them, the mechanical
record-comparison doing all evaluation, with published human-audited extraction
samples; (2) only a minority of articles make resolvable claims, so per-outlet
sample sizes build slowly; (3) connectors to each statistical source must be
built and pinned. This is a research-grade pipeline — the strongest possible
anchor, and the most expensive.

### C. Revision behavior — cheap, behavioral, already half-built

An outlet's own edit history is a behavioral public record it generates about
itself. Track article revisions (we already poll every 6h; a revision mode
re-fetches each article on a decaying schedule for ~72h and diffs by content
hash) and measure: substantive-edit rate, **stealth-edit rate** (substantive
changes without a correction notice), correction latency, and correction-notice
practice. Strong prior art: NewsDiffs (2012–), the NewsEdits dataset (1.2M+
revision histories, NAACL 2022), DiffEngine/NewsSniffer.

The honest limit: this measures **process transparency, not accuracy**. Many
corrections can mean error-prone *or* conscientious. The literature (and every
incumbent's rubric) treats correction practice as a credibility criterion, but
it must be published under its real name: process behavior.

### D. Corroboration structure — free by-product of the lean pipeline

We already cluster same-event articles across 20 outlets. Within a cluster,
an outlet's *distinctive* claims (present in its version, absent from all
others) are measurable via embedding alignment — no truth judgment. Track the
**time-lagged corroboration rate**: distinctive claims that other outlets later
confirm (scoops) vs. those that never get picked up. Persistent epistemic
isolation is a signal; it is not falsity, and scoop-heavy outlets need the time
lag to avoid punishment for being first. Also measurable per cluster:
**wire fidelity** — drift between an outlet's rendering and the wire original
it credits.

### E. Fact-checker cross-reference — validation, not signal

The ClaimReview corpus (Google Fact Check Tools API, Data Commons feed;
FactCheck.org, PolitiFact, WaPo judgments) is open and machine-readable, but it
is human judgment with severe selection bias: checkers check what went viral,
which correlates with audience size and topic, not with outlet accuracy.
Feeding it into scoring would import the panel we exist to remove — the same
circularity rule as lean (D7): **incumbent factuality ratings (MBFC factual
reporting, Ad Fontes reliability) and ClaimReview hit-rates are validation
targets only.**

## 3. Proposed architecture (v0.5+, strictly gated)

- **F1 — process reliability** (from C): revision tracking, stealth-edit rate,
  correction latency/notice practice. Ships first; infrastructure is a small
  delta on the collector.
- **F2 — corroboration structure** (from D): unilateral-claim rate with time
  lag, wire fidelity. Ships from existing cluster data.
- **F3 — resolvable-claim accuracy** (from B): pilot on one domain first
  (economic statistics — cleanest official sources), expand only if the pilot
  survives audit. Requires the D8 extraction carve-out as a new ADR before any
  code.
- **Naming rule**: the published axis is called **process reliability**, never
  "factuality" or "truth", until/unless F3 matures enough to carry an accuracy
  component. A score is a claim; the name is part of the claim.
- **Validation gate** (mirror of M3): composite F-signal must rank-correlate
  ρ ≥ 0.6 with MBFC factual-reporting and Ad Fontes reliability ratings over
  the outlet sample. Below gate ⇒ iterate or kill, published either way. The
  bar is lower than lean's 0.7 because factuality prediction is documented in
  the literature as the harder task, and the incumbent ratings we validate
  against are themselves noisier on this axis.

## 4. What this can never do

No reproducible system measures truth at scale; claiming otherwise would just
hide the judgment somewhere. The incumbents' "factuality" grades are rubric
judgments of process plus reputation. Ours would be: measured process behavior
(F1), measured corroboration structure (F2), and — for one auditable slice of
claims — mechanical comparison against official records (F3). Narrower than
what a "truth score" implies, and honest about it. That honesty is the product.

## 5. Sequencing

Nothing here starts before the lean M3 gate reports. Then: F1 (revision
tracking is cheap and its data, like the corpus, gains value with every day it
runs — worth starting early), F2, F3 pilot. Each phase gets its own ADR with
kill criteria before code.

## 6. Sources

- QuanTemp numerical-claim benchmark: <https://arxiv.org/abs/2403.17169>
- Full Fact automated stats-checking: <https://fullfact.org/blog/2022/feb/claim-challenge-update/>
- CLEF CheckThat! fact-checking labs: <https://ceur-ws.org/Vol-4038/paper_53.pdf>
- NewsEdits revision dataset: <https://arxiv.org/abs/2206.07106>
- NewsDiffs: <https://en.wikipedia.org/wiki/NewsDiffs>
- Google Fact Check Tools API: <https://developers.google.com/fact-check/tools/api>
- Data Commons fact-check corpus: <https://datacommons.org/factcheck/blog>
- Baly et al., predicting factuality of sources (EMNLP 2018): <https://aclanthology.org/D18-1389/>
