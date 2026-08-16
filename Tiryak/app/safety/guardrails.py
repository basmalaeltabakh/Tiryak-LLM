import json
from typing import Dict, List
from fastapi import HTTPException
from app.rag.llm_provider import generate_content

SAFETY_DISCLAIMER = {
    "en": (
        "⚠️ This information is provided for reference based on official guidelines. "
        "It supports — but does not replace — professional medical judgment. Always verify against "
        "the full clinical picture, and consult a pharmacist, physician, or poison control center for emergencies."
    ),
    "ar": (
        "⚠️ المعلومة دي مبنية على مصادر طبية رسمية، وهي بس للمساعدة ومش بديل عن رأي دكتور أو صيدلي. "
        "لازم تتأكد من حالتك الصحية الكاملة مع متخصص، ولو الحالة طارئة كلّم الإسعاف أو مركز السموم على طول."
    )
}


def _safe_generate_json(prompt: str) -> dict:
    try:
        result = generate_content(prompt)
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=f"All AI providers are currently unavailable. Please try again later. ({str(e)})"
        )

    text = result["text"].strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "risk_level": "needs_caution",
            "reasoning": "Classifier output could not be parsed; defaulting to cautious handling."
        }


def classify_query_risk(query: str, clinical_topic: str, user_type: str = "pharmacist") -> Dict:
    if user_type == "patient":
        audience_context = (
            "The user is a PATIENT or member of the public asking for general health education — "
            "NOT a healthcare professional. Be conservative: any request that reads as a specific "
            "instruction to start, stop, or change their own medication should be classified as at "
            "least 'needs_caution', steering them to consult a pharmacist or doctor rather than act alone."
        )
    else:
        audience_context = "The user is a healthcare professional (pharmacist) using this as clinical decision support."

    prompt = f"""You are a safety classifier for a clinical guideline assistant. The tool's defined scope is: "{clinical_topic}". It answers ONLY from official medical guidelines and NEVER diagnoses, prescribes, or handles emergencies.

{audience_context}

The query may be in Arabic or English — classify it regardless of language.

Classify the following user query into exactly one of three risk levels:

- "allowed": A general question about {clinical_topic} answerable by citing official guideline text.
- "needs_caution": A question describing a specific personal/patient scenario — answerable from guideline text, but requires extra caveats.
- "refuse": The query describes a medical emergency, asks for a diagnosis, asks the assistant to decide a treatment plan or specific dose, or is unrelated to {clinical_topic}.

Query: "{query}"

Return ONLY a valid JSON object (no markdown, no explanation outside the JSON):
{{"risk_level": "allowed" | "needs_caution" | "refuse", "reasoning": "<one short sentence>"}}

JSON output:"""

    return _safe_generate_json(prompt)


def get_refusal_response(reasoning: str, language: str = "en") -> Dict:
    disclaimer = SAFETY_DISCLAIMER.get(language, SAFETY_DISCLAIMER["en"])
    if language == "ar":
        answer = (
            "معلش، مقدرش أساعد في الطلب ده. أنا بجاوب بس من مصادر طبية رسمية وفي نطاق محدد، "
            "ومش بقدر أتعامل مع حالات الطوارئ أو التشخيص أو تحديد جرعة لمريض معين.\n\n"
            "لو دي حالة طارئة، كلّم الإسعاف أو مركز السموم على طول.\n\n"
            f"{disclaimer}"
        )
    else:
        answer = (
            "I can't help with this request. This tool only provides guideline-based reference "
            "information within its defined clinical scope, and cannot handle emergencies, "
            "diagnoses, or specific prescribing decisions.\n\n"
            "If this is a medical emergency, please contact emergency services or poison control immediately.\n\n"
            f"{disclaimer}"
        )
    return {
        "answer": answer,
        "sources": [],
        "evidence_panel": [],
        "provider_used": None,
        "confidence": {},
        "safety": {"risk_level": "refuse", "reasoning": reasoning}
    }


def check_retrieval_sufficiency(chunks: List[Dict], distance_threshold: float = 0.75) -> bool:
    if not chunks:
        return False
    avg_distance = sum(c["distance"] for c in chunks) / len(chunks)
    return avg_distance <= distance_threshold


def get_insufficient_evidence_response(language: str = "en") -> Dict:
    disclaimer = SAFETY_DISCLAIMER.get(language, SAFETY_DISCLAIMER["en"])
    if language == "ar":
        answer = (
            "للأسف مفيش معلومة كافية في المصادر الرسمية المتاحة عندي أجاوب بيها على السؤال ده بثقة. "
            "بدل ما أخمّن، هقولك بصراحة إن المعلومة دي مش متوفرة عندي دلوقتي.\n\n"
            f"{disclaimer}"
        )
    else:
        answer = (
            "I don't have sufficient evidence in the official guideline sources to answer this "
            "question reliably. Rather than guess, I'm flagging this as outside my current "
            "evidence base.\n\n"
            f"{disclaimer}"
        )
    return {
        "answer": answer,
        "sources": [],
        "evidence_panel": [],
        "provider_used": None,
        "confidence": {},
        "safety": {
            "risk_level": "insufficient_evidence",
            "reasoning": "Retrieved context was not similar enough to the query to answer reliably."
        }
    }