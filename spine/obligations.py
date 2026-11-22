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

METHOD_VERSION = "obligations/0.2.0"   # 0.2: English "must"; zh/ja/ko/es duty markers

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

_EN_DUTY = re.compile(r"\b(?:shall|must|is required to|are required to)\b", re.I)
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
    low = sentence.lower()
    m = _EN_DUTY.search(low)
    head = (low[:m.start()] if m else low)[-200:]
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
    lang = language(text)
    if lang != "en":
        return extract_ml(provision_id, text, lang)
    head = (title_hint or text[:120]).strip()
    if NONE_TITLES.search(head):
        return [{"obligation_id": f"{provision_id}/none", "provision_id": provision_id,
                 "paragraph": None, "text": None, "addressee": None, "modality": None,
                 "evidence_kind": "NONE", "rule": "title:" + NONE_TITLES.search(head).group(0).strip().lower(),
                 "status": "DRAFT", "counsel_confirmed": False, "method": METHOD_VERSION}]
    rows = []
    for para, ptext in paragraphs(text):
        for k, sent in enumerate(s for s in _SENT.split(ptext) if _EN_DUTY.search(s)):
            if NON_DUTY.search(sent) and not re.search(r"shall (?:ensure|take|provide|inform|draw|keep)", sent, re.I):
                continue
            who = addressee(sent)
            kind, rule = evidence_kind(sent, who)
            modality = "prohibition" if re.search(r"\b(?:shall|must|may) not\b", sent, re.I) else "duty"
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


# ── non-English cuts (zh, ja, ko, es) ───────────────────────────────────────
def language(text: str) -> str:
    t = text[:2000]
    if re.search(r"[\uac00-\ud7a3]", t):
        return "ko"
    if re.search(r"[\u3040-\u30ff]", t):
        return "ja"
    if re.search(r"[\u4e00-\u9fff]", t):
        return "zh"
    if re.search(r"\b(?:artículo|deberá|deberán|el|la|los|las|del|ley)\b", t, re.I) and re.search(r"[áéíóúñ]", t):
        return "es"
    return "en"


ML = {
    "zh": {"duty": r"应当|必须|不得|禁止|严禁|應當|必須|(?<![適相回反對供因效感])應(?!用)|須",
           "prohib": r"不得|禁止|严禁",
           "split": r"(?<=[。；;])|\n",
           "none": r"^\s*第\s*[一二三四五六七八九十百零〇\d]+\s*[条條]\s*(?:[（(]?(?:定义|定義|目的)[）)]?)|本(?:法|办法|规定|條例|条例|法律)自.{0,30}(?:起施行|施行)",
           "auth": ["国家网信部门", "网信部门", "国务院", "人民政府", "有关部门", "主管部门", "主管机关", "主管機關", "政府", "中央", "委员会", "委員會", "国家"],
           "who": [("个人信息处理者", "controller"), ("個人資料", "controller"), ("非公務機關", "controller"), ("公務機關", "AUTHORITY"),
                   ("网络运营者", "network_operator"), ("服务提供者", "provider"), ("提供者", "provider"), ("使用者", "user"),
                   ("运营者", "network_operator"), ("处理者", "processor"), ("数据处理者", "controller")],
           "obs": r"公开|公示|公布|公告|标识|標示|显著|告知|明示|公開|說明|告知當事人",
           "sub": r"记录|記錄|备案|備案|评估|評估|报告|報告|检测|审计|审核|保存|日志|制度|措施|演练|培训|檢查"},
    "ja": {"duty": r"しなければならない|してはならない|ならない|ものとする",
           "prohib": r"てはならない",
           "split": r"(?<=。)|\n",
           "none": r"^\s*第[一二三四五六七八九十百]+条\s*[（(](?:目的|定義|施行期日|適用範囲)[）)]|^附則",
           "auth": ["国は", "国及び地方公共団体", "地方公共団体", "政府", "行政機関", "委員会", "本部", "内閣", "大臣"],
           "who": [("個人情報取扱事業者", "controller"), ("仮名加工情報取扱事業者", "controller"), ("匿名加工情報取扱事業者", "controller"),
                   ("個人関連情報取扱事業者", "controller"), ("事業者", "undertaking"), ("研究開発機関", "research_body"), ("国民", "public")],
           "obs": r"公表|公開|表示|明示|本人に通知|本人に対し|通知し|知り得る状態",
           "sub": r"記録|報告|届出|評価|監査|保存|体制|措置を講じ|管理|作成"},
    "ko": {"duty": r"하여야\s*한다|해야\s*한다|아니\s*된다|하여야\s*하며",
           "prohib": r"아니\s*된다",
           "split": r"(?<=다\.)|\n",
           "none": r"^\s*제\d+조(?:의\d+)?\((?:목적|정의|시행일)\)",
           "auth": ["정부", "국가", "장관", "지방자치단체", "위원회", "보호위원회", "대통령"],
           "who": [("개인정보처리자", "controller"), ("인공지능사업자", "provider"), ("사업자", "provider"), ("수탁자", "processor"), ("국내대리인", "authorised_representative")],
           "obs": r"공개|표시|고지|알려야|알리|게시|공표|통지",
           "sub": r"기록|보관|신고|제출|평가|점검|수립|조치|관리|보고"},
    "es": {"duty": r"\b(?:deberá|deberán|debe|deben|está obligad[oa]|están obligad[oa]s|se prohíbe|no podrá|no podrán)\b",
           "prohib": r"\b(?:se prohíbe|no podrá|no podrán)\b",
           "split": r"(?<=[.;:])\s+(?=[A-ZÁÉÍÓÚÑ(])",
           "none": r"^(?:artículo\s+\w+\.?-?\s*)?(?:objeto|definiciones|ámbito de aplicación|vigencia)\b",
           "auth": ["la agencia", "el ministerio", "el estado", "la autoridad", "las entidades de la administración pública",
                    "la secretaría", "el consejo", "el poder ejecutivo", "la presidencia"],
           "who": [("el responsable", "controller"), ("los responsables", "controller"), ("el encargado", "processor"),
                   ("proveedor", "provider"), ("desarrollador", "provider"), ("implementador", "deployer"), ("titular", "data_subject")],
           "obs": r"publicar|publicidad|informar al titular|informar a los titulares|poner a disposición del público|transparencia|etiquet|rotul",
           "sub": r"registro|evaluación|reportar|notificar a la agencia|documentar|conservar|implementar|adoptar medidas|auditor"},
}


