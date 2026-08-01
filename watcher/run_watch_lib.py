#!/usr/bin/env python3
"""sov_corpus_watcher.py — the actual NEW mechanism for the drift product.
Polls the authority, re-hashes each provision, emits drift_event on change. Two guards decide if it works (drift-spec §4.1):
  1. NORMALISATION IS THE WHOLE GAME — freeze + version the normaliser, hash the NORMALISER into the record. A
     normaliser change is itself a drift event. (Else you get false drift on every poll from whitespace/boilerplate.)
  2. FAIL CLOSED — if the authority is unreachable, record UNKNOWN, NEVER "unchanged". A watcher that says "no drift"
     when it couldn't fetch is the health-check bug again — a verdict about the law when the fact was about the request. [Law 2]
"""
import hashlib, re, json

NORMALISER_VERSION = "norm-v2"
def normalise(text: str) -> str:
    """FROZEN v2 (v1 had a line-wrap false-drift bug). Strip consolidated-text boilerplate + collapse whitespace deterministically."""
    t = text
    t = re.sub(r'\r\n?', '\n', t)                          # unify line endings
    t = re.sub(r'^\s*(?:\u2500+|-{3,}|_{3,})\s*$', '', t, flags=re.M)  # rule lines
    t = re.sub(r'\[\s*\d+\s*\]', '', t)                    # footnote markers [12]
    t = re.sub(r'^\s*(?:OJ L.*|ELI:.*|Consolidated text:.*)$', '', t, flags=re.M|re.I)  # OJ/ELI boilerplate
    t = re.sub(r'\s+', ' ', t)                             # collapse ALL whitespace incl newlines — line-wrapping is cosmetic, must NOT drift
    return t.strip().lower()

def norm_hash(text: str):
    n = normalise(text)
    # hash the normaliser version INTO the record so a normaliser change registers as drift
    return hashlib.sha256((NORMALISER_VERSION + "\x00" + n).encode()).hexdigest()

def check_provision(instrument, provision, stored_hash, fetch_fn):
    """Returns a status dict. FAIL-CLOSED: fetch failure -> UNKNOWN, never 'unchanged'."""
    try:
        text = fetch_fn(instrument, provision)   # the real one hits EUR-Lex CELLAR / legislation.gov.uk
        if text is None: raise RuntimeError("empty")
    except Exception as e:
        return {"instrument": instrument, "provision": provision, "status": "UNKNOWN",
                "reason": f"fetch_failed: {type(e).__name__}", "normaliser": NORMALISER_VERSION}  # NOT 'unchanged'
    h = norm_hash(text)
    changed = (stored_hash is not None and h != stored_hash)
    return {"instrument": instrument, "provision": provision,
            "status": "DRIFT" if changed else "unchanged", "hash_after": h,
            "hash_before": stored_hash, "normaliser": NORMALISER_VERSION}

if __name__ == "__main__":
    # TEST 1 — normaliser stability: cosmetic reformatting must NOT produce false drift
    raw1 = "Art 50(2)\n\n[12] Providers  shall   ensure\r\nthat outputs are marked.\nOJ L 1689/2024\n----"
    raw2 = "Art 50(2)\n[12]  Providers shall ensure that outputs are marked.\n\nELI: reg/2024/1689"  # cosmetic diff only
    h1, h2 = norm_hash(raw1), norm_hash(raw2)
    print(f"normaliser stability (cosmetic reformat): {'PASS (same hash, no false drift)' if h1==h2 else 'FAIL — false drift'}")
    # TEST 2 — real substantive change DOES drift
    raw3 = "Art 50(2)\nProviders shall ensure that outputs are marked AND watermarked."  # real amendment
    print(f"real amendment detected: {'PASS (drift)' if norm_hash(raw3)!=h1 else 'FAIL — missed'}")
    # TEST 3 — fail-closed
    r = check_provision("EU-AI-ACT","Art.50(2)","h_old", lambda i,p:(_ for _ in ()).throw(ConnectionError("proxy 403")))
    print(f"fail-closed on unreachable authority: {'PASS ('+r['status']+', not unchanged)' if r['status']=='UNKNOWN' else 'FAIL'}")
    # TEST 4 — normaliser version bump = drift (a norm change is itself a drift event)
    print("normaliser hashed into record:", norm_hash("x")[:12], "(version-bound → norm change registers as drift)")
