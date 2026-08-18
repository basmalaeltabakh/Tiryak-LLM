import streamlit as st
import requests
import base64
import html
import os
import re
from pathlib import Path
import streamlit.components.v1 as components

API_BASE_URL = "http://127.0.0.1:8000"

# Real backend default from app/safety/guardrails.py check_retrieval_sufficiency()
INSUFFICIENT_EVIDENCE_DISTANCE_THRESHOLD = 0.75

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
    "bg": "#0E1117",
    "panel_bg": "#1A1D23",
    "card_bg": "#1E2128",
    "card_border": "#2D3139",
    "caution_fg": "#C77A00",
    "caution_bg": "#2D1F00",
    "emergency_fg": "#C1392B",
    "emergency_bg": "#2D0A0A",
    "insufficient_fg": "#6B7280",
    "insufficient_bg": "#1F2128",
    "safe_fg": "#3FB950",
    "safe_bg": "#062B14",
    "user_bubble": "#1B3A6B",
    "primary_btn": "#2563EB",
    "text": "#E6E8EB",
    "text_muted": "#9AA1AC",
}
C = COLORS

st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
    html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}

    .stApp {{ background: {C["bg"]} !important; color: {C["text"]}; }}
    [data-testid="stAppViewContainer"] {{ background: {C["bg"]} !important; }}
    [data-testid="stHeader"] {{ background: transparent !important; }}

    /* ─── Fixed-width left panel ─── */
    section[data-testid="stSidebar"] {{
        background: {C["panel_bg"]} !important;
        min-width: 280px !important;
        max-width: 280px !important;
        width: 280px !important;
        border-right: 1px solid {C["card_border"]};
    }}
    section[data-testid="stSidebar"] > div {{ width: 280px !important; }}
    [data-testid="stSidebarResizeHandle"] {{ display: none !important; }}
    section[data-testid="stSidebar"] * {{ color: {C["text"]}; }}
    section[data-testid="stSidebar"] .stCaption, section[data-testid="stSidebar"] small {{ color: {C["text_muted"]} !important; }}

    .block-container {{ padding-bottom: 110px !important; padding-top: 1.5rem !important; }}

    /* ─── Segmented "who's asking" control ─── */
    div[data-testid="stRadio"] > div[role="radiogroup"] {{
        display: flex; gap: 4px; background: {C["card_bg"]};
        border: 1px solid {C["card_border"]}; border-radius: 10px; padding: 4px;
    }}
    div[data-testid="stRadio"] label {{
        flex: 1; justify-content: center; margin: 0 !important;
        border-radius: 7px; padding: 6px 8px !important; font-weight: 600;
    }}
    div[data-testid="stRadio"] label[data-selected="true"] {{
        background: {C["primary_btn"]};
    }}
    /* ─── Dark-theme form inputs (react-aria/BaseWeb portals render outside the sidebar DOM, so these stay unscoped) ─── */
    div[data-testid="stNumberInputContainer"], div[data-testid="stTextInputRootElement"],
    div[data-testid="stMultiSelectTagsContainer"], div[data-baseweb="select"] > div {{
        background: {C["card_bg"]} !important; border: 1px solid {C["card_border"]} !important; border-radius: 8px !important;
    }}
    div[data-testid="stNumberInputField"], div[data-testid="stTextInputRootElement"] input,
    div[data-testid="stMultiSelectTagsContainer"] input {{
        background: transparent !important; color: {C["text"]} !important;
    }}
    ul[role="listbox"], div[role="listbox"] {{ background: {C["card_bg"]} !important; border: 1px solid {C["card_border"]} !important; }}
    ul[role="listbox"] *, div[role="listbox"] * {{ color: {C["text"]} !important; }}
    [data-testid="stFileUploaderDropzone"] {{
        background: {C["card_bg"]} !important; border: 1px dashed {C["card_border"]} !important;
    }}
    [data-testid="stFileUploaderDropzone"] * {{ color: {C["text_muted"]} !important; }}

    /* ─── Generic buttons ─── */
    .stButton > button, .stFormSubmitButton > button {{
        border-radius: 10px !important; font-weight: 600 !important;
        background: {C["card_bg"]} !important; color: {C["text"]} !important;
        border: 1px solid {C["card_border"]} !important;
    }}
    .stButton > button:hover, .stFormSubmitButton > button:hover {{ border-color: {C["primary_btn"]} !important; color: {C["primary_btn"]} !important; }}
    .stButton > button[kind="primary"] {{
        background: {C["primary_btn"]} !important; border: none !important; color: white !important;
    }}
    .stButton > button p, .stFormSubmitButton > button p {{ color: inherit !important; }}

    /* ─── Chip list rows (medications) ─── */
    .tk-chip-row {{
        display: flex; align-items: center; justify-content: space-between;
        background: {C["card_bg"]}; border: 1px solid {C["card_border"]};
        border-radius: 8px; padding: 6px 10px; margin-bottom: 6px; font-size: 0.85rem;
    }}

    /* ─── Chat scroll area ─── */
    .chat-scroll {{ max-height: calc(100vh - 230px); overflow-y: auto; padding: 4px 6px 24px 2px; }}

    .tk-user-row {{ display: flex; justify-content: flex-end; margin: 16px 0 6px; }}
    .tk-user-bubble {{
        background: {C["user_bubble"]}; color: #fff; padding: 10px 16px;
        border-radius: 16px 16px 4px 16px; max-width: 68%;
        font-size: 0.92rem; line-height: 1.5; word-wrap: break-word;
    }}
    .tk-user-image {{ max-width: 220px; border-radius: 14px; border: 1px solid {C["card_border"]}; }}

    .tk-card {{
        background: {C["card_bg"]}; border: 1px solid {C["card_border"]};
        border-radius: 14px; padding: 16px 18px; margin: 4px 0 14px; max-width: 82%;
    }}

    .tk-badge-row {{ display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }}
    .badge {{
        display: inline-flex; align-items: center; gap: 6px; padding: 4px 12px;
        border-radius: 20px; font-size: 0.8rem; font-weight: 700; border: 1px solid transparent;
    }}
    .badge-safe {{ color: {C["safe_fg"]}; background: {C["safe_bg"]}; border-color: {C["safe_fg"]}55; }}
    .badge-caution {{ color: {C["caution_fg"]}; background: {C["caution_bg"]}; border-color: {C["caution_fg"]}55; }}
    .badge-emergency {{ color: {C["emergency_fg"]}; background: {C["emergency_bg"]}; border-color: {C["emergency_fg"]}55; }}
    .badge-insufficient {{ color: {C["insufficient_fg"]}; background: {C["insufficient_bg"]}; border-color: {C["insufficient_fg"]}55; }}
    .tk-conf-label {{ font-size: 0.78rem; color: {C["text_muted"]}; }}

    .tk-answer-text {{ font-size: 0.95rem; line-height: 1.7; color: {C["text"]}; }}

    .tk-tip {{
        background: {C["caution_bg"]}; border: 1px solid {C["caution_fg"]}55; color: #F5C77A;
        padding: 10px 14px; border-radius: 10px; margin-top: 14px; font-size: 0.85rem; line-height: 1.5;
    }}

    .tk-evidence {{ border-top: 1px solid {C["card_border"]}; margin-top: 14px; padding-top: 12px; }}
    .tk-evidence-label {{ font-size: 0.75rem; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: {C["text_muted"]}; margin-bottom: 6px; }}
    .tk-evidence blockquote {{
        margin: 4px 0 8px; padding: 8px 12px; border-left: 3px solid {C["primary_btn"]}88;
        background: #161920; border-radius: 6px; font-size: 0.85rem; color: #C9CCD3; font-style: italic;
    }}
    .tk-source {{ font-size: 0.78rem; color: {C["text_muted"]}; }}

    .tk-emg-btns {{ display: flex; gap: 10px; margin: 14px 0 10px; }}
    .tk-emg-call {{
        background: {C["emergency_fg"]}; color: #fff; padding: 9px 18px; border-radius: 10px;
        text-decoration: none; font-weight: 700; font-size: 0.88rem;
    }}
    .tk-emg-outline {{
        border: 1px solid {C["emergency_fg"]}; color: #F1A9A0; padding: 9px 18px;
        border-radius: 10px; font-weight: 700; font-size: 0.88rem;
    }}
    .tk-emg-footer {{ font-size: 0.78rem; color: {C["text_muted"]}; }}

    .tk-search-table {{ width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 0.85rem; }}
    .tk-search-table td {{ padding: 6px 4px; border-bottom: 1px solid {C["card_border"]}; }}
    .tk-search-table td:first-child {{ color: {C["text_muted"]}; }}
    .tk-search-table td:last-child {{ text-align: right; font-weight: 600; }}

    iframe[title="voice_input_component.voice_chat_input"] {{
        position: fixed; bottom: 20px;
        left: calc(280px + 2vw); right: 2vw;
        z-index: 999; max-width: 900px;
        filter: drop-shadow(0 4px 20px rgba(0,0,0,0.35));
    }}
    </style>
