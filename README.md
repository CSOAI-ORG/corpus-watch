# corpus-watch: provision-spine engine

Daily, fail-closed re-measurement of every frozen regulatory provision in the Council of AI
corpus against its official source, one provision at a time.

> Status: this branch replaces the old whole-document watcher (`watcher/run_watch.py`,
> `sov_corpus_watcher.py`, `.github/workflows/corpus_watcher.yml`). **`corpus_state.json` and
> `drift_events.jsonl` are SUPERSEDED** and kept unchanged, with `reports/`, as history only.
> Measured on 20 Nov 2026 they carried two defects. First, `EU-AI-ACT` (113 keys) and `EU-CRA`
> (71 keys) each held one distinct hash: the whole document was hashed and copied to every
> article. Second, all 319 of 319 drift events were UK (UK-GDPR, DPA-2018, NIS2-UK) and flipped
> A->B->A, which was page-metadata churn, not law. The watcher last ran on 14 Sep 2026.
> On its first pass (21 Nov 2026) this engine found all 1095 of 1095 legislation.gov.uk provisions
> UNCHANGED from the same `data.xml` routes, and 1061 of them reproduce their frozen hash byte for byte.

```
data/inputs/registry_<wave>.jsonl + provisions_<wave>.jsonl   (schema v2, normaliser 1.0.0; any number of waves)
  -> route each provision to an AUTHORITY ADAPTER by its recorded source (host / kind)
  -> per source document: fetch #1, extract, re-split with the recorded recipe, re-hash
                          fetch #2, extract, re-split, re-hash        = DETERMINISM GATE
  -> per provision: REPRODUCED/UNCHANGED | NOISE | AMENDED | UNKNOWN  (vs the frozen hash)
     + INSERTED from a validated structural lister (current-text routes only)
     + EU: current-law class vs the latest CELLAR consolidation (spine.fluid)
  -> EU-six: the 417 frozen v1 hashes re-derived (root 37e2e10d...), v2 OJ exact, v3 consolidated
  -> DRAFT obligation cut for every provision (deterministic; EN, ZH, JA, KO, ES)
  -> agent-register join -> stale-draft list (rows whose provision was amended)
  -> ladder per provision -> door data data/spine/provisions/<id>.json + index.json -> report.md
```

## Daily auto-batch (`.github/workflows/provision-spine.yml`)

- `plan` runs the offline tests and lists the adapters that `data/inputs` needs. A new wave needs no code change.
- `shard` is a matrix with one job per adapter. **An unreachable or unstable authority exits 2: that
  job goes red and publishes nothing**, so none of its provisions can be reported as unchanged.
- `aggregate` merges the green shards and carries a red shard's previous records forward,
  flagged `carried_forward`. It re-runs the EU-six checks (CELLAR unreachable = exit 2, no PR) and
  **opens a PR on branch `spine/daily` when `data/spine` moved. It never merges.** A
  human reviewer merges. If any shard failed, the run ends red.
- Per-provision rows carry no timestamps. The run time is only in `report.json` / `state.json` /
  `index.json`, so the diff test cannot be masked by timestamp lines.

## Adding a wave

Drop `data/inputs/registry_<wave>.jsonl` and `data/inputs/provisions_<wave>.jsonl` (schema v2) in place. The loader:

- rejects rows whose text does not re-hash, or whose `normaliser_version` is not 1.0.0;
- reports cross-wave conflicts (same `provision_id`, different hash) and drops both rows,
  never last-writer-wins;
- routes each row by its `source.url` host, so an unknown host falls through to `pinned_document`.

A new official host with its own rendering conventions needs an adapter only if its text
does not re-split from the generic extraction.

Registry precedence: the loader keeps the first FULL_TEXT row for an instrument, and otherwise the last row
in filename order. When a later wave carries a full updated row for an instrument, remove the earlier row
from its older registry file so that the update applies.

### Waves added after the first pass

- `apac_standards` (added 22 Nov 2026): 97 registry rows (20 jurisdiction codes) and 1,195 provision rows. Of
  these, 642 carry text, 400 are hash-only (licence withheld; `recipe_hashonly` kept), and 153 are IDS_ONLY. 26
  registry rows supersede earlier rows (12 in `registry_asia_pacific.jsonl`, 14 in `registry_europe_intl.jsonl`),
  which were removed there. 10 provision rows repeat earlier ids with the same hash and dedupe. The offline plan
  routes all 1,042 FULL_TEXT rows to `pinned_document` (48 documents) and the IDS_ONLY rows to `identifier_only`;
  no new adapter is needed. **This wave has not been measured yet.** The engine pass needs the authorities'
  routes, so the next daily run measures it. The first-pass figures below cover the 7 earlier waves only.

