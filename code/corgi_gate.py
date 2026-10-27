#!/usr/bin/env python3
"""
corgi_gate.py — CORGI's C3 experiment: does the profiling-driven quality GATE beat baselines?

We first contaminate a clean labeled corpus (BEIR SciFact) with SEMANTIC near-duplicate
distractors (copies of documents with their last ~15% of words dropped — byte-different, so
exact deduplication cannot catch them, but cosine-similar). We then index the corpus under
four regimes and measure retrieval:

  clean        : original corpus only (reference upper bound)
  ungated      : contaminated corpus, no cleaning
  exact-dedup  : remove byte-identical (normalized-hash) duplicates
  CORGI-gated  : remove embedding near-duplicates (cosine >= tau, keep first) + thin chunks

Metrics: nDCG@10, Recall@10, indexed corpus size, dup_occupancy@10 (share of top-10 that are
injected distractors), tokens@10 (avg total words across the top-10 — the RAG context budget).

Usage:
  python -I corgi_gate.py --data ../data/beir/scifact --out ../out \
      --contaminate 0.4 --tau 0.95 --drop-last-frac 0.15 --min-tokens 20
"""
import argparse
import csv
import hashlib
import json
import math
import os
import re

import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # works even under python -I
from corgi_inject import load_jsonl, load_qrels, embed, ndcg_at_k, recall_at_k

_norm = re.compile(r"\s+")


def nhash(t):
    return hashlib.md5(_norm.sub(" ", t.strip().lower()).encode("utf-8")).hexdigest()


