#!/usr/bin/env python3
"""
Download a BEIR dataset (default: scifact) and extract it. BEIR datasets are small,
labeled IR benchmarks (corpus.jsonl + queries.jsonl + qrels/test.tsv) — the labeled
ground truth C2 needs.

Usage: python fetch_beir.py --name scifact --out ../data/beir
"""
import argparse
import io
import os
import zipfile

import requests

URL = "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/{name}.zip"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="scifact")
    ap.add_argument("--out", default="../data/beir")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    url = URL.format(name=args.name)
    print(f"downloading {url} ...")
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        z.extractall(args.out)
    dest = os.path.join(args.out, args.name)
    print(f"extracted to {dest}")
    for f in ("corpus.jsonl", "queries.jsonl", "qrels/test.tsv"):
        p = os.path.join(dest, f)
        print(f"  {'OK ' if os.path.exists(p) else 'MISSING'} {f}")


if __name__ == "__main__":
    main()
