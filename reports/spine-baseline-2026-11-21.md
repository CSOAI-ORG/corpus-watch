# provision-spine engine run report (21 Nov 2026)

Every number below is read from `provision_state.jsonl`, `documents.jsonl`, `report.json` and
`stale_drafts.jsonl` written by this run (`spine/pkg`, `python final_run.py`, full-text local inputs).
Generated at 2026-11-21T05:26:12+00:00.

## Scope

- Inputs: 7 waves (americas 746, asia_pacific 1,259, eu_six 414, europe_intl 2,407, europe_national 696, latam_africa_me 552, us 1,378 rows). After cross-wave dedupe (identical hashes, 0 conflicts, 0 rejects):
  7,155 unique rows (7,136 hashed + 19 IDS_ONLY), 607 registry instruments.
- Engine total: **7176** provisions. That is 7,155 + 18 inserted by EU consolidations + 3 legacy CSRD nested rows.
- Source documents: 306; gates {'STABLE': 296, 'UNREACHABLE': 1, 'NO_FETCH': 9}. Engine exit code 2 (Chile unreachable).
- Frozen v1 root reproduces: True.

## Adapters

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

## Per jurisdiction

| jurisdiction | provisions | exact hash reproduced | change vs frozen | current law |
|---|---|---|---|---|
| AR | 49 | 49 | {'UNCHANGED': 49} | {'PINNED_NOT_CHECKED': 49} |
| AU | 374 | 373 | {'UNCHANGED': 374} | {'PINNED_NOT_CHECKED': 374} |
| BR | 80 | 53 | {'UNCHANGED': 80} | {'PINNED_NOT_CHECKED': 80} |
| CA | 81 | 81 | {'UNCHANGED': 81} | {'UNCHANGED': 81} |
| CH | 77 | 26 | {'UNCHANGED': 77} | {'PINNED_NOT_CHECKED': 77} |
| CL | 102 | 0 | {'UNKNOWN': 102} | {'UNKNOWN': 102} |
| CN | 372 | 372 | {'UNCHANGED': 372} | {'PINNED_NOT_CHECKED': 372} |
| CoE | 36 | 36 | {'UNCHANGED': 36} | {'PINNED_NOT_CHECKED': 36} |
| DE | 106 | 106 | {'UNCHANGED': 106} | {'PINNED_NOT_CHECKED': 106} |
| DK | 13 | 12 | {'UNCHANGED': 13} | {'PINNED_NOT_CHECKED': 13} |
| ES | 102 | 98 | {'UNCHANGED': 102} | {'UNCHANGED': 102} |
| EU | 1690 | 1516 | {'INSERTED': 18, 'NOT_IN_CORPUS_V2': 3, 'UNCHANGED': 1668, 'UNKNOWN': 1} | {'AMENDED': 106, 'INSERTED': 18, 'NOISE': 27, 'PINNED_NOT_CHECKED': 23, 'UNCHANGED': 1047, 'UNKNOWN': 469} |
| FI | 29 | 25 | {'UNCHANGED': 29} | {'PINNED_NOT_CHECKED': 29} |
| GB | 1143 | 1064 | {'AMENDED': 1, 'UNCHANGED': 1142} | {'AMENDED': 1, 'PINNED_NOT_CHECKED': 34, 'UNCHANGED': 1108} |
| HU | 22 | 19 | {'UNCHANGED': 22} | {'PINNED_NOT_CHECKED': 22} |
| IE | 150 | 1 | {'UNCHANGED': 150} | {'PINNED_NOT_CHECKED': 150} |
| INTL | 54 | 6 | {'UNCHANGED': 39, 'UNKNOWN': 15} | {'PINNED_NOT_CHECKED': 39, 'UNKNOWN': 15} |
| IT | 104 | 31 | {'UNCHANGED': 104} | {'PINNED_NOT_CHECKED': 104} |
| JP | 215 | 161 | {'UNCHANGED': 215} | {'UNCHANGED': 215} |
| KR | 212 | 42 | {'UNCHANGED': 212} | {'PINNED_NOT_CHECKED': 212} |
| LV | 12 | 11 | {'NOISE': 1, 'UNCHANGED': 11} | {'PINNED_NOT_CHECKED': 12} |
| MT | 11 | 6 | {'UNCHANGED': 11} | {'PINNED_NOT_CHECKED': 11} |
| MU | 60 | 58 | {'UNCHANGED': 60} | {'PINNED_NOT_CHECKED': 60} |
| NG | 62 | 21 | {'UNCHANGED': 62} | {'PINNED_NOT_CHECKED': 62} |
| OECD | 2 | 0 | {'UNKNOWN': 2} | {'UNKNOWN': 2} |
| PE | 43 | 22 | {'UNCHANGED': 43} | {'PINNED_NOT_CHECKED': 43} |
| PY | 62 | 62 | {'UNCHANGED': 62} | {'PINNED_NOT_CHECKED': 62} |
| RW | 70 | 70 | {'UNCHANGED': 70} | {'PINNED_NOT_CHECKED': 70} |
| SA | 43 | 0 | {'UNCHANGED': 43} | {'PINNED_NOT_CHECKED': 43} |
| TW | 86 | 86 | {'UNCHANGED': 86} | {'UNCHANGED': 86} |
| UN | 1 | 0 | {'UNKNOWN': 1} | {'UNKNOWN': 1} |
| US | 1601 | 440 | {'UNCHANGED': 1601} | {'PINNED_NOT_CHECKED': 1341, 'UNCHANGED': 260} |
| UY | 112 | 0 | {'UNCHANGED': 112} | {'UNCHANGED': 112} |