def _who_ml(head: str, cfg: dict, lang: str) -> str:
    """Subject-first languages: the addressee is the EARLIEST actor named before the duty
    marker (zh/ja/ko/es put the subject first; later actors are objects, e.g. 委员会に報告)."""
    h = head.lower() if lang == "es" else head
    best, pos = "UNRESOLVED", None
    cands = [(n, "AUTHORITY") for n in cfg["auth"]] + list(cfg["who"])
    for needle, tag in sorted(cands, key=lambda c: -len(c[0])):
        p = h.find(needle)
        if p >= 0 and (pos is None or p < pos):
            best, pos = tag, p
    return best


def extract_ml(provision_id: str, text: str, lang: str) -> list[dict]:
    cfg = ML[lang]
    base = {"provision_id": provision_id, "status": "DRAFT", "counsel_confirmed": False, "method": METHOD_VERSION,
            "language": lang}
    if re.search(cfg["none"], text.strip()[:200], re.I) and not re.search(cfg["duty"], text[200:], re.I):
        return [{**base, "obligation_id": f"{provision_id}/none", "paragraph": None, "text": None, "addressee": None,
                 "modality": None, "evidence_kind": "NONE", "rule": f"title:{lang}"}]
    sents = [x.strip() for x in re.split(cfg["split"], text) if x and x.strip()]
    rows = []
    for k, sent in enumerate(sents):
        m = re.search(cfg["duty"], sent, re.I)
        if not m:
            continue
        who = _who_ml(sent[:m.start()], cfg, lang)
        if who == "AUTHORITY":
            kind, rule = "AUTHORITY", "addressee-is-public-body"
        elif re.search(cfg["obs"], sent, re.I):
            kind, rule = "OBSERVED", f"{lang}:public-trace"
        elif re.search(cfg["sub"], sent, re.I):
            kind, rule = "SUBMITTED", f"{lang}:internal-record"
        else:
            kind, rule = "UNTRIAGED", "no-rule-matched"
        modality = "prohibition" if re.search(cfg["prohib"], sent, re.I) else "duty"
        rows.append({**base, "obligation_id": f"{provision_id}/s{k + 1}", "paragraph": None, "text": sent[:700],
                     "addressee": who, "modality": modality, "evidence_kind": kind, "rule": rule})
    if not rows:
        rows.append({**base, "obligation_id": f"{provision_id}/none", "paragraph": None, "text": None, "addressee": None,
                     "modality": None, "evidence_kind": "NONE", "rule": "no-duty-sentence"})
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
    zh = "第十七条　提供者应当按照规定对生成合成内容添加显式标识。"
    if not any(x["evidence_kind"] == "OBSERVED" and x["addressee"] == "provider" for x in extract("TEST:zh", zh)):
        fails.append("zh labelling duty not OBSERVED/provider")
    ja = "第二十六条　個人情報取扱事業者は、その取り扱う個人データの漏えいが生じたときは、委員会に報告しなければならない。"
    if not any(x["evidence_kind"] == "SUBMITTED" for x in extract("TEST:ja", ja)):
        fails.append("ja breach report not SUBMITTED")
    ko = "제31조(투명성 확보 의무) ① 인공지능사업자는 고영향 인공지능을 이용한 제품 또는 서비스를 제공하려는 경우 이를 이용자에게 사전에 고지하여야 한다."
    if not any(x["evidence_kind"] == "OBSERVED" and x["addressee"] == "provider" for x in extract("TEST:ko", ko)):
        fails.append("ko notice duty not OBSERVED/provider")
    cn_auth = "第八条　国家网信部门负责统筹协调网络安全工作。国务院电信主管部门应当依照本法履行职责。"
    if any(x["evidence_kind"] in ("OBSERVED", "SUBMITTED") for x in extract("TEST:cnauth", cn_auth)):
        fails.append("zh authority duty sold as private obligation")
    if extract("TEST:zhbakery", "我们的面包店早上七点开门，欢迎光临。")[0]["evidence_kind"] != "NONE":
        fails.append("zh bakery text produced an obligation")
    return fails
