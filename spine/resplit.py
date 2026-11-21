"""spine.resplit: re-split today's official text with the recorded per-instrument recipe.

Recipe 'anchor/1' (recorded per provision, derived from the frozen row):
  start anchor = first K chars of the projection P(frozen text)
  end anchor   = last K chars of P(frozen text)
  order        = position of the provision in its frozen document
K = clamp(len(P)/4, 16, 64). With texts withheld (licence), only hashes travel and the
recipe falls back to 'hash-only' (doc-bytes identity and structural hash match).

Classification of one provision against its frozen hash:
  REPRODUCED  P(frozen) found contiguously; the normalised span hashes to the frozen hash
  UNCHANGED   P(frozen) found contiguously, hash differs only by whitespace placement, or
              the words are identical (punctuation/quote-only), or the document bytes are
              byte-identical to the frozen fetch
  NOISE       anchors found, every differing token is numeric (footnote / page renumbering)
  AMENDED     anchors found, at least one word changed
  UNKNOWN     an anchor is missing, the source is unreachable or unstable, or no text
INSERTED is reported by the engine from the adapter's structural lister.
"""
from __future__ import annotations

import hashlib
import re

from . import corpus as C
from .textx import Projected, proj

RECIPE = "anchor/1"
_V1_TAIL = re.compile(r"(?:<[^<>]*|\(\s*OJ\s+L[^()]*)$")


