"""spine.adapters: one adapter per official source family.

An adapter turns the source recorded on a frozen provision row (source.url / method /
manifestation) into the official machine route that serves the same text today, fetches it,
and extracts plain text. It never decides drift; spine.engine does that, per provision,
after the determinism gate (two independent fetches must give the same provision hashes).

Routing is data-driven: `route(row, registry_row)` picks the adapter from the source host,
so a new wave file that uses a known host needs no code change, and an unknown host falls
through to `pinned_document` (fetch the recorded URL, sniff the format).
"""
from __future__ import annotations

import hashlib
import json
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

from . import textx

UA = "csoai-provision-spine/0.2 (+https://councilof.ai/mechanism/; read-only daily check)"


class Unreachable(Exception):
    """The authority could not be read. Always UNKNOWN, never 'unchanged'."""


# Retry schedule: bounded exponential backoff between tries (5, 15, 45 s for tries=4), so one
# URL spends at most tries x timeout + 65 s before it is reported UNREACHABLE.
BACKOFF_BASE = 5
BACKOFF_FACTOR = 3
BACKOFF_CAP = 60
CONNECT_PROBE_TIMEOUT = 15

# Hosts where, in this process, every try timed out AND a fresh TCP connect probe also timed
# out. A later URL on such a host is reported UNREACHABLE at once (same verdict, provisions
# stay UNKNOWN) instead of spending another tries x timeout on a network path already shown
# to be down for this pass. A host that accepts TCP but answers slowly is never put here.
_HOST_DOWN: dict[str, str] = {}


def reset_host_state() -> None:
    _HOST_DOWN.clear()


def _backoff(i: int) -> int:
    return min(BACKOFF_CAP, BACKOFF_BASE * BACKOFF_FACTOR ** i)


def _is_timeout(exc: BaseException) -> bool:
    reason = getattr(exc, "reason", exc)
    return isinstance(reason, (socket.timeout, TimeoutError)) or "timed out" in str(reason)


def failure_phase(exc: BaseException, during_read: bool = False) -> str:
    """Where a fetch failed: http-<code>, dns, tls, open-timeout (TCP connect, TLS handshake or
    response headers did not finish in time), read-timeout, connect-refused, connection-reset,
    network or other. open-timeout is narrowed by `_probe_connect` to connect-timeout or
    response-timeout."""
    if isinstance(exc, urllib.error.HTTPError):
        return f"http-{exc.code}"
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    if isinstance(reason, socket.gaierror):
        return "dns"
    if _is_timeout(exc):
        return "read-timeout" if during_read else "open-timeout"
    if isinstance(reason, ssl.SSLError):
        return "tls"
    if isinstance(reason, ConnectionRefusedError):
        return "connect-refused"
    if isinstance(reason, ConnectionResetError):
        return "connection-reset"
    if isinstance(reason, OSError):
        return "network"
    return "other"


def _probe_connect(url: str) -> str:
    """After open-timeouts, tell a dropped network path from a slow server: one plain TCP
    connect to the same host and port (no request sent). Skipped behind an HTTP(S) proxy,
    where a direct connect says nothing about the route actually used."""
    if urllib.request.getproxies():
        return "open-timeout"
    u = urllib.parse.urlsplit(url)
    port = u.port or (443 if u.scheme == "https" else 80)
    try:
        socket.create_connection((u.hostname, port), timeout=CONNECT_PROBE_TIMEOUT).close()
        return "response-timeout"
    except (socket.timeout, TimeoutError):
        return "connect-timeout"
    except OSError:
        return "open-timeout"


