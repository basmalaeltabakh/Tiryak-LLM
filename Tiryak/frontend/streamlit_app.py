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

# ─── Light, on-brand palette (matches .streamlit/config.toml's existing
# green/white/navy identity — we build on it, not against it) ───
COLORS = {
    "bg": "#F3F4F6",
    "surface": "#FFFFFF",
    "surface_sunken": "#F8F9FA",
    "border": "#E3E6EA",
    "border_strong": "#D2D7DE",
    "ink": "#0F1B33",
    "ink_soft": "#48566E",
    "ink_faint": "#71809A",
    "primary": "#22B573",
    "primary_hover": "#1C9962",
    "primary_soft": "#E1F5EC",
    "danger": "#D64545",
    "danger_soft": "#FBEAEA",
    "caution": "#B8860B",
    "caution_soft": "#FBF3DE",
    "neutral": "#6B7280",
    "neutral_soft": "#EEF0F2",
    "user_bubble": "#1B2A4A",
}
C = COLORS

# ─── Session state (must be set before the CSS block below, which reads
# st.session_state.active_view to render the sidebar's active-nav highlight) ───
defaults = {
    "documents": [],
    "chat_history": [],
    "last_processed_input_id": None,
    "user_type": "pharmacist",
    "patient_age": None,
    "conditions": [],
    "medications": [],
    "show_scan_uploader": False,
    "document_scope": [],
    "right_panel_mode": "conversation",
    "right_panel_doc_id": None,
    "summary_cache": {},
    "insights_cache": {},
    "active_view": "home",
    "show_patient_editor": False,
    "health_status": None,
    "language": "en",
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# The language radio further down renders in its natural sidebar position
# (after logo/nav), but Streamlit already syncs a changed widget's value
# into st.session_state[key] before the script reruns — so re-reading it
# here, before anything else in the script calls t(), keeps every label
# on the same rerun as the click instead of lagging by one interaction.
if "language_toggle" in st.session_state:
    st.session_state.language = st.session_state.language_toggle

st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}

    /* ─── Overall UI scale: +12.5% root base, so every rem-based Streamlit
    control (buttons, inputs, spacing) grows with it — headings below get
    their own explicit px targets on top of this ─── */
    html {{ font-size: 18px !important; }}

    .stApp {{ background: {C["bg"]} !important; color: {C["ink"]}; }}
    [data-testid="stAppViewContainer"] {{ background: {C["bg"]} !important; }}
    [data-testid="stHeader"] {{ background: transparent !important; }}
    .block-container {{
        padding-bottom: 110px !important; padding-top: 1.8rem !important;
        max-width: 1240px !important; margin: 0 auto !important;
    }}

    /* ─── Typography baseline: default Streamlit text reads too light —
    force real contrast everywhere except explicitly-secondary elements ─── */
    [data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li,
    .stApp label, [data-testid="stWidgetLabel"] p {{
        color: {C["ink"]} !important; font-weight: 400; font-size: 16px !important; line-height: 1.6;
    }}
    [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {{
        color: {C["ink_soft"]} !important; font-weight: 500 !important; font-size: 15px !important;
    }}
    h1, h2, h3 {{ color: {C["ink"]} !important; font-weight: 700 !important; }}
    .stButton > button, .stFormSubmitButton > button {{ font-size: 15px !important; }}
    .stButton > button p, .stFormSubmitButton > button p {{ font-size: 15px !important; }}

    /* ─── Sidebar: fixed width, clean surface ─── */
    section[data-testid="stSidebar"] {{
        background: {C["surface"]} !important;
        min-width: 292px !important; max-width: 292px !important; width: 292px !important;
        border-right: 1px solid {C["border"]};
    }}
    section[data-testid="stSidebar"] > div {{ width: 292px !important; }}
    [data-testid="stSidebarResizeHandle"] {{ display: none !important; }}
    section[data-testid="stSidebar"] * {{ color: {C["ink"]}; }}
    section[data-testid="stSidebar"] .stCaption, section[data-testid="stSidebar"] small {{ color: {C["ink_soft"]} !important; }}
    section[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] > div > div {{ padding: 28px 20px 16px !important; }}

    /* ─── Brand / logo area ─── */
    .tk-brand-name {{ font-weight: 700; color: {C["ink"]}; font-size: 26px; letter-spacing: -0.02em; line-height: 1.15; margin-top: 8px; }}
    .tk-brand-tag {{ font-size: 14px; color: {C["ink_soft"]}; font-weight: 500; margin-top: 2px; }}

    /* ─── Section labels: real headings, not disabled-looking tags ─── */
    .tk-eyebrow {{
        font-size: 17px; font-weight: 700; letter-spacing: 0.01em;
        color: {C["ink"]}; margin: 22px 0 10px;
    }}
    .tk-eyebrow:first-of-type {{ margin-top: 0; }}

    /* ─── Segmented "who's asking" control ─── */
    div[data-testid="stRadio"] > div[role="radiogroup"] {{
        display: flex; gap: 4px; background: {C["surface_sunken"]};
        border: 1px solid {C["border"]}; border-radius: 10px; padding: 4px;
    }}
    div[data-testid="stRadio"] label {{
        flex: 1; justify-content: center; margin: 0 !important;
        border-radius: 7px; padding: 6px 8px !important; font-weight: 600; color: {C["ink_soft"]} !important;
        transition: background 0.15s; white-space: nowrap;
    }}
    div[data-testid="stRadio"] label p {{ white-space: nowrap !important; }}
    div[data-testid="stRadio"] label[data-selected="true"] {{
        background: {C["primary"]}; color: #fff !important;
    }}
    div[data-testid="stRadio"] label[data-selected="true"] p {{ color: #fff !important; }}

    /* ─── Form inputs: consistent, soft, premium ─── */
    div[data-testid="stNumberInputContainer"], div[data-testid="stTextInputRootElement"],
    div[data-testid="stMultiSelectTagsContainer"], div[data-baseweb="select"] > div {{
        background: {C["surface"]} !important; border: 1px solid {C["border_strong"]} !important; border-radius: 9px !important;
    }}
    div[data-testid="stNumberInputField"], div[data-testid="stTextInputRootElement"] input,
    div[data-testid="stMultiSelectTagsContainer"] input {{
        background: transparent !important; color: {C["ink"]} !important;
    }}
    ul[role="listbox"], div[role="listbox"] {{ background: {C["surface"]} !important; border: 1px solid {C["border_strong"]} !important; }}
    [data-testid="stFileUploaderDropzone"] {{
        background: {C["surface_sunken"]} !important; border: 1.5px dashed {C["border_strong"]} !important; border-radius: 12px !important;
    }}
    [data-testid="stFileUploaderDropzone"] * {{ color: {C["ink_soft"]} !important; }}

    /* ─── Buttons: larger, easier click targets ─── */
    .stButton > button, .stFormSubmitButton > button {{
        border-radius: 10px !important; font-weight: 600 !important;
        background: {C["surface"]} !important; color: {C["ink"]} !important;
        border: 1px solid {C["border_strong"]} !important;
        transition: all 0.15s ease !important;
        padding: 11px 20px !important; min-height: 46px !important;
    }}
    .stButton > button:hover, .stFormSubmitButton > button:hover {{
        border-color: {C["primary"]} !important; color: {C["primary_hover"]} !important;
        box-shadow: 0 1px 4px rgba(34,181,115,0.15) !important;
    }}
    .stButton > button[kind="primary"] {{ background: {C["primary"]} !important; border: none !important; color: #fff !important; }}
    .stButton > button[kind="primary"]:hover {{ background: {C["primary_hover"]} !important; color: #fff !important; }}
    .stButton > button p, .stFormSubmitButton > button p {{ color: inherit !important; }}
    [data-testid="stPopoverButton"] {{ border-radius: 9px !important; }}

    /* ─── Medication chip rows ─── */
    .tk-chip-row {{
        display: flex; align-items: center; justify-content: space-between;
        background: {C["surface_sunken"]}; border: 1px solid {C["border"]};
        border-radius: 8px; padding: 7px 11px; margin-bottom: 6px; font-size: 0.85rem; color: {C["ink"]};
    }}

    /* ─── Document library cards ─── */
    .tk-doc-card {{
        background: {C["surface_sunken"]}; border: 1px solid {C["border"]}; border-radius: 10px;
        padding: 10px 12px; margin-bottom: 8px;
    }}
    .tk-doc-name {{ font-size: 0.82rem; font-weight: 600; color: {C["ink"]}; margin-bottom: 2px; }}
    .tk-doc-meta {{ font-size: 0.72rem; color: {C["ink_faint"]}; }}

    /* ─── Chat scroll area (Claude-style generous spacing) ─── */
    .chat-scroll {{ max-height: calc(100vh - 240px); overflow-y: auto; padding: 4px 8px 24px 2px; }}

    .tk-user-row {{ display: flex; justify-content: flex-end; margin: 22px 0 8px; }}
    .tk-user-bubble {{
        background: {C["user_bubble"]}; color: #fff; padding: 11px 17px;
        border-radius: 16px 16px 4px 16px; max-width: 68%;
        font-size: 0.94rem; line-height: 1.55; word-wrap: break-word;
    }}
    .tk-user-image {{ max-width: 220px; border-radius: 14px; border: 1px solid {C["border"]}; }}

    /* ─── Answer card (Notion-style white card, soft shadow, generous padding) ─── */
    .tk-card {{
        background: {C["surface"]}; border: 1px solid {C["border"]};
        border-radius: 14px; padding: 18px 20px; margin: 4px 0 10px; max-width: 86%;
        box-shadow: 0 1px 3px rgba(27,42,74,0.06);
    }}

    .tk-badge-row {{ display: flex; align-items: center; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; }}
    .badge {{
        display: inline-flex; align-items: center; gap: 6px; padding: 4px 12px;
        border-radius: 20px; font-size: 0.78rem; font-weight: 700; border: 1px solid transparent;
    }}
    .badge-safe {{ color: {C["primary_hover"]}; background: {C["primary_soft"]}; }}
    .badge-caution {{ color: {C["caution"]}; background: {C["caution_soft"]}; }}
    .badge-emergency {{ color: {C["danger"]}; background: {C["danger_soft"]}; }}
    .badge-insufficient {{ color: {C["neutral"]}; background: {C["neutral_soft"]}; }}
    .tk-conf-label {{ font-size: 0.76rem; color: {C["ink_faint"]}; font-weight: 500; }}

    .tk-answer-text {{ font-size: 16px; line-height: 1.7; color: {C["ink"]}; }}

    .tk-tip {{
        background: {C["caution_soft"]}; border: 1px solid {C["caution"]}33; color: #7A5D0A;
        padding: 10px 14px; border-radius: 10px; margin-top: 14px; font-size: 0.84rem; line-height: 1.5;
    }}

    /* ─── Perplexity-style inline citation chip strip ─── */
    .tk-cite-strip {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 14px; }}
    .tk-cite-chip {{
        display: inline-flex; align-items: center; gap: 5px;
        background: {C["surface_sunken"]}; border: 1px solid {C["border"]}; border-radius: 8px;
        padding: 4px 9px; font-size: 0.72rem; color: {C["ink_soft"]};
        font-variant-numeric: tabular-nums;
    }}
    .tk-cite-chip b {{ color: {C["primary_hover"]}; font-weight: 700; }}
    .tk-more-hint {{ font-size: 0.72rem; color: {C["ink_faint"]}; margin-top: 8px; }}

    .tk-emg-btns {{ display: flex; gap: 10px; margin: 14px 0 10px; }}
    .tk-emg-call {{
        background: {C["danger"]}; color: #fff; padding: 9px 18px; border-radius: 10px;
        text-decoration: none; font-weight: 700; font-size: 0.88rem;
    }}
    .tk-emg-footer {{ font-size: 0.78rem; color: {C["ink_faint"]}; }}

    .tk-search-table {{ width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 0.85rem; }}
    .tk-search-table td {{ padding: 6px 4px; border-bottom: 1px solid {C["border"]}; color: {C["ink_soft"]}; }}
    .tk-search-table td:first-child {{ color: {C["ink_faint"]}; }}
    .tk-search-table td:last-child {{ text-align: right; font-weight: 600; color: {C["ink"]}; }}

    /* ─── Medicine card (Notion-card feel) ─── */
    .tk-med-card {{
        background: {C["surface"]}; border: 1px solid {C["border"]}; border-radius: 12px;
        padding: 14px 16px; margin-bottom: 10px; box-shadow: 0 1px 3px rgba(27,42,74,0.05);
    }}
    .tk-med-head {{ display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 6px; }}
    .tk-med-name {{ font-weight: 700; font-size: 0.95rem; color: {C["ink"]}; }}
    .tk-med-source {{ font-size: 0.68rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.03em; padding: 2px 8px; border-radius: 6px; }}
    .tk-med-source.egypt {{ background: {C["primary_soft"]}; color: {C["primary_hover"]}; }}
    .tk-med-source.fda {{ background: {C["neutral_soft"]}; color: {C["neutral"]}; }}
    .tk-med-source.notfound {{ background: {C["danger_soft"]}; color: {C["danger"]}; }}
    .tk-med-row {{ font-size: 15px; color: {C["ink_soft"]}; margin-top: 4px; }}
    .tk-med-row b {{ color: {C["ink"]}; font-weight: 600; }}

    /* ─── Right panel ─── */
    .tk-panel-header {{ font-size: 19px; font-weight: 700; color: {C["ink"]}; margin-bottom: 16px; }}
    .tk-panel-empty {{ color: {C["ink_soft"]}; font-size: 15px; text-align: center; padding: 40px 12px; line-height: 1.6; }}
    .tk-evidence-item {{ border-bottom: 1px solid {C["border"]}; padding: 12px 0; }}
    .tk-evidence-item:first-child {{ padding-top: 0; }}
    .tk-evidence-item:last-child {{ border-bottom: none; }}
    .tk-evidence-item blockquote {{
        margin: 4px 0 6px; padding: 8px 11px; border-left: 3px solid {C["primary"]}77;
        background: {C["surface_sunken"]}; border-radius: 6px; font-size: 0.83rem; color: {C["ink_soft"]}; font-style: italic;
    }}
    .tk-evidence-source {{ font-size: 0.74rem; color: {C["ink_faint"]}; font-variant-numeric: tabular-nums; }}
    .tk-metric-row {{ display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid {C["border"]}; font-size: 0.85rem; }}
    .tk-metric-row:last-child {{ border-bottom: none; }}
    .tk-metric-label {{ color: {C["ink_faint"]}; }}
    .tk-metric-value {{ color: {C["ink"]}; font-weight: 600; }}

    /* Composer: kept in its real position in the content flow (inside
    .block-container, after the columns) and pinned via `sticky` rather than
    `fixed` — `fixed` uses the viewport as its containing block, which
    ignores the sidebar-aware centering .block-container gets from its
    parent flex layout, and fights the iframe's own width="" attribute.
    `sticky` respects the normal flow, so it inherits the exact same width
    as the rest of the content by construction — no manual math needed. */
    iframe[title="streamlit_app.voice_chat_input"] {{
        position: sticky; bottom: 24px;
        width: 100% !important;
        z-index: 999;
        filter: drop-shadow(0 10px 30px rgba(15,27,51,0.14));
    }}

    /* ─── Sidebar nav: premium vertical list with real breathing room ─── */
    section[data-testid="stSidebar"] div[data-testid="stElementContainer"]:has(.stButton) {{ margin-bottom: 22px; }}
    section[data-testid="stSidebar"] .stButton > button {{
        text-align: left !important; justify-content: flex-start !important;
        border: 1px solid transparent !important; background: transparent !important;
        font-weight: 600 !important; font-size: 16px !important;
        padding: 16px 18px !important; min-height: 54px !important; border-radius: 12px !important;
        transition: background 0.12s ease, color 0.12s ease !important;
        display: flex !important; align-items: center !important; gap: 14px !important;
    }}
    section[data-testid="stSidebar"] .stButton > button:hover {{
        background: {C["surface_sunken"]} !important; box-shadow: none !important; color: {C["ink"]} !important;
    }}
    section[data-testid="stSidebar"] .stButton > button p {{ text-align: left !important; letter-spacing: 0.01em; font-size: 16px !important; }}
    section[data-testid="stSidebar"] .stButton [data-testid="stIconMaterial"] {{ font-size: 22px !important; }}
    /* Anchor a quiet footer mark at the bottom so the nav's empty space
    below it reads as intentional breathing room, not an unfinished layout */
    section[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] > div > div {{
        display: flex !important; flex-direction: column !important; min-height: calc(100vh - 44px) !important;
    }}
    .tk-sidebar-footer {{ margin-top: auto; padding-top: 20px; border-top: 1px solid {C["border"]}; font-size: 13px; color: {C["ink_faint"]}; }}
    /* Active nav item — targeted via Streamlit's real st-key-<key> class, not a manual div wrap */
    section[data-testid="stSidebar"] .st-key-nav_{st.session_state.active_view} > div > button {{
        background: {C["primary_soft"]} !important; color: {C["primary_hover"]} !important;
        border-left: 3px solid {C["primary"]} !important; border-radius: 0 10px 10px 0 !important;
        padding-left: 13px !important;
    }}
    section[data-testid="stSidebar"] .st-key-nav_{st.session_state.active_view} > div > button p {{
        color: {C["primary_hover"]} !important; font-weight: 700 !important;
    }}

    /* ─── Top bar: page title, 26-30px target ─── */
    .tk-topbar-title {{ font-size: 28px; font-weight: 700; color: {C["ink"]}; letter-spacing: -0.01em; line-height: 1.2; }}
    div[data-testid="column"]:has(.tk-topbar-title) {{ display: flex; align-items: center; }}
    div[data-testid="stRadio"] {{ display: flex; justify-content: flex-end; }}
    div[data-testid="stRadio"] > div[role="radiogroup"] {{ max-width: 340px; }}
    div[data-testid="stRadio"] label {{ font-size: 15px !important; padding: 9px 16px !important; }}

    /* ─── Dashboard cards: premium padding, 18-20px titles ─── */
    .tk-dash-card {{
        background: {C["surface"]}; border: 1px solid {C["border"]}; border-radius: 16px;
        padding: 24px 26px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(15,27,51,0.05);
    }}
    .tk-dash-card-head {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }}
    .tk-dash-card-title {{ font-size: 19px; font-weight: 600; color: {C["ink"]}; line-height: 1.3; }}

    /* ─── Hero: label → title (32-40px) → one-line description ─── */
    .tk-hero-eyebrow {{ font-size: 15px; font-weight: 600; color: {C["ink_soft"]}; margin-bottom: 4px; }}
    .tk-hero-title {{ font-size: 36px; font-weight: 700; color: {C["ink"]}; letter-spacing: -0.02em; margin-bottom: 10px; line-height: 1.2; }}
    .tk-hero-tagline {{ color: {C["ink_faint"]}; font-size: 14px; font-weight: 500; margin-bottom: 8px; }}
    .tk-hero-sub {{ color: {C["ink_soft"]}; font-size: 17px; font-weight: 400; line-height: 1.5; }}

    .tk-patient-pill {{ display: inline-flex; align-items: center; gap: 6px; background: {C["surface_sunken"]}; border: 1px solid {C["border"]}; border-radius: 20px; padding: 6px 14px; font-size: 14px; font-weight: 500; color: {C["ink_soft"]}; margin: 2px 4px 2px 0; }}
    .tk-readiness-dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }}

    /* ─── Quick action cards: larger icon, bold title-as-button, roomier description ─── */
    .tk-qa-icon {{ font-size: 34px; margin-bottom: 12px; line-height: 1; }}
    .tk-qa-desc {{ font-size: 15px; color: {C["ink_soft"]}; margin-top: 10px; line-height: 1.4; }}
    .st-key-qa_ask button, .st-key-qa_scan button, .st-key-qa_upload button {{
        font-size: 19px !important; font-weight: 700 !important;
        padding: 6px 0 !important; border: none !important; background: transparent !important;
        justify-content: flex-start !important; min-height: unset !important;
    }}
    .st-key-qa_ask button p, .st-key-qa_scan button p, .st-key-qa_upload button p {{ font-size: 19px !important; }}
    .st-key-qa_ask button:hover, .st-key-qa_scan button:hover, .st-key-qa_upload button:hover {{
        color: {C["primary_hover"]} !important; box-shadow: none !important;
    }}
    .st-key-qa_ask button p, .st-key-qa_scan button p, .st-key-qa_upload button p {{ text-align: left !important; }}
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.tk-qa-icon) {{
        transition: transform 0.18s ease, box-shadow 0.18s ease;
    }}
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.tk-qa-icon):hover {{
        transform: translateY(-3px);
        box-shadow: 0 10px 24px rgba(15,27,51,0.12);
    }}
    </style>
""", unsafe_allow_html=True)

# ─── Localization: centralized translation dictionaries, English default.
# Frontend-only — this changes displayed labels, never the request payloads
# sent to the backend (those stay keyed by stable English/internal values). ───
TRANSLATIONS = {
    "en": {
        "language_name": "English",
        "brand_tag": "Guideline Assistant",
        "sidebar_footer": "Tiryak · Clinical Guideline Assistant",
        "language_label": "Language",
        "nav_home": "Home", "nav_chats": "Chats", "nav_library": "Library", "nav_settings": "Settings",
        "audience_pharmacist": "Pharmacist", "audience_patient": "Patient",

        "hero_eyebrow": "Welcome back",
        "hero_title": "Medication Safety Assistant",
        "hero_tagline": "Evidence-based AI assistant powered by trusted clinical guidelines.",
        "hero_sub": "Ask about medication safety and drug interactions — every answer is grounded in official clinical guidelines.",

        "quick_actions": "Quick actions",
        "qa_ask_title": "Ask AI", "qa_ask_desc": "Start a conversation",
        "qa_scan_title": "Scan prescription", "qa_scan_desc": "OCR + analysis",
        "qa_upload_title": "Upload document", "qa_upload_desc": "Add clinical references",

        "recent_conversation": "Recent conversation",
        "you_prefix": "You",
        "continue_in_chats": "Continue in Chats →",

        "knowledge_base_title": "Clinical Knowledge Base",
        "guidelines_loaded": "{n} clinical guideline{plural} loaded",
        "open_library": "Open Library →",

        "current_patient": "Current patient",
        "edit_btn": "Edit",
        "add_patient_context": "+ Add patient context",

        "age_label": "Age",
        "conditions_label": "Conditions",
        "conditions_placeholder": "Type to add a condition…",
        "medications_label": "Medications",
        "add_medication_label": "Add medication",
        "add_medication_placeholder": "e.g. Metformin 500mg",
        "add_btn": "+ add",
        "done_btn": "Done",

        "library_title": "Library",
        "library_upload_label": "PDF, DOCX, or PPTX",
        "process_document": "⚡ Process document",
        "processing_document": "Processing document…",
        "parsing": "Parsing…",
        "indexed_chunks": "✅ Indexed — {n} chunks",
        "failed_generic": "❌ Failed",
        "no_documents_yet": "No documents loaded yet — upload one above.",
        "summarize_btn": "📝 Summarize",
        "insights_btn": "🔍 Insights",
        "remove_btn": "🗑️ Remove",

        "settings_title": "Settings",
        "patient_profile_title": "Patient profile",
        "patient_profile_caption": "Session-only — resets on refresh. No cross-session profile storage exists yet.",
        "diagnostics_title": "Diagnostics",
        "check_backend": "Check backend readiness",
        "backend_ready": "Ready",
        "backend_unreachable": "Unreachable",
        "last_provider_used": "Last AI provider used: {provider}",

        "chats_empty_sub": "Ask about medication safety and drug interactions — every answer is grounded in official clinical guidelines.",
        "new_chat": "＋ New chat",
        "scan_prescription_caption": "📷 Scan prescription",
        "prescription_photo_label": "Prescription photo",

        "details_header": "Details",
        "loaded_knowledge_sources": "Loaded knowledge sources",
        "search_scope": "Search scope",
        "search_scope_placeholder": "All documents",
        "ai_readiness": "AI readiness",
        "active_patient": "Active patient",
        "no_documents_loaded": "No documents loaded yet.",
        "tab_evidence": "Evidence", "tab_sources": "Sources", "tab_confidence": "Confidence",
        "no_evidence": "No retrieved evidence for this answer.",
        "no_sources": "No sources referenced for this answer.",
        "back_to_conversation": "← Back to conversation",
        "no_summary_yet": "No summary generated yet.",
        "no_insights_yet": "No insights generated yet.",
        "section_by_section": "Section-by-section ({n} sections)",
        "tab_entities": "Entities", "tab_tables": "Tables",
        "no_tabular_data": "No tabular data found in this document.",
        "retrieval_confidence": "Retrieval confidence",
        "grounding_verdict": "Grounding verdict",
        "ai_provider": "AI provider",

        "chat_placeholder": "Ask about any medication...",
        "request_failed": "❌ Request failed: {error}",
        "request_failed_label": "❌ Request failed",
        "error_generic": "❌ Error: {error}",
        "badge_safe": "✅ Safe", "badge_caution": "⚠️ Caution",
        "badge_emergency": "🚨 Emergency", "badge_insufficient": "🔍 Insufficient evidence",
        "confidence_suffix": "{level} confidence",
        "citation_hint": "Full evidence, sources &amp; confidence breakdown in the panel →",
        "table_documents": "Documents", "table_indexed": "{n} indexed",
        "table_closest_match": "Closest match", "table_below_threshold": "below threshold",
        "table_threshold": "Threshold",
        "med_not_found_label": "Not found",
        "med_not_found_detail": "Not in the Egyptian drug database or FDA — confirm the name with a pharmacist.",
        "med_source_egypt": "Egypt DB", "med_source_fda": "FDA",
        "med_active_ingredient": "Active ingredient:", "med_manufacturer": "Manufacturer:",
        "med_class": "Class:", "med_price": "Price:", "med_purpose": "Purpose:", "med_currency": "EGP",
        "confidence_low": "Low", "confidence_medium": "Medium", "confidence_high": "High", "confidence_na": "N/a",
        "pages_label": "Pages {range}", "table_fallback_title": "Table",
        "entity_people": "People", "entity_organizations": "Organizations", "entity_dates": "Dates",
        "entity_monetary_amounts": "Monetary amounts", "entity_percentages": "Percentages",
        "entity_parse_error": "Could not parse entity extraction output.",
        "checking_guidelines": "🔍 Checking clinical guidelines...",
        "transcribing": "🎙️ Transcribing & checking guidelines...",
        "reading_prescription": "📷 Reading prescription — this can take up to 2 minutes...",
        "done_medications_identified": "✅ Done — {n} medication(s) identified",
        "done_nothing_legible": "✅ Done — nothing clearly legible",
        "failed_to_read_prescription": "❌ Failed to read prescription",
        "summarizing": "Summarizing — large documents batch many LLM calls and can take a few minutes…",
        "extracting_insights": "Extracting entities & tables…",
        "failed_colon": "❌ Failed: {error}",
    },
    "ar": {
        "language_name": "العربية",
        "brand_tag": "مساعد الإرشادات السريرية",
        "sidebar_footer": "Tiryak · مساعد الإرشادات السريرية",
        "language_label": "اللغة",
        "nav_home": "الرئيسية", "nav_chats": "المحادثات", "nav_library": "المكتبة", "nav_settings": "الإعدادات",
        "audience_pharmacist": "صيدلي", "audience_patient": "مريض",

        "hero_eyebrow": "مرحبًا بعودتك",
        "hero_title": "مساعد سلامة الأدوية",
        "hero_tagline": "مساعد ذكاء اصطناعي قائم على الأدلة، مدعوم بإرشادات سريرية موثوقة.",
        "hero_sub": "اسأل عن سلامة الأدوية والتفاعلات الدوائية — كل إجابة مبنية على إرشادات سريرية رسمية.",

        "quick_actions": "إجراءات سريعة",
        "qa_ask_title": "اسأل الذكاء الاصطناعي", "qa_ask_desc": "ابدأ محادثة",
        "qa_scan_title": "مسح الروشتة", "qa_scan_desc": "تحليل ضوئي وتحليل بيانات",
        "qa_upload_title": "رفع مستند", "qa_upload_desc": "إضافة مراجع سريرية",

        "recent_conversation": "آخر محادثة",
        "you_prefix": "أنت",
        "continue_in_chats": "أكمل في المحادثات ←",

        "knowledge_base_title": "قاعدة المعرفة السريرية",
        "guidelines_loaded": "تم تحميل {n} إرشاد سريري",
        "open_library": "افتح المكتبة ←",

        "current_patient": "المريض الحالي",
        "edit_btn": "تعديل",
        "add_patient_context": "+ إضافة بيانات المريض",

        "age_label": "العمر",
        "conditions_label": "الحالات المرضية",
        "conditions_placeholder": "اكتب لإضافة حالة…",
        "medications_label": "الأدوية",
        "add_medication_label": "إضافة دواء",
        "add_medication_placeholder": "مثال: ميتفورمين 500 مجم",
        "add_btn": "+ إضافة",
        "done_btn": "تم",

        "library_title": "المكتبة",
        "library_upload_label": "PDF أو DOCX أو PPTX",
        "process_document": "⚡ معالجة المستند",
        "processing_document": "جارٍ معالجة المستند…",
        "parsing": "جارٍ التحليل…",
        "indexed_chunks": "✅ تمت الفهرسة — {n} جزء",
        "failed_generic": "❌ فشل",
        "no_documents_yet": "لا توجد مستندات محمّلة بعد — قم برفع مستند أعلاه.",
        "summarize_btn": "📝 تلخيص",
        "insights_btn": "🔍 رؤى",
        "remove_btn": "🗑️ حذف",

        "settings_title": "الإعدادات",
        "patient_profile_title": "ملف المريض",
        "patient_profile_caption": "خاص بالجلسة فقط — يُعاد ضبطه عند التحديث. لا يوجد تخزين دائم للملف بعد.",
        "diagnostics_title": "التشخيصات",
        "check_backend": "التحقق من جاهزية الخادم",
        "backend_ready": "جاهز",
        "backend_unreachable": "غير متاح",
        "last_provider_used": "آخر مزوّد ذكاء اصطناعي مستخدم: {provider}",

        "chats_empty_sub": "اسأل عن سلامة الأدوية والتفاعلات الدوائية — كل إجابة مبنية على إرشادات سريرية رسمية.",
        "new_chat": "＋ محادثة جديدة",
        "scan_prescription_caption": "📷 مسح الروشتة",
        "prescription_photo_label": "صورة الروشتة",

        "details_header": "التفاصيل",
        "loaded_knowledge_sources": "مصادر المعرفة المحمّلة",
        "search_scope": "نطاق البحث",
        "search_scope_placeholder": "كل المستندات",
        "ai_readiness": "جاهزية الذكاء الاصطناعي",
        "active_patient": "المريض النشط",
        "no_documents_loaded": "لا توجد مستندات محمّلة بعد.",
        "tab_evidence": "الأدلة", "tab_sources": "المصادر", "tab_confidence": "الثقة",
        "no_evidence": "لا توجد أدلة مسترجعة لهذه الإجابة.",
        "no_sources": "لا توجد مصادر مرجعية لهذه الإجابة.",
        "back_to_conversation": "→ العودة إلى المحادثة",
        "no_summary_yet": "لم يتم إنشاء ملخص بعد.",
        "no_insights_yet": "لم يتم إنشاء رؤى بعد.",
        "section_by_section": "قسمًا بقسم ({n} أقسام)",
        "tab_entities": "الكيانات", "tab_tables": "الجداول",
        "no_tabular_data": "لم يتم العثور على بيانات جدولية في هذا المستند.",
        "retrieval_confidence": "ثقة الاسترجاع",
        "grounding_verdict": "نتيجة التحقق من الأدلة",
        "ai_provider": "مزوّد الذكاء الاصطناعي",

        "chat_placeholder": "اسأل عن أي دواء...",
        "request_failed": "❌ فشل الطلب: {error}",
        "request_failed_label": "❌ فشل الطلب",
        "error_generic": "❌ خطأ: {error}",
        "entity_people": "أشخاص", "entity_organizations": "منظمات", "entity_dates": "تواريخ",
        "entity_monetary_amounts": "مبالغ مالية", "entity_percentages": "نسب مئوية",
        "entity_parse_error": "تعذّر تحليل نتائج استخراج الكيانات.",
        "badge_safe": "✅ آمن", "badge_caution": "⚠️ تنبيه",
        "badge_emergency": "🚨 طوارئ", "badge_insufficient": "🔍 أدلة غير كافية",
        "confidence_suffix": "ثقة {level}",
        "citation_hint": "الأدلة الكاملة والمصادر وتفاصيل الثقة في اللوحة الجانبية ←",
        "table_documents": "المستندات", "table_indexed": "{n} مفهرس",
        "table_closest_match": "أقرب تطابق", "table_below_threshold": "أقل من الحد الأدنى",
        "table_threshold": "الحد الأدنى",
        "med_not_found_label": "غير موجود",
        "med_not_found_detail": "غير موجود في قاعدة بيانات الأدوية المصرية أو FDA — يرجى التأكد من الاسم مع الصيدلي.",
        "med_source_egypt": "قاعدة البيانات المصرية", "med_source_fda": "FDA",
        "med_active_ingredient": "المادة الفعالة:", "med_manufacturer": "الشركة المصنعة:",
        "med_class": "الفئة الدوائية:", "med_price": "السعر:", "med_purpose": "الغرض:", "med_currency": "جنيه مصري",
        "confidence_low": "منخفضة", "confidence_medium": "متوسطة", "confidence_high": "عالية", "confidence_na": "غير متاحة",
        "pages_label": "صفحات {range}", "table_fallback_title": "جدول",
        "checking_guidelines": "🔍 جارٍ التحقق من الإرشادات السريرية...",
        "transcribing": "🎙️ جارٍ تفريغ الصوت والتحقق من الإرشادات...",
        "reading_prescription": "📷 جارٍ قراءة الروشتة — قد يستغرق ذلك حتى دقيقتين...",
        "done_medications_identified": "✅ تم — تم التعرف على {n} دواء",
        "done_nothing_legible": "✅ تم — لا توجد نصوص واضحة للقراءة",
        "failed_to_read_prescription": "❌ فشل في قراءة الروشتة",
        "summarizing": "جارٍ التلخيص — المستندات الكبيرة تستدعي عدة طلبات ذكاء اصطناعي وقد تستغرق بضع دقائق…",
        "extracting_insights": "جارٍ استخراج الكيانات والجداول…",
        "failed_colon": "❌ فشل: {error}",
    },
}

CONDITION_LABELS_AR = {
    "Diabetes": "السكري",
    "Hypertension": "ضغط الدم المرتفع",
    "Kidney disease (CKD)": "مرض الكلى المزمن",
    "Liver disease": "مرض الكبد",
    "Pregnancy": "الحمل",
    "Asthma / COPD": "الربو / الانسداد الرئوي المزمن",
    "Heart failure": "قصور القلب",
    "Elderly (65+)": "كبار السن (65+)",
}


def t(key: str, **kwargs) -> str:
    """Looks up `key` in the translation dict for the active UI language,
    falling back to English, then to the key itself if still missing."""
    lang = st.session_state.get("language", "en")
    template = TRANSLATIONS.get(lang, {}).get(key, TRANSLATIONS["en"].get(key, key))
    return template.format(**kwargs) if kwargs else template


def is_rtl() -> bool:
    return st.session_state.get("language") == "ar"


def condition_label(value: str) -> str:
    if is_rtl():
        return CONDITION_LABELS_AR.get(value, value)
    return value


if is_rtl():
    st.markdown(f"""
    <style>
    /* ─── RTL: text direction + the sidebar's screen side only. The rest of
    the layout (card order, button/icon positions, composer, columns) stays
    exactly where it is in English — we deliberately do NOT cascade
    `direction: rtl` from the page root, since that would also flip every
    flex row (columns, button internals, the composer bar) via the CSS
    flexbox spec, not just text. Only two things move: ─── */

    /* 1) Sidebar to the right — the one explicitly requested layout change.
    stAppViewContainer is sidebar + main content as flex row siblings;
    row-reverse swaps their screen side without touching `direction`
    anywhere else, so nothing inside either child gets mirrored. */
    [data-testid="stAppViewContainer"] {{ flex-direction: row-reverse !important; }}
    section[data-testid="stSidebar"] {{ border-right: none !important; border-left: 1px solid {C["border"]}; }}

    /* 2) Right-align + RTL-shape standalone prose/heading text (not
    buttons, not icons, not multi-item flex rows) so Arabic reads
    naturally without moving any icon, button, or card. */
    .tk-hero-eyebrow, .tk-hero-title, .tk-hero-tagline, .tk-hero-sub,
    .tk-eyebrow, .tk-dash-card-title, .tk-panel-header, .tk-topbar-title,
    .tk-qa-desc, .tk-brand-tag, .tk-sidebar-footer, .tk-patient-pill,
    [data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li,
    [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {{
        direction: rtl; text-align: right;
    }}
    </style>
    """, unsafe_allow_html=True)

PRESET_CONDITIONS = [
    "Diabetes", "Hypertension", "Kidney disease (CKD)", "Liver disease",
    "Pregnancy", "Asthma / COPD", "Heart failure", "Elderly (65+)",
]

SUGGESTED_PROMPTS_EN = [
    "What medications increase the risk of falls in elderly patients?",
    "What are the sick day rules for common medications?",
    "How should benzodiazepines be tapered safely?",
]
SUGGESTED_PROMPTS_AR = [
    "ما هي الأدوية التي تزيد من خطر السقوط لدى كبار السن؟",
    "ما هي قواعد أيام المرض للأدوية الشائعة؟",
    "كيف يتم تقليل جرعة البنزوديازيبينات بأمان؟",
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

    language_note = "[Respond in Arabic.]" if contains_arabic(question_text) else "[Respond in English.]"
    enriched = f"{language_note}\n\n{question_text}"
    if parts:
        enriched = f"[Patient context — {' '.join(parts)}]\n\n{enriched}"
    return enriched


def active_scope_ids() -> list:
    return list(st.session_state.document_scope)


def check_backend_health() -> bool:
    """Pings the real, existing GET /health endpoint — no backend change,
    just the first frontend use of a route that already existed."""
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=4)
        return response.status_code == 200
    except requests.RequestException:
        return False


def patient_context_summary() -> str:
    parts = []
    if st.session_state.patient_age:
        parts.append(f"Age {st.session_state.patient_age}")
    if st.session_state.conditions:
        parts.append(", ".join(st.session_state.conditions))
    if st.session_state.medications:
        parts.append(f"{len(st.session_state.medications)} medication(s)")
    return " · ".join(parts)


def has_patient_context() -> bool:
    return bool(st.session_state.patient_age or st.session_state.conditions or st.session_state.medications)


# ─── Card renderers ───
def render_answer_card(entry: dict, risk_level: str) -> str:
    if risk_level == "allowed":
        badge_label, badge_cls = t("badge_safe"), "badge-safe"
        tip = "🛡️ المعلومة دي للمساعدة بس ومش بديل عن رأي الصيدلي أو الدكتور."
    else:
        badge_label, badge_cls = t("badge_caution"), "badge-caution"
        tip = "⚠️ السؤال ده خاص بحالة معينة — يفضل تتأكد مع صيدلي أو دكتور قبل ما تتصرف بناءً عليه."

    conf = (entry.get("confidence") or {}).get("retrieval_confidence", "medium")
    conf_word = t(f"confidence_{str(conf).lower()}") if f"confidence_{str(conf).lower()}" in TRANSLATIONS["en"] else t("confidence_na")
    conf_label = t("confidence_suffix", level=conf_word)

    panel = entry.get("evidence_panel") or []
    cite_html = ""
    if panel:
        chips = []
        for i, ev in enumerate(panel[:5], start=1):
            chips.append(
                f'<span class="tk-cite-chip"><b>{i}</b> {short_doc_label(ev.get("filename"))} · p.{ev.get("page_number", "?")}</span>'
            )
        cite_html = f'<div class="tk-cite-strip">{"".join(chips)}</div>'
        if len(panel) > 1 or entry.get("provider_used"):
            cite_html += f'<div class="tk-more-hint">{t("citation_hint")}</div>'

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
      {cite_html}
    </div>''')


def render_emergency_card() -> str:
    return _flatten(f'''
    <div class="tk-card">
      <span class="badge badge-emergency">{t("badge_emergency")}</span>
      <div dir="rtl" class="tk-answer-text" style="margin-top:10px;">روح أقرب مستشفى دلوقتي</div>
      <div class="tk-emg-btns">
        <a class="tk-emg-call" href="tel:123">اتصل بـ ١٢٣</a>
      </div>
      <div dir="rtl" class="tk-emg-footer">النظام مش بيجاوب على أسئلة الطوارئ</div>
    </div>''')


def render_insufficient_card() -> str:
    doc_count = len(st.session_state.documents) if st.session_state.documents else "—"
    return _flatten(f'''
    <div class="tk-card">
      <span class="badge badge-insufficient">{t("badge_insufficient")}</span>
      <div dir="rtl" class="tk-answer-text" style="margin-top:10px;">مفيش في الأدلة معلومة واضحة</div>
      <table class="tk-search-table">
        <tr><td>{t("table_documents")}</td><td>{t("table_indexed", n=doc_count)}</td></tr>
        <tr><td>{t("table_closest_match")}</td><td>{t("table_below_threshold")}</td></tr>
        <tr><td>{t("table_threshold")}</td><td>{INSUFFICIENT_EVIDENCE_DISTANCE_THRESHOLD}</td></tr>
      </table>
    </div>''')


def render_medicine_card(drug: dict) -> str:
    if drug.get("not_found"):
        return _flatten(f'''
        <div class="tk-med-card">
          <div class="tk-med-head">
            <span class="tk-med-name">{esc(drug.get("matched_name"))}</span>
            <span class="tk-med-source notfound">{t("med_not_found_label")}</span>
          </div>
          <div class="tk-med-row">{t("med_not_found_detail")}</div>
        </div>''')

    source = drug.get("source")
    source_cls = "egypt" if source == "egypt" else "fda"
    source_label = t("med_source_egypt") if source == "egypt" else t("med_source_fda")
    name_en = drug.get("commercial_name_en") or drug.get("matched_name")
    name_ar = drug.get("commercial_name_ar")
    rows = []
    if drug.get("active_ingredients"):
        rows.append(f'<div class="tk-med-row"><b>{t("med_active_ingredient")}</b> {esc(drug["active_ingredients"])}</div>')
    if drug.get("manufacturer"):
        rows.append(f'<div class="tk-med-row"><b>{t("med_manufacturer")}</b> {esc(drug["manufacturer"])}</div>')
    if drug.get("drug_class"):
        rows.append(f'<div class="tk-med-row"><b>{t("med_class")}</b> {esc(drug["drug_class"])}</div>')
    if drug.get("price_egp"):
        rows.append(f'<div class="tk-med-row"><b>{t("med_price")}</b> {esc(drug["price_egp"])} {t("med_currency")}</div>')
    if drug.get("purpose"):
        rows.append(f'<div class="tk-med-row"><b>{t("med_purpose")}</b> {esc(drug["purpose"])}</div>')

    return _flatten(f'''
    <div class="tk-med-card">
      <div class="tk-med-head">
        <span class="tk-med-name">{esc(name_en)}{f" · {esc(name_ar)}" if name_ar else ""}</span>
        <span class="tk-med-source {source_cls}">{source_label}</span>
      </div>
      {"".join(rows)}
    </div>''')


def render_entry_html(entry: dict) -> str:
    if entry.get("image_b64"):
        user_html = f'<div class="tk-user-row"><img class="tk-user-image" src="data:{entry.get("image_mime", "image/jpeg")};base64,{entry["image_b64"]}" /></div>'
    else:
        user_html = f'<div class="tk-user-row"><div class="tk-user-bubble">{esc(entry.get("question", ""))}</div></div>'

    med_html = ""
    for drug in entry.get("drug_matches") or []:
        med_html += render_medicine_card(drug)

    risk_level = (entry.get("safety") or {}).get("risk_level")
    if risk_level == "refuse":
        card_html = render_emergency_card()
    elif risk_level == "insufficient_evidence":
        card_html = render_insufficient_card()
    else:
        card_html = render_answer_card(entry, risk_level)

    return user_html + med_html + card_html


def render_right_panel_prechat():
    """Before any message exists, the panel shows real, current state instead
    of an empty placeholder — loaded sources, search scope, backend readiness,
    and active patient context, each only if it actually has data."""
    if st.session_state.documents:
        st.markdown(f'<div class="tk-eyebrow" style="margin-top:0;">{t("loaded_knowledge_sources")}</div>', unsafe_allow_html=True)
        for doc in st.session_state.documents:
            icon = "🔒" if doc["document_id"].startswith("seed_") else "📄"
            st.caption(f"{icon} {short_doc_label(doc['filename'])}")

        st.markdown(f'<div class="tk-eyebrow">{t("search_scope")}</div>', unsafe_allow_html=True)
        doc_options = {doc["filename"]: doc["document_id"] for doc in st.session_state.documents}
        scoped_names = [name for name, did in doc_options.items() if did in st.session_state.document_scope]
        chosen = st.multiselect(
            "Limit search to", options=list(doc_options.keys()), default=scoped_names,
            placeholder=t("search_scope_placeholder"), label_visibility="collapsed", format_func=short_doc_label,
            key="scope_prechat",
        )
        st.session_state.document_scope = [doc_options[name] for name in chosen]
    else:
        st.markdown(f'<div class="tk-panel-empty">{t("no_documents_loaded")}</div>', unsafe_allow_html=True)

    st.markdown(f'<div class="tk-eyebrow">{t("ai_readiness")}</div>', unsafe_allow_html=True)
    if st.session_state.health_status is None:
        st.session_state.health_status = check_backend_health()
    dot_color = C["primary"] if st.session_state.health_status else C["danger"]
    label = t("backend_ready") if st.session_state.health_status else t("backend_unreachable")
    st.markdown(
        f'<span class="tk-readiness-dot" style="background:{dot_color};"></span>{label}',
        unsafe_allow_html=True
    )

    if has_patient_context():
        st.markdown(f'<div class="tk-eyebrow">{t("active_patient")}</div>', unsafe_allow_html=True)
        st.caption(patient_context_summary())


def render_right_panel_conversation():
    if not st.session_state.chat_history:
        render_right_panel_prechat()
        return

    entry = st.session_state.chat_history[-1]
    panel = entry.get("evidence_panel") or []
    sources = entry.get("sources") or []
    confidence = entry.get("confidence") or {}

    tab_evidence, tab_sources, tab_confidence = st.tabs([t("tab_evidence"), t("tab_sources"), t("tab_confidence")])

    with tab_evidence:
        if not panel:
            st.markdown(f'<div class="tk-panel-empty">{t("no_evidence")}</div>', unsafe_allow_html=True)
        else:
            for ev in panel:
                distance = ev.get("similarity_distance", 1)
                score = max(0.0, round(1 - distance, 2))
                section = ev.get("section_title")
                bits = [short_doc_label(ev.get("filename")), f"p.{ev.get('page_number', '?')}"]
                if section:
                    bits.append(f"§{esc(section)}")
                bits.append(f"score {score}")
                st.markdown(_flatten(f'''
                <div class="tk-evidence-item">
                  <blockquote>&ldquo;{esc(ev.get("text_snippet", ""))}&rdquo;</blockquote>
                  <div class="tk-evidence-source">{"  ·  ".join(bits)}</div>
                </div>'''), unsafe_allow_html=True)

    with tab_sources:
        if not sources:
            st.markdown(f'<div class="tk-panel-empty">{t("no_sources")}</div>', unsafe_allow_html=True)
        else:
            refs = sorted(set((s.get("filename"), s.get("page_number")) for s in sources))
            for filename, page in refs:
                st.markdown(
                    f'<div class="tk-evidence-item">📄 <b>{esc(short_doc_label(filename))}</b> — page {esc(page)}</div>',
                    unsafe_allow_html=True
                )

    with tab_confidence:
        retrieval_conf = confidence.get("retrieval_confidence", "n/a")
        grounding = confidence.get("grounding_verdict", "n/a")
        provider = entry.get("provider_used") or "n/a"
        st.markdown(_flatten(f'''
        <div class="tk-metric-row"><span class="tk-metric-label">{t("retrieval_confidence")}</span><span class="tk-metric-value">{esc(str(retrieval_conf).capitalize())}</span></div>
        <div class="tk-metric-row"><span class="tk-metric-label">{t("grounding_verdict")}</span><span class="tk-metric-value">{esc(str(grounding).replace("_", " ").capitalize())}</span></div>
        <div class="tk-metric-row"><span class="tk-metric-label">{t("ai_provider")}</span><span class="tk-metric-value">{esc(str(provider).capitalize())}</span></div>
        '''), unsafe_allow_html=True)


def render_right_panel_summary():
    doc_id = st.session_state.right_panel_doc_id
    data = st.session_state.summary_cache.get(doc_id)
    if st.button(t("back_to_conversation"), key="back_from_summary"):
        st.session_state.right_panel_mode = "conversation"
        st.rerun()
    if not data:
        st.markdown(f'<div class="tk-panel-empty">{t("no_summary_yet")}</div>', unsafe_allow_html=True)
        return
    st.markdown(data["final_summary"])
    with st.expander(t("section_by_section", n=len(data['chunk_summaries']))):
        for chunk in data["chunk_summaries"]:
            st.markdown(f"**{t('pages_label', range=chunk['page_range'])}**")
            st.caption(chunk["summary"])
            st.divider()


def render_right_panel_insights():
    doc_id = st.session_state.right_panel_doc_id
    data = st.session_state.insights_cache.get(doc_id)
    if st.button(t("back_to_conversation"), key="back_from_insights"):
        st.session_state.right_panel_mode = "conversation"
        st.rerun()
    if not data:
        st.markdown(f'<div class="tk-panel-empty">{t("no_insights_yet")}</div>', unsafe_allow_html=True)
        return

    entities = data.get("entities", {})
    tables = data.get("tables", [])

    tab_entities, tab_tables = st.tabs([t("tab_entities"), t("tab_tables")])
    with tab_entities:
        if entities.get("error"):
            st.caption(t("entity_parse_error"))
        else:
            for label_key, key in [("entity_people", "people"), ("entity_organizations", "organizations"),
                                    ("entity_dates", "dates"), ("entity_monetary_amounts", "monetary_amounts"),
                                    ("entity_percentages", "percentages")]:
                values = entities.get(key) or []
                if values:
                    st.markdown(f"**{t(label_key)}**")
                    st.caption(", ".join(values))
    with tab_tables:
        if not tables:
            st.markdown(f'<div class="tk-panel-empty">{t("no_tabular_data")}</div>', unsafe_allow_html=True)
        for tbl in tables:
            st.markdown(f"**{tbl.get('title') or t('table_fallback_title')}** (p.{tbl.get('page_number', '?')})")
            st.table([dict(zip(tbl.get("headers", []), row)) for row in tbl.get("rows", [])])


# ─── Backend calls ───
def handle_text_question(question_text: str, doc_ids: list) -> bool:
    enriched = build_enriched_question(question_text)
    with st.spinner(t("checking_guidelines")):
        try:
            payload = {"question": enriched, "document_ids": doc_ids, "user_type": st.session_state.user_type}
            response = requests.post(f"{API_BASE_URL}/query/ask", json=payload, timeout=180)
        except requests.RequestException as e:
            st.error(t("request_failed", error=e))
            return False

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
        st.session_state.right_panel_mode = "conversation"
        return True
    st.error(t("error_generic", error=response.text))
    return False


def handle_voice_question(audio_base64: str, doc_ids: list) -> bool:
    audio_bytes = base64.b64decode(audio_base64)
    with st.spinner(t("transcribing")):
        try:
            files = {"file": ("question.webm", audio_bytes, "audio/webm")}
            params = {
                "document_ids": ",".join(doc_ids),
                "speak_answer": True,
                "user_type": st.session_state.user_type
            }
            response = requests.post(f"{API_BASE_URL}/voice/ask", files=files, params=params, timeout=180)
        except requests.RequestException as e:
            st.error(t("request_failed", error=e))
            return False

    if response.status_code == 200:
        data = response.json()
        entry = {
            "question": f"🎤 {data.get('transcribed_question', '')}",
            "answer": data["answer"],
            "sources": data.get("sources", []),
            "confidence": data.get("confidence", {}),
            "provider_used": data.get("provider_used"),
            "safety": data.get("safety", {}),
            "evidence_panel": data.get("evidence_panel", [])
        }
        if data.get("audio_answer_path"):
            audio_filename = Path(data["audio_answer_path"]).name
            audio_response = requests.get(f"{API_BASE_URL}/voice/audio/{audio_filename}")
            if audio_response.status_code == 200:
                entry["audio_answer_bytes"] = audio_response.content
        st.session_state.chat_history.append(entry)
        st.session_state.right_panel_mode = "conversation"
        return True
    st.error(t("error_generic", error=response.text))
    return False


def handle_prescription_image(image_base64: str, mime_type: str) -> bool:
    image_bytes = base64.b64decode(image_base64)
    with st.status(t("reading_prescription"), expanded=True) as status:
        try:
            files = {"file": ("photo.jpg", image_bytes, mime_type)}
            params = {"user_type": st.session_state.user_type}
            response = requests.post(f"{API_BASE_URL}/prescription/read", files=files, params=params, timeout=280)
        except requests.RequestException as e:
            status.update(label=t("request_failed_label"), state="error")
            st.error(t("request_failed", error=e))
            return False

        if response.status_code != 200:
            status.update(label=t("failed_to_read_prescription"), state="error")
            st.error(t("error_generic", error=response.text))
            return False

        data = response.json()
        extraction = data.get("extraction", {})
        names = extraction.get("clearly_read_names", [])
        status.update(
            label=t("done_medications_identified", n=len(names)) if names else t("done_nothing_legible"),
            state="complete"
        )

    if not names:
        st.session_state.chat_history.append({
            "question": "📷 [صورة مرفوعة]",
            "image_b64": image_base64, "image_mime": mime_type,
            "answer": data.get("message", "معرفتش أقرا اسم دوا واضح من الصورة."),
            "sources": [], "confidence": {}, "provider_used": None,
            "safety": {"risk_level": "insufficient_evidence", "reasoning": "No medication name read from image."},
            "evidence_panel": []
        })
        st.session_state.right_panel_mode = "conversation"
        return True

    st.session_state.chat_history.append({
        "question": f"📷 الأدوية اللي اتعرفت: {', '.join(names)}",
        "image_b64": image_base64, "image_mime": mime_type,
        "answer": data.get("answer") or "",
        "drug_matches": data.get("drug_database_matches", []),
        "sources": data.get("sources", []),
        "confidence": data.get("confidence", {}),
        "provider_used": data.get("provider_used"),
        "safety": data.get("safety", {}),
        "evidence_panel": data.get("evidence_panel", [])
    })
    st.session_state.right_panel_mode = "conversation"
    return True


def handle_summarize(document_id: str) -> bool:
    with st.spinner(t("summarizing")):
        try:
            response = requests.post(f"{API_BASE_URL}/summary/generate", json={"document_id": document_id}, timeout=280)
        except requests.RequestException as e:
            st.error(t("request_failed", error=e))
            return False
    if response.status_code == 200:
        data = response.json()
        st.session_state.summary_cache[document_id] = {
            "final_summary": data["final_summary"],
            "chunk_summaries": data["chunk_summaries"],
        }
        st.session_state.right_panel_mode = "summary"
        st.session_state.right_panel_doc_id = document_id
        return True
    st.error(t("failed_colon", error=response.text))
    return False


def handle_insights(document_id: str) -> bool:
    with st.spinner(t("extracting_insights")):
        try:
            ent_resp = requests.post(f"{API_BASE_URL}/extract/entities", json={"document_id": document_id}, timeout=180)
            tbl_resp = requests.post(f"{API_BASE_URL}/extract/tables", json={"document_id": document_id}, timeout=180)
        except requests.RequestException as e:
            st.error(t("request_failed", error=e))
            return False
    if ent_resp.status_code != 200 or tbl_resp.status_code != 200:
        st.error(t("failed_colon", error=(ent_resp.text if ent_resp.status_code != 200 else tbl_resp.text)))
        return False
    entities = ent_resp.json().get("entities", {})
    tables = tbl_resp.json().get("tables", [])
    st.session_state.insights_cache[document_id] = {"entities": entities, "tables": tables}
    st.session_state.right_panel_mode = "insights"
    st.session_state.right_panel_doc_id = document_id
    return True


def render_patient_editor():
    st.session_state.patient_age = st.number_input(
        t("age_label"), min_value=0, max_value=120,
        value=st.session_state.patient_age or 0, step=1, key="patient_age_input",
    ) or None

    st.session_state.conditions = st.multiselect(
        t("conditions_label"),
        options=sorted(set(PRESET_CONDITIONS) | set(st.session_state.conditions)),
        default=st.session_state.conditions,
        accept_new_options=True,
        placeholder=t("conditions_placeholder"),
        format_func=condition_label,
        key="conditions_input",
    )

    st.caption(t("medications_label"))
    for i, med in enumerate(st.session_state.medications):
        c1, c2 = st.columns([5, 1])
        with c1:
            st.markdown(f'<div class="tk-chip-row">{esc(med)}</div>', unsafe_allow_html=True)
        with c2:
            if st.button("✕", key=f"rm_med_{i}"):
                st.session_state.medications.pop(i)
                st.rerun()

    with st.form("add_med_form", clear_on_submit=True):
        new_med = st.text_input(t("add_medication_label"), placeholder=t("add_medication_placeholder"), label_visibility="collapsed")
        if st.form_submit_button(t("add_btn"), use_container_width=True):
            if new_med.strip():
                st.session_state.medications.append(new_med.strip())
                st.rerun()

    if st.button(t("done_btn"), key="close_patient_editor"):
        st.session_state.show_patient_editor = False
        st.rerun()


def render_scan_uploader():
    scan_file = st.file_uploader(t("prescription_photo_label"), type=["png", "jpg", "jpeg"], label_visibility="collapsed", key="scan_uploader")
    if scan_file is not None:
        b64_img = base64.b64encode(scan_file.getvalue()).decode()
        if handle_prescription_image(b64_img, scan_file.type or "image/jpeg"):
            st.session_state.show_scan_uploader = False
            st.session_state.active_view = "chats"
            st.rerun()


# ─── Home view ───
def render_home_view():
    st.markdown(
        f'<div class="tk-hero-eyebrow">{t("hero_eyebrow")}</div>'
        f'<div class="tk-hero-title">{t("hero_title")}</div>'
        f'<div class="tk-hero-tagline">{t("hero_tagline")}</div>'
        f'<div class="tk-hero-sub">{t("hero_sub")}</div>',
        unsafe_allow_html=True
    )
    st.markdown('<div style="height:20px"></div>', unsafe_allow_html=True)

    st.markdown(f'<div class="tk-eyebrow">{t("quick_actions")}</div>', unsafe_allow_html=True)
    qa1, qa2, qa3 = st.columns(3)
    with qa1:
        with st.container(border=True):
            st.markdown('<div class="tk-qa-icon">💬</div>', unsafe_allow_html=True)
            if st.button(t("qa_ask_title"), key="qa_ask", use_container_width=True):
                st.session_state.active_view = "chats"
                st.rerun()
            st.markdown(f'<div class="tk-qa-desc">{t("qa_ask_desc")}</div>', unsafe_allow_html=True)
    with qa2:
        with st.container(border=True):
            st.markdown('<div class="tk-qa-icon">📷</div>', unsafe_allow_html=True)
            if st.button(t("qa_scan_title"), key="qa_scan", use_container_width=True):
                st.session_state.active_view = "chats"
                st.session_state.show_scan_uploader = True
                st.rerun()
            st.markdown(f'<div class="tk-qa-desc">{t("qa_scan_desc")}</div>', unsafe_allow_html=True)
    with qa3:
        with st.container(border=True):
            st.markdown('<div class="tk-qa-icon">📄</div>', unsafe_allow_html=True)
            if st.button(t("qa_upload_title"), key="qa_upload", use_container_width=True):
                st.session_state.active_view = "library"
                st.rerun()
            st.markdown(f'<div class="tk-qa-desc">{t("qa_upload_desc")}</div>', unsafe_allow_html=True)
    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)

    if st.session_state.chat_history:
        last = st.session_state.chat_history[-1]
        with st.container(border=True):
            st.markdown(f'<div class="tk-dash-card-title">{t("recent_conversation")}</div>', unsafe_allow_html=True)
            st.caption(f"{t('you_prefix')}: {last.get('question', '')[:140]}")
            answer_preview = (last.get("answer") or "")[:180]
            st.write(answer_preview + ("…" if len(last.get("answer") or "") > 180 else ""))
            if st.button(t("continue_in_chats"), key="continue_chat"):
                st.session_state.active_view = "chats"
                st.rerun()

    if not st.session_state.documents:
        refresh_documents()
    if st.session_state.documents:
        with st.container(border=True):
            doc_count = len(st.session_state.documents)
            st.markdown(f'<div class="tk-dash-card-title">{t("knowledge_base_title")}</div>', unsafe_allow_html=True)
            st.caption(t("guidelines_loaded", n=doc_count, plural=('s' if doc_count != 1 else '')))
            for doc in st.session_state.documents[:5]:
                icon = "🔒" if doc["document_id"].startswith("seed_") else "📄"
                st.caption(f"{icon} {short_doc_label(doc['filename'])}")
            if st.button(t("open_library"), key="open_library"):
                st.session_state.active_view = "library"
                st.rerun()

    with st.container(border=True):
        st.markdown(f'<div class="tk-dash-card-title">{t("current_patient")}</div>', unsafe_allow_html=True)
        if has_patient_context():
            st.markdown(f'<span class="tk-patient-pill">{esc(patient_context_summary())}</span>', unsafe_allow_html=True)
            st.write("")
            if st.button(t("edit_btn"), key="edit_patient_home"):
                st.session_state.show_patient_editor = not st.session_state.show_patient_editor
        else:
            if st.button(t("add_patient_context"), key="add_patient_home"):
                st.session_state.show_patient_editor = not st.session_state.show_patient_editor
        if st.session_state.show_patient_editor:
            render_patient_editor()


# ─── Library view ───
def render_library_view():
    st.markdown(f'<p class="tk-topbar-title" style="margin-bottom:16px;">{t("library_title")}</p>', unsafe_allow_html=True)
    if not st.session_state.documents:
        refresh_documents()

    uploaded_file = st.file_uploader(t("library_upload_label"), type=["pdf", "docx", "pptx"], key="doc_uploader")
    if uploaded_file is not None:
        if st.button(t("process_document"), type="primary"):
            with st.status(t("processing_document"), expanded=True) as status:
                status.update(label=t("parsing"))
                files = {"file": (uploaded_file.name, uploaded_file.getvalue())}
                response = requests.post(f"{API_BASE_URL}/documents/upload", files=files)
                if response.status_code == 200:
                    status.update(label=t("indexed_chunks", n=response.json()['num_chunks']), state="complete")
                    refresh_documents()
                else:
                    status.update(label=t("failed_generic"), state="error")
                    st.error(t("failed_colon", error=response.text))

    st.write("")
    if not st.session_state.documents:
        st.markdown(f'<div class="tk-panel-empty">{t("no_documents_yet")}</div>', unsafe_allow_html=True)
        return

    for doc in st.session_state.documents:
        doc_id = doc["document_id"]
        is_seed = doc_id.startswith("seed_")
        icon = "🔒" if is_seed else "📄"
        with st.container(border=True):
            st.markdown(f'<div class="tk-doc-name">{icon} {esc(short_doc_label(doc["filename"]))}</div>', unsafe_allow_html=True)
            b1, b2, b3, _ = st.columns([1, 1, 1, 4])
            with b1:
                if st.button(t("summarize_btn"), key=f"sum_{doc_id}"):
                    if handle_summarize(doc_id):
                        st.session_state.active_view = "chats"
                        st.rerun()
            with b2:
                if st.button(t("insights_btn"), key=f"ins_{doc_id}"):
                    if handle_insights(doc_id):
                        st.session_state.active_view = "chats"
                        st.rerun()
            with b3:
                if not is_seed:
                    if st.button(t("remove_btn"), key=f"del_{doc_id}"):
                        requests.delete(f"{API_BASE_URL}/documents/{doc_id}")
                        refresh_documents()
                        st.rerun()


# ─── Settings view ───
def render_settings_view():
    st.markdown(f'<p class="tk-topbar-title" style="margin-bottom:16px;">{t("settings_title")}</p>', unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown(f'<div class="tk-dash-card-title">{t("patient_profile_title")}</div>', unsafe_allow_html=True)
        st.caption(t("patient_profile_caption"))
        render_patient_editor()

    with st.container(border=True):
        st.markdown(f'<div class="tk-dash-card-title">{t("diagnostics_title")}</div>', unsafe_allow_html=True)
        if st.button(t("check_backend"), key="refresh_health"):
            st.session_state.health_status = check_backend_health()
        if st.session_state.health_status is not None:
            dot_color = C["primary"] if st.session_state.health_status else C["danger"]
            label = t("backend_ready") if st.session_state.health_status else t("backend_unreachable")
            st.markdown(f'<span class="tk-readiness-dot" style="background:{dot_color};"></span>{label}', unsafe_allow_html=True)
        if st.session_state.chat_history:
            last_provider = st.session_state.chat_history[-1].get("provider_used")
            if last_provider:
                st.caption(t("last_provider_used", provider=last_provider))


# ─── Chat view ───
def render_chat_view():
    main_col, right_col = st.columns([2.6, 1], gap="medium")

    with main_col:
        has_conversation = len(st.session_state.chat_history) > 0

        if has_conversation:
            _, new_chat_col = st.columns([5, 1])
            with new_chat_col:
                if st.button(t("new_chat"), key="new_chat_btn"):
                    st.session_state.chat_history = []
                    st.session_state.right_panel_mode = "conversation"
                    st.rerun()

        if st.session_state.show_scan_uploader:
            with st.container(border=True):
                st.caption(t("scan_prescription_caption"))
                render_scan_uploader()

        if not has_conversation:
            st.markdown(
                f'<div style="text-align:center; padding-top:6vh;">'
                f'<p style="font-size:1.9rem; font-weight:800; color:{C["ink"]}; margin-bottom:6px;">Tiryak</p>'
                f'<p style="color:{C["ink_soft"]}; max-width:520px; margin:0 auto 24px;">{t("chats_empty_sub")}</p>'
                f'</div>',
                unsafe_allow_html=True
            )
            suggested_prompts = SUGGESTED_PROMPTS_AR if is_rtl() else SUGGESTED_PROMPTS_EN
            cols = st.columns(len(suggested_prompts))
            for i, prompt in enumerate(suggested_prompts):
                with cols[i]:
                    if st.button(prompt, key=f"suggest_{i}", use_container_width=True):
                        if handle_text_question(prompt, active_scope_ids()):
                            st.rerun()
        else:
            with st.container(height=600, border=False):
                for entry in st.session_state.chat_history:
                    st.markdown(render_entry_html(entry), unsafe_allow_html=True)
                    if entry.get("audio_answer_bytes"):
                        st.audio(entry["audio_answer_bytes"], format="audio/mp3")
                st.markdown('<div id="tk-chat-end"></div>', unsafe_allow_html=True)
            components.html(
                """<script>
                var el = window.parent.document.getElementById('tk-chat-end');
                if (el) { el.scrollIntoView({behavior: 'instant', block: 'end'}); }
                </script>""",
                height=0,
            )

    with right_col:
        st.markdown(f'<div class="tk-panel-header">{t("details_header")}</div>', unsafe_allow_html=True)
        mode = st.session_state.right_panel_mode
        if mode == "summary":
            render_right_panel_summary()
        elif mode == "insights":
            render_right_panel_insights()
        else:
            render_right_panel_conversation()


# ─── Sidebar: minimal nav + language switcher ───
with st.sidebar:
    logo_col, name_col = st.columns([2, 3])
    with logo_col:
        if LOGO_PATH:
            st.image(LOGO_PATH, width=76)
    with name_col:
        st.markdown(
            f'<div class="tk-brand-name">Tiryak</div><div class="tk-brand-tag">{t("brand_tag")}</div>',
            unsafe_allow_html=True
        )
    st.markdown(
        f'<div style="border-bottom:1px solid {C["border"]}; margin:18px 0 16px;"></div>',
        unsafe_allow_html=True
    )

    NAV_ITEMS = [
        ("home", t("nav_home"), ":material/home:"),
        ("chats", t("nav_chats"), ":material/chat_bubble:"),
        ("library", t("nav_library"), ":material/menu_book:"),
        ("settings", t("nav_settings"), ":material/settings:"),
    ]
    for view_key, label, icon in NAV_ITEMS:
        if st.button(label, key=f"nav_{view_key}", icon=icon, use_container_width=True):
            st.session_state.active_view = view_key
            st.rerun()

    st.session_state.language = st.radio(
        t("language_label"), options=["en", "ar"],
        format_func=lambda code: TRANSLATIONS[code]["language_name"],
        label_visibility="collapsed", horizontal=True, key="language_toggle",
    )

    st.markdown(
        f'<div class="tk-sidebar-footer">{t("sidebar_footer")}</div>',
        unsafe_allow_html=True
    )

# ─── Top bar: current view + always-visible audience toggle, one unified header ───
VIEW_TITLES = {"home": t("nav_home"), "chats": t("nav_chats"), "library": t("nav_library"), "settings": t("nav_settings")}
top_left, top_right = st.columns([3, 2], vertical_alignment="center")
with top_left:
    st.markdown(f'<span class="tk-topbar-title">{VIEW_TITLES[st.session_state.active_view]}</span>', unsafe_allow_html=True)
with top_right:
    st.session_state.user_type = st.radio(
        "Audience", options=["pharmacist", "patient"],
        format_func=lambda x: t("audience_pharmacist") if x == "pharmacist" else t("audience_patient"),
        label_visibility="collapsed", horizontal=True, key="audience_toggle",
    )
st.markdown(f'<div style="border-bottom:1px solid {C["border"]}; margin:2px 0 24px;"></div>', unsafe_allow_html=True)

# ─── Route to active view ───
if st.session_state.active_view == "home":
    render_home_view()
elif st.session_state.active_view == "library":
    render_library_view()
elif st.session_state.active_view == "settings":
    render_settings_view()
else:
    render_chat_view()

# ─── Input bar — only where conversation happens ───
if st.session_state.active_view in ("home", "chats"):
    result = voice_chat_input(
        key="unified_input",
        placeholder=t("chat_placeholder"),
    )

    if result is not None and isinstance(result, dict):
        input_id = result.get("id")
        if st.session_state.last_processed_input_id != input_id:
            st.session_state.last_processed_input_id = input_id

            if result.get("type") == "text":
                if handle_text_question(result["value"], active_scope_ids()):
                    st.session_state.active_view = "chats"
                    st.rerun()
            elif result.get("type") == "audio":
                if handle_voice_question(result["value"], active_scope_ids()):
                    st.session_state.active_view = "chats"
                    st.rerun()
            elif result.get("type") == "image":
                if handle_prescription_image(result["value"], result.get("mime_type", "image/jpeg")):
                    st.session_state.active_view = "chats"
                    st.rerun()
