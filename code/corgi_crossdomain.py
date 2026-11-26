#!/usr/bin/env python3
"""
corgi_crossdomain.py — does the gate result hold beyond SciFact/finance? For each BEIR dataset:

  natural  : profile + gate the RAW corpus (no injection): exact-dup ratio, Red@tau, fraction the
             gate quarantines, delta nDCG@10 / recall@10 vs. the raw corpus, and the number of
             queries whose relevant document gets quarantined (the cost of gating).
  injected : the corgi_sensitivity.py protocol (40% near-duplicate copies, last 15% of words
             dropped), several seeds; ungated / exact / MinHash / CORGI nDCG@10 with paired
             Wilcoxon tests vs. ungated.

Usage:
  python -I corgi_crossdomain.py --datasets nfcorpus,arguana --seeds 3 --out ../results
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from corgi_inject import load_jsonl, load_qrels  # noqa: E402
from corgi_gate import nhash  # noqa: E402
from corgi_sensitivity import (summarize, corgi_gate, minhash_dedup, paired, MODEL)  # noqa: E402


def run(name, data_root, cache_dir, seeds, tau, theta, contaminate, drop):
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL)
    enc = lambda t: np.asarray(model.encode(t, batch_size=64, show_progress_bar=False,
                                            normalize_embeddings=True), dtype=np.float32)
    d = os.path.join(data_root, name)
    corpus = load_jsonl(os.path.join(d, "corpus.jsonl"))
    queries = load_jsonl(os.path.join(d, "queries.jsonl"))
    qrels = load_qrels(os.path.join(d, "qrels", "test.tsv"))
    doc_ids = list(corpus)
    texts = [corpus[x] for x in doc_ids]
    n = len(doc_ids)
    q_ids = [q for q in queries if q in qrels and any(r in corpus for r in qrels[q])]
    cache = os.path.join(cache_dir, f"{name}_corpus_emb_all-MiniLM-L6-v2.npy")
    if os.path.exists(cache) and np.load(cache).shape[0] == n:
        Ce = np.load(cache)
    else:
        Ce = enc(texts)
        np.save(cache, Ce)
    Qe = enc([queries[q] for q in q_ids])
    toks = np.array([len(t.split()) for t in texts])
    pos = {x: i for i, x in enumerate(doc_ids)}
    res = {"dataset": name, "n_docs": n, "n_queries": len(q_ids)}

    # ---------------- natural (raw corpus) ----------------
    S = Ce @ Ce.T
    np.fill_diagonal(S, 0.0)
    exact = 1 - len({nhash(t) for t in texts}) / n
    nn = S.max(axis=1)
    res["natural"] = {"exact_dup_ratio": round(float(exact), 4),
                      "red@0.95": round(float((nn >= 0.95).mean()), 4),
                      "red@0.90": round(float((nn >= 0.90).mean()), 4),
                      "mean_nn_sim": round(float(nn.mean()), 4)}
    no_inj = np.zeros(n, bool)
    base = summarize(Ce, doc_ids, no_inj, np.ones(n, bool), Qe, q_ids, qrels)
    res["natural"]["baseline"] = {"ndcg": round(float(base["ndcg"].mean()), 4),
                                  "recall": round(float(base["recall"].mean()), 4)}
    res["natural"]["gate"] = []
    for t in (0.90, 0.93, 0.95, 0.97):
        keep = corgi_gate(S, toks, t, theta)
        s = summarize(Ce, doc_ids, no_inj, keep, Qe, q_ids, qrels)
        rem = set(np.where(~keep)[0])
        lost = sum(1 for q in q_ids if any(pos.get(x) in rem for x in qrels[q] if x in pos))
        res["natural"]["gate"].append({
            "tau": t, "removed": int((~keep).sum()), "frac_removed": round(float((~keep).mean()), 4),
            "ndcg": round(float(s["ndcg"].mean()), 4), "d_ndcg": round(float(s["ndcg"].mean() - base["ndcg"].mean()), 4),
            "recall": round(float(s["recall"].mean()), 4),
            "d_recall": round(float(s["recall"].mean() - base["recall"].mean()), 4),
            "queries_with_quarantined_relevant_doc": lost,
            "pct_queries_with_quarantined_relevant_doc": round(100 * lost / len(q_ids), 2),
            "queries_recall_drop": int((s["recall"] < base["recall"] - 1e-9).sum()),
            "paired_ndcg_vs_raw": paired(s["ndcg"], base["ndcg"])})
        print(f"[{name}/natural] tau={t}: removed {res['natural']['gate'][-1]['removed']} "
              f"({100*res['natural']['gate'][-1]['frac_removed']:.1f}%), dNDCG {res['natural']['gate'][-1]['d_ndcg']}, "
              f"queries losing relevant doc {lost}/{len(q_ids)}")

    # ---------------- injected ----------------
    inj_runs = []
    for seed in range(seeds):
        rng = np.random.default_rng(seed)
        m = int(contaminate * n)
        src = rng.permutation(n)[:m]
        nd_texts = []
        for j in src:
            w = texts[j].split()
            nd_texts.append(" ".join(w[:max(1, int(len(w) * (1 - drop)))]))
        E = np.vstack([Ce, enc(nd_texts)])
        ids = doc_ids + [f"{doc_ids[j]}__ndup" for j in src]
        all_t = texts + nd_texts
        tk = np.array([len(t.split()) for t in all_t])
        inj = np.zeros(len(ids), bool)
        inj[n:] = True
        M = len(ids)
        SS = E @ E.T
        np.fill_diagonal(SS, 0.0)
        seen, kex = set(), np.ones(M, bool)
        for i, t in enumerate(all_t):
            h = nhash(t)
            if h in seen:
                kex[i] = False
            seen.add(h)
        R = {"clean": summarize(E, ids, inj, ~inj, Qe, q_ids, qrels),
             "ungated": summarize(E, ids, inj, np.ones(M, bool), Qe, q_ids, qrels),
             "exact-dedup": summarize(E, ids, inj, kex, Qe, q_ids, qrels),
             "minhash-0.8": summarize(E, ids, inj, minhash_dedup(all_t, 0.8, seed=seed), Qe, q_ids, qrels)}
        kc = corgi_gate(SS, tk, tau, theta)
        R["CORGI"] = summarize(E, ids, inj, kc, Qe, q_ids, qrels)
        inj_runs.append({
            "seed": seed,
            "regimes": {k: {"ndcg": float(v["ndcg"].mean()), "recall": float(v["recall"].mean()),
                            "dup_occ": float(v["dup_occ"].mean()), "size": v["size"]} for k, v in R.items()},
            "near_dups_removed_frac": float((~kc & inj).sum() / inj.sum()),
            "originals_removed": int((~kc & ~inj).sum()),
            "sig_CORGI_vs_ungated": paired(R["CORGI"]["ndcg"], R["ungated"]["ndcg"]),
            "sig_minhash_vs_ungated": paired(R["minhash-0.8"]["ndcg"], R["ungated"]["ndcg"]),
            "sig_CORGI_vs_clean": paired(R["CORGI"]["ndcg"], R["clean"]["ndcg"])})
        r = inj_runs[-1]["regimes"]
        print(f"[{name}/inj seed {seed}] clean {r['clean']['ndcg']:.4f} ungated {r['ungated']['ndcg']:.4f} "
              f"exact {r['exact-dedup']['ndcg']:.4f} minhash {r['minhash-0.8']['ndcg']:.4f} "
              f"CORGI {r['CORGI']['ndcg']:.4f} (orig removed {inj_runs[-1]['originals_removed']}, "
              f"p vs ungated {inj_runs[-1]['sig_CORGI_vs_ungated']['wilcoxon_p']:.2g})")
    agg = {}
    for k in inj_runs[0]["regimes"]:
        for mname in ("ndcg", "recall", "dup_occ", "size"):
            a = np.array([s["regimes"][k][mname] for s in inj_runs])
            agg.setdefault(k, {})[mname] = {"mean": round(float(a.mean()), 4),
                                            "std": round(float(a.std(ddof=1)) if len(a) > 1 else 0.0, 4)}
    res["injected"] = {"seeds": seeds, "summary": agg, "per_seed": inj_runs,
                       "seeds_CORGI_sig_vs_ungated": sum(s["sig_CORGI_vs_ungated"]["wilcoxon_p"] < 0.05 for s in inj_runs)}
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", default="nfcorpus,arguana")
    ap.add_argument("--data", default="../data/beir")
    ap.add_argument("--cache", default="../out")
    ap.add_argument("--out", default="../results")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--tau", type=float, default=0.95)
    ap.add_argument("--theta", type=int, default=20)
    ap.add_argument("--contaminate", type=float, default=0.4)
    ap.add_argument("--drop-last-frac", type=float, default=0.15)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    out = [run(n, a.data, a.cache, a.seeds, a.tau, a.theta, a.contaminate, a.drop_last_frac)
           for n in a.datasets.split(",")]
    p = os.path.join(a.out, "c6_crossdomain.json")
    with open(p, "w") as f:
        json.dump(out, f, indent=2)
    print("wrote", p)


if __name__ == "__main__":
    main()
