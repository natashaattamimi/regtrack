"""
Test suite for the regtrack pipeline. Standard library only.

    python3 -m unittest discover -s tests -v
"""

import csv
import json
import os
import re
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

import extract  # noqa: E402
import ingest  # noqa: E402
import its  # noqa: E402


def load_monthly():
    with open(os.path.join(ROOT, "data", "indonesian_crypto_transactions_monthly.csv"), encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return ([r["month"] for r in rows],
            [float(r["value_idr_trillion"]) for r in rows],
            [int(r["imputed"]) for r in rows])


def load_embedded_M():
    with open(os.path.join(ROOT, "dashboard.html"), encoding="utf-8") as f:
        s = f.read()
    return json.loads(re.search(r"var M=(\[.*?\]);", s, re.S).group(1))


class TestIngest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.raw = os.path.join(self.tmp, "raw")
        self.mpath = os.path.join(self.raw, "manifest.json")
        self.src = os.path.join(self.tmp, "report.txt")
        with open(self.src, "w", encoding="utf-8") as f:
            f.write("Jan+Feb = 55.26")

    def test_same_bytes_are_stored_once(self):
        a = ingest.add_snapshot(self.src, "https://example.test/a", "Bappebti", self.raw, self.mpath)
        b = ingest.add_snapshot(self.src, "https://example.test/b", "Bappebti", self.raw, self.mpath)
        self.assertEqual(a["sha256"], b["sha256"])
        self.assertEqual(len(ingest.load_manifest(self.mpath)["snapshots"]), 1)

    def test_changed_bytes_create_new_snapshot(self):
        ingest.add_snapshot(self.src, "https://example.test/a", "Bappebti", self.raw, self.mpath)
        with open(self.src, "a", encoding="utf-8") as f:
            f.write(" revised")
        ingest.add_snapshot(self.src, "https://example.test/a", "Bappebti", self.raw, self.mpath)
        self.assertEqual(len(ingest.load_manifest(self.mpath)["snapshots"]), 2)

    def test_verify_detects_tampering(self):
        e = ingest.add_snapshot(self.src, "https://example.test/a", "Bappebti", self.raw, self.mpath)
        self.assertEqual(ingest.verify(self.raw, self.mpath), [])
        with open(os.path.join(self.raw, e["file"]), "a", encoding="utf-8") as f:
            f.write("x")
        self.assertTrue(any("hash mismatch" in p for p in ingest.verify(self.raw, self.mpath)))


class TestExtract(unittest.TestCase):
    SOURCE = "On 1 August 2025 the sales tax rose from 0.1% to 0.21%. VAT was removed."
    HASH = "abc123"

    def rec(self, **kw):
        base = {"date": "2025-08", "jurisdiction": "Indonesia", "type": "restrictive",
                "evidence": "the sales tax rose from 0.1% to 0.21%", "value": 0.21, "unit": "%"}
        base.update(kw)
        return base

    def test_accepts_verbatim_evidence(self):
        self.assertEqual(extract.validate_record(self.rec(source_sha256=self.HASH), self.SOURCE, self.HASH), [])

    def test_rejects_evidence_not_in_source(self):
        probs = extract.validate_record(self.rec(evidence="tax was abolished", source_sha256=self.HASH),
                                        self.SOURCE, self.HASH)
        self.assertIn("evidence snippet not found in source text", probs)

    def test_rejects_wrong_source_hash(self):
        probs = extract.validate_record(self.rec(source_sha256="other"), self.SOURCE, self.HASH)
        self.assertIn("source hash does not match the document", probs)

    def test_rejects_bad_date_and_type(self):
        probs = extract.validate_record(self.rec(date="2025-13", type="bullish", source_sha256=self.HASH),
                                        self.SOURCE, self.HASH)
        self.assertTrue(any("bad date" in p for p in probs))
        self.assertTrue(any("bad type" in p for p in probs))

    def test_extract_splits_accepted_and_rejected(self):
        good = self.rec()
        bad = self.rec(evidence="invented sentence")
        stub = lambda prompt: json.dumps([good, bad])
        accepted, rejected = extract.extract(self.SOURCE, self.HASH, stub)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(len(rejected), 1)

    def test_non_json_model_output_is_reported(self):
        accepted, rejected = extract.extract(self.SOURCE, self.HASH, lambda p: "not json")
        self.assertEqual(accepted, [])
        self.assertIn("error", rejected[0])


class TestITS(unittest.TestCase):
    """The estimator must reproduce the published growth-break numbers."""

    @classmethod
    def setUpClass(cls):
        cls.months, cls.values, cls.imputed = load_monthly()

    def test_growth_break_matches_published(self):
        r = its.growth_break(self.months, self.values, "2025-01")
        self.assertAlmostEqual(r["shift_pp"], -14.3, delta=0.1)   # published −14.3
        self.assertAlmostEqual(r["p"], 0.117, delta=0.002)         # published 0.117
        self.assertEqual(r["n_pre"], 23)
        self.assertEqual(r["n_post"], 21)

    def test_pre_and_post_means_match_published(self):
        r = its.growth_break(self.months, self.values, "2025-01")
        self.assertAlmostEqual(r["pre_mean_growth"], 9.3, delta=0.5)   # published +9.3%/month
        self.assertAlmostEqual(r["post_mean_growth"], -5.2, delta=0.5) # published −5.2%/month

    def test_placebo_battery_has_no_significant_fake_date(self):
        plac = its.placebo_battery(self.months, self.values, "2025-01")
        self.assertGreater(len(plac), 10)
        self.assertTrue(all(p["p"] > 0.05 for p in plac))

    def test_level_shift_spec_is_run_but_not_used(self):
        r = its.level_shift_its(self.months, self.values, "2025-01")
        self.assertIn("post_shift_log", r)

    def test_mde_is_reported_not_claimed(self):
        r = its.growth_break(self.months, self.values, "2025-01")
        mde = its.minimum_detectable_effect(r["se"])
        # Recorded so the power claim can be checked. Not asserted against the
        # site's "about 34 points" figure, which has no computation in the repo.
        self.assertGreater(mde, 0)

    def test_embedded_series_equals_csv(self):
        emb = load_embedded_M()
        self.assertEqual([m for m, _, _ in emb], self.months)
        self.assertEqual([v for _, v, _ in emb], self.values)


class TestDataConsistency(unittest.TestCase):
    def test_annual_totals_reconcile_within_rounding(self):
        months, values, _ = load_monthly()
        sums = {}
        for m, v in zip(months, values):
            sums[m[:4]] = sums.get(m[:4], 0.0) + v
        with open(os.path.join(ROOT, "data", "annual_transaction_totals.csv"), encoding="utf-8") as f:
            ann = {r["year"]: float(r["value_idr_trillion"]) for r in csv.DictReader(f)}
        for y in ("2023", "2024", "2025"):
            self.assertLess(abs(sums[y] - ann[y]), 0.1, msg=y)

    def test_imputed_count_is_fourteen(self):
        _, _, imputed = load_monthly()
        self.assertEqual(sum(imputed), 14)


if __name__ == "__main__":
    unittest.main()
