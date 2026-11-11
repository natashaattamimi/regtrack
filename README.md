# regtrack

regtrack tracks what Indonesia's crypto regulation did to the market, and tests whether the
regulatory moves are visible in the data. The project is organised in phases. Phase 1 is the
current work. Phase 2 is the planned extension. Later phases will be shaped by ongoing events
and trends, so the plan below is a starting point rather than a fixed schedule.

## Phase 1: current stance and progress (as of 11 November 2026)

**Question.** Did the transfer of crypto oversight from Bappebti to the OJK (effective
10 January 2025) change the trajectory of Indonesian crypto transaction value?

**Current answer.** No break in monthly growth was detectable at the handover: a shift of
−14.3 percentage points per month, p = 0.117, not significant. The method can only detect breaks
of about 25 points per month or more at 80% power, so smaller effects cannot be ruled out. This is
a null result with a stated detection limit, not evidence of no effect.

### What the project contains

- **Public site.** Three self-contained pages, `index.html` (landing and summary),
  `dashboard.html` (monthly series, annual totals, event study, ASEAN map, method), and
  `datasets.html` (searchable catalogue and a regression lab). Each page embeds its data directly
  and loads nothing at run time.
- **Data (`data/`).** Monthly transaction value for January 2023 to September 2026 (45 months),
  with 14 months imputed from combined or cumulative reports and flagged. Also included are annual
  totals (2021–2025), regulatory milestones for Indonesia, Singapore, and the wider ASEAN region,
  the regulatory-intensity series, cumulative anchors from Bappebti reports, and the published
  event-study estimates. A Thai SEC file exists but holds only placeholders, with no values yet.
- **ITS estimator (`pipeline/its.py`).** An interrupted time series on monthly log growth, fit as
  segmented regression by OLS with Newey–West HAC standard errors. OLS is the fitting method; the
  design is the ITS. It includes a placebo battery of fake interruption dates and a minimum
  detectable-effect calculation.
- **Source provenance (`pipeline/ingest.py`).** Stores each raw source under its SHA-256 hash, with
  a manifest recording URL, publisher, and retrieval time, so revised figures never overwrite
  earlier snapshots.
- **Evidence-checked extraction (`pipeline/extract.py`).** Every extracted fact must carry an
  evidence snippet that appears verbatim in its source. The model call itself is a stub; no model
  is connected yet.
- **Tests (`tests/`).** 17 unit tests covering the estimator, which reproduces the published
  growth-break figures, plus ingest and extraction behaviour and data consistency checks.
- **Independent reproduction (`reverse_engineering/`).** A standard-library script that checks
  schemas, compares the embedded data with the CSVs, reconciles annual totals, reproduces the
  headline estimate, and writes a report.
- **Media attention (`tools/media_attention.py`).** Collects Indonesian crypto headlines per month
  and scores their tone with an LLM. Its output is not in the repository, and no page uses it yet.
- **Documents.** `analysis_plan.md` and `docs/video_transcript.md` are reconstructions, written
  after the results were known. They are not pre-registrations and not the original scripts.

### Verification done so far

- The 45 monthly values in `dashboard.html` match the monthly CSV exactly.
- Monthly sums match the annual totals to within rounding: 2023 exactly, 2024 within 0.01, 2025
  within 0.08.
- The growth-break estimate reproduces at −14.26 pp (published −14.3), p = 0.117.
- The placebo battery across 32 fake dates has no significant result at 5%.

### Known gaps and disagreements with the site

These need to be resolved or disclosed before the results are cited externally.

- The "drop imputed months" robustness check gives −21.4 pp (p = 0.109, n = 30). The site reports
  −11.8 pp (p = 0.282, n = 31). The construction used on the site is not documented.
- Adding a linear trend moves the estimate to −36.7 pp (p = 0.069). The site does not report this.
- The site's "roughly thirty-four points" minimum detectable break is not reproduced; the computed
  value is about 25.5.
- The site's level-shift result (+1163%) is not reproduced by a log-level model. The site's
  coefficients appear to be on levels, so the specification may differ from what is documented.
- The placebo p-value range differs between the site (0.12–0.63, six dates) and this
  recomputation (0.12–0.82, 32 dates). The two sets of fake dates are different.
- p-values use a normal approximation and are approximate at n ≈ 44.
- The original pipeline, test suite, pre-registered analysis plan, and video transcript are not in
  this repository. What is here is reconstructed.

## Phase 2: planned extension

Phase 2 extends the analysis in three directions. Each depends on data that Phase 1 does not yet
have, so each is marked with what is needed to start.

**Causal estimates with other countries.** The ASEAN milestone files already date regulatory
actions in Singapore, Thailand, Malaysia, Vietnam, the Philippines, and the wider region. The
planned design is a comparative ITS and, where pre-period data allow, a synthetic-control estimate
using these markets as controls. This needs monthly transaction or trading-volume series for each
country on a comparable basis. Thailand's SEC monthly reports are the first candidate; the
placeholder file exists but needs values entered from the published reports.

**Media-actor mapping.** The aim is to map who acts and who reports. This means linking each
regulatory output (law, rule, decision) to the actor that issued it and to the outlets that carried
it, with each mapping tagged as liberalising, restrictive, or procedural, and traceable to the
exact source sentence. The extraction module already enforces verbatim evidence snippets, which is
the base for this. It is not built yet: it needs the extraction model connected, a hand-coded
validation sample, and an agreement rate reported before any results are used.

**Media attention and tone.** Extend `tools/media_attention.py` so its output feeds the analysis.
This needs an API key, a hand-coded validation sample (the script writes 30 titles for this), and
a decision on whether a headline count is a fair proxy for public attention. Until then, the series
should be treated as exploratory.

Other extensions that are plausible given the current data include re-estimating the event study
when the ICEx launch and the August 2025 tax change have enough post-period months to separate
them, and adding the regulatory-intensity series as a control.

## Later phases

Later phases are not yet defined. They are expected to be shaped by what happens in the market and
in regulation over the coming months. New rules, a fresh tax change, or a shift in enforcement could
each open a new event to test, and a sharp change in volume or public attention could raise
questions the current design can't answer. Phase 2 should be reviewed against current events
before it is scheduled in detail, and this README should be updated when a phase closes.

## Running the checks

Requires Python 3 and nothing else.

```
python3 -m unittest discover -s tests -v
python3 reverse_engineering/reproduce.py
```

## Repository layout

- `index.html`, `dashboard.html`, `datasets.html`: the public site
- `data/`: CSVs behind the site
- `pipeline/`: ITS estimator, ingest, and extraction modules
- `tests/`: unit tests
- `reverse_engineering/`: independent recomputation and its report
- `tools/`: media-attention collector
- `analysis_plan.md`, `docs/video_transcript.md`: reconstructed documents, not the originals
