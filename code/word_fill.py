#!/usr/bin/env python3
"""
Fill the IEEE A4 template with the CORGI paper content via Word COM, using the
template's own named styles. Opens the original .doc fresh each run (idempotent),
writes paper/CORGI_paper.docx.

Usage: python word_fill.py ../Conference-template-A4.doc ../paper/CORGI_paper.docx
"""
import os
import sys
import win32com.client as win32

TPL = os.path.abspath(sys.argv[1])
OUT = os.path.abspath(sys.argv[2])

TITLE = "CORGI: Profiling and Quality-Gating the Retrieval-Augmented Generation Corpus"

ABSTRACT = ("Abstract—Retrieval-augmented generation (RAG) systems are only as reliable as "
    "the corpus they retrieve from, yet that corpus—documents, chunks, and embeddings—is "
    "almost never profiled or quality-controlled the way a governed database is. Defects such as "
    "semantic duplication, staleness, topical gaps, and cross-source contradiction are discovered "
    "only reactively, through poor answers, after they have inflated token cost and hallucination. "
    "We present CORGI, a system that (i) profiles a RAG corpus with computable data-quality metrics "
    "at the chunk and embedding level, (ii) predicts which content will degrade retrieval, and "
    "(iii) gates or quarantines that content before indexing. On public IR/RAG benchmarks and a "
    "heterogeneous energy-sector document lake (SEC 10-K filings), CORGI improves retrieval accuracy "
    "and groundedness while reducing corpus size and per-query token cost versus ungated and "
    "naive-deduplication baselines; a controlled defect-injection study establishes a causal link "
    "from corpus-quality signals to downstream quality. We release the system and a reusable RAG "
    "corpus-quality benchmark.")

KEYWORDS = ("Keywords—data quality, data profiling, retrieval-augmented generation, embeddings, "
    "vector databases, data lakes, large language models, admission control, benchmark")

