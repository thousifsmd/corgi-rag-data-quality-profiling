#!/usr/bin/env python3
"""
corgi_ablation.py — per-dimension ablation of the CORGI gate.

Contaminate SciFact with BOTH defect classes CORGI targets:
  * redundancy  : 40% near-duplicate copies (last 15% of words dropped; byte-different)
  * completeness: 15% thin fragments (5-word slices) that pad the index

Then run the gate with cumulative rule sets and measure retrieval + index hygiene:
  none | thin-only | redundancy-only | full (redundancy+thin)

Shows which gate rule carries which benefit (redundancy -> retrieval quality; thin -> index size).
Writes ../out/c4_ablation.{json,csv}.

Usage: python -I corgi_ablation.py --data ../data/beir/scifact --out ../out
"""
import argparse, csv, json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from corgi_inject import load_jsonl, load_qrels, embed, ndcg_at_k, recall_at_k


def evaluate(Qe, E, ids, toks, inj, q_ids, qrels, k=10):
    scores = Qe @ E.T
    nd = occ = 0.0; nq = 0; kk = min(k, E.shape[0])
    for i, qid in enumerate(q_ids):
        rel = qrels.get(qid)
        if not rel:
            continue
        top = np.argpartition(-scores[i], kk-1)[:kk]
        top = top[np.argsort(-scores[i][top])]
        ranked = [ids[j] for j in top]
        nd += ndcg_at_k(ranked, rel, k)
        occ += sum(1 for j in top if inj[j]) / kk
        nq += 1
    return round(nd/nq, 4), round(occ/nq, 4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", default="../out")
    ap.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")
    ap.add_argument("--contaminate", type=float, default=0.4)
    ap.add_argument("--thin-frac", type=float, default=0.15)
    ap.add_argument("--tau", type=float, default=0.95)
    ap.add_argument("--min-tokens", type=int, default=20)
    ap.add_argument("--drop-last-frac", type=float, default=0.15)
    ap.add_argument("--thin-words", type=int, default=5)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    rng = np.random.default_rng(args.seed)
    corpus = load_jsonl(os.path.join(args.data, "corpus.jsonl"))
    queries = load_jsonl(os.path.join(args.data, "queries.jsonl"))
    qrels = load_qrels(os.path.join(args.data, "qrels", "test.tsv"))
    doc_ids = list(corpus.keys()); texts = [corpus[d] for d in doc_ids]; n = len(doc_ids)
    q_ids = [q for q in queries if q in qrels]; q_texts = [queries[q] for q in q_ids]

    slug = args.model.split("/")[-1]
    cache = os.path.join(args.out, f"scifact_corpus_emb_{slug}.npy")
    if os.path.exists(cache) and np.load(cache).shape[0] == n:
        Ce0 = np.load(cache); print("loaded cached corpus embeddings")
    else:
        Ce0 = embed(texts, args.model); np.save(cache, Ce0)
    Qe = embed(q_texts, args.model)

    # redundancy defect: near-duplicate copies
    mdup = int(args.contaminate * n); src = rng.permutation(n)[:mdup]
    ndup = [" ".join(texts[j].split()[:max(1, int(len(texts[j].split())*(1-args.drop_last_frac)))]) for j in src]
    # completeness defect: thin fragments
    mthin = int(args.thin_frac * n); tsrc = rng.permutation(n)[:mthin]
    thin = [" ".join(texts[j].split()[:args.thin_words]) for j in tsrc]
    print(f"injecting {mdup} near-dups + {mthin} thin fragments ...")
    E = np.vstack([Ce0, embed(ndup, args.model), embed(thin, args.model)])
    ids = doc_ids + [f"d{j}__ndup" for j in src] + [f"d{j}__thin" for j in tsrc]
    toks = np.array([len(t.split()) for t in texts + ndup + thin])
    inj_dup = np.zeros(len(ids), bool); inj_dup[n:n+mdup] = True   # near-dups (for dup_occ)
    M = len(ids)

    # precompute greedy near-dup "is a later copy of a kept earlier chunk"
    S = E @ E.T; np.fill_diagonal(S, 0.0)
    red_drop = np.zeros(M, bool); kept = np.ones(M, bool)
    for i in range(M):
        if not kept[i]:
            continue
        dup = np.where(S[i, i+1:] >= args.tau)[0] + (i+1)
        kept[dup] = False; red_drop[dup] = True
    thin_drop = toks < args.min_tokens

    configs = {
        "none":            np.ones(M, bool),
        "thin-only":       ~thin_drop,
        "redundancy-only": ~red_drop,
        "full":            ~(red_drop | thin_drop),
    }
    results = {}
    for name, keep in configs.items():
        idx = np.where(keep)[0]
        nd, occ = evaluate(Qe, E[idx], [ids[j] for j in idx], toks[idx], inj_dup[idx], q_ids, qrels)
        results[name] = {"ndcg@10": nd, "dup_occ@10": occ, "index_size": int(keep.sum()),
                         "thin_retained": int((keep & thin_drop).sum())}
    meta = {"n_clean": n, "near_dups": mdup, "thin": mthin, "tau": args.tau,
            "min_tokens": args.min_tokens, "model": args.model}
    with open(os.path.join(args.out, "c4_ablation.json"), "w") as f:
        json.dump({"meta": meta, "results": results}, f, indent=2)
    with open(os.path.join(args.out, "c4_ablation.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["config", "ndcg@10", "dup_occ@10", "index_size", "thin_retained"])
        for k in ("none", "thin-only", "redundancy-only", "full"):
            v = results[k]; w.writerow([k, v["ndcg@10"], v["dup_occ@10"], v["index_size"], v["thin_retained"]])

    print(f"\n{'config':<16}{'nDCG@10':>9}{'dupOcc':>8}{'index':>8}{'thinKept':>10}")
    for k in ("none", "thin-only", "redundancy-only", "full"):
        v = results[k]
        print(f"{k:<16}{v['ndcg@10']:>9}{v['dup_occ@10']:>8}{v['index_size']:>8}{v['thin_retained']:>10}")


if __name__ == "__main__":
    main()
