"""
extract.py — structured extraction with mandatory evidence snippets.

The original design used an LLM to pull dated, typed facts out of ingested
documents. Every extracted fact must carry an `evidence` string that appears
verbatim in the source text. Facts whose evidence cannot be found in the source
are rejected, so an extraction can never cite text the document does not contain.

The LLM call is pluggable. `call_model` is the only function that touches a
network API; it is not included here. Tests use a stub.

Record schema (one dict per fact):
    date        "YYYY-MM"
    jurisdiction, theme, type ("liberalising" | "restrictive" | "procedural")
    value       optional number (e.g. a tax rate or a transaction total)
    unit        optional string
    evidence    verbatim snippet from the source text
    source_sha256
"""

import json
import re

REQUIRED = ("date", "jurisdiction", "type", "evidence", "source_sha256")
TYPES = {"liberalising", "restrictive", "procedural"}
DATE_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def normalise_ws(s):
    return re.sub(r"\s+", " ", s).strip()


def validate_record(rec, source_text, source_sha256):
    """Return a list of problems. An empty list means the record is accepted."""
    problems = []
    for key in REQUIRED:
        if not rec.get(key):
            problems.append(f"missing {key}")
    if problems:
        return problems
    if not DATE_RE.match(rec["date"]):
        problems.append(f"bad date {rec['date']!r}")
    if rec["type"] not in TYPES:
        problems.append(f"bad type {rec['type']!r}")
    if rec["source_sha256"] != source_sha256:
        problems.append("source hash does not match the document")
    if normalise_ws(rec["evidence"]) not in normalise_ws(source_text):
        problems.append("evidence snippet not found in source text")
    return problems


def extract(source_text, source_sha256, call_model):
    """Ask the model for records, keep the valid ones, and report the rest.

    call_model(prompt) -> str containing a JSON array of records.
    """
    prompt = (
        "Extract dated regulatory facts from the document below. Return a JSON array. "
        "Each item needs: date (YYYY-MM), jurisdiction, theme, type "
        "(liberalising|restrictive|procedural), optional value and unit, and evidence: "
        "a sentence copied EXACTLY from the document.\n\n" + source_text
    )
    raw = call_model(prompt)
    try:
        items = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [], [{"error": f"model output is not JSON: {exc}"}]
    accepted, rejected = [], []
    for rec in items:
        rec = dict(rec, source_sha256=source_sha256)
        probs = validate_record(rec, source_text, source_sha256)
        if probs:
            rejected.append({"record": rec, "problems": probs})
        else:
            accepted.append(rec)
    return accepted, rejected
