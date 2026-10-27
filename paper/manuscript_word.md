# CORGI — Word manuscript (paste into Conference-template-A4.doc)

**How to use this file.** Open `Conference-template-A4.doc`. For each block below, copy the
text into the matching placeholder and apply the IEEE **style** named in `[[ ]]`. The template
already carries the correct A4 margins, two-column layout, Times fonts, and auto-numbered
headings — so applying the named style is all you need. This file mirrors `main.tex`; it is the
single source if you author in Word instead of LaTeX. Blocks marked **[TODO]** are not yet
written (same gaps as the LaTeX draft).

> Template rule: *no math/symbols/special characters in the Title or Abstract.* Body equations
> are fine — rebuild them with Word's Equation editor (Insert ▸ Equation) from the linear forms below.

---

## TITLE  `[[Paper Title]]`
CORGI: Profiling and Quality-Gating the Retrieval-Augmented Generation Corpus

## AUTHORS  `[[Author]]` (fill the 6 author blocks; delete unused)
- line 1: Given Name Surname
- line 2: dept. name of organization
- line 3: name of organization
- line 4: City, Country
- line 5: email or ORCID

## ABSTRACT  `[[Abstract]]`  (lead word **Abstract—** in bold)
Retrieval-augmented generation (RAG) systems are only as reliable as the corpus they retrieve
from, yet that corpus — documents, chunks, and embeddings — is almost never profiled or
quality-controlled the way a governed database is. Defects such as semantic duplication,
staleness, topical gaps, and cross-source contradiction are discovered only reactively, through
poor answers, after they have inflated token cost and hallucination. We present CORGI, a system
that (i) profiles a RAG corpus with computable data-quality metrics at the chunk and embedding
level, (ii) predicts which content will degrade retrieval, and (iii) gates or quarantines that
content before indexing. On public IR/RAG benchmarks and a heterogeneous energy-sector document
lake (SEC 10-K filings), CORGI improves retrieval accuracy and groundedness while reducing corpus
size and per-query token cost versus ungated and naive-deduplication baselines; a controlled
defect-injection study establishes a causal link from corpus-quality signals to downstream
quality. We release the system and a reusable RAG corpus-quality benchmark.

## KEYWORDS  `[[Keywords]]`  (lead word **Keywords—** in bold)
data quality, data profiling, retrieval-augmented generation, embeddings, vector databases,
data lakes, large language models, admission control, benchmark

---

## I. INTRODUCTION  `[[Heading 1]]`
**[TODO: 1 paragraph hook — the ungoverned data layer; defects found reactively through bad answers.]**

Body text `[[Text]]`. Our contributions are:
- **C1.** A data-quality model for RAG corpora with computable metrics at the chunk/embedding
  level (redundancy, staleness, coverage; completeness, validity).
- **C2.** A controlled defect-injection study showing a causal dose–response from corpus-quality
  defects to retrieval/answer quality.
- **C3.** CORGI, a profiling-driven quality gate that beats ungated, exact-dedup, and
  no-profile baselines.
- **C4.** An open system and reusable benchmark; results generalize across two embedding models
  and a real energy data lake.

---

## II. DATA-QUALITY MODEL FOR RAG CORPORA  `[[Heading 1]]`
Classical data-quality (DQ) theory defines dimensions — completeness, validity, uniqueness,
timeliness — over the rows and columns of structured data, where a cell is present or absent and
two rows are either equal or not. A RAG corpus has no such schema: its atoms are *chunks* of free
text and their vector *embeddings*, for which equality is approximate and "missing" is ill-defined.
We re-operationalize each dimension as a computable function over chunks and embeddings; every
definition is realized exactly in our reference implementation, so the model is testable rather
than nominal.

### A. Notation  `[[Heading 2]]`
A corpus C is a set of documents; each document d carries a timestamp t_d and is segmented into
*sentence-aligned* chunks (whole sentences packed to a target of W words without splitting a
sentence; over-long table/header runs are hard-wrapped). Let K = {c_1,…,c_N} be the chunk set.
Each chunk c has token length |c| and a unit embedding e(c) in R^D with ||e(c)||=1, so cosine
similarity is the dot product e(c)·e(c′).

### B. Dimensions  `[[Heading 2]]`
*Rebuild each equation with Word's Equation editor from these linear forms.*

- **Completeness** (thin-chunk ratio), token floor θ:
  Comp = (1/N) · Σ_{c∈K} 1[ |c| < θ ].
  Also report document date completeness (fraction of docs with a usable t_d).
- **Validity** (boundary-defect rate): a chunk is boundary-valid if it begins with a capital,
  digit, or opening quote and ends in sentence-final punctuation.
  Val = (1/N) · Σ_{c∈K} 1[ c is not boundary-valid ].
- **Uniqueness (exact)**, hashing a normalized chunk h(c):
  Uniq_ex = 1 − |{ h(c) }| / N.
- **Uniqueness (semantic redundancy)** at threshold τ:
  Red_τ = (1/N) · Σ_{c∈K} 1[ s(c) ≥ τ ],  where s(c) = max_{c′≠c} e(c)·e(c′),
  computed by approximate nearest-neighbor search (near-linear, not O(N²)).
- **Timeliness** with reference time t_ref, age a(c) = t_ref − t_{d(c)} (years), horizon Δ:
  Stale_Δ = (1/N) · Σ_c 1[ a(c) ≥ Δ ];  also report mean age.
