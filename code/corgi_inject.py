#!/usr/bin/env python3
"""
corgi_inject.py — CORGI's C2 causal study: inject controlled corpus-quality DEFECTS into a
labeled IR benchmark and measure the dose-response on retrieval quality.

Defects:
  * truncate   : replace a dose-fraction of documents with their first ~T words
                 (a validity/completeness defect) -> relevant docs lose matching content.
  * duplicate  : append near-duplicate copies of a dose-fraction of documents (a redundancy
                 defect) -> copies crowd the ranking / waste top-k slots.

Metrics: nDCG@10 and Recall@10 against qrels; for duplication also dup_occupancy@10
(fraction of the top-10 that are injected duplicates -> wasted RAG context).

Reads BEIR layout: <data>/corpus.jsonl, queries.jsonl, qrels/test.tsv.
Writes ../out/c2_dose_response.{json,csv} (+ fig if matplotlib present).

Usage:
  python -I corgi_inject.py --data ../data/beir/scifact --out ../out \
      --doses 0,0.1,0.2,0.3,0.4,0.5 --truncate-words 25
"""
import argparse
import csv
import json
import math
import os
import sys

import numpy as np


def load_jsonl(path, id_key="_id"):
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            text = (o.get("title", "") + " " + o.get("text", "")).strip() if "title" in o else o.get("text", "")
            out[str(o[id_key])] = text
    return out


def load_qrels(path):
    qrels = {}
    with open(path, encoding="utf-8") as f:
        rd = csv.reader(f, delimiter="\t")
        header = next(rd, None)
        for row in rd:
            if len(row) < 3:
                continue
            qid, did, score = row[0], row[1], row[2]
            if int(float(score)) > 0:
                qrels.setdefault(str(qid), set()).add(str(did))
    return qrels


def embed(texts, model_name):
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_name)
    e = model.encode(texts, batch_size=64, show_progress_bar=True, normalize_embeddings=True)
    return np.asarray(e, dtype=np.float32)


def ndcg_at_k(ranked, rel, k=10):
    dcg = sum((1.0 / math.log2(i + 2)) for i, d in enumerate(ranked[:k]) if d in rel)
    idcg = sum((1.0 / math.log2(i + 2)) for i in range(min(len(rel), k)))
    return (dcg / idcg) if idcg > 0 else 0.0


def recall_at_k(ranked, rel, k=10):
    return len(set(ranked[:k]) & rel) / len(rel) if rel else 0.0


