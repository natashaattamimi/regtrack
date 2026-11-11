# Reverse engineering the regtrack site

This folder documents how the regtrack site is built from its data and checks the headline
numbers independently. It was produced by reading the existing files, not from the original
source pipeline, which is not in this repository (see "What is missing" below).

Contents:

- `reproduce.py` — standard-library Python script. It checks the data, reproduces the growth-break
  estimate, runs sensitivity and placebo checks, and writes a report.
- `reproduction_report.html` and `reproduction_report.json` — the output of the script.
- `README.md` — this document.

Run it from the repository root. It needs Python 3 and nothing else:

```
python3 reverse_engineering/reproduce.py
```

## How the site is built

The site is three self-contained HTML files with no build step and no runtime data fetches.
Every number the pages show is written into the HTML as a JavaScript literal. The CSV files in
`data/` are the human-readable copies of those literals. Nothing in the pages reads `data/` at
run time, so changing a CSV does not change the site until someone copies the new values into
the HTML.

| Page | What it shows | Data it embeds |
|---|---|---|
| `index.html` | Landing page: the question, the monthly record, three findings | `M`, `EVTS`, `YEARS` |
| `dashboard.html` | Full analysis: market series, annual totals, event study, ASEAN map, method | `M` (monthly series), `YRS` (annual totals), `EV` (regulatory events), `THEMES`, `GEO`, `KPI`, `STEPS`, a hard-coded naive ITS fit |
| `datasets.html` | Searchable catalog of records and a regression "analyse" lab | `DATA`, `RECS`, `VARS`, `PRESETS` |

The analysis itself is not run in the browser. The event-study results (−14.3 pp, p = 0.117, and
the level-shift model that fails placebo) are typed in as text. The "analyse lab" in
`datasets.html` runs regressions live on the monthly panel in JavaScript.

## Data files and what they feed

| File | Rows | Role | Used by |
|---|---|---|---|
| `indonesian_crypto_transactions_monthly.csv` | 45 (Jan 2023 – Sep 2026) | Monthly transaction value, Rp trillion, with `imputed` flag | Matches `var M` in `dashboard.html` exactly |
| `annual_transaction_totals.csv` | 5 (2021–2025) | Annual totals by regulator | Matches `var YRS` |
| `master_dataset.csv` | 45 | Monthly panel with log growth, regulator era, and events | Analysis panel |
| `regulatory_intensity_monthly.csv` | 45 | Monthly regulatory-event intensity (Indonesia, Singapore, ASEAN) | Event dummies |
| `regulatory_milestones_indonesia_singapore.csv` | 17 | Dated milestones with theme | Milestone table |
| `regulatory_milestones_asean_regional.csv` | 13 | Dated milestones for other ASEAN jurisdictions | ASEAN map |
| `event_study_estimates_ojk_takeover.csv` | 6 | Published event-study outputs for the Jan 2025 handover | Documentation of results |
| `event_study_estimates_aug_2025_tax_change.csv` | 5 | Published estimates for the Aug 2025 tax change | Documentation of results |
| `bappebti_cumulative_anchors_2022_2024.csv` | 9 | Cumulative reported figures used to back out monthly values | Source for the imputed 2023–2024 months |
| `thailand_sec_monthly_seeds.csv` | 10 | Placeholders for Thai SEC monthly figures (no values yet) | Not used in any calculation |

14 of the 45 months are imputed: nine in 2023, two in Feb–Mar 2025, and three in Mar–May 2026. Their
source notes say they were derived from combined or cumulative reports, usually by splitting a reported
total evenly. Those months are flagged `imputed = 1`, and the dashboard draws them as hollow points.

## The event study

The defensible specification is a growth-rate break. Monthly log growth in transaction value is
regressed on a dummy that switches on in January 2025, with Newey-West (Bartlett) standard errors
at lag 3. The estimate is −14.3 percentage points per month, p = 0.117, which is not significant.

