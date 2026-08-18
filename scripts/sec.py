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
import argparse, base64, json, os, sys, time, urllib.request

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
            # Ingested under the registrant's domain when one was asserted, so the filing lands in
            # the same corpus as that company's web pages and reports and joins on the same key.
            body = {"url": url, "tags": ["sec", f"form:{f['form']}"]}
            if args.domain:
                body["fromOrgDomain"] = args.domain
                body["tags"] += ["esg", f"domain:{args.domain}"]
            print(f"       -> {post('/api/v1/documents/url', body).get('status')}")
        except Exception as e:
            print(f"       -> ingest failed: {str(e)[:70]}", file=sys.stderr)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
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
