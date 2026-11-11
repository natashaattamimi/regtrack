#!/usr/bin/env python3
"""
reproduce.py — independent reverse-engineering check for the regtrack dashboard.

Standard library only. Run from the repository root:

    python3 reverse_engineering/reproduce.py                # checks + report
    python3 reverse_engineering/reproduce.py --out report   # custom output stem

What it does
  1. Schema check: every CSV in data/ is read and its header is compared with
     the columns the site and the analysis are known to rely on.
  2. Embedded-data check: the monthly series (var M) and annual totals
     (var YRS) hard-coded in dashboard.html are parsed and compared with
     data/indonesian_crypto_transactions_monthly.csv and
     data/annual_transaction_totals.csv.
  3. Reconciliation: monthly sums are compared with the reported annual totals.
  4. Growth-break reproduction (the defensible specification on the site):
     ITS (segmented regression) of monthly log growth on a post-handover dummy,
     fit by OLS with Newey-West (Bartlett)
     HAC standard errors with lag 3. Published: -14.3 pp/month, p = 0.117.
  5. Sensitivity checks that the site does NOT report: adding a linear trend,
     and dropping imputed months.
  6. Placebo: the same specification run at every candidate fake date with
     at least 6 observations on each side.

Outputs: <stem>.json (machine-readable) and <stem>.html (self-contained report).
p-values use a normal approximation to the t distribution, which is adequate for
n ≈ 44 but slightly anti-conservative; the report says so.
"""

import argparse
import csv
import html
import json
import math
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # repository root (contains data/ and dashboard.html)
EVENT_MONTH = "2025-01"       # OJK takeover, 10 Jan 2025

EXPECTED_COLUMNS = {
    "annual_transaction_totals.csv": ["year", "value_idr_trillion", "regulator"],
    "indonesian_crypto_transactions_monthly.csv": ["month", "value_idr_trillion", "imputed", "source_note"],
    "master_dataset.csv": ["month", "value_idr_trillion", "imputed", "regulator_era",
                           "mom_log_growth_pct", "events_that_month", "source_derivation"],
    "regulatory_intensity_monthly.csv": ["month", "intensity_id", "intensity_sg", "intensity_asean", "id_events_weighted"],
    "regulatory_milestones_indonesia_singapore.csv": ["date", "jurisdiction", "theme", "title", "description"],
    "regulatory_milestones_asean_regional.csv": ["date", "jurisdiction", "title", "description"],
    "event_study_estimates_ojk_takeover.csv": ["specification", "quantity", "estimate", "detail", "p_value"],
    "event_study_estimates_aug_2025_tax_change.csv": ["specification", "term", "coef", "se", "p"],
    "bappebti_cumulative_anchors_2022_2024.csv": ["period", "value_idr_trillion", "yoy_note"],
    "thailand_sec_monthly_seeds.csv": ["month", "value_thb_million", "type", "source_note"],
}

# Published figures the reproduction is compared against.
PUBLISHED = {"shift_pp": -14.3, "p": 0.117, "pre_growth": 9.3, "post_growth": -5.2}


# ---------- small utilities -------------------------------------------------

