#!/usr/bin/env python3
"""Resolve SEC registrants and ingest their filings.

    python3 scripts/sec.py resolve CSCO --domain cisco.com
    python3 scripts/sec.py filings 858877 --forms 10-K 20-F --ingest

IDENTITY IS BY TICKER OR CIK, NEVER BY NAME. EDGAR indexes by name and CIK, has no domain index
and no website field, so a domain-keyed corpus can only reach it through an external bridge. Name
matching against 8,000 registrants was measured on a real corpus and produced, among 18 apparent
matches, five different companies: imperial-tobacco.co.uk to Canadian Imperial Bank of Commerce,
mitsui.com to Sumitomo Mitsui Financial, axa.com to Axalta Coating Systems. A filing carries
audited figures, so a wrong attribution looks maximally authoritative. This tool will not do it.

The ticker itself must come from a VERIFIED identity. Diffbot returns ticker FIRE for cisco.com
because it resolves that domain to Sourcefire — a company Cisco acquired — so a bridge is only as
good as its own guard. Pass --domain only when you have checked it.

EDGAR requires a descriptive User-Agent and rate-limits to ~10 req/s; both are honoured here.
"""
import argparse, base64, json, os, re, sys, time, urllib.request

BASE = os.environ.get("EMBABEL_URL", "http://localhost:8042").rstrip("/")
H = {"Content-Type": "application/json",
     "Authorization": "Basic " + base64.b64encode(
         f"{os.environ.get('EMBABEL_USER','')}:{os.environ.get('EMBABEL_PASS','')}".encode()).decode()}
UA = os.environ.get("SEC_USER_AGENT", "embabel-realm-sec research contact@embabel.com")


def post(path, body, timeout=300):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers=H, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def edgar(url: str, timeout: int = 60):
    """EDGAR asks for a descriptive User-Agent and throttles; a default urllib agent gets 403."""
    time.sleep(0.15)                                    # under the ~10 req/s ceiling
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip, deflate"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            import gzip; raw = gzip.decompress(raw)
        return json.loads(raw)


def cik_for_ticker(ticker: str):
    for v in edgar("https://www.sec.gov/files/company_tickers.json").values():
        if v["ticker"].upper() == ticker.upper():
            return str(v["cik_str"]).zfill(10), v["title"]
    return None, None


def cmd_lookup(args) -> int:
    """Find candidate registrants by ticker or name, and PRESENT them rather than choosing.

    Refusing to fuzzy-match a domain does not mean refusing to look a company up. The defect was
    silent SELECTION — a pipeline that quietly attached Canadian Imperial Bank of Commerce to
    imperial-tobacco.co.uk. A lookup that shows every candidate and makes a person choose has the
    opposite property: ambiguity becomes visible instead of resolved by luck.

    An exact ticker is unambiguous and is reported as such. A name search is a search, and
    "IBM" matching both the ticker and the registrant name is exactly the easy case.
    """
    q = args.query.strip()
    rows = list(edgar("https://www.sec.gov/files/company_tickers.json").values())
    exact_ticker = [v for v in rows if v["ticker"].upper() == q.upper()]
    by_name = [v for v in rows if q.lower() in v["title"].lower()][:12]
    if exact_ticker:
        v = exact_ticker[0]
        print(f"  EXACT TICKER  {v['ticker']:8}{v['title'][:52]:54}CIK {str(v['cik_str']).zfill(10)}")
    others = [v for v in by_name if not exact_ticker or v["cik_str"] != exact_ticker[0]["cik_str"]]
    if others:
        print(f"  {len(others)} name match(es) — a NAME is not an identity; pick one deliberately:")
        for v in others:
            print(f"    {v['ticker']:8}{v['title'][:52]:54}CIK {str(v['cik_str']).zfill(10)}")
    if not exact_ticker and not others:
        print(f"  no registrant matches '{q}' — it may not be SEC-registered at all")
        return 1
    if not exact_ticker and len(others) > 1:
        print("\n  AMBIGUOUS. Resolve with the ticker of the one you mean, not this query.")
    return 0


