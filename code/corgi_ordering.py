#!/usr/bin/env python3
"""
corgi_ordering.py — does Algorithm 1's processing order matter on a dated corpus? The gate keeps
the FIRST occurrence of a near-duplicate, so oldest-first order keeps stale text. Compares
oldest-first vs newest-first: corpus reduction and quarantined share per filing year.

Usage: python -I corgi_ordering.py --input ../data/edgar --manifest ../data/edgar/manifest.csv \
         --emb ../out/embeddings.npy --out ../results
"""
import argparse, collections, json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corgi_profile as cp
import corgi_error_analysis as ea

ap = argparse.ArgumentParser()
ap.add_argument("--input", required=True); ap.add_argument("--manifest", required=True)
ap.add_argument("--emb", required=True); ap.add_argument("--out", default="../results")
ap.add_argument("--tau", type=float, default=0.95); ap.add_argument("--theta", type=int, default=20)
a = ap.parse_args()
docs = cp.load_docs(a.input, cp.load_manifest(a.manifest))
texts, metas = cp.build_chunks(docs, 200, 40)
E = np.load(a.emb)
assert E.shape[0] == len(texts)
yr = np.array([int(m["date"][:4]) for m in metas])
valid = (np.array([len(t.split()) for t in texts]) >= a.theta) & np.array([ea.boundary_ok(t) for t in texts])
res = {"tau": a.tau, "theta": a.theta, "valid_chunks": int(valid.sum())}
for name, order in (("oldest_first", np.arange(len(texts))),
                    ("newest_first", np.argsort(-yr, kind="stable"))):
    keep_o, _ = ea.gate_with_cause(E[order], valid[order], a.tau)
    keep = np.zeros(len(texts), bool); keep[order] = keep_o
    q = ~keep & valid
    res[name] = {"quarantined_redundant": int(q.sum()),
                 "by_year": {str(y): {"valid": int((valid & (yr == y)).sum()),
                                      "quarantined": int((q & (yr == y)).sum()),
                                      "frac_quarantined": round(float((q & (yr == y)).sum() / max(1, (valid & (yr == y)).sum())), 4)}
                             for y in sorted(set(yr))}}
    print(name, res[name]["quarantined_redundant"], {y: v["frac_quarantined"] for y, v in res[name]["by_year"].items()})
json.dump(res, open(os.path.join(a.out, "c9_ordering.json"), "w"), indent=2)
