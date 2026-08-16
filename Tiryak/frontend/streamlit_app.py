import streamlit as st
import requests
import base64
import os
from pathlib import Path
import streamlit.components.v1 as components

API_BASE_URL = "http://127.0.0.1:8000"

# ─── Logo resolution (checks png then jpg, relative to this script) ───
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_LOGO_CANDIDATES = [
    os.path.join(_SCRIPT_DIR, "assets", "tiryak_logo.png"),
    os.path.join(_SCRIPT_DIR, "assets", "tiryak_logo.jpg"),
]
LOGO_PATH = next((p for p in _LOGO_CANDIDATES if os.path.exists(p)), None)

st.set_page_config(
    page_title="Tiryak - Clinical Guideline Assistant",
    page_icon=(LOGO_PATH if LOGO_PATH else "💊"),
    layout="wide",
    initial_sidebar_state="expanded"
)

_component_dir = os.path.join(_SCRIPT_DIR, "voice_input_component")
voice_chat_input = components.declare_component("voice_chat_input", path=_component_dir)

COLORS = {
    "primary_green": "#22B573",
    "primary_blue": "#3B82F6",
    "dark_navy": "#1B2A4A",
    "soft_green": "#DCFCE7",
    "soft_yellow": "#FEF3C7",
    "soft_red": "#FEE2E2",
    "soft_gray": "#F3F4F6",
    "text_gray": "#6B7280",
    "white": "#FFFFFF",
}