def cmd_resolve(args) -> int:
    cik, name = cik_for_ticker(args.ticker)
    if not cik:
        print(f"ticker {args.ticker} is not an SEC registrant", file=sys.stderr)
        return 1
    sub = edgar(f"https://data.sec.gov/submissions/CIK{cik}.json")
    data = {"cik": cik, "ticker": args.ticker.upper(), "name": sub.get("name") or name,
            "sicDescription": sub.get("sicDescription"),
            "exchange": (sub.get("exchanges") or [None])[0],
            "resolvedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    if args.domain:
        data["domain"] = args.domain
    print(f"  CIK {cik}  {data['name']}  [{data.get('sicDescription')}]"
          + (f"  domain={args.domain} (YOUR claim, not the SEC's)" if args.domain else ""))
    post("/api/v1/tools/create_entry", {"type": "SecRegistrant", "data": {k: v for k, v in data.items() if v}})
    return 0


def cmd_filings(args) -> int:
    cik = str(args.cik).zfill(10)
    sub = edgar(f"https://data.sec.gov/submissions/CIK{cik}.json")
    r = sub["filings"]["recent"]
    rows = [{"form": r["form"][i], "filingDate": r["filingDate"][i],
             "accessionNumber": r["accessionNumber"][i], "primaryDocument": r["primaryDocument"][i]}
            for i in range(len(r["form"]))]
    wanted = [x for x in rows if x["form"] in args.forms][: args.limit]
    print(f"  {sub.get('name')} — {len(wanted)} of {len(rows)} indexed filings match {args.forms}")
    for f in wanted:
        acc = f["accessionNumber"].replace("-", "")
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{f['primaryDocument']}"
        print(f"    {f['form']:8}{f['filingDate']}  {url[:88]}")
        post("/api/v1/tools/create_entry", {"type": "SecFiling", "data": {
            "accessionNumber": f["accessionNumber"], "cik": cik, "form": f["form"],
            "filingDate": f["filingDate"], "primaryDocumentUrl": url, "ingested": bool(args.ingest)}})
        if not args.ingest:
            continue
        try:
            print(f"       -> {ingest_filing(url, f, args.domain)}")
        except Exception as e:
            print(f"       -> ingest failed: {str(e)[:70]}", file=sys.stderr)
    return 0


TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"\s+")


def ingest_filing(url: str, f: dict, domain: str | None) -> str:
    """Fetch the filing OURSELVES and post the text.

    The server cannot fetch this. SEC requires a User-Agent that identifies the caller AND carries
    a contact address, and rejects anything else with 403 — measured: "Mozilla/5.0" and a bare
    "embabel research" both 403, while "Embabel Research contact@embabel.com" returns 3.5 MB. A 403
    reaches the caller as HTTP 500 from /api/v1/documents/url, which is why filings looked like an
    ingestion bug rather than a policy one.

    The document name carries the DOMAIN because /documents/text takes no fromOrgDomain, and the
    ESG views key on the document uri — so the name is what lets a filing join a company's web
    pages and reports.
    """
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as r:
        raw = r.read().decode("utf-8", errors="replace")
    text = WS.sub(" ", TAG.sub(" ", raw)).strip()
    stem = (domain + "-") if domain else ""
    name = f"{stem}{f['form']}-{f['filingDate']}.txt".replace("/", "-")
    tags = ["sec", f"form:{f['form']}"] + (["esg", f"domain:{domain}"] if domain else [])
    res = post("/api/v1/documents/text", {"name": name, "content": text, "tags": tags}, timeout=600)
    return f"{res.get('status')} — {name}, {len(text):,} chars"


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    l = sub.add_parser("lookup"); l.add_argument("query"); l.set_defaults(fn=cmd_lookup)
    r = sub.add_parser("resolve"); r.add_argument("ticker"); r.add_argument("--domain")
    r.set_defaults(fn=cmd_resolve)
    f = sub.add_parser("filings"); f.add_argument("cik")
    f.add_argument("--forms", nargs="+", default=["10-K", "20-F"])
    f.add_argument("--limit", type=int, default=3)
    f.add_argument("--ingest", action="store_true"); f.add_argument("--domain")
    f.set_defaults(fn=cmd_filings)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
