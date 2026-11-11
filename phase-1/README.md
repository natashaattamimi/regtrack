# regtrack

A small, self-contained record of Indonesia's move of crypto oversight from Bappebti to the OJK
(effective 10 January 2025), and an interrupted time series (ITS) test of whether transaction value
changed at that point.

The headline finding is a null: no break in monthly growth was detectable at the handover
(−14.3 percentage points per month, p = 0.117), with a stated detection limit and placebo tests.
Read the caveats before quoting it.

## Contents

- `index.html`, `dashboard.html`, `datasets.html` — the three pages of the site. Each embeds its data directly; nothing loads at run time.
- `data/` — the CSVs behind the pages. 45 monthly observations, Jan 2023 to Sep 2026. 14 months are imputed from combined or cumulative reports and flagged.
- `pipeline/` — ITS estimator (`its.py`), content-hashed source snapshots (`ingest.py`), and evidence-checked extraction (`extract.py`).
- `tests/` — unit tests for the pipeline, including checks that the estimator reproduces the published figures.
- `reverse_engineering/` — an independent recomputation of the headline numbers, with a report.
- `analysis_plan.md` — a **reconstruction** of the analysis plan, written after the results. It is not the original pre-registration.
- `docs/video_transcript.md` — a **reconstruction** of the 60-second video script.
- `tools/media_attention.py` — a script that collects headline counts and tone for a media-attention series. Its output is not in this repository and no page loads it yet.

## Running the checks

Requires Python 3 and nothing else.

```
python3 -m unittest discover -s tests -v
python3 reverse_engineering/reproduce.py
```

## Reading the results

- The primary specification is segmented regression fit by OLS, with Newey–West (HAC) standard errors. OLS is the fitting method; the design is the ITS.
- The minimum detectable break at 80% power is about 25.5 points per month. The site's "roughly thirty-four" is not reproduced.
- The "drop imputed months" robustness check does not reproduce the site's figures (−21.4 pp here, against −11.8 on the site).
- Adding a linear trend moves the estimate to about −36.7 pp (p = 0.069).
- p-values use a normal approximation and are approximate at n ≈ 44.

## Status of rebuilt files

Several files were not in the original repository and have been reconstructed from the site and
data: the pipeline code, the tests, `analysis_plan.md`, and `docs/video_transcript.md`. They show
that the documented numbers can be recomputed. They do not show that the original pipeline did
what the site describes.
