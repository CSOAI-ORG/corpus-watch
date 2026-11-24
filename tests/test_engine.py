"""Offline tests for the registry-driven engine. Each guard exists because a past watcher or
a past slice broke it:
  - whole-document hash copied to every article (corpus-watch EU subsets, 113 keys / 1 hash)
  - page-metadata churn reported as drift (corpus-watch UK, 319/319 events flipping A->B->A)
  - unreachable source reported as 'no drift'
  - a cross-reference mistaken for an inserted article
  - a new wave needing code changes
"""
import hashlib
import json
import os

import pytest

from spine import adapters as A
from spine import corpus as C
from spine import engine as E
from spine import inputs as I
from spine import obligations as O
from spine import resplit as R
from spine import textx as X

UK_XML = """<Legislation xmlns="http://www.legislation.gov.uk/namespaces/legislation" RestrictStartDate="{stamp}">
<ukm:Metadata xmlns:ukm="http://www.legislation.gov.uk/namespaces/metadata"><dc:modified xmlns:dc="x">{stamp}</dc:modified></ukm:Metadata>
<Primary><Body>
<P1group><Title>Overview</Title><P1 id="section-1"><Pnumber>1</Pnumber><P1para>
<P2 id="section-1-1"><Pnumber>1</Pnumber><P2para><Text>This Act makes provision about the processing of personal data.</Text></P2para></P2>
<P2 id="section-1-2"><Pnumber>2</Pnumber><P2para><Text>Most processing of personal data is subject to the UK GDPR.</Text></P2para></P2>
</P1para></P1></P1group>
<P1group><Title>Terms relating to the processing of personal data</Title><P1 id="section-3"><Pnumber>3</Pnumber><P1para>
<P2 id="section-3-1"><Pnumber>1</Pnumber><P2para><Text>This section defines some terms used in this Act.</Text></P2para></P2>
<BlockAmendment><P1group><Title>Interview notices</Title><P1 id="x"><Pnumber>148A</Pnumber><P1para><Text>The Commissioner may give an interview notice.</Text></P1para></P1></P1group></BlockAmendment>
</P1para></P1></P1group>
</Body></Primary></Legislation>"""

FROZEN_UK = [
    "Overview\n(1)\nThis Act makes provision about the processing of personal data.\n(2)\nMost processing of personal data is subject to the UK GDPR.",
    "Terms relating to the processing of personal data\n(1)\nThis section defines some terms used in this Act.\nInterview notices\n148A\nThe Commissioner may give an interview notice.",
]


def _row(pid, text, number, url="https://www.legislation.gov.uk/ukpga/2018/12/data.xml", sha=None):
    return {"provision_id": pid, "instrument_id": pid.split(":")[0], "number": number, "label": number, "text": text,
            "provision_sha256": C.provision_hash(text), "normaliser_version": "1.0.0",
            "source": {"url": url, "method": "http", "document_sha256": sha}, "_wave": "t", "_order": 0}


def _fetcher(seq):
    """Injectable fetch: returns bytes from seq in turn (cycling), like two live fetches."""
    state = {"i": 0}

    def f(ad, url, ctx):
        b = seq[state["i"] % len(seq)]
        state["i"] += 1
        if isinstance(b, Exception):
            raise b
        b = b.encode() if isinstance(b, str) else b
        return {"bytes": b, "sha256": hashlib.sha256(b).hexdigest(), "format": X.sniff(b), "resolved_url": url, "final_url": url}
    return f


def _doc(rows, adapter="legislation_gov_uk", celex=None, frozen_doc_sha=None):
    return {"adapter": adapter, "instrument_id": rows[0]["instrument_id"], "url": rows[0]["source"]["url"],
            "celex": celex, "jurisdiction": "GB", "frozen_document_sha256": frozen_doc_sha, "rows": rows}


