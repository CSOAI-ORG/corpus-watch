"""Offline tests. Every guard here exists because a past watcher broke it:
   - whole-document hashing reported per article (corpus-watch EU subsets)
   - metadata churn reported as drift (corpus-watch UK, 319/319 events)
   - fetch failure reported as 'no drift'
Online reproduction of the 417 frozen hashes runs only with SPINE_ONLINE=1.
"""
import json
import os

import pytest

from spine import corpus as C
from spine import fluid as F
from spine import obligations as O

DOC = """<html><body>
<div id="art_1"><p class="oj-ti-art">Article 1</p><p>Subject matter. This Regulation lays down rules.</p></div>
<div id="art_2"><p class="oj-ti-art">Article 2</p><div class="x"><p>1. Providers shall ensure that outputs are marked in a machine-readable format.</p></div><div class="y"/></div>
<div id="art_2a"><p class="oj-ti-art">Article 2a</p><p>1. Deployers shall inform natural persons exposed to the system.</p></div>
<div id="anx_I"><p>ANNEX I</p><p>List of legislation.</p></div>
</body></html>"""


def test_normaliser_frozen_and_salted():
    assert C.normalise("A\u00a0 b\u2019s \u2014 c") == "a b's - c"
    assert C.provision_hash("x") != C.provision_hash("y")
    assert C.provision_hash("Hello  World") == C.provision_hash("hello world")
    with pytest.raises(ValueError):
        C.normalise(None)


def test_root_matches_reference_algorithm():
    anchors = {"b:1": "22", "a:1": "11"}
    import hashlib
    h = hashlib.sha256(); h.update(b"a:1"); h.update(b"11"); h.update(b"b:1"); h.update(b"22")
    assert C.corpus_root(anchors) == h.hexdigest()


def test_exact_parser_handles_nesting_selfclosing_and_inserted_articles():
    e = C.parse_exact(DOC)
    assert set(e) == {"1", "2", "2a", "-1"}
    assert "machine-readable" in e["2"] and "Deployers" not in e["2"]
    assert sorted(e, key=C.sort_key) == ["1", "2", "2a", "-1"]


def test_per_article_hashes_are_distinct():
    """The corpus-watch defect: 113 AI Act keys shared one hash. Never again."""
    e = C.parse_exact(DOC)
    hs = [C.provision_hash(v) for v in e.values()]
    assert len(set(hs)) == len(hs)


def test_change_classes():
    assert C.change_class("a b c", "a b c")[0] == "UNCHANGED"
    assert C.change_class("it is the 'x' rule ( 12 )", "it is the \u2018x\u2019 rule")[0] == "UNCHANGED"
    assert C.change_class("see OJ L 12, p. 4", "see OJ L 13, p. 5")[0] == "NOISE"
    assert C.change_class("providers may notify", "providers shall notify")[0] == "AMENDED"
    assert C.change_class("providers shall ensure x", "the commission shall assess whether adherence to x")[0] == "AMENDED"
    assert C.change_class(None, "new text")[0] == "INSERTED"
    assert C.change_class("old", None)[0] == "DELETED"


def test_determinism_gate_flags_unstable_source():
    calls = {"n": 0}

    def flappy(_u):
        calls["n"] += 1
        return DOC if calls["n"] % 2 else DOC.replace("List of legislation", "List of legislation, updated 09:14")

    _, rec = F.stable_parse("m", fetch=flappy, gate=True)
    assert rec["gate"] == "UNSTABLE" and rec["unstable_keys"] == ["-1"]
    _, rec = F.stable_parse("m", fetch=lambda _u: DOC, gate=True)
    assert rec["gate"] == "STABLE"


def test_build_fails_closed_when_authority_unreachable():
    def boom(_u):
        raise OSError("tunnel 502")

    frozen = {"32024R1689:1": "ab" * 32}
    out = C.build(frozen, fetch=boom, work=lambda c: {"celex": c, "work": "w", "manifestation": "m", "modified": None})
    states = {p["provision_id"]: p["state"] for p in out["provisions"]}
    assert states["32024R1689:1"] == "UNKNOWN"
    assert "REPRODUCED" not in states.values()
    assert len(out["unknown_instruments"]) == len(C.INSTRUMENTS)


def test_obligation_fixtures():
    assert O.selftest() == []


def test_current_law_unstable_marks_unknown():
    calls = {"n": 0}

    def flappy(_u):
        calls["n"] += 1
        return DOC if calls["n"] % 2 else DOC.replace("rules", "rules (rev)")

    orig = C.cellar_work
    C.cellar_work = lambda c: {"celex": c, "work": "w", "manifestation": "m", "modified": None}
    try:
        cl = F.current_law("32024R1689", C.parse_exact(DOC), fetch=flappy, versions=["02024R1689-20260727"])
    finally:
        C.cellar_work = orig
    assert {v["class"] for v in cl["provisions"].values()} == {"UNKNOWN"}


@pytest.mark.skipif(os.environ.get("SPINE_ONLINE") != "1", reason="online check")
def test_online_417_reproduce():
    import urllib.request
    man = json.load(urllib.request.urlopen("https://councilof.ai/interop/frozen-provision-hashes.json"))
    out = C.build(man["anchors"])
    assert out["root_v1"] == man["corpus_root"]
