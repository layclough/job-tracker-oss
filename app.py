import streamlit as st
import sqlite3
import pandas as pd
from pathlib import Path
from datetime import datetime

# Import views with dynamic reload
import importlib
import src.llm_config
import src.extractor
import src.generator
import views.tracker
import views.tailor
import views.master
import views.dashboard
importlib.reload(src.llm_config)
importlib.reload(src.extractor)
importlib.reload(src.generator)
importlib.reload(views.tracker)
importlib.reload(views.tailor)
importlib.reload(views.master)
importlib.reload(views.dashboard)
from src.llm_config import (
    PROVIDERS,
    load_llm_settings,
    get_provider_saved_settings,
    save_llm_settings,
    test_llm_connection,
)
from views.tracker import tracker_view
from views.tailor import tailor_view
from views.master import master_view
from views.dashboard import dashboard_view

# --- PATHS CONFIGURATION ---
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "00_Data" / "jobs.db"
TRACKER_MD_PATH = BASE_DIR / "00_Data" / "Job_Tracker.md"
MASTER_RESUME_PATH = BASE_DIR / "00_Data" / "Master_Resume.md"
INPUT_DIR = BASE_DIR / "01_Input"
OUTPUT_DIR = BASE_DIR / "02_Output"

for folder in [DB_PATH.parent, INPUT_DIR, OUTPUT_DIR]:
    folder.mkdir(parents=True, exist_ok=True)

