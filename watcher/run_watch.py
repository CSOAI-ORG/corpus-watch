#!/usr/bin/env python3
"""run_watch.py — GH Actions entrypoint for the corpus watcher (N-sites stage ①).
Contract (N-sites §2): pull corpus_state from Git → run watcher deterministic → push drift events to Git. FAIL CLOSED.
Real EUR-Lex/legislation.gov.uk fetch is wired but the workflow runs even if the authority is unreachable (records UNKNOWN)."""
import argparse, json, os, sys, hashlib, urllib.request
# import the verified watcher (normaliser v2, fail-closed) — same module, no reimplementation
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from sov_corpus_watcher import check_provision, NORMALISER_VERSION
except Exception:
    # in the deployed repo the watcher sits alongside; fall back to local copy
    from run_watch_lib import check_provision, NORMALISER_VERSION  # type: ignore

# CELEX ids per instrument (the EU AI Act = 32024R1689; Cyber Resilience Act proposal = 32024R2847).
# Provision-level fetch resolves the act, then the watcher hashes the whole normalised text
# (provision-level slicing is a later refinement; act-level drift is the coarse signal).
_CELEX = {"EU-AI-ACT": "32024R1689", "EU-CRA": "32024R2847"}
def fetch_leguk(instrument, provision):
    """legislation.gov.uk per-provision /data.xml. Returns None on any failure -> UNKNOWN (fail-closed)."""
    import urllib.request, urllib.error
    tmpl = _LEGUK.get(instrument)
    if not tmpl: return None
    num = provision.split(".")[-1]
    url = "https://www.legislation.gov.uk/" + tmpl.format(p=num)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "csoai-corpus-watch/1.0"})
        body = urllib.request.urlopen(req, timeout=30).read()
    except Exception:
        return None                      # fail-closed
    if len(body) < 200 or b"<html" in body[:200].lower(): return None  # error page, not statute XML
    return body.decode("utf-8", "replace")

def _is_law_text(b: bytes) -> bool:
    """Guard: reject the JS/cookie-challenge page. Real EU law text has many 'Article N' / 'Regulation N' / 'Annex' markers
    scattered through the body; the JS challenge page does not. The CRA proposal puts the table of contents in the first
    ~4kB and the article bodies later — counting markers across the WHOLE body catches it without false-rejecting a real
    instrument. Threshold 5 is conservative for any EU act (smallest AI-Act-adjacent instrument has dozens of articles)."""
    import re as _re
    full = b.decode("utf-8", "replace")
    count = sum(len(_re.findall(pat, full)) for pat in (r"\bArticle\s+\d+", r"\bRegulation\s+\d+", r"\bAnnex\b"))
    return count >= 5
# legislation.gov.uk instruments — byte-stable /data.xml, provision-level (verified live 2026-07-29:
# repeated fetches byte-identical, no per-request nonce — the property EUR-Lex HTML lacks).
# path templates: {p} = provision number
_LEGUK = {
    "UK-GDPR":   "eur/2016/679/article/{p}/data.xml",      # UK GDPR (retained EU 2016/679)
    "DPA-2018":  "ukpga/2018/12/section/{p}/data.xml",     # Data Protection Act 2018
    "NIS2-UK":   "uksi/2018/506/regulation/{p}/data.xml",  # NIS Regulations 2018 (UK NIS1)
}
def fetch_eurlex(instrument, provision):
    """VERIFIED CELLAR content-negotiation path (FOREST_82): publications.europa.eu XHTML manifestation returns REAL
    law text (no JS challenge, unlike the eur-lex.europa.eu HTML page). Returns None on any failure/challenge -> UNKNOWN."""
    import urllib.request, urllib.error
    celex = _CELEX.get(instrument)
    if not celex: return None
    url = f"http://publications.europa.eu/resource/celex/{celex}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/xhtml+xml", "Accept-Language": "eng",
                                                   "User-Agent": "python-urllib"})
        body = urllib.request.urlopen(req, timeout=30).read()
    except Exception:
        return None                      # fail-closed
    if not _is_law_text(body): return None   # challenge/garbage -> UNKNOWN, never false drift
    return body.decode("utf-8", "replace")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--authority", default="eur-lex")
    ap.add_argument("--subset", default="ai-act-113")
    ap.add_argument("--out", default="drift_events.jsonl")
    a = ap.parse_args()
    state_path = "corpus_state.json"
    state = json.load(open(state_path)) if os.path.exists(state_path) else {"normaliser": NORMALISER_VERSION, "hashes": {}}
    # subsets: instrument, fetch_fn, provision list. Start small, prove normalisation before scaling (N-sites §4.1).
    SUBSETS = {
        "ai-act-113":   ("EU-AI-ACT", fetch_eurlex, [f"Art.{n}" for n in range(1, 114)]),
        "cra-articles": ("EU-CRA",    fetch_eurlex, [f"Art.{n}" for n in range(1, 72)]),   # CRA: 71 articles (provision-level slicing = 1 fetch per Art., coarse hash per Art.)
        "uk-gdpr-core": ("UK-GDPR",   fetch_leguk,  [f"Art.{n}" for n in (5, 6, 13, 25, 32, 33, 35)]),
        "dpa-2018-s123":("DPA-2018",  fetch_leguk,  ["s.1", "s.2", "s.3"]),
        "nis-regs-core":("NIS2-UK",   fetch_leguk,  [f"reg.{n}" for n in (1, 10, 11, 14)]),
    }
    if a.subset not in SUBSETS:
        sys.exit(f"unknown subset: {a.subset} (have: {', '.join(SUBSETS)})")
    instrument, fetch_fn, provisions = SUBSETS[a.subset]
    events, unknown, unchanged = [], 0, 0
    for p in provisions:
        key = f"{instrument}::{p}"
        r = check_provision(instrument, p, state["hashes"].get(key), fetch_fn)
        if r["status"] == "DRIFT":
            events.append(r); state["hashes"][key] = r["hash_after"]
        elif r["status"] == "UNKNOWN":
            unknown += 1
        else:
            unchanged += 1
            state["hashes"][key] = r["hash_after"]  # seed/update baseline — else first run never seeds and drift can never fire
    json.dump(state, open(state_path, "w"), indent=1)
    with open(a.out, "a") as f:
        for e in events: f.write(json.dumps(e) + "\n")
    # summary to the Actions log (fail-closed accounting is explicit, not hidden)
    print(json.dumps({"provisions": len(provisions), "drift": len(events), "unknown": unknown,
                      "unchanged": unchanged, "normaliser": NORMALISER_VERSION}))
    # fail-closed: if EVERYTHING was UNKNOWN, exit non-zero so the run is visibly not "all clear"
    if provisions and unknown == len(provisions):
        print("FAIL-CLOSED: all provisions UNKNOWN (authority unreachable) — NOT reporting 'no drift'", file=sys.stderr)
        sys.exit(2)

if __name__ == "__main__":
    main()