def http_get(url: str, accept: str = "*/*", timeout: int = 90, tries: int = 4, lang: str | None = None) -> tuple[bytes, str]:
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    if host in _HOST_DOWN:
        raise Unreachable(f"{_HOST_DOWN[host]} [phase=connect-timeout; host={host}; "
                          f"skipped: TCP connect to this host already timed out in this pass]")
    last = None
    phases: list[str] = []
    n = 0
    for i in range(tries):
        n = i + 1
        during_read = False
        try:
            h = {"User-Agent": UA, "Accept": accept, "Accept-Encoding": "gzip"}
            if lang:
                h["Accept-Language"] = lang
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
                final = r.geturl()
                during_read = True
                body = r.read()
                if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
                    import gzip
                    body = gzip.decompress(body)
            if "unblock.federalregister.gov" in final:
                raise Unreachable("bot-challenge redirect (unblock.federalregister.gov)")
            return body, final
        except urllib.error.HTTPError as exc:
            last = exc
            phases.append(failure_phase(exc))
            if exc.code in (400, 401, 403, 404, 406, 410):
                break
            wait = _backoff(i)
            if exc.code == 429:
                try:
                    wait = min(60, int(exc.headers.get("Retry-After", "20")))
                except ValueError:
                    wait = 20
            if n < tries:
                time.sleep(wait)
        except Unreachable:
            raise
        except Exception as exc:  # network / proxy / timeout
            last = exc
            phases.append(failure_phase(exc, during_read))
            if "not on the allowlist" in str(exc) or "Tunnel connection failed: 403" in str(exc):
                break
            if n < tries:
                time.sleep(_backoff(i))
    phase = phases[-1] if phases else "other"
    if phases and all(ph == "open-timeout" for ph in phases):
        phase = _probe_connect(url)
    msg = f"{type(last).__name__}: {str(last)[:200]}"
    if phase == "connect-timeout" and host:
        _HOST_DOWN[host] = msg
    raise Unreachable(f"{msg} [phase={phase}; host={host}; tries={n}]")


class Adapter:
    name = "base"
    hosts: tuple[str, ...] = ()
    accept = "*/*"
    lang: str | None = None
    insertion_lister = None      # optional: text -> {number: ""}; ids present in the source today
    lister_input = "text"        # "raw" = lister reads decoded bytes, "text" = extracted text
    latest_version = "inherent"  # the route always serves the current text
    note = ""

    def matches(self, url: str) -> bool:
        host = urllib.parse.urlparse(url).netloc
        return any(host == h or host.endswith("." + h) for h in self.hosts)

    def resolve(self, url: str, ctx: dict) -> str:
        return url.split("#")[0]

    def fetch(self, url: str, ctx: dict) -> dict:
        target = self.resolve(url, ctx)
        body, final = http_get(target, self.accept, lang=self.lang)
        return {"bytes": body, "final_url": final, "resolved_url": target,
                "sha256": hashlib.sha256(body).hexdigest(), "format": textx.sniff(body)}

    def text(self, fetched: dict) -> str:
        return textx.extract(fetched["bytes"])

    def describe(self) -> dict:
        return {"adapter": self.name, "hosts": list(self.hosts), "latest_version": self.latest_version,
                "insertion_detection": bool(self.insertion_lister), "note": self.note}


# ── EU Publications Office (CELLAR) ─────────────────────────────────────────
class Cellar(Adapter):
    name = "eu_cellar"
    hosts = ("publications.europa.eu",)
    accept = "application/xhtml+xml, text/html;q=0.9"
    lang = "eng"
    latest_version = "pinned-OJ (current law via spine.fluid consolidated diff)"
    note = "OJ XHTML manifestation; EU-six resolved from CELEX via SPARQL"

    def resolve(self, url, ctx):
        if url.startswith("http"):
            return url
        from . import corpus as C
        return C.cellar_work(ctx["celex"])["manifestation"]

    lister_input = "raw"

    @staticmethod
    def insertion_lister(raw: str) -> dict:
        """OJ element ids -> corpus numbering ('12', 'annex-III'); inserted articles keep their suffix."""
        from . import corpus as C
        out = {}
        for k, v in C.parse_exact(raw).items():
            if k.startswith("-"):
                n = int(re.match(r"-(\d+)", k).group(1))
                roman = [r for r, i in C._ROMAN.items() if i == n]
                k = "annex-" + (roman[0] if roman else str(n)) + k[len(str(-n)):]
            out[k] = v
        return out


class LegislationGovUK(Adapter):
    name = "legislation_gov_uk"
    hosts = ("www.legislation.gov.uk", "legislation.gov.uk")
    accept = "application/xml"
    note = "data.xml (latest revised); provision text hashed, so page metadata churn is not drift"
    lister_input = "raw"

    def text(self, fetched):
        return uk_render(fetched["bytes"])

    @staticmethod
    def insertion_lister(raw: str) -> dict:
        ids = {}
        for m in re.finditer(r'<P1\b[^>]*\bid="(section|article|regulation)-(\d+[A-Z]*)"', raw):
            ids[("s" if m.group(1) == "section" else "") + m.group(2)] = ""
        for m in re.finditer(r'<Schedule\b[^>]*\bid="schedule-(\d+[A-Z]*)"', raw):
            ids["sch" + m.group(1)] = ""
        return ids


