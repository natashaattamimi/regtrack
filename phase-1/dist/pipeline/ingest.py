"""
ingest.py — content-hashed raw snapshots with a provenance manifest.

Every raw source file (a PDF, an HTML page, a CSV from a regulator) is copied
into raw/<sha256>.<ext> and recorded in raw/manifest.json with its source URL,
retrieval time, and hash. Re-ingesting identical bytes is a no-op; changed bytes
create a new snapshot, so a revised regulator figure never silently overwrites
the old one.

Usage:
    python3 pipeline/ingest.py add <path> --source-url URL --publisher NAME
    python3 pipeline/ingest.py verify
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(ROOT, "raw")
MANIFEST = os.path.join(RAW_DIR, "manifest.json")


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def load_manifest(path=MANIFEST):
    if not os.path.exists(path):
        return {"snapshots": []}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_manifest(m, path=MANIFEST):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2, ensure_ascii=False)


def add_snapshot(src, source_url, publisher, raw_dir=RAW_DIR, manifest_path=None):
    """Copy src into raw_dir under its hash. Returns the manifest entry."""
    manifest_path = manifest_path or os.path.join(raw_dir, "manifest.json")
    digest = sha256_file(src)
    ext = os.path.splitext(src)[1].lower() or ".bin"
    manifest = load_manifest(manifest_path)
    for entry in manifest["snapshots"]:
        if entry["sha256"] == digest:
            return entry  # identical bytes already stored
    os.makedirs(raw_dir, exist_ok=True)
    dest = os.path.join(raw_dir, f"{digest}{ext}")
    shutil.copyfile(src, dest)
    entry = {
        "sha256": digest,
        "file": os.path.basename(dest),
        "original_name": os.path.basename(src),
        "publisher": publisher,
        "source_url": source_url,
        "retrieved_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "bytes": os.path.getsize(dest),
    }
    manifest["snapshots"].append(entry)
    save_manifest(manifest, manifest_path)
    return entry


def verify(raw_dir=RAW_DIR, manifest_path=None):
    """Check every stored file still matches its recorded hash. Returns list of problems."""
    manifest_path = manifest_path or os.path.join(raw_dir, "manifest.json")
    manifest = load_manifest(manifest_path)
    problems = []
    for entry in manifest["snapshots"]:
        p = os.path.join(raw_dir, entry["file"])
        if not os.path.exists(p):
            problems.append(f"missing: {entry['file']}")
        elif sha256_file(p) != entry["sha256"]:
            problems.append(f"hash mismatch: {entry['file']}")
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("path")
    a.add_argument("--source-url", required=True)
    a.add_argument("--publisher", required=True)
    sub.add_parser("verify")
    args = ap.parse_args(argv)
    if args.cmd == "add":
        e = add_snapshot(args.path, args.source_url, args.publisher)
        print(f"{e['sha256'][:12]}  {e['file']}  ({e['publisher']})")
        return 0
    problems = verify()
    for p in problems:
        print(p)
    print("ok" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