def test_uk_metadata_churn_is_not_drift():
    """corpus-watch flipped UK GDPR Art 5 32 times in 47 days. Page metadata changing between
    the two gate fetches must leave every provision UNCHANGED and the gate STABLE."""
    rows = [_row("GB-dpa-2018:s1", FROZEN_UK[0], "s1"), _row("GB-dpa-2018:s3", FROZEN_UK[1], "s3")]
    f = _fetcher([UK_XML.format(stamp="2026-11-20T04:07:58"), UK_XML.format(stamp="2026-11-21T04:07:58")])
    res = E.measure_doc(_doc(rows), gate=True, fetch=f)
    assert res["doc"]["bytes_stable"] is False          # bytes churn ...
    assert res["doc"]["gate"] == "STABLE"               # ... but provision text does not
    assert {m["class"] for m in res["provisions"].values()} == {"UNCHANGED"}
    assert all(m["reproduced"] for m in res["provisions"].values())   # exact frozen hash, UK renderer


def test_per_provision_hashes_are_distinct_not_whole_document():
    rows = [_row("GB-dpa-2018:s1", FROZEN_UK[0], "s1"), _row("GB-dpa-2018:s3", FROZEN_UK[1], "s3")]
    res = E.measure_doc(_doc(rows), gate=False, fetch=_fetcher([UK_XML.format(stamp="a")]))
    hs = [m["current_sha256"] for m in res["provisions"].values()]
    assert len(set(hs)) == len(hs) == 2
    assert hashlib.sha256(UK_XML.format(stamp="a").encode()).hexdigest() not in hs


def test_unreachable_is_unknown_never_unchanged():
    rows = [_row("GB-dpa-2018:s1", FROZEN_UK[0], "s1")]
    res = E.measure_doc(_doc(rows), gate=True, fetch=_fetcher([A.Unreachable("tunnel 403")]))
    assert res["doc"]["gate"] == "UNREACHABLE"
    assert res["provisions"]["GB-dpa-2018:s1"]["class"] == "UNKNOWN"


def test_authority_refusal_is_blocked_and_unknown():
    rows = [_row("GB-dpa-2018:s1", FROZEN_UK[0], "s1")]
    res = E.measure_doc(_doc(rows), gate=True, fetch=_fetcher([A.Unreachable("HTTPError: HTTP Error 401: Unauthorized")]))
    assert res["doc"]["gate"] == "BLOCKED"
    assert res["provisions"]["GB-dpa-2018:s1"]["class"] == "UNKNOWN"
    assert res["provisions"]["GB-dpa-2018:s1"]["method"] == "source-blocked"


def test_unstable_text_between_fetches_is_unknown():
    rows = [_row("GB-dpa-2018:s1", FROZEN_UK[0], "s1")]
    a = UK_XML.format(stamp="x")
    b = a.replace("Most processing", "All processing")
    res = E.measure_doc(_doc(rows), gate=True, fetch=_fetcher([a, b]))
    assert res["doc"]["gate"] == "UNSTABLE"
    assert res["provisions"]["GB-dpa-2018:s1"]["class"] == "UNKNOWN"


def test_amended_noise_and_missing_anchor():
    old = ("Article 9 The provider shall keep the logs for a period of six months and shall make them available "
           "to the authority on request, see page 12 of the Official Journal.")
    nxt = "Article 10 Final provisions of this test text follow here."
    rows = [_row("T-x:9", old, "9", url="https://example.org/a"), _row("T-x:10", nxt, "10", url="https://example.org/a")]
    amended = f"<p>{old.replace('six months', 'twelve months')}</p><p>{nxt}</p>"
    m = R.measure(rows, X.extract(amended.encode()))
    assert m["T-x:9"]["class"] == "AMENDED" and m["T-x:9"]["edits"] >= 1
    noise = f"<p>{old.replace('page 12', 'page 13')}</p><p>{nxt}</p>"
    assert R.measure(rows, X.extract(noise.encode()))["T-x:9"]["class"] == "NOISE"
    gone = f"<p>Completely different text about bread.</p><p>{nxt}</p>"
    assert R.measure(rows, X.extract(gone.encode()))["T-x:9"]["class"] == "UNKNOWN"   # never AMENDED/UNCHANGED


