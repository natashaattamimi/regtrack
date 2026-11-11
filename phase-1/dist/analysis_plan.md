# Analysis plan — Bappebti → OJK crypto oversight handover

## Question

Did the transfer of crypto oversight from Bappebti to the OJK (effective 10 January 2025) change
the trajectory of Indonesian crypto transaction value?

## Outcome and sample

- Outcome: monthly crypto transaction value in Indonesia, Rp trillion (`data/indonesian_crypto_transactions_monthly.csv`).
- Sample: January 2023 to September 2026, 45 months, 23 pre-handover and 21 post-handover growth observations.
- Growth outcome: monthly log growth, in percent, `100 × Δlog(value)`.
- Imputation: 14 of 45 months are derived from combined or cumulative reports and flagged `imputed = 1`.
  They are kept in the main specification and dropped in a robustness check.

## Primary specification

Growth-rate interrupted time series:

    growth_t = α + β · post_t + ε_t,    post_t = 1 if t ≥ Jan 2025

This is a single-interruption ITS, estimated as segmented regression: the model is fit by ordinary
least squares, with Newey–West (Bartlett) HAC standard errors, lag 3, to account for serial
correlation. The estimand is β, the change in monthly growth at the interruption, in percentage
points per month. OLS is the fitting method here, not the design; the design is the ITS.

## Placebo battery

The same model is re-run at every candidate fake interruption date with at least six months of
data on each side. A real break is credible only if fake dates do not produce comparable
estimates. The battery is reported in full.

## Robustness

1. Drop the imputed months.
2. Add a linear time trend.

These are reported alongside the primary estimate. Neither was designated as primary.

## Rejected specification

A naive level-shift ITS was also run. Its placebo dates produced shifts of +230% to +1750% (per
`data/event_study_estimates_ojk_takeover.csv`), so the design was judged misspecified and its
estimates are not quoted as findings.

## Power

The minimum detectable break at 80% power and the 5% level is approximately 2.8 × SE(β). With the
reproduced SE of 9.11, this is about 25.5 percentage points per month. The dashboard and tour
describe the threshold as "roughly 34"; that figure has no computation in the repository, and this
plan uses the computed value.

## Reporting rules

- Report the null as a null. "No change was detectable at the interruption" is the claim; "no effect"
  is not.
- Mark every derived month as derived in any chart or table.
- Disclose revisions to published figures. The FY2024 total is 650.61 in the Bappebti series and 640.61
  as cited by OJK.
- Quote the normal-approximation p-values as approximate at n ≈ 44.

## Known limitations

- Forty-five observations and one interruption give little power.
- The specification is sensitive: adding a linear trend moves β to about −36.7 pp (p = 0.069).
- Concurrent events (the August 2025 tax change, the August–September 2025 unrest, and the March 2026
  ICEx launch) are not separately identified.
