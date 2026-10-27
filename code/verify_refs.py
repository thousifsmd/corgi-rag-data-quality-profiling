#!/usr/bin/env python3
"""Verify references against Crossref (sequential, polite). Prints matched metadata."""
import json, time, urllib.parse, urllib.request

REFS = {
    1: "Profiling relational data a survey Abedjan Golab Naumann VLDB Journal",
    2: "Beyond accuracy what data quality means to data consumers Wang Strong",
    3: "Data Quality Concepts Methodologies and Techniques Batini Scannapieco",
    4: "Retrieval-augmented generation for knowledge-intensive NLP tasks Lewis",
    6: "Dense passage retrieval for open-domain question answering Karpukhin EMNLP",
    7: "Deduplicating training data makes language models better Lee ACL",
    8: "The RefinedWeb dataset for Falcon LLM Penedo",
    9: "RAGAS Automated Evaluation of Retrieval Augmented Generation Es",
    10: "Sentence-BERT Sentence Embeddings using Siamese BERT-Networks Reimers Gurevych",
    11: "Billion-scale similarity search with GPUs Johnson Douze Jegou IEEE",
    12: "BEIR Heterogeneous Benchmark Zero-shot Evaluation Information Retrieval Thakur",
    13: "Fact or Fiction Verifying Scientific Claims Wadden EMNLP",
}

for n, q in REFS.items():
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(
        {"query.bibliographic": q, "rows": 1, "mailto": "your-email@example.com"})
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "corgi-refcheck/0.1 (mailto:your-email@example.com)"})
        d = json.load(urllib.request.urlopen(req, timeout=30))
        items = d.get("message", {}).get("items", [])
        if items:
            p = items[0]
            title = (p.get("title") or ["?"])[0]
            cont = (p.get("container-title") or [""])
            cont = cont[0] if cont else ""
            vol = p.get("volume", ""); page = p.get("page", "")
            yr = (p.get("issued", {}).get("date-parts", [[None]])[0][0])
            au = ", ".join((a.get("family", "") ) for a in p.get("author", [])[:3])
            print(f"[{n}] {title} | {cont} v{vol} p{page} | {yr} | {au} | doi:{p.get('DOI','')}")
        else:
            print(f"[{n}] NO MATCH: {q}")
    except Exception as e:
        print(f"[{n}] ERROR {e}")
    time.sleep(1.5)
