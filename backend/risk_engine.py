"""
Kavach AI - Risk Engine
-----------------------
Deterministic, rule-based signal detection + scoring.

Design intent (matches the product doc):
- No single signal is treated as automatic proof of fraud.
- Signals are combined into a score, then mapped to LOW / REVIEW / HIGH.
- Every result carries WHY (signals found), WHAT IT MEANS, and a safe
  NEXT ACTION in plain language - never a bare confidence percentage.
- This module has zero dependency on any LLM - it must work completely
  offline and deterministically, which matters a lot for a live demo.
"""

import re
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Signal definitions
# ---------------------------------------------------------------------------
# Each signal: (id, weight, compiled regex list, why-text-en, why-text-hi)

URGENCY_PATTERNS = [
    r"\bwithin\s+\d+\s*(minutes?|mins?|hours?|hrs?)\b",
    r"\bimmediately\b", r"\burgent(ly)?\b", r"\btoday only\b",
    r"\bact now\b", r"\bexpires? (today|soon|shortly)\b",
    r"\blast (chance|warning)\b", r"\bfinal notice\b",
    r"\b(within|in)\s+\d+\s*hours?\b",
]

THREAT_PATTERNS = [
    r"\baccount (will be|shall be|is going to be)?\s*(blocked|frozen|suspended|deactivated|closed)\b",
    r"\bblocked (today|within)\b",
    r"\bsim (will be)?\s*(deactivated|blocked|disconnected)\b",
    r"\bconnection will be disconnected\b",
    r"\blegal action\b", r"\bpenalty\b", r"\bfine of\b",
    r"\bkyc (has|is)?\s*expired\b", r"\bkyc will expire\b",
    r"\bcard will be blocked\b",
]

IMPERSONATION_PATTERNS = [
    r"\bwe are calling from your bank\b", r"\bi am calling from\b",
    r"\bcalling from (your )?bank\b", r"\bgovernment (department|official)\b",
    r"\bincome tax department\b", r"\brbi\b", r"\btrai\b",
    r"\bcourier (company|department)\b", r"\bcustomer (support|care) (executive|agent)\b",
    r"\btelecom (department|provider|operator)\b", r"\bbank (executive|representative|official)\b",
    r"\bfrom (paytm|phonepe|google pay|amazon|flipkart) support\b",
]

OTP_PIN_PATTERNS = [
    r"\botp\b", r"\bupi pin\b", r"\bpin number\b", r"\bcvv\b",
    r"\bone[\s-]?time password\b", r"\btell me the (otp|pin|code)\b",
    r"\bshare (your |the )?(otp|pin|password|cvv)\b",
    r"\bverification code\b", r"\bshare.{0,15}code you (just )?received\b",
]

PAYMENT_PATTERNS = [
    r"\bpay (immediately|now|to receive)\b", r"\bcomplete (the )?payment\b",
    r"\benter your (upi )?pin to (receive|claim|get)\b",
    r"\bprocessing fee\b", r"\brefund fee\b", r"\bunlock (your )?(reward|prize|money)\b",
    r"\bscan (this|the) qr code\b", r"\btransfer (money|funds|amount)\b",
]

REWARD_PATTERNS = [
    r"\bcongratulations\b", r"\byou (have )?won\b", r"\blucky (draw|winner)\b",
    r"\bcashback of\b", r"\bclaim your (reward|prize|gift)\b", r"\bfree (gift|reward)\b",
]

LINK_ACTION_PATTERNS = [
    r"\bclick (here|this|the link|below)\b",
    r"\b(using|via|through) (this|the) link\b",
    r"\bcomplete verification\b.{0,30}\blink\b",
    r"\bvisit (this|the) link\b", r"\bupdate (your )?details?\b.{0,20}\blink\b",
    r"\bdownload (this )?(app|apk)\b.{0,20}(here|now|link)\b",
]

SENSITIVE_INFO_PATTERNS = [
    r"\baadhaar\b", r"\bpan (card|number)\b", r"\bbank account number\b",
    r"\bpassword\b", r"\bidentity proof\b", r"\bdate of birth\b",
]

# URL shorteners commonly abused in scams (non-exhaustive, demo-scope list)
URL_SHORTENERS = {
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "is.gd", "cutt.ly",
    "rb.gy", "shorturl.at", "tiny.cc", "ow.ly", "buff.ly",
}

