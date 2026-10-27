# CORGI — code

All scripts are CPU-only and self-contained. Install once:

```bash
python -m pip install -r requirements.txt
```

First run downloads the sentence-transformer model(s) (~90 MB MiniLM, ~420 MB MPNet).
Outputs go to `../out/`; downloaded corpora to `../data/` (both git-ignored). Run scripts that
read downloaded data with `python -I` (isolated mode).

## Pipeline scripts

| Script | Purpose | Key output |
|---|---|---|
| `fetch_edgar.py` | Download SEC 10-K filings (ticker→CIK via SEC; incremental, retries) | `../data/edgar/*.txt` + `manifest.csv` |
| `clean_xbrl.py` | Strip inline-XBRL "tag soup" from fetched filings (backs up to `_raw/`) | cleaned `*.txt` in place |
| `corgi_profile.py` | **C1** — profile a corpus: redundancy, staleness, coverage, completeness, validity (+ τ sweep) | `report.json` |
| `fetch_beir.py` | Download a BEIR dataset (default SciFact) — labeled IR ground truth | `../data/beir/<name>/` |
| `corgi_inject.py` | **C2** — inject truncation/duplication defects at doses; measure retrieval dose-response | `c2_dose_response.{json,csv}`, `fig2_dose_response.png` |
| `corgi_gate.py` | **C3** — contaminate with semantic near-dups; compare clean/ungated/exact-dedup/CORGI-gated | `c3_gate_<model>.{json,csv}` |
| `corgi_ablation.py` | Per-dimension gate ablation (redundancy vs. thin) | `c4_ablation.{json,csv}` |
| `make_fig1.py` | Render the pipeline diagram (Figure 1) | `fig1_pipeline.png` |

`corgi_gate.py` and `corgi_ablation.py` import helpers from `corgi_inject.py` (kept in one flat
directory so the imports resolve; `sys.path` is handled for `python -I`).

### Typical run

```bash
# C1 — EDGAR case study
python fetch_edgar.py --email "you@example.com" --tickers XOM COP OXY PSX VLO EOG KMI HAL BKR MPC --per-company 5 --out ../data/edgar
python -I clean_xbrl.py --input ../data/edgar
python -I corgi_profile.py --input ../data/edgar --manifest ../data/edgar/manifest.csv --out ../out --sweep-tau "0.85,0.90,0.95,0.99"

# C2 / C3 / C4 — SciFact
python fetch_beir.py --name scifact --out ../data/beir
python -I corgi_inject.py  --data ../data/beir/scifact --out ../out
python -I corgi_gate.py    --data ../data/beir/scifact --out ../out
python -I corgi_ablation.py --data ../data/beir/scifact --out ../out
python -I corgi_gate.py    --data ../data/beir/scifact --out ../out --model sentence-transformers/all-mpnet-base-v2
```

## Metric definitions (what `corgi_profile.py` computes)

| report.json key | DQ dimension | Meaning |
|---|---|---|
| `completeness.thin_chunk_ratio` | Completeness | fraction of chunks below the token floor θ |
| `validity.bad_boundary_ratio` | Validity | fraction of chunks not starting/ending on clean sentence boundaries |
| `uniqueness_exact.exact_dup_ratio` | Uniqueness | verbatim (normalized-hash) duplicate chunks |
| `uniqueness_semantic.redundancy_ratio` | Uniqueness | chunks whose nearest neighbor cosine ≥ τ (ANN) |
| `redundancy_sweep` | — | redundancy ratio at several τ (robustness) |
| `timeliness.{mean_age_years,stale_ratio}` | Timeliness | chunk age vs. a freshness horizon Δ |
| `coverage.coverage_balance` | Coverage | normalized entropy of embedding clusters (1 = balanced) |

Chunks are **sentence-aligned** (whole sentences packed to ~`--chunk-size` words).

> **Paper-build tooling** (`word_convert.py`, `word_fill.py`, `verify_refs.py`) is separate from the
> research code and documented in [`README_ieee_template_builder.md`](README_ieee_template_builder.md).
> It is Windows + MS Word only and not needed to run any experiment.

## Reproducibility notes
- Deterministic: `--seed` (default 0), KMeans `random_state=0`.
- Embeddings cache per model in `../out/scifact_corpus_emb_<model>.npy`; delete to force recompute.
- Pin versions via `requirements.txt`; the embedding model name is recorded in each output.