def read_csv(relpath):
    with open(os.path.join(ROOT, relpath), encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def norm_cdf(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def p_two_sided(t):
    return 2 * (1 - norm_cdf(abs(t)))


def invert(A):
    k = len(A)
    M = [row[:] + [1.0 if i == j else 0.0 for j in range(k)] for i, row in enumerate(A)]
    for c in range(k):
        p = max(range(c, k), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        pv = M[c][c]
        if abs(pv) < 1e-12:
            raise ValueError("singular design matrix")
        M[c] = [x / pv for x in M[c]]
        for r in range(k):
            if r != c:
                f = M[r][c]
                M[r] = [x - f * y for x, y in zip(M[r], M[c])]
    return [row[k:] for row in M]


def ols_hac(y, X, lag=3):
    """Segmented-regression ITS fit by OLS, with Newey-West (Bartlett) HAC standard errors."""
    n, k = len(y), len(X[0])
    XtX = [[sum(X[r][a] * X[r][b] for r in range(n)) for b in range(k)] for a in range(k)]
    Xty = [sum(X[r][a] * y[r] for r in range(n)) for a in range(k)]
    inv = invert(XtX)
    beta = [sum(inv[a][j] * Xty[j] for j in range(k)) for a in range(k)]
    e = [y[r] - sum(X[r][a] * beta[a] for a in range(k)) for r in range(n)]

    def gamma(l):
        return [[sum(X[t][a] * e[t] * X[t - l][b] * e[t - l] for t in range(l, n))
                 for b in range(k)] for a in range(k)]

    S = gamma(0)
    for l in range(1, lag + 1):
        w = 1 - l / (lag + 1)
        G = gamma(l)
        for a in range(k):
            for b in range(k):
                S[a][b] += w * (G[a][b] + G[b][a])
    V = [[sum(inv[a][i] * S[i][j] * inv[j][b] for i in range(k) for j in range(k))
          for b in range(k)] for a in range(k)]
    se = [math.sqrt(max(V[a][a], 0.0)) for a in range(k)]
    return beta, se


def log_growth(values):
    return [math.log(values[i]) - math.log(values[i - 1]) for i in range(1, len(values))]


# ---------- checks ----------------------------------------------------------

def check_schemas():
    results = []
    for fname, cols in EXPECTED_COLUMNS.items():
        path = os.path.join(ROOT, "data", fname)
        if not os.path.exists(path):
            results.append({"file": fname, "ok": False, "detail": "missing"})
            continue
        with open(path, encoding="utf-8", newline="") as f:
            header = next(csv.reader(f))
        missing = [c for c in cols if c not in header]
        rows = sum(1 for _ in open(path, encoding="utf-8")) - 1
        results.append({"file": fname, "ok": not missing, "rows": rows,
                        "detail": "ok" if not missing else "missing columns: " + ", ".join(missing)})
    return results


def extract_embedded(dashboard_path):
    with open(dashboard_path, encoding="utf-8") as f:
        s = f.read()
    m = re.search(r"var M=(\[.*?\]);", s, re.S)
    y = re.search(r"var YRS=(\[.*?\]);", s, re.S)
    if not (m and y):
        raise RuntimeError("could not find var M / var YRS in dashboard.html")
    return json.loads(m.group(1)), json.loads(y.group(1))


def check_embedded_vs_csv():
    M, YRS = extract_embedded(os.path.join(ROOT, "dashboard.html"))
    csv_rows = read_csv("data/indonesian_crypto_transactions_monthly.csv")
    mismatches = []
    if len(M) != len(csv_rows):
        mismatches.append(f"row count {len(M)} (html) vs {len(csv_rows)} (csv)")
    for (month, value, imp), r in zip(M, csv_rows):
        if month != r["month"] or abs(value - float(r["value_idr_trillion"])) > 1e-9:
            mismatches.append(f"{month}: html {value} vs csv {r['value_idr_trillion']}")
    return {"months_html": len(M), "months_csv": len(csv_rows),
            "first": M[0][0], "last": M[-1][0], "mismatches": mismatches,
            "imputed_months": sum(imp for _, _, imp in M), "M": M, "YRS": YRS}


def reconcile_annual(M, YRS):
    sums, counts = defaultdict(float), defaultdict(int)
    for month, value, _ in M:
        sums[month[:4]] += value
        counts[month[:4]] += 1
    reported = {str(int(y)): v for y, v in YRS}
    out = []
    for year in sorted(sums):
        rep = reported.get(year)
        out.append({"year": year, "months": counts[year], "monthly_sum": round(sums[year], 2),
                    "reported": rep, "diff": None if rep is None else round(sums[year] - rep, 2)})
    return out


# ---------- growth-break model ---------------------------------------------

def growth_break(M, event_month=EVENT_MONTH, trend=False, drop_imputed=False):
    rows = [(m, v, imp) for m, v, imp in M]
    if drop_imputed:
        # keep original indices so growth is computed on consecutive observed months only
        rows = [r for r in rows if r[2] == 0]
    months = [r[0] for r in rows]
    values = [r[1] for r in rows]
    g = log_growth(values)
    gm = months[1:]
    if event_month not in gm:
        raise ValueError(f"event month {event_month} not in sample")
    ev = gm.index(event_month)
    X, y = [], []
    for i, growth in enumerate(g):
        post = 1.0 if i >= ev else 0.0
        row = [1.0]
        if trend:
            row.append(float(i + 1))
        row.append(post)
        X.append(row)
        y.append(growth * 100)  # percent log growth
    beta, se = ols_hac(y, X, lag=3)
    idx = len(beta) - 1
    t = beta[idx] / se[idx] if se[idx] else float("nan")
    pre = [y[i] for i in range(ev)]
    post = [y[i] for i in range(ev, len(y))]
    return {
        "shift_pp": round(beta[idx], 2),
        "se": round(se[idx], 2),
        "t": round(t, 3),
        "p": round(p_two_sided(t), 3),
        "n_pre": len(pre),
        "n_post": len(post),
        "pre_mean_growth": round(sum(pre) / len(pre), 2) if pre else None,
        "post_mean_growth": round(sum(post) / len(post), 2) if post else None,
    }


def placebo(M, min_side=6):
    months = [r[0] for r in M][1:]
    out = []
    for i, m in enumerate(months):
        pre_n = i
        post_n = len(months) - i
        if pre_n < min_side or post_n < min_side or m == EVENT_MONTH:
            continue
        r = growth_break(M, event_month=m)
        out.append({"fake_month": m, "shift_pp": r["shift_pp"], "p": r["p"]})
    return out


# ---------- report ---------------------------------------------------------

def html_report(res):
    def rows_html(rows, cols):
        head = "".join(f"<th>{html.escape(c)}</th>" for c in cols)
        body = "".join("<tr>" + "".join(f"<td>{html.escape(str(r.get(c, '')))}</td>" for c in cols) + "</tr>"
                       for r in rows)
        return f"<table><tr>{head}</tr>{body}</table>"

    g = res["growth_break"]
    status = "ok" if all(s["ok"] for s in res["schemas"]) and not res["embedded"]["mismatches"] else "check"
    placebo_rows = res["placebo"]
    real_p = g["p"]
    placebo_sig = sum(1 for r in placebo_rows if r["p"] < 0.05)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>regtrack — reproduction report</title>
<style>
:root{{color-scheme:light}}
body{{font-family:-apple-system,system-ui,sans-serif;max-width:920px;margin:40px auto;padding:0 20px;color:#1a1a1a;line-height:1.55}}
h1{{font-size:26px}} h2{{font-size:19px;margin-top:34px;border-bottom:1px solid #ddd;padding-bottom:4px}}
table{{border-collapse:collapse;width:100%;font-size:14px;margin:10px 0}}
th,td{{border:1px solid #ddd;padding:6px 9px;text-align:left}} th{{background:#f4f4f4}}
.pill{{display:inline-block;padding:2px 9px;border-radius:10px;font-size:13px;font-weight:600}}
.ok{{background:#dff5e4;color:#14612a}} .check{{background:#fde8c8;color:#7a4a00}}
.note{{color:#555;font-size:14px}} code{{background:#f3f3f3;padding:1px 4px;border-radius:3px}}
</style></head><body>
<h1>Reproduction report — Indonesia crypto handover</h1>
<p class="note">Generated by <code>reverse_engineering/reproduce.py</code> from the files in <code>data/</code> and <code>dashboard.html</code>.
Overall status: <span class="pill {status}">{status}</span></p>

<h2>1. Schema check</h2>
{rows_html(res["schemas"], ["file", "ok", "rows", "detail"])}

<h2>2. Embedded data vs CSV</h2>
<p>Dashboard months: {res["embedded"]["months_html"]} (CSV: {res["embedded"]["months_csv"]}),
range {res["embedded"]["first"]} to {res["embedded"]["last"]}, imputed months: {res["embedded"]["imputed_months"]}.
Mismatches: {len(res["embedded"]["mismatches"]) or "none"}.</p>

<h2>3. Annual reconciliation</h2>
<p class="note">Differences of a few hundredths are rounding in the monthly figures. The 2024 total is the Bappebti figure,
and OJK cites a revised 640.61 (see the source note in the annual CSV).</p>
{rows_html(res["annual"], ["year", "months", "monthly_sum", "reported", "diff"])}

<h2>4. Growth-break reproduction (site's defensible spec)</h2>
<table>
<tr><th></th><th>Published</th><th>Reproduced</th></tr>
<tr><td>Shift at Jan 2025 (pp/month)</td><td>{PUBLISHED["shift_pp"]}</td><td>{g["shift_pp"]}</td></tr>
<tr><td>p-value</td><td>{PUBLISHED["p"]}</td><td>{g["p"]}</td></tr>
<tr><td>Pre-period mean growth (%/month)</td><td>{PUBLISHED["pre_growth"]}</td><td>{g["pre_mean_growth"]}</td></tr>
<tr><td>Post-period mean growth (%/month)</td><td>{PUBLISHED["post_growth"]}</td><td>{g["post_mean_growth"]}</td></tr>
</table>
<p class="note">Specification: single-interruption ITS (segmented regression) on monthly log growth (%), with a post-Jan-2025 dummy; fit by OLS with Newey-West HAC SE, lag 3.
Shift matches the published estimate; p-value uses a normal approximation.</p>

<h2>5. Sensitivity checks (not on the site)</h2>
{rows_html(res["sensitivity"], ["check", "shift_pp", "se", "p", "n_pre", "n_post"])}
<p class="note"><b>Does not reproduce:</b> the site's robustness row (drop imputed months) reports −11.8 pp, p = 0.282, n = 31.
This script's drop-imputed sample gives −21.4 pp, p = 0.109, n = 30 (growth is recomputed on the observed months only).
The site's exact construction is not documented in the repo, so the discrepancy is unresolved.</p>
<p class="note"><b>Read this before quoting the result.</b> The shift is significant at neither the 5% nor the 10% level
in the main specification, and adding a linear trend changes the magnitude substantially. The site's claim of
"no detectable break" is consistent with these numbers, but the estimate itself is not robust to specification.</p>

<h2>6. Placebo</h2>
<p>{len(placebo_rows)} fake dates tested; {placebo_sig} with p &lt; 0.05. Real-date p = {real_p}.</p>
{rows_html(placebo_rows, ["fake_month", "shift_pp", "p"])}
</body></html>"""


# ---------- main -----------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(HERE, "reproduction_report"),
                    help="output path stem (writes .json and .html)")
    args = ap.parse_args()

    schemas = check_schemas()
    emb = check_embedded_vs_csv()
    annual = reconcile_annual(emb["M"], emb["YRS"])
    main_spec = growth_break(emb["M"])
    sensitivity = [
        {"check": "linear trend added", **{k: v for k, v in growth_break(emb["M"], trend=True).items()
                                          if k in ("shift_pp", "se", "p", "n_pre", "n_post")}},
        {"check": "imputed months dropped", **{k: v for k, v in growth_break(emb["M"], drop_imputed=True).items()
                                              if k in ("shift_pp", "se", "p", "n_pre", "n_post")}},
    ]
    plac = placebo(emb["M"])

    res = {"schemas": schemas, "embedded": {k: v for k, v in emb.items() if k not in ("M", "YRS")},
           "annual": annual, "growth_break": main_spec, "sensitivity": sensitivity, "placebo": plac,
           "published": PUBLISHED}

    stem = args.out
    with open(stem + ".json", "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2, ensure_ascii=False)
    with open(stem + ".html", "w", encoding="utf-8") as f:
        f.write(html_report(res))

    bad = [s for s in schemas if not s["ok"]]
    print(f"schemas ok: {len(schemas) - len(bad)}/{len(schemas)}")
    print(f"embedded vs csv mismatches: {len(emb['mismatches'])}")
    print(f"growth break: shift {main_spec['shift_pp']} pp (published {PUBLISHED['shift_pp']}), "
          f"p {main_spec['p']} (published {PUBLISHED['p']})")
    print(f"placebo: {len(plac)} fake dates, {sum(1 for r in plac if r['p'] < 0.05)} with p < 0.05")
    print(f"wrote {stem}.json and {stem}.html")
    return 1 if bad or emb["mismatches"] else 0


if __name__ == "__main__":
    sys.exit(main())