_UK_SKIP = {"Metadata", "Contents", "Commentaries", "CommentaryRef", "Footnotes", "MarginNotes", "Resources"}
_UK_BLOCK = {"P", "P1", "P2", "P3", "P4", "P5", "P6", "Text", "Title", "Pnumber", "Para", "Schedule", "Number",
             "TitleBlock", "Reference", "P1group", "Pblock", "Part", "Chapter", "Tabular", "Row"}


def uk_render(b: bytes) -> str:
    """legislation.gov.uk CLML -> text the way the frozen GB slice rendered it: section-level P1
    numbers dropped (the heading carries the provision), schedule P1 numbers and P1 numbers inside
    BlockAmendment bare, lower levels '(n)' unless the element carries PuncBefore/PuncAfter."""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(b)
    out: list[str] = []

    def local(t):
        return t.rsplit("}", 1)[-1] if isinstance(t, str) else ""

    def walk(e, parent: str, in_sched: bool, in_amend: bool = False):
        name = local(e.tag)
        if name in _UK_SKIP:
            if e.tail:
                out.append(e.tail)
            return
        if name == "Schedule":
            in_sched = True
        if name == "BlockAmendment":
            in_amend = True
        if name == "Pnumber":
            num = "".join(e.itertext()).strip()
            pb, pa = e.get("PuncBefore"), e.get("PuncAfter")
            if parent == "P1" and in_amend:
                out.append("\n" + num + "\n")   # inserted section number inside amending text: bare
            elif parent == "P1" and not in_sched:
                pass                      # section number: the heading already identifies it
            elif pb is not None or pa is not None:
                out.append("\n" + (pb or "") + num + (pa or "") + "\n")
            elif parent == "P1":
                out.append("\n" + num + "\n")
            else:
                out.append("\n(" + num + ")\n")
            if e.tail:
                out.append(e.tail)
            return
        blk = name in _UK_BLOCK
        if blk:
            out.append("\n")
        if e.text:
            out.append(e.text)
        for c in e:
            walk(c, name, in_sched, in_amend)
        if blk:
            out.append("\n")
        if e.tail:
            out.append(e.tail)

    walk(root, "", False)
    return "".join(out)


class ECFR(Adapter):
    name = "us_ecfr"
    hosts = ("www.ecfr.gov",)
    note = "eCFR renderer API (current); HTML pages redirect automated clients to a challenge"

    def resolve(self, url, ctx):
        v = re.search(r"/api/versioner/v1/full/(\d{4}-\d{2}-\d{2})/title-(\d+)\.xml", url)
        if v:  # a dated full-text export: re-point it at the title's current up-to-date date
            cur = ecfr_current_date(int(v.group(2)))
            return url.replace(v.group(1), cur) if cur else url
        m = re.search(r"/current/title-(\d+)/section-([0-9A-Za-z.\-]+)", url)
        if not m:
            return url
        return f"https://www.ecfr.gov/api/renderer/v1/content/enhanced/current/title-{m.group(1)}?section={m.group(2)}"


_ECFR_TITLES: dict = {}


def ecfr_current_date(title: int) -> str | None:
    if not _ECFR_TITLES:
        body, _ = http_get("https://www.ecfr.gov/api/versioner/v1/titles.json", "application/json")
        for t in json.loads(body)["titles"]:
            _ECFR_TITLES[t["number"]] = t.get("up_to_date_as_of")
    return _ECFR_TITLES.get(title)


class FederalRegister(Adapter):
    name = "us_federal_register"
    hosts = ("www.federalregister.gov",)
    latest_version = "pinned (a published FR document does not change)"
    note = "FR full_text HTML route; document pages redirect automated clients to a challenge"

    def resolve(self, url, ctx):
        m = re.search(r"/documents/(\d{4})/(\d{2})/(\d{2})/([0-9\-]+)/", url)
        if not m:
            return url
        y, mo, d, num = m.groups()
        return f"https://www.federalregister.gov/documents/full_text/html/{y}/{mo}/{d}/{num}.html"

    def text(self, fetched):
        t = textx.extract(fetched["bytes"])
        t = re.sub(r"\(\s*printed\s+page\s+\d+\s*\)", " ", t, flags=re.I)
        return t.replace("\u201c", "``").replace("\u201d", "''")   # frozen slice used GPO-style quotes


