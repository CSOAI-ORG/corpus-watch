"""spine.inputs: wave files in, one registry + one provision set out. No code change per wave.

Layout (any number of waves, any names):
  data/inputs/registry_<wave>.jsonl     schema v2 registry rows (instrument_id, jurisdiction,
                                         freeze_mode, text_licence, official_id, ...)
  data/inputs/provisions_<wave>.jsonl   schema v2 provision rows (provision_id, instrument_id,
                                         number, label, text | null, provision_sha256,
                                         normaliser_version, source{url|kind|manifestation,...})
Rules:
  - a provision row must carry normaliser_version 1.0.0 (other versions are rejected, listed);
  - when two waves carry the same provision_id with different hashes, both are kept out and
    the conflict is reported (never silently last-writer-wins);
  - a row with text must re-hash to its provision_sha256 or it is rejected (listed);
  - rows without text (licence-withheld or IDS_ONLY) are kept as hash-only rows.
"""
from __future__ import annotations

import collections
import glob
import json
import os
import re

from . import corpus as C

# Republication basis, decided per instrument from its registry text_licence. Order matters:
# an explicit 'not verified' / 'unknown' always wins (withhold), whatever else the string says.
LICENCE_RULES = [
    ("WITHHOLD", r"not verified|not re-read|unknown|not separately verified|not stated|all rights reserved|proprietary|paywall", None),
    ("PERMIT", r"2011/833", "EU reuse Decision 2011/833/EU"),
    ("PERMIT", r"open government licence", "Open Government Licence v3.0"),
    ("PERMIT", r"17 u\.s\.c\. 105|us public domain", "US federal government work, 17 U.S.C. 105"),
    ("PERMIT", r"edicts doctrine|georgia v\. public\.resource", "US government edicts doctrine (Georgia v. Public.Resource.Org, 2020)"),
    ("PERMIT", r"cc-by-4\.0|cc by 4\.0", "CC-BY-4.0 (attribution in README)"),
    ("PERMIT", r"japan copyright act art\. 13", "Japan Copyright Act art. 13 (statutes not protected)"),
    ("PERMIT", r"korea copyright act art\. 7", "Korea Copyright Act art. 7 (statutes not protected)"),
    ("PERMIT", r"prc copyright law art\. 5", "PRC Copyright Law art. 5 (laws and official documents not protected)"),
    ("PERMIT", r"taiwan copyright act art\. 9", "Taiwan Copyright Act art. 9 (laws not protected)"),
    ("PERMIT", r"§ 5 urhg|amtliches werk", "Germany UrhG § 5 (official works not protected)"),
    ("PERMIT", r"ophavsretsloven § 9", "Denmark Ophavsretsloven § 9 (statutes not protected)"),
    ("PERMIT", r"tekijänoikeuslaki 9 §", "Finland Tekijänoikeuslaki 9 § (statutes not protected)"),
    ("PERMIT", r"art\. 13 lpi", "Spain LPI art. 13 (official acts not protected) + BOE reuse terms (attribution)"),
    ("PERMIT", r"urg art\. 5", "Switzerland URG Art. 5 (enactments not protected)"),
    ("PERMIT", r"szjt\. 1\. § \(4\)", "Hungary Szjt. 1. § (4) (legislation not protected)"),
    ("PERMIT", r"lei 9\.610/1998 art\. 8", "Brazil Lei 9.610/1998 art. 8 IV (official texts not protected)"),
    ("PERMIT", r"edpb copyright notice: reuse authorised", "EDPB reuse notice (source acknowledgement, no distortion)"),
    ("PERMIT", r"reproduction of federal law order", "Canada Reproduction of Federal Law Order SI/97-5 (accuracy + non-endorsement conditions)"),
]


def licence_basis(text_licence: str | None) -> dict:
    t = (text_licence or "").lower()
    for decision, pat, basis in LICENCE_RULES:
        if re.search(pat, t):
            return {"republish": decision == "PERMIT", "basis": basis or f"withheld: '{text_licence}'"}
    return {"republish": False, "basis": f"withheld: no recognised basis in '{text_licence}'"}