def test_byte_identical_document_is_unchanged():
    rows = [_row("T-x:1", "Some frozen text that the recipe cannot locate at all.", "1", url="https://example.org/b")]
    body = b"<p>layout differs from the frozen split</p>"
    res = E.measure_doc(_doc(rows, adapter="pinned_document", frozen_doc_sha=hashlib.sha256(body).hexdigest()),
                        gate=True, fetch=_fetcher([body]))
    m = res["provisions"]["T-x:1"]
    assert m["class"] == "UNCHANGED" and m["method"] == "doc-bytes-identical" and m["resplit_class"] == "UNKNOWN"


def test_hash_only_recipe_for_withheld_text():
    t = "Artículo 1.- Introdúcense las siguientes modificaciones en la ley N° 19.628, sobre protección de la vida privada."
    row = _row("CL-x:1", t, "1", url="https://www.bcn.cl/leychile/navegar?idNorma=1")
    pub, basis = I.split_for_publication([row], {"CL-x": {"text_licence": "unknown (reuse terms not verified)"}})
    assert pub[0]["text"] is None and "recipe_hashonly" in pub[0] and not basis["CL-x"]["republish"]
    assert t[:30] not in json.dumps(pub[0], ensure_ascii=False)
    ok = R.measure(pub, X.extract(f"<div>Encabezado</div><p>{t}</p>".encode()))
    assert ok["CL-x:1"]["class"] == "UNCHANGED"
    changed = R.measure(pub, X.extract(f"<p>{t.replace('vida privada', 'datos personales')}</p>".encode()))
    assert changed["CL-x:1"]["class"] == "UNKNOWN" and changed["CL-x:1"]["changed_hash_only"]


def test_licence_basis():
    assert I.licence_basis("EU reuse Decision 2011/833/EU")["republish"]
    assert I.licence_basis("Open Government Licence v3.0 (legislation.gov.uk)")["republish"]
    assert I.licence_basis("Korea Copyright Act art. 7 excludes statutes and decrees from protection")["republish"]
    assert I.licence_basis("PRC Copyright Law art. 5 excludes laws, regulations and official documents")["republish"]
    assert not I.licence_basis("unknown (official BCN Ley Chile publication; reuse terms not verified)")["republish"]
    assert not I.licence_basis("Text as published in OJ (EU reuse Decision 2011/833/EU); CoE reuse terms not verified")["republish"]
    assert not I.licence_basis(None)["republish"]


def test_new_wave_needs_no_code_change(tmp_path):
    reg = {"instrument_id": "ZZ-new-law-2027", "jurisdiction": "ZZ", "freeze_mode": "FULL_TEXT",
           "text_licence": "CC-BY-4.0", "official_id": "ZZ 1/2027"}
    text = "Section 1. Every operator must publish a notice on its website."
    prov = _row("ZZ-new-law-2027:s1", text, "s1", url="https://law.example.zz/act/1/full.html")
    prov.pop("_wave"); prov.pop("_order")
    (tmp_path / "registry_wave9.jsonl").write_text(json.dumps(reg) + "\n")
    (tmp_path / "provisions_wave9.jsonl").write_text(json.dumps(prov) + "\n")
    res = E.run(str(tmp_path), fetch=_fetcher([f"<html><p>{text}</p></html>"]), consolidated=False, log=None)
    rec = res["records"][0]
    assert rec["adapter"] == "pinned_document" and rec["jurisdiction"] == "ZZ"
    assert rec["change_vs_frozen"] == "UNCHANGED" and res["exit_code"] == 0
    assert O.provision_kind(O.extract(rec["provision_id"], text)) == "OBSERVED"


def test_run_exit_2_on_unreachable(tmp_path):
    prov = _row("ZZ-a-2027:1", "Section 1. Text.", "1", url="https://law.example.zz/a")
    prov.pop("_wave"); prov.pop("_order")
    (tmp_path / "provisions_w.jsonl").write_text(json.dumps(prov) + "\n")
    res = E.run(str(tmp_path), fetch=_fetcher([A.Unreachable("403")]), consolidated=False, log=None)
    assert res["exit_code"] == 2 and res["records"][0]["change_vs_frozen"] == "UNKNOWN"