# A small demo allowlist of official domains for well-known Indian
# organisations. In production this would be a maintained, larger dataset
# (and/or a reputation API) - kept small and explicit here for transparency.
KNOWN_ORG_DOMAINS = {
    "sbi": ["onlinesbi.sbi", "sbi.co.in"],
    "icici": ["icicibank.com"],
    "hdfc": ["hdfcbank.com"],
    "axis": ["axisbank.com"],
    "pnb": ["pnbindia.in"],
    "rbi": ["rbi.org.in"],
    "income tax": ["incometax.gov.in"],
    "irctc": ["irctc.co.in"],
    "paytm": ["paytm.com"],
    "phonepe": ["phonepe.com"],
    "google pay": ["pay.google.com"],
    "amazon": ["amazon.in", "amazon.com"],
    "flipkart": ["flipkart.com"],
    "india post": ["indiapost.gov.in"],
}


def _compile(patterns):
    return [re.compile(p, re.IGNORECASE) for p in patterns]


_COMPILED = {
    "urgency": _compile(URGENCY_PATTERNS),
    "threat": _compile(THREAT_PATTERNS),
    "impersonation": _compile(IMPERSONATION_PATTERNS),
    "otp_pin": _compile(OTP_PIN_PATTERNS),
    "payment": _compile(PAYMENT_PATTERNS),
    "reward": _compile(REWARD_PATTERNS),
    "link_action": _compile(LINK_ACTION_PATTERNS),
    "sensitive_info": _compile(SENSITIVE_INFO_PATTERNS),
}

# Weight of each signal category towards the overall score (0-100 scale)
WEIGHTS = {
    "urgency": 12,
    "threat": 15,
    "impersonation": 10,
    "otp_pin": 30,
    "payment": 20,
    "reward": 10,
    "link_action": 12,
    "sensitive_info": 15,
    "url_mismatch": 30,
    "url_shortener": 12,
    "url_no_https": 6,
    "url_ip_host": 20,
    "url_many_subdomains": 10,
}

THRESHOLD_REVIEW = 20
THRESHOLD_HIGH = 45


@dataclass
class Signal:
    id: str
    why_en: str
    why_hi: str


@dataclass
class AnalysisResult:
    risk_level: str            # "LOW" | "REVIEW" | "HIGH"
    score: int
    signals: list = field(default_factory=list)   # list[Signal]
    action_en: str = ""
    action_hi: str = ""
    extra: dict = field(default_factory=dict)


_WHY_TEXT = {
    "urgency": (
        "The message creates urgency, pressuring you to act fast.",
        "यह संदेश जल्दी करने का दबाव बना रहा है।",
    ),
    "threat": (
        "It threatens a consequence, like blocking your account or SIM.",
        "यह धमकी देता है, जैसे खाता या सिम बंद करना।",
    ),
    "impersonation": (
        "The sender claims to represent a bank, government office, or company.",
        "भेजने वाला बैंक, सरकारी विभाग या कंपनी होने का दावा कर रहा है।",
    ),
    "otp_pin": (
        "It asks for an OTP, UPI PIN, password, or verification code.",
        "यह OTP, UPI पिन, पासवर्ड या सत्यापन कोड मांग रहा है।",
    ),
    "payment": (
        "It asks you to make a payment or enter your PIN to 'receive' something.",
        "यह भुगतान करने या कुछ 'पाने' के लिए पिन डालने को कह रहा है।",
    ),
    "reward": (
        "It offers an unexpected prize, cashback, or reward.",
        "यह एक अप्रत्याशित इनाम या कैशबैक देने का दावा करता है।",
    ),
    "link_action": (
        "It pushes you to click a link or download something right away.",
        "यह तुरंत लिंक पर क्लिक करने या कुछ डाउनलोड करने को कह रहा है।",
    ),
    "sensitive_info": (
        "It asks for sensitive personal or financial information.",
        "यह संवेदनशील व्यक्तिगत या वित्तीय जानकारी मांग रहा है।",
    ),
    "url_mismatch": (
        "The website address does not match the organisation it claims to be.",
        "वेबसाइट का पता उस संस्था से मेल नहीं खाता जिसका वह दावा करता है।",
    ),
    "url_shortener": (
        "The link uses a URL shortener, which can hide the real destination.",
        "यह लिंक एक छोटा किया गया URL है, जो असली पता छुपा सकता है।",
    ),
    "url_no_https": (
        "The website does not use a secure (https) connection.",
        "यह वेबसाइट सुरक्षित (https) कनेक्शन का उपयोग नहीं करती।",
    ),
    "url_ip_host": (
        "The link points to a raw number-based address instead of a normal website name.",
        "यह लिंक सामान्य वेबसाइट नाम की बजाय सीधे नंबर-आधारित पते पर जाता है।",
    ),
    "url_many_subdomains": (
        "The web address has an unusually complicated structure.",
        "इस वेब पते की संरचना असामान्य रूप से जटिल है।",
    ),
}


def _add_signal(found: list, sid: str):
    en, hi = _WHY_TEXT[sid]
    found.append(Signal(id=sid, why_en=en, why_hi=hi))