class GovInfo(Adapter):
    name = "us_govinfo"
    hosts = ("www.govinfo.gov",)
    latest_version = "pinned (USCODE edition in URL)"


class EGovJP(Adapter):
    name = "jp_egov"
    hosts = ("laws.e-gov.go.jp",)
    accept = "application/xml"
    note = "e-Gov law API v2 law_data (current revision); title rendered before caption as frozen"
    lister_input = "raw"

    def text(self, fetched):
        x = textx.decode(fetched["bytes"])
        x = re.sub(r"(<ArticleCaption[^>]*>.*?</ArticleCaption>)\s*(<ArticleTitle[^>]*>.*?</ArticleTitle>)", r"\2 \1", x, flags=re.S)
        return textx.markup_text(x)

    @staticmethod
    def insertion_lister(raw: str) -> dict:
        main = raw.split("<SupplProvision", 1)[0]
        return {m.group(1) + (f"-{m.group(2)}" if m.group(2) else ""): ""
                for m in re.finditer(r'<Article\b[^>]*\bNum="(\d+)(?:_(\d+))?"', main)}


class LawGoKR(Adapter):
    name = "kr_law_go_kr"
    hosts = ("www.law.go.kr", "law.go.kr")
    latest_version = "pinned (efYd effective-date version in URL)"

    @staticmethod
    def insertion_lister(text: str) -> dict:
        return {m.group(1) + (f"-{m.group(2)}" if m.group(2) else ""): ""
                for m in re.finditer(r"제(\d+)조(?:의(\d+))?\(", text)}


class LegislationAU(Adapter):
    name = "au_legislation_gov_au"
    hosts = ("api.prod.legislation.gov.au",)
    latest_version = "pinned (compilation start date in URL)"
    note = "Federal Register of Legislation API, Word compilation"


class LawMojTW(Adapter):
    name = "tw_law_moj"
    hosts = ("law.moj.gov.tw",)
    note = "LawAll page (current). Page bytes change per request (ASP.NET state); provision hashes do not"

    @staticmethod
    def insertion_lister(text: str) -> dict:
        return {m.group(1): "" for m in re.finditer(r"第\s*(\d+(?:-\d+)?)\s*條", text)}


class FlkNPC(Adapter):
    name = "cn_flk_npc"
    hosts = ("flk.npc.gov.cn",)
    latest_version = "pinned (bbbs = one published version of the law)"
    note = "NPC national law database: download API returns a signed object-store URL for the DOCX"

    def fetch(self, url, ctx):
        body, final = http_get(url, "application/json")
        try:
            target = json.loads(body)["data"]["url"]
        except Exception as exc:
            raise Unreachable(f"flk download API returned no file URL: {exc}")
        doc, final2 = http_get(target)
        return {"bytes": doc, "final_url": final2, "resolved_url": target.split("?")[0],
                "sha256": hashlib.sha256(doc).hexdigest(), "format": textx.sniff(doc)}

    @staticmethod
    def insertion_lister(text: str) -> dict:
        return {str(kanji_int(m.group(1))): "" for m in re.finditer(r"(?:^|\n)\s*第([一二三四五六七八九十百零〇]+)条", text)}


class GovCN(FlkNPC):
    name = "cn_gov_cn"
    hosts = ("www.gov.cn",)
    latest_version = "pinned (policy-library page)"
    note = "State Council policy library page (republishes CAC orders; cac.gov.cn blocks automated clients)"
    fetch = Adapter.fetch