- **Coverage**: cluster {e(c)} into K groups with proportions p_1..p_K:
  Cov = −(1/ln K) · Σ_k p_k · ln p_k  ∈ [0,1]  (1 = balanced; low = skew/gaps).

**TABLE I.** DATA-QUALITY DIMENSIONS RE-OPERATIONALIZED FOR A RAG CORPUS  `[[use template table styles; caption style "TableCaption"]]`

| Dimension | Signal | Metric |
|---|---|---|
| Completeness | degenerate chunks | thin-chunk ratio (Comp) |
| Validity | chunk boundary quality | bad-boundary ratio (Val) |
| Uniqueness | exact + embedding near-dups | Uniq_ex, Red_τ |
| Timeliness | chunk age vs. horizon | stale ratio (Stale_Δ) |
| Coverage | topic balance | normalized entropy (Cov) |

---

## III. THE CORGI SYSTEM  `[[Heading 1]]`
Pipeline: ingest → chunk → embed → [CORGI: profile → gate] → index → retrieve → generate.
The novelty is the bracketed stage; the rest is standard scaffolding behind swappable interfaces.
**[TODO: Fig. 1 pipeline. Profiler (ANN near-dup, staleness, coverage). Gate: rule-based v1,
learned v2, quarantine, calibration.]**

---

## IV. EXPERIMENTAL SETUP  `[[Heading 1]]`
**Datasets.** General (labeled): a BEIR/NQ/HotpotQA subset **[TODO pick]**. Case study: SEC EDGAR
10-K filings for ten major energy issuers (XOM, COP, OXY, PSX, VLO, EOG, KMI, HAL, BKR, MPC),
fiscal years 2021–2025.
**Baselines.** ungated RAG; exact/byte deduplication; retrieval without profiling.
**Metrics.** recall@k, nDCG@k, MRR; faithfulness/groundedness, EM/F1; corpus size, tokens/query,
latency.
**Defect injection.** duplicate, stale, contradictory, and truncated chunks at controlled doses.

---

## V. RESULTS  `[[Heading 1]]`

### A. Corpus profile (C1)  `[[Heading 2]]`
Table II reports the measured profile of the EDGAR case-study corpus: 50 annual reports (10-K)
from ten major energy issuers over fiscal years 2021–2025 (filed 2022–2026), segmented into
22,063 sentence-aligned chunks and embedded with a 384-dimensional sentence encoder. The dominant
finding is redundancy: at τ = 0.95, 57.1% of chunks have a near-duplicate, with mean
nearest-neighbor similarity 0.94. Crucially, exact deduplication removes only 6.1% — so
embedding-level profiling surfaces about 9× more redundant content than byte-identical matching,
and roughly 51 further percentage points that exact methods cannot see. Timeliness and validity
are also material: 39.8% of content is at least three years old, and 10.1% of chunks are malformed
units (truncated tables and headers). This redundancy is not an artifact of the similarity
threshold (Table III): even at a stringent τ = 0.99, 32.5% of chunks retain a near-duplicate,
rising to 75.4% at τ = 0.90.

**TABLE II.** MEASURED PROFILE OF THE EDGAR CASE-STUDY CORPUS (50 docs, 22,063 chunks; W=200,
τ=0.95, θ=20, Δ=3 yr, K=20, t_ref=2026-10-26)

| Metric | Value |
|---|---|
| Date completeness | 100.0% |
| Thin-chunk ratio (Comp) | 1.3% |
| Bad-boundary ratio (Val) | 10.1% |
| Exact-dup ratio (Uniq_ex) | 6.1% |
| **Semantic redundancy (Red_0.95)** | **57.1%** |
|  — mean nearest-neighbor similarity | 0.94 |
| Mean chunk age | 2.68 yr |
| Stale ratio (Stale_3yr) | 39.8% |
| Coverage balance (Cov) | 0.97 |

**TABLE III.** REDUNDANCY IS ROBUST TO THE THRESHOLD: FRACTION OF CHUNKS WITH A NEAR-DUPLICATE (Red_τ)

| τ | 0.85 | 0.90 | 0.93 | 0.95 | 0.97 | 0.99 |
|---|---|---|---|---|---|---|
| Red_τ | 87.4% | 75.4% | 65.2% | 57.1% | 47.4% | 32.5% |

### B. Defects cause degradation (C2)  `[[Heading 2]]`
**[TODO: Fig. 2 dose–response curves per defect type.]**

### C. Gating beats baselines (C3)  `[[Heading 2]]`
**[TODO: Table — CORGI vs. ungated / exact-dedup / no-profile on nDCG@10, faithfulness,
corpus size, tokens/query.]**

### D. Ablations and generalization (C4)  `[[Heading 2]]`
**[TODO: per-dimension ablation; second embedding model; energy case study.]**

---

## VI. RELATED WORK  `[[Heading 1]]`
Relational data profiling and data-quality dimensions are mature for structured data but not
operationalized at the chunk/embedding level; RAG-optimization work tunes retrieval but assumes
the corpus is given; RAG-evaluation work scores outputs. CORGI governs the input corpus itself.
**[TODO: cite 8–12 refs.]**

## VII. CONCLUSION  `[[Heading 1]]`
**[TODO: restate contribution + artifact link.]**

## REFERENCES  `[[Heading 1 (unnumbered) / "References"]]`
Use the template's reference style. Starter entries are in `refs.bib`.
