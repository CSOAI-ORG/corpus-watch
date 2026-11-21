"""spine.fluid: v3 = the law as it applies today, plus the determinism gate.

v1 frozen OJ original as hashed on 2026-08-12 (legacy parser, truncations kept).
v2 OJ original, exact element boundaries.
v3 latest CELLAR consolidated version (0YYYYTNNNN-YYYYMMDD), exact boundaries.
   Inserted articles (e.g. AI Act 4a, 60a, 75a-75d from Reg (EU) 2026/1744)
   become new provisions; deleted ones are kept with change class DELETED.

Determinism gate: an instrument's source is fetched twice. If the two fetches
yield different provision hashes, the instrument is UNSTABLE and every
provision in it is UNKNOWN for this run. This is the guard the old
corpus-watch lacked (its 319 UK drift events flip A->B->A).
"""
from __future__ import annotations

import hashlib

from . import corpus as C


def latest_consolidated(celex: str, versions=None) -> str | None:
    vs = versions if versions is not None else C.consolidated_versions(celex)
    return vs[-1] if vs else None


def stable_parse(manifestation: str, fetch=C.fetch_xhtml, gate: bool = True) -> tuple[dict[str, str], dict]:
    a = fetch(manifestation)
    pa = C.parse_exact(a)
    rec = {"manifestation": manifestation, "xhtml_sha256": hashlib.sha256(a.encode()).hexdigest(),
           "elements": len(pa), "gate": "SKIPPED"}
    if gate:
        b = fetch(manifestation)
        pb = C.parse_exact(b)
        ha = {k: C.provision_hash(v) for k, v in pa.items()}
        hb = {k: C.provision_hash(v) for k, v in pb.items()}
        rec["gate"] = "STABLE" if ha == hb else "UNSTABLE"
        if ha != hb:
            rec["unstable_keys"] = sorted(set(k for k in set(ha) | set(hb) if ha.get(k) != hb.get(k)))[:50]
    return pa, rec


def current_law(celex: str, oj_exact: dict[str, str], fetch=C.fetch_xhtml, versions=None,
                gate: bool = True) -> dict:
    """Diff the OJ original against the latest consolidated text, provision by provision."""
    cons = latest_consolidated(celex, versions)
    out = {"celex": celex, "consolidated": cons, "provisions": {}, "source": None}
    if cons is None:
        cur, rec = oj_exact, {"gate": "OJ_ONLY"}
    else:
        try:
            w = C.cellar_work(cons)
        except LookupError:
            # CELLAR holds this consolidation in other formats only: v3 not measurable today.
            out["source"] = {"gate": "NO_XHTML", "consolidated_celex": cons}
            for k in oj_exact:
                out["provisions"][k] = {"class": "UNKNOWN", "edits": None, "v3_sha256": None}
            return out
        cur, rec = stable_parse(w["manifestation"], fetch=fetch, gate=gate)
        rec.update({"consolidated_celex": cons, "work": w["work"]})
    out["source"] = rec
    if rec.get("gate") == "UNSTABLE":
        for k in oj_exact:
            out["provisions"][k] = {"class": "UNKNOWN", "edits": None, "v3_sha256": None}
        return out
    for k in sorted(set(oj_exact) | set(cur), key=C.sort_key):
        cls, edits = C.change_class(oj_exact.get(k), cur.get(k))
        out["provisions"][k] = {"class": cls, "edits": edits,
                                "v3_sha256": C.provision_hash(cur[k]) if k in cur else None,
                                "v3_text": cur.get(k)}
    return out
