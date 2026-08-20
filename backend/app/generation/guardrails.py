"""Prompt injection and jailbreak detection for Eva-AI.

This module provides a deterministic, regex-based first-pass filter that runs
BEFORE retrieval and LLM calls. It catches adversarial inputs that attempt to
override the grounding constraints defined in the system prompt.

Constitution Principle V: Adversarial robustness must be implemented at the
application layer, not relied upon from the LLM alone.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Injection / jailbreak pattern library
# ---------------------------------------------------------------------------
# Each pattern is a compiled regex. Any match = injection detected.
# Patterns are case-insensitive and match across word boundaries where needed.

_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    # Classic instruction-override phrases
    re.compile(r"ignore\s+(all\s+)?(previous|above|prior|earlier)\s+instructions?", re.I),
    re.compile(r"disregard\s+(all\s+)?(previous|above|prior|earlier)\s+instructions?", re.I),
    re.compile(
        r"forget\s+(all\s+)?(previous|above|prior|earlier|your)\s+(instructions?|rules?|context)",
        re.I,
    ),
    re.compile(
        r"override\s+(your\s+)?(previous\s+)?(instructions?|rules?|constraints?|prompt)", re.I
    ),
    re.compile(
        r"bypass\s+(your\s+)?(safety|security|restrictions?|constraints?|rules?|guidelines?)", re.I
    ),
    # Persona-switching / DAN patterns
    re.compile(r"\byou\s+are\s+now\b", re.I),
    re.compile(r"\bact\s+as\s+(if\s+you\s+(are|were)|a\s+different)", re.I),
    re.compile(r"\bpretend\s+(you\s+(are|have|don'?t)|there\s+are\s+no)", re.I),
    re.compile(r"\bDAN\b"),  # "Do Anything Now" jailbreak tag
    re.compile(r"\bjailbreak\b", re.I),
    re.compile(r"\bdev(eloper)?\s+mode\b", re.I),
    re.compile(r"\bunrestricted\s+mode\b", re.I),
    # Repeat / print / reveal system prompt
    re.compile(r"\brepeat\b.{0,30}\b(system\s+prompt|above|instructions?)\b", re.I),
    re.compile(r"\bprint\s+(your\s+)?(system\s+)?prompt\b", re.I),
    re.compile(r"\bshow\s+(me\s+)?(your\s+)?(system\s+)?prompt\b", re.I),
    re.compile(r"\breveal\s+(your\s+)?(instructions?|system\s+prompt|constraints?)\b", re.I),
    re.compile(r"\bwhat\s+(is|are|were)\s+your\s+(original\s+)?instructions?\b", re.I),
    # "As a [role]" safety-bypass framing
    re.compile(
        r"\bas\s+a\s+(medical\s+student|doctor|nurse|researcher|test|demo)\b.{0,60}(no\s+restrictions?|without\s+guidelines?|pretend)",
        re.I,
    ),
    # Injection delimiter tricks
    re.compile(r"---\s*system\s*:", re.I),
    re.compile(r"\[system\]", re.I),
    re.compile(r"<\s*system\s*>", re.I),
    re.compile(r"\bSYSTEM\s+PROMPT\s*:", re.I),
    # Role-flip / "must answer without" commands
    re.compile(
        r"\byou\s+(must|should|will)\s+(now\s+)?(answer|respond|reply)\s+without\s+(restrictions?|guidelines?|rules?)",
        re.I,
    ),
    re.compile(r"\b(must|should|will)\s+now\s+(answer|respond|reply)\s+without\b", re.I),
    re.compile(
        r"\bnow\s+(answer|respond|reply)\s+without\s+(restrictions?|guidelines?|rules?)", re.I
    ),
    re.compile(
        r"\banswer\s+without\s+(any\s+)?(restrictions?|guidelines?|rules?|constraints?)\b", re.I
    ),
    re.compile(r"\bno\s+longer\s+(bound|restricted|constrained|limited)\s+by\b", re.I),
    # Forget-your-X-completely variants
    re.compile(r"\bforget\b.{0,30}\b(instructions?|rules?|context|constraints?|guidelines?)", re.I),
]

# Minimum query length below which we don't bother pattern-matching
_MIN_QUERY_LENGTH = 3

# Maximum query length; anything longer is suspicious
_MAX_QUERY_LENGTH = 1000


def detect_prompt_injection(query: str) -> bool:
    """Return True if the query contains a known prompt-injection or jailbreak pattern.

    This is a fast, deterministic, regex-based heuristic. It runs before any
    retrieval or LLM call to short-circuit adversarial inputs cheaply.

    Args:
        query: The raw user query string.

    Returns:
        True  → injection detected; the request should be refused.
        False → no injection pattern found; safe to proceed.
    """
    if not query or len(query.strip()) < _MIN_QUERY_LENGTH:
        return False

    for pattern in _INJECTION_PATTERNS:
        if pattern.search(query):
            logger.warning(
                "Prompt injection detected. Pattern=%r query_prefix=%r",
                pattern.pattern,
                query[:80],
            )
            return True

    return False


_GREETING_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"^(hi|hello|hey|greetings|good morning|good afternoon|good evening|howdy)\b[!.? ]*$", re.I
    ),
    re.compile(
        r"^(who are you|what are you|what do you do|how can you help(?: me)?|"
        r"can you help(?: me)?|help me|what is your purpose|what can you do)\s*[?!.]*$",
        re.I,
    ),
    re.compile(
        r"^(مرحبا|أهلا|اهلا|السلام عليكم|صباح الخير|مساء الخير|من أنت|من انت|ماذا تفعل|كيف تساعدني|ما هي قدراتك)\??$",
        re.I,
    ),
]

GREETING_RESPONSE_EN = (
    "Hello! I am Eva-AI, a Clinical Decision Support assistant specialized in **adrenal insufficiency identification, diagnosis, crisis management, and sick-day dosing rules** strictly based on **NICE guideline NG243**.\n\n"
    "How can I assist you with clinical guideline evidence today?"
)

GREETING_RESPONSE_AR = (
    "مرحباً! أنا إيفا (Eva-AI)، مساعدة دعم القرار السريري المتخصصة في **تحديد وإدارة قصور الغدة الكظرية وإرشادات جرعات أيام المرض وحالات الطوارئ** استناداً حصرياً إلى **إرشادات NICE NG243**.\n\n"
    "كيف يمكنني مساعدتك اليوم في الأدلة والإرشادات السريرية؟"
)


def is_greeting(query: str) -> bool:
    """Return True if the query is a conversational greeting or capability inquiry."""
    cleaned = re.sub(r"\s+", " ", query.strip())
    return any(pattern.match(cleaned) for pattern in _GREETING_PATTERNS)


def sanitize_query(query: str) -> str:
    """Lightly sanitize the query for safe logging and downstream use.

    Strips leading/trailing whitespace and collapses internal runs of
    whitespace to a single space. Does NOT alter the semantic content of
    legitimate clinical queries.
    """
    return re.sub(r"\s+", " ", query.strip())


# ---------------------------------------------------------------------------
# Dosage & Medication Recommendation Refusal Guard (Day 3 Update)
# ---------------------------------------------------------------------------

DOSAGE_REFUSAL_MESSAGE_EN = (
    "I am not authorized to provide specific drug dosages, medication recommendations, "
    "or prescribing instructions. Eva AI is a clinical decision-support tool, not a prescribing clinician. "
    "For patient safety, all dosing decisions and drug recommendations must be evaluated by a licensed "
    "healthcare professional, or referenced directly from the official NICE NG243 guidelines."
)

DOSAGE_REFUSAL_MESSAGE_AR = (
    "أنا غير مخول لتقديم جرعات الأدوية، أو توصيات العلاج، أو تعليمات الوصفات الطبية. "
    "إيفا (Eva AI) هي أداة دعم قرار سريري وليست طبيباً معالجاً. لسلامة المرضى، يجب اتخاذ "
    "جميع قرارات الجرعات وتوصيات الأدوية من قِبل ممارس صحي مرخص، أو الرجوع إليها مباشرة من دليل إرشادات NICE NG243 الرسمي."
)

_DOSAGE_MED_KEYWORDS = [
    # English keywords
    "dose", "dosage", "dosing", "mg", "microgram", "mcg", "nmol", "nmol/L",
    "milligram", "taper", "tapering", "regimen", "maintenance", "sick-day",
    "sick day", "stress dose", "how much", "what amount", "should i take",
    "can i take", "prescrib", "recommend", "medication", "drug", "steroid",
    "hydrocortisone", "fludrocortisone", "prednisolone", "dexamethasone",
    "corticosteroid",
    # Arabic keywords
    "جرع", "ملغ", "ميكروغرام", "هيدروكورتيزون", "فلودروكورتيزون", "بريدنيزولون",
    "ديكساميثازون", "ستيرويد", "دواء", "أدوية", "علاج دوائي", "وصف"
]


_CLINICAL_SCENARIO_PATTERNS = [
    r"\b\d+[- ]year[- ]old\b",
    r"\bpresents?\s+(?:with|to)\b",
    r"\bdiagnos(?:ed|is)\b",
    r"\bundergoing\b",
    r"\bpatient\s+with\b",
    r"\bperson\s+with\b",
    r"\bmother\s+with\b",
    r"\bemergency\s+management\b",
    r"\bmanagement\s+protocol\b",
    r"\bprotocol\s+for\b",
    r"\brules\s+for\b",
    r"\bsynacthen\b",
    r"\bcortisol\b",
    r"\binvestigation\b",
    r"\bfever\b",
    r"\bvomit\b",
    r"\btablets?\b",
    r"\bgrams?\b",
    r"\bwithhold\b",
    r"\bhpa\s+axis\b",
    r"\bsurgery\b",
    r"\banaesthesia\b",
    r"\banesthesia\b",
    r"\bmaterials\b",
    r"\bwhy\s+and\s+for\s+how\s+long\b",
    r"\bwhen\s+should\b",
    r"\bdoes\s+a\s+patient\b",
    r"\bhow\s+many\s+emergency\b",
    r"(?:مريض|مشخص|يعاني|إصابة|أيام\s+المرض\s+عند|إسعافي\s+فوري)",
]


def is_dosage_or_medication_query(query: str) -> bool:
    """Return True if the query is a direct dosage/prescribing inquiry without clinical scenario context."""
    if not query:
        return False
    lower_query = query.lower()
    if not any(k in lower_query for k in _DOSAGE_MED_KEYWORDS):
        return False
    # If the query contains rich clinical scenario / guideline lookup context, allow retrieval & grounded response
    if any(re.search(pat, lower_query, re.IGNORECASE) for pat in _CLINICAL_SCENARIO_PATTERNS):
        return False
    return True