class JusticeCA(Adapter):
    name = "ca_justice_laws"
    hosts = ("laws-lois.justice.gc.ca",)
    note = "Justice Laws consolidated FullText.html (current); index/page URLs resolve to it"

    def resolve(self, url, ctx):
        m = re.match(r"(https://laws-lois\.justice\.gc\.ca/(?:eng|fra)/(?:acts|regulations)/[^/]+/)", url)
        return m.group(1) + "FullText.html" if m else url

    def text(self, fetched):
        x = textx.decode(fetched["bytes"])
        x = re.sub(r'(?s)<span class="wb-invisible">.*?</span>', " ", x)      # screen-reader labels
        x = re.sub(r"(?s)<dt\b.*?</dt>", " ", x)                              # defined-term list headers
        x = re.sub(r'(?s)<div class="PITLink">.*?</div>', " ", x)             # previous-version links
        x = re.sub(r'(?s)<div class="HistoricalNote">.*?</div>',
                   lambda m: re.sub(r"</li>\s*<li[^>]*>(?!<a[^>]*wb-lbx)", ";", m.group(0)), x)
        # history items are joined by ';' as frozen, except before a lightbox amendment link (frozen: space)
        return textx.markup_text(x)


class UtahLegislature(Adapter):
    name = "us_state_utah"
    hosts = ("le.utah.gov",)
    latest_version = "resolved: page shell's versionDefault = 'Current Version'"
    note = "xcode shell page names the current version; its .xml holds history + catchline + text (as frozen)"

    def fetch(self, url, ctx):
        if "/xcode/" not in url:          # enrolled bills etc.: a pinned document
            return Adapter.fetch(self, url, ctx)
        shell, _ = http_get(url.split("?")[0])
        m = re.search(rb'versionDefault="([^"]+)"', shell)
        if not m:
            raise Unreachable("Utah shell page has no versionDefault")
        cur = m.group(1).decode()
        pinned = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("v", [None])[0]
        target = url.split("?")[0].rsplit("/", 1)[0] + f"/{cur}.xml"
        body, final = http_get(target)
        return {"bytes": body, "final_url": final, "resolved_url": target, "sha256": hashlib.sha256(body).hexdigest(),
                "format": textx.sniff(body), "version_pinned": pinned, "version_current": cur}


class USStatePinned(Adapter):
    name = "us_state_pinned"
    hosts = ("capitol.texas.gov", "leg.colorado.gov", "cppa.ca.gov")
    latest_version = "pinned (enrolled bill / approved regulation text)"
    note = "enrolled bill or approved text; later amendments arrive as new instruments in the registry"


class BCNChile(Adapter):
    name = "cl_bcn_leychile"
    hosts = ("www.bcn.cl",)
    accept = "application/xml"
    note = "BCN Ley Chile XML service (obtxml); the navegar page is a JS shell"

    def resolve(self, url, ctx):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        n = q.get("idNorma", [None])[0]
        return f"https://www.leychile.cl/Consulta/obtxml?opt=7&idNorma={n}" if n else url


# ── remote ZIP members (HTTP Range): bulk archives are never downloaded whole ───────
_ZIP_DIRS: dict = {}


def _range(url: str, start: int, end: int) -> bytes:
    """bytes [start, end] inclusive; start < 0 = suffix range."""
    rng = f"bytes={start}" if start < 0 else f"bytes={start}-{end}"
    last = None
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Range": rng})
            with urllib.request.urlopen(req, timeout=180) as r:
                if r.status != 206:
                    raise Unreachable(f"server ignored Range ({r.status}); refusing to download the whole archive")
                return r.read()
        except Unreachable:
            raise
        except Exception as exc:
            last = exc
            time.sleep(3 * (i + 1))
    raise Unreachable(f"{type(last).__name__}: {str(last)[:200]}")


