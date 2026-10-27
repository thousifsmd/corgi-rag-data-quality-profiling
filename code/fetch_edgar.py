#!/usr/bin/env python3
"""
fetch_edgar.py — download 10-K filings for a set of (Texas energy) companies
from SEC EDGAR and write them as plain text, with a manifest for the profiler.

SEC rules this script follows:
  * A descriptive User-Agent that includes a contact email (required by SEC).
  * Rate limiting (<= 10 requests/sec; we sleep between requests).
See https://www.sec.gov/os/accessing-edgar-data

Output layout (all under --out):
    <ticker>_10-K_<filing_date>.txt      one plain-text document per filing
    manifest.csv                         doc_id,ticker,form,date,path

Usage:
    python fetch_edgar.py --email "you@example.com" \
        --tickers XOM COP OXY PSX VLO EOG \
        --per-company 3 --out ../data/edgar

Notes:
  * Ticker->CIK is resolved live from SEC's company_tickers.json (no hardcoded CIKs).
  * HTML filings are stripped to text (BeautifulSoup if available, else a regex fallback).
"""
import argparse
import csv
import os
import re
import sys
import time
import html as _html

import requests

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{doc}"

# A reasonable default basket of large Texas-headquartered / major energy issuers.
DEFAULT_TICKERS = ["XOM", "COP", "OXY", "PSX", "VLO", "EOG", "KMI", "HAL", "BKR"]

# Ticker -> CIK overrides for cases where SEC's ticker map points at the wrong entity
# (e.g. after a reorg the ticker resolves to a holding-company shell with no 10-Ks).
# XOM resolves to "ExxonMobil Holdings Corp" (CIK 2115436, no filings); the 10-Ks are
# under the operating company "Exxon Mobil Corporation" (CIK 34088).
TICKER_CIK_OVERRIDES = {"XOM": 34088}


# Inline-XBRL "context soup": runs of prefix:Name tokens, ISO dates, 10-digit CIKs,
# and *Member axis names. 3+ in a row is unambiguous XBRL metadata, not prose.
_XBRL_TOKEN = (
    r"(?:[a-z][a-z0-9-]{0,9}:[A-Za-z0-9]+"   # us-gaap:Foo, dei:Bar, cop:Baz, country:US
    r"|\d{10}"                                 # bare CIK
    r"|\d{4}-\d{2}-\d{2}"                      # ISO date
    r"|[A-Za-z0-9.]+Member"                    # ...Member axis (may include digits/dots)
    r"|\.\d{1,4})"                             # leftover coupon fragments (.8 .375)
)
_XBRL_SOUP = re.compile(r"(?:" + _XBRL_TOKEN + r"\s*){3,}")


def strip_xbrl_soup(text: str) -> str:
    """Collapse runs of inline-XBRL context tokens that survive HTML extraction."""
    return _XBRL_SOUP.sub(" ", text)


def strip_html(raw: str) -> str:
    """Best-effort HTML -> text. Removes scripts, hidden iXBRL blocks, and tag soup."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(raw, "lxml")
        for tag in soup(["script", "style"]):
            tag.decompose()
        # hidden iXBRL fact/context blocks (display:none / visibility:hidden)
        for tag in soup.find_all(style=re.compile(r"(display\s*:\s*none|visibility\s*:\s*hidden)", re.I)):
            tag.decompose()
        # inline-XBRL metadata containers (keep ix:nonfraction/ix:nonnumeric visible values)
        for tag in soup.find_all(re.compile(r"^ix:(header|hidden|references|resources)", re.I)):
            tag.decompose()
        text = soup.get_text(separator=" ")
    except Exception:
        text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        text = _html.unescape(text)
    text = strip_xbrl_soup(text)   # safety net for residual soup
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def get(session, url, sleep=0.2, retries=4):
    """GET with retries + linear backoff (SEC occasionally 429s or drops a connection)."""
    last = None
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=60)
            r.raise_for_status()
            time.sleep(sleep)  # be polite to SEC
            return r
        except Exception as e:
            last = e
            time.sleep(1.0 * (attempt + 1))
    raise last


def resolve_ciks(session, tickers):
    """Map uppercase ticker -> int CIK using SEC's official mapping file."""
    data = get(session, SEC_TICKERS_URL).json()
    by_ticker = {row["ticker"].upper(): int(row["cik_str"]) for row in data.values()}
    out = {}
    for t in tickers:
        t = t.upper()
        if t in TICKER_CIK_OVERRIDES:
            out[t] = TICKER_CIK_OVERRIDES[t]
        elif t in by_ticker:
            out[t] = by_ticker[t]
        else:
            print(f"  [warn] ticker not found in SEC mapping: {t}", file=sys.stderr)
    return out


def recent_10k(session, cik, limit):
    """Return list of (filing_date, accession_nodash, primary_doc) for 10-K filings."""
    j = get(session, SUBMISSIONS_URL.format(cik=cik)).json()
    recent = j.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accs = recent.get("accessionNumber", [])
    docs = recent.get("primaryDocument", [])
    rows = []
    for form, d, acc, doc in zip(forms, dates, accs, docs):
        if form == "10-K" and doc:
            rows.append((d, acc.replace("-", ""), doc))
        if len(rows) >= limit:
            break
    return rows


def main():
    ap = argparse.ArgumentParser(description="Download 10-K filings from SEC EDGAR.")
    ap.add_argument("--email", required=True,
                    help="Contact email for the SEC User-Agent (required by SEC).")
    ap.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS)
    ap.add_argument("--per-company", type=int, default=3,
                    help="How many most-recent 10-Ks per company.")
    ap.add_argument("--out", default="../data/edgar")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    session = requests.Session()
    session.headers.update({
        "User-Agent": f"CORGI-research/0.1 ({args.email})",
        "Accept-Encoding": "gzip, deflate",
    })

    ciks = resolve_ciks(session, args.tickers)
    manifest_path = os.path.join(args.out, "manifest.csv")
    # Incremental: load already-downloaded doc_ids so re-runs append instead of clobbering.
    existing = set()
    if os.path.exists(manifest_path):
        with open(manifest_path, newline="", encoding="utf-8") as mf:
            for row in csv.DictReader(mf):
                existing.add(row["doc_id"])
    need_header = not existing
    n = 0
    with open(manifest_path, "a" if existing else "w", newline="", encoding="utf-8") as mf:
        w = csv.writer(mf)
        if need_header:
            w.writerow(["doc_id", "ticker", "form", "date", "path"])
        for ticker, cik in ciks.items():
            try:
                filings = recent_10k(session, cik, args.per_company)
            except Exception as e:
                print(f"  [warn] {ticker}: submissions fetch failed: {e}", file=sys.stderr)
                continue
            for (fdate, acc_nodash, doc) in filings:
                doc_id = f"{ticker}_10-K_{fdate}"
                if doc_id in existing:
                    print(f"  skip  {doc_id} (already have it)")
                    continue
                url = ARCHIVE_DOC_URL.format(cik=cik, acc_nodash=acc_nodash, doc=doc)
                try:
                    raw = get(session, url).text
                except Exception as e:
                    print(f"  [warn] {ticker} {fdate}: doc fetch failed: {e}", file=sys.stderr)
                    continue
                text = strip_html(raw)
                path = os.path.join(args.out, f"{doc_id}.txt")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text)
                w.writerow([doc_id, ticker, "10-K", fdate, path])
                existing.add(doc_id)
                n += 1
                print(f"  saved {doc_id}  ({len(text):,} chars)")

    print(f"\nDone. {n} filings -> {args.out}\nManifest: {manifest_path}")


if __name__ == "__main__":
    main()
