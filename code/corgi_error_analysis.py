#!/usr/bin/env python3
"""
corgi_error_analysis.py — qualitative + quantitative error analysis of the CORGI gate on the
SEC EDGAR corpus, and sensitivity of the coverage metric to k. Answers reviewer requests for
(i) examples of chunks wrongly flagged / wrongly admitted, (ii) k-means k sensitivity, and
(iii) checks whether the 57% redundancy headline is inflated by chunk overlap.

Pipeline: rebuild the exact chunks used by corgi_profile.py (same chunker/params), load the
cached embeddings, run Algorithm 1 (thin/boundary rules, then greedy keep-first near-dup removal),
record for every quarantined chunk the KEEPER that caused it, and characterize each pair:
  relation : same-doc (overlap/adjacent), same company other year, other company
  textual  : word-3-shingle Jaccard between chunk and keeper
  numeric  : do the numeric tokens differ? (template text with different figures is NOT redundant)

Usage:
  python -I corgi_error_analysis.py --input ../data/edgar --manifest ../data/edgar/manifest.csv \
      --emb ../out/embeddings.npy --out ../results
"""
import argparse
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corgi_profile as cp  # noqa: E402

NUM = re.compile(r"\d[\d,\.]*")


def boundary_ok(c):
    c = c.strip()
    if not c:
        return False
    return (c[0].isupper() or c[0].isdigit() or c[0] in "\"'(") and c[-1] in ".?!\"')"


def shingles(t, n=3):
    w = t.lower().split()
    return {" ".join(w[i:i + n]) for i in range(max(1, len(w) - n + 1))}


def jacc(a, b):
    return len(a & b) / max(1, len(a | b))


