# CORGI: Data-Quality Profiling and Gating for Retrieval-Augmented Generation Corpora

Reference implementation and benchmark for **CORGI** (CORpus + the gate/inspector), a system that profiles a
retrieval-augmented generation (RAG) corpus with computable data-quality metrics and
**gates** defective or redundant content before it is indexed.

The core finding: enterprise corpora are pervasively, *semantically* redundant in a way that
byte-level deduplication cannot see, and that redundancy causally degrades retrieval — so a
profiling-driven admission gate recovers retrieval quality while shrinking the index.

## What's here

| Path | Contents |
|---|---|
| `code/` | all scripts (data fetch, profiler, defect-injection, gate, ablation, figures) + `requirements.txt` |
| `results/` | committed snapshot of the paper's numbers (JSON/CSV) and figures |
| `data/`, `out/` | **git-ignored** — downloaded corpora and embedding caches; |

## Quickstart

```bash
cd code
python -m pip install -r requirements.txt

# 1. Case-study corpus profile (C1) — SEC EDGAR 10-Ks
python fetch_edgar.py --email "you@example.com" --tickers XOM COP OXY PSX VLO EOG KMI HAL BKR MPC --per-company 5 --out ../data/edgar
python -I clean_xbrl.py --input ../data/edgar
python -I corgi_profile.py --input ../data/edgar --manifest ../data/edgar/manifest.csv --out ../out --sweep-tau "0.85,0.90,0.95,0.99"

# 2. Labeled benchmark (C2/C3/C4) — BEIR SciFact
python fetch_beir.py --name scifact --out ../data/beir
python -I corgi_inject.py  --data ../data/beir/scifact --out ../out   # C2 causal dose-response
python -I corgi_gate.py    --data ../data/beir/scifact --out ../out   # C3 gate vs. baselines
python -I corgi_ablation.py --data ../data/beir/scifact --out ../out  # per-dimension ablation
python -I corgi_gate.py --data ../data/beir/scifact --out ../out --model sentence-transformers/all-mpnet-base-v2   # C4 generalization
```

Full per-script documentation and the metric definitions are in [`code/README.md`](code/README.md).

## Reproducibility
- CPU-only; first run downloads the sentence-transformer model(s).
- Deterministic seeds throughout (`--seed`, `random_state=0`).
- `results/` holds the exact numbers reported in the paper so you can diff a fresh run.

## Requirements
Python 3.10+ (tested on 3.14), see `code/requirements.txt`. No GPU required.

## Data sources & licensing
- **SEC EDGAR** 10-K filings — public domain (U.S. government); fetched live, not redistributed here.
- **BEIR / SciFact** — downloaded from the BEIR distribution; see BEIR's license.

## License
MIT — see [`LICENSE`](LICENSE).

## Citation
If you use CORGI or the benchmark, please cite:

```bibtex
@misc{shaik2026corgi,
  author       = {Shaik, Mohammed Thousif},
  title        = {{CORGI}: Data Profiling and Quality-Gating the Retrieval-Augmented Generation Corpus},
  year         = {2026},
  howpublished = {https://github.com/thousifsmd/corgi-rag-data-quality},
  note         = {GitHub repository}
}
```

