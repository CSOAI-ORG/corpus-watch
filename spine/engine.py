"""spine.engine: registry-driven fluid pass over every frozen provision of every wave.

  data/inputs/{registry,provisions}_*.jsonl
     -> plan: group provisions by (adapter, instrument, source document), frozen order kept
     -> per document: adapter fetch #1 -> extract -> re-split (recorded recipe) -> hashes
                      adapter fetch #2 -> extract -> re-split -> hashes      (determinism gate)
     -> per provision: change class vs frozen (REPRODUCED/UNCHANGED/NOISE/AMENDED/UNKNOWN)
     -> per document: INSERTED ids from the adapter's structural lister (where validated)
     -> EU CELEX instruments (non EU-six): current-law class vs latest CELLAR consolidation

Fail-closed rules:
  * unreachable or unstable source -> every provision in it UNKNOWN, gate recorded, exit 2
  * a missing anchor -> UNKNOWN for that provision (never AMENDED, never UNCHANGED)
  * byte-identical document (sha256 equals the frozen fetch) -> provisions cannot have
    changed: UNCHANGED, method 'doc-bytes-identical' (the re-split result is kept alongside)

CLI (one shard per adapter, used by the daily workflow matrix):
  python -m spine.engine --inputs data/inputs --adapter us_ecfr --out shards/us_ecfr
Exit 0 = all documents measured; 2 = at least one UNREACHABLE/UNSTABLE document.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import re

from . import adapters as A
from . import corpus as C
from . import inputs as I
from . import resplit as R
from .textx import decode, extract

EU_SIX = set(C.INSTRUMENTS)
_CELEX = re.compile(r"^[0-9]{5}[A-Z]{1,2}[0-9]{4}$")


def _celex_of(row: dict, reg: dict) -> str | None:
    m = re.match(r"^(3\d{4}[A-Z]{1,2}\d{4}):", row["provision_id"])
    if m:
        return m.group(1)
    oid = ((reg or {}).get("official_id") or "").replace("CELEX", "").strip()
    return oid if _CELEX.match(oid) else None


def plan(inp: dict, only: set[str] | None = None) -> list[dict]:
    docs: dict[tuple, dict] = {}
    for r in sorted(inp["provisions"], key=lambda r: (r["_wave"], r["_order"])):
        reg = inp["registry"].get(r["instrument_id"]) or {}
        ad = A.route(r)
        if only and ad.name not in only:
            continue
        s = r.get("source") or {}
        celex = _celex_of(r, reg)
        if ad.name == "eu_cellar" and celex in EU_SIX:
            key = (ad.name, r["instrument_id"], "celex:" + celex)     # EU-six: one OJ document per act
            url = "celex:" + celex
        else:
            url = A.source_url(r) or "none"
            key = (ad.name, r["instrument_id"], url)
        d = docs.setdefault(key, {"adapter": ad.name, "instrument_id": r["instrument_id"], "url": url,
                                  "celex": celex, "jurisdiction": I.jurisdiction(reg, r["provision_id"]),
                                  "frozen_document_sha256": s.get("document_sha256") or s.get("xhtml_sha256"),
                                  "rows": []})
        d["rows"].append(r)
    return list(docs.values())


def _lister_ids(ad, raw_text: str, text: str) -> dict:
    if not ad.insertion_lister:
        return {}
    return ad.insertion_lister(raw_text if ad.lister_input == "raw" else text)


def measure_doc(d: dict, gate: bool = True, fetch=None) -> dict:
    """Measure one source document. `fetch(adapter, url, ctx)` may be injected for tests."""
    ad = A.BY_NAME[d["adapter"]]
    rec = {k: d[k] for k in ("adapter", "instrument_id", "url", "celex", "jurisdiction", "frozen_document_sha256")}
    rec["provisions_frozen"] = len(d["rows"])
    if ad.name == "identifier_only":
        rec["gate"] = "NO_FETCH"
        return {"doc": rec, "provisions": {r["provision_id"]: {"class": "UNKNOWN", "method": "IDS_ONLY", "span_sha256": None}
                                           for r in d["rows"]}, "inserted": {}}
    ctx = {"celex": d["celex"]}
    do = fetch or (lambda a, u, c: a.fetch(u, c))
    try:
        f1 = do(ad, d["url"], ctx)
        t1 = ad.text(f1)
        m1 = R.measure(d["rows"], t1)
        if gate:
            f2 = do(ad, d["url"], ctx)
            if f2["sha256"] == f1["sha256"]:
                m2 = m1        # identical bytes, deterministic extraction: same hashes by construction
            else:
                t2 = ad.text(f2)
                m2 = R.measure(d["rows"], t2)
    except A.Unreachable as exc:
        rec.update(gate="UNREACHABLE", error=str(exc))
        return {"doc": rec, "provisions": {r["provision_id"]: {"class": "UNKNOWN", "method": "source-unreachable",
                                                               "span_sha256": None} for r in d["rows"]}, "inserted": {}}
    except Exception as exc:          # parse/extract failure: fail closed, but this is a defect, not drift
        rec.update(gate="ERROR", error=f"{type(exc).__name__}: {str(exc)[:200]}")
        return {"doc": rec, "provisions": {r["provision_id"]: {"class": "UNKNOWN", "method": "extract-error",
                                                               "span_sha256": None} for r in d["rows"]}, "inserted": {}}
    rec.update({"resolved_url": f1.get("resolved_url"), "format": f1.get("format"), "sha256_fetch1": f1["sha256"],
                "bytes": len(f1["bytes"])})
    for k in ("version_pinned", "version_current"):
        if k in f1:
            rec[k] = f1[k]
    if gate:
        rec["sha256_fetch2"] = f2["sha256"]
        rec["bytes_stable"] = f1["sha256"] == f2["sha256"]
        same = R.gate_key(m1) == R.gate_key(m2)
        rec["gate"] = "STABLE" if same else "UNSTABLE"
        if not same:
            g1, g2 = R.gate_key(m1), R.gate_key(m2)
            rec["unstable_provisions"] = sorted(k for k in g1 if g1[k] != g2.get(k))[:50]
            return {"doc": rec, "provisions": {r["provision_id"]: {"class": "UNKNOWN", "method": "gate-unstable",
                                                                   "span_sha256": None} for r in d["rows"]}, "inserted": {}}
    else:
        rec["gate"] = "SKIPPED"
    ident = bool(d["frozen_document_sha256"]) and f1["sha256"] == d["frozen_document_sha256"]
    rec["bytes_identical_to_frozen"] = ident
    if ident:
        for pid, m in m1.items():
            if m["class"] != "UNCHANGED":
                m["resplit_class"], m["resplit_method"] = m["class"], m.get("method")
                m["class"], m["method"] = "UNCHANGED", "doc-bytes-identical"
    # structural insertion check
    inserted = {}
    # Insertions are only measurable on routes that serve the CURRENT text. Pinned routes
    # (an OJ original, an enrolled bill, an effective-date version) cannot gain provisions;
    # EU insertions arrive through the consolidated-version diff instead.
    current_route = current_route_of(ad)
    if ad.insertion_lister and current_route and not ident:
        raw = decode(f1["bytes"]) if f1.get("format") == "markup" else t1
        now = _lister_ids(ad, raw, t1)
        frozen_nums = {str(r.get("number")) for r in d["rows"]}
        matched = frozen_nums & set(now)
        extra = sorted(set(now) - frozen_nums, key=lambda k: (len(k), k))
        rec["lister"] = {"ids_in_source": len(now), "frozen_matched": len(matched), "frozen": len(frozen_nums)}
        validated = frozen_nums and len(matched) / len(frozen_nums) >= 0.8
        if validated and len(extra) <= max(3, int(0.2 * len(frozen_nums))):
            inserted = {k: now[k] for k in extra}
            rec["lister"]["inserted"] = extra
        elif extra:
            rec["lister"]["unfrozen_in_source"] = len(extra)
            rec["lister"]["note"] = "partial freeze or lister not validated: extra ids are NOT reported as inserted"
    rec["classes"] = dict(collections.Counter(m["class"] for m in m1.values()))
    return {"doc": rec, "provisions": m1, "inserted": inserted, "_raw": f1 if d["celex"] else None}


def current_law(d: dict, res: dict, gate: bool = True) -> dict:
    """EU CELEX documents outside the EU-six: diff the OJ original against the latest
    consolidation (spine.fluid), per provision. Non-EU sources: current law = the route
    itself (inherent) or pinned; see adapter.latest_version."""
    from . import fluid as F
    raw = res.get("_raw")
    if not raw or d["celex"] in EU_SIX or not d["celex"]:
        return {}
    try:
        oj = C.parse_exact(decode(raw["bytes"]))
        cl = F.current_law(d["celex"], oj, gate=gate)
    except Exception as exc:
        return {"_source": {"gate": "ERROR", "error": f"{type(exc).__name__}: {str(exc)[:160]}"}}
    out = {"_source": {k: v for k, v in (cl.get("source") or {}).items() if k != "unstable_keys"} | {"consolidated": cl.get("consolidated")}}
    for k, v in cl["provisions"].items():
        num = k
        if k.startswith("-"):
            n = int(re.match(r"-(\d+)", k).group(1))
            roman = [r for r, i in C._ROMAN.items() if i == n]
            num = "annex-" + (roman[0] if roman else str(n)) + k[len(str(-n)):]
        out[num] = {"class": v["class"], "edits": v.get("edits"), "v3_sha256": v.get("v3_sha256"),
                    "v3_text": v.get("v3_text")}
    return out


def ad_of(d: dict):
    return A.BY_NAME[d["adapter"]]


def current_route_of(ad) -> bool:
    """True when the adapter's route serves the law as it applies today (so the class vs frozen
    is also the class vs current law)."""
    return ad.latest_version == "inherent" or ad.latest_version.startswith("resolved")


def run(inputs_dir: str, only: set[str] | None = None, gate: bool = True, fetch=None,
        consolidated: bool = True, log=print) -> dict:
    inp = I.load(inputs_dir)
    docs = plan(inp, only)
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    records, doc_recs = [], []
    for i, d in enumerate(docs):
        res = measure_doc(d, gate=gate, fetch=fetch)
        cur = current_law(d, res, gate=gate) if consolidated else {}
        doc = res["doc"]
        if cur.get("_source"):
            doc["current_law"] = cur["_source"]
        doc_recs.append(doc)
        if log:
            log(f"[{i + 1}/{len(docs)}] {d['adapter']:22} {d['instrument_id'][:40]:40} {doc['gate']:11} {doc.get('classes', '')}")
        reg = inp["registry"].get(d["instrument_id"]) or {}
        lic = I.licence_basis(reg.get("text_licence"))
        frozen_nums = {str(r.get("number")) for r in d["rows"]}
        for r in d["rows"]:
            m = res["provisions"][r["provision_id"]]
            c3 = cur.get(str(r.get("number"))) if cur else None
            if c3 and c3["class"] == "INSERTED":
                # the OJ element parser missed an element the frozen slice has (e.g. an annex with a
                # different id form): diff the frozen text against the consolidated text directly.
                if r.get("text") and c3.get("v3_text"):
                    cls, ed = C.change_class(r["text"], c3["v3_text"])
                    c3 = {**c3, "class": cls, "edits": ed}
                else:
                    c3 = {**c3, "class": "UNKNOWN"}
            records.append({
                "provision_id": r["provision_id"], "instrument_id": r["instrument_id"], "number": r.get("number"),
                "label": r.get("label"), "jurisdiction": d["jurisdiction"], "wave": r["_wave"],
                "adapter": d["adapter"], "source_url": d["url"], "resolved_url": doc.get("resolved_url"),
                "gate": doc["gate"], "bytes_identical_to_frozen": doc.get("bytes_identical_to_frozen"),
                "frozen_sha256": r.get("provision_sha256"), "change_vs_frozen": m["class"],
                "method": m.get("method"), "reproduced": bool(m.get("reproduced")),
                "current_sha256": m.get("current_sha256"), "edits": m.get("edits"),
                "resplit_class": m.get("resplit_class"), "resplit_method": m.get("resplit_method"),
                "current_law_class": ((c3 or {}).get("class") or "UNKNOWN") if cur.get("_source") else
                                     (m["class"] if current_route_of(ad_of(d)) else "PINNED_NOT_CHECKED"),
                "current_law_source": (cur.get("_source") or {}).get("consolidated") if cur else None,
                "licence_republish": lic["republish"], "licence_basis": lic["basis"],
                "_text": r.get("text"), "_current_text": m.get("current_text") or ((c3 or {}).get("v3_text") if c3 and c3.get("class") == "AMENDED" else None)})
        for k, txt in res["inserted"].items():
            records.append({
                "provision_id": f"{d['instrument_id'] if not (d['celex'] in EU_SIX) else d['celex']}:{k}",
                "instrument_id": d["instrument_id"], "number": k, "label": k, "jurisdiction": d["jurisdiction"],
                "wave": "(detected)", "adapter": d["adapter"], "source_url": d["url"], "resolved_url": doc.get("resolved_url"),
                "gate": doc["gate"], "bytes_identical_to_frozen": False, "frozen_sha256": None,
                "change_vs_frozen": "INSERTED", "method": "structural-lister", "reproduced": False,
                "current_sha256": C.provision_hash(txt) if txt else None, "edits": None,
                "resplit_class": None, "resplit_method": None, "current_law_class": None, "current_law_source": None,
                "licence_republish": lic["republish"], "licence_basis": lic["basis"], 
                "_text": None, "_current_text": txt or None})
        # inserted by consolidation (EU CELEX outside the six)
        for k, v in (cur or {}).items():
            if k != "_source" and v["class"] == "INSERTED" and k not in frozen_nums:
                records.append({
                    "provision_id": f"{d['instrument_id']}:{k}", "instrument_id": d["instrument_id"], "number": k,
                    "label": k, "jurisdiction": d["jurisdiction"], "wave": "(consolidation)", "adapter": d["adapter"],
                    "source_url": d["url"], "resolved_url": None, "gate": doc["gate"], "bytes_identical_to_frozen": None,
                    "frozen_sha256": None, "change_vs_frozen": "INSERTED", "method": "consolidated-version",
                    "reproduced": False, "current_sha256": v.get("v3_sha256"), "edits": v.get("edits"),
                    "resplit_class": None, "resplit_method": None, "current_law_class": "INSERTED",
                    "current_law_source": cur["_source"].get("consolidated"),
                    "licence_republish": lic["republish"], "licence_basis": lic["basis"], 
                    "_text": None, "_current_text": v.get("v3_text")})
    bad = [x for x in doc_recs if x["gate"] in ("UNREACHABLE", "UNSTABLE", "ERROR")]
    return {"generated_at": now, "inputs": inp["files"], "records": records, "documents": doc_recs,
            "conflicts": inp["conflicts"], "rejected": inp["rejected"], "registry": inp["registry"],
            "registry_conflicts": inp["registry_conflicts"], "exit_code": 2 if bad else 0,
            "adapters": [A.BY_NAME[n].describe() for n in sorted({d["adapter"] for d in docs})]}


def write_shard(res: dict, out: str) -> None:
    """Shard = CI artifact between matrix jobs (not committed). Current text travels only for
    changed provisions of instruments whose licence permits republication."""
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "provision_state.jsonl"), "w", encoding="utf-8") as f:
        for r in res["records"]:
            row = {k: v for k, v in r.items() if not k.startswith("_")}
            if r.get("_current_text") and r.get("licence_republish"):
                row["current_text"] = r["_current_text"]
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    with open(os.path.join(out, "adapters.json"), "w") as f:
        json.dump({"adapters": res["adapters"], "exit_code": res["exit_code"], "generated_at": res["generated_at"]}, f, indent=1)
    with open(os.path.join(out, "documents.jsonl"), "w", encoding="utf-8") as f:
        for d in res["documents"]:
            f.write(json.dumps(d, ensure_ascii=False, sort_keys=True) + "\n")


def load_shards(shards_dir: str, inp: dict, prev_state: str | None = None) -> dict:
    """Merge per-adapter shards. An adapter with no shard (its job failed: unreachable or
    unstable) keeps its previous records verbatim, flagged
    carried_forward (rows carry no timestamps: the run time is in report.json only); with no previous record its provisions are UNKNOWN 'shard-missing'."""
    expected = sorted({d["adapter"] for d in plan(inp)})
    records, documents, adapters, missing = [], [], [], []
    prev = {}
    if prev_state and os.path.exists(prev_state):
        with open(prev_state, encoding="utf-8") as f:
            for l in f:
                if l.strip():
                    r = json.loads(l)
                    prev[r["provision_id"]] = r
    for name in expected:
        d = os.path.join(shards_dir, name)
        if not os.path.exists(os.path.join(d, "provision_state.jsonl")):
            missing.append(name)
            for doc in plan(inp, {name}):
                for r in doc["rows"]:
                    p = prev.get(r["provision_id"])
                    if p and p.get("adapter") == name:
                        records.append({**p, "carried_forward": True})
                    else:
                        records.append({"provision_id": r["provision_id"], "instrument_id": r["instrument_id"],
                                        "number": r.get("number"), "label": r.get("label"),
                                        "jurisdiction": doc["jurisdiction"], "wave": r["_wave"], "adapter": name,
                                        "source_url": doc["url"], "gate": "SHARD_MISSING",
                                        "frozen_sha256": r.get("provision_sha256"), "change_vs_frozen": "UNKNOWN",
                                        "method": "shard-missing", "reproduced": False, "carried_forward": False})
            continue
        with open(os.path.join(d, "provision_state.jsonl"), encoding="utf-8") as f:
            records += [json.loads(l) for l in f if l.strip()]
        with open(os.path.join(d, "documents.jsonl"), encoding="utf-8") as f:
            documents += [json.loads(l) for l in f if l.strip()]
        if os.path.exists(os.path.join(d, "adapters.json")):
            adapters += json.load(open(os.path.join(d, "adapters.json")))["adapters"]
    for name in missing:
        documents.append({"adapter": name, "instrument_id": "*", "url": "*", "gate": "SHARD_MISSING",
                          "provisions_frozen": sum(len(x["rows"]) for x in plan(inp, {name}))})
        adapters.append(A.BY_NAME[name].describe())
    return {"records": records, "documents": documents, "adapters": adapters, "conflicts": inp["conflicts"],
            "rejected": inp["rejected"], "missing_shards": missing, "exit_code": 0, "inputs": inp["files"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", default="data/inputs")
    ap.add_argument("--adapter", action="append", help="limit to adapter name(s); repeatable")
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-gate", action="store_true")
    ap.add_argument("--list-adapters", action="store_true")
    a = ap.parse_args()
    if a.list_adapters:
        inp = I.load(a.inputs)
        print(json.dumps(sorted({d["adapter"] for d in plan(inp)})))
        return 0
    res = run(a.inputs, set(a.adapter) if a.adapter else None, gate=not a.no_gate)
    write_shard(res, a.out)
    print(json.dumps({"documents": len(res["documents"]), "provisions": len(res["records"]),
                      "gates": dict(collections.Counter(d["gate"] for d in res["documents"])),
                      "classes": dict(collections.Counter(r["change_vs_frozen"] for r in res["records"]))}))
    return res["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