## Authority adapters (first pass, 21 Nov 2026, from this sandbox)

| adapter | status 21 Nov 2026 | documents | provisions | route for current text |
|---|---|---|---|---|
| `au_legislation_gov_au` | REACHABLE | 2 | 374 | pinned (compilation start date in URL) |
| `ca_justice_laws` | REACHABLE | 2 | 81 | inherent |
| `cl_bcn_leychile` | UNREACHABLE | 1 | 102 | inherent |
| `cn_flk_npc` | REACHABLE | 4 | 274 | pinned (bbbs = one published version of the law) |
| `cn_gov_cn` | REACHABLE | 4 | 98 | pinned (policy-library page) |
| `es_boe_api` | REACHABLE | 2 | 102 | inherent |
| `eu_cellar` | REACHABLE | 33 | 1694 | pinned-OJ (current law via spine.fluid consolidated diff) |
| `gb_ico_guidance` | REACHABLE | 14 | 14 | inherent |
| `identifier_only` | NOT_FETCHED | 9 | 19 | inherent |
| `it_normattiva_akn` | REACHABLE | 3 | 104 | pinned (dataVigenza in URL) |
| `jp_egov` | REACHABLE | 2 | 215 | inherent |
| `kr_law_go_kr` | REACHABLE | 3 | 212 | pinned (efYd effective-date version in URL) |
| `legislation_gov_uk` | REACHABLE | 6 | 1095 | inherent |
| `pinned_document` | REACHABLE | 54 | 1480 | pinned (recorded URL) |
| `tw_law_moj` | REACHABLE | 2 | 86 | inherent |
| `us_ca_leginfo_bulk` | REACHABLE | 63 | 366 | pinned (session archive member = one bill version) |
| `us_ecfr` | REACHABLE | 21 | 143 | inherent |
| `us_federal_register` | REACHABLE | 14 | 115 | pinned (a published FR document does not change) |
| `us_govinfo` | REACHABLE | 8 | 86 | pinned (USCODE edition in URL) |
| `us_state_pinned` | REACHABLE | 27 | 266 | pinned (enrolled bill / approved regulation text) |
| `us_state_utah` | REACHABLE | 27 | 117 | resolved: page shell's versionDefault = 'Current Version' |
| `uy_impo` | REACHABLE | 5 | 112 | inherent |

`cl_bcn_leychile`: www.leychile.cl answers "Not Allowed" (HTTP 401) to automated clients and
bcn.cl/leychile is a JavaScript shell. The block is not bypassed. Its 102 provisions stay
UNKNOWN and that shard stays red until the owner supplies the official file (pinned-document
route with source URL and file sha256). The eCFR and Federal Register HTML pages redirect automated
clients to a challenge page. The adapters use the official machine routes on the same hosts instead
(eCFR renderer API, FR `full_text` HTML).

## Change classes (vs the frozen hash)

| class | meaning |
|---|---|
| UNCHANGED | the frozen text was found contiguously in today's official text. `reproduced=true` when the normalised span hashes to the frozen hash exactly. Otherwise only whitespace placement differs (`ws-equal`), or words are equal and only punctuation differs (`*/words-equal`), or the document bytes are identical to the frozen fetch (`doc-bytes-identical`) |
| NOISE | anchors found, every differing token is numeric (footnote or page renumbering) |
| AMENDED | anchors found, at least one word changed |
| INSERTED | a provision present today that the frozen slice did not have (EU consolidations; structural listers on current-text routes only) |
| UNKNOWN | unreachable, unstable between the two fetches, anchor missing, text withheld and changed, or IDS_ONLY. **Never folded into UNCHANGED** |

`current_law_class` is separate. For EU instruments it is the diff of the OJ original against
the latest CELLAR consolidation. On routes that serve the current text (legislation.gov.uk,
e-Gov, law.moj.gov.tw, Justice Laws, eCFR, Utah current version) it equals the class vs frozen.
On pinned routes (an enrolled bill, an effective-date version, a published PDF) it is
`PINNED_NOT_CHECKED`.

## What is committed, and the licence basis per instrument

Code is MIT (`LICENSE`). Law text is committed **only** where the instrument's `text_licence`
permits republication. The basis is recorded per instrument in `data/inputs/licence_basis.jsonl`:
239 of 272 FULL_TEXT instruments carry text, under the following bases:

