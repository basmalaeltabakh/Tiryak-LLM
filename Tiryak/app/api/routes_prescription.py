import logging
from fastapi import APIRouter, UploadFile, File

from app.advanced.image_reader import extract_medication_names_from_image
from app.advanced.drug_lookup import lookup_multiple_drugs
from app.rag.pipeline import answer_question_safely

router = APIRouter()
logger = logging.getLogger("tiryak.prescription")


def _build_identity_summary_ar(drug_infos: list) -> str:
    lines = []
    for info in drug_infos:
        if info.get("not_found"):
            lines.append(f"🔎 **{info['matched_name']}**: معرفتش ألاقيه في قاعدة بيانات الأدوية المصرية ولا في FDA، يفضل تتأكد من الاسم أو تسأل الصيدلي.")
            continue

        if info["source"] == "egypt":
            name_en = info.get("commercial_name_en") or info["matched_name"]
            name_ar = info.get("commercial_name_ar")
            block = f"💊 **{name_en}**" + (f" ({name_ar})" if name_ar else "")
            block += f"\n- **المادة الفعالة:** {info.get('active_ingredients') or 'مش متاح'}"
            block += f"\n- **الشركة المصنعة:** {info.get('manufacturer') or 'مش متاح'}"
            block += f"\n- **التصنيف:** {info.get('drug_class') or 'مش متاح'}"
            if info.get("price_egp"):
                block += f"\n- **السعر التقريبي:** {info['price_egp']} جنيه"
            block += "\n- **المصدر:** قاعدة بيانات الأدوية المصرية 🇪🇬"
        else:  # fda
            name_en = info.get("commercial_name_en") or info["matched_name"]
            block = f"💊 **{name_en}** (دواء أجنبي، مش مسجل في قاعدة البيانات المصرية اللي عندنا)"
            block += f"\n- **المادة الفعالة:** {info.get('active_ingredients') or 'مش متاح'}"
            if info.get("purpose"):
                block += f"\n- **بيُستخدم في:** {info['purpose']}"
            block += "\n- **المصدر:** FDA (قاعدة بيانات أمريكية) — يفضل تتأكد إنه نفسه متوفر في مصر مع الصيدلي"

        lines.append(block)

    return "\n\n".join(lines)


@router.post("/read")
async def read_prescription_image(
    file: UploadFile = File(...),
    user_type: str = "pharmacist"
):
    """
    1. Extracts medication names from the image (no guessing at unclear handwriting)
    2. Looks up factual drug identity info — Egyptian database first, FDA as fallback
    3. Runs a guideline-grounded safety question through the shared safe pipeline
    """
    image_bytes = await file.read()
    mime_type = file.content_type or "image/jpeg"
    logger.info(f"prescription/read: received {file.filename!r}, {len(image_bytes)} bytes, mime={mime_type}")

    extraction = extract_medication_names_from_image(image_bytes, mime_type=mime_type)
    logger.info(f"prescription/read: Gemini extraction result = {extraction}")
    names = extraction.get("clearly_read_names", [])

    if not names:
        return {
            "extraction": extraction,
            "identity_summary": None,
            "answer": None,
            "message": "معرفتش أقرا اسم دوا واضح من الصورة دي. جربي صورة أوضح، أو اكتبي اسم الدواء يدويًا."
        }

    drug_infos = lookup_multiple_drugs(names)
    identity_summary = _build_identity_summary_ar(drug_infos)

    generated_question = f"في محاذير أو تفاعلات مهمة لازم أعرفها عن: {', '.join(names)}؟"

    safety_result = answer_question_safely(
        question=generated_question,
        document_ids=None,
        user_type=user_type
    )

    return {
        "extraction": extraction,
        "identity_summary": identity_summary,
        "drug_database_matches": drug_infos,
        "generated_question": generated_question,
        **safety_result
    }