# provision-spine: frozen to fluid

One engine from a frozen provision hash to a sellable evidence door.

```
CELLAR (EU Publications Office, official machine API)
  -> v1  frozen OJ text, byte-compatible with /interop/frozen-provision-hashes.json (417, root 37e2e10d...)
  -> v2  OJ original, exact element boundaries (no truncation, no footnote spill)
  -> v3  latest consolidated text = the law as it applies today (amended / inserted / deleted)
  -> determinism gate (fetch twice; unstable source = UNKNOWN, never drift)
  -> + already-frozen slices (Europe-International: CoE, GB, INTL, OECD, UN ...)
  -> DRAFT obligations (deterministic cut on current text) joined with the agent register
       -> stale-draft flags where the law moved under a draft
       -> two-method OBSERVED shortlist = next predicates
  -> ladder per provision -> door data /provisions/<id>.json + index.json -> report.md
  -> daily GitHub Action: opens a PR when anything moved. Never merges.
```

Run locally:

```
PYTHONPATH=. pytest -q tests
PYTHONPATH=. python -m spine.pipeline --out data/spine \
  --extra-provisions data/inputs/provisions_europe_intl.jsonl \
  --agent-register data/inputs/obligation_register_eu_v0_draft.jsonl
```

Exit code 2 means an authority was unreachable or its bytes were unstable between two
fetches. CI then goes red and opens no PR: a failed fetch is never reported as "no drift".

## How the 417 frozen hashes were recovered

The frozen corpus (2026-08-12) was produced by parser 1.0 (`scripts/eurlex_sync.py` in
eu-ai-act-compliance-mcp) and normaliser 1.0.0 (`corpus_anchor.py`):
`sha256("1.0.0\0" + normalise(text))`. Recipes that reproduce it, recorded per provision as
`v1_recipe`:

| recipe | provisions |
|---|---|
| parser1.0/structural (AI Act articles and annexes) | 134 |
| parser1.0/structural-heading-stripped (GDPR, CRA, DORA, NIS2, CSRD) | 271 |
| parser1.0/title-pattern (CSRD, including nested amending articles 25, 29, 40) | 12 |

v1 caveats, kept and never overwritten: 11 provisions are truncated (AI Act 3 and 5, CRA 3
and 13, NIS2 6 and 32, DORA 3, CSRD 1 and 3, plus nested CSRD 25 and 29). v1 bodies also run
on into the next chapter heading. v2 and v3 fix both.

## Why this replaces the EU subsets of corpus-watch

Measured 20 Nov 2026 from `corpus_state.json` and `drift_events.jsonl` in this repo:

- `EU-AI-ACT` (113 keys) and `EU-CRA` (71 keys) each hold **one distinct hash**: the whole
  document was hashed and copied to every article, so article-level drift was never measured.
- All **319 of 319** drift events are UK (`UK-GDPR`, `DPA-2018`, `NIS2-UK`) and flip back and
  forth (e.g. UK GDPR Art. 5 32 times in 47 days, hashes A->B->A). That is page-metadata
  churn, not law. The determinism gate here would have marked those sources UNSTABLE.
- The scheduled watcher last ran 14 Sep 2026.

## What it found on its first pass (20 Nov 2026)

- All 417 frozen provisions reproduce from live CELLAR bytes; root matches.
- AI Act consolidated `02024R1689-20260727` (Reg (EU) 2026/1744): 39 provisions amended,
  7 inserted (Art. 4a, 60a, 75a, 75b, 75c, 75d, Annex XIV), 7 noise-only (numeric
  footnote/OJ-reference changes only), 80 unchanged. Any changed word counts as amended.
  Art. 50(2) marking duty is unchanged; Art. 50(7) moved from AI Office to Commission.
- DORA consolidated version has no English XHTML in CELLAR: v3 = UNKNOWN (fail-closed).

Nothing in this package is legal advice. Obligation rows are DRAFT until a reviewer sets
`counsel_confirmed`.
