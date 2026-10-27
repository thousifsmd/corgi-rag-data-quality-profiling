#!/usr/bin/env python3
"""
corgi_profile.py — CORGI corpus profiler.

Reads a directory of .txt documents (optionally with a manifest.csv giving dates),
chunks + embeds them, and computes data-quality metrics for a RAG corpus:

  COMPLETENESS   fraction of "thin" chunks (below a token floor); docs missing a date
  VALIDITY       boundary quality: fraction of chunks with clean sentence boundaries
  UNIQUENESS     exact-duplicate ratio AND semantic near-duplicate (redundancy) ratio
  TIMELINESS     staleness: mean chunk age and fraction older than --stale-years
  COVERAGE       topic balance: normalized entropy of embedding clusters (1=balanced)

Outputs a human-readable report to stdout and a machine-readable report.json
(the numbers you paste into the paper's results table).

Usage:
    python -I corgi_profile.py --input ../data/edgar --manifest ../data/edgar/manifest.csv \
        --out ../out --chunk-size 200 --overlap 40 --dup-threshold 0.95 \
        --topics 20 --stale-years 3 --min-tokens 20

(-I runs Python isolated — recommended when reading downloaded data.)
"""
import argparse
import csv
import glob
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime

import numpy as np


# ----------------------------- data loading -----------------------------

def load_manifest(path):
    """doc_id -> {date: 'YYYY-MM-DD', ticker: ...}"""
    meta = {}
    if path and os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                meta[row["doc_id"]] = row
    return meta


def load_docs(input_dir, meta):
    docs = []
    for p in sorted(glob.glob(os.path.join(input_dir, "*.txt"))):
        doc_id = os.path.splitext(os.path.basename(p))[0]
        with open(p, encoding="utf-8", errors="ignore") as f:
            text = f.read()
        d = meta.get(doc_id, {})
        docs.append({"doc_id": doc_id, "text": text, "date": d.get("date")})
    return docs


# Split on sentence-final punctuation followed by whitespace and a capital/quote/digit.
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


def split_sentences(text):
    text = re.sub(r"\s+", " ", text.strip())
    if not text:
        return []
    return [s for s in _SENT_SPLIT.split(text) if s]


def chunk_sentences(text, size, overlap):
    """Pack whole sentences into ~`size`-word chunks without splitting a sentence.
    `overlap` = approx. words of trailing sentences repeated into the next chunk.
    Sentences longer than `size` (tables/headers) are hard-wrapped by words."""
    sents = split_sentences(text)
    if not sents:
        return []
    chunks, cur, cur_w = [], [], 0
    for s in sents:
        w = len(s.split())
        if w >= size:                      # oversized pseudo-sentence (table/header)
            if cur:
                chunks.append(" ".join(cur)); cur, cur_w = [], 0
            words = s.split()
            for j in range(0, len(words), size):
                chunks.append(" ".join(words[j:j + size]))
            continue
        if cur_w + w > size and cur:
            chunks.append(" ".join(cur))
            if overlap > 0:                # carry trailing sentences as overlap
                ov, ow = [], 0
                for ps in reversed(cur):
                    pw = len(ps.split())
                    if ow + pw > overlap:
                        break
                    ov.insert(0, ps); ow += pw
                cur, cur_w = ov, ow
            else:
                cur, cur_w = [], 0
        cur.append(s); cur_w += w
    if cur:
        chunks.append(" ".join(cur))
    return chunks


def build_chunks(docs, size, overlap):
    """Return parallel lists: chunk texts, and per-chunk metadata (doc_id, date)."""
    texts, metas = [], []
    for d in docs:
        for c in chunk_sentences(d["text"], size, overlap):
            texts.append(c)
            metas.append({"doc_id": d["doc_id"], "date": d["date"]})
    return texts, metas


# ----------------------------- embeddings -----------------------------

def embed(texts, model_name, cache):
    if cache and os.path.exists(cache):
        emb = np.load(cache)
        if emb.shape[0] == len(texts):
            print(f"  loaded cached embeddings {emb.shape} from {cache}")
            return emb
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        sys.exit("sentence-transformers not installed. Run: pip install -r requirements.txt")
    print(f"  embedding {len(texts):,} chunks with {model_name} ...")
    model = SentenceTransformer(model_name)
    emb = model.encode(texts, batch_size=64, show_progress_bar=True,
                       normalize_embeddings=True)  # unit vectors -> cosine = dot
    emb = np.asarray(emb, dtype=np.float32)
    if cache:
        np.save(cache, emb)
    return emb