def anchors(text: str) -> dict:
    p = proj(text)
    k = max(16, min(64, len(p) // 4)) if len(p) >= 16 else len(p)
    return {"recipe": RECIPE, "k": k, "start": p[:k], "end": p[-k:], "plen": len(p)}


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def apply(rows: list[dict], text: str) -> dict[str, dict]:
    """rows: frozen provisions of ONE source document, in document order, each with
    provision_id, text, provision_sha256. Returns per-provision measurement."""
    P = Projected(text)
    p = P.p
    out: dict[str, dict] = {}
    cursor = 0
    # A frozen text that ends in a raw tag fragment ('...(9)</a', '<a id="ntr8-..."') or an
    # unclosed '( OJ L 94, ... p. 65' is a parser-1.0 artefact of the last-article 5,000-character
    # slice cutting through footnote markup; that tail is not law text and is not searched for.
    recs = []
    for r in rows:
        t = r["text"]
        frag = _V1_TAIL.search(t)
        if frag and frag.start() < len(t) // 2:
            frag = None
        tt = t[: frag.start()] if frag else t
        recs.append((r, proj(tt), anchors(tt), bool(frag)))
    for i, (r, fp, a, frag) in enumerate(recs):
        pid = r["provision_id"]
        if not fp:
            out[pid] = {"class": "UNKNOWN", "method": "empty-frozen-text", "span_sha256": None}
            continue
        pos = p.find(fp, cursor)
        if pos < 0:
            pos = p.find(fp)
        if pos >= 0:
            span = P.span(pos, pos + len(fp))
            h = C.provision_hash(span)
            exact = h == r["provision_sha256"]
            out[pid] = {"class": "UNCHANGED", "method": ("exact" if exact else "ws-equal") + ("+v1-tag-fragment" if frag else ""),
                        "reproduced": exact, "current_sha256": h, "span_sha256": _sha(fp)}
            cursor = pos + len(fp)
            continue
        s = p.find(a["start"], cursor)
        if s < 0:
            s = p.find(a["start"])
        if s < 0:
            out[pid] = {"class": "UNKNOWN", "method": "start-anchor-missing", "span_sha256": None}
            continue
        limit = s + 3 * len(fp) + 2000
        e = p.find(a["end"], s + len(a["start"]), limit)
        if e >= 0:
            end = e + len(a["end"])
            how = "anchors"
        else:
            nxt = recs[i + 1][2]["start"] if i + 1 < len(recs) else None
            n2 = p.find(nxt, s + len(a["start"]), limit) if nxt else -1
            if n2 < 0:
                out[pid] = {"class": "UNKNOWN", "method": "end-anchor-missing", "span_sha256": None}
                continue
            end, how = n2, "start+next-start"
        span = P.span(s, end)
        cls, edits = C.change_class(r["text"], span)
        if cls == "UNCHANGED":
            how += "/words-equal"
        out[pid] = {"class": cls, "method": how, "edits": edits, "reproduced": False,
                    "current_sha256": C.provision_hash(span), "span_sha256": _sha(proj(span)),
                    "current_text": span if cls in ("AMENDED", "NOISE") else None}
        cursor = end
    return out


# ── hash-only recipe: for rows whose text may not be republished ────────────
# Committed per row instead of text: K, a 61-bit Rabin-Karp hash of the start anchor, the
# projection length and sha256 of the full projection. Enough to locate and verify the
# provision in today's official text; not enough to reconstruct it.
_B, _M = 1_000_003, (1 << 61) - 1


def _rk(s: str) -> int:
    h = 0
    for ch in s:
        h = (h * _B + ord(ch)) % _M
    return h


def hashonly_recipe(text: str) -> dict:
    p = proj(text)
    a = anchors(text)
    return {"recipe": "hash-only/1", "k": a["k"], "start_rk": _rk(p[:a["k"]]), "plen": len(p), "proj_sha256": _sha(p)}


def _rk_positions(p: str, k: int, targets: set) -> dict:
    out: dict = {}
    if len(p) < k or k == 0:
        return out
    pw = pow(_B, k - 1, _M)
    h = _rk(p[:k])
    for i in range(len(p) - k + 1):
        if h in targets:
            out.setdefault(h, []).append(i)
        if i + k < len(p):
            h = ((h - ord(p[i]) * pw) * _B + ord(p[i + k])) % _M
    return out


def apply_hashonly(rows: list[dict], text: str) -> dict[str, dict]:
    P = Projected(text)
    by_k: dict = {}
    for r in rows:
        rc = r["recipe_hashonly"]
        by_k.setdefault(rc["k"], set()).add(rc["start_rk"])
    pos = {k: _rk_positions(P.p, k, t) for k, t in by_k.items()}
    out = {}
    for r in rows:
        rc = r["recipe_hashonly"]
        cands = pos.get(rc["k"], {}).get(rc["start_rk"], [])
        hit = next((i for i in cands if _sha(P.p[i:i + rc["plen"]]) == rc["proj_sha256"]), None)
        if hit is not None:
            span = P.span(hit, hit + rc["plen"])
            h = C.provision_hash(span)
            ok = h == r["provision_sha256"]
            out[r["provision_id"]] = {"class": "UNCHANGED", "method": "hash-only/" + ("exact" if ok else "ws-equal"),
                                      "reproduced": ok, "current_sha256": h, "span_sha256": rc["proj_sha256"]}
        else:
            out[r["provision_id"]] = {"class": "UNKNOWN", "span_sha256": None, "changed_hash_only": bool(cands),
                                      "method": "hash-only/start-found-text-differs (needs local text to diff)" if cands
                                      else "hash-only/start-anchor-missing"}
    return out


def measure(rows: list[dict], text: str) -> dict[str, dict]:
    with_text = [r for r in rows if r.get("text")]
    hashonly = [r for r in rows if not r.get("text") and r.get("recipe_hashonly")]
    out = apply(with_text, text) if with_text else {}
    if hashonly:
        out.update(apply_hashonly(hashonly, text))
    for r in rows:
        out.setdefault(r["provision_id"], {"class": "UNKNOWN", "method": "no-text-no-recipe", "span_sha256": None})
    return out


def gate_key(m: dict[str, dict]) -> dict[str, tuple]:
    """What must be identical between the two fetches for the source to be STABLE."""
    return {k: (v["class"], v.get("span_sha256")) for k, v in m.items()}