Ladder per jurisdiction:

- AR: {'OBLIGATIONS_DRAFTED': 29, 'SOURCE_RECOVERED': 20}
- AU: {'OBLIGATIONS_DRAFTED': 190, 'SOURCE_RECOVERED': 184}
- BR: {'SOURCE_RECOVERED': 80}
- CA: {'OBLIGATIONS_DRAFTED': 37, 'SOURCE_RECOVERED': 44}
- CH: {'SOURCE_RECOVERED': 77}
- CL: {'HASH_ONLY': 102}
- CN: {'OBLIGATIONS_DRAFTED': 223, 'SOURCE_RECOVERED': 149}
- CoE: {'OBLIGATIONS_DRAFTED': 30, 'SOURCE_RECOVERED': 6}
- DE: {'SOURCE_RECOVERED': 106}
- DK: {'SOURCE_RECOVERED': 13}
- ES: {'OBLIGATIONS_DRAFTED': 29, 'SOURCE_RECOVERED': 73}
- EU: {'CROSSWALK_ONLY': 38, 'HASH_ONLY': 1, 'OBLIGATIONS_DRAFTED': 1324, 'PREDICATE': 1, 'RELATED_MEASURE': 12, 'SOURCE_RECOVERED': 314}
- FI: {'SOURCE_RECOVERED': 29}
- GB: {'OBLIGATIONS_DRAFTED': 569, 'SOURCE_RECOVERED': 574}
- HU: {'SOURCE_RECOVERED': 22}
- IE: {'OBLIGATIONS_DRAFTED': 115, 'SOURCE_RECOVERED': 35}
- INTL: {'HASH_ONLY': 15, 'OBLIGATIONS_DRAFTED': 22, 'SOURCE_RECOVERED': 17}
- IT: {'SOURCE_RECOVERED': 104}
- JP: {'OBLIGATIONS_DRAFTED': 146, 'SOURCE_RECOVERED': 69}
- KR: {'OBLIGATIONS_DRAFTED': 124, 'SOURCE_RECOVERED': 88}
- LV: {'SOURCE_RECOVERED': 12}
- MT: {'OBLIGATIONS_DRAFTED': 10, 'SOURCE_RECOVERED': 1}
- MU: {'OBLIGATIONS_DRAFTED': 51, 'SOURCE_RECOVERED': 9}
- NG: {'OBLIGATIONS_DRAFTED': 53, 'SOURCE_RECOVERED': 9}
- OECD: {'HASH_ONLY': 2}
- PE: {'OBLIGATIONS_DRAFTED': 13, 'SOURCE_RECOVERED': 30}
- PY: {'OBLIGATIONS_DRAFTED': 28, 'SOURCE_RECOVERED': 34}
- RW: {'OBLIGATIONS_DRAFTED': 19, 'SOURCE_RECOVERED': 51}
- SA: {'SOURCE_RECOVERED': 43}
- TW: {'OBLIGATIONS_DRAFTED': 53, 'SOURCE_RECOVERED': 33}
- UN: {'HASH_ONLY': 1}
- US: {'OBLIGATIONS_DRAFTED': 757, 'SOURCE_RECOVERED': 844}
- UY: {'OBLIGATIONS_DRAFTED': 52, 'SOURCE_RECOVERED': 60}

## Method of the UNCHANGED calls

- `exact`: 4847
- `doc-bytes-identical`: 1224
- `ws-equal`: 940
- `source-unreachable`: 102
- `IDS_ONLY`: 19
- `anchors/words-equal`: 17
- `consolidated-version`: 11
- `None`: 10
- `ws-equal+v1-tag-fragment`: 3
- `anchors`: 2
- `start+next-start/words-equal`: 1

