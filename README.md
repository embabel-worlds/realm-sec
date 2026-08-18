# realm-sec

US SEC filings as a graph-joinable source: resolve a registrant, index its EDGAR filings, and
ingest the documents so a 10-K's climate and risk disclosure becomes quotable text rather than a
link.

## Identity is by ticker or CIK. Never by name.

EDGAR is free, keyless and authoritative, and it indexes by **CIK**. It has no domain index and no
website field, so joining it to a domain-keyed corpus needs an external identity bridge — and this
realm refuses to invent one.

Measured on a 272-domain corpus: **18 domains had a name appearing in EDGAR at all (7%)**, and five
of those eighteen were different companies.

| domain | EDGAR "match" |
|---|---|
| `imperial-tobacco.co.uk` | Canadian Imperial Bank of Commerce |
| `mitsui.com` | Sumitomo Mitsui Financial Group |
| `axa.com` | Axalta Coating Systems |

A filing carries audited figures, so a wrong attribution looks maximally authoritative. That is why
the tool takes a ticker or a CIK and nothing else.

**And a bridge is only as good as its own guard.** Diffbot returns ticker `FIRE` for `cisco.com`,
because it resolves that domain to Sourcefire — a company Cisco acquired. Pass `--domain` only when
you have checked the resolution.

## Use

```bash
python3 scripts/sec.py resolve CSCO --domain cisco.com
python3 scripts/sec.py filings 858877 --forms 10-K 20-F --ingest --domain cisco.com
```

Filings ingested with `--domain` are tagged `domain:<d>`, which is how they join an ESG corpus keyed
on the same domain — without either realm depending on the other's labels.

## Scope

US registrants only. On a European corpus this realm is nearly inert: of nine assessed companies,
one was an SEC registrant. The European equivalent of a filing is the CSRD sustainability
statement, which is a PDF on the company's own domain and needs no bridge at all.