def zip_directory(url: str) -> dict:
    """{basename: (local_header_offset, compressed_size, method, name)} from the central directory."""
    import struct
    if url in _ZIP_DIRS:
        return _ZIP_DIRS[url]
    tail = _range(url, -70000, 0)
    i = tail.rfind(b"PK\x05\x06")
    if i < 0:
        raise Unreachable("zip end-of-central-directory not found")
    _, _, _, _, n, cd_size, cd_off, _ = struct.unpack("<4s4H2LH", tail[i:i + 22])
    j = tail.rfind(b"PK\x06\x06")
    if j >= 0:  # zip64 end of central directory record
        n, cd_size, cd_off = struct.unpack("<QQQ", tail[j + 32:j + 56])
    cd = _range(url, cd_off, cd_off + cd_size - 1)
    out, p = {}, 0
    while p + 46 <= len(cd) and cd[p:p + 4] == b"PK\x01\x02":
        (method, csize, usize, nlen, xlen, clen, off) = (struct.unpack("<H", cd[p + 10:p + 12])[0],
            *struct.unpack("<LL", cd[p + 20:p + 28]), *struct.unpack("<HHH", cd[p + 28:p + 34]),
            struct.unpack("<L", cd[p + 42:p + 46])[0])
        name = cd[p + 46:p + 46 + nlen].decode("utf-8", "replace")
        extra = cd[p + 46 + nlen:p + 46 + nlen + xlen]
        q = 0
        while q + 4 <= len(extra):
            hid, hlen = struct.unpack("<HH", extra[q:q + 4])
            if hid == 1:  # zip64 extended information, fields present only where the 32-bit value is 0xFFFFFFFF
                vals, k = extra[q + 4:q + 4 + hlen], 0
                if usize == 0xFFFFFFFF:
                    usize = struct.unpack("<Q", vals[k:k + 8])[0]; k += 8
                if csize == 0xFFFFFFFF:
                    csize = struct.unpack("<Q", vals[k:k + 8])[0]; k += 8
                if off == 0xFFFFFFFF:
                    off = struct.unpack("<Q", vals[k:k + 8])[0]; k += 8
            q += 4 + hlen
        out[name.rsplit("/", 1)[-1]] = (off, csize, method, name)
        p += 46 + nlen + xlen + clen
    _ZIP_DIRS[url] = out
    return out


def zip_member(url: str, member: str) -> bytes:
    import struct
    import zlib
    d = zip_directory(url)
    if member not in d:
        raise Unreachable(f"member {member} not in archive")
    off, csize, method, _ = d[member]
    head = _range(url, off, off + 29)
    nlen, xlen = struct.unpack("<HH", head[26:30])
    data = _range(url, off + 30 + nlen + xlen, off + 30 + nlen + xlen + csize - 1)
    if method == 0:
        return data
    if method == 8:
        return zlib.decompress(data, -15)
    raise Unreachable(f"unsupported zip method {method}")


class LegInfoBulk(Adapter):
    name = "us_ca_leginfo_bulk"
    hosts = ("downloads.leginfo.legislature.ca.gov",)
    latest_version = "pinned (session archive member = one bill version)"
    note = "California pubinfo bulk ZIP; only the named .lob member is fetched, by HTTP Range"

    def fetch(self, url, ctx):
        base, _, member = url.partition("#")
        body = zip_member(base, member)
        return {"bytes": body, "final_url": url, "resolved_url": url, "sha256": hashlib.sha256(body).hexdigest(),
                "format": textx.sniff(body)}


class ICO(Adapter):
    name = "gb_ico_guidance"
    hosts = ("ico.org.uk",)
    note = "ICO guidance chapter pages: <main> content with <nav>/<form>/<aside> removed (as frozen)"

    def text(self, fetched):
        x = textx.decode(fetched["bytes"])
        m = re.search(r"(?is)<main\b.*?</main>", x)
        x = m.group(0) if m else x
        x = re.sub(r"(?is)<(nav|form|aside|button|summary)\b.*?</\1\s*>", " ", x)   # UI chrome, not guidance text
        x = re.sub(r'(?is)<span class="hidden"[^>]*>.*?</span>', " ", x)                # hidden screen-reader labels
        return textx.markup_text(x)


