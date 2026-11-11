#!/usr/bin/env python3
"""
media_attention.py — build the monthly Indonesian crypto media-attention series
for the Regulatory Tracker's public-attention module.

What it does
  1. Gathers Indonesian crypto coverage per month from Google News RSS
     (query "crypto OR aset kripto", Indonesian + English, 2023-01 .. 2026-09).
  2. Counts articles per month and classifies each title's tone via an
     LLM endpoint (OpenAI-compatible; point LITELLM_BASE/LITELLM_KEY at your
     LiteLLM gateway, or OPENAI_API_KEY at api.openai.com).
  3. Aggregates a monthly tone index in [-1, +1] = (pos - neg) / total.
  4. Holds out 30 random titles for hand-coding: write your own -1/0/+1 in
     validation_subsample.csv, rerun with --validate, and the script reports
     agreement. Do not skip this — the module's numbers are only as good as
     the validated tone classifier.

Output: data/media_attention.csv
  month,n_articles,tone_index,agreement_rate
Drop that file into the site's data/ folder — the dashboard's Method tab
renders the series and the media-vs-policy lead/trail test automatically.

Usage
  python3 media_attention.py                 # collect + classify + write CSV
  python3 media_attention.py --validate validation_subsample.csv

Notes
  - Google News RSS counts are an attention proxy (coverage volume), not a
    census of all articles. Note this in any write-up.
  - Rate-limit friendly: sleeps between requests. ~45 monthly queries.
"""

import io, os, re, sys, time, base64, json, random, urllib.request, urllib.parse
import xml.etree.ElementTree as ET

YEAR_MONTHS = [(y, m) for y in (2023, 2024, 2025, 2026) for m in range(1, 13)
               if not (y == 2026 and m > 9)]
QUERY = '("crypto" OR "aset kripto" OR "bitcoin") Indonesia'
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
OUT_CSV = os.path.join(DATA_DIR, "media_attention.csv")
SUB_CSV = "validation_subsample.csv"

API_BASE = os.environ.get("LITELLM_BASE", "https://api.openai.com/v1")
API_KEY = os.environ.get("LITELLM_KEY") or os.environ.get("OPENAI_API_KEY")
MODEL = os.environ.get("MEDIA_TONE_MODEL", "gpt-4o-mini")


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (regtrack-research)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "ignore")


def month_bounds(y, m):
    import calendar
    last = calendar.monthrange(y, m)[1]
    return f"after:{y}-{m:02d}-01", f"before:{y}-{m:02d}-{last:02d}"


def collect_month(y, m):
    aft, bef = month_bounds(y, m)
    titles, seen = [], set()
    for lang in ("hl=id&gl=id&ceid=ID:id", "hl=en&gl=US&ceid=US:en"):
        q = urllib.parse.quote(f"{QUERY} {aft} {bef}")
        url = f"https://news.google.com/rss/search?q={q}&{lang}"
        try:
            xml_txt = http_get(url)
        except Exception as exc:
            print(f"  ! fetch failed ({exc}); retrying once")
            time.sleep(4)
            try:
                xml_txt = http_get(url)
            except Exception:
                continue
        root = ET.fromstring(xml_txt)
        for item in root.iter("item"):
            t = re.sub(r"<[^>]+>", "", item.findtext("title") or "").strip()
            key = t[:80].lower()
            if t and key not in seen:
                seen.add(key)
                titles.append(t)
        time.sleep(2)
    return titles


def classify_tone(titles):
    """Return {title: -1|0|+1} using an LLM. -1 negative, 0 neutral, +1 positive
    toward crypto adoption/regulation in Indonesia (not sentiment about price!)."""
    if not API_KEY:
        raise SystemExit("Set LITELLM_KEY/OPENAI_API_KEY to classify tone.")
    out = {}
    batch = titles[:400]
    for i in range(0, len(batch), 20):
        chunk = batch[i:i + 20]
        lines = "\n".join(f"{j+1}. {t}" for j, t in enumerate(chunk))
        body = {
            "model": MODEL,
            "temperature": 0,
            "messages": [
                {"role": "system", "content":
                 "You code news headlines for tone toward cryptocurrency adoption and "
                 "crypto regulation in Indonesia. Score each headline: -1 (negative: fraud, "
                 "losses, crackdown, warning), 0 (neutral/factual), +1 (positive: growth, "
                 "adoption, innovation, supportive policy). Reply ONLY with JSON: "
                 '{"scores":[<int>, ...]} matching the numbered lines.'},
                {"role": "user", "content": lines},
            ],
        }
        req = urllib.request.Request(
            f"{API_BASE}/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            txt = json.loads(r.read())["choices"][0]["message"]["content"]
        scores = json.loads(re.search(r"\{.*\}", txt, re.S).group())["scores"]
        for j, t in enumerate(chunk):
            out[t] = max(-1, min(1, int(scores[j])))
        time.sleep(1)
    return out


def write_validation_subsample(all_titles, tones, n=30):
    sample = random.sample(all_titles, min(n, len(all_titles)))
    with open(SUB_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv_writer(f)
        w.writerow(["title", "llm_tone", "hand_tone", ""])
        for t in sample:
            w.writerow([t, tones.get(t, ""), "", ""])
    print(f"Hand-code the hand_tone column in {SUB_CSV} (-1/0/+1), then rerun with --validate.")


def csv_writer(f):
    import csv
    return csv.writer(f)


def validate(path):
    import csv
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    coded = [r for r in rows if r["hand_tone"] and r["llm_tone"]]
    agree = sum(1 for r in coded if int(r["hand_tone"]) == int(r["llm_tone"]))
    rate = agree / len(coded) if coded else 0
    print(f"Agreement: {agree}/{len(coded)} = {rate:.0%}")
    if rate < 0.7:
        print("Below 70% — treat tone_index as unreliable; re-prompt or hand-code more.")
    return rate


def main():
    if "--validate" in sys.argv:
        path = sys.argv[sys.argv.index("--validate") + 1] if len(sys.argv) > sys.argv.index("--validate") + 1 else SUB_CSV
        validate(path)
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    all_titles, per_month = [], {}
    print("Collecting coverage from Google News RSS ...")
    for y, m in YEAR_MONTHS:
        titles = collect_month(y, m)
        per_month[f"{y}-{m:02d}"] = titles
        all_titles += titles
        print(f"  {y}-{m:02d}: {len(titles)} headlines")
    print(f"Total {len(all_titles)} headlines; classifying tone ...")
    tones = classify_tone(all_titles)
    rows = [["month", "n_articles", "tone_index", "agreement_rate"]]
    for key, titles in per_month.items():
        scored = [tones.get(t, 0) for t in titles]
        tone = (sum(scored) / len(scored)) if scored else ""
        rows.append([key, len(titles), f"{tone:.3f}" if tone != "" else "", ""])
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv_writer(f)
        w.writerows(rows)
    write_validation_subsample(all_titles, tones)
    print(f"Wrote {OUT_CSV}. Next: hand-code {SUB_CSV}, run --validate, "
          f"put the agreement rate in the CSV, then redeploy the site.")


if __name__ == "__main__":
    main()