""", unsafe_allow_html=True)

# ─── Session state ───
defaults = {
    "documents": [],
    "chat_history": [],
    "document_summaries": {},
    "last_processed_input_id": None,
    "user_type": "pharmacist",
    "patient_age": None,
    "conditions": [],
    "medications": [],
    "show_scan_uploader": False,
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

PRESET_CONDITIONS = [
    "Diabetes", "Hypertension", "Kidney disease (CKD)", "Liver disease",
    "Pregnancy", "Asthma / COPD", "Heart failure", "Elderly (65+)",
]

SUGGESTED_PROMPTS = [
    "What medications increase the risk of falls in elderly patients?",
    "What are the sick day rules for common medications?",
    "How should benzodiazepines be tapered safely?",
]


def esc(text) -> str:
    return html.escape(str(text if text is not None else "")).replace("\n", "<br>")


def md_lite(text) -> str:
    """Escapes text, then re-applies the small subset of Markdown an LLM answer
    actually uses (bold, paragraph breaks). Raw HTML blocks passed to st.markdown
    are never re-processed for nested Markdown, so **bold** would otherwise show
    as literal asterisks."""
    t = html.escape(str(text if text is not None else ""))
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = t.replace("\n\n", "<br><br>").replace("\n", "<br>")
    return t


def contains_arabic(text) -> bool:
    return any("؀" <= ch <= "ۿ" for ch in str(text or ""))


def _flatten(fragment: str) -> str:
    """Strips leading whitespace from every line of an HTML fragment. Streamlit's
    st.markdown runs content through Python-Markdown before injecting raw HTML;
    a 4+ space indent on a line makes Markdown treat it as an indented code block
    and print the tags literally instead of rendering them."""
    return "\n".join(line.strip() for line in fragment.strip().splitlines())


def short_doc_label(filename: str) -> str:
    if not filename:
        return "Guideline"
    if "HEARTS" in filename:
        return "WHO HEARTS"
    if "AWaRe" in filename:
        return "WHO AWaRe"
    if "Polypharmacy" in filename:
        return "Polypharmacy Guide"
    return (filename[:28] + "…") if len(filename) > 29 else filename


def refresh_documents():
    try:
        response = requests.get(f"{API_BASE_URL}/documents/list", timeout=10)
        if response.status_code == 200:
            st.session_state.documents = response.json()["documents"]
    except requests.RequestException:
        pass


def build_enriched_question(question_text: str) -> str:
    parts = []
    if st.session_state.patient_age:
        parts.append(f"Patient age: {st.session_state.patient_age}.")
    if st.session_state.conditions:
        parts.append(f"Known conditions: {', '.join(st.session_state.conditions)}.")
    if st.session_state.medications:
        parts.append(f"Current medications: {', '.join(st.session_state.medications)}.")
    if not parts:
        return question_text
    return f"[Patient context — {' '.join(parts)}]\n\n{question_text}"


# ─── Card renderers ───
def render_answer_card(entry: dict, risk_level: str) -> str:
    if risk_level == "allowed":
        badge_label, badge_cls = "✅ Safe", "badge-safe"
        tip = "🛡️ المعلومة دي للمساعدة بس ومش بديل عن رأي الصيدلي أو الدكتور."
    else:
        badge_label, badge_cls = "⚠️ Caution", "badge-caution"
        tip = "⚠️ السؤال ده خاص بحالة معينة — يفضل تتأكد مع صيدلي أو دكتور قبل ما تتصرف بناءً عليه."

    conf = (entry.get("confidence") or {}).get("retrieval_confidence", "medium")
    conf_label = f"{str(conf).capitalize()} confidence"

    evidence_html = ""
    panel = entry.get("evidence_panel") or []
    if panel:
        ev = panel[0]
        distance = ev.get("similarity_distance", 1)
        score = max(0.0, round(1 - distance, 2))
        section = ev.get("section_title")
        source_bits = [short_doc_label(ev.get("filename")), f"p.{ev.get('page_number', '?')}"]
        if section:
            source_bits.append(f"§{esc(section)}")
        source_bits.append(str(score))
        evidence_html = f'''
        <div class="tk-evidence">
          <div class="tk-evidence-label">Evidence</div>
          <blockquote>&ldquo;{esc(ev.get("text_snippet", ""))}&rdquo;</blockquote>
          <div class="tk-source">Source: {"  ".join(source_bits)}</div>
        </div>'''

    answer_text = entry.get("answer", "")
    answer_dir = "rtl" if contains_arabic(answer_text) else "ltr"
    tip_dir = "rtl" if contains_arabic(tip) else "ltr"

    return _flatten(f'''
    <div class="tk-card">
      <div class="tk-badge-row">
        <span class="badge {badge_cls}">{badge_label}</span>
        <span class="tk-conf-label">{conf_label}</span>
      </div>
      <div dir="{answer_dir}" class="tk-answer-text">{md_lite(answer_text)}</div>
      <div dir="{tip_dir}" class="tk-tip">{tip}</div>
      {evidence_html}
    </div>''')


def render_emergency_card() -> str:
    return _flatten('''
    <div class="tk-card">
      <span class="badge badge-emergency">🚨 Emergency</span>
      <div dir="rtl" class="tk-answer-text" style="margin-top:10px;">روح أقرب مستشفى دلوقتي</div>
      <div class="tk-emg-btns">
        <a class="tk-emg-call" href="tel:123">اتصل بـ ١٢٣</a>
        <span class="tk-emg-outline">أقرب مستشفى</span>
      </div>
      <div dir="rtl" class="tk-emg-footer">النظام مش بيجاوب على أسئلة الطوارئ</div>
    </div>''')


def render_insufficient_card() -> str:
    doc_count = len(st.session_state.documents) if st.session_state.documents else "—"
    return _flatten(f'''
    <div class="tk-card">
      <span class="badge badge-insufficient">🔍 Insufficient evidence</span>
      <div dir="rtl" class="tk-answer-text" style="margin-top:10px;">مفيش في الأدلة معلومة واضحة</div>
      <table class="tk-search-table">
        <tr><td>Documents</td><td>{doc_count} indexed</td></tr>
        <tr><td>Closest match</td><td>below threshold</td></tr>
        <tr><td>Threshold</td><td>{INSUFFICIENT_EVIDENCE_DISTANCE_THRESHOLD}</td></tr>
      </table>
    </div>''')


def render_entry_html(entry: dict) -> str:
    if entry.get("image_b64"):
        user_html = f'<div class="tk-user-row"><img class="tk-user-image" src="data:{entry.get("image_mime", "image/jpeg")};base64,{entry["image_b64"]}" /></div>'
    else:
        user_html = f'<div class="tk-user-row"><div class="tk-user-bubble">{esc(entry.get("question", ""))}</div></div>'

    risk_level = (entry.get("safety") or {}).get("risk_level")
    if risk_level == "refuse":
        card_html = render_emergency_card()
    elif risk_level == "insufficient_evidence":
        card_html = render_insufficient_card()
    else:
        card_html = render_answer_card(entry, risk_level)

    return user_html + card_html


# ─── Backend calls ───
def handle_text_question(question_text: str, doc_ids: list):
    enriched = build_enriched_question(question_text)
    with st.spinner("🔍 Checking clinical guidelines..."):
        payload = {"question": enriched, "document_ids": doc_ids, "user_type": st.session_state.user_type}
        response = requests.post(f"{API_BASE_URL}/query/ask", json=payload)

    if response.status_code == 200:
        data = response.json()
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
        st.session_state.chat_history.append({
            "question": f"🎤 {data.get('transcribed_question', '')}",
            "answer": data["answer"],
            "sources": data.get("sources", []),
            "confidence": data.get("confidence", {}),
            "provider_used": data.get("provider_used"),
            "safety": data.get("safety", {}),
            "evidence_panel": data.get("evidence_panel", [])
        })
    else:
        st.error(f"❌ Error: {response.text}")


def handle_prescription_image(image_base64: str, mime_type: str):
    image_bytes = base64.b64decode(image_base64)
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
        st.session_state.chat_history.append({
            "question": "📷 [صورة مرفوعة]",
            "image_b64": image_base64, "image_mime": mime_type,
            "answer": data.get("message", "معرفتش أقرا اسم دوا واضح من الصورة."),
            "sources": [], "confidence": {}, "provider_used": None,
            "safety": {"risk_level": "insufficient_evidence", "reasoning": "No medication name read from image."},
            "evidence_panel": []
        })
        return

    identity_summary = data.get("identity_summary") or ""
    combined_answer = (identity_summary + "\n\n" + (data.get("answer") or "")).strip()
    st.session_state.chat_history.append({
        "question": f"📷 الأدوية اللي اتعرفت: {', '.join(names)}",
        "image_b64": image_base64, "image_mime": mime_type,
        "answer": combined_answer,
        "sources": data.get("sources", []),
        "confidence": data.get("confidence", {}),
        "provider_used": data.get("provider_used"),
        "safety": data.get("safety", {}),
        "evidence_panel": data.get("evidence_panel", [])
    })


# ─── Left panel: patient context ───
with st.sidebar:
    if LOGO_PATH:
        st.image(LOGO_PATH, width=64)
    st.markdown(
        f'<p style="font-weight:700; color:{C["text"]}; font-size:1.05rem; margin:4px 0 0;">Tiryak</p>',
        unsafe_allow_html=True
    )
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    st.caption("WHO'S ASKING")
    st.session_state.user_type = st.radio(
        "Audience",
        options=["pharmacist", "patient"],
        format_func=lambda x: "Pharmacist" if x == "pharmacist" else "Patient",
        label_visibility="collapsed",
        horizontal=True,
    )

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    st.caption("PATIENT CONTEXT")
    st.session_state.patient_age = st.number_input(
        "Age", min_value=0, max_value=120,
        value=st.session_state.patient_age or 0, step=1,
    ) or None

    st.session_state.conditions = st.multiselect(
        "Conditions",
        options=sorted(set(PRESET_CONDITIONS) | set(st.session_state.conditions)),
        default=st.session_state.conditions,
        accept_new_options=True,
        placeholder="Type to add a condition…",
    )

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    st.caption("CURRENT MEDICATIONS")

    for i, med in enumerate(st.session_state.medications):
        c1, c2 = st.columns([5, 1])
        with c1:
            st.markdown(f'<div class="tk-chip-row">{esc(med)}</div>', unsafe_allow_html=True)
        with c2:
            if st.button("✕", key=f"rm_med_{i}"):
                st.session_state.medications.pop(i)
                st.rerun()

    with st.form("add_med_form", clear_on_submit=True):
        new_med = st.text_input("Add medication", placeholder="e.g. Metformin 500mg", label_visibility="collapsed")
        if st.form_submit_button("+ add", use_container_width=True):
            if new_med.strip():
                st.session_state.medications.append(new_med.strip())
                st.rerun()

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    if st.button("📷 Scan prescription", use_container_width=True):
        st.session_state.show_scan_uploader = not st.session_state.show_scan_uploader

    if st.session_state.show_scan_uploader:
        scan_file = st.file_uploader("Prescription photo", type=["png", "jpg", "jpeg"], label_visibility="collapsed", key="scan_uploader")
        if scan_file is not None:
            b64_img = base64.b64encode(scan_file.getvalue()).decode()
            handle_prescription_image(b64_img, scan_file.type or "image/jpeg")
            st.session_state.show_scan_uploader = False
            st.rerun()

    if not st.session_state.documents:
        refresh_documents()

    with st.expander("⚙️ Manage guideline documents"):
        uploaded_file = st.file_uploader("PDF, DOCX, or PPTX", type=["pdf", "docx", "pptx"], label_visibility="collapsed", key="doc_uploader")
        if uploaded_file is not None:
            if st.button("⚡ Process Document", type="primary", use_container_width=True):
                with st.spinner("Processing..."):
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue())}
                    response = requests.post(f"{API_BASE_URL}/documents/upload", files=files)
                    if response.status_code == 200:
                        st.success(f"✅ Done! {response.json()['num_chunks']} chunks indexed.")
                        refresh_documents()
                    else:
                        st.error(f"❌ Failed: {response.text}")

        if st.session_state.documents:
            for doc in st.session_state.documents:
                is_seed = doc["document_id"].startswith("seed_")
                label = f"🔒 {short_doc_label(doc['filename'])}" if is_seed else f"📄 {short_doc_label(doc['filename'])}"
                c1, c2 = st.columns([5, 1])
                with c1:
                    st.caption(label)
                with c2:
                    if not is_seed:
                        if st.button("🗑️", key=f"del_{doc['document_id']}"):
                            requests.delete(f"{API_BASE_URL}/documents/{doc['document_id']}")
                            refresh_documents()
                            st.rerun()

selected_ids: list = []  # empty = search across all indexed documents

# ─── Right panel: conversation ───
has_conversation = len(st.session_state.chat_history) > 0

if not has_conversation:
    st.markdown(
        f'<div style="text-align:center; padding-top:8vh;">'
        f'<p style="font-size:1.8rem; font-weight:800; color:{C["text"]}; margin-bottom:4px;">Tiryak</p>'
        f'<p style="color:{C["text_muted"]}; max-width:520px; margin:0 auto 24px;">Ask about medication safety and drug interactions — every answer is grounded in official clinical guidelines.</p>'
        f'</div>',
        unsafe_allow_html=True
    )
    cols = st.columns(len(SUGGESTED_PROMPTS))
    for i, prompt in enumerate(SUGGESTED_PROMPTS):
        with cols[i]:
            if st.button(prompt, key=f"suggest_{i}", use_container_width=True):
                handle_text_question(prompt, selected_ids)
                st.rerun()
else:
    chat_html = "".join(render_entry_html(entry) for entry in st.session_state.chat_history)
    st.markdown(f'<div class="chat-scroll" id="tk-chat-scroll">{chat_html}</div>', unsafe_allow_html=True)
    components.html(
        """<script>
        var d = window.parent.document.getElementById('tk-chat-scroll');
        if (d) { d.scrollTop = d.scrollHeight; }
        </script>""",
        height=0,
    )

# ─── Input bar (pinned bottom of right panel) ───
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
