"""spine.corpus: frozen to fluid.

Recovers the source bytes behind the frozen 417-provision manifest
(/interop/frozen-provision-hashes.json, root 37e2e10d...) from the official
EU Publications Office CELLAR API, and keeps them fluid: every run re-fetches,
re-hashes and reports drift, fail-closed.

Two corpus versions are kept side by side and never overwrite each other:

  v1  byte-compatible with the frozen manifest. Reproduces parser 1.0
      (eurlex_sync.parse_articles_from_xhtml): article body capped at 10,000
      characters, and the last article sliced at 5,000 characters. Annexes are
      stored as negative article numbers (-1 = Annex I).
  v2  the same normaliser 1.0.0 over the FULL provision text (no caps).
      Its hashes differ from v1 exactly where v1 was truncated.

Fail closed: a provision that cannot be fetched or parsed is UNKNOWN, never
unchanged.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict

NORMALISER_VERSION = "1.0.0"   # frozen; identical to corpus_anchor.py

_WS = re.compile(r"\s+")
_SOFT_HYPHEN = re.compile(r"[\u00ad\u200b\u200c\u200d\ufeff]")
_EDITORIAL = re.compile(
    r"►?[MC]\d+\s*|\(\s*OJ\s+L[^)]*\)|\[?consolidated text\]?|▼[A-Z]\d*", re.I)


def normalise(text: str) -> str:
    if text is None:
        raise ValueError("cannot normalise None: a missing provision is UNKNOWN, not empty")
    t = _SOFT_HYPHEN.sub("", text)
    t = _EDITORIAL.sub(" ", t)
    t = t.replace("\u2019", "'").replace("\u2018", "'")
    t = t.replace("\u201c", '"').replace("\u201d", '"')
    t = t.replace("\u2013", "-").replace("\u2014", "-").replace("\u00a0", " ")
    t = _WS.sub(" ", t).strip()
    return t.casefold()


def provision_hash(text: str) -> str:
    return hashlib.sha256(f"{NORMALISER_VERSION}\x00{normalise(text)}".encode()).hexdigest()


def corpus_root(anchors: dict[str, str]) -> str:
    h = hashlib.sha256()
    for k in sorted(anchors):
        h.update(k.encode()); h.update(anchors[k].encode())
    return h.hexdigest()


# ── Instruments ─────────────────────────────────────────────────────────────
INSTRUMENTS = {
    "32024R1689": {"name": "EU AI Act", "annexes": True},
    "32016R0679": {"name": "GDPR", "annexes": False},
    "32024R2847": {"name": "Cyber Resilience Act", "annexes": False},
    "32022R2554": {"name": "DORA", "annexes": False},
    "32022L2555": {"name": "NIS2 Directive", "annexes": False},
    "32022L2464": {"name": "CSRD", "annexes": False},
}

SPARQL = "https://publications.europa.eu/webapi/rdf/sparql"
UA = "csoai-corpus-spine/0.1 (+https://councilof.ai/mechanism/)"


def _http(url: str, accept: str, timeout: int = 90, tries: int = 4) -> bytes:
    import time
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as exc:   # transient gateway errors are common on CELLAR
            last = exc
            time.sleep(3 * (i + 1))
    raise last


def sparql(q: str) -> list[dict]:
    url = SPARQL + "?" + urllib.parse.urlencode({"query": q})
    return json.loads(_http(url, "application/sparql-results+json"))["results"]["bindings"]


def cellar_work(celex: str) -> dict:
    """Work URI, English XHTML manifestation and last-modified date. Raises on miss."""
    rows = sparql(f"""
    PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
    SELECT ?work ?manif ?modified WHERE {{
      ?work cdm:resource_legal_id_celex ?c . FILTER(STR(?c) = "{celex}")
      OPTIONAL {{ ?work cdm:work_date_last_modification ?modified . }}
      ?expr cdm:expression_belongs_to_work ?work .
      ?expr cdm:expression_uses_language <http://publications.europa.eu/resource/authority/language/ENG> .
      ?manif cdm:manifestation_manifests_expression ?expr .
      ?manif cdm:manifestation_type ?t . FILTER(STR(?t) = "xhtml")
    }} LIMIT 1""")
    if not rows:
        raise LookupError(f"CELLAR has no English XHTML for {celex}")
    b = rows[0]
    return {"celex": celex, "work": b["work"]["value"], "manifestation": b["manif"]["value"],
            "modified": b.get("modified", {}).get("value")}


def consolidated_versions(celex: str) -> list[str]:
    """Consolidated-text CELEX ids (0YYYYTNNNN-YYYYMMDD) that CELLAR knows for an act.
    A new one appearing is an amendment event the watcher must surface."""
    base = "0" + celex[1:]
    rows = sparql(f"""
    PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
    SELECT DISTINCT ?c WHERE {{
      ?w cdm:resource_legal_id_celex ?c . FILTER(STRSTARTS(STR(?c), "{base}-"))
    }}""")
    return sorted({r["c"]["value"] for r in rows})


def fetch_xhtml(manifestation: str) -> str:
    return _http(manifestation, "application/xhtml+xml, text/html;q=0.9").decode("utf-8", "replace")


# ── Parsing ─────────────────────────────────────────────────────────────────
_ROMAN = {r: i + 1 for i, r in enumerate(
    "I II III IV V VI VII VIII IX X XI XII XIII XIV XV XVI XVII XVIII XIX XX".split())}
_ART = re.compile(r'<div[^>]*(?:id=["\']art[_-]?(\d+)["\']|eId=["\']art_(\d+)["\'])[^>]*>', re.I)
_ANX = re.compile(r'<div[^>]*id=["\']anx_([IVXL]+)["\'][^>]*>')


def strip_tags(h: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h)).strip()


def _segments(xhtml: str, pat: re.Pattern, key):
    ms = list(pat.finditer(xhtml))
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else None
        yield key(m), m.end(), end, i + 1 == len(ms)


def parse(xhtml: str, celex: str, annexes: bool) -> dict[int, dict]:
    """{article_number: {"v1": text, "v2": text, "truncated_in_v1": bool}}.
    Annexes are negative numbers. v1 reproduces parser 1.0 byte for byte."""
    out: dict[int, dict] = {}
    for n, s, e, last in _segments(xhtml, _ART, lambda m: int(next(g for g in m.groups() if g))):
        # v2: full text. The last article runs to the first annex or the end of the body.
        if e is None:
            nxt = _ANX.search(xhtml, s)
            e2 = nxt.start() if nxt else len(xhtml)
        else:
            e2 = e
        full = strip_tags(xhtml[s:e2])
        v1_end = e if e is not None else min(s + 5000, len(xhtml))
        v1 = strip_tags(xhtml[s:v1_end])[:10000]
        if len(v1) > 50 and n not in out:
            out[n] = {"v1": v1, "v2": full, "truncated_in_v1": normalise(v1) != normalise(full)}
    if annexes:
        for n, s, e, last in _segments(xhtml, _ANX, lambda m: -_ROMAN[m.group(1)]):
            seg = xhtml[s:e] if e is not None else xhtml[s:]
            full = strip_tags(seg)
            v1 = full[:10000]
            out[n] = {"v1": v1, "v2": full, "truncated_in_v1": normalise(v1) != normalise(full)}
    return out


_EXACT = re.compile(r'<div\b[^>]*\bid="(art_(\d+)([a-z]*)|anx_([IVXL]+)([a-z]*))"[^>]*>')
_DIVTAG = re.compile(r'<div\b[^>]*>|</div\s*>', re.I)


def _balanced(xhtml: str, start_tag_end: int) -> str:
    """Inner HTML of the div whose start tag ends at start_tag_end (depth-balanced).
    Self-closing <div .../> tags do not open a level."""
    depth = 1
    for m in _DIVTAG.finditer(xhtml, start_tag_end):
        tag = m.group(0)
        if tag.startswith("</"):
            depth -= 1
        elif not tag.endswith("/>"):
            depth += 1
        if depth == 0:
            return xhtml[start_tag_end:m.start()]
    raise ValueError("unbalanced div")


def parse_exact(xhtml: str) -> dict[str, str]:
    """{'4': text, '4a': text, '-1': Annex I, '-14': Annex XIV} from the exact element
    boundaries. Handles inserted articles (4a, 75a...) in consolidated texts and never
    spills into footnotes or the next element. Used for v2 (OJ) and v3 (consolidated)."""
    out = {}
    for m in _EXACT.finditer(xhtml):
        if m.group(2):
            key = m.group(2) + m.group(3)
        else:
            key = str(-_ROMAN[m.group(4)]) + m.group(5)
        if key in out:
            continue
        out[key] = strip_tags(_balanced(xhtml, m.end()))
    return out


def sort_key(k: str):
    m = re.fullmatch(r"(-?)(\d+)([a-z]*)", k)
    return (m.group(1) == "-", int(m.group(2)), m.group(3))


def _words(t: str) -> list[str]:
    t = re.sub(r"\(\s*\d+\s*\)", " ", normalise(t))        # footnote call-outs
    t = re.sub(r"[`'\"]", "", t)
    return re.findall(r"[a-z0-9]+", t)


def change_class(before: str | None, after: str | None) -> tuple[str, int]:
    """INSERTED / DELETED / UNCHANGED / NOISE (<3 word edits: quotes, footnotes) / AMENDED."""
    import difflib
    if before is None and after is not None:
        return "INSERTED", len(_words(after))
    if after is None:
        return "DELETED", len(_words(before or ""))
    a, b = _words(before), _words(after)
    if a == b:
        return "UNCHANGED", 0
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    ops = [o for o in sm.get_opcodes() if o[0] != "equal"]
    edits = sum(max(i2 - i1, j2 - j1) for op, i1, i2, j1, j2 in ops)
    changed = [t for op, i1, i2, j1, j2 in ops for t in a[i1:i2] + b[j1:j2]]
    # NOISE only if every differing token is a number (footnote / OJ page renumbering).
    # A single changed word ('may' -> 'shall') is an amendment.
    return ("NOISE" if changed and all(t.isdigit() for t in changed) else "AMENDED"), edits


def _strip_heading(text: str, key: str) -> str:
    return re.sub(rf"^(?:Article {re.escape(key)}|ANNEX [IVXL]+)\s+", "", text) if text else text


_TITLE = re.compile(r'<p[^>]*class=["\'][^"\']*oj-ti-art[^"\']*["\'][^>]*>\s*Article\s+(\d+)', re.I)


def parse_title_pattern(xhtml: str) -> dict[int, str]:
    """Parser 1.0 fallback path (visible 'Article N' titles). Later duplicates overwrite
    earlier ones, as INSERT OR REPLACE did. Picks up nested amending articles (CSRD)."""
    out = {}
    for n, s, e, last in _segments(xhtml, _TITLE, lambda m: int(m.group(1))):
        end = e if e is not None else min(s + 5000, len(xhtml))
        t = strip_tags(xhtml[s:end])
        if len(t) > 50:
            out[n] = t[:10000]
    return out


def v1_candidates(n: int, t: dict | None, title_texts: dict[int, str]):
    """Named recipes, tried in order. The recipe that reproduces a frozen hash is recorded."""
    if t is not None:
        yield "parser1.0/structural", t["v1"]
        yield "parser1.0/structural-heading-stripped", re.sub(rf"^Article {abs(n)}\s+", "", t["v1"])
    if n in title_texts:
        yield "parser1.0/title-pattern", title_texts[n]
        yield "parser1.0/title-pattern-heading-stripped", re.sub(rf"^\s*{n}\s+", "", title_texts[n])


def _body(text: str, n: int) -> str:
    """Normalised text without its leading 'Article N' / 'N' heading (truncation comparison only)."""
    t = normalise(text)
    return re.sub(rf"^(article )?{abs(n)} ", "", t) if n > 0 else t


def _is_truncated(v1: str, v2: str, n: int, nested: bool) -> bool:
    """True when v1 is MISSING text that v2 has. Extra trailing headings in v1 (the legacy
    parser ran to the next article start) are not truncation."""
    if nested:
        return len(v1) >= 10000
    return _body(v2, n) not in _body(v1, n)


@dataclass
class Provision:
    provision_id: str
    celex: str
    instrument: str
    number: int
    kind: str                 # article | annex
    label: str
    v1_sha256: str
    v2_sha256: str
    frozen_sha256: str | None
    state: str                # REPRODUCED | DRIFTED | NEW | UNKNOWN
    truncated_in_v1: bool
    chars_v2: int
    v1_recipe: str | None = None
    nested_amendment: bool = False   # an 'Article N' inside amending text, not the act's own article


def label(celex: str, n: int) -> str:
    if n < 0:
        r = [k for k, v in _ROMAN.items() if v == -n][0]
        return f"{INSTRUMENTS[celex]['name']} Annex {r}"
    return f"{INSTRUMENTS[celex]['name']} Art. {n}"


def build(frozen: dict[str, str], fetch=fetch_xhtml, work=cellar_work) -> dict:
    """One fluid pass over every instrument. Returns provisions, texts and run record."""
    provisions, texts, sources, unknown = [], {}, [], []
    for celex, meta in INSTRUMENTS.items():
        try:
            w = work(celex)
            x = fetch(w["manifestation"])
            parsed = parse(x, celex, meta["annexes"])
            if not parsed:
                raise ValueError("parsed 0 provisions")
            sources.append({**w, "xhtml_sha256": hashlib.sha256(x.encode()).hexdigest(),
                            "bytes": len(x), "parsed": len(parsed)})
        except Exception as exc:  # fail closed
            unknown.append({"celex": celex, "error": f"{type(exc).__name__}: {exc}"})
            for pid in (k for k in frozen if k.startswith(celex + ":")):
                n = int(pid.split(":")[1])
                provisions.append(Provision(pid, celex, meta["name"], n, "annex" if n < 0 else "article",
                                            label(celex, n), "", "", frozen[pid], "UNKNOWN", False, 0))
            continue
        exact = parse_exact(x)
        for n, t in parsed.items():          # v2 = exact element text (no footnote spill)
            if str(n) in exact:
                t["v2"] = exact[str(n)]
        title_texts = parse_title_pattern(x)
        ids = set(parsed) | {int(k.split(":")[1]) for k in frozen if k.startswith(celex + ":")}
        for n in sorted(ids, key=lambda v: (v < 0, abs(v))):
            pid = f"{celex}:{n}"
            t = parsed.get(n)
            nested = t is None and n in title_texts
            if t is None and not nested:
                provisions.append(Provision(pid, celex, meta["name"], n, "annex" if n < 0 else "article",
                                            label(celex, n), "", "", frozen.get(pid), "UNKNOWN", False, 0))
                continue
            if t is None:   # nested amending article: v1 and v2 are the title-pattern text
                full = title_texts[n]
                t = {"v1": full, "v2": full, "truncated_in_v1": len(full) >= 10000}
            fz = frozen.get(pid)
            recipe, v1_text = None, None
            for rname, cand in v1_candidates(n, parsed.get(n), title_texts):
                if fz is not None and provision_hash(cand) == fz:
                    recipe, v1_text = rname, cand
                    break
            if v1_text is None:
                v1_text = t["v1"]
            h1, h2 = provision_hash(v1_text), provision_hash(t["v2"])
            state = "NEW" if fz is None else ("REPRODUCED" if recipe else "DRIFTED")
            provisions.append(Provision(pid, celex, meta["name"], n, "annex" if n < 0 else "article",
                                        label(celex, n), h1, h2, fz, state,
                                        _is_truncated(v1_text, t["v2"], n, nested), len(t["v2"]),
                                        recipe, nested))
            texts[pid] = {"v1": v1_text, "v2": t["v2"]}
    v1 = {p.provision_id: p.v1_sha256 for p in provisions if p.v1_sha256}
    v2 = {p.provision_id: p.v2_sha256 for p in provisions if p.v2_sha256}
    return {"provisions": [asdict(p) for p in provisions], "texts": texts, "sources": sources,
            "unknown_instruments": unknown, "root_v1": corpus_root(v1), "root_v2": corpus_root(v2)}
