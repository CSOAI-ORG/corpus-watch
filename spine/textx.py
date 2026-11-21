"""spine.textx: official bytes -> plain text, and the whitespace-free projection.

Extraction is format-sniffed (PDF, DOCX, HTML/XML) and deliberately simple: tags become
spaces or newlines, entities are unescaped, scripts/styles dropped. Provision boundaries are
NOT taken from layout; they come from the recorded recipe (spine.resplit).

The projection P(t) = normalise_v1(t) with all whitespace removed. Two texts with equal
projections differ only in whitespace, which normaliser 1.0.0 already treats as
insignificant except for its placement. Exact hash equality is reported separately.
"""
from __future__ import annotations

import html
import io
import re
import zipfile
from array import array

from .corpus import normalise

_DROP = re.compile(r"(?is)<(script|style|noscript|head)\b.*?</\1\s*>|<!--.*?-->|<\?xml[^>]*\?>|<!DOCTYPE[^>]*>")
_BLOCK = re.compile(r"(?i)</?(?:p|div|br|li|tr|td|th|h[1-6]|table|section|article|ul|ol|dd|dt|blockquote|pre|"
                    r"title|P\d?|P\d?group|Pblock|Text|Title|Number|Pnumber|Para|Article|Paragraph|Item|Sentence|"
                    r"ParagraphSentence|ItemSentence|Column|Schedule|Part|Chapter|Section)\b[^>]*>")
_TAG = re.compile(r"<[^>]+>")


def sniff(b: bytes) -> str:
    if b[:5] == b"%PDF-":
        return "pdf"
    if b[:4] == b"PK\x03\x04":
        return "docx"
    return "markup"


def decode(b: bytes) -> str:
    head = b[:2048].decode("ascii", "replace").lower()
    m = re.search(r'charset=["\']?([a-z0-9_\-]+)', head) or re.search(r'encoding=["\']([a-z0-9_\-]+)', head)
    enc = (m.group(1) if m else "utf-8")
    try:
        return b.decode(enc, "replace")
    except LookupError:
        return b.decode("utf-8", "replace")


def markup_text(s: str) -> str:
    s = _DROP.sub(" ", s)
    s = _BLOCK.sub("\n", s)
    s = _TAG.sub(" ", s)
    return html.unescape(s)


def docx_text(b: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        x = z.read("word/document.xml").decode("utf-8", "replace")
    x = re.sub(r"<w:tab\s*/>", "\t", x)
    x = re.sub(r"<w:br\s*/>|</w:p>", "\n", x)
    x = re.sub(r"<w:instrText\b.*?</w:instrText>", "", x, flags=re.S)
    return html.unescape(_TAG.sub("", x))


def pdf_text(b: bytes) -> str:
    import pypdf  # optional dependency, only needed for pinned PDF documents
    r = pypdf.PdfReader(io.BytesIO(b))
    return "\n".join((p.extract_text() or "") for p in r.pages)


def zip_text(b: bytes) -> str:
    """DOCX, or an archive of XML/HTML members (e.g. gesetze-im-internet xml.zip): members in name order."""
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        names = z.namelist()
        if "word/document.xml" in names:
            return docx_text(b)
        parts = [markup_text(decode(z.read(n))) for n in sorted(names)
                 if n.lower().endswith((".xml", ".htm", ".html", ".lob", ".txt"))]
    return "\n".join(parts)


def extract(b: bytes) -> str:
    k = sniff(b)
    if k == "pdf":
        return pdf_text(b)
    if k == "docx":
        return zip_text(b)
    return markup_text(decode(b))


def proj(text: str) -> str:
    return re.sub(r"\s+", "", normalise(text))


class Projected:
    """normalised text n, projection p, and index map p[i] -> n[keep[i]]."""

    def __init__(self, text: str):
        self.n = normalise(text)
        keep = array("l")
        chars = []
        for i, ch in enumerate(self.n):
            if not ch.isspace():
                keep.append(i)
                chars.append(ch)
        self.p = "".join(chars)
        self.keep = keep

    def span(self, s: int, e: int) -> str:
        """normalised text covering projection [s, e)."""
        if e <= s:
            return ""
        return self.n[self.keep[s]: self.keep[e - 1] + 1]