## EU current law (latest CELLAR consolidation)

- 32024R1689 02024R1689-20260727 gate STABLE: {'AMENDED': 39, 'INSERTED': 7, 'UNCHANGED': 80, 'NOISE': 7}
- 32016R0679 02016R0679-20160504 gate STABLE: {'UNCHANGED': 90, 'AMENDED': 9}
- 32024R2847 02024R2847-20241120 gate STABLE: {'UNCHANGED': 74, 'NOISE': 2, 'AMENDED': 3}
- 32022R2554 02022R2554-20221227 gate NO_XHTML: {'UNKNOWN': 64}
- 32022L2555 02022L2555-20221227 gate STABLE: {'UNCHANGED': 48, 'AMENDED': 1}
- 32022L2464 02022L2464-20260318 gate STABLE: {'AMENDED': 5, 'UNCHANGED': 3}
- EU-intl instruments: see `current_law_class` / `current_law_source` in provision_state.jsonl. CELLAR has no
  English manifestation for the consolidations of DSA (02022R2065-20221027), Data Act (02023R2854-20231222),
  EHDS (02025R0327-20250305), EUDPR (02018R1725-20181121) or Political Ads (02024R0900-20240320), nor for DORA
  (02022R2554-20221227), so these are UNKNOWN.
- Inserted by amendment: 32024R1689:-14, 32024R1689:4a, 32024R1689:60a, 32024R1689:75a, 32024R1689:75b, 32024R1689:75c, 32024R1689:75d, EU-gpsr-2023:8a, EU-gpsr-2023:8b, EU-gpsr-2023:8c, EU-ivdr-2017:10a, EU-machinery-2023:25a, EU-machinery-2023:25b, EU-machinery-2023:25c, EU-machinery-2023:25d, EU-machinery-2023:25e, EU-mdr-2017:10a, EU-mica-2023:110a.

## Provisional changes vs frozen

- `GB-ico-ai-data-protection-guidance:what-are-the-accountability-and-governan...` AMENDED (anchors, 11 word edits). The
  inserted text is the lead-in of an `<li>` that has a nested list; the frozen text keeps the nested items but not the
  lead-in, which points to an extraction artefact in the slice builder. **Provisional, reviewer to decide.**
- `LV-ai-centre-law-2025:7` NOISE (footnote marker '8' added).

## Stale drafts

434 agent-register rows sit on amended text ({'32016R0679': 64, '32022L2464': 48, '32022L2555': 9, '32024R1689': 313}); every one is `counsel_confirmed=false`.
Action: re-draft from current text, then counsel review. List: `stale_drafts.jsonl`.

## Obligations (deterministic DRAFT cut, every provision with text)

- rows: 23104; by kind {'NONE': 3175, 'SUBMITTED': 2029, 'AUTHORITY': 3293, 'UNTRIAGED': 13966, 'OBSERVED': 641}
- provision roll-up: {'NONE': 3175, 'SUBMITTED': 750, 'UNTRIAGED': 2347, 'OBSERVED': 462, 'AUTHORITY': 423, 'UNKNOWN': 19}
- two-method agreement with the agent register (EU-six): {'OBSERVED': {'both': 10, 'deterministic_only': 24, 'agent_only': 21}, 'SUBMITTED': {'both': 99, 'deterministic_only': 21, 'agent_only': 98}}

## Blocked or limited, with route

- CL Ley 21.719 (102 provisions): www.leychile.cl `Consulta/obtxml` returns 401 "Not Allowed" and bcn.cl is a JS shell.
  Route: the owner downloads the official text into the granted folder, then it is frozen as a pinned document with
  URL and file sha256. Not bypassed.
- 19 IDS_ONLY rows (ISO/IEC 22989, 23894, 42001, 42005, 42006, OWASP agentic top 10, OECD, UNESCO, EN 18286): no text
  frozen (licence/paywall), so nothing to re-fetch. They stay HASH_ONLY.
- 6 EU consolidations have no English manifestation: current law UNKNOWN until CELLAR publishes one.
- Pinned routes (AU, KR, CN flk/gov.cn, FR documents, Texas, Colorado, CPPA, NIST/OMB/Peru PDFs, C2PA): newer versions
  are not discovered. The next step is a per-adapter latest-version resolver (AU API versions endpoint, law.go.kr current
  lsiSeq, flk version list).
- 1224 provisions rely on byte identity (by adapter: {'pinned_document': 759, 'us_ecfr': 128, 'uy_impo': 112, 'us_state_utah': 99, 'us_state_pinned': 96, 'it_normattiva_akn': 25, 'us_govinfo': 5}).
