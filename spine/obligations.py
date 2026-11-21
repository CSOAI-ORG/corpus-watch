"""spine.obligations: provision text -> DRAFT obligation rows, deterministic.

No model grading. Every row records the rule that produced it, so the cut is
re-runnable and auditable. Every row is DRAFT with counsel_confirmed = false
until a human reviewer flips it; nothing here is legal advice.

Evidence kinds (week plan, section 1):
  OBSERVED   the duty leaves a public trace a stranger can check (a notice, a mark,
             a published policy, a register entry). Sellable as a signed measurement.
  SUBMITTED  the duty is internal (documentation, risk management, records, assessment,
             notification to an authority). Sellable as signed issuance of the
             customer's own evidence. Not certification.
  AUTHORITY  the addressee is a public body (Commission, Member State, AI Office,
             supervisory authority). Not sold to private parties.
  NONE       definitions, scope, entry into force, amendments, empowerments.
  UNTRIAGED  a duty sentence matched no evidence rule. Needs a human.
"""
from __future__ import annotations

import re

METHOD_VERSION = "obligations/0.1.0"

# Addressees, longest first so "authorised representative" beats "representative".
ADDRESSEES = [
    ("provider of general-purpose ai model", "gpai_provider"),
    ("providers of general-purpose ai models", "gpai_provider"),
    ("authorised representative", "authorised_representative"),
    ("notified bod", "notified_body"),
    ("market surveillance authorit", "AUTHORITY"),
    ("supervisory authorit", "AUTHORITY"),
    ("competent authorit", "AUTHORITY"),
    ("national authorit", "AUTHORITY"),
    ("member state", "AUTHORITY"),
    ("the commission", "AUTHORITY"),
    ("the ai office", "AUTHORITY"),
    ("the board", "AUTHORITY"),
    ("esas", "AUTHORITY"),
    ("enisa", "AUTHORITY"),
    ("csirt", "AUTHORITY"),
    ("financial entit", "financial_entity"),
    ("ict third-party service provider", "ict_third_party_provider"),
    ("essential and important entit", "essential_or_important_entity"),
    ("essential entit", "essential_or_important_entity"),
    ("important entit", "essential_or_important_entity"),
    ("manufacturer", "manufacturer"),
    ("importer", "importer"),
    ("distributor", "distributor"),
    ("deployer", "deployer"),
    ("provider", "provider"),
    ("controller", "controller"),
    ("processor", "processor"),
    ("undertaking", "undertaking"),
    ("statutory auditor", "auditor"),
]

# Sentences that use 'shall' but impose no duty on anyone.
NON_DUTY = re.compile(
    r"shall (?:not )?(?:apply|mean|be understood|enter into force|be binding|be without prejudice|"
    r"be construed|be deemed|be repealed|be amended|be replaced|be inserted|be added|be deleted|"
    r"be read as|be empowered|have the power|be conferred)", re.I)

# Evidence rules. First match wins; order matters (public trace beats internal duty).
OBSERVED_RULES = [
    ("publish", r"\b(?:make|made|be) (?:it |them |that information |the [\w ]{1,40} )?publicly available|\bpublish(?:es|ed)?\b|made available to the public"),
    ("inform-persons", r"\binform (?:the )?(?:natural persons|data subjects?|users|recipients|the public)\b|\bprovide (?:the )?data subject\b|information to be provided"),
    ("disclose-ai", r"\bdisclose that the content\b|\binteracting with an ai system\b|artificially generated or manipulated"),
    ("machine-readable-mark", r"\bmarked in a machine-readable format\b|\bdetectable as artificially generated\b"),
    ("register-entry", r"\bregister (?:themselves|it|that system|the [\w ]{1,30})? ?in the eu database\b|\benter(?:ed)? in the eu database\b"),
    ("contact-point", r"\bsingle point of contact\b|\bcontact details\b|\bpoint of contact\b.*\bpublic"),
    ("cvd-policy", r"\bcoordinated vulnerability disclosure\b|\bsupport period\b.*\b(?:indicate|inform|specify)"),
    ("sustainability-statement", r"\bsustainability statement\b|\bsustainability reporting\b.*\bmanagement report\b"),
]
SUBMITTED_RULES = [
    ("documentation", r"\b(?:draw up|keep|maintain|retain|document|record)\b.*\b(?:documentation|records?|logs?|register|written)\b|\btechnical documentation\b"),
    ("risk-management", r"\brisk[- ]management\b|\brisk assessment\b|\bassess(?:ment)? (?:of )?(?:the )?risks?\b"),
    ("assessment", r"\b(?:carry out|perform|conduct|undergo)\b.*\b(?:assessment|evaluation|test(?:ing)?|audit)\b|\bconformity assessment\b|\bimpact assessment\b"),
    ("management-system", r"\bquality management system\b|\b(?:establish|implement|maintain)\b.*\b(?:system|framework|policy|policies|procedures?|process(?:es)?|measures?)\b"),
    ("notify-authority", r"\b(?:notify|report|submit|communicate)\b.*\b(?:authorit|commission|ai office|csirt|supervis|regulator)\w*"),
    ("ensure", r"\bshall ensure\b|\bshall take (?:appropriate )?(?:technical and organisational )?measures\b"),
    ("cooperate", r"\bcooperate with\b|\bupon (?:a )?reasoned request\b|\bprovide .* (?:information|documentation) .* request"),
]
NONE_TITLES = re.compile(r"^(?:article \d+ )?(?:definitions|subject[- ]matter|scope|entry into force|amendments? to|"
                         r"exercise of the delegation|committee procedure|repeal|transposition|review|evaluation|"
                         r"transitional provisions?|final provisions?)", re.I)

