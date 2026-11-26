#!/usr/bin/env python3
"""
Fallback BEIR fetcher via the Hugging Face mirror (BeIR/<name>, BeIR/<name>-qrels), for when
the UKP Darmstadt host used by fetch_beir.py is unreachable. Writes the same layout:
  <out>/<name>/corpus.jsonl, queries.jsonl, qrels/test.tsv

Usage: python fetch_beir_hf.py --name nfcorpus --out ../data/beir
"""
import argparse
import json
import os
import shutil

import pandas as pd
from huggingface_hub import hf_hub_download


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--out", default="../data/beir")
    args = ap.parse_args()

    dest = os.path.join(args.out, args.name)
    os.makedirs(os.path.join(dest, "qrels"), exist_ok=True)

    for kind in ("corpus", "queries"):
        p = hf_hub_download(f"BeIR/{args.name}", f"{kind}/{kind}-00000-of-00001.parquet", repo_type="dataset")
        df = pd.read_parquet(p)
        with open(os.path.join(dest, f"{kind}.jsonl"), "w", encoding="utf-8") as f:
            for r in df.to_dict("records"):
                o = {"_id": str(r["_id"]), "text": r.get("text", "") or ""}
                if kind == "corpus":
                    o["title"] = r.get("title", "") or ""
                f.write(json.dumps(o, ensure_ascii=False) + "\n")
        print(f"{kind}: {len(df)} rows")

    q = hf_hub_download(f"BeIR/{args.name}-qrels", "test.tsv", repo_type="dataset")
    shutil.copy(q, os.path.join(dest, "qrels", "test.tsv"))
    print("extracted to", dest)


if __name__ == "__main__":
    main()