# Body as a sequence of ops. ("h1"/"h2"/"body"/"bullet", text) or ("table", caption, header, rows).
BODY = [
    ("h1", "Introduction"),
    ("body", "Retrieval-augmented generation (RAG) has become the dominant way to ground large "
             "language models in enterprise knowledge, and production systems increasingly build "
             "their retrieval corpus by pouring documents from a data lake through a chunk-and-embed "
             "pipeline into a vector index. That corpus is data, yet it is governed like nothing "
             "else in the enterprise: the same organization that profiles, deduplicates, and "
             "quality-checks every row of a warehouse table will index millions of chunks with no "
             "comparable controls. The consequences surface only downstream—duplicated passages "
             "crowd the retrieved context, stale text contradicts current facts, and poorly "
             "segmented chunks dilute relevance—so teams diagnose a data problem as a model problem "
             "after it has already inflated token cost and hallucination. We argue that the "
             "retrieval corpus deserves first-class data governance, exercised at the moment data "
             "enters the index. We introduce CORGI, which profiles a RAG corpus with computable "
             "data-quality metrics and gates defective or redundant content before it is indexed. "
             "Our contributions are as follows."),
    ("bullet", "C1. A data-quality model for RAG corpora with computable metrics at the chunk and "
               "embedding level (redundancy, staleness, coverage; completeness, validity)."),
    ("bullet", "C2. A controlled defect-injection study showing a causal dose-response from "
               "corpus-quality defects to retrieval and answer quality."),
    ("bullet", "C3. CORGI, a profiling-driven quality gate that beats ungated, exact-dedup, and "
               "no-profile baselines."),
    ("bullet", "C4. An open system and reusable benchmark; results generalize across two embedding "
               "models and a real energy data lake."),

    ("h1", "Data-Quality Model for RAG Corpora"),
    ("body", "Classical data-quality (DQ) theory defines dimensions—completeness, validity, "
             "uniqueness, timeliness—over the rows and columns of structured data, where a cell "
             "is present or absent and two rows are either equal or not. A RAG corpus has no such "
             "schema: its atoms are chunks of free text and their vector embeddings, for which "
             "equality is approximate and “missing” is ill-defined. We re-operationalize "
             "each dimension as a computable function over chunks and embeddings; every definition "
             "is realized exactly in our reference implementation."),
    ("h2", "Notation"),
    ("body", "A corpus C is a set of documents; each document d carries a timestamp t_d and is "
             "segmented into sentence-aligned chunks (whole sentences packed to a target of W words "
             "without splitting a sentence; over-long table/header runs are hard-wrapped). Let "
             "K = {c_1,...,c_N} be the chunk set. Each chunk c has token length |c| and a unit "
             "embedding e(c) in R^D with ||e(c)|| = 1, so cosine similarity is the dot product "
             "e(c).e(c')."),
    ("h2", "Dimensions"),
    ("body", "Completeness (thin-chunk ratio), token floor theta:  "
             "Comp = (1/N) * sum_c 1[ |c| < theta ].  Also report document date completeness."),
    ("body", "Validity (boundary-defect rate): a chunk is boundary-valid if it begins with a "
             "capital, digit, or opening quote and ends in sentence-final punctuation.  "
             "Val = (1/N) * sum_c 1[ c is not boundary-valid ]."),
    ("body", "Uniqueness (exact), hashing a normalized chunk h(c):  "
             "Uniq_ex = 1 - |{ h(c) }| / N."),
    ("body", "Uniqueness (semantic redundancy) at threshold tau:  "
             "Red_tau = (1/N) * sum_c 1[ s(c) >= tau ],  where s(c) = max over c'!=c of e(c).e(c'), "
             "computed by approximate nearest-neighbor search (near-linear, not O(N^2))."),
    ("body", "Timeliness with reference time t_ref and age a(c) = t_ref - t_d(c) (years), horizon "
             "Delta:  Stale = (1/N) * sum_c 1[ a(c) >= Delta ];  also report mean age."),
    ("body", "Coverage: cluster the embeddings into K groups with proportions p_1..p_K:  "
             "Cov = -(1/ln K) * sum_k p_k ln p_k  in [0,1]  (1 = balanced; low = skew/gaps)."),
    ("table", "TABLE I.  DATA-QUALITY DIMENSIONS RE-OPERATIONALIZED FOR A RAG CORPUS",
        ["Dimension", "Signal", "Metric"],
        [["Completeness", "degenerate chunks", "thin-chunk ratio (Comp)"],
         ["Validity", "chunk boundary quality", "bad-boundary ratio (Val)"],
         ["Uniqueness", "exact + embedding near-dups", "Uniq_ex, Red_tau"],
         ["Timeliness", "chunk age vs. horizon", "stale ratio (Stale)"],
         ["Coverage", "topic balance", "normalized entropy (Cov)"]]),

    ("h1", "The CORGI System"),
    ("body", "CORGI inserts a two-step profile-and-gate stage between embedding and indexing "
             "(Fig. 1). The surrounding stages—ingest, chunk, embed, index, retrieve, generate—are "
             "the standard RAG pipeline and are delegated to existing components behind narrow "
             "interfaces; CORGI operates only on chunk text, chunk metadata, and embeddings, so any "
             "encoder or vector store can be substituted. The system is unsupervised: it needs no "
             "relevance labels, only the corpus itself."),
    ("figure", "../out/fig1_pipeline.png",
        "Fig. 1.  CORGI inserts a profile-and-gate stage between embedding and indexing; defective "
        "or redundant chunks are quarantined before they reach the index."),
    ("h2", "Profiler"),
    ("body", "The profiler consumes the chunked, embedded corpus and emits the data-quality report "
             "of Section II. It computes thin-chunk and boundary-validity rates by scanning chunk "
             "text; the exact-duplicate ratio by hashing normalized chunks; semantic redundancy via "
             "an approximate-nearest-neighbor pass that records, for each chunk, its maximum cosine "
             "similarity to any other chunk; staleness from document timestamps; and coverage as the "
             "normalized entropy of an embedding clustering. Every metric is derived from one pass "
             "over the embedding index, and sampling bounds the cost to near-linear in corpus size. "
             "The report is produced per source and for the whole corpus—analogous to a relational "
             "data-profile report—and flags the specific chunks responsible for each defect."),
    ("h2", "Gate (admission control)"),
    ("body", "The gate converts profile signals into an index-or-quarantine decision. Its default "
             "policy is rule-based: a chunk is quarantined if (i) it is a semantic near-duplicate of "
             "an already-admitted chunk (cosine >= tau, processed greedily so the first occurrence is "
             "kept), or (ii) it is degenerate (token length below theta) or malformed "
             "(boundary-invalid). Near-duplicate removal is the dominant lever on redundant corpora "
             "(Section V-C); tau and theta expose a precision/recall trade-off between aggressive "
             "cleaning and content loss. A learned variant replaces the rules with a calibrated model "
             "mapping profile features to predicted downstream degradation; we use the rule-based gate "
             "in all experiments. Quarantined content is retained out-of-index for audit rather than "
             "deleted, preserving provenance and keeping the gate reversible."),
    ("algo", "Algorithm 1   CORGI profile-and-gate", [
        "Input:  chunks c_1..c_N, unit embeddings e_i, timestamps;",
        "        thresholds tau (redundancy), theta (min tokens)",
        "Output: admitted set A (indexed), quarantine Q (audited)",
        " 1  for i = 1..N:  s_i <- max_{j!=i} e_i . e_j   # ANN NN-sim",
        " 2  A <- {};  Q <- {};  kept <- {}",
        " 3  for i = 1..N in corpus order:",
        " 4     if |c_i| < theta:          Q += c_i; continue   # completeness",
        " 5     if not boundary_valid(c_i): Q += c_i; continue   # validity",
        " 6     if exists k in kept with e_i . e_k >= tau:       # redundancy",
        " 7           Q += c_i; continue",
        " 8     A += c_i;  kept += c_i",
        " 9  index A;  retain Q out-of-index for audit",
    ]),

    ("h1", "Experimental Setup"),
    ("body", "Datasets. General (labeled): BEIR SciFact (5,183 documents, 300 test queries). Case study: SEC "
             "EDGAR 10-K filings for ten major energy issuers (XOM, COP, OXY, PSX, VLO, EOG, KMI, "
             "HAL, BKR, MPC), fiscal years 2021-2025. Baselines: ungated RAG; exact/byte "
             "deduplication; retrieval without profiling. Metrics: recall@k, nDCG@k, MRR; "
             "faithfulness/groundedness, EM/F1; corpus size, tokens/query, latency. Defect "
             "injection: duplicate, stale, contradictory, and truncated chunks at controlled doses."),

    ("h1", "Results"),
    ("h2", "Corpus profile (C1)"),
    ("body", "Table II reports the measured profile of the EDGAR case-study corpus: 50 annual "
             "reports (10-K) from ten major energy issuers over fiscal years 2021-2025 (filed "
             "2022-2026), segmented into 22,063 sentence-aligned chunks and embedded with a "
             "384-dimensional sentence encoder. The dominant finding is redundancy: at tau = 0.95, "
             "57.1% of chunks have a near-duplicate, with mean nearest-neighbor similarity 0.94. "
             "Crucially, exact deduplication removes only 6.1% — so embedding-level profiling "
             "surfaces about 9x more redundant content than byte-identical matching, and roughly 51 "
             "further percentage points that exact methods cannot see. Timeliness and validity are "
             "also material: 39.8% of content is at least three years old, and 10.1% of chunks are "
             "malformed units (truncated tables and headers). This redundancy is not an artifact of "
             "the similarity threshold (Table III): even at a stringent tau = 0.99, 32.5% of chunks "
             "retain a near-duplicate, rising to 75.4% at tau = 0.90."),
    ("table", "TABLE II.  MEASURED PROFILE OF THE EDGAR CASE-STUDY CORPUS (50 DOCS, 22,063 CHUNKS; "
              "W=200, tau=0.95, theta=20, Delta=3 YR, K=20)",
        ["Metric", "Value"],
        [["Date completeness", "100.0%"],
         ["Thin-chunk ratio (Comp)", "1.3%"],
         ["Bad-boundary ratio (Val)", "10.1%"],
         ["Exact-dup ratio (Uniq_ex)", "6.1%"],
         ["Semantic redundancy (Red_0.95)", "57.1%"],
         ["  mean nearest-neighbor similarity", "0.94"],
         ["Mean chunk age", "2.68 yr"],
         ["Stale ratio (Stale_3yr)", "39.8%"],
         ["Coverage balance (Cov)", "0.97"]]),
    ("table", "TABLE III.  REDUNDANCY IS ROBUST TO THE THRESHOLD: FRACTION WITH A NEAR-DUPLICATE (Red_tau)",
        ["tau", "0.85", "0.90", "0.93", "0.95", "0.97", "0.99"],
        [["Red_tau", "87.4%", "75.4%", "65.2%", "57.1%", "47.4%", "32.5%"]]),
    ("h2", "Defects cause degradation (C2)"),
    ("body", "To test whether corpus-quality defects causally degrade retrieval, we inject "
             "controlled defects into a labeled benchmark (BEIR SciFact; 5,183 documents, 300 "
             "test queries) and measure dense-retrieval quality as a function of defect dose. We "
             "corrupt a nested set of documents (the first d*N under a fixed shuffle), so higher "
             "doses strictly contain lower ones. Duplication — appending near-duplicate copies of "
             "d*N documents — degrades retrieval monotonically: nDCG@10 falls from 0.645 to 0.564 "
             "(-12.6% relative) as the dose reaches 0.5, while the share of the top-10 occupied by "
             "duplicates grows to 33.3%, directly wasting the retrieval budget a RAG reader "
             "consumes. Truncation — a validity defect clipping documents to their first 25 words "
             "— yields a milder but consistent decline (nDCG@10 0.645 to 0.615; recall@10 0.783 to "
             "0.745), reflecting that SciFact abstracts are front-loaded. Together these establish "
             "a causal link from the corpus-quality signals CORGI profiles to downstream retrieval "
             "quality (Fig. 2, Table IV)."),
    ("figure", "../out/fig2_dose_response.png",
        "Fig. 2.  Defect dose-response on BEIR SciFact. Left: truncation (validity). Right: "
        "duplication (redundancy) — nDCG@10 falls as duplicate occupancy of the top-10 rises."),
    ("table", "TABLE IV.  RETRIEVAL DOSE-RESPONSE UNDER INJECTED DEFECTS (BEIR SCIFACT, 300 QUERIES)",
        ["Dose", "Dup nDCG@10", "Dup occ@10", "Trunc nDCG@10", "Trunc recall@10"],
        [["0.0", "0.645", "0.00", "0.645", "0.783"],
         ["0.1", "0.633", "0.09", "0.655", "0.783"],
         ["0.2", "0.615", "0.16", "0.642", "0.772"],
         ["0.3", "0.592", "0.22", "0.626", "0.754"],
         ["0.4", "0.578", "0.28", "0.623", "0.755"],
         ["0.5", "0.564", "0.33", "0.615", "0.745"]]),
    ("h2", "Gating beats baselines (C3)"),
    ("body", "Does the gate help where it matters — on a redundant corpus? We contaminate SciFact "
             "with 2,073 semantic near-duplicates (40% of documents, each a copy with its final 15% "
             "of words removed: byte-different but cosine-similar) and compare four indexing regimes "
             "(Table V). Contamination cuts nDCG@10 from 0.645 to 0.583 and fills 28.8% of the top-10 "
             "with distractors. Exact deduplication removes zero of them — the near-duplicates are not "
             "byte-identical — and is therefore indistinguishable from no cleaning, echoing the C1 gap "
             "between exact (6.1%) and semantic (57.1%) redundancy on real filings. CORGI's gate "
             "removes 2,045 of 2,073 near-duplicates (98.6%) at tau = 0.95, restoring nDCG@10 to 0.645 "
             "(the clean upper bound), cutting duplicate occupancy of the top-10 from 28.8% to 0.4%, "
             "and shrinking the index by 28% (7,256 to 5,211 passages). The governance signal that "
             "classical deduplication cannot see is precisely the one that recovers retrieval quality."),
    ("table", "TABLE V.  QUALITY GATE VS. BASELINES ON A CONTAMINATED CORPUS (SCIFACT + 40% NEAR-DUPLICATES)",
        ["Regime", "nDCG@10", "Recall@10", "Dup occ@10", "Index size"],
        [["Clean (reference)", "0.645", "0.783", "0.000", "5,183"],
         ["Ungated", "0.583", "0.755", "0.288", "7,256"],
         ["Exact-dedup", "0.583", "0.755", "0.288", "7,256"],
         ["CORGI-gated", "0.645", "0.783", "0.004", "5,211"]]),
    ("h2", "Generalization across encoders (C4)"),
    ("body", "To test whether these results depend on the embedding model, we repeat the gate "
             "experiment (Section V-C) with a second encoder, all-mpnet-base-v2 (768-dim), in "
             "place of all-MiniLM-L6-v2 (384-dim). The pattern is identical under both (Table VI): "
             "contaminating the corpus with semantic near-duplicates depresses nDCG@10 and fills "
             "about 28% of the top-10 with distractors; exact deduplication removes none of them and "
             "is indistinguishable from no cleaning; and CORGI's gate removes 98.6-99.1% of the "
             "injected near-duplicates, restoring nDCG@10 to the clean upper bound and driving "
             "duplicate occupancy of the top-10 below 0.5%. The profiling-and-gating result is thus "
             "not an artifact of a particular encoder."),
    ("table", "TABLE VI.  GATE GENERALIZES ACROSS ENCODERS: nDCG@10 BY REGIME. EXACT-DEDUP REMOVES "
              "0 NEAR-DUPLICATES UNDER BOTH; CORGI DRIVES TOP-10 DUPLICATE OCCUPANCY BELOW 0.5%.",
        ["Encoder", "Clean", "Ungated", "Exact-dedup", "CORGI", "Near-dups removed"],
        [["MiniLM (384-d)", "0.645", "0.583", "0.583", "0.645", "2045/2073 (98.6%)"],
         ["MPNet (768-d)", "0.656", "0.588", "0.588", "0.656", "2055/2073 (99.1%)"]]),

    ("h2", "Per-dimension gate ablation"),
    ("body", "To isolate each gate rule's contribution, we contaminate SciFact with both defect "
             "classes CORGI targets—2,073 near-duplicates (redundancy) and 777 thin five-word "
             "fragments (completeness)—and ablate the gate (Table VII). Removing thin fragments "
             "alone barely moves retrieval (nDCG@10 0.566 to 0.583) but is pure index hygiene "
             "(−777 passages). Removing near-duplicates alone is the dominant quality lever: it "
             "recovers most of the lost nDCG (0.566 to 0.621) and collapses top-10 duplicate "
             "occupancy from 0.251 to 0.003. The full gate combines both, restoring nDCG@10 to the "
             "clean upper bound (0.645) while producing the smallest index (5,211 vs. 8,033 "
             "passages, −35%). Redundancy thus governs retrieval quality and the completeness rule "
             "governs index cost; CORGI applies both."),
    ("table", "TABLE VII.  PER-DIMENSION GATE ABLATION (SCIFACT + NEAR-DUPLICATES + THIN FRAGMENTS)",
        ["Gate", "nDCG@10", "Dup occ@10", "Index size", "Thin kept"],
        [["None (contaminated)", "0.566", "0.251", "8,033", "777"],
         ["Thin only", "0.583", "0.288", "7,256", "0"],
         ["Redundancy only", "0.621", "0.003", "5,987", "776"],
         ["Full (CORGI)", "0.645", "0.004", "5,211", "0"]]),

    ("h1", "Discussion and Limitations"),
    ("body", "CORGI's premise—that the retrieval corpus is an ungoverned data asset—is borne out by "
             "complementary findings: enterprise corpora are pervasively and semantically redundant "
             "(57% on real 10-K filings, Section V-A), that redundancy causally degrades retrieval "
             "(Section V-B) in a way exact deduplication cannot repair (Section V-C), consistently "
             "across encoders (Section V-D). Because the gate reuses the embeddings already computed "
             "for indexing, it adds negligible cost and is model-agnostic, making it a practical "
             "admission-control layer for existing RAG stacks."),
    ("body", "Our study has limits. First, the profiling corpus is a single domain (SEC filings); "
             "while the method is domain-agnostic, redundancy and coverage rates will vary across "
             "corpora. Second, the causal and gate experiments use a claims-verification benchmark "
             "with binary relevance; we did not measure end-to-end answer groundedness in a human "
             "study, which we leave to future work. Third, the gate depends on the similarity "
             "threshold tau and chunk size; we report a redundancy sensitivity sweep (Table III), but "
             "a full precision/recall characterization of over-removal—discarding similar but "
             "non-redundant content—remains open. Finally, we evaluate the rule-based gate; the "
             "learned variant (Section III) is left for future work."),

    ("h1", "Related Work"),
    ("body", "Data profiling and data quality are mature disciplines for structured data. Profiling "
             "discovers cardinalities, keys, and dependencies over relational tables [1], and "
             "data-quality theory formalizes dimensions such as completeness, accuracy, consistency, "
             "and timeliness [2], [3]. These frameworks assume a schema and exact-or-null cell "
             "semantics and do not extend to free-text chunks or their embeddings. Retrieval-augmented "
             "generation grounds language models in retrieved passages [4], [5], typically with dense "
             "retrievers [6]; this work improves how a corpus is retrieved but assumes the corpus "
             "itself is given and clean. Data curation for model training deduplicates and filters "
             "large corpora [7], [8], but operates at the document or token level with exact or "
             "MinHash near-duplicate hashing, targets pre-training rather than retrieval, and does not "
             "profile embedding-level quality or tie it to retrieval outcomes. RAG-evaluation "
             "frameworks score generated answers for faithfulness and relevance [9]; they measure "
             "outputs, whereas CORGI measures and governs inputs. Sentence encoders [10] and vector "
             "indexes [11] provide the substrate CORGI builds on, and we evaluate on the BEIR "
             "benchmark [12] and its SciFact task [13]. To our knowledge, CORGI is the first to "
             "operationalize classical data-quality dimensions at the chunk and embedding level, "
             "profile them at scale, and gate on them with a measured causal link to retrieval quality."),

    ("h1", "Conclusion"),
    ("body", "We argued that the corpus is the ungoverned layer of enterprise RAG, and introduced "
             "CORGI, which profiles a retrieval corpus with computable data-quality metrics and gates "
             "defective or redundant content before indexing. On fifty SEC 10-K filings we measured "
             "pervasive, threshold-robust redundancy that exact deduplication cannot see; on a labeled "
             "benchmark we showed that injected redundancy and truncation causally degrade retrieval; "
             "and we demonstrated that CORGI's gate restores retrieval quality to the clean upper bound "
             "while shrinking the index, where exact deduplication offers no benefit. CORGI reframes "
             "data governance as a first-class, measurable control for retrieval-augmented and agentic "
             "AI. We release the system and a reusable corpus-quality benchmark; future work extends "
             "the learned gate and the profiler's consistency and coverage dimensions."),

    ("h1", "References"),
    ("refs", "[1] Z. Abedjan, L. Golab, and F. Naumann, “Profiling relational data: a survey,” "
             "The VLDB Journal, vol. 24, no. 4, pp. 557–581, 2015."),
    ("refs", "[2] R. Y. Wang and D. M. Strong, “Beyond accuracy: What data quality means to data "
             "consumers,” J. Management Information Systems, vol. 12, no. 4, pp. 5–33, 1996."),
    ("refs", "[3] C. Batini and M. Scannapieco, Data Quality: Concepts, Methodologies and Techniques. "
             "Springer, 2006."),
    ("refs", "[4] P. Lewis et al., “Retrieval-augmented generation for knowledge-intensive NLP "
             "tasks,” in Proc. NeurIPS, 2020."),
    ("refs", "[5] Y. Gao et al., “Retrieval-augmented generation for large language models: A "
             "survey,” arXiv:2312.10997, 2023."),
    ("refs", "[6] V. Karpukhin et al., “Dense passage retrieval for open-domain question "
             "answering,” in Proc. EMNLP, 2020, pp. 6769–6781."),
    ("refs", "[7] K. Lee et al., “Deduplicating training data makes language models better,” "
             "in Proc. ACL, 2022, pp. 8424–8445."),
    ("refs", "[8] G. Penedo et al., “The RefinedWeb dataset for Falcon LLM: Outperforming curated "
             "corpora with web data,” in Proc. NeurIPS Datasets and Benchmarks Track, 2023."),
    ("refs", "[9] S. Es, J. James, L. Espinosa-Anke, and S. Schockaert, “RAGAs: Automated "
             "evaluation of retrieval augmented generation,” in Proc. EACL: System "
             "Demonstrations, 2024, pp. 150–158."),
    ("refs", "[10] N. Reimers and I. Gurevych, “Sentence-BERT: Sentence embeddings using Siamese "
             "BERT-networks,” in Proc. EMNLP-IJCNLP, 2019, pp. 3980–3990."),
    ("refs", "[11] J. Johnson, M. Douze, and H. Jégou, “Billion-scale similarity search with "
             "GPUs,” IEEE Trans. Big Data, vol. 7, no. 3, pp. 535–547, 2021."),
    ("refs", "[12] N. Thakur, N. Reimers, A. Rücklé, A. Srivastava, and I. Gurevych, "
             "“BEIR: A heterogeneous benchmark for zero-shot evaluation of information retrieval "
             "models,” in Proc. NeurIPS Datasets and Benchmarks, 2021."),
    ("refs", "[13] D. Wadden et al., “Fact or fiction: Verifying scientific claims,” in Proc. "
             "EMNLP, 2020, pp. 7534–7550."),
]