def evaluate(Qe, Ce, doc_ids, queries, qrels, k=10, dup_flag=None):
    """Score queries against corpus embeddings Ce (rows aligned to doc_ids)."""
    scores = Qe @ Ce.T                      # (nq, ndocs), cosine (unit vectors)
    ndcg = rec = dup_occ = 0.0
    nq = 0
    kk = min(k, Ce.shape[0])
    for i, qid in enumerate(queries):
        rel = qrels.get(qid)
        if not rel:
            continue
        top = np.argpartition(-scores[i], kk - 1)[:kk]
        top = top[np.argsort(-scores[i][top])]
        ranked = [doc_ids[j] for j in top]
        ndcg += ndcg_at_k(ranked, rel, k)
        rec += recall_at_k(ranked, rel, k)
        if dup_flag is not None:
            dup_occ += sum(1 for j in top if dup_flag[j]) / kk
        nq += 1
    out = {"ndcg@10": round(ndcg / nq, 4), "recall@10": round(rec / nq, 4), "queries": nq}
    if dup_flag is not None:
        out["dup_occupancy@10"] = round(dup_occ / nq, 4)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="BEIR dataset dir (corpus/queries/qrels).")
    ap.add_argument("--out", default="../out")
    ap.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")
    ap.add_argument("--doses", default="0,0.1,0.2,0.3,0.4,0.5")
    ap.add_argument("--truncate-words", type=int, default=25)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    rng = np.random.default_rng(args.seed)
    doses = [float(x) for x in args.doses.split(",") if x.strip()]

    corpus = load_jsonl(os.path.join(args.data, "corpus.jsonl"))
    queries = load_jsonl(os.path.join(args.data, "queries.jsonl"))
    qrels = load_qrels(os.path.join(args.data, "qrels", "test.tsv"))

    doc_ids = list(corpus.keys())
    texts = [corpus[d] for d in doc_ids]
    # keep only queries that have qrels AND appear in queries file
    q_ids = [q for q in queries if q in qrels]
    q_texts = [queries[q] for q in q_ids]
    print(f"corpus={len(doc_ids)} docs, eval queries={len(q_ids)}, doses={doses}")

    cache = os.path.join(args.out, "scifact_corpus_emb.npy")
    if os.path.exists(cache) and np.load(cache).shape[0] == len(doc_ids):
        Ce0 = np.load(cache); print("loaded cached corpus embeddings")
    else:
        print("embedding corpus ..."); Ce0 = embed(texts, args.model); np.save(cache, Ce0)
    print("embedding queries ..."); Qe = embed(q_texts, args.model)

    n = len(doc_ids)
    results = {"truncate": [], "duplicate": []}

    # ---- TRUNCATION sweep (validity/completeness defect) ----
    # Nested victim sets (shuffle once; corrupt the first d*N docs) -> monotonic by construction.
    perm_t = rng.permutation(n)
    for d in doses:
        if d == 0:
            res = evaluate(Qe, Ce0, doc_ids, q_ids, qrels)
        else:
            m = int(d * n)
            victims = perm_t[:m]
            Ce = Ce0.copy()
            trunc_texts = [" ".join(texts[j].split()[: args.truncate_words]) for j in victims]
            Ce[victims] = embed(trunc_texts, args.model)
            res = evaluate(Qe, Ce, doc_ids, q_ids, qrels)
        res["dose"] = d
        results["truncate"].append(res)
        print(f"  truncate dose={d}: {res}")

    # ---- DUPLICATION sweep (redundancy defect) ----
    perm_d = rng.permutation(n)                 # nested source sets
    for d in doses:
        if d == 0:
            flag = np.zeros(n, dtype=bool)
            res = evaluate(Qe, Ce0, doc_ids, q_ids, qrels, dup_flag=flag)
        else:
            m = int(d * n)
            src = perm_d[:m]
            Ce = np.vstack([Ce0, Ce0[src]])
            ids = doc_ids + [f"{doc_ids[j]}__dup{t}" for t, j in enumerate(src)]
            flag = np.zeros(Ce.shape[0], dtype=bool); flag[n:] = True
            res = evaluate(Qe, Ce, ids, q_ids, qrels, dup_flag=flag)
        res["dose"] = d
        results["duplicate"].append(res)
        print(f"  duplicate dose={d}: {res}")

    with open(os.path.join(args.out, "c2_dose_response.json"), "w") as f:
        json.dump(results, f, indent=2)
    # flat CSV for easy plotting / pasting
    with open(os.path.join(args.out, "c2_dose_response.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["defect", "dose", "ndcg@10", "recall@10", "dup_occupancy@10"])
        for defect in ("truncate", "duplicate"):
            for r in results[defect]:
                w.writerow([defect, r["dose"], r["ndcg@10"], r["recall@10"],
                            r.get("dup_occupancy@10", "")])

    # optional Fig 2
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(1, 2, figsize=(8, 3.2))
        dt = [r["dose"] for r in results["truncate"]]
        ax[0].plot(dt, [r["ndcg@10"] for r in results["truncate"]], "o-", label="nDCG@10")
        ax[0].plot(dt, [r["recall@10"] for r in results["truncate"]], "s--", label="Recall@10")
        ax[0].set_title("Truncation (validity defect)"); ax[0].set_xlabel("defect dose"); ax[0].legend()
        dd = [r["dose"] for r in results["duplicate"]]
        ax[1].plot(dd, [r["ndcg@10"] for r in results["duplicate"]], "o-", label="nDCG@10")
        ax[1].plot(dd, [r["dup_occupancy@10"] for r in results["duplicate"]], "^--", label="dup occupancy@10")
        ax[1].set_title("Duplication (redundancy defect)"); ax[1].set_xlabel("defect dose"); ax[1].legend()
        fig.tight_layout()
        fig.savefig(os.path.join(args.out, "fig2_dose_response.png"), dpi=200)
        print("wrote fig2_dose_response.png")
    except Exception as e:
        print(f"(matplotlib figure skipped: {e})")

    print("\nWrote c2_dose_response.json/.csv to", args.out)


if __name__ == "__main__":
    main()
