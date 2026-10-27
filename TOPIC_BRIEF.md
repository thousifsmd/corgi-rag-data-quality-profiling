# Paper Topic Brief

**Working title:** *CORGI: Profiling and Quality-Gating the RAG Corpus* 
*(alt subtitle: "Data-Quality Admission Control for Retrieval-Augmented Generation")*

**System name:** **CORGI** — *Corpus Quality **G**ate & **I**nspector* (placeholder; swap freely — a
memorable system name is worth having for a Rank-A systems/data paper).

**Status:** Topic definition. **Target:** a **Rank-A conference** (data / IR / data-mining family).
**Created:** 2026-10-25 · **Reshaped:** 2026-10-25 (from survey-style to conference-style).
**Author profile:** industry practitioner — data governance, data quality, profiling, catalog.

> **This is a conference paper, not a survey.** Keep it tight, system-and-experiment driven, one
> sharp contribution proven with a strong empirical result and a released artifact. It must **not**
> overlap the 2027 SLR (`C:\Thousif\Research\SLR_Output\`) — no literature synthesis as a
> contribution. EB1A strategy lives in memory, not in this paper's body.

---

## 1. The thesis (two sentences)

RAG systems are deployed on data lakes that are never profiled, so semantic duplication,
staleness, topical gaps, and contradictions silently inflate cost and hallucination. **CORGI
profiles a RAG corpus the way we profile a database, predicts which data will hurt retrieval,
and gates it out before indexing — turning data quality into a measurable, enforceable
control for RAG.**

---

## 2. Abstract (conference-length)

Retrieval-augmented generation (RAG) systems are only as reliable as the corpus they retrieve
from, yet that corpus — documents, chunks, and embeddings — is almost never profiled or
quality-controlled the way a governed database is. Defects such as semantic duplication,
staleness, topical gaps, and cross-source contradiction are found only *reactively*, through bad
answers, after they have inflated token cost and hallucination. We present **CORGI**, a system
that (i) profiles a RAG corpus with computable data-quality metrics at the chunk and embedding
level, (ii) predicts, from those profiles, which content will degrade retrieval, and (iii) gates
or quarantines that content before indexing. On public IR/RAG benchmarks and a heterogeneous
energy-sector data lake, CORGI improves retrieval accuracy and answer groundedness while cutting
corpus size and per-query token cost versus ungated and naive-deduplication baselines, and a
controlled defect-injection study establishes a *causal* — not merely correlational — link from
corpus-quality signals to downstream quality. We release the system and a reusable RAG
Corpus-Quality benchmark.

**Keywords:** data quality, data profiling, RAG, embeddings, vector databases, data lakes, LLM,
admission control, benchmark.

> *Replace the qualitative result clause with the real headline number (e.g. "+N% nDCG@10, −M%
> tokens, −K% corpus") before submission. A Rank-A abstract states the number.*

---

## 3. What makes it a paper (the claims — "we show that…")

C1. **Database-style profiling transfers to RAG corpora.** We define computable chunk/embedding
    metrics for redundancy, staleness, and coverage and show they can be produced at scale as a
    *corpus profile report*.
C2. **Corpus-quality signals cause downstream degradation.** A controlled defect-injection study
    shows a dose–response from each defect type to retrieval/answer quality — the paper's
    scientific core, and what separates CORGI from "just dedup" or "just RAG tuning."
C3. **Gating on those signals beats the baselines.** CORGI's admission control improves accuracy
    and groundedness while shrinking the corpus and token cost vs. ungated / exact-dedup / no-profile.
C4. **It generalizes.** Same method, two embedding models and a messy real energy lake → the
    result is not dataset- or embedding-specific.

That's the whole paper. Four claims, one system, one headline table. No RQ1–RQ4 enumeration, no
survey matrix.

---

## 4. Why it's novel (the one-paragraph related-work stance)

Relational **data profiling** (cardinality, FD/UCC/IND discovery) and **data-quality** dimensions
are mature for structured data but have never been operationalized at the chunk/embedding level.
**RAG optimization** work (chunking, retriever tuning, re-ranking) improves retrieval but *assumes
the corpus is given*; **RAG evaluation** work (faithfulness/groundedness metrics) scores *outputs*.
CORGI is the first to govern the *input corpus itself* — defining, profiling, and gating data
quality at the embedding level with a measured causal link to downstream performance. (One
paragraph in the paper, not a table.)

---

## 5. System & method

**Pipeline:** `ingest → chunk → embed → [CORGI: profile → gate] → index → retrieve → generate`.
The novelty is the bracketed stage; the rest is standard scaffolding, swappable behind interfaces.

### 5.1 Profiling (the inspector)
Ship **three dimensions** well rather than five shallowly:
- **Redundancy** — semantic near-duplicate detection via ANN clustering in embedding space
  (cosine-threshold swept), cost-bounded (not O(n²)).
- **Staleness** — chunk age × content-volatility → staleness score + distribution.
- **Coverage** — probe the corpus with a topic/question set; surface uncovered regions.
- *(Deferred to a journal extension: consistency/contradiction, validity/boundary quality.)*
Output: a machine- + human-readable **corpus profile report**, analogous to a DB profile report.

### 5.2 Gating (the gate)
- **v1 rule-based** (per-dimension thresholds) + quarantine store.
- **v2 learned** — profile features → predicted degradation; block/quarantine above a calibrated risk.
- Ablations: each dimension alone vs. combined, to show which signal carries the lift.

### 5.3 Evaluation
- **Baselines:** ungated RAG · exact/byte dedup · retrieval without profiling.
- **Metrics:** recall@k, nDCG@k, MRR (retrieval); faithfulness/groundedness, EM/F1 (answers);
  corpus size, tokens/query, latency (cost).
- **Causal (C2):** inject duplicates / stale / contradictory / truncated chunks at dose levels;
  measure dose–response.

### 5.4 The "money" artifacts for the paper
- **Figure 1:** the CORGI pipeline (the one everyone screenshots).
- **Figure 2:** dose–response curves (defect level → quality drop) — proves C2.
- **Table 1:** CORGI vs. baselines (accuracy ↑, groundedness ↑, size ↓, tokens ↓) — proves C3.
- **Released:** open-source system + RAG Corpus-Quality benchmark (reproducible in one command).

---

## 6. Datasets — DECIDED (2026-10-26)
**Case-study lake = SEC EDGAR 10-K filings for major Texas energy issuers** (XOM, COP, OXY, PSX,
VLO, EOG): free, no-auth bulk API, text-native, and naturally defect-rich (repeated boilerplate →
redundancy; dated filings → staleness; drift across years → consistency). A **general labeled
corpus** (BEIR / NQ / HotpotQA subset) is added later for comparable retrieval metrics. Energy data
is **evaluation only** — the contribution is domain-agnostic. Downloader + menu: `code/` + checklist §4.

---

## 7. Paper anatomy (Rank-A, **6 pages**, IEEE double-column)
Skeleton already written: `paper/main.tex` (IEEEtran `conference`). Page budget:

1. **Intro** — hook, four claims, headline number. (1 p)
2. **DQ model** — computable chunk/embedding definitions. (1.25 pp)
3. **CORGI system** — profiler + gate, Figure 1. (1.5 pp)
4. **Experimental setup** — datasets, baselines, metrics, defect protocol. (0.75 p)
5. **Results** — C1–C4, Figure 2 + Tables. (1.5 pp)
6. **Related work** (1 paragraph) **+ Conclusion.** (0.75 p)

At 6 pages, discussion/limitations fold into Results; if over budget, cut ablation prose first.

> Rank-A reviewers reward: a sharp delta over baselines, a *causal* result, reproducibility, and a
> reusable artifact. They punish: survey framing, vague "framework" papers, and unvalidated claims.

---

## 8. Minimum viable paper (what must exist to submit)

- The DQ model for 3 dimensions (redundancy, staleness, coverage).
- The profiler + the gate, running reproducibly.
- **C2** (defect-injection causal study) and **C3** (gated-vs-baseline table) with real numbers.
- One general benchmark + one energy case study.
- Open-source release + benchmark.

A tight paper proving 3 dimensions + the gate + a causal result beats a broad one that proves nothing.

---

## 9. Open decisions (resolve before building)
- [ ] Final 3 dimensions (recommend redundancy + staleness + coverage).
- [ ] Embedding model(s) (1 primary + 1 for the generalization claim C4).
- [ ] Vector store / ANN backend.
- [x] Headline energy dataset — **SEC EDGAR 10-Ks (Texas energy)** (decided 2026-10-26).
- [ ] Answer-quality ground truth (reuse NQ / HotpotQA labels).
- [ ] Co-author? (affects ambition within Rank-A).
- [ ] System name (CORGI = placeholder).

---

## Scope guardrails
- Contribution stays **data-management / data-quality**; energy = evaluation only.
- **No overlap with the 2027 SLR**; no literature synthesis as a contribution.
- No "expected"/qualitative results in the final submission — state the numbers.
- EB1A field-coherence framing: keep in memory + run past counsel; not in the paper body.