# ----------------------------- metrics -----------------------------

_norm_re = re.compile(r"\s+")

def _norm(s):
    return _norm_re.sub(" ", s.strip().lower())


def completeness(texts, min_tokens):
    thin = sum(1 for t in texts if len(t.split()) < min_tokens)
    return {"thin_chunk_ratio": round(thin / len(texts), 4), "thin_chunks": thin}


def validity_boundary(texts):
    def ok(c):
        c = c.strip()
        if not c:
            return False
        start_ok = c[0].isupper() or c[0].isdigit() or c[0] in "\"'("
        end_ok = c[-1] in ".?!\"')"
        return start_ok and end_ok
    bad = sum(1 for t in texts if not ok(t))
    return {"bad_boundary_ratio": round(bad / len(texts), 4), "bad_boundary_chunks": bad}


def exact_duplicates(texts):
    hashes = [hashlib.md5(_norm(t).encode("utf-8")).hexdigest() for t in texts]
    uniq = len(set(hashes))
    dups = len(hashes) - uniq
    return {"exact_dup_ratio": round(dups / len(hashes), 4),
            "exact_dup_chunks": dups, "unique_chunks": uniq}


def nn_sims(emb):
    """Cosine similarity of each chunk to its nearest OTHER chunk (computed once)."""
    if emb.shape[0] < 2:
        return np.zeros(emb.shape[0], dtype=np.float32)
    from sklearn.neighbors import NearestNeighbors
    nn = NearestNeighbors(n_neighbors=2, metric="cosine").fit(emb)
    dist, _ = nn.kneighbors(emb)
    return (1.0 - dist[:, 1]).astype(np.float32)


def semantic_redundancy(sims, threshold):
    if sims.size == 0:
        return {"redundancy_ratio": 0.0, "near_dup_chunks": 0, "mean_nn_sim": 0.0}
    near = sims >= threshold
    return {"redundancy_ratio": round(float(near.mean()), 4),
            "near_dup_chunks": int(near.sum()),
            "mean_nn_sim": round(float(sims.mean()), 4)}


def redundancy_sweep(sims, taus):
    """Redundancy ratio at each threshold, reusing the same similarity array."""
    if sims.size == 0:
        return {f"{t:.2f}": 0.0 for t in taus}
    return {f"{t:.2f}": round(float((sims >= t).mean()), 4) for t in taus}


def coverage(emb, k):
    k = min(k, emb.shape[0])
    if k < 2:
        return {"coverage_balance": None, "n_topics": k}
    from sklearn.cluster import KMeans
    km = KMeans(n_clusters=k, n_init=10, random_state=0).fit(emb)
    sizes = np.bincount(km.labels_, minlength=k).astype(float)
    p = sizes / sizes.sum()
    ent = -(p * np.log(p + 1e-12)).sum() / np.log(k)   # normalized 0..1 (1 = balanced)
    return {"coverage_balance": round(float(ent), 4),
            "n_topics": k,
            "largest_topic_share": round(float(p.max()), 4),
            "empty_or_tiny_topics": int((sizes < max(1, 0.01 * sizes.sum())).sum())}


def staleness(metas, ref_date, stale_years):
    ages = []
    for m in metas:
        d = m.get("date")
        if not d:
            continue
        try:
            dt = datetime.strptime(d, "%Y-%m-%d").date()
            ages.append((ref_date - dt).days / 365.25)
        except ValueError:
            continue
    if not ages:
        return {"dated_chunk_ratio": 0.0, "mean_age_years": None, "stale_ratio": None}
    ages = np.array(ages)
    return {"dated_chunk_ratio": round(len(ages) / len(metas), 4),
            "mean_age_years": round(float(ages.mean()), 2),
            "max_age_years": round(float(ages.max()), 2),
            "stale_ratio": round(float((ages >= stale_years).mean()), 4)}


# ----------------------------- driver -----------------------------

