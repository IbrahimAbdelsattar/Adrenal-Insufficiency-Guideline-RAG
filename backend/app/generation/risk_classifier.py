"""Clinical Input-Risk Classification Module.

Triage and classify incoming clinical queries into risk tiers prior to generation:
- EMERGENCY_CRITICAL: Acute adrenal crisis, shock, severe vomiting with collapse.
- SICK_DAY_STRESS: Fever, physiological stress, minor/major surgery, sick-day rules.
- PEDIATRIC_SPECIALIST: Pediatric/neonatal considerations requiring BSPED protocols.
- STEROID_WITHDRAWAL: Glucocorticoid weaning, tapering, and HPA axis recovery.
- ADVERSARIAL_SECURITY: Jailbreak attempts, prompt injection, roleplay bypasses.
- OUT_OF_SCOPE: Non-endocrinology medical queries and non-medical prompts.
- ROUTINE_CLINICAL: Routine replacement, monitoring, education, and diagnosis.
"""

from __future__ import annotations

import re
from typing import Any

from backend.app.generation.guardrails import detect_prompt_injection
from backend.app.models import InputRiskAssessment, InputRiskTier
from backend.app.retrieval.scope import is_clinical_domain_query

# Regular expressions for risk factor detection
_EMERGENCY_PATTERNS = [
    r"\b(?:adrenal\s+crisis|acute\s+crisis|hypoadrenal\s+crisis|addisonian\s+crisis)\b",
    r"\b(?:circulatory\s+collapse|hypovolemic\s+shock|cardiogenic\s+shock|septic\s+shock)\b",
    r"\b(?:unconscious|unresponsive|comatose|stupor|profound\s+lethargy|collapse)\b",
    r"\b(?:bp\s*(?:<|under|less\s+than)?\s*(?:[5-8]\d|90)\s*/\s*(?:[3-5]\d|60))\b",
    r"\b(?:severe\s+hypotension|refractory\s+hypotension|postural\s+collapse)\b",
    r"\b(?:persistent\s+vomiting|cannot\s+retain|unable\s+to\s+keep|intractable\s+vomiting)\b",
    r"\b(?:emergency\s+injection|stat\s+dose|100\s*mg\s+(?:im|iv|intramuscular|intravenous))\b",
    r"\b(?:hypoglyc[ae]mic\s+(?:seizure|convulsion|coma))\b",
    # Arabic Emergency Expressions
    r"(?:أزمة\s+كظرية|هبوط\s+حاد|صدمة\s+وعائية|غيبوبة|فقدان\s+الوعي|انهيار|إغماء)",
    r"(?:استفراغ\s+مستمر|قيء\s+شديد|عاجز\s+عن\s+البلع|حقن\s+إسعافي|جرعة\s+طارئة)",
]

_SICK_DAY_PATTERNS = [
    r"\b(?:sick\s*day|sick-day|stress\s+dose|physiological\s+stress)\b",
    r"\b(?:fever|pyrexia|temperature\s*(?:>=?|>|\b)\s*(?:38|39|40|100|101|102|103|104))\b",
    r"\b(?:gastroenteritis|norovirus|covid|influenza|flu|chest\s+infection)\b",
    r"\b(?:surgery|surgical|pre-op|post-op|anaesthesia|anesthesia|colonoscopy|endoscopy)\b",
    r"\b(?:dental\s+(?:extraction|surgery|procedure))\b",
    r"\b(?:trauma|fracture|burns|injury)\b",
    r"\b(?:pregnancy|labour|labor|delivery|third\s+trimester)\b",
    # Arabic Sick-Day Expressions
    r"(?:أيام\s+المرض|حمى|سخونة|ارتفاع\s+درجة\s+الحرارة|عملية\s+جراحية|خلع\s+ضرس|ولادة)",
]

_PEDIATRIC_PATTERNS = [
    r"\b(?:pediatric|paediatric|child|children|infant|toddler|neonate|baby|young\s+person|adolescent)\b",
    r"\b(?:bsped|body\s+surface\s+area|bsa|mg/m2|growth\s+velocity)\b",
    # Arabic Pediatric Expressions
    r"(?:طفل|أطفال|رضيع|حديث\s+الولادة|جرعة\s+الأطفال)",
]

_WITHDRAWAL_PATTERNS = [
    r"\b(?:withdrawal|wean|weaning|taper|tapering|discontinu(?:e|ing)|reduc(?:e|ing)\s+steroid)\b",
    r"\b(?:hpa\s+axis\s+recovery|secondary\s+ai\s+recovery|long-term\s+steroid\s+cessation)\b",
    # Arabic Withdrawal Expressions
    r"(?:سحب\s+الستيرويد|تخفيض\s+الجرعة|إيقاف\s+الكورتيزون|فطام\s+الستيرويد)",
]

_OUT_OF_SCOPE_NON_ENDOCRINE = [
    r"\b(?:myocardial\s+infarction|stemi|nstemi|angina|coronary|troponin)\b",
    r"\b(?:asthma\s+exacerbation|copd|bronchospasm|salbutamol|inhaler)\b",
    r"\b(?:type\s+2\s+diabetes|metformin|insulin\s+glargine|glp-1|semaglutide|hba1c)\b",
    r"\b(?:appendicitis|cholecystitis|bowel\s+obstruction|laparoscopy)\b",
    r"\b(?:stroke|tpa|thrombectomy|hemiparesis|ischemic\s+stroke)\b",
    r"\b(?:capital\s+of|weather\s+in|recipe|python\s+code|write\s+a\s+poem)\b",
]