The level-shift specification (the one on the site marked "misspecified") is not reproduced here.
The published event-study CSV reports that placebo dates produce level shifts of +230% to +1750%,
so the design is discarded.

## What the reproduction confirms

- All 10 CSV files have the columns the analysis expects.
- The 45 monthly values in `dashboard.html` match the monthly CSV exactly, with no differences.
- Monthly sums agree with the annual totals within rounding: 2023 exactly, 2024 within 0.01,
  2025 within 0.08.
- The growth-break estimate reproduces: −14.26 pp with HAC standard error 9.11, t = −1.57,
  p = 0.117. This matches the published −14.3 and p = 0.117.
- The placebo check shows no fake date significant at 5%. This agrees with the site's statement
  that none of the fake dates is significant.

## What the reproduction does not confirm

- **Robustness, dropping imputed months.** The site reports −11.8 pp, p = 0.282, n = 31. This
  script gets −21.4 pp, p = 0.109, n = 30. The exact construction is not documented, so the
  difference is unresolved.
- **Placebo p-values.** The site cites six fake dates with p between 0.12 and 0.63. This script
  tests all 32 candidate months with at least six observations on each side, and the p-values
  run from 0.12 to 0.82. The sets are different, so the two sets of numbers are not directly
  comparable.
- **Sensitivity to specification.** Adding a linear time trend to the same model moves the
  estimate to −36.7 pp with p = 0.069. The site does not mention this. The conclusion "no
  detectable break" is still consistent with these numbers, but the size of the effect depends
  heavily on the specification.
- **p-values.** This script uses a normal approximation to the t distribution. With 44
  observations that is close but slightly optimistic, so the true p-values are a little larger.

## Notes on `tools/media_attention.py`

This script collects Indonesian crypto headlines from Google News, classifies each headline's
tone with an LLM, and writes a monthly tone index to `data/media_attention.csv`. Three things
are worth knowing before relying on it:

1. Its output file is not in the repository, and no HTML page loads it. The dashboard's
   "attention" counts are computed from the regulatory events, not from this script. So this
   module does not currently feed the live site, despite the docstring saying the dashboard
   "renders the series automatically".
2. The docstring describes the search query as `crypto OR aset kripto`, but the code uses
   `"crypto" OR "aset kripto" OR "bitcoin"`. The code is the reliable source.
3. Its agreement rate is only meaningful after a person hand-codes the 30-title validation
   sample. The script writes that sample but does not contain any hand-coded labels.

## Rebuilt components

The original ingest and extraction pipeline, test suite, `analysis_plan.md`, and
`docs/video_transcript.md` were not in the repository. They have been rebuilt from the site and the
data. Each rebuilt file says so in its header:

- `pipeline/its.py` — growth-break estimator and placebo battery. Reproduces −14.26 pp and p = 0.117.
- `pipeline/ingest.py` — content-hashed raw snapshots with a provenance manifest.
- `pipeline/extract.py` — LLM extraction in which every fact must carry a verbatim evidence snippet.
  The model call is a stub; no model is wired in.
- `tests/test_pipeline.py` — 17 tests (`python3 -m unittest discover -s tests`).
- `analysis_plan.md` — a post-hoc reconstruction, **not** a pre-registration.
- `docs/video_transcript.md` — the 60-second cut, rebuilt from the tour script.

These rebuilds show that the documented numbers can be recomputed from the data. They do not show
that the original pipeline did what the product tour describes.

Two claims on the site do not match the computed values:

- The tour says the design detects breaks of "roughly thirty-four points a month". The standard
  error gives about 25.5 points at 80% power.
- The site's level-shift result (+1163%) is not reproduced by a log-level model. The site's
  coefficients are stated on levels, so the specification may be different from what was documented.

## Limits of this reconstruction

The data-flow description is inferred from the files, not taken from a build script, because none
exists. The numbers were checked by independent recomputation, not by re-running the original
analysis. Where the site and this recomputation differ, the report states both values and leaves
the question open.
