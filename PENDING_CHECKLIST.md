# Pending Work & Build Checklist

**Paper:** *Profiling and Quality-Gating the RAG Corpus* (see `TOPIC_BRIEF.md`)
**Last updated:** 2026-10-25
**Legend — Priority:** 🔴 blocker · 🟠 important · 🟢 nice-to-have. **Owner:** You / Claude / Both.

> This is a *method + system + benchmark* paper. The critical path is **code + experiments**, not
> prose. Prioritize getting a working profiler and a reproducible result before polishing writing.

---

## 0. Decisions to lock before building (🔴 — You / Both)

- [ ] **Scope: which 2–3 DQ dimensions ship first.** Recommend **redundancy (semantic dedup)**,
      **staleness**, **coverage/gap**. Defer consistency + validity to a journal extension.
- [ ] **Embedding model(s).** Pick 1 primary + 1 for robustness (e.g. a strong open model + one
      alternative to show the method isn't embedding-specific).
- [ ] **Vector store / ANN library.** One reference backend (FAISS / HNSWlib / a pgvector or
      Chroma/Qdrant instance) — keep it swappable behind an interface.
- [ ] **Headline case-study dataset** (see §4). Recommend **Volve** (energy, clean license) or
      **Texas RRC** (Texas relevance); **OSDU** if emphasizing the catalog/metadata tie-in.
- [ ] **Answer-quality ground truth** — reuse an existing QA benchmark's labels (HotpotQA / NQ)
      rather than hand-labeling.
- [ ] **Co-author?** Decide early — affects venue ambition and review workload.

---

## 1. Research / design (🔴🟠 — Both)

- [ ] **Formalize the DQ model (claim C1).** Write precise definitions + a computable metric per
      dimension. Output: a definitions table + math, drafted *before* coding so code matches theory.
- [ ] **Design the profile-report schema.** What a "RAG corpus data-profile report" contains
      (per-source + per-corpus stats, flagged items). Mirror a relational data-profile report.
- [ ] **Design the quality-gate decision function (claims C2/C3).** Rule-based v1, learned v2
      (profile features → predicted degradation). Define the training/calibration signal.
- [ ] **Design the causal defect-injection protocol (claim C2 — the scientific core).** Defect
      types (duplicate, stale, contradictory, truncated/bad-boundary), dose levels, dose–response.
- [ ] **Lock evaluation metrics.** Retrieval: recall@k, nDCG@k, MRR. Answer: faithfulness/
      groundedness, EM/F1 where labels exist. Cost: corpus size, tokens/query, latency.
- [ ] **Define baselines.** Ungated RAG · exact/byte dedup · retrieval without profiling.

---

## 2. Algorithm & coding (🔴 — Claude / Both)

> Keep every stage behind a clean interface so backends (embedding model, vector store) are
> swappable. Target a single reproducible CLI: `profile → gate → index → evaluate`.

### 2.1 Harness & scaffolding
- [ ] Repo skeleton, config, deterministic seeds, environment pinning (requirements/lockfile).
- [ ] Ingestion + chunking module (configurable chunk size/overlap; record provenance per chunk).
- [ ] Embedding module (batched, cached to disk to avoid recompute).
- [ ] Vector-index wrapper (build/query, ANN params exposed).

### 2.2 Profiling algorithm (the core novelty)
- [ ] **Redundancy / near-duplicate detection** — ANN clustering in embedding space; cosine
      threshold sweep; report duplicate sets + redundancy ratio. Cost-bounded via ANN, not O(n²).
- [ ] **Staleness profiling** — chunk age (from metadata) × content-volatility signal; staleness
      score + distribution.
- [ ] **Coverage / gap profiling** — embed a query/topic probe set; measure corpus support per
      topic; surface uncovered regions. (Probe set from the eval questions or a topic model.)
- [ ] *(deferred)* **Cross-source consistency** — contradiction detection among co-retrieved chunks.
- [ ] *(deferred)* **Validity** — boundary quality, language/format conformance, well-formedness.
- [ ] **Profile-report generator** — emit machine-readable (JSON) + human-readable report.
- [ ] **Scalability pass** — sampling/sketching for distribution metrics; benchmark runtime vs.
      corpus size; report cost curve.

### 2.3 Quality gate
- [ ] v1 rule-based gate (per-dimension thresholds) + quarantine store.
- [ ] v2 learned gate (profile features → predicted degradation); calibration set.
- [ ] Ablation harness: gate on each dimension alone vs. combined.

### 2.4 Evaluation driver
- [ ] End-to-end runner: build corpus → profile → gate → index → run query set → score.
- [ ] Defect-injection generator (controlled, parameterized).
- [ ] Results collation → tables + figures (auto-generated from result JSON).
- [ ] Reproducibility script: one command reproduces headline numbers.

---

## 3. Experiments (🔴 — Both)

- [ ] **E1 — Profiling validity:** profiler finds known/injected defects (precision/recall of
      detection).
- [ ] **E2 — Causal link (C2):** dose–response of each defect type on retrieval/answer metrics.
- [ ] **E3 — Quality gate (C3):** gated vs. baselines on accuracy, groundedness, size, cost.
- [ ] **E4 — Ablations:** per-dimension contribution; embedding-model robustness; ANN-param
      sensitivity.
- [ ] **E5 — Scalability:** runtime/memory vs. corpus size.
- [ ] **E6 — Energy case study:** full pipeline on the chosen energy lake; show it generalizes to
      messy heterogeneous real data.

---

## 4. Datasets — sample "data lakes" you can download (🟠 — You / Both)

> Goal: public, publishable sources (no employer IP). Mix **general IR/RAG corpora** (for
> standard, comparable metrics) with **one messy enterprise/energy lake** (for the case study).

### 4.1 General IR / RAG corpora (for comparable, headline metrics)
| Dataset | What it is | Why / notes | Where |
|---|---|---|---|
| **BEIR** | 18-task heterogeneous IR benchmark | de-facto retrieval benchmark; many domains | github.com/beir-cellar/beir |
| **MS MARCO** | large passage ranking + QA | big, standard, good for scale tests | microsoft.github.io/msmarco |
| **Natural Questions (NQ)** | real Google queries + Wikipedia answers | QA ground truth for answer metrics | ai.google.com/research/NaturalQuestions |
| **HotpotQA** | multi-hop QA over Wikipedia | tests coverage/consistency; has labels | hotpotqa.github.io |
| **KILT** | knowledge-intensive tasks over one Wikipedia snapshot | unified corpus, several tasks | github.com/facebookresearch/KILT |
| **Wikipedia dump** | full encyclopedia corpus | easy to chunk; inject defects at will | dumps.wikimedia.org |
| **arXiv dataset** | scientific papers (metadata + text) | dates → great for *staleness* experiments | kaggle.com (Cornell arXiv) / arxiv.org/help/bulk_data |

### 4.2 Energy-sector "data lake" case study (messy, heterogeneous, Texas-relevant)
| Dataset | What it is | Why it fits | Where / how to get |
|---|---|---|---|
| **Volve** (Equinor) | full open field dataset: well logs, reports, seismic, production — ~40k files, multiple formats | the canonical open, *publishable* oil-&-gas lake; heterogeneity is the point | data.equinor.com → "Volve" (free account; open license) |
| **Texas RRC** | Railroad Commission of Texas public well, production, permit, completion data | direct Texas relevance; real regulatory/enterprise data; messy formats | rrc.texas.gov → Research & Statistics / data downloads (also RRC online query + bulk) |
| **OSDU** | Open Subsurface Data Universe — schemas + open test datasets + reference platform | ties to the *catalog/metadata* angle; industry-standard governance substrate | community.opengroup.org/osdu (GitLab) + OSDU Forum open test data |
| **PPDM** | Professional Petroleum Data Management reference data model | metadata/catalog framing; schema source | ppdm.org |
| **SEC EDGAR** | 10-K / 10-Q filings of energy companies (free text) | large, dated, real enterprise docs → RAG corpus + staleness | sec.gov/edgar (full-text + bulk) |
| **DOE OSTI** | U.S. Dept. of Energy technical reports (open) | open energy document corpus for RAG | osti.gov |
| **EIA open data** | U.S. Energy Information Administration datasets + API | structured energy data; metadata-rich | eia.gov/opendata |
| **USGS energy data** | geological/energy datasets | supplementary heterogeneity | usgs.gov |

> **Recommendation:** headline case study = **Volve** (clean license, genuinely heterogeneous
> "lake") and/or **SEC EDGAR energy filings** (text-heavy, dated → perfect for staleness +
> coverage). Add **OSDU/PPDM** only if you want to push the catalog/metadata narrative.
> **Check each license before redistributing any derived benchmark; cite sources.**

### 4.3 Dataset tasks
- [ ] Download + stage 1 general corpus (recommend BEIR subset or NQ/HotpotQA for labels).
- [ ] Download + stage the energy case-study lake (Volve and/or EDGAR energy subset).
- [ ] Build the **defect-injected variants** (duplicate/stale/contradictory/truncated).
- [ ] Record license + provenance for every source (needed for the released benchmark).
- [ ] Decide what (if anything) of the benchmark is redistributable vs. "reproduce via script."

---

## 5. Artifact release (🟠 — Both)

- [ ] Open-source the profiler + gate + eval harness (clean README, one-command repro).
- [ ] Package the **RAG Corpus Quality Benchmark** (corpora refs + injected variants + harness).
- [ ] Archive a versioned release (e.g. Zenodo DOI) — citable artifact = impact evidence.
- [ ] License choice for code + benchmark (MIT or Apache-2.0 typical).

### 5a. GitHub URL in the paper (normal & encouraged for a systems/benchmark paper)
- [ ] **Add an Availability footnote + statement** to the paper linking the GitHub repo
      (placeholder until the repo exists). Placement: first-page footnote and/or an
      "Availability" statement before References. (Claude can add this to the docx.)
- [ ] **Double-blind caveat:** if the target venue reviews double-blind, the *review* version must
      hide BOTH the author block AND the code URL — use an anonymized mirror
      (e.g. anonymous.4open.science) or omit the URL for review; restore real name + GitHub for
      camera-ready. (Single-blind / IEEE Access journal → real URL is fine directly.)
      Does NOT conflict with EB1A — the *published* version carries name + repo.
- [ ] **Mint a Zenodo DOI** for a versioned release (GitHub↔Zenodo) — permanent + citable; better
      than a bare GitHub link and supports the EB1A impact story.
- [ ] **Repo hygiene before linking:** README with run commands, requirements.txt, LICENSE; do NOT
      commit downloaded EDGAR/SciFact data or large embedding caches — ship the scripts that
      regenerate them.

---

## 6. Writing (🟠 — Both; after first real results)

- [ ] Abstract (drafted ✅ in `TOPIC_BRIEF.md` — update with real numbers).
- [ ] Intro + motivation (use the "ungoverned data layer" framing).
- [ ] Related work (one paragraph positioning *against* prior work, per brief §4 — not a survey;
      keep distinct from the SLR).
- [ ] DQ model / definitions (§5.1).
- [ ] Profiling algorithm + complexity.
- [ ] Quality gate.
- [ ] Experiments + results (tables/figures auto-generated).
- [ ] Discussion, limitations, threats to validity.
- [ ] Reproducibility statement + artifact links.
- [ ] Figures: pipeline diagram, profile-report example, dose–response, gated-vs-baseline bars.

---

## 7. Cross-cutting guardrails (🔴 — standing rules)

- [ ] Contribution stays **data-management / data-quality**; energy data is **evaluation only**.
- [ ] **No overlap with the 2027 SLR** (`SLR_Output/`): no literature synthesis as a contribution.
- [ ] Keep numbers honest — no "expected" results language in the final submission.
- [ ] Loop in immigration counsel on the field-coherence framing before committing (EB1A).

---

## Recommended order of attack

1. **Lock §0 decisions** (dimensions, embedding model, vector store, case-study dataset).
2. **Formalize the DQ model** (§1) so code matches theory.
3. **Build the harness + profiler for the first 2–3 dimensions** (§2.1–2.2).
4. **Run E1 + E2** (profiling validity + causal link) — the scientific core.
5. **Add the gate + run E3/E4** (the impact result).
6. **Energy case study (E6) + scalability (E5).**
7. **Release artifact, then write up with real numbers.**