def gate_with_cause(E, valid, tau, block=2048):
    """Algorithm 1: invalid chunks quarantined first (never keepers); greedy keep-first dedup.
    Returns keep mask and cause[j] = index of the kept chunk that removed j (or -1)."""
    N = E.shape[0]
    keep = valid.copy()
    cause = np.full(N, -1, dtype=np.int64)
    for s in range(0, N, block):
        S = E[s:s + block] @ E.T
        for r in range(S.shape[0]):
            i = s + r
            if not keep[i]:
                continue
            js = np.where(S[r, i + 1:] >= tau)[0] + i + 1
            js = js[keep[js]]
            keep[js] = False
            cause[js] = i
    return keep, cause


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--emb", required=True)
    ap.add_argument("--out", default="../results")
    ap.add_argument("--tau", type=float, default=0.95)
    ap.add_argument("--theta", type=int, default=20)
    ap.add_argument("--chunk-size", type=int, default=200)
    ap.add_argument("--overlap", type=int, default=40)
    ap.add_argument("--n-examples", type=int, default=3)
    ap.add_argument("--skip-overlap0", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rng = np.random.default_rng(0)

    meta = cp.load_manifest(a.manifest)
    docs = cp.load_docs(a.input, meta)
    texts, metas = cp.build_chunks(docs, a.chunk_size, a.overlap)
    E = np.load(a.emb)
    assert E.shape[0] == len(texts), f"chunk/embedding mismatch {E.shape[0]} vs {len(texts)}"
    N = len(texts)
    did = [m["doc_id"] for m in metas]
    comp = [d.split("_")[0] for d in did]
    toks = np.array([len(t.split()) for t in texts])
    valid = (toks >= a.theta) & np.array([boundary_ok(t) for t in texts])

    keep, cause = gate_with_cause(E, valid, a.tau)
    q = np.where(~keep)[0]
    thin_or_bad = q[~valid[q]]
    redund = q[valid[q]]
    out = {"N": N, "tau": a.tau, "theta": a.theta, "chunk_size": a.chunk_size, "overlap": a.overlap,
           "quarantined": int(len(q)), "frac_quarantined": round(len(q) / N, 4),
           "quarantined_thin_or_bad_boundary": int(len(thin_or_bad)),
           "quarantined_redundant": int(len(redund))}
    print(f"N={N}: quarantined {len(q)} ({100*len(q)/N:.1f}%): "
          f"{len(thin_or_bad)} thin/bad-boundary, {len(redund)} near-dup")

    # ---- characterize each redundancy removal against its keeper ----
    rel_c = {"same_doc": 0, "same_company_other_year": 0, "other_company": 0}
    rows = []
    shc = {}
    for j in redund:
        i = cause[j]
        if i < 0:
            continue
        rel = ("same_doc" if did[i] == did[j] else
               "same_company_other_year" if comp[i] == comp[j] else "other_company")
        rel_c[rel] += 1
        sj = shc.setdefault(j, shingles(texts[j]))
        si = shc.setdefault(i, shingles(texts[i]))
        jc = jacc(si, sj)
        ni, nj = set(NUM.findall(texts[i])), set(NUM.findall(texts[j]))
        num_differs = (ni != nj)
        rows.append({"j": int(j), "i": int(i), "rel": rel, "jaccard": jc, "num_differs": bool(num_differs),
                     "cos": float(E[i] @ E[j])})
    R = len(rows)
    J = np.array([r["jaccard"] for r in rows])
    out["redundant_pairs"] = R
    out["relation_breakdown"] = {k: {"n": v, "frac": round(v / R, 4)} for k, v in rel_c.items()}
    out["jaccard_buckets"] = {">=0.8 (textual duplicate)": round(float((J >= 0.8).mean()), 4),
                              "0.5-0.8": round(float(((J >= 0.5) & (J < 0.8)).mean()), 4),
                              "<0.5 (similar meaning, different text)": round(float((J < 0.5).mean()), 4)}
    nd = np.array([r["num_differs"] for r in rows])
    out["frac_pairs_with_different_numbers"] = round(float(nd.mean()), 4)
    out["frac_low_jaccard_and_different_numbers"] = round(float(((J < 0.8) & nd).mean()), 4)
    print("relations:", out["relation_breakdown"])
    print("jaccard:", out["jaccard_buckets"], "| differing numbers:", out["frac_pairs_with_different_numbers"])

    def ex(r):
        j, i = r["j"], r["i"]
        return {"quarantined_doc": did[j], "keeper_doc": did[i], "relation": r["rel"],
                "cosine": round(r["cos"], 3), "jaccard": round(r["jaccard"], 3),
                "numbers_differ": r["num_differs"],
                "quarantined_text": texts[j][:420], "keeper_text": texts[i][:420]}

    pick = lambda sel: [ex(rows[k]) for k in rng.permutation(np.where(sel)[0])[:a.n_examples]]
    rel_arr = np.array([r["rel"] for r in rows])
    out["examples_correct_removals"] = pick((J >= 0.8) & (rel_arr != "same_doc") & ~nd)
    out["examples_same_doc_overlap"] = pick(rel_arr == "same_doc")
    out["examples_possible_false_positives"] = pick((J < 0.8) & nd)
    out["examples_thin_or_bad_boundary"] = [{"doc": did[j], "tokens": int(toks[j]), "text": texts[j][:300]}
                                           for j in rng.permutation(thin_or_bad)[:a.n_examples]]

    # ---- slipped through: admitted chunks that have a near-dup at 0.90<=cos<tau ----
    kidx = np.where(keep)[0]
    Ek = E[kidx]
    miss = []
    for s in range(0, len(kidx), 4096):
        S = Ek[s:s + 4096] @ Ek.T
        for r in range(S.shape[0]):
            S[r, s + r] = -1
        mx = S.max(axis=1)
        am = S.argmax(axis=1)
        for r in np.where((mx >= 0.90) & (mx < a.tau))[0]:
            miss.append((kidx[s + r], kidx[am[r]], float(mx[r])))
    out["admitted_with_near_miss_cos_0.90_to_tau"] = {"n": len(miss), "frac_of_admitted": round(len(miss) / len(kidx), 4)}
    mr = [miss[k] for k in rng.permutation(len(miss))[:a.n_examples]]
    out["examples_slipped_through"] = [
        {"doc_a": did[x], "doc_b": did[y], "cosine": round(c, 3),
         "text_a": texts[x][:350], "text_b": texts[y][:350]} for x, y, c in mr]
    print(f"admitted chunks with a 0.90<=cos<{a.tau} neighbour: {len(miss)} ({100*len(miss)/len(kidx):.1f}%)")

    # ---- overlap sensitivity of the redundancy headline ----
    nn = cp.nn_sims(E)
    out["redundancy_with_overlap"] = {"overlap": a.overlap, "red@0.95": round(float((nn >= 0.95).mean()), 4)}
    if not a.skip_overlap0:
        t0, m0 = cp.build_chunks(docs, a.chunk_size, 0)
        cache0 = os.path.join(os.path.dirname(a.emb), "embeddings_overlap0.npy")
        E0 = cp.embed(t0, "sentence-transformers/all-MiniLM-L6-v2", cache0)
        nn0 = cp.nn_sims(E0)
        d0 = [m["doc_id"] for m in m0]
        # near-dup partner in a DIFFERENT document (excludes within-doc adjacency effects)
        from sklearn.neighbors import NearestNeighbors
        nbr = NearestNeighbors(n_neighbors=30, metric="cosine").fit(E0)
        dist, idx = nbr.kneighbors(E0)
        cross = np.array([any((1 - dist[r, c]) >= 0.95 and d0[idx[r, c]] != d0[r] for c in range(1, 30))
                          for r in range(len(t0))])
        out["redundancy_overlap0"] = {"n_chunks": len(t0), "red@0.95": round(float((nn0 >= 0.95).mean()), 4),
                                      "red@0.95_cross_document_only": round(float(cross.mean()), 4),
                                      "exact_dup_ratio": cp.exact_duplicates(t0)["exact_dup_ratio"]}
        print("overlap0:", out["redundancy_overlap0"])

    # ---- coverage: sensitivity to k ----
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    samp = rng.choice(N, 5000, replace=False)
    cov = []
    for k in (5, 10, 20, 50, 100):
        cs = []
        for seed in range(3):
            km = KMeans(n_clusters=k, n_init=3, random_state=seed).fit(E)
            p = np.bincount(km.labels_, minlength=k) / N
            cs.append(float(-(p * np.log(p + 1e-12)).sum() / np.log(k)))
        sil = float(silhouette_score(E[samp], km.predict(E[samp])))
        cov.append({"k": k, "cov_mean": round(float(np.mean(cs)), 4), "cov_std": round(float(np.std(cs, ddof=1)), 4),
                    "silhouette": round(sil, 4), "inertia": round(float(km.inertia_), 1),
                    "largest_cluster_share": round(float(p.max()), 4)})
        print("coverage", cov[-1])
    out["coverage_vs_k"] = cov

    with open(os.path.join(a.out, "c8_error_analysis.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("wrote c8_error_analysis.json")


if __name__ == "__main__":
    main()