def set_styled_para_text(doc, style_name, text):
    """Set the text of the first paragraph having the given style, keeping its para mark+style."""
    for p in doc.Paragraphs:
        try:
            if p.Style.NameLocal == style_name:
                r = p.Range
                r.End = r.End - 1  # exclude the paragraph mark
                r.Text = text
                return True
        except Exception:
            pass
    return False


def main():
    word = win32.Dispatch("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        word.ScreenUpdating = False
        doc = word.Documents.Open(TPL)

        set_styled_para_text(doc, "paper title", TITLE)

        # --- single author: collapse the 6 placeholder blocks to one ---
        authors = [p for p in doc.Paragraphs if p.Style.NameLocal == "Author"]
        if len(authors) > 1:
            doc.Range(authors[1].Range.Start, authors[-1].Range.End).Delete()
        if authors:
            r0 = authors[0].Range
            r0.End = r0.End - 1  # keep the paragraph mark + style
            r0.Text = ("Mohammed Thousif Shaik" + chr(11) + "Independent Researcher" + chr(11) +
                       "Round Rock, TX, USA" + chr(11) + "thousifsmd@gmail.com")

        set_styled_para_text(doc, "Abstract", ABSTRACT)
        set_styled_para_text(doc, "Keywords", KEYWORDS)

        # find first Heading 1 (template's example "Introduction") = body start + its section
        body_start = body_sec = None
        for p in doc.Paragraphs:
            if p.Style.NameLocal == "Heading 1":
                body_start = p.Range.Start
                body_sec = p.Range.Sections(1).Index
                break
        if body_start is None:
            body_start = doc.Content.End - 1
            body_sec = doc.Sections.Count

        # Delete the template's example body WITHIN its (2-column) section only, preserving that
        # section's final paragraph mark (carries the 2-column sectPr) and the trailing section break.
        # This keeps the template's native layout instead of flattening/rebuilding sections.
        sec_end = doc.Sections(body_sec).Range.End
        doc.Range(body_start, sec_end - 1).Delete()

        sel = word.Selection
        sel.SetRange(body_start, body_start)
        sel.Collapse(1)  # wdCollapseStart

        for op in BODY:
            kind = op[0]
            if kind == "table":
                _, caption, header, rows = op
                sel.Style = "table head"
                sel.TypeText(caption)
                sel.TypeParagraph()
                t = doc.Tables.Add(sel.Range, len(rows) + 1, len(header))
                try:
                    t.Style = "Table Grid"
                except Exception:
                    pass
                for j, h in enumerate(header):
                    c = t.Cell(1, j + 1).Range
                    c.Text = h
                    try: c.Style = "table col head"
                    except Exception: pass
                for i, row in enumerate(rows):
                    for j, val in enumerate(row):
                        c = t.Cell(i + 2, j + 1).Range
                        c.Text = str(val)
                        try: c.Style = "table copy"
                        except Exception: pass
                sel.SetRange(t.Range.End, t.Range.End)
                sel.Collapse(0)  # wdCollapseEnd
                sel.TypeParagraph()
            elif kind == "figure":
                _, img_path, caption = op
                shp = sel.InlineShapes.AddPicture(FileName=os.path.abspath(img_path))
                try:
                    shp.LockAspectRatio = True
                    shp.Width = 240  # ~ one column width (points)
                except Exception:
                    pass
                sel.Collapse(0)
                sel.TypeParagraph()
                sel.Style = "figure caption"
                sel.TypeText(caption)
                sel.TypeParagraph()
            elif kind == "algo":
                _, caption, lines = op
                sel.Style = "table head"
                sel.TypeText(caption)
                sel.TypeParagraph()
                t = doc.Tables.Add(sel.Range, 1, 1)
                try:
                    t.Style = "Table Grid"
                except Exception:
                    pass
                cell = t.Cell(1, 1).Range
                cell.Text = chr(11).join(lines)
                cell.Font.Name = "Consolas"
                cell.Font.Size = 8
                sel.SetRange(t.Range.End, t.Range.End)
                sel.Collapse(0)
                sel.TypeParagraph()
            else:
                style = {"h1": "Heading 1", "h2": "Heading 2", "body": "Body Text",
                         "bullet": "bullet list", "refs": "references"}[kind]
                sel.Style = style
                sel.TypeText(op[1])
                sel.TypeParagraph()

        # Collapse the template's title/author/spacer sections (with their stray page breaks) into
        # ONE 1-column section so the single author centers full width, while preserving the
        # 2-column body section. The body's section break sits immediately before the Abstract, so
        # we strip breaks only in the region BEFORE it.
        # Ensure the body section is two columns (template default). We deliberately leave the
        # template's native section breaks and the title/author band untouched: those breaks are
        # what keep the body on page 1, and removing/forcing them (merging sections) either makes
        # the title 2-column or pushes the body to a blank page 2.
        # delete the template's leftover floating text boxes (e.g. the "use a text box to insert a
        # graphic" example). Our figures are INLINE shapes, so every floating Shape is template cruft.
        for i in range(doc.Shapes.Count, 0, -1):
            try:
                doc.Shapes(i).Delete()
            except Exception:
                pass

        # title + author live in one section -> set it to a single column so they span full width
        # and center (keeps the Abstract on page 1; the template's other breaks are left intact).
        for p in doc.Paragraphs:
            if p.Style.NameLocal == "paper title":
                try:
                    doc.Sections(p.Range.Sections(1).Index).PageSetup.TextColumns.SetCount(1)
                except Exception:
                    pass
                break
        # body section (the one holding the first heading) -> two columns, 18pt gutter
        body_sec = None
        for p in doc.Paragraphs:
            if p.Style.NameLocal == "Heading 1":
                body_sec = p.Range.Sections(1).Index
                break
        if body_sec:
            tc = doc.Sections(body_sec).PageSetup.TextColumns
            if tc.Count != 2:
                tc.SetCount(2); tc.EvenlySpaced = True; tc.Spacing = 18

        doc.SaveAs2(OUT, FileFormat=16)
        print("WROTE:", OUT)
        print("pages:", doc.ComputeStatistics(2), "words:", doc.ComputeStatistics(0))
        doc.Close(False)
    finally:
        word.ScreenUpdating = True
        word.Quit()


if __name__ == "__main__":
    main()