def evaluate(Qe, Ce, ids, toks, inj, q_ids, qrels, k=10):
    scores = Qe @ Ce.T
    nd = rc = occ = tok = 0.0
    nq = 0
    kk = min(k, Ce.shape[0])
    for i, qid in enumerate(q_ids):
        rel = qrels.get(qid)
        if not rel:
            continue
        top = np.argpartition(-scores[i], kk - 1)[:kk]
        top = top[np.argsort(-scores[i][top])]
        ranked = [ids[j] for j in top]
        nd += ndcg_at_k(ranked, rel, k)
        rc += recall_at_k(ranked, rel, k)
        occ += sum(1 for j in top if inj[j]) / kk
        tok += sum(toks[j] for j in top)
        nq += 1
    return {"ndcg@10": round(nd / nq, 4), "recall@10": round(rc / nq, 4),
            "dup_occ@10": round(occ / nq, 4), "tokens@10": round(tok / nq, 1),
            "index_size": int(Ce.shape[0])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", default="../out")
    ap.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")
    ap.add_argument("--contaminate", type=float, default=0.4)
    ap.add_argument("--tau", type=float, default=0.95)
    ap.add_argument("--drop-last-frac", type=float, default=0.15)
    ap.add_argument("--min-tokens", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    rng = np.random.default_rng(args.seed)

    corpus = load_jsonl(os.path.join(args.data, "corpus.jsonl"))
    queries = load_jsonl(os.path.join(args.data, "queries.jsonl"))
    qrels = load_qrels(os.path.join(args.data, "qrels", "test.tsv"))

    doc_ids = list(corpus.keys())
    texts = [corpus[d] for d in doc_ids]
    n = len(doc_ids)
    q_ids = [q for q in queries if q in qrels]
    q_texts = [queries[q] for q in q_ids]

    slug = args.model.split("/")[-1]
    cache = os.path.join(args.out, f"scifact_corpus_emb_{slug}.npy")
    if os.path.exists(cache) and np.load(cache).shape[0] == n:
        Ce0 = np.load(cache); print("loaded cached corpus embeddings")
    else:
        print("embedding corpus ..."); Ce0 = embed(texts, args.model); np.save(cache, Ce0)
    Qe = embed(q_texts, args.model)

    # ---- contaminate with semantic near-duplicates (byte-different) ----
    m = int(args.contaminate * n)
    src = rng.permutation(n)[:m]
    ndup_texts = []
    for j in src:
        w = texts[j].split()
        keep = max(1, int(len(w) * (1 - args.drop_last_frac)))
        ndup_texts.append(" ".join(w[:keep]))
    print(f"injecting {m} near-duplicates ...")
    Nd = embed(ndup_texts, args.model)

    ids = doc_ids + [f"{doc_ids[j]}__ndup" for j in src]
    all_texts = texts + ndup_texts
    E = np.vstack([Ce0, Nd])
    toks = np.array([len(t.split()) for t in all_texts])
    inj = np.zeros(len(ids), dtype=bool); inj[n:] = True
    hashes = [nhash(t) for t in all_texts]
    M = len(ids)

    def submat(mask):
        idx = np.where(mask)[0]
        return E[idx], [ids[j] for j in idx], toks[idx], inj[idx]

    results = {}
    # clean reference
    e, i_, t_, j_ = submat(np.array([True] * n + [False] * m))
    results["clean"] = evaluate(Qe, e, i_, t_, j_, q_ids, qrels)
    # ungated
    results["ungated"] = evaluate(Qe, E, ids, toks, inj, q_ids, qrels)
    # exact-dedup (normalized hash, keep first occurrence)
    seen, keep_ex = set(), np.ones(M, bool)
    for i, h in enumerate(hashes):
        if h in seen:
            keep_ex[i] = False
        else:
            seen.add(h)
    e, i_, t_, j_ = submat(keep_ex)
    results["exact-dedup"] = evaluate(Qe, e, i_, t_, j_, q_ids, qrels)
    results["exact-dedup"]["removed"] = int(M - keep_ex.sum())
    # CORGI gate: greedy embedding near-dup removal (keep first) + thin-chunk removal
    S = E @ E.T
    np.fill_diagonal(S, 0.0)
    keep_g = np.ones(M, bool)
    for i in range(M):
        if not keep_g[i]:
            continue
        dup = np.where(S[i, i + 1:] >= args.tau)[0] + (i + 1)
        keep_g[dup] = False
    removed_dup = int(M - keep_g.sum())
    keep_g &= (toks >= args.min_tokens)
    e, i_, t_, j_ = submat(keep_g)
    results["CORGI-gated"] = evaluate(Qe, e, i_, t_, j_, q_ids, qrels)
    results["CORGI-gated"]["removed"] = int(M - keep_g.sum())
    results["CORGI-gated"]["removed_near_dup"] = removed_dup

    meta = {"n_clean": n, "injected": m, "contaminate": args.contaminate,
            "tau": args.tau, "drop_last_frac": args.drop_last_frac}
    with open(os.path.join(args.out, f"c3_gate_{slug}.json"), "w") as f:
        json.dump({"meta": meta, "results": results}, f, indent=2)
    with open(os.path.join(args.out, f"c3_gate_{slug}.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["regime", "ndcg@10", "recall@10", "dup_occ@10", "tokens@10", "index_size"])
        for r in ("clean", "ungated", "exact-dedup", "CORGI-gated"):
            v = results[r]
            w.writerow([r, v["ndcg@10"], v["recall@10"], v["dup_occ@10"], v["tokens@10"], v["index_size"]])

    print("\n=== C3: gate vs. baselines (SciFact, contaminated with near-dups) ===")
    print(f"{'regime':<13} {'nDCG@10':>8} {'Rec@10':>8} {'dupOcc':>7} {'tok@10':>8} {'size':>7}")
    for r in ("clean", "ungated", "exact-dedup", "CORGI-gated"):
        v = results[r]
        print(f"{r:<13} {v['ndcg@10']:>8} {v['recall@10']:>8} {v['dup_occ@10']:>7} "
              f"{v['tokens@10']:>8} {v['index_size']:>7}")
    print("Wrote c3_gate.json/.csv to", args.out)


if __name__ == "__main__":
    main()