def main():
    ap = argparse.ArgumentParser(description="Profile a RAG corpus for data quality.")
    ap.add_argument("--input", required=True, help="Directory of .txt documents.")
    ap.add_argument("--manifest", default=None, help="Optional manifest.csv with dates.")
    ap.add_argument("--out", default="../out")
    ap.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")
    ap.add_argument("--chunk-size", type=int, default=200)
    ap.add_argument("--overlap", type=int, default=40)
    ap.add_argument("--dup-threshold", type=float, default=0.95)
    ap.add_argument("--sweep-tau", default="0.90,0.95,0.97",
                    help="Comma-separated thresholds for the redundancy sensitivity sweep.")
    ap.add_argument("--topics", type=int, default=20)
    ap.add_argument("--stale-years", type=float, default=3.0)
    ap.add_argument("--min-tokens", type=int, default=20)
    ap.add_argument("--sample", type=int, default=0,
                    help="Randomly sample N chunks (0 = use all). Keeps first runs fast.")
    ap.add_argument("--ref-date", default=date.today().isoformat(),
                    help="Reference date for staleness (YYYY-MM-DD).")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    ref_date = datetime.strptime(args.ref_date, "%Y-%m-%d").date()

    meta = load_manifest(args.manifest)
    docs = load_docs(args.input, meta)
    if not docs:
        sys.exit(f"No .txt documents found in {args.input}")
    texts, metas = build_chunks(docs, args.chunk_size, args.overlap)
    if not texts:
        sys.exit("No chunks produced (documents empty?)")

    if args.sample and args.sample < len(texts):
        rng = np.random.default_rng(0)
        idx = rng.choice(len(texts), size=args.sample, replace=False)
        texts = [texts[i] for i in idx]
        metas = [metas[i] for i in idx]

    emb = embed(texts, args.model, os.path.join(args.out, "embeddings.npy"))
    sims = nn_sims(emb)                      # nearest-other similarities (computed once)
    taus = [float(x) for x in args.sweep_tau.split(",") if x.strip()]

    n_dated = sum(1 for d in docs if d["date"])
    report = {
        "corpus": {
            "n_docs": len(docs),
            "n_chunks": len(texts),
            "docs_with_date": n_dated,
            "doc_date_completeness": round(n_dated / len(docs), 4),
            "chunk_size": args.chunk_size,
            "overlap": args.overlap,
            "embedding_model": args.model,
            "ref_date": args.ref_date,
        },
        "completeness": completeness(texts, args.min_tokens),
        "validity": validity_boundary(texts),
        "uniqueness_exact": exact_duplicates(texts),
        "uniqueness_semantic": semantic_redundancy(sims, args.dup_threshold),
        "redundancy_sweep": redundancy_sweep(sims, taus),
        "timeliness": staleness(metas, ref_date, args.stale_years),
        "coverage": coverage(emb, args.topics),
    }

    out_json = os.path.join(args.out, "report.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    # ---- pretty print ----
    print("\n" + "=" * 60)
    print("CORGI CORPUS PROFILE")
    print("=" * 60)
    c = report["corpus"]
    print(f"Docs: {c['n_docs']}   Chunks: {c['n_chunks']}   "
          f"Chunk size/overlap: {c['chunk_size']}/{c['overlap']}")
    print(f"Doc date completeness: {c['doc_date_completeness']*100:.1f}%\n")
    rows = [
        ("Completeness  thin-chunk ratio",   report["completeness"]["thin_chunk_ratio"]),
        ("Validity      bad-boundary ratio", report["validity"]["bad_boundary_ratio"]),
        ("Uniqueness    exact-dup ratio",    report["uniqueness_exact"]["exact_dup_ratio"]),
        ("Redundancy    semantic near-dup",  report["uniqueness_semantic"]["redundancy_ratio"]),
        ("              mean NN similarity", report["uniqueness_semantic"]["mean_nn_sim"]),
        ("Timeliness    mean age (yrs)",     report["timeliness"]["mean_age_years"]),
        ("              stale ratio",        report["timeliness"]["stale_ratio"]),
        ("Coverage      topic balance",      report["coverage"]["coverage_balance"]),
        ("              largest topic share",report["coverage"].get("largest_topic_share")),
    ]
    for label, val in rows:
        print(f"  {label:<36} {val}")
    print("  " + "-" * 44)
    print("  Redundancy sensitivity (tau -> ratio):")
    for t, r in report["redundancy_sweep"].items():
        print(f"      tau={t}  ->  {r}")
    print("=" * 60)
    print(f"\nWrote {out_json}")


if __name__ == "__main__":
    main()
