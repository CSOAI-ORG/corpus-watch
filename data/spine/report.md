# Provision spine: daily fluid pass 2026-11-28T14:01:52+00:00

Every number below is derived from files written in this pass. Obligation rows are DRAFT machine cuts (counsel_confirmed=false). Measurement, not certification.

- Frozen 417 still reproduce (root matches): **True**
- Provisions in the engine: **8361** by jurisdiction {'EU': 1690, 'AU': 374, 'CA': 81, 'CL': 102, 'CN': 404, 'ES': 102, 'CoE': 36, 'GB': 1143, 'ID': 76, 'IN': 21, 'INTL': 374, 'OECD': 26, 'UN': 215, 'IT': 104, 'JP': 215, 'KR': 212, 'US': 1969, 'PE': 43, 'HK': 130, 'DE': 106, 'DK': 13, 'FI': 29, 'IE': 150, 'LV': 12, 'HU': 22, 'MT': 11, 'CH': 77, 'AR': 49, 'BR': 80, 'MU': 60, 'NG': 62, 'PY': 62, 'RW': 70, 'SA': 43, 'TW': 86, 'UY': 112}
- Ladder: {'HASH_ONLY': 293, 'SOURCE_RECOVERED': 3275, 'OBLIGATIONS_DRAFTED': 4742, 'CROSSWALK_ONLY': 38, 'RELATED_MEASURE': 12, 'PREDICATE': 1, 'CAPSULE_BOUND': 0}
- Change since OJ original (EU six): {'AMENDED': 108, 'UNCHANGED': 3059, 'NOISE': 27, 'UNKNOWN': 683, 'INSERTED': 18, 'PINNED_NOT_CHECKED': 4466}
- Agent-register rows now on amended text (re-draft needed): **434** of 2620
- Two-method OBSERVED shortlist (next predicates): 32016R0679:13, 32016R0679:14, 32016R0679:37, 32022L2464:29, 32022L2464:40, 32024R1689:26, 32024R1689:50, 32024R1689:71, 32024R2847:13, 32024R2847:19
- Change class vs frozen (all waves): {'UNCHANGED': 8044, 'NOT_IN_CORPUS_V2': 3, 'INSERTED': 18, 'UNKNOWN': 293, 'AMENDED': 2, 'NOISE': 1}
- Current-law class (EU consolidations): {'AMENDED': 108, 'UNCHANGED': 3059, 'NOISE': 27, 'UNKNOWN': 683, 'INSERTED': 18, 'PINNED_NOT_CHECKED': 4466}
- Engine documents: 385 gates {'STABLE': 345, 'NO_FETCH': 40}; missing shards: none

## Authority adapters

| adapter | status | documents | provisions | gates | current-version route |
|---|---|---|---|---|---|
| au_legislation_gov_au | REACHABLE | 2 | 374 | {'STABLE': 2} | pinned (compilation start date in URL) |
| ca_justice_laws | REACHABLE | 2 | 81 | {'STABLE': 2} | inherent |
| cl_bcn_leychile | REACHABLE | 1 | 102 | {'STABLE': 1} | inherent |
| cn_flk_npc | REACHABLE | 4 | 274 | {'STABLE': 4} | pinned (bbbs = one published version of the law) |
| cn_gov_cn | REACHABLE | 4 | 98 | {'STABLE': 4} | pinned (policy-library page) |
| es_boe_api | REACHABLE | 2 | 102 | {'STABLE': 2} | inherent |
| eu_cellar | REACHABLE | 33 | 1694 | {'STABLE': 33} | pinned-OJ (current law via spine.fluid consolidated diff) |
| gb_ico_guidance | REACHABLE | 14 | 14 | {'STABLE': 14} | inherent |
| identifier_only | NOT_FETCHED | 40 | 162 | {'NO_FETCH': 40} | inherent |
| it_normattiva_akn | REACHABLE | 3 | 104 | {'STABLE': 3} | pinned (dataVigenza in URL) |
| jp_egov | REACHABLE | 2 | 215 | {'STABLE': 2} | inherent |
| kr_law_go_kr | REACHABLE | 3 | 212 | {'STABLE': 3} | pinned (efYd effective-date version in URL) |
| legislation_gov_uk | REACHABLE | 6 | 1095 | {'STABLE': 6} | inherent |
| pinned_document | REACHABLE | 102 | 2522 | {'STABLE': 102} | pinned (recorded URL) |
| tw_law_moj | REACHABLE | 2 | 86 | {'STABLE': 2} | inherent |
| us_ca_leginfo_bulk | REACHABLE | 63 | 366 | {'STABLE': 63} | pinned (session archive member = one bill version) |
| us_ecfr | REACHABLE | 21 | 143 | {'STABLE': 21} | inherent |
| us_federal_register | REACHABLE | 14 | 115 | {'STABLE': 14} | pinned (a published FR document does not change) |
| us_govinfo | REACHABLE | 8 | 86 | {'STABLE': 8} | pinned (USCODE edition in URL) |
| us_state_pinned | REACHABLE | 27 | 266 | {'STABLE': 27} | pinned (enrolled bill / approved regulation text) |
| us_state_utah | REACHABLE | 27 | 117 | {'STABLE': 27} | resolved: page shell's versionDefault = 'Current Version' |
| uy_impo | REACHABLE | 5 | 112 | {'STABLE': 5} | inherent |