# --- DATABASE SCHEMA INITIALIZATION ---
def init_database(db_path: Path):
    """Initializes SQLite tables, triggers, and default reference statuses if not present."""
    with sqlite3.connect(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS application_statuses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status_name TEXT UNIQUE NOT NULL,
                display_order INTEGER NOT NULL,
                is_default BOOLEAN DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company TEXT,
                title TEXT,
                status TEXT,
                date_submitted TEXT,
                follow_up_date TEXT,
                match_score REAL DEFAULT 0.0,
                salary TEXT DEFAULT 'N/A',
                experience TEXT DEFAULT 'N/A',
                skills TEXT DEFAULT '[]',
                missing_skills TEXT DEFAULT '[]',
                jd_file TEXT,
                resume_file TEXT,
                notes TEXT,
                resume_docx TEXT,
                status_id INTEGER REFERENCES application_statuses(id)
            );

            CREATE TABLE IF NOT EXISTS application_status_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                application_id INTEGER REFERENCES applications(id) ON DELETE CASCADE,
                old_status_id INTEGER REFERENCES application_statuses(id),
                new_status_id INTEGER REFERENCES application_statuses(id),
                changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notes TEXT
            );

            CREATE TRIGGER IF NOT EXISTS log_status_change
            AFTER UPDATE OF status_id ON applications
            WHEN old.status_id IS NOT new.status_id
            BEGIN
                INSERT INTO application_status_history (application_id, old_status_id, new_status_id, changed_at)
                VALUES (new.id, old.status_id, new.status_id, CURRENT_TIMESTAMP);
            END;
        """)

        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM application_statuses")
        if cursor.fetchone()[0] == 0:
            default_statuses = [
                ("Analyzed", 1, 1),
                ("Tailored", 2, 0),
                ("Applied", 3, 0),
                ("Interviewing", 4, 0),
                ("Rejected", 5, 0),
                ("Ghosted", 6, 0),
                ("Withdrawn", 7, 0),
                ("Offered", 8, 0),
                ("Ignored", 9, 0),
            ]
            cursor.executemany(
                "INSERT INTO application_statuses (status_name, display_order, is_default) VALUES (?, ?, ?)",
                default_statuses,
            )
            conn.commit()

init_database(DB_PATH)

st.set_page_config(
    page_title="Job Hunt Tracker & Resume Tailor",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Tailwind-inspired Light Theme CSS matching App.tsx
def load_global_css():
    css_path = Path(__file__).parent / "assets" / "global_styles.css"
    with open(css_path, "r") as f:
        css = f.read()
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

load_global_css()  # reload tag: v33

# --- AUTO-EXPORTER: DB -> Job_Tracker.md ---
def export_db_to_markdown():
    if not DB_PATH.exists():
        return
        
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql_query(
            "SELECT date_submitted, company, title, status, jd_file, resume_file, follow_up_date, notes FROM applications ORDER BY id DESC", 
            conn
        )
    
    if df.empty:
        return

    md_lines = ["# 💼 Application Master Record\n"]
    md_lines.append("| Date | Company | Role | Status | Source JD | Submitted Resume | Follow-Up Date | Notes |")
    md_lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    
    for _, row in df.iterrows():
        date_sub = row['date_submitted'] or '—'
        company = row['company'] or 'N/A'
        title = row['title'] or 'N/A'
        status = row['status'] or 'Analyzed'
        
        jd_link = f"[Link](../{row['jd_file']})" if row['jd_file'] and row['jd_file'] != 'N/A' else '—'
        res_link = f"[Link](../{row['resume_file']})" if row['resume_file'] and row['resume_file'] != 'N/A' else '—'
        
        follow = row['follow_up_date'] or '—'
        notes = row['notes'] or ''
        
        md_lines.append(f"| {date_sub} | {company} | {title} | {status} | {jd_link} | {res_link} | {follow} | {notes} |")
        
    TRACKER_MD_PATH.write_text("\n".join(md_lines), encoding="utf-8")

@st.dialog("AI Model & Security Settings", width="small")
def open_settings_dialog():
    active_cfg = load_llm_settings()
    provider_keys = list(PROVIDERS.keys())
    provider_labels = [PROVIDERS[k]["label"] for k in provider_keys]
    current_idx = provider_keys.index(active_cfg["provider"]) if active_cfg["provider"] in provider_keys else 0

    selected_label = st.selectbox(
        "AI Provider",
        options=provider_labels,
        index=current_idx,
        key="dlg_llm_provider_select",
    )
    selected_provider = provider_keys[provider_labels.index(selected_label)]
    preset = PROVIDERS[selected_provider]
    saved_prov = get_provider_saved_settings(selected_provider)

    suggestions = preset.get("model_suggestions", [])
    model_help = f"Examples: {', '.join(suggestions)}" if suggestions else "Enter the exact model identifier."
    model_val = st.text_input(
        "Model Name",
        value=saved_prov["model"],
        help=model_help,
        key=f"dlg_llm_model_v2_{selected_provider}",
    )

    caption_slot = st.empty()
    if suggestions:
        caption_slot.caption(f"Suggested models: `{ '`, `'.join(suggestions) }`")
    else:
        caption_slot.empty()

    base_url_val = st.text_input(
        "API Base URL",
        value=saved_prov["base_url"],
        key=f"dlg_llm_url_{selected_provider}",
    )

    # Fixed st.empty() slots ensure the dialog element count never shrinks or shifts
    # across provider changes, preventing duplicate button rows in Streamlit fragments.
    key_badge_slot = st.empty()
    key_input_slot = st.empty()
    key_clear_slot = st.empty()
    privacy_slot = st.empty()

    api_key_input = ""
    clear_saved_key = False
    if preset["requires_key"]:
        if saved_prov["has_key"]:
            key_badge_slot.markdown(
                f"""
                <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 6px; padding: 8px 12px; margin-bottom: 8px; font-size: 12px; color: #166534; display: flex; justify-content: space-between; align-items: center;">
                    <span>🔒 Saved in <code>.env</code>: <code>{saved_prov['masked_key']}</code></span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            api_key_input = key_input_slot.text_input(
                "Update API Key (Optional)",
                value="",
                type="password",
                placeholder="Leave blank to keep existing key, or paste a new key...",
                key=f"dlg_llm_key_{selected_provider}",
            )
            clear_saved_key = key_clear_slot.checkbox(
                "Remove saved API key from .env",
                key=f"dlg_clear_key_{selected_provider}",
            )
        else:
            key_badge_slot.empty()
            api_key_input = key_input_slot.text_input(
                "API Key",
                value="",
                type="password",
                placeholder=f"Paste your {preset['short_label']} API key...",
                key=f"dlg_llm_key_{selected_provider}",
            )
            key_clear_slot.empty()

        privacy_slot.markdown(
            """
            <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px 12px; margin-top: 6px; margin-bottom: 8px; font-size: 11px; color: #475569; line-height: 1.45;">
                <b>Security & Privacy:</b> Keys are stored locally in <code>.env</code> (git-ignored, <code>0600</code> permissions) and never exposed in the UI. External APIs receive your Master Resume and JD text over HTTPS.
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        key_badge_slot.empty()
        key_input_slot.empty()
        key_clear_slot.empty()
        privacy_slot.markdown(
            """
            <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 6px; padding: 8px 12px; margin-top: 6px; margin-bottom: 8px; font-size: 11px; color: #166534; line-height: 1.45;">
                <b>100% Local Privacy:</b> Your Master Resume and Job Descriptions never leave your machine.
            </div>
            """,
            unsafe_allow_html=True,
        )

    test_col, save_col = st.columns(2)
    with test_col:
        btn_test = st.button(
            "Test Connection",
            width="stretch",
            key="btn_test_llm_conn",
        )
    with save_col:
        btn_save = st.button(
            "Save Settings",
            type="primary",
            width="stretch",
            key="btn_save_llm_settings",
        )

    feedback_slot = st.empty()

    if btn_test:
        with feedback_slot.container():
            with st.spinner("Testing connection..."):
                ok, msg = test_llm_connection(
                    selected_provider,
                    model_val,
                    base_url_val,
                    api_key_override=api_key_input,
                )
            if ok:
                st.success(msg)
            else:
                st.error(msg)

    if btn_save:
        if preset["requires_key"] and not saved_prov["has_key"] and not api_key_input.strip() and not clear_saved_key:
            feedback_slot.error(f"Please enter an API key for {preset['label']}.")
        else:
            save_llm_settings(
                provider_id=selected_provider,
                model=model_val,
                base_url=base_url_val,
                new_api_key=api_key_input,
                clear_key=clear_saved_key,
            )
            st.toast(f"Saved AI model settings ({preset['short_label']})")
            st.rerun()


# --- SIDEBAR NAVIGATION ---
with st.sidebar:
    st.markdown("""
        <div class="sidebar-brand-wrapper">
            <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#0f172a" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect width="20" height="14" x="2" y="7" rx="2" ry="2"/>
                <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>
            </svg>
            <h1 class="sidebar-brand-title">JobHunt.AI</h1>
        </div>
    """, unsafe_allow_html=True)

    tab_choice = st.radio(
        "Navigation",
        [
            "Master Resume",
            "Add Job & Tailor",
            "Application Tracker",
            "Dashboard"
        ],
        index=1,
        key="main_nav_radio",
        label_visibility="collapsed"
    )

    active_llm = load_llm_settings()

    st.markdown(f"""
    <div class="sidebar-footer-container" id="sidebar-footer">
        <div class="sidebar-db-status">
            <div class="sidebar-db-header">
                <div class="sidebar-db-dot"></div>
                <span class="sidebar-db-title">Local DB Connected</span>
            </div>
            <p class="sidebar-db-text">Provider: <span class="sidebar-db-time">{active_llm["short_label"]}</span></p>
            <p class="sidebar-db-text">Model: <code class="sidebar-db-code">{active_llm["model"]}</code></p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    open_settings_clicked = st.button("Settings", type="primary", width="stretch", key="btn_open_settings")

if open_settings_clicked:
    open_settings_dialog()

# --- ROUTER ---
# Dedicated st.empty() slots per view ensure Streamlit 1.59 completely unmounts
# the previous tab's header and body DOM nodes when switching navigation tabs.
slot_master = st.empty()
slot_tailor = st.empty()
slot_tracker = st.empty()
slot_dashboard = st.empty()

if "Application Tracker" in tab_choice:
    slot_master.empty()
    slot_tailor.empty()
    slot_dashboard.empty()
    with slot_tracker.container(key="page_slot_tracker"):
        tracker_view(
            db_path=DB_PATH,
            export_db_to_markdown=export_db_to_markdown
        )
elif "Dashboard" in tab_choice:
    slot_master.empty()
    slot_tailor.empty()
    slot_tracker.empty()
    with slot_dashboard.container(key="page_slot_dashboard"):
        dashboard_view(
            db_path=DB_PATH
        )
elif "Add Job & Tailor" in tab_choice:
    slot_master.empty()
    slot_tracker.empty()
    slot_dashboard.empty()
    with slot_tailor.container(key="page_slot_tailor"):
        tailor_view(
            db_path=DB_PATH,
            master_resume_path=MASTER_RESUME_PATH,
            input_dir=INPUT_DIR,
            output_dir=OUTPUT_DIR,
            export_db_to_markdown=export_db_to_markdown
        )
elif "Master Resume" in tab_choice:
    slot_tailor.empty()
    slot_tracker.empty()
    slot_dashboard.empty()
    with slot_master.container(key="page_slot_master"):
        master_view(
            master_resume_path=MASTER_RESUME_PATH
        )

# Force reload tag: v24