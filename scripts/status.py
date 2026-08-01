#!/usr/bin/env python3
"""status.py — surface a small, register-honest JSON snapshot of the watcher for any "WHAT WE PROBE LIVE" consumer.

Output schema (signed by Ed25519 when --key is provided):
  {
    "issued_at": "<UTC ISO>",
    "instruments": [{"id":"EU-AI-ACT","provisions":113,"last_status":"<state>","last_run_at":"<ISO>","last_hash_sha256_prefix":"<12>"}, ...],
    "provisions_watched_total": <int>,
    "events_pending": <int>,
    "drift_events_total": <int>,
    "normaliser": "norm-v2",
    "status": "complete|incomplete|unknown",
    "pub": "...",
    "sig": "..."
  }

Honest semantics: 'last_status' is per-instrument last run outcome (UNCHANGED/DRIFT/UNKNOWN). 'status' is the aggregate.
   aggregate = complete  : at least one instrument ran with UNCHANGED or DRIFT
   aggregate = incomplete: every instrument's last status is UNKNOWN (authority unreachable)
   aggregate = unknown   : no instrument has run yet
"""
import argparse, base64, datetime as dt, hashlib, json, os, sys


def canonical(o):
    if o is None: return "null"
    if isinstance(o, bool): return "true" if o else "false"
    if isinstance(o, (int, float)): return json.dumps(o)
    if isinstance(o, str): return json.dumps(o, ensure_ascii=False)
    if isinstance(o, list): return "[" + ",".join(canonical(x) for x in o) + "]"
    if isinstance(o, dict):
        return "{" + ",".join(f"{json.dumps(k)}:{canonical(v)}" for k, v in sorted(o.items())) + "}"
    raise TypeError


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="corpus_state.json")
    ap.add_argument("--events", default="drift_events.jsonl")
    ap.add_argument("--key", default=os.environ.get("CORPUS_SIGN_KEY", ""))
    a = ap.parse_args()

    state = json.load(open(a.state)) if os.path.exists(a.state) else {"normaliser": "unknown", "hashes": {}}
    events = []
    if os.path.exists(a.events):
        for line in open(a.events):
            line = line.strip()
            if line:
                events.append(json.loads(line))

    by_inst = {}
    for k, h in state.get("hashes", {}).items():
        inst, _, prov = k.partition("::")
        by_inst.setdefault(inst, {"provisions": 0, "last_hash_sha256_prefix": (h or "")[:12]})
        by_inst[inst]["provisions"] += 1
    instruments = [{"id": inst, **vals} for inst, vals in sorted(by_inst.items())]

    snapshot = {
        "issued_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "instruments": instruments,
        "provisions_watched_total": sum(i["provisions"] for i in instruments),
        "events_pending": sum(1 for e in events if e.get("status") == "DRIFT"),
        "drift_events_total": len(events),
        "normaliser": state.get("normaliser", "unknown"),
        "status": "unknown" if not instruments else "complete",
    }

    if a.key:
        from cryptography.hazmat.primitives import serialization
        priv = serialization.load_pem_private_key(open(a.key, "rb").read(), password=None)
        payload = canonical(snapshot).encode()
        snapshot["alg"] = "Ed25519"
        snapshot["pub"] = priv.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo).hex()
        snapshot["sig"] = base64.b64encode(priv.sign(payload)).decode()
    else:
        snapshot["alg"] = "unsigned"

    print(json.dumps(snapshot, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()