## By jurisdiction (change class vs frozen)

| jurisdiction | total | classes |
|---|---|---|
| AR | 49 | {'UNCHANGED': 49} |
| AU | 374 | {'UNCHANGED': 374} |
| BR | 80 | {'UNCHANGED': 80} |
| CA | 81 | {'UNCHANGED': 81} |
| CH | 77 | {'UNCHANGED': 77} |
| CL | 102 | {'UNCHANGED': 49, 'UNKNOWN': 53} |
| CN | 404 | {'UNCHANGED': 404} |
| CoE | 36 | {'UNCHANGED': 36} |
| DE | 106 | {'UNCHANGED': 106} |
| DK | 13 | {'UNCHANGED': 13} |
| ES | 102 | {'UNCHANGED': 102} |
| EU | 1690 | {'UNCHANGED': 1668, 'NOT_IN_CORPUS_V2': 3, 'INSERTED': 18, 'UNKNOWN': 1} |
| FI | 29 | {'UNCHANGED': 29} |
| GB | 1143 | {'UNCHANGED': 1113, 'AMENDED': 2, 'UNKNOWN': 28} |
| HK | 130 | {'UNCHANGED': 82, 'UNKNOWN': 48} |
| HU | 22 | {'UNCHANGED': 20, 'UNKNOWN': 1, 'NOISE': 1} |
| ID | 76 | {'UNKNOWN': 76} |
| IE | 150 | {'UNCHANGED': 150} |
| IN | 21 | {'UNKNOWN': 21} |
| INTL | 374 | {'UNKNOWN': 61, 'UNCHANGED': 313} |
| IT | 104 | {'UNCHANGED': 104} |
| JP | 215 | {'UNCHANGED': 215} |
| KR | 212 | {'UNCHANGED': 212} |
| LV | 12 | {'UNCHANGED': 11, 'UNKNOWN': 1} |
| MT | 11 | {'UNCHANGED': 11} |
| MU | 60 | {'UNCHANGED': 60} |
| NG | 62 | {'UNCHANGED': 62} |
| OECD | 26 | {'UNKNOWN': 2, 'UNCHANGED': 24} |
| PE | 43 | {'UNCHANGED': 43} |
| PY | 62 | {'UNCHANGED': 62} |
| RW | 70 | {'UNCHANGED': 70} |
| SA | 43 | {'UNCHANGED': 43} |
| TW | 86 | {'UNCHANGED': 86} |
| UN | 215 | {'UNKNOWN': 1, 'UNCHANGED': 214} |
| US | 1969 | {'UNCHANGED': 1969} |
| UY | 112 | {'UNCHANGED': 112} |

## EU-six sources and determinism gate

