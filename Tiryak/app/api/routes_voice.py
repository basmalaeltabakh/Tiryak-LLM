from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

from app.advanced.voice_service import transcribe_audio, text_to_speech
from app.rag.pipeline import answer_question_safely
from app.config import TOP_K_RESULTS, UPLOADS_DIR

router = APIRouter()


@router.post("/transcribe")
async def transcribe_endpoint(file: UploadFile = File(...)):
    """
    Transcribes an uploaded audio file into text (Arabic or English).
    """
    audio_bytes = await file.read()
    text = transcribe_audio(audio_bytes, filename=file.filename)
    return {"transcribed_text": text}


@router.post("/ask")
async def voice_ask_endpoint(
    file: UploadFile = File(...),
    document_ids: str = "",
    top_k: int = TOP_K_RESULTS,
    check_grounding: bool = True,
    speak_answer: bool = True,
    user_type: str = "pharmacist"
):
    """
    Full voice pipeline: transcribes spoken audio into a question, then
    routes it through the SAME shared safety pipeline used by the text
    endpoint (risk classification -> retrieval -> guardrails -> generation),
    and optionally converts the answer back into speech.
    """
    audio_bytes = await file.read()
    question_text = transcribe_audio(audio_bytes, filename=file.filename)

    doc_id_list = [d.strip() for d in document_ids.split(",") if d.strip()]

    result = answer_question_safely(
        question=question_text,
        document_ids=doc_id_list if doc_id_list else None,
        top_k=top_k,
        check_grounding=check_grounding,
        user_type=user_type
    )

    response_data = {
        "transcribed_question": question_text,
        "answer": result["answer"],
        "sources": result.get("sources", []),
        "evidence_panel": result.get("evidence_panel", []),
        "confidence": result.get("confidence", {}),
        "provider_used": result.get("provider_used"),
        "safety": result.get("safety", {}),
        "audio_answer_path": None
    }

    if speak_answer:
        audio_path = text_to_speech(result["answer"])
        response_data["audio_answer_path"] = audio_path

    return response_data


@router.get("/audio/{filename}")
async def get_audio_file(filename: str):
    """
    Serves a generated TTS audio file so the frontend can play it back.
    """
    file_path = UPLOADS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found.")
    return FileResponse(str(file_path), media_type="audio/mpeg")