st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
    html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}
    .stApp {{ background: linear-gradient(135deg, #FAFBFC 0%, #F0F4F8 100%); }}

    .landing-wrap {{
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        text-align: center;
        padding-top: 8vh;
    }}
    .landing-title {{
        font-size: 2.6rem;
        font-weight: 800;
        color: {COLORS["dark_navy"]};
        margin: 18px 0 4px 0;
        letter-spacing: -1px;
    }}
    .landing-subtitle {{
        color: {COLORS["text_gray"]};
        font-size: 1.05rem;
        max-width: 520px;
        margin-bottom: 28px;
    }}

    .tiryak-badge {{
        display: inline-flex; align-items: center; gap: 6px;
        background: linear-gradient(135deg, {COLORS["primary_green"]}15, {COLORS["primary_blue"]}10);
        border: 1px solid {COLORS["primary_green"]}30;
        color: {COLORS["dark_navy"]};
        padding: 4px 14px; border-radius: 20px;
        font-size: 0.75rem; font-weight: 600;
    }}

    [data-testid="stSidebar"] {{
        background: linear-gradient(180deg, {COLORS["white"]} 0%, {COLORS["soft_gray"]}40 100%);
        border-right: 1px solid #E5E7EB;
    }}

    .stButton > button {{
        border-radius: 10px !important; font-weight: 600 !important;
        transition: all 0.2s ease !important; box-shadow: 0 1px 3px rgba(0,0,0,0.08) !important;
    }}
    .stButton > button:hover {{ transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,0.12) !important; }}
    .stButton > button[kind="primary"] {{
        background: linear-gradient(135deg, {COLORS["primary_green"]}, {COLORS["primary_green"]}dd) !important;
        border: none !important;
    }}

    .stChatMessage {{
        background: {COLORS["white"]} !important;
        border: 1px solid #E5E7EB;
        border-radius: 16px !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04) !important;
        margin-bottom: 12px !important; padding: 16px !important;
    }}

    .risk-badge {{
        display: inline-flex; align-items: center; gap: 6px;
        padding: 5px 14px; border-radius: 20px;
        font-size: 0.82rem; font-weight: 700; margin: 8px 0;
        border: 1px solid transparent;
    }}
    .risk-allowed {{ background: linear-gradient(135deg, {COLORS["soft_green"]}, #BBF7D0); color: #15803D; border-color: #86EFAC; }}
    .risk-needs_caution {{ background: linear-gradient(135deg, {COLORS["soft_yellow"]}, #FDE68A); color: #92400E; border-color: #FCD34D; }}
    .risk-refuse {{ background: linear-gradient(135deg, {COLORS["soft_red"]}, #FECACA); color: #B91C1C; border-color: #FCA5A5; }}
    .risk-insufficient_evidence {{ background: linear-gradient(135deg, {COLORS["soft_gray"]}, #E5E7EB); color: #374151; border-color: #D1D5DB; }}

    .disclaimer-box {{
        background: linear-gradient(135deg, {COLORS["primary_green"]}10, {COLORS["primary_blue"]}08);
        border-left: 4px solid {COLORS["primary_green"]};
        padding: 14px 18px; border-radius: 10px; font-size: 0.85rem;
        margin-top: 14px; color: {COLORS["dark_navy"]}; line-height: 1.6;
        border: 1px solid {COLORS["primary_green"]}20;
    }}

    iframe[title="voice_input_component.voice_chat_input"] {{
        position: fixed; bottom: 24px;
        left: calc(21rem + 2vw); right: 2vw;
        z-index: 999; max-width: 900px;
        filter: drop-shadow(0 4px 20px rgba(0,0,0,0.08));
    }}

    .audience-toggle label {{ font-weight: 600 !important; }}
    </style>
""", unsafe_allow_html=True)

# ─── Session state ───
if "documents" not in st.session_state:
    st.session_state.documents = []
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "document_summaries" not in st.session_state:
    st.session_state.document_summaries = {}
if "last_processed_input_id" not in st.session_state:
    st.session_state.last_processed_input_id = None
if "user_type" not in st.session_state:
    st.session_state.user_type = "pharmacist"

RISK_LABELS = {
    "allowed": "🟢 Allowed",
    "needs_caution": "🟡 Needs Caution",
    "refuse": "🔴 Refused",
    "insufficient_evidence": "⚪ Insufficient Evidence"
}

SUGGESTED_PROMPTS = [
    "What medications increase the risk of falls in elderly patients?",
    "What are the sick day rules for common medications?",
    "How should benzodiazepines be tapered safely?",
]


def refresh_documents():
    response = requests.get(f"{API_BASE_URL}/documents/list")
    if response.status_code == 200:
        st.session_state.documents = response.json()["documents"]


def render_answer_meta(data: dict):
    risk_level = data.get("safety", {}).get("risk_level", "unknown")
    badge_class = f"risk-{risk_level}" if risk_level in RISK_LABELS else ""
    st.markdown(f'<span class="risk-badge {badge_class}">{RISK_LABELS.get(risk_level, risk_level)}</span>', unsafe_allow_html=True)

    if data.get("evidence_panel"):
        with st.expander("📋 Evidence Panel — retrieved guideline excerpts"):
            for ev in data["evidence_panel"]:
                st.markdown(f"**{ev['filename']}**, Page {ev['page_number']} — similarity: `{ev['similarity_distance']}`")
                st.caption(ev["text_snippet"])
                st.divider()

    if data.get("confidence"):
        with st.expander("📊 Sources & Confidence"):
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Retrieval Confidence", data['confidence'].get('retrieval_confidence', 'n/a'))
            with col2:
                st.metric("Grounding Check", data['confidence'].get('grounding_verdict', 'n/a'))
            if data.get("sources"):
                refs = sorted(set((s["filename"], s["page_number"]) for s in data["sources"]))
                st.write("**Sources referenced:**")
                for filename, page in refs:
                    st.write(f"- 📄 {filename}, Page {page}")
            st.caption(f"**AI Provider:** {data.get('provider_used', 'n/a')}")

    st.markdown(
        f'<div class="disclaimer-box">⚕️ <strong>Medical Disclaimer:</strong> Tiryak supports — but does not replace — '
        f'professional medical judgment. Always verify with a licensed healthcare provider.</div>',
        unsafe_allow_html=True
    )


def handle_text_question(question_text: str, doc_ids: list):
    with st.chat_message("user"):
        st.write(question_text)

    with st.chat_message("assistant"):
        with st.spinner("🔍 Checking clinical guidelines..."):
            payload = {
                "question": question_text,
                "document_ids": doc_ids,
                "user_type": st.session_state.user_type
            }
            response = requests.post(f"{API_BASE_URL}/query/ask", json=payload)

            if response.status_code == 200:
                data = response.json()
                st.write(data["answer"])
                render_answer_meta(data)

                st.session_state.chat_history.append({
                    "question": question_text,
                    "answer": data["answer"],
                    "sources": data.get("sources", []),
                    "confidence": data.get("confidence", {}),
                    "provider_used": data.get("provider_used"),
                    "safety": data.get("safety", {}),
                    "evidence_panel": data.get("evidence_panel", [])
                })
            else:
                st.error(f"❌ Error: {response.text}")


def handle_voice_question(audio_base64: str, doc_ids: list):
    audio_bytes = base64.b64decode(audio_base64)

    with st.spinner("🎙️ Transcribing & checking guidelines..."):
        files = {"file": ("question.webm", audio_bytes, "audio/webm")}
        params = {
            "document_ids": ",".join(doc_ids),
            "speak_answer": True,
            "user_type": st.session_state.user_type
        }
        response = requests.post(f"{API_BASE_URL}/voice/ask", files=files, params=params)

        if response.status_code == 200:
            data = response.json()

            with st.chat_message("user"):
                st.write(f"🎤 *{data.get('transcribed_question', '')}*")

            with st.chat_message("assistant"):
                st.write(data["answer"])
                render_answer_meta(data)

                if data.get("audio_answer_path"):
                    audio_filename = Path(data["audio_answer_path"]).name
                    audio_response = requests.get(f"{API_BASE_URL}/voice/audio/{audio_filename}")
                    if audio_response.status_code == 200:
                        st.audio(audio_response.content, format="audio/mp3")

            st.session_state.chat_history.append({
                "question": data.get("transcribed_question", ""),
                "answer": data["answer"],
                "sources": data.get("sources", []),
                "confidence": data.get("confidence", {}),
                "provider_used": data.get("provider_used"),
                "safety": data.get("safety", {}),
                "evidence_panel": data.get("evidence_panel", [])
            })
        else:
            st.error(f"❌ Error: {response.text}")

def handle_prescription_image(image_base64: str, mime_type: str, user_type_ignored=None):
    image_bytes = base64.b64decode(image_base64)

    with st.chat_message("user"):
        st.image(image_bytes, width=220, caption="صورة مرفوعة")

    with st.chat_message("assistant"):
        with st.spinner("📷 بقرا الصورة وبدور في قاعدة بيانات الأدوية..."):
            files = {"file": ("photo.jpg", image_bytes, mime_type)}
            params = {"user_type": st.session_state.user_type}
            response = requests.post(f"{API_BASE_URL}/prescription/read", files=files, params=params)

            if response.status_code != 200:
                st.error(f"❌ Error: {response.text}")
                return

            data = response.json()
            extraction = data.get("extraction", {})
            names = extraction.get("clearly_read_names", [])

            if not names:
                st.warning(data.get("message", "معرفتش أقرا اسم دوا واضح من الصورة."))
                if extraction.get("notes"):
                    st.caption(f"ملاحظة: {extraction['notes']}")
                return

            if extraction.get("unclear_count", 0) > 0:
                st.caption(f"⚠️ في {extraction['unclear_count']} اسم/أسماء تانية مش واضحة، اتجاهلت عشان منخمنش.")

            if data.get("identity_summary"):
                st.markdown("### 💊 معلومات عن الأدوية")
                st.markdown(data["identity_summary"])
                st.caption("المصدر: قاعدة بيانات FDA الرسمية للأدوية")
                st.divider()

            st.markdown("### 🛡️ محاذير وتفاعلات (من الدليل الطبي)")
            st.write(data["answer"])
            render_answer_meta(data)

            st.session_state.chat_history.append({
                "question": f"📷 [صورة] الأدوية اللي اتعرفت: {', '.join(names)}",
                "answer": (data.get("identity_summary", "") or "") + "\n\n" + (data.get("answer") or ""),
                "sources": data.get("sources", []),
                "confidence": data.get("confidence", {}),
                "provider_used": data.get("provider_used"),
                "safety": data.get("safety", {}),
                "evidence_panel": data.get("evidence_panel", [])
            })
# ─── Sidebar: optional extra guidelines + audience toggle ───
with st.sidebar:
    if LOGO_PATH:
        st.image(LOGO_PATH, width=90)
    st.markdown(
        f'<p style="text-align:center; font-weight:700; color:{COLORS["dark_navy"]}; font-size:1.1rem; margin-bottom:2px;">Tiryak</p>'
        f'<p style="text-align:center; color:{COLORS["text_gray"]}; font-size:0.78rem; margin-top:0;">Guideline Assistant</p>',
        unsafe_allow_html=True
    )
    st.divider()

    st.subheader("Who's asking?")
    st.session_state.user_type = st.radio(
        "Audience",
        options=["pharmacist", "patient"],
        format_func=lambda x: "👩‍⚕️ Pharmacist" if x == "pharmacist" else "🧑 Patient",
        label_visibility="collapsed",
        horizontal=True
    )
    st.caption("Answers adapt language and caution level based on this.")
    st.divider()

    if not st.session_state.documents:
        refresh_documents()

    with st.expander("➕ Add more guideline documents (optional)"):
        uploaded_file = st.file_uploader("PDF, DOCX, or PPTX", type=["pdf", "docx", "pptx"], label_visibility="collapsed")
        if uploaded_file is not None:
            if st.button("⚡ Process Document", type="primary", use_container_width=True):
                with st.spinner("Processing..."):
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue())}
                    response = requests.post(f"{API_BASE_URL}/documents/upload", files=files)
                    if response.status_code == 200:
                        data = response.json()
                        st.success(f"✅ Done! {data['num_chunks']} chunks indexed.")
                        refresh_documents()
                    else:
                        st.error(f"❌ Failed: {response.text}")

        if st.session_state.documents:
            st.write("**Indexed documents:**")
            for doc in st.session_state.documents:
                is_seed = doc["document_id"].startswith("seed_")
                label = f"🔒 {doc['filename']}" if is_seed else f"📄 {doc['filename']}"
                c1, c2 = st.columns([5, 1])
                with c1:
                    st.caption(label)
                with c2:
                    if not is_seed:
                        if st.button("🗑️", key=f"del_{doc['document_id']}"):
                            requests.delete(f"{API_BASE_URL}/documents/{doc['document_id']}")
                            st.session_state.document_summaries.pop(doc['document_id'], None)
                            refresh_documents()
                            st.rerun()

    selected_ids = []  # empty = search across all indexed documents (including the always-on seed guideline)
    if len(st.session_state.documents) > 1:
        with st.expander("🎯 Limit search to specific documents (optional)"):
            filename_options = {doc["filename"]: doc["document_id"] for doc in st.session_state.documents}
            chosen = st.multiselect("Only search within:", options=list(filename_options.keys()))
            selected_ids = [filename_options[f] for f in chosen]

    if st.session_state.documents:
        st.divider()
        st.subheader("📝 Summarize a document")
        filename_options_all = {doc["filename"]: doc["document_id"] for doc in st.session_state.documents}
        summary_target = st.selectbox("Choose:", options=list(filename_options_all.keys()))
        if st.button("✨ Generate Summary", use_container_width=True):
            target_id = filename_options_all[summary_target]
            with st.spinner("Generating summary..."):
                response = requests.post(f"{API_BASE_URL}/summary/generate", json={"document_id": target_id})
                if response.status_code == 200:
                    st.session_state.document_summaries[target_id] = {
                        "filename": summary_target,
                        "summary": response.json()["final_summary"]
                    }
                else:
                    st.error(f"❌ Failed: {response.text}")

# ─── Main area ───
has_conversation = len(st.session_state.chat_history) > 0

if not has_conversation:
    st.markdown('<div class="landing-wrap">', unsafe_allow_html=True)
    if LOGO_PATH:
        col_a, col_b, col_c = st.columns([1, 1, 1])
        with col_b:
            st.image(LOGO_PATH, width=110)
    st.markdown('<p class="landing-title">Tiryak</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="landing-subtitle">Ask about medication safety and drug interactions — every answer is grounded in official clinical guidelines, with full citations.</p>',
        unsafe_allow_html=True
    )
    st.markdown('<span class="tiryak-badge">🛡️ Sourced from official clinical guidelines</span>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.write("")
    cols = st.columns(len(SUGGESTED_PROMPTS))
    for i, prompt in enumerate(SUGGESTED_PROMPTS):
        with cols[i]:
            if st.button(prompt, key=f"suggest_{i}", use_container_width=True):
                handle_text_question(prompt, selected_ids)
                st.rerun()
    st.write("")
else:
    for doc_id, summary_data in st.session_state.document_summaries.items():
        with st.expander(f"📄 Summary — {summary_data['filename']}", expanded=False):
            st.markdown(summary_data["summary"])

    st.markdown('<div style="height: 90px;"></div>', unsafe_allow_html=True)

    for entry in st.session_state.chat_history:
        with st.chat_message("user"):
            st.write(entry["question"])
        with st.chat_message("assistant"):
            st.write(entry["answer"])
            render_answer_meta(entry)

# ─── Unified input bar (always visible, pinned to bottom) ───
result = voice_chat_input(key="unified_input")

if result is not None and isinstance(result, dict):
    input_id = result.get("id")
    if st.session_state.last_processed_input_id != input_id:
        st.session_state.last_processed_input_id = input_id

        if result.get("type") == "text":
            handle_text_question(result["value"], selected_ids)
            st.rerun()
        elif result.get("type") == "audio":
            handle_voice_question(result["value"], selected_ids)
            st.rerun()
        elif result.get("type") == "image":
            handle_prescription_image(result["value"], result.get("mime_type", "image/jpeg"))
            st.rerun()