| CELEX | latest consolidated | gate | classes |
|---|---|---|---|
| 32024R1689 | 02024R1689-20260727 | STABLE | {'AMENDED': 39, 'INSERTED': 7, 'UNCHANGED': 80, 'NOISE': 7} |
| 32016R0679 | 02016R0679-20160504 | STABLE | {'UNCHANGED': 90, 'AMENDED': 9} |
| 32024R2847 | 02024R2847-20241120 | STABLE | {'UNCHANGED': 74, 'NOISE': 2, 'AMENDED': 3} |
| 32022R2554 | 02022R2554-20221227 | NO_XHTML | {'UNKNOWN': 64} |
| 32022L2555 | 02022L2555-20221227 | STABLE | {'UNCHANGED': 48, 'AMENDED': 1} |
| 32022L2464 | 02022L2464-20260318 | STABLE | {'AMENDED': 5, 'UNCHANGED': 3} |

## Drift since last pass

Baseline pass: no previous state.

Inserted by amendment: 32024R1689:-14, 32024R1689:4a, 32024R1689:60a, 32024R1689:75a, 32024R1689:75b, 32024R1689:75c, 32024R1689:75d, EU-gpsr-2023:8a, EU-gpsr-2023:8b, EU-gpsr-2023:8c, EU-ivdr-2017:10a, EU-machinery-2023:25a, EU-machinery-2023:25b, EU-machinery-2023:25c, EU-machinery-2023:25d, EU-machinery-2023:25e, EU-mdr-2017:10a, EU-mica-2023:110a

Amended since OJ (108): 32016R0679:37, 32016R0679:41, 32016R0679:42, 32016R0679:43, 32016R0679:57, 32016R0679:64, 32016R0679:65, 32016R0679:69, 32016R0679:70, 32022L2464:1, 32022L2464:2, 32022L2464:3, 32022L2464:5, 32022L2464:6, 32022L2555:19, 32024R1689:-1, 32024R1689:-8, 32024R1689:1, 32024R1689:10, 32024R1689:108, 32024R1689:11, 32024R1689:111, 32024R1689:113, 32024R1689:17, 32024R1689:2, 32024R1689:25, 32024R1689:27, 32024R1689:28, 32024R1689:29, 32024R1689:3, 32024R1689:30, 32024R1689:4, 32024R1689:40, 32024R1689:42, 32024R1689:43, 32024R1689:5, 32024R1689:50, 32024R1689:56, 32024R1689:57, 32024R1689:58, 32024R1689:6, 32024R1689:60, 32024R1689:63, 32024R1689:64, 32024R1689:69, 32024R1689:70, 32024R1689:72, 32024R1689:75, 32024R1689:76, 32024R1689:77, 32024R1689:95, 32024R1689:96, 32024R1689:97, 32024R1689:99, EU-ccd2-2023:10, EU-ccd2-2023:16, EU-ccd2-2023:2, EU-ccd2-2023:3, EU-ccd2-2023:annex-I, EU-ccd2-2023:annex-II, EU-gpsr-2023:2, EU-gpsr-2023:3, EU-gpsr-2023:48, EU-ivdr-2017:110, EU-ivdr-2017:112, EU-ivdr-2017:113, EU-ivdr-2017:40, EU-ivdr-2017:48, EU-ivdr-2017:70, EU-ivdr-2017:74, EU-ivdr-2017:annex-I, EU-ivdr-2017:annex-III, EU-ivdr-2017:annex-IX, EU-ivdr-2017:annex-VII, EU-ivdr-2017:annex-VIII, EU-led-2016:51, EU-machinery-2023:20, EU-machinery-2023:3, EU-machinery-2023:47, EU-machinery-2023:8, EU-machinery-2023:annex-III, EU-machinery-2023:annex-V, EU-mdr-2017:106, EU-mdr-2017:120, EU-mdr-2017:122, EU-mdr-2017:123, EU-mdr-2017:2, EU-mdr-2017:34, EU-mdr-2017:44, EU-mdr-2017:52, EU-mdr-2017:59, EU-mdr-2017:61, EU-mdr-2017:7, EU-mdr-2017:74, EU-mdr-2017:78, EU-mdr-2017:annex-I, EU-mdr-2017:annex-II, EU-mdr-2017:annex-III, EU-mdr-2017:annex-IX, EU-mdr-2017:annex-VI, EU-mdr-2017:annex-VII, EU-mdr-2017:annex-VIII, EU-mdr-2017:annex-XV, EU-mica-2023:81, EU-mica-2023:92, EU-platform-work-2024:2, GB-ico-ai-data-protection-guidance:what-are-the-accountability-and-governan, GB-uk-gdpr-2016:4

