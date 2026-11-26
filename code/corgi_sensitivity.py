#!/usr/bin/env python3
"""
corgi_sensitivity.py — reviewer-driven extension of the C3 gate experiment (does NOT modify
corgi_gate.py or any existing result file). Answers:

  (a) Gate policy sensitivity   : sweep similarity threshold tau and thin-chunk floor theta.
  (b) Cost of gating            : over-removal precision/recall (injected near-dups = positives),
                                  queries that lose a relevant doc, per-query recall drops, and
                                  the gate run on a CLEAN corpus (pure collateral damage).
  (c) Statistical rigor         : multiple contamination seeds, bootstrap 95% CIs and a paired
                                  Wilcoxon test of per-query nDCG@10 (regime vs. ungated).
  (d) More baselines            : MinHash-LSH near-dup dedup (word 3-shingles), SemDeDup-style
                                  cluster-restricted embedding dedup, random pruning matched to
                                  the CORGI index size.
  (e) Absolute cost             : wall-clock seconds for each gate/baseline step.

Same contamination protocol as corgi_gate.py (copy of a doc with its last 15% of words removed,
40% of documents); the contamination seed is varied.

Usage:
  python -I corgi_sensitivity.py --data ../data/beir/scifact --cache ../out --out ../results \
      --seeds 5
"""
import argparse
import json
import os
import sys
import time
import zlib

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from corgi_inject import load_jsonl, load_qrels, ndcg_at_k, recall_at_k  # noqa: E402
from corgi_gate import nhash  # noqa: E402

MODEL = "sentence-transformers/all-MiniLM-L6-v2"


# ----------------------------------------------------------------------------- retrieval eval
def per_query(Qe, Ce, ids, inj, q_ids, qrels, k=10):
    """Return per-query arrays (nDCG@k, recall@k, dup_occ@k) for the corpus (Ce, ids, inj)."""
    scores = Qe @ Ce.T
    kk = min(k, Ce.shape[0])
    nd, rc, oc = [], [], []
    for i, qid in enumerate(q_ids):
        top = np.argpartition(-scores[i], kk - 1)[:kk]
        top = top[np.argsort(-scores[i][top])]
        ranked = [ids[j] for j in top]
        rel = qrels[qid]
        nd.append(ndcg_at_k(ranked, rel, k))
        rc.append(recall_at_k(ranked, rel, k))
        oc.append(sum(1 for j in top if inj[j]) / kk)
    return np.array(nd), np.array(rc), np.array(oc)


def summarize(E, ids, inj, mask, Qe, q_ids, qrels):
    idx = np.where(mask)[0]
    nd, rc, oc = per_query(Qe, E[idx], [ids[j] for j in idx], inj[idx], q_ids, qrels)
    return {"ndcg": nd, "recall": rc, "dup_occ": oc, "size": int(mask.sum())}


# ----------------------------------------------------------------------------- gate + baselines
def corgi_gate(S, toks, tau, min_tokens):
    """Greedy keep-first embedding near-dup removal (cos >= tau) + thin-chunk floor."""
    M = S.shape[0]
    keep = np.ones(M, bool)
    for i in range(M):
        if keep[i]:
            keep[np.where(S[i, i + 1:] >= tau)[0] + i + 1] = False
    return keep & (toks >= min_tokens)


def semdedup(E, tau, n_clusters, seed):
    """SemDeDup-style: k-means, then greedy keep-first dedup only within each cluster."""
    from sklearn.cluster import KMeans
    lab = KMeans(n_clusters=n_clusters, n_init=1, random_state=seed).fit_predict(E)
    keep = np.ones(E.shape[0], bool)
    for c in range(n_clusters):
        idx = np.where(lab == c)[0]
        if len(idx) < 2:
            continue
        S = E[idx] @ E[idx].T
        for a in range(len(idx)):
            if keep[idx[a]]:
                for b in np.where(S[a, a + 1:] >= tau)[0] + a + 1:
                    keep[idx[b]] = False
    return keep


def minhash_dedup(texts, thr=0.8, n_perm=128, bands=32, seed=0):
    """MinHash + LSH banding on word 3-shingles; greedy keep-first, est. Jaccard >= thr."""
    rng = np.random.default_rng(seed)
    P = 2147483647
    a = rng.integers(1, P, n_perm, dtype=np.int64)[:, None]
    b = rng.integers(0, P, n_perm, dtype=np.int64)[:, None]
    sigs = np.zeros((len(texts), n_perm), dtype=np.int64)
    for i, t in enumerate(texts):
        w = t.lower().split()
        sh = {" ".join(w[j:j + 3]) for j in range(max(1, len(w) - 2))}
        h = np.array([zlib.crc32(s.encode()) for s in sh], dtype=np.int64)[None, :]
        sigs[i] = ((a * h + b) % P).min(axis=1)
    rows = n_perm // bands
    buckets = {}
    for i in range(len(texts)):
        for bd in range(bands):
            buckets.setdefault((bd, sigs[i, bd * rows:(bd + 1) * rows].tobytes()), []).append(i)
    cand = {}
    for ids_ in buckets.values():
        if len(ids_) > 1:
            for x in ids_:
                cand.setdefault(x, set()).update(y for y in ids_ if y > x)
    keep = np.ones(len(texts), bool)
    for i in range(len(texts)):
        if keep[i] and i in cand:
            for j in cand[i]:
                if keep[j] and (sigs[i] == sigs[j]).mean() >= thr:
                    keep[j] = False
    return keep