def _jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def load(inputs_dir: str) -> dict:
    reg_files = sorted(glob.glob(os.path.join(inputs_dir, "registry_*.jsonl")))
    prov_files = sorted(glob.glob(os.path.join(inputs_dir, "provisions_*.jsonl")))
    registry, reg_conflicts = {}, []
    for f in reg_files:
        for r in _jsonl(f):
            iid = r["instrument_id"]
            if iid in registry and registry[iid].get("instrument_root") != r.get("instrument_root") \
                    and registry[iid].get("freeze_mode") == r.get("freeze_mode") == "FULL_TEXT":
                reg_conflicts.append({"instrument_id": iid, "files": [registry[iid]["_wave"], os.path.basename(f)]})
            # richer row wins only if the earlier one was not frozen
            if iid not in registry or registry[iid].get("freeze_mode") != "FULL_TEXT":
                registry[iid] = {**r, "_wave": os.path.basename(f)}
    seen: dict[str, dict] = {}
    conflicts, rejected = [], []
    for f in prov_files:
        wave = os.path.basename(f)
        for order, r in enumerate(_jsonl(f)):
            pid = r["provision_id"]
            if r.get("normaliser_version", "1.0.0") != C.NORMALISER_VERSION:
                rejected.append({"provision_id": pid, "wave": wave, "reason": "normaliser_version"})
                continue
            if r.get("text") and C.provision_hash(r["text"]) != r.get("provision_sha256"):
                rejected.append({"provision_id": pid, "wave": wave, "reason": "text does not re-hash"})
                continue
            r = {**r, "_wave": wave, "_order": order}
            if pid in seen:
                if seen[pid].get("provision_sha256") != r.get("provision_sha256"):
                    conflicts.append({"provision_id": pid, "waves": [seen[pid]["_wave"], wave]})
                    seen[pid]["_conflict"] = True
                elif not seen[pid].get("text") and r.get("text"):
                    seen[pid] = r
                continue
            seen[pid] = r
    provisions = [r for r in seen.values() if not r.get("_conflict")]
    for p in provisions:
        if p["instrument_id"] not in registry:
            registry[p["instrument_id"]] = {"instrument_id": p["instrument_id"], "jurisdiction": p["instrument_id"].split("-")[0],
                                            "freeze_mode": "FULL_TEXT" if p.get("text") else "IDS_ONLY",
                                            "text_licence": None, "_wave": "(implicit)"}
    return {"registry": registry, "provisions": provisions, "conflicts": conflicts,
            "registry_conflicts": reg_conflicts, "rejected": rejected,
            "files": [os.path.basename(f) for f in reg_files + prov_files]}


def jurisdiction(registry_row: dict | None, provision_id: str) -> str:
    if registry_row and registry_row.get("jurisdiction"):
        return registry_row["jurisdiction"]
    return "EU" if re.match(r"^3\d{4}[A-Z]", provision_id) else provision_id.split("-")[0]


def split_for_publication(provisions: list[dict], registry: dict) -> tuple[list[dict], dict]:
    """Rows safe to commit: text kept only where the instrument's licence permits republication."""
    out, basis = [], {}
    for p in provisions:
        iid = p["instrument_id"]
        if iid not in basis:
            basis[iid] = licence_basis((registry.get(iid) or {}).get("text_licence"))
        q = {k: v for k, v in p.items() if not k.startswith("_")}
        if q.get("text") and not basis[iid]["republish"]:
            from .resplit import hashonly_recipe
            q["recipe_hashonly"] = hashonly_recipe(q["text"])
            q["text"] = None
            q["text_withheld"] = basis[iid]["basis"]
        out.append(q)
    return out, basis


def counts(provisions, registry):
    c = collections.Counter(jurisdiction(registry.get(p["instrument_id"]), p["provision_id"]) for p in provisions)
    return dict(sorted(c.items()))