- US government edicts doctrine (Georgia v. Public.Resource.Org, 2020): 111 instruments
- US federal government work, 17 U.S.C. 105: 50 instruments
- EU reuse Decision 2011/833/EU: 32 instruments
- Open Government Licence v3.0: 11 instruments
- PRC Copyright Law art. 5 (laws and official documents not protected): 8 instruments
- CC-BY-4.0 (attribution in README): 3 instruments
- Japan Public Data Terms of Use v1.0 (CC BY 4.0-compatible; attribution in README): 3 instruments
- Korea Copyright Act art. 7 (statutes not protected): 3 instruments
- Germany UrhG § 5 (official works not protected): 2 instruments
- Spain LPI art. 13 (official acts not protected) + BOE reuse terms (attribution): 2 instruments
- CC-BY-SA-4.0 (attribution + share-alike, see README): 2 instruments
- Japan Copyright Act art. 13 (statutes not protected): 2 instruments
- Taiwan Copyright Act art. 9 (laws not protected): 2 instruments
- Brazil Lei 9.610/1998 art. 8 IV (official texts not protected): 1 instrument
- Canada Reproduction of Federal Law Order SI/97-5 (accuracy + non-endorsement conditions): 1 instrument
- Switzerland URG Art. 5 (enactments not protected): 1 instrument
- Denmark Ophavsretsloven § 9 (statutes not protected): 1 instrument
- EDPB reuse notice (source acknowledgement, no distortion): 1 instrument
- Finland Tekijänoikeuslaki 9 § (statutes not protected): 1 instrument
- Hungary Szjt. 1. § (4) (legislation not protected): 1 instrument
- Apache-2.0 (copyright notice + licence reference in README): 1 instrument

Withheld (33 FULL_TEXT instruments, 1356 provision rows): AR-Ley25326-datos-2000, CL-Ley21719-datos-2024, CN-anthropomorphic-ai-interaction-measures-2026, CoE-cets225-ai-convention-2024, HK-pdpo-cap486, HU-ai-act-implementation-act-2025, IE-ai-designation-regulations-2025, IE-regulation-of-ai-act-2026, INTL-au-continental-ai-strategy-2024, IT-dlgs-160-2026, IT-dlgs-179-2026, IT-legge-132-2025, LV-ai-centre-law-2025, MT-ai-regulations-2025, MU-dpa-2017, NG-ndpc-gaid-2025, OECD-ai-recommendation-2019, PE-DS115-2025-PCM-AIreg-2025, PY-Ley7593-datos-2025, RW-dp-law-058-2021, SA-pdpl-2021, UN-ares-78-265-2024, UN-ares-78-311-2024, UN-ares-79-239-2024, UN-ares-79-325-2025, UN-ares-80-118-2025, UN-ares-80-58-2025, UN-global-digital-compact-2024, US-CA-CCR11-CCPA-RA-ADMT-2025, UY-Dec276-2025-sandboxIA-2025, UY-Dec414-2009-datos-2009, UY-Ley18331-datos-2008, UY-Ley20212-art74-75-IA-2023.
For each of these the registry `text_licence` gives no verified republication basis: it says unknown,
"not verified", "not re-verified", "not stated" or "terms not re-read", or names no basis on the permitted list.
The APAC-and-standards wave adds two such cases that need an owner decision rather than a code change:
UN General Assembly texts (public domain under ST/AI/189/Add.9/Rev.2, which is not on the permitted list;
7 instruments, 214 rows) and the OECD AI Recommendation (OECD terms allow unaltered reproduction but not sale). Their rows carry
hashes, identifiers and a `recipe_hashonly` instead: a Rabin-Karp hash of the start anchor, the
projection length and the projection sha256. That is enough to locate and verify the provision
in today's official text, not enough to reconstruct it. A changed withheld provision is reported
UNKNOWN (`changed_hash_only`), because without the text it cannot be diffed.