# ----------------------------------------------------------------------------- statistics
def boot_ci(x, n=10000, seed=0):
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), (n, len(x)))
    m = x[idx].mean(axis=1)
    return float(x.mean()), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def paired(a, b):
    """Paired comparison a vs b: mean diff, bootstrap CI, Wilcoxon p."""
    from scipy.stats import wilcoxon
    d = a - b
    mean, lo, hi = boot_ci(d)
    try:
        p = float(wilcoxon(d).pvalue) if np.any(d != 0) else 1.0
    except ValueError:
        p = 1.0
    return {"mean_diff": round(mean, 4), "ci95": [round(lo, 4), round(hi, 4)], "wilcoxon_p": p}


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--cache", default="../out")
    ap.add_argument("--out", default="../results")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--contaminate", type=float, default=0.4)
    ap.add_argument("--drop-last-frac", type=float, default=0.15)
    ap.add_argument("--taus", default="0.85,0.90,0.93,0.95,0.97,0.99")
    ap.add_argument("--thetas", default="0,10,20,30,50")
    args = ap.parse_args()
    taus = [float(x) for x in args.taus.split(",")]
    thetas = [int(x) for x in args.thetas.split(",")]
    os.makedirs(args.out, exist_ok=True)

    corpus = load_jsonl(os.path.join(args.data, "corpus.jsonl"))
    queries = load_jsonl(os.path.join(args.data, "queries.jsonl"))
    qrels = load_qrels(os.path.join(args.data, "qrels", "test.tsv"))
    doc_ids = list(corpus.keys())
    texts = [corpus[d] for d in doc_ids]
    n = len(doc_ids)
    q_ids = [q for q in queries if q in qrels]

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL)
    enc = lambda t: np.asarray(model.encode(t, batch_size=64, show_progress_bar=False,
                                            normalize_embeddings=True), dtype=np.float32)
    cache = os.path.join(args.cache, "scifact_corpus_emb_all-MiniLM-L6-v2.npy")
    Ce0 = np.load(cache) if os.path.exists(cache) and np.load(cache).shape[0] == n else enc(texts)
    Qe = enc([queries[q] for q in q_ids])
    toks0 = np.array([len(t.split()) for t in texts])
    rel_of = {q: qrels[q] for q in q_ids}
    pos_of = {d: i for i, d in enumerate(doc_ids)}

    # ---------- (b) gate on the CLEAN corpus: pure collateral damage ----------
    t0 = time.time()
    S0 = Ce0 @ Ce0.T
    np.fill_diagonal(S0, 0.0)
    t_sim_clean = time.time() - t0
    no_inj = np.zeros(n, bool)
    base_clean = summarize(Ce0, doc_ids, no_inj, np.ones(n, bool), Qe, q_ids, qrels)
    clean_gate = []
    for tau in taus:
        t0 = time.time()
        keep = corgi_gate(S0, toks0, tau, 20)
        t_gate = time.time() - t0
        s = summarize(Ce0, doc_ids, no_inj, keep, Qe, q_ids, qrels)
        removed = set(np.where(~keep)[0])
        lost_rel = sum(1 for q in q_ids if any(pos_of.get(d) in removed for d in rel_of[q]))
        clean_gate.append({
            "tau": tau, "removed": int((~keep).sum()), "frac_removed": round(float((~keep).mean()), 4),
            "ndcg": round(float(s["ndcg"].mean()), 4), "d_ndcg": round(float(s["ndcg"].mean() - base_clean["ndcg"].mean()), 4),
            "recall": round(float(s["recall"].mean()), 4), "d_recall": round(float(s["recall"].mean() - base_clean["recall"].mean()), 4),
            "queries_with_quarantined_relevant_doc": lost_rel,
            "queries_recall_drop": int((s["recall"] < base_clean["recall"] - 1e-9).sum()),
            "gate_seconds": round(t_gate, 2)})
        print(f"[clean] tau={tau}: removed {clean_gate[-1]['removed']}, dNDCG {clean_gate[-1]['d_ndcg']}, "
              f"queries w/ quarantined relevant doc {lost_rel}/{len(q_ids)}")

    # ---------- per-seed contaminated experiments ----------
    per_seed = []
    for seed in range(args.seeds):
        rng = np.random.default_rng(seed)
        m = int(args.contaminate * n)
        src = rng.permutation(n)[:m]
        nd_texts = []
        for j in src:
            w = texts[j].split()
            nd_texts.append(" ".join(w[:max(1, int(len(w) * (1 - args.drop_last_frac)))]))
        Nd = enc(nd_texts)
        ids = doc_ids + [f"{doc_ids[j]}__ndup" for j in src]
        all_texts = texts + nd_texts
        E = np.vstack([Ce0, Nd])
        toks = np.array([len(t.split()) for t in all_texts])
        inj = np.zeros(len(ids), bool)
        inj[n:] = True
        M = len(ids)
        t0 = time.time()
        S = E @ E.T
        np.fill_diagonal(S, 0.0)
        t_sim = time.time() - t0
        R = {}
        timing = {"similarity_matrix_s": round(t_sim, 2)}

        R["clean"] = summarize(E, ids, inj, ~inj, Qe, q_ids, qrels)
        R["ungated"] = summarize(E, ids, inj, np.ones(M, bool), Qe, q_ids, qrels)

        t0 = time.time()
        hashes = [nhash(t) for t in all_texts]
        seen, keep_ex = set(), np.ones(M, bool)
        for i, h in enumerate(hashes):
            if h in seen:
                keep_ex[i] = False
            else:
                seen.add(h)
        timing["exact_dedup_s"] = round(time.time() - t0, 2)
        R["exact-dedup"] = summarize(E, ids, inj, keep_ex, Qe, q_ids, qrels)

        t0 = time.time()
        keep_mh = minhash_dedup(all_texts, thr=0.8, seed=seed)
        timing["minhash_s"] = round(time.time() - t0, 2)
        R["minhash-0.8"] = summarize(E, ids, inj, keep_mh, Qe, q_ids, qrels)

        t0 = time.time()
        keep_sd = semdedup(E, 0.95, int(np.sqrt(M)), seed)
        timing["semdedup_s"] = round(time.time() - t0, 2)
        R["semdedup-0.95"] = summarize(E, ids, inj, keep_sd, Qe, q_ids, qrels)

        t0 = time.time()
        keep_c = corgi_gate(S, toks, 0.95, 20)
        timing["corgi_gate_s"] = round(time.time() - t0, 2)
        R["CORGI"] = summarize(E, ids, inj, keep_c, Qe, q_ids, qrels)

        rp = np.zeros(M, bool)
        rp[rng.permutation(M)[:int(keep_c.sum())]] = True
        R["random-prune (matched size)"] = summarize(E, ids, inj, rp, Qe, q_ids, qrels)

        # removal quality for each method (injected near-dups are the positives)
        def removal_quality(keep):
            rem = ~keep
            tp = int((rem & inj).sum()); fp = int((rem & ~inj).sum())
            return {"removed": int(rem.sum()), "near_dups_removed": tp, "originals_removed": fp,
                    "precision": round(tp / max(1, tp + fp), 4), "recall": round(tp / int(inj.sum()), 4)}
        quality = {"exact-dedup": removal_quality(keep_ex), "minhash-0.8": removal_quality(keep_mh),
                   "semdedup-0.95": removal_quality(keep_sd), "CORGI": removal_quality(keep_c)}

        # tau and theta sweeps
        tau_sweep = []
        for tau in taus:
            keep = corgi_gate(S, toks, tau, 20)
            s = summarize(E, ids, inj, keep, Qe, q_ids, qrels)
            rem = set(np.where(~keep)[0])
            lost = sum(1 for q in q_ids if any(pos_of[d] in rem for d in rel_of[q]))
            tau_sweep.append({"tau": tau, "ndcg": float(s["ndcg"].mean()), "recall": float(s["recall"].mean()),
                              "dup_occ": float(s["dup_occ"].mean()), "size": s["size"],
                              "queries_with_quarantined_relevant_doc": lost,
                              "queries_recall_drop_vs_clean": int((s["recall"] < R["clean"]["recall"] - 1e-9).sum()),
                              **removal_quality(keep)})
        theta_sweep = []
        for th in thetas:
            keep = corgi_gate(S, toks, 0.95, th)
            s = summarize(E, ids, inj, keep, Qe, q_ids, qrels)
            theta_sweep.append({"theta": th, "ndcg": float(s["ndcg"].mean()), "recall": float(s["recall"].mean()),
                                "size": s["size"], "removed": int((~keep).sum())})

        # significance vs ungated (per-query nDCG@10)
        sig = {k: paired(R[k]["ndcg"], R["ungated"]["ndcg"]) for k in
               ("CORGI", "exact-dedup", "minhash-0.8", "semdedup-0.95", "random-prune (matched size)", "clean")}
        sig["CORGI_vs_clean"] = paired(R["CORGI"]["ndcg"], R["clean"]["ndcg"])
        sig["CORGI_vs_minhash"] = paired(R["CORGI"]["ndcg"], R["minhash-0.8"]["ndcg"])
        sig["CORGI_vs_semdedup"] = paired(R["CORGI"]["ndcg"], R["semdedup-0.95"]["ndcg"])

        per_seed.append({
            "seed": seed, "M": M, "timing": timing,
            "regimes": {k: {"ndcg": round(float(v["ndcg"].mean()), 4), "recall": round(float(v["recall"].mean()), 4),
                            "dup_occ": round(float(v["dup_occ"].mean()), 4), "size": v["size"]} for k, v in R.items()},
            "removal_quality": quality, "tau_sweep": tau_sweep, "theta_sweep": theta_sweep,
            "significance_vs_ungated_ndcg": sig})
        r = per_seed[-1]["regimes"]
        print(f"[seed {seed}] clean {r['clean']['ndcg']} ungated {r['ungated']['ndcg']} "
              f"exact {r['exact-dedup']['ndcg']} minhash {r['minhash-0.8']['ndcg']} "
              f"semdedup {r['semdedup-0.95']['ndcg']} CORGI {r['CORGI']['ndcg']} "
              f"random {r['random-prune (matched size)']['ndcg']}  "
              f"CORGI-vs-ungated p={sig['CORGI']['wilcoxon_p']:.2g}")

    # ---------- aggregate over seeds ----------
    def agg(vals):
        a = np.array(vals, float)
        return {"mean": round(float(a.mean()), 4), "std": round(float(a.std(ddof=1)) if len(a) > 1 else 0.0, 4)}
    regimes = per_seed[0]["regimes"].keys()
    summary = {"regimes": {k: {m: agg([s["regimes"][k][m] for s in per_seed]) for m in ("ndcg", "recall", "dup_occ", "size")}
                           for k in regimes},
               "removal_quality": {k: {m: agg([s["removal_quality"][k][m] for s in per_seed])
                                       for m in ("removed", "near_dups_removed", "originals_removed", "precision", "recall")}
                                   for k in per_seed[0]["removal_quality"]},
               "tau_sweep": [{"tau": t, **{m: agg([s["tau_sweep"][i][m] for s in per_seed]) for m in
                              ("ndcg", "recall", "dup_occ", "size", "precision", "recall",
                               "originals_removed", "queries_with_quarantined_relevant_doc",
                               "queries_recall_drop_vs_clean")}} for i, t in enumerate(taus)],
               "theta_sweep": [{"theta": t, **{m: agg([s["theta_sweep"][i][m] for s in per_seed]) for m in
                                ("ndcg", "recall", "size", "removed")}} for i, t in enumerate(thetas)],
               "timing_seconds": {k: agg([s["timing"][k] for s in per_seed]) for k in per_seed[0]["timing"]},
               "significance_vs_ungated_ndcg_seeds_p_lt_0.05": {
                   k: sum(1 for s in per_seed if s["significance_vs_ungated_ndcg"][k]["wilcoxon_p"] < 0.05)
                   for k in per_seed[0]["significance_vs_ungated_ndcg"]}}
    out = {"meta": {"seeds": args.seeds, "contaminate": args.contaminate, "drop_last_frac": args.drop_last_frac,
                    "model": MODEL, "n_clean": n, "n_queries": len(q_ids),
                    "clean_similarity_matrix_s": round(t_sim_clean, 2)},
           "clean_corpus_gate": clean_gate, "summary": summary, "per_seed": per_seed}
    path = os.path.join(args.out, "c5_sensitivity.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print("wrote", path)


if __name__ == "__main__":
    main()