def classify_input_risk(
    query: str,
    history: list[dict[str, Any]] | None = None,
) -> InputRiskAssessment:
    """Evaluate an incoming user query and classify its clinical/operational risk tier."""
    cleaned_query = (query or "").strip().lower()

    # 1. Adversarial & Security Threat Detection
    if detect_prompt_injection(query):
        return InputRiskAssessment(
            tier=InputRiskTier.ADVERSARIAL_SECURITY,
            is_emergency=False,
            risk_score=1.0,
            detected_risk_factors=["Prompt Injection / Adversarial Jailbreak Pattern"],
            recommended_triage_action="Bypass LLM and refuse immediately (Fail-Closed).",
            safety_banner="🛡️ SECURITY GUARDRAIL: Request triggered safety inspection. Prompt refused.",
        )

    # 2. Acute Emergency Critical Detection
    emergency_matches = [
        pattern
        for pattern in _EMERGENCY_PATTERNS
        if re.search(pattern, cleaned_query, re.IGNORECASE)
    ]
    if emergency_matches:
        return InputRiskAssessment(
            tier=InputRiskTier.EMERGENCY_CRITICAL,
            is_emergency=True,
            risk_score=0.95,
            detected_risk_factors=[
                "Acute Adrenal Crisis Indicators",
                f"Matched {len(emergency_matches)} emergency pattern(s)",
            ],
            recommended_triage_action=(
                "IMMEDIATE EMERGENCY ACTION REQUIRED: Administer 100 mg parenteral hydrocortisone "
                "(IM or IV) immediately. Do not delay for diagnostic tests. Call emergency services (999/112)."
            ),
            safety_banner=(
                "🚨 CRITICAL EMERGENCY ALERT: Suspected Acute Adrenal Crisis. "
                "Immediate 100 mg parenteral hydrocortisone indicated without diagnostic delay."
            ),
        )

    # 3. Sick-Day & Physiological Stress Detection
    sick_day_matches = [
        pattern
        for pattern in _SICK_DAY_PATTERNS
        if re.search(pattern, cleaned_query, re.IGNORECASE)
    ]
    if sick_day_matches:
        return InputRiskAssessment(
            tier=InputRiskTier.SICK_DAY_STRESS,
            is_emergency=False,
            risk_score=0.65,
            detected_risk_factors=["Physiological Stress / Intercurrent Illness / Surgical Cover"],
            recommended_triage_action=(
                "Apply NICE NG243 Sick-Day Rules: Double regular oral glucocorticoid doses. "
                "Switch to parenteral hydrocortisone if persistent vomiting occurs."
            ),
            safety_banner=(
                "🤒 SICK-DAY PROTOCOL: Increased glucocorticoid requirements during physiological stress."
            ),
        )

    # 4. Pediatric & BSPED Specialist Detection
    pediatric_matches = [
        pattern
        for pattern in _PEDIATRIC_PATTERNS
        if re.search(pattern, cleaned_query, re.IGNORECASE)
    ]
    if pediatric_matches:
        return InputRiskAssessment(
            tier=InputRiskTier.PEDIATRIC_SPECIALIST,
            is_emergency=False,
            risk_score=0.70,
            detected_risk_factors=["Pediatric / Infant / Growth Consideration"],
            recommended_triage_action=(
                "Pediatric dosing must strictly adhere to BSPED protocols and body surface area calculations."
            ),
            safety_banner=(
                "👶 PEDIATRIC PROTOCOL: Refer to BSPED guidelines for age/weight-adjusted dosing."
            ),
        )

    # 5. Steroid Withdrawal & Tapering Detection
    withdrawal_matches = [
        pattern
        for pattern in _WITHDRAWAL_PATTERNS
        if re.search(pattern, cleaned_query, re.IGNORECASE)
    ]
    if withdrawal_matches:
        return InputRiskAssessment(
            tier=InputRiskTier.STEROID_WITHDRAWAL,
            is_emergency=False,
            risk_score=0.55,
            detected_risk_factors=["Steroid Tapering / HPA Axis Weaning"],
            recommended_triage_action=(
                "Follow gradual tapering protocol (NICE NG243 § 1.9) with morning cortisol monitoring."
            ),
            safety_banner=(
                "📉 STEROID TAPERING PROTOCOL: Gradual dose reduction required to avoid secondary adrenal crisis."
            ),
        )

    # 6. Out-of-Scope Detection
    out_of_scope_matches = [
        pattern
        for pattern in _OUT_OF_SCOPE_NON_ENDOCRINE
        if re.search(pattern, cleaned_query, re.IGNORECASE)
    ]
    if out_of_scope_matches and not is_clinical_domain_query(query):
        return InputRiskAssessment(
            tier=InputRiskTier.OUT_OF_SCOPE,
            is_emergency=False,
            risk_score=0.40,
            detected_risk_factors=["Non-Adrenal / Non-Endocrinology Topic"],
            recommended_triage_action="Provide polite scope boundary notice without hallucinating clinical advice.",
            safety_banner="ℹ️ OUT-OF-SCOPE: Query falls outside NICE NG243 Adrenal Insufficiency domain.",
        )

    # 7. Routine Clinical (Default)
    return InputRiskAssessment(
        tier=InputRiskTier.ROUTINE_CLINICAL,
        is_emergency=False,
        risk_score=0.15,
        detected_risk_factors=["Routine Identification & Maintenance Management"],
        recommended_triage_action="Generate evidence-grounded response with structural inline citations.",
        safety_banner="",
    )