class Normattiva(Adapter):
    name = "it_normattiva_akn"
    hosts = ("www.normattiva.it",)
    accept = "application/xml"
    latest_version = "pinned (dataVigenza in URL)"
    note = "Normattiva Akoma Ntoso export; authorialNote (editorial notes) removed as frozen"

    def fetch(self, url, ctx):
        """caricaAKN serves the export inside a portal session: open the act's own detail page
        first (ordinary session cookie, same User-Agent), then request the export. A portal
        HTML page instead of Akoma Ntoso is UNREACHABLE, never a re-split of the wrong document."""
        import http.cookiejar
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        dgu, cod = q.get("dataGU", [""])[0], q.get("codiceRedaz", [""])[0]
        op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        try:
            if dgu and cod:
                det = ("https://www.normattiva.it/atto/caricaDettaglioAtto?atto.dataPubblicazioneGazzetta="
                       f"{dgu[:4]}-{dgu[4:6]}-{dgu[6:]}&atto.codiceRedazionale={cod}")
                op.open(urllib.request.Request(det, headers={"User-Agent": UA}), timeout=90).read()
            with op.open(urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/xml"}), timeout=90) as r:
                body = r.read()
        except Exception as exc:
            raise Unreachable(f"{type(exc).__name__}: {str(exc)[:200]}")
        if b"akomaNtoso" not in body[:4000]:
            raise Unreachable("caricaAKN returned the portal page, not Akoma Ntoso")
        return {"bytes": body, "final_url": url, "resolved_url": url, "sha256": hashlib.sha256(body).hexdigest(),
                "format": "markup"}

    def text(self, fetched):
        x = textx.decode(fetched["bytes"])
        x = re.sub(r"(?is)<(?:\w+:)?authorialNote\b.*?</(?:\w+:)?authorialNote\s*>", " ", x)
        return textx.markup_text(x)


class IMPO(Adapter):
    name = "uy_impo"
    hosts = ("www.impo.com.uy",)
    accept = "application/json"
    note = "IMPO consolidated text via ?json=true (the method the frozen slice used)"

    def resolve(self, url, ctx):
        return url + ("&" if "?" in url else "?") + "json=true"

    def text(self, fetched):
        j = json.loads(textx.decode(fetched["bytes"]), strict=False)
        parts = []

        def walk(v):
            if isinstance(v, str):
                parts.append(textx.markup_text(v))
            elif isinstance(v, dict):
                for x in v.values():
                    walk(x)
            elif isinstance(v, list):
                for x in v:
                    walk(x)
        walk(j)
        return "\n".join(parts)


class BOE(Adapter):
    name = "es_boe_api"
    hosts = ("www.boe.es",)
    accept = "application/xml"
    note = "BOE open-data API legislacion-consolidada/texto (current consolidated text)"


class PinnedDocument(Adapter):
    name = "pinned_document"
    hosts = ()
    latest_version = "pinned (recorded URL)"
    note = "generic: fetch the recorded URL, sniff PDF/DOCX/HTML, apply the per-instrument recipe"

    def matches(self, url):
        return url.startswith("http")


class IdentifierOnly(Adapter):
    name = "identifier_only"
    note = "IDS_ONLY rows: no text frozen (licence or access), nothing to re-fetch"

    def matches(self, url):
        return False


ADAPTERS: list[Adapter] = [Cellar(), LegislationGovUK(), ECFR(), FederalRegister(), GovInfo(), EGovJP(), LawGoKR(),
                           LegislationAU(), LawMojTW(), FlkNPC(), GovCN(), JusticeCA(), UtahLegislature(), LegInfoBulk(), ICO(), Normattiva(), IMPO(), BOE(),
                           USStatePinned(), BCNChile(), PinnedDocument()]
IDS = IdentifierOnly()
BY_NAME = {a.name: a for a in ADAPTERS + [IDS]}


def source_url(row: dict) -> str:
    """The address the engine fetches. `fetch_url` (the publisher's own host) wins over `url`, which stays the
    citation (e.g. a DOI). doi.org answers 403 to automated clients; nvlpubs.nist.gov serves the same bytes."""
    s = row.get("source") or {}
    return s.get("fetch_url") or s.get("url") or s.get("manifestation") or ""


def route(row: dict) -> Adapter:
    s = row.get("source") or {}
    if s.get("method") == "identifier_only" or not row.get("provision_sha256"):
        return IDS
    if s.get("kind") in ("git_db", "cellar_xhtml_refetch") or (s.get("manifestation") and not s.get("url")):
        return BY_NAME["eu_cellar"]
    u = source_url(row)
    for a in ADAPTERS:
        if a.matches(u):
            return a
    return IDS


_KD = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_KU = {"十": 10, "百": 100, "千": 1000}


def kanji_int(s: str) -> int:
    """Traditional CJK numerals as used for article numbers: 百二十三 = 123, 百零五 = 105."""
    total, cur = 0, 0
    for ch in s:
        if ch in _KD:
            cur = _KD[ch]
        elif ch in _KU:
            total += (cur or 1) * _KU[ch]
            cur = 0
    return total + cur