def test_wave_conflict_is_reported_not_overwritten(tmp_path):
    a = _row("ZZ-a-2027:1", "Section 1. Text one.", "1"); a.pop("_wave"); a.pop("_order")
    b = dict(a, text="Section 1. Text two.", provision_sha256=C.provision_hash("Section 1. Text two."))
    (tmp_path / "provisions_w1.jsonl").write_text(json.dumps(a) + "\n")
    (tmp_path / "provisions_w2.jsonl").write_text(json.dumps(b) + "\n")
    inp = I.load(str(tmp_path))
    assert inp["conflicts"] and not inp["provisions"]


def test_bad_hash_rejected(tmp_path):
    a = _row("ZZ-a-2027:1", "Section 1. Text one.", "1"); a.pop("_wave"); a.pop("_order")
    a["provision_sha256"] = "00" * 32
    (tmp_path / "provisions_w.jsonl").write_text(json.dumps(a) + "\n")
    assert I.load(str(tmp_path))["rejected"][0]["reason"] == "text does not re-hash"


def test_routing_by_source_host():
    assert A.route({"provision_sha256": "x", "source": {"url": "https://laws.e-gov.go.jp/api/2/law_data/1"}}).name == "jp_egov"
    assert A.route({"provision_sha256": "x", "source": {"kind": "git_db"}}).name == "eu_cellar"
    assert A.route({"provision_sha256": None, "source": {"url": "https://www.iso.org/"}}).name == "identifier_only"
    assert A.ECFR().resolve("https://www.ecfr.gov/current/title-16/section-461.1", {}).endswith("title-16?section=461.1")
    assert A.FederalRegister().resolve(
        "https://www.federalregister.gov/documents/2019/02/14/2019-02544/maintaining", {}).endswith("/2019/02/14/2019-02544.html")
    assert A.JusticeCA().resolve("https://laws-lois.justice.gc.ca/eng/acts/P-8.6/page-9.html", {}).endswith("/P-8.6/FullText.html")


def test_jp_lister_ignores_cross_references():
    raw = ('<MainProvision><Article Num="1"><ArticleTitle>第一条</ArticleTitle><Sentence>第二十四条の四の規定による</Sentence></Article>'
           '<Article Num="2_2"><ArticleTitle>第二条の二</ArticleTitle></Article></MainProvision><SupplProvision><Article Num="3"/></SupplProvision>')
    assert set(A.EGovJP.insertion_lister(raw)) == {"1", "2-2"}


def test_kanji_numerals():
    assert [A.kanji_int(x) for x in ("一", "十", "十五", "百二十三", "百零五", "一百八十五")] == [1, 10, 15, 123, 105, 185]


def test_multilingual_obligation_fixtures():
    assert O.selftest() == []


@pytest.mark.skipif(not os.path.isdir("data/inputs"), reason="committed inputs not present")
def test_committed_inputs_rehash_and_withheld_rows_have_recipes():
    inp = I.load("data/inputs")
    assert not inp["rejected"] and not inp["conflicts"]
    for p in inp["provisions"]:
        if p.get("text_withheld"):
            assert p.get("text") is None and p.get("recipe_hashonly")


def test_failed_shard_carries_previous_records_forward(tmp_path):
    """A red shard publishes nothing; the aggregate keeps its previous records verbatim
    (flagged carried_forward) instead of calling them unchanged or dropping them."""
    inp_dir = tmp_path / "inputs"; inp_dir.mkdir()
    a = _row("ZZ-a-2027:1", "Section 1. Text one.", "1", url="https://law.example.zz/a"); a.pop("_wave"); a.pop("_order")
    (inp_dir / "provisions_w.jsonl").write_text(json.dumps(a) + "\n")
    prev = tmp_path / "provision_state.jsonl"
    prev.write_text(json.dumps({"provision_id": "ZZ-a-2027:1", "adapter": "pinned_document",
                                "change_vs_frozen": "UNCHANGED", "method": "exact"}) + "\n")
    shards = tmp_path / "shards"; shards.mkdir()
    res = E.load_shards(str(shards), I.load(str(inp_dir)), prev_state=str(prev))
    assert res["missing_shards"] == ["pinned_document"]
    rec = res["records"][0]
    assert rec["carried_forward"] is True and rec["change_vs_frozen"] == "UNCHANGED"
    res2 = E.load_shards(str(shards), I.load(str(inp_dir)), prev_state=None)
    assert res2["records"][0]["change_vs_frozen"] == "UNKNOWN" and res2["records"][0]["method"] == "shard-missing"