Attribution: Australian text is © Commonwealth of Australia (Federal Register of Legislation), CC BY 4.0.
The C2PA Specification is CC BY 4.0, © C2PA. UK text contains public sector information licensed
under the Open Government Licence v3.0. Canadian federal enactments are reproduced under the
Reproduction of Federal Law Order (SI/97-5); this copy is not an official version and is not
endorsed by the Government of Canada. EU text is © European Union, reused under Decision
2011/833/EU. Spanish text: source Agencia Estatal Boletín Oficial del Estado (BOE), reused under its open-data
terms. EDPB text: source European Data Protection Board, reproduced without distortion.
NIST publications (AI 100, AI 200, AI 700, AI 800, SP 800-218A) are works of the US Government
(17 U.S.C. 105); source: National Institute of Standards and Technology, nvlpubs.nist.gov. MITRE ATLAS text:
Copyright 2021-2026 The MITRE Corporation, from the atlas-data repository, licensed under the Apache License,
Version 2.0 (https://www.apache.org/licenses/LICENSE-2.0). OWASP Top 10 for LLM Applications (2025, 2026):
OWASP Foundation, GenAI Security Project, CC BY-SA 4.0. Those rows stay under CC BY-SA 4.0 (share-alike) and
not under this repository's MIT code licence. G7 Hiroshima AI Process texts: source Ministry of Internal Affairs
and Communications of Japan (soumu.go.jp), Public Data Terms of Use v1.0 (CC BY 4.0-compatible).
`data/inputs/agent_register_index.jsonl` holds only identifiers and evidence-kind
labels of the agent-drafted EU obligation register (no drafted prose); the register itself is
not committed pending owner review.

## First pass (21 Nov 2026)

- Provisions in the engine: **7176**. That is 7,155 unique input rows across 7 waves (americas 746, asia_pacific 1,259, eu_six 414, europe_intl 2,407, europe_national 696, latam_africa_me 552, us 1,378 rows before cross-wave dedupe), plus
  18 insertions found in EU consolidations, plus 3 legacy
  CSRD nested-article rows.
- Exact frozen-hash reproduction: **4847**. AMENDED vs frozen: 1 (provisional, see below); NOISE: 1. UNCHANGED vs frozen: 7032; UNKNOWN: 121 (102 Chile blocked, 19 IDS_ONLY).
- Frozen v1 417 still reproduce, root matches: **True**.
- EU current law: AI Act consolidated 02024R1689-20260727 gives 39 AMENDED, 7 INSERTED and 7 NOISE.
  MDR, IVDR, Machinery, GPSR, MiCA, CCD2, LED and Platform Work also have consolidations with amended articles.
  DSA, Data Act, EHDS, EUDPR, Political Ads and DORA consolidations have no English manifestation in CELLAR,
  so their current law is UNKNOWN (fail-closed).
- Agent-register rows on amended text (stale drafts): **434 of 2620**.
- DRAFT obligation rows: 23104 (method obligations/0.2.0, every row `counsel_confirmed=false`).

The one AMENDED row (ICO guidance chapter 'accountability and governance') is **provisional**. The live page has
the lead-in of a list item that contains a nested list ('a description of the scope and context of the processing,
including:'), and the frozen text lacks exactly that lead-in while it keeps the nested items. That pattern looks like
an extraction artefact in the slice builder, but it cannot be decided from bytes that have changed since the freeze.
A reviewer decides. The NOISE row is LV AI Centre Law Article 7: a footnote marker '8' was added.

## What this does NOT claim

- It is **not legal advice and not certification**. It measures whether the text that was frozen is
  still the text the official source serves. Obligation rows are deterministic keyword cuts,
  DRAFT until a human reviewer sets `counsel_confirmed`. Non-English cuts (ZH/JA/KO/ES) use small
  marker lists and are weaker than the English cut. 2347 provisions have duty sentences that no evidence rule matched (UNTRIAGED).
- UNCHANGED means *the frozen text is still present*. It does not mean the instrument is
  unamended. On pinned routes (AU, KR, CN, Normattiva, the US Federal Register, govinfo editions, CA leginfo bill
  versions, Texas, Colorado, CPPA, and every `pinned_document` source) a newer version would not be seen; that is
  what `PINNED_NOT_CHECKED` says (3424 provisions).
- 1224 provisions are UNCHANGED because the document bytes are identical to the frozen fetch
  (by adapter: {'pinned_document': 759, 'us_ecfr': 128, 'uy_impo': 112, 'us_state_utah': 99, 'us_state_pinned': 96, 'it_normattiva_akn': 25, 'us_govinfo': 5}). Their per-provision re-split does not
  reproduce the original PDF extractor's boundaries. If those PDFs change, those provisions become UNKNOWN, not AMENDED.
- 18 provisions are UNCHANGED with identical words and differing punctuation only (`*/words-equal`). This is the inherited change rule.
- Recipes were re-derived for each source family so that they reproduce the frozen rows: UK Pnumber
  rendering, e-Gov title/caption order, Justice Laws labels, FR quote style, Utah XML. They are recorded in
  `spine/adapters.py` with the reason. They are not the original slice builders' code.
- A registry row is a routing record. It is not a relationship with any regulator and not a compliance claim.
- Reachability was measured from one sandbox on one day. GitHub runners may see different blocks
  (e.g. Chinese hosts from US runners). Those shards then go red: they are never silently green.

## Run locally

```
pip install -r requirements.txt pytest
pytest -q
python -m spine.engine --inputs data/inputs --adapter legislation_gov_uk --out shards/legislation_gov_uk
python -m spine.pipeline --out data/spine --inputs data/inputs --agent-register data/inputs/agent_register_index.jsonl
```

Exit code 2 means an authority was unreachable or unstable. A failed fetch is never reported as "no drift".
