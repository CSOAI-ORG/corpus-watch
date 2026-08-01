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

# CELEX ids per instrument (the EU AI Act = 32024R1689). Provision-level fetch resolves the act, then the watcher
# hashes the whole normalised text (provision-level slicing is a later refinement; act-level drift is the coarse signal).
_CELEX = {"EU-AI-ACT": "32024R1689"}
def _is_law_text(b: bytes) -> bool:
    """Guard (CC lane finding): reject the JS/cookie-challenge page. Real law text has article/regulation/annex/whereas."""
    low = b[:4000].lower()
    if len(b) < 8000 and b"context" in low and b"article" not in low: return False  # challenge page
    return any(k in low for k in (b"article", b"regulation", b"annex", b"whereas"))
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
    # subset = the 113 AI Act provisions (start small, prove normalisation before scaling — N-sites §4.1)
    provisions = [f"Art.{n}" for n in range(1, 114)] if a.subset == "ai-act-113" else []
    events, unknown, unchanged = [], 0, 0
    for p in provisions:
        key = f"EU-AI-ACT::{p}"
        r = check_provision("EU-AI-ACT", p, state["hashes"].get(key), fetch_eurlex)
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
