# How tiltmeter works

This page explains the whole system in plain language. No math. Every claim
here links to the technical spec, [METHODOLOGY.md](../METHODOLOGY.md), which
has the full details and sources. Words in *italics* are defined in the
[glossary](glossary.md).

## The problem

Some news outlets lean left. Some lean right. Companies already sell ratings
that say which is which. But those ratings come from panels of people voting
behind closed doors. You cannot check their work. You just have to trust them.

tiltmeter is different. It is a measuring tool. Anyone can run it, check every
step, and get the same numbers. If you think a rating is wrong, you can look
at the exact news stories behind it and see for yourself.

## The idea: a seating chart for the news

Picture every big news event of the month as a party. Not every outlet shows
up to every party. Each outlet picks which stories it covers. Those picks are
choices, and choices reveal leanings.

tiltmeter watches those choices. Outlets that keep covering the same kinds of
stories get seated near each other on a map. Outlets that make very different
picks sit far apart. That map is built from the outlets' own behavior. Nobody
votes on it. ([D3](../METHODOLOGY.md#d3-the-v1-signal-is-story-selection-framed-as-ideal-point-estimation))

One question is left: which side of the map is "left" and which is "right"?
We do not decide that by opinion either. We compare the language of each side
of the map to speeches from Congress. One pole will sound more like Democrats.
The other will sound more like Republicans. Party membership is a public fact,
not a rating. So the whole map is anchored to public records. ([D5](../METHODOLOGY.md#d5-the-axis-is-oriented-by-congressional-language-not-by-assumed-outlet-leans))

## The steps

1. **Collect.** Several times a day, tiltmeter reads the public article feeds
   of 20 US outlets, from far left to far right. It saves each new article
   with a *fingerprint* — a code that proves the text has not been changed.
   ([D9](../METHODOLOGY.md#d9-the-corpus-is-politics-section-rss-stored-locally-published-as-manifests))
2. **Group.** Articles about the same event are grouped into one story. Now we
   can see which outlets covered each story and which stayed silent.
3. **Map.** The pattern of "covered it / skipped it" choices places each
   outlet on the seating chart.
4. **Label the sides.** Speeches from Congress tell us which end of the chart
   is left and which is right.
5. **Score.** Each outlet gets a number from −1 (left) to +1 (right), plus an
   honest error range. Lean can drift, so every score has a date. There are no
   permanent labels. ([D6](../METHODOLOGY.md#d6-scores-are-time-series-with-uncertainty-never-permanent-labels))

## How we check ourselves

We compare our numbers to the big commercial ratings. If our order of outlets
is close to theirs, the method works. If not, we fix the method — in public,
with a written record of what changed and why. One thing worth knowing: the
commercial raters often disagree with *each other*. So matching them exactly
is not even the goal. ([D7](../METHODOLOGY.md#d7-validation-against-incumbent-raters-is-a-gate-with-published-sensitivity))

We also publish "what if" checks. What if we group stories a bit differently?
What if we use a different time window? If small choices like these swing the
scores a lot, you deserve to know. ([D7](../METHODOLOGY.md#d7-validation-against-incumbent-raters-is-a-gate-with-published-sensitivity))

## What tiltmeter does not do

- It does not rate truth or quality. A score near zero does not mean "good".
  It means "picks stories like the middle of Congress talks". ([D2](../METHODOLOGY.md#d2-version-1-rates-political-lean-only))
- It does not use AI models to judge the news. Studies show those models have
  leans of their own. ([D8](../METHODOLOGY.md#d8-no-llm-judgment-in-the-scoring-path))
- It does not let anyone — including us — nudge a rating by hand. There is no
  hand. ([D1](../METHODOLOGY.md#d1-ratings-come-from-a-reproducible-pipeline-not-editorial-judgment))

## Check our work

Every published score links to an evidence page: the real headlines that drove
it, the outlets that sat nearest, the error range, and the exact data batch
used. And anyone can rerun the whole thing with three commands and get the
same file, byte for byte. ([D10](../METHODOLOGY.md#d10-every-number-is-traceable-to-evidence-a-layman-can-read))

That is the whole point. Do not trust us. Check.