_PARA = re.compile(r"(?:^|\s)(\d{1,2})\.\s+(?=[A-Z])")
_SENT = re.compile(r"(?<=[.;:])\s+(?=[A-Z(])")


def paragraphs(text: str) -> list[tuple[str, str]]:
    """Split EU article text into ('1', '...') numbered paragraphs; '0' for unnumbered."""
    cuts = [(m.start(1), m.group(1)) for m in _PARA.finditer(text)]
    if not cuts:
        return [("0", text)]
    out = []
    if cuts[0][0] > 0:
        out.append(("0", text[:cuts[0][0]].strip()))
    for i, (pos, num) in enumerate(cuts):
        end = cuts[i + 1][0] if i + 1 < len(cuts) else len(text)
        out.append((num, text[pos + len(num) + 1:end].strip()))
    return out


def addressee(sentence: str) -> str:
    """The addressee is the subject phrase before the first 'shall'."""
    head = sentence.lower().split(" shall ", 1)[0][-200:]
    best, best_pos = "UNRESOLVED", -1
    for needle, tag in ADDRESSEES:
        pos = head.rfind(needle)
        if pos > best_pos:
            best, best_pos = tag, pos
    return best


def evidence_kind(sentence: str, who: str) -> tuple[str, str]:
    s = sentence.lower()
    if who == "AUTHORITY":
        return "AUTHORITY", "addressee-is-public-body"
    for name, pat in OBSERVED_RULES:
        if re.search(pat, s):
            return "OBSERVED", name
    for name, pat in SUBMITTED_RULES:
        if re.search(pat, s):
            return "SUBMITTED", name
    return "UNTRIAGED", "no-rule-matched"


def extract(provision_id: str, text: str, title_hint: str = "") -> list[dict]:
    """DRAFT obligation rows for one provision."""
    head = (title_hint or text[:120]).strip()
    if NONE_TITLES.search(head):
        return [{"obligation_id": f"{provision_id}/none", "provision_id": provision_id,
                 "paragraph": None, "text": None, "addressee": None, "modality": None,
                 "evidence_kind": "NONE", "rule": "title:" + NONE_TITLES.search(head).group(0).strip().lower(),
                 "status": "DRAFT", "counsel_confirmed": False, "method": METHOD_VERSION}]
    rows = []
    for para, ptext in paragraphs(text):
        for k, sent in enumerate(s for s in _SENT.split(ptext) if " shall " in f" {s.lower()} "):
            if NON_DUTY.search(sent) and not re.search(r"shall (?:ensure|take|provide|inform|draw|keep)", sent, re.I):
                continue
            who = addressee(sent)
            kind, rule = evidence_kind(sent, who)
            modality = "prohibition" if re.search(r"shall not\b", sent, re.I) else "duty"
            rows.append({"obligation_id": f"{provision_id}/p{para}/s{k + 1}", "provision_id": provision_id,
                         "paragraph": para, "text": sent[:700], "addressee": who, "modality": modality,
                         "evidence_kind": kind, "rule": rule, "status": "DRAFT",
                         "counsel_confirmed": False, "method": METHOD_VERSION})
    if not rows:
        rows.append({"obligation_id": f"{provision_id}/none", "provision_id": provision_id,
                     "paragraph": None, "text": None, "addressee": None, "modality": None,
                     "evidence_kind": "NONE", "rule": "no-duty-sentence", "status": "DRAFT",
                     "counsel_confirmed": False, "method": METHOD_VERSION})
    return rows


def provision_kind(rows: list[dict]) -> str:
    """Roll-up used by the ladder: the strongest sellable kind present."""
    kinds = {r["evidence_kind"] for r in rows}
    for k in ("OBSERVED", "SUBMITTED", "UNTRIAGED", "AUTHORITY", "NONE"):
        if k in kinds:
            return k
    return "NONE"


def selftest() -> list[str]:
    """Fail-closed fixtures. Returns a list of failures (empty = pass)."""
    fails = []
    bakery = ("Our bakery opens at 7am. Fresh bread is baked daily and the act of kneading "
              "takes skill. Customers shall enjoy the croissants, which are available until noon.")
    r = extract("TEST:bakery", bakery)
    if any(x["evidence_kind"] in ("OBSERVED", "SUBMITTED") for x in r):
        fails.append("bakery paragraph produced a sellable obligation")
    art50 = ("Article 50 Transparency obligations 2. Providers of AI systems, including general-purpose "
             "AI systems, generating synthetic audio, image, video or text content, shall ensure that the "
             "outputs of the AI system are marked in a machine-readable format and detectable as "
             "artificially generated or manipulated.")
    r = extract("TEST:50", art50)
    if not any(x["evidence_kind"] == "OBSERVED" and x["addressee"] == "provider" for x in r):
        fails.append("Art 50(2) marking duty not triaged OBSERVED/provider")
    qms = ("Article 17 Quality management system 1. Providers of high-risk AI systems shall put a quality "
           "management system in place that ensures compliance with this Regulation.")
    if not any(x["evidence_kind"] == "SUBMITTED" for x in extract("TEST:17", qms)):
        fails.append("QMS duty not triaged SUBMITTED")
    auth = "1. Member States shall designate at least one notifying authority."
    if not all(x["evidence_kind"] == "AUTHORITY" for x in extract("TEST:auth", auth)):
        fails.append("Member State duty not triaged AUTHORITY")
    defs = "Article 3 Definitions For the purposes of this Regulation, the following definitions apply: (1) 'AI system' means"
    if extract("TEST:3", defs)[0]["evidence_kind"] != "NONE":
        fails.append("definitions article not triaged NONE")
    return fails
