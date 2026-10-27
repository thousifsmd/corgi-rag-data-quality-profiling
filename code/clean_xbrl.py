#!/usr/bin/env python3
"""
clean_xbrl.py — scrub inline-XBRL "context soup" from already-downloaded EDGAR .txt files
so you don't have to re-download. Cleans in place; originals are backed up to <dir>/_raw/.

Usage:
    python -I clean_xbrl.py --input edgar
    python -I clean_xbrl.py --input ../data/edgar
"""
import argparse
import glob
import os
import re
import shutil

# Same pattern as fetch_edgar.strip_xbrl_soup: runs of prefix:Name tokens, ISO dates,
# 10-digit CIKs, and *Member axis names. 3+ in a row = XBRL metadata, not prose.
_XBRL_TOKEN = (
    r"(?:[a-z][a-z0-9-]{0,9}:[A-Za-z0-9]+"
    r"|\d{10}"
    r"|\d{4}-\d{2}-\d{2}"
    r"|[A-Za-z0-9.]+Member"                    # ...Member axis (may include digits/dots)
    r"|\.\d{1,4})"                             # leftover coupon fragments (.8 .375)
)
_XBRL_SOUP = re.compile(r"(?:" + _XBRL_TOKEN + r"\s*){3,}")


def main():
    ap = argparse.ArgumentParser(description="Remove inline-XBRL soup from EDGAR .txt files.")
    ap.add_argument("--input", required=True, help="Folder of *.txt filings.")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.input, "*.txt")))
    if not files:
        raise SystemExit(f"No .txt files in {args.input}")

    raw_dir = os.path.join(args.input, "_raw")
    os.makedirs(raw_dir, exist_ok=True)

    tot_before = tot_after = 0
    for p in files:
        with open(p, encoding="utf-8", errors="ignore") as f:
            text = f.read()
        before = len(text.split())
        # back up original once
        bak = os.path.join(raw_dir, os.path.basename(p))
        if not os.path.exists(bak):
            shutil.copy2(p, bak)
        cleaned = _XBRL_SOUP.sub(" ", text)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
        after = len(cleaned.split())
        with open(p, "w", encoding="utf-8") as f:
            f.write(cleaned)
        tot_before += before
        tot_after += after
        pct = 100 * (before - after) / before if before else 0
        print(f"  {os.path.basename(p):<30} {before:>7,} -> {after:>7,} words  (-{pct:4.1f}%)")

    pct = 100 * (tot_before - tot_after) / tot_before if tot_before else 0
    print(f"\nTotal: {tot_before:,} -> {tot_after:,} words  (-{pct:.1f}% removed as XBRL soup)")
    print(f"Originals backed up in: {raw_dir}")


if __name__ == "__main__":
    main()