def test_licence_basis_national_statutes():
    assert I.licence_basis("Amtliches Werk (§ 5 UrhG); gesetze-im-internet.de consolidated text")["republish"]
    assert I.licence_basis("Danish statutes are not protected by copyright (Ophavsretsloven § 9); Retsinformation open data")["republish"]
    assert I.licence_basis("Brazilian official legislative text (Lei 9.610/1998 art. 8 IV excludes official texts from copyright)")["republish"]
    # an explicit 'not verified' / 'not re-read' always withholds, whatever statute is cited
    assert not I.licence_basis("Official acts are excluded from copyright (Art. 5 L. 633/1941); Normattiva reuse terms not separately verified")["republish"]
    assert not I.licence_basis("Government of Ireland copyright; eISB Open Data Licence (terms not re-read this run)")["republish"]
    assert not I.licence_basis("Official NDPC publication; reuse terms not stated")["republish"]


def test_ico_renderer_drops_ui_chrome():
    html = ('<html><body><nav>Search this document</nav><main><p>Contents</p><span class="hidden">Click to toggle details</span>'
            '<details><summary>Latest updates</summary><p>This guidance was updated on 15 March 2023.</p></details></main></body></html>')
    t = A.ICO().text({"bytes": html.encode()})
    assert "toggle" not in t and "Latest updates" not in t and "Search this document" not in t and "15 March 2023" in t


def test_licence_basis_apac_standards_wave():
    # bases added with the APAC-and-standards wave (owner-agreed permissive list)
    assert I.licence_basis("Apache-2.0 (atlas-data LICENSE.txt, Copyright 2021-2026 MITRE)")["republish"]
    assert I.licence_basis("CC-BY-SA-4.0 (repository README; share-alike applies)")["republish"]
    assert I.licence_basis("Japan MIC site policy: content under the Public Data Terms of Use v1.0 (CC BY 4.0-compatible) unless otherwise noted")["republish"]
    assert I.licence_basis("Public domain in the US (17 U.S.C. 105, work of the US Government); NIST asks for attribution")["republish"]
    # 'not re-verified' withholds like 'not verified', whatever statute is cited
    assert not I.licence_basis("Not subject to copyright (PRC Copyright Law art. 5: laws, regulations and administrative documents); stated from legal knowledge, not re-verified")["republish"]
    # bases outside the permissive list stay withheld until the owner adds them
    assert not I.licence_basis("Public domain: UN documents issued with a UN symbol (ST/AI/189/Add.9/Rev.2)")["republish"]
    assert not I.licence_basis("HKSAR Government copyright (dc:rights); DoJ e-Legislation data released as open data on data.gov.hk under the DATA.GOV.HK terms of use")["republish"]
    assert not I.licence_basis("ISO/IEC copyright - all rights reserved")["republish"]


@pytest.mark.skipif(not os.path.isdir("data/inputs"), reason="committed inputs not present")
def test_committed_licence_basis_matches_rules():
    inp = I.load("data/inputs")
    rows = {json.loads(l)["instrument_id"]: json.loads(l) for l in open("data/inputs/licence_basis.jsonl", encoding="utf-8")}
    assert set(rows) == set(inp["registry"])
    for iid, r in inp["registry"].items():
        b = I.licence_basis(r.get("text_licence"))
        assert rows[iid]["basis"] == b["basis"]
        assert rows[iid]["republish_text"] == (b["republish"] and r.get("freeze_mode") == "FULL_TEXT")
    for p in inp["provisions"]:
        if p.get("text"):
            assert I.licence_basis(inp["registry"][p["instrument_id"]].get("text_licence"))["republish"], p["provision_id"]
