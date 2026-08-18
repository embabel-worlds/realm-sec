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
python3 scripts/sec.py lookup IBM                 # find a registrant
python3 scripts/sec.py resolve IBM --domain ibm.com
python3 scripts/sec.py filings 51143 --forms 10-K --ingest --domain ibm.com
```

`lookup` searches by ticker or name and **presents candidates** — refusing to fuzzy-match a domain
was never a reason to refuse to look a company up. The defect was silent SELECTION, so ambiguity is
made visible instead:

```
$ sec.py lookup IBM
  EXACT TICKER  IBM     INTERNATIONAL BUSINESS MACHINES CORP     CIK 0000051143

$ sec.py lookup imperial
  5 name match(es) — a NAME is not an identity; pick one deliberately:
    CM      CANADIAN IMPERIAL BANK OF COMMERCE /CAN/             CIK 0001045520
    IMO     IMPERIAL OIL LTD                                     CIK 0000049938
    ...
  AMBIGUOUS. Resolve with the ticker of the one you mean, not this query.
```

That second case is the one that matters: it is the query that silently attached a Canadian bank to
a tobacco company in the corpus this realm was built against.

## Fetching: SEC blocks on User-Agent

SEC requires an agent carrying a contact address and answers anything else with **403** — measured,
`Mozilla/5.0` and a bare `embabel research` both fail while `Embabel Research contact@embabel.com`
returns the document. A 403 reaches a caller as HTTP 500 from `/api/v1/documents/url`, which makes a
policy problem look like an ingestion bug. So this realm fetches filings itself with a compliant
agent and posts the text. Override with `SEC_USER_AGENT`.

Filings ingested with `--domain` are tagged `domain:<d>`, which is how they join an ESG corpus keyed
on the same domain — without either realm depending on the other's labels.

## Scope

US registrants only. On a European corpus this realm is nearly inert: of nine assessed companies,
one was an SEC registrant. The European equivalent of a filing is the CSRD sustainability
statement, which is a PDF on the company's own domain and needs no bridge at all.
