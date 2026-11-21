"""spine.pipeline: one pass, end to end.

  CELLAR -> corpus (v1 reproduction + v2 full text) -> drift vs last state
         -> DRAFT obligation register -> ladder per provision
         -> door data (/provisions/<id>.json + index) -> daily report

Every count in the report is derived from files written in this pass; none is typed.
Run:  python -m spine.pipeline --out out/ [--frozen manifest.json] [--coverage coverage.json]
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import re
import urllib.request

from . import corpus as C
from . import obligations as O

FROZEN_URL = "https://councilof.ai/interop/frozen-provision-hashes.json"
COVERAGE_URL = "https://councilof.ai/mechanism/coverage.json"

# Ladder rungs, lowest to highest. A provision sits on the highest rung it has earned.
LADDER = [
    "HASH_ONLY",            # identifier + frozen hash, no bytes
    "SOURCE_RECOVERED",     # official bytes re-fetched; v1 hash reproduces
    "OBLIGATIONS_DRAFTED",  # DRAFT obligation rows with an evidence kind
    "CROSSWALK_ONLY",       # (from coverage.json) mapped in a crosswalk
    "RELATED_MEASURE",      # (from coverage.json) a GSPC axis measures something related
    "PREDICATE",            # (from coverage.json) a deterministic check exists
    "CAPSULE_BOUND",        # at least one signed capsule carries this provision_id
]


def _get_json(src: str) -> dict:
    if os.path.exists(src):
        return json.load(open(src))
    req = urllib.request.Request(src, headers={"User-Agent": C.UA})
    return json.load(urllib.request.urlopen(req, timeout=60))


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def diff_states(prev: dict | None, cur: dict) -> dict:
    """Four classes plus UNKNOWN. UNKNOWN is never folded into 'unchanged'."""
    if not prev:
        return {"baseline": True}
    b = {p["provision_id"]: p for p in prev["provisions"]}
    a = {p["provision_id"]: p for p in cur["provisions"]}
    cur = lambda p: p.get("v3_sha256") or p.get("v2_sha256")
    amended = sorted(k for k in set(a) & set(b) if cur(a[k]) and cur(b[k]) and cur(a[k]) != cur(b[k]))
    unknown = sorted(k for k, p in a.items() if p["state"] == "UNKNOWN")
    return {"baseline": False, "amended": amended, "added": sorted(set(a) - set(b)),
            "removed": sorted(set(b) - set(a)), "unknown": unknown,
            "unchanged": len(set(a) & set(b)) - len(amended) - len([k for k in unknown if k in b])}


def ladder_for(p: dict, kind: str, cov: dict[str, dict], bound: dict[str, int]) -> str:
    pid = p["provision_id"]
    rung = "HASH_ONLY"
    if p["state"] in ("REPRODUCED", "INSERTED_BY_AMENDMENT") or p.get("v2_sha256") or p.get("v3_sha256"):
        rung = "SOURCE_RECOVERED"
    if rung == "SOURCE_RECOVERED" and kind != "NONE":
        rung = "OBLIGATIONS_DRAFTED"
    status = cov.get(pid, {}).get("status")
    if status in LADDER and LADDER.index(status) > LADDER.index(rung):
        rung = status
    if bound.get(pid, 0) > 0:
        rung = "CAPSULE_BOUND"
    return rung


def _jsonl(path: str | None) -> list[dict]:
    if not path or not os.path.exists(path):
        return []
    return [json.loads(l) for l in open(path) if l.strip()]


def run(out: str, frozen_src: str = FROZEN_URL, coverage_src: str = COVERAGE_URL,
        fetch=None, bindings: dict[str, int] | None = None, consolidated: bool = True,
        gate: bool = True, extra_provisions: str | None = None, llm_register: str | None = None,
        versions: dict[str, list[str]] | None = None) -> dict:
    """One fluid pass. extra_provisions = JSONL of already-frozen non-EU-6 provisions
    (provision_id, instrument_id, text, provision_sha256, normaliser_version);
    llm_register = JSONL of agent-drafted obligation rows (provision_id, evidence_kind, ...)."""
    os.makedirs(out, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    frozen = _get_json(frozen_src)
    coverage = _get_json(coverage_src)
    if C.corpus_root(frozen["anchors"]) != frozen["corpus_root"]:
        raise RuntimeError("frozen manifest root does not recompute: refusing to compare against it")
    raw_fetch = fetch or C.fetch_xhtml
    memo: dict[str, str] = {}

    def mfetch(u):
        if u not in memo:
            memo[u] = raw_fetch(u)
        return memo[u]

    built = C.build(frozen["anchors"], fetch=mfetch)

    # ── v3: the law as it applies today ────────────────────────────────────
    from . import fluid as F
    current, amend_log = {}, []
    if consolidated:
        for celex in C.INSTRUMENTS:
            try:
                oj_m = next(s["manifestation"] for s in built["sources"] if s["celex"] == celex)
                oj_exact = C.parse_exact(mfetch(oj_m))
                vs = (versions or {}).get(celex)
                cl = F.current_law(celex, oj_exact, fetch=raw_fetch if gate else mfetch,
                                   versions=vs, gate=gate)
            except Exception as exc:     # fail closed: UNKNOWN, never UNCHANGED
                cl = {"celex": celex, "consolidated": None, "source": {"gate": "ERROR", "error": str(exc)},
                      "provisions": {}}
            current[celex] = cl
            amend_log.append({"celex": celex, "consolidated": cl["consolidated"], "gate": cl["source"].get("gate"),
                              "classes": dict(collections.Counter(v["class"] for v in cl["provisions"].values()))})
    for p in built["provisions"]:
        cl = current.get(p["celex"], {}).get("provisions", {}).get(str(p["number"]))
        p["v3_class"] = cl["class"] if cl else ("UNKNOWN" if consolidated else "NOT_CHECKED")
        p["v3_sha256"] = cl["v3_sha256"] if cl else None
        p["v3_edits"] = cl["edits"] if cl else None
        p["jurisdiction"] = "EU"
    # inserted provisions (e.g. 32024R1689:4a) become first-class provisions
    for celex, cl in current.items():
        for k, v in cl["provisions"].items():
            if v["class"] == "INSERTED":
                pid = f"{celex}:{k}"
                n = int(re.match(r"-?\d+", k).group(0))
                built["provisions"].append({
                    "provision_id": pid, "celex": celex, "instrument": C.INSTRUMENTS[celex]["name"],
                    "number": k, "kind": "annex" if k.startswith("-") else "article",
                    "label": C.label(celex, n) + (k[len(str(n)):] if not k.startswith("-") else ""),
                    "v1_sha256": "", "v2_sha256": "", "frozen_sha256": None, "state": "INSERTED_BY_AMENDMENT",
                    "truncated_in_v1": False, "chars_v2": 0, "v1_recipe": None, "nested_amendment": False,
                    "v3_class": "INSERTED", "v3_sha256": v["v3_sha256"], "v3_edits": v["edits"],
                    "jurisdiction": "EU"})
                built["texts"][pid] = {"v1": None, "v2": None, "v3": v["v3_text"]}
    for celex, cl in current.items():
        for k, v in cl["provisions"].items():
            pid = f"{celex}:{k}"
            if pid in built["texts"] and v.get("v3_text"):
                built["texts"][pid]["v3"] = v["v3_text"]

    # ── consolidate already-frozen provisions from other slices ─────────────
    extras = _jsonl(extra_provisions)
    extra_bad = 0
    for e in extras:
        ok = bool(e.get("text")) and C.provision_hash(e["text"]) == e.get("provision_sha256")
        extra_bad += 0 if ok else 1
        built["provisions"].append({
            "provision_id": e["provision_id"], "celex": e.get("instrument_id"), "instrument": e.get("instrument_id"),
            "number": e.get("number"), "kind": "article", "label": f'{e.get("instrument_id")} {e.get("label", "")}'.strip(),
            "v1_sha256": "", "v2_sha256": e.get("provision_sha256") if ok else "", "frozen_sha256": e.get("provision_sha256"),
            "state": "REPRODUCED" if ok else "UNKNOWN", "truncated_in_v1": False, "chars_v2": len(e.get("text") or ""),
            "v1_recipe": None, "nested_amendment": False, "v3_class": "NOT_CHECKED", "v3_sha256": None,
            "v3_edits": None, "jurisdiction": (e.get("instrument_id") or "?").split("-")[0]})
        if ok:
            built["texts"][e["provision_id"]] = {"v1": None, "v2": e["text"], "v3": None}

    # ── obligations: deterministic cut on the CURRENT text ──────────────────
    register, kinds = [], {}
    for p in built["provisions"]:
        t = built["texts"].get(p["provision_id"])
        text = t and (t.get("v3") or t.get("v2"))
        if not text:
            kinds[p["provision_id"]] = "UNKNOWN"
            continue
        rows = O.extract(p["provision_id"], text)
        for r in rows:
            r["text_version"] = "v3" if t.get("v3") else "v2"
        register.extend(rows)
        kinds[p["provision_id"]] = O.provision_kind(rows)

    # ── agent register: join, flag stale drafts, two-method agreement ───────
    llm = _jsonl(llm_register)
    cls_by = {p["provision_id"]: p.get("v3_class") for p in built["provisions"]}
    llm_k, det_k = collections.defaultdict(set), collections.defaultdict(set)
    stale = 0
    for r in llm:
        llm_k[r["provision_id"]].add(r.get("evidence_kind"))
        r["source_currency"] = "STALE_AMENDED" if cls_by.get(r["provision_id"]) == "AMENDED" else "CURRENT"
        stale += r["source_currency"] == "STALE_AMENDED"
    for r in register:
        det_k[r["provision_id"]].add(r["evidence_kind"])
    agreement = {}
    if llm:
        for k in ("OBSERVED", "SUBMITTED"):
            ids = set(llm_k)
            agreement[k] = {"both": sum(k in det_k[i] and k in llm_k[i] for i in ids),
                            "deterministic_only": sum(k in det_k[i] and k not in llm_k[i] for i in ids),
                            "agent_only": sum(k not in det_k[i] and k in llm_k[i] for i in ids)}
        shortlist = sorted(i for i in llm_k if "OBSERVED" in det_k[i] and "OBSERVED" in llm_k[i])
        with open(os.path.join(out, "obligations_agent_joined.jsonl"), "w") as f:
            for r in llm:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    else:
        shortlist = []

    cov = {r["provision_id"]: r for r in coverage.get("provisions_touched", [])}
    bound = bindings or {}
    for p in built["provisions"]:
        p["evidence_kind"] = kinds[p["provision_id"]]
        p["ladder"] = ladder_for(p, kinds[p["provision_id"]], cov, bound)
        c = cov.get(p["provision_id"], {})
        p["related_axes"] = c.get("related_axes", [])
        p["predicates"] = c.get("predicates", [])
        p["capsules_bound"] = bound.get(p["provision_id"], 0)

    prev_path = os.path.join(out, "state.json")
    prev = json.load(open(prev_path)) if os.path.exists(prev_path) else None
    state = {"schema": "csoai.provision-spine.state/0.1", "generated_at": now,
             "normaliser_version": C.NORMALISER_VERSION, "obligation_method": O.METHOD_VERSION,
             "frozen_root": frozen["corpus_root"], "root_v1": built["root_v1"], "root_v2": built["root_v2"],
             "root_v1_matches_frozen": built["root_v1"] == frozen["corpus_root"],
             "sources": built["sources"], "unknown_instruments": built["unknown_instruments"],
             "provisions": built["provisions"]}
    drift = diff_states(prev, state)

    # files
    with open(os.path.join(out, "corpus_current.jsonl"), "w") as f:
        for p in built["provisions"]:
            t = built["texts"].get(p["provision_id"])
            if t and (t.get("v3") or t.get("v2")):
                f.write(json.dumps({"provision_id": p["provision_id"], "label": p["label"],
                                    "jurisdiction": p.get("jurisdiction"), "text_version": "v3" if t.get("v3") else "v2",
                                    "change_since_oj": p.get("v3_class"),
                                    "sha256": p.get("v3_sha256") or p["v2_sha256"],
                                    "text": t.get("v3") or t.get("v2")}, ensure_ascii=False) + "\n")
    with open(os.path.join(out, "corpus_v2.jsonl"), "w") as f:
        for p in built["provisions"]:
            t = built["texts"].get(p["provision_id"])
            if t and t.get("v2") and p.get("jurisdiction") == "EU":
                f.write(json.dumps({"provision_id": p["provision_id"], "label": p["label"],
                                    "sha256_v2": p["v2_sha256"], "text": t["v2"]}, ensure_ascii=False) + "\n")
    with open(os.path.join(out, "corpus_v1_reproduction.jsonl"), "w") as f:
        for p in built["provisions"]:
            t = built["texts"].get(p["provision_id"])
            if t and t.get("v1"):
                f.write(json.dumps({"provision_id": p["provision_id"], "frozen_sha256": p["frozen_sha256"],
                                    "sha256_v1": p["v1_sha256"], "recipe": p["v1_recipe"],
                                    "state": p["state"], "text": t["v1"]}, ensure_ascii=False) + "\n")
    with open(os.path.join(out, "obligations.jsonl"), "w") as f:
        for r in register:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    door = os.path.join(out, "provisions")
    os.makedirs(door, exist_ok=True)
    obl_by = collections.defaultdict(list)
    for r in register:
        obl_by[r["provision_id"]].append(r)
    index = []
    for p in built["provisions"]:
        rec = {"schema": "csoai.provision/0.1", "provision_id": p["provision_id"], "label": p["label"],
               "instrument": p["instrument"], "ladder": p["ladder"], "evidence_kind": p["evidence_kind"],
               "frozen_sha256": p["frozen_sha256"], "sha256_v1": p["v1_sha256"], "sha256_v2": p["v2_sha256"],
               "source_state": p["state"], "truncated_in_v1": p["truncated_in_v1"],
               "jurisdiction": p.get("jurisdiction"), "change_since_oj": p.get("v3_class"),
               "change_edits": p.get("v3_edits"), "sha256_current": p.get("v3_sha256") or p["v2_sha256"],
               "agent_register_kinds": sorted(k for k in llm_k.get(p["provision_id"], set()) if k),
               "predicate_shortlist": p["provision_id"] in shortlist,
               "related_axes": p["related_axes"], "predicates": p["predicates"],
               "capsules_bound": p["capsules_bound"],
               "obligations": [{k: r[k] for k in ("obligation_id", "paragraph", "addressee", "modality",
                                                  "evidence_kind", "rule", "status", "text")}
                               for r in obl_by[p["provision_id"]]],
               "door": f"/api/evidence-bundle?provision={p['provision_id']}",
               "disclaimer": "Obligation rows are DRAFT machine cuts (counsel_confirmed=false). Measurement, not certification."}
        fn = p["provision_id"].replace(":", "_") + ".json"
        json.dump(rec, open(os.path.join(door, fn), "w"), ensure_ascii=False, indent=1)
        index.append({k: rec[k] for k in ("provision_id", "label", "jurisdiction", "ladder", "evidence_kind",
                                          "source_state", "change_since_oj")})
    json.dump({"schema": "csoai.provision-index/0.1", "generated_at": now, "provisions": index},
              open(os.path.join(door, "index.json"), "w"), indent=1)

    counts = {
        "provisions": len(built["provisions"]),
        "source_state": dict(collections.Counter(p["state"] for p in built["provisions"])),
        "ladder": {k: sum(p["ladder"] == k for p in built["provisions"]) for k in LADDER},
        "evidence_kind_by_provision": dict(collections.Counter(kinds.values())),
        "obligation_rows": len(register),
        "obligation_rows_by_kind": dict(collections.Counter(r["evidence_kind"] for r in register)),
        "truncated_in_v1": sum(p["truncated_in_v1"] for p in built["provisions"]),
        "capsules_bound_provisions": sum(1 for v in bound.values() if v),
        "by_jurisdiction": dict(collections.Counter(p.get("jurisdiction") for p in built["provisions"])),
        "change_since_oj": dict(collections.Counter(p.get("v3_class") for p in built["provisions"])),
        "extra_provisions_ingested": len(extras), "extra_provisions_hash_failed": extra_bad,
        "agent_register_rows": len(llm), "agent_rows_stale_amended": stale,
        "two_method_agreement": agreement, "predicate_shortlist": shortlist,
    }
    state["amendments"] = amend_log
    state["counts"] = counts
    state["drift"] = drift
    json.dump(state, open(prev_path, "w"), indent=1)
    report = {"generated_at": now, "root_v1_matches_frozen": state["root_v1_matches_frozen"],
              "root_v2": built["root_v2"], "counts": counts, "drift": drift,
              "unknown_instruments": built["unknown_instruments"], "amendments": amend_log,
              "amended_provisions": sorted(p["provision_id"] for p in built["provisions"] if p.get("v3_class") == "AMENDED"),
              "inserted_provisions": sorted(p["provision_id"] for p in built["provisions"] if p.get("v3_class") == "INSERTED"),
              "files_sha256": {fn: hashlib.sha256(open(os.path.join(out, fn), "rb").read()).hexdigest()
                               for fn in ("corpus_current.jsonl", "corpus_v2.jsonl", "corpus_v1_reproduction.jsonl",
                                          "obligations.jsonl")}}
    json.dump(report, open(os.path.join(out, "report.json"), "w"), indent=1)
    open(os.path.join(out, "report.md"), "w").write(render_md(report))
    return report


def render_md(r: dict) -> str:
    c = r["counts"]
    L = [f"# Provision spine: daily fluid pass {r['generated_at']}", "",
         "Every number below is derived from files written in this pass. Obligation rows are DRAFT "
         "machine cuts (counsel_confirmed=false). Measurement, not certification.", "",
         f"- Frozen 417 still reproduce (root matches): **{r['root_v1_matches_frozen']}**",
         f"- Provisions in the engine: **{c['provisions']}** by jurisdiction {c['by_jurisdiction']}",
         f"- Ladder: {c['ladder']}",
         f"- Change since OJ original (EU six): {c['change_since_oj']}",
         f"- Agent-register rows now on amended text (re-draft needed): **{c['agent_rows_stale_amended']}** of {c['agent_register_rows']}",
         f"- Two-method OBSERVED shortlist (next predicates): {', '.join(c['predicate_shortlist']) or 'none'}",
         "", "## Sources and determinism gate", "", "| CELEX | latest consolidated | gate | classes |", "|---|---|---|---|"]
    for a in r["amendments"]:
        L.append(f"| {a['celex']} | {a['consolidated']} | {a['gate']} | {a['classes']} |")
    if r["unknown_instruments"]:
        L += ["", "## UNKNOWN (fail-closed, not 'unchanged')", ""] + [f"- {u['celex']}: {u['error']}" for u in r["unknown_instruments"]]
    d = r["drift"]
    L += ["", "## Drift since last pass", ""]
    if d.get("baseline"):
        L.append("Baseline pass: no previous state.")
    else:
        for k in ("amended", "added", "removed", "unknown"):
            L.append(f"- {k}: {len(d[k])} {d[k][:25]}")
        L.append(f"- unchanged: {d['unchanged']}")
    L += ["", f"Inserted by amendment: {', '.join(r['inserted_provisions'])}", "",
          f"Amended since OJ ({len(r['amended_provisions'])}): {', '.join(r['amended_provisions'])}", ""]
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out")
    ap.add_argument("--frozen", default=FROZEN_URL)
    ap.add_argument("--coverage", default=COVERAGE_URL)
    ap.add_argument("--extra-provisions", default=None)
    ap.add_argument("--agent-register", default=None)
    ap.add_argument("--no-consolidated", action="store_true")
    ap.add_argument("--no-gate", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        fails = O.selftest()
        print("\n".join(fails) or "selftest ok")
        return 1 if fails else 0
    r = run(a.out, a.frozen, a.coverage, consolidated=not a.no_consolidated, gate=not a.no_gate,
            extra_provisions=a.extra_provisions, llm_register=a.agent_register)
    print(json.dumps(r["counts"], indent=1))
    # Exit 2 when any source is UNKNOWN or unstable, so CI never reports 'no drift' on a failed fetch.
    bad_gate = [x for x in r["amendments"] if x["gate"] in ("UNSTABLE", "ERROR")]
    return 2 if (r["unknown_instruments"] or bad_gate) else 0


if __name__ == "__main__":
    raise SystemExit(main())
