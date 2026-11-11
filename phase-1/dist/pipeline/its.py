"""
its.py — interrupted time series estimator and placebo battery.

Stdlib only. Implements the growth-rate break specification described in the
dashboard's Method tab:

  * outcome: monthly log growth of transaction value, in percent
  * regressor: post-interruption dummy (plus optional linear trend)
  * estimation: segmented regression (ITS) fit by OLS, with Newey-West
    (Bartlett) HAC standard errors, lag 3. OLS is the fitting method; the
    design is the interrupted time series.
  * placebo battery: the same model re-run at fake interruption dates

The level-shift specification is included only so the failure can be
reproduced; the site treats it as misspecified.
"""

import math

HAC_LAG = 3
MIN_SIDE = 6


def _invert(A):
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


def its_segmented_fit(y, X, lag=HAC_LAG):
    """Fit the segmented-regression ITS model by OLS; return (beta, se) with
    Newey-West HAC standard errors."""
    n, k = len(y), len(X[0])
    XtX = [[sum(X[r][a] * X[r][b] for r in range(n)) for b in range(k)] for a in range(k)]
    Xty = [sum(X[r][a] * y[r] for r in range(n)) for a in range(k)]
    inv = _invert(XtX)
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
    return beta, [math.sqrt(max(V[a][a], 0.0)) for a in range(k)]


def p_two_sided(t):
    """Normal approximation. Slightly optimistic at n ≈ 44."""
    return 2 * (1 - 0.5 * (1 + math.erf(abs(t) / math.sqrt(2))))


def log_growth_pct(values):
    return [100 * (math.log(values[i]) - math.log(values[i - 1])) for i in range(1, len(values))]


def growth_break(months, values, event_month, trend=False):
    """Growth-rate break at event_month. Returns a dict of estimates."""
    g = log_growth_pct(values)
    gm = months[1:]
    if event_month not in gm:
        raise ValueError(f"{event_month} not in sample")
    ev = gm.index(event_month)
    X = []
    for i in range(len(g)):
        row = [1.0]
        if trend:
            row.append(float(i + 1))
        row.append(1.0 if i >= ev else 0.0)
        X.append(row)
    beta, se = its_segmented_fit(g, X)
    j = len(beta) - 1
    t = beta[j] / se[j] if se[j] else float("nan")
    pre, post = g[:ev], g[ev:]
    return {
        "event_month": event_month,
        "shift_pp": beta[j],
        "se": se[j],
        "t": t,
        "p": p_two_sided(t),
        "n_pre": len(pre),
        "n_post": len(post),
        "pre_mean_growth": sum(pre) / len(pre) if pre else None,
        "post_mean_growth": sum(post) / len(post) if post else None,
    }


def placebo_battery(months, values, event_month, min_side=MIN_SIDE):
    """Re-run the break at every candidate fake date with enough data each side."""
    out = []
    gm = months[1:]
    for i, m in enumerate(gm):
        if m == event_month:
            continue
        if i < min_side or (len(gm) - i) < min_side:
            continue
        r = growth_break(months, values, m)
        out.append({"fake_month": m, "shift_pp": r["shift_pp"], "p": r["p"]})
    return out


def level_shift_its(months, values, event_month):
    """Naive level-shift ITS on log levels (constant, trend, post, trend × post).

    RECONSTRUCTION: the site's level model was fitted on levels, not logs (its
    stated coefficients are const 2.0245, post 2.5363), so this function does not
    reproduce the site's +1163% estimate. It is included only to show the
    misspecification on this data. Do not quote its output as a finding."""
    y = [math.log(v) for v in values]
    ev = months.index(event_month)
    X, t_index = [], []
    for i in range(len(y)):
        t = i + 1
        post = 1.0 if i >= ev else 0.0
        X.append([1.0, float(t), post, float(max(0, t - ev))])
    beta, se = its_segmented_fit(y, X)
    j = 2
    return {"post_shift_log": beta[j], "se": se[j],
            "t": beta[j] / se[j] if se[j] else float("nan"),
            "p": p_two_sided(beta[j] / se[j]) if se[j] else float("nan")}


def minimum_detectable_effect(se, alpha_z=1.96, power_z=0.8416):
    """Smallest |shift| detectable with 80% power at the 5% level, given the
    estimated standard error of the break coefficient (percentage points/month)."""
    return (alpha_z + power_z) * se