def analyze_text(text: str, source_type: str = "message") -> AnalysisResult:
    """Analyze free text (message body, OCR output, or call transcript)."""
    text = text or ""
    score = 0
    found: list = []
    matched_ids = set()

    for sid, patterns in _COMPILED.items():
        for pat in patterns:
            if pat.search(text):
                if sid not in matched_ids:
                    score += WEIGHTS[sid]
                    _add_signal(found, sid)
                    matched_ids.add(sid)
                break

    # Calls get a small extra weight on OTP requests - a live human asking
    # for an OTP during a call is a very strong real-world signal.
    if source_type == "call" and "otp_pin" in matched_ids:
        score += 10

    return _finalize(score, found)


def _finalize(score: int, found: list) -> AnalysisResult:
    score = min(score, 100)
    if score >= THRESHOLD_HIGH:
        level = "HIGH"
    elif score >= THRESHOLD_REVIEW:
        level = "REVIEW"
    else:
        level = "LOW"

    action_en, action_hi = _next_action(level, found)
    return AnalysisResult(risk_level=level, score=score, signals=found,
                           action_en=action_en, action_hi=action_hi)


def _next_action(level: str, found: list):
    ids = {s.id for s in found}

    if level == "HIGH":
        if "otp_pin" in ids:
            return (
                "Do not share the OTP, PIN, or password with anyone. End the call or ignore the "
                "message, then contact the organisation using the number on their official "
                "website or app.",
                "OTP, पिन या पासवर्ड किसी के साथ साझा न करें। कॉल काटें या संदेश को नज़रअंदाज़ करें, "
                "फिर संस्था से उनकी आधिकारिक वेबसाइट या ऐप में दिए नंबर से संपर्क करें।",
            )
        if "payment" in ids or "reward" in ids:
            return (
                "Do not make any payment or scan the QR code. Verify the offer independently "
                "through the organisation's official app or website.",
                "कोई भुगतान न करें और QR कोड स्कैन न करें। संस्था के आधिकारिक ऐप या वेबसाइट से इसकी पुष्टि करें।",
            )
        return (
            "Do not click the link or share any information. Open the organisation's official "
            "app or website yourself and verify this message.",
            "लिंक पर क्लिक न करें और कोई जानकारी साझा न करें। खुद संस्था की आधिकारिक ऐप या वेबसाइट खोलकर जांच करें।",
        )

    if level == "REVIEW":
        return (
            "We found some warning signs, but not enough to be certain. Verify this through an "
            "official source before acting, or ask someone you trust.",
            "हमें कुछ चेतावनी के संकेत मिले हैं, पर पूरी तरह निश्चित नहीं हैं। कार्रवाई करने से पहले किसी "
            "आधिकारिक स्रोत से पुष्टि करें, या किसी भरोसेमंद व्यक्ति से पूछें।",
        )

    return (
        "No major warning signs were found in what you shared. If anything still feels off, "
        "it's always fine to verify independently.",
        "जो जानकारी आपने साझा की उसमें कोई बड़ा खतरे का संकेत नहीं मिला। फिर भी अगर कुछ असामान्य लगे, "
        "तो स्वतंत्र रूप से पुष्टि करना हमेशा ठीक है।",
    )


# ---------------------------------------------------------------------------
# URL-specific analysis
# ---------------------------------------------------------------------------

def analyze_url(url: str, claimed_org: Optional[str] = None) -> AnalysisResult:
    from url_utils import inspect_url

    url = (url or "").strip()
    score = 0
    found: list = []

    info = inspect_url(url)

    if info["is_ip_host"]:
        score += WEIGHTS["url_ip_host"]
        _add_signal(found, "url_ip_host")

    if info["is_shortener"]:
        score += WEIGHTS["url_shortener"]
        _add_signal(found, "url_shortener")

    if not info["is_https"]:
        score += WEIGHTS["url_no_https"]
        _add_signal(found, "url_no_https")

    if info["subdomain_count"] >= 3:
        score += WEIGHTS["url_many_subdomains"]
        _add_signal(found, "url_many_subdomains")

    mismatch_org = info["mentions_org_but_mismatched"]
    if mismatch_org:
        score += WEIGHTS["url_mismatch"]
        _add_signal(found, "url_mismatch")

    result = _finalize(score, found)
    result.extra["domain"] = info["domain"]
    result.extra["mismatch_org"] = mismatch_org
    return result


def combine(*results: AnalysisResult) -> AnalysisResult:
    """Combine several AnalysisResult objects (e.g. text + url) into one,
    taking the higher risk level and merging signals without duplicates."""
    total_score = 0
    seen = set()
    merged: list = []
    for r in results:
        total_score += r.score
        for s in r.signals:
            if s.id not in seen:
                seen.add(s.id)
                merged.append(s)
    return _finalize(total_score, merged)
