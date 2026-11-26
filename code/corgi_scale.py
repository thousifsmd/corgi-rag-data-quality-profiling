#!/usr/bin/env python3
"""
corgi_scale.py — absolute runtime / memory of the CORGI near-duplicate profile+gate pass, using
FAISS HNSW (the ANN path described in Section III-C), plus ANN-vs-exact agreement.

Two modes:
  --embed-only        embed a BEIR corpus once and cache it (embedding cost is NOT part of CORGI:
                      the profiler reuses the embeddings already computed for indexing)
  --size N            run the gate on the first N cached embeddings in THIS process (so peak
                      memory is per-size), print one JSON line.

Usage:
  python -I corgi_scale.py --embed-only --corpus ../data/beir/quora/corpus.jsonl --cache ../out/quora_emb.npy
  python -I corgi_scale.py --emb ../out/quora_emb.npy --size 100000 --tau 0.95
  python -I corgi_scale.py --emb ../out/embeddings.npy --size 22063 --tau 0.95 --label edgar
"""
import argparse
import json
import os
import sys
import time

import numpy as np
import psutil


def peak_mb():
    mi = psutil.Process().memory_info()
    return round(getattr(mi, "peak_wset", mi.rss) / 2**20, 1)


def gate_from_neighbors(D, I, tau):
    """Greedy keep-first removal using precomputed neighbor lists (the O(1)-per-chunk step)."""
    N = D.shape[0]
    keep = np.ones(N, bool)
    for i in range(N):
        if keep[i]:
            m = (I[i] > i) & (D[i] >= tau)
            keep[I[i][m]] = False
    return keep


def exact_gate(E, tau, block=2048):
    """Exact greedy keep-first gate via blocked matmul (reference for ANN agreement)."""
    N = E.shape[0]
    keep = np.ones(N, bool)
    for s in range(0, N, block):
        S = E[s:s + block] @ E.T
        for r in range(S.shape[0]):
            i = s + r
            if keep[i]:
                keep[np.where(S[r, i + 1:] >= tau)[0] + i + 1] = False
    return keep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--embed-only", action="store_true")
    ap.add_argument("--corpus")
    ap.add_argument("--cache")
    ap.add_argument("--emb")
    ap.add_argument("--size", type=int)
    ap.add_argument("--tau", type=float, default=0.95)
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--M", type=int, default=32)
    ap.add_argument("--ef", type=int, default=64)
    ap.add_argument("--exact-max", type=int, default=100000)
    ap.add_argument("--label", default="")
    a = ap.parse_args()

    if a.embed_only:
        from sentence_transformers import SentenceTransformer
        texts = []
        with open(a.corpus, encoding="utf-8") as f:
            for line in f:
                o = json.loads(line)
                texts.append((o.get("title", "") + " " + o.get("text", "")).strip())
        model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        t0 = time.time()
        E = np.asarray(model.encode(texts, batch_size=256, show_progress_bar=False,
                                    normalize_embeddings=True), dtype=np.float32)
        np.save(a.cache, E)
        print(json.dumps({"embedded": len(texts), "embed_seconds": round(time.time() - t0, 1)}))
        return

    import faiss
    E = np.ascontiguousarray(np.load(a.emb, mmap_mode="r")[:a.size], dtype=np.float32)
    N, d = E.shape
    base_mb = peak_mb()
    out = {"label": a.label, "N": N, "dim": d, "tau": a.tau, "hnsw_M": a.M, "efSearch": a.ef,
           "emb_matrix_mb": round(E.nbytes / 2**20, 1)}
    t0 = time.time()
    idx = faiss.IndexHNSWFlat(d, a.M, faiss.METRIC_INNER_PRODUCT)
    idx.hnsw.efConstruction = 80
    idx.add(E)
    out["build_s"] = round(time.time() - t0, 2)
    idx.hnsw.efSearch = a.ef
    t0 = time.time()
    D, I = idx.search(E, a.k + 1)
    out["search_s"] = round(time.time() - t0, 2)
    # drop self-match
    selfmask = I == np.arange(N)[:, None]
    for r in np.where(~selfmask.any(axis=1))[0]:
        selfmask[r, -1] = True
    D = np.where(selfmask, -1.0, D)
    t0 = time.time()
    keep = gate_from_neighbors(D, I, a.tau)
    out["gate_pass_s"] = round(time.time() - t0, 2)
    out["profile_plus_gate_s"] = round(out["build_s"] + out["search_s"] + out["gate_pass_s"], 2)
    out["quarantined"] = int((~keep).sum())
    out["frac_quarantined"] = round(float((~keep).mean()), 4)
    out["red@tau"] = round(float(((D >= a.tau).any(axis=1)).mean()), 4)
    out["peak_rss_mb"] = peak_mb()
    out["peak_rss_over_embeddings_mb"] = round(out["peak_rss_mb"] - base_mb, 1)
    if N <= a.exact_max:
        t0 = time.time()
        kx = exact_gate(E, a.tau)
        out["exact_gate_s"] = round(time.time() - t0, 2)
        rx, ra = set(np.where(~kx)[0]), set(np.where(~keep)[0])
        out["exact_quarantined"] = len(rx)
        out["ann_vs_exact_recall"] = round(len(rx & ra) / max(1, len(rx)), 4)
        out["ann_vs_exact_precision"] = round(len(rx & ra) / max(1, len(ra)), 4)
        out["ann_speedup_vs_exact"] = round(out["exact_gate_s"] / out["profile_plus_gate_s"], 2)
    print(json.dumps(out))


if __name__ == "__main__":
    main()
