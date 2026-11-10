import streamlit as st
import sqlite3
import json
import re
from pathlib import Path
from datetime import datetime
import trafilatura

from src.extractor import extract_jd_details, calculate_gap, get_job_description_content
from src.generator import generate_tailored_resume, convert_md_to_docx, resolve_master_resume_path

def render_progress_card(placeholder, header_title: str, percent: int, steps: list[tuple[str, str]]):
    """Renders a progress bar and checklist card matching the page's exact slate/emerald card styling."""
    rows_html = []
    for text, state in steps:
        if state == "done":
            rows_html.append(
                f'<div style="display: flex; align-items: center; gap: 8px; line-height: 1.5;">'
                f'<span style="color: #10b981; font-weight: 800; width: 14px; text-align: center; display: inline-block;">✓</span>'
                f'<span style="color: #0f172a; font-weight: 600;">{text}</span>'
                f'</div>'
            )
        elif state == "active":
            rows_html.append(
                f'<div style="display: flex; align-items: center; gap: 8px; line-height: 1.5;">'
                f'<span style="color: #334155; font-weight: 800; width: 14px; text-align: center; display: inline-block;">•</span>'
                f'<span style="color: #0f172a; font-weight: 600;">{text}</span>'
                f'</div>'
            )
        else:
            rows_html.append(
                f'<div style="display: flex; align-items: center; gap: 8px; line-height: 1.5;">'
                f'<span style="color: #cbd5e1; font-weight: 700; width: 14px; text-align: center; display: inline-block;">·</span>'
                f'<span style="color: #94a3b8; font-weight: 400;">{text}</span>'
                f'</div>'
            )

    checklist_html = "".join(rows_html)
    dot_color = "#10b981" if percent >= 100 else "#334155"

    placeholder.markdown(f"""
    <div style="background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; margin-top: 12px; margin-bottom: 16px;">
        <div style="background-color: #fcfcfc; border-bottom: 1px solid #e2e8f0; padding: 14px 20px; display: flex; justify-content: space-between; align-items: center;">
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="width: 8px; height: 8px; border-radius: 50%; background-color: {dot_color}; display: inline-block;"></span>
                <span style="font-weight: 700; font-size: 13px; color: #0f172a;">{header_title}</span>
            </div>
            <span style="font-weight: 700; font-size: 12px; color: #334155; background-color: #f1f5f9; border: 1px solid #cbd5e1; padding: 2px 8px; border-radius: 4px;">{percent}%</span>
        </div>
        <div style="height: 5px; background-color: #e2e8f0; width: 100%;">
            <div style="width: {percent}%; height: 100%; background-color: #334155; transition: width 0.25s ease;"></div>
        </div>
        <div style="background-color: #f8fafc; padding: 14px 20px; display: flex; flex-direction: column; gap: 6px; font-size: 12px; color: #475569;">
            {checklist_html}
        </div>
    </div>
    """, unsafe_allow_html=True)


def generate_file_slug(company: str, title: str) -> str:
    today_str = datetime.now().strftime("%Y_%m_%d")
    clean_company = re.sub(r'[^\w\s]', '', company).strip().replace(" ", "_")
    clean_title = re.sub(r'[^\w\s]', '', title).strip().replace(" ", "_")
    return f"{today_str}_{clean_company}_{clean_title}"

def generate_tailored_filenames(company: str, title: str, candidate_name: str = "") -> tuple[str, str]:
    """Generates sanitized filenames:
       MD: YYYY_MM_DD_Company_Role.md
       DOCX: Prefix_Role_Company_Year.docx (where Prefix is derived from candidate name or 'Resume')
       Replaces Senior with Sr, Product Manager with PM.
    """
    now = datetime.now()
    today_str = now.strftime("%Y_%m_%d")
    year_str = now.strftime("%Y")

    # Replace "Senior" with "Sr", "Product Manager" with "PM" (case-insensitive)
    t = re.sub(r'\bSenior\b', 'Sr', title, flags=re.IGNORECASE)
    t = re.sub(r'\bProduct\s+Manager\b', 'PM', t, flags=re.IGNORECASE)

    # Sanitize alphanumeric strings
    c_clean = re.sub(r'[^\w\s]', '', company).strip()
    c_clean = re.sub(r'\s+', '_', c_clean)
    c_clean = re.sub(r'_+', '_', c_clean).strip('_') or "Company"

    t_clean = re.sub(r'[^\w\s]', '', t).strip()
    t_clean = re.sub(r'\s+', '_', t_clean)
    t_clean = re.sub(r'_+', '_', t_clean).strip('_') or "Role"

    # Derive prefix dynamically from candidate name (e.g. John Doe -> JohnD, Jane Smith -> JaneS)
    prefix = "Resume"
    if not candidate_name and "master_profile" in st.session_state:
        candidate_name = st.session_state["master_profile"].get("header", {}).get("name", "").strip()
    if candidate_name:
        parts = candidate_name.split()
        if len(parts) >= 2:
            prefix = f"{parts[0]}{parts[-1][0].upper()}"
        elif parts:
            prefix = parts[0]

    md_filename = f"{today_str}_{c_clean}_{t_clean}.md"
    docx_filename = f"{prefix}_{t_clean}_{c_clean}_{year_str}.docx"
    return md_filename, docx_filename


def generate_tailored_filename(company: str, title: str, extension: str = "md") -> str:
    """Generates sanitized filename format for compatibility."""
    md_f, docx_f = generate_tailored_filenames(company, title)
    return docx_f if extension.lstrip('.').lower() == 'docx' else md_f


def get_recently_analyzed_jobs(db_path: Path, limit: int = 3) -> list[dict]:
    """Retrieves up to `limit` pending analyzed applications that have not yet had a tailored resume generated."""
    if not db_path.exists():
        return []
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, company, title, status, status_id, date_submitted,
                       match_score, salary, experience, skills, missing_skills,
                       jd_file, resume_file, notes
                FROM applications
                WHERE (status = 'Analyzed' OR status_id = 1)
                  AND status NOT IN ('Rejected', 'Ghosted', 'Withdrawn', 'Applied', 'Interviewing', 'Offered', 'Ignored')
                  AND (resume_file IS NULL OR resume_file = '' OR resume_file = 'N/A')
                ORDER BY id DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            jobs = []
            dismissed = st.session_state.get('dismissed_job_ids', set())
            for r in rows:
                if r['id'] in dismissed:
                    continue
                skills_raw = r['skills'] or '[]'
                try:
                    skills_list = json.loads(skills_raw) if isinstance(skills_raw, str) else skills_raw
                    if not isinstance(skills_list, list):
                        skills_list = []
                except Exception:
                    skills_list = [s.strip() for s in skills_raw.split(',') if s.strip()]

                missing_raw = r['missing_skills'] or '[]'
                missing_core = []
                missing_pref = []
                partial_core = []
                partial_pref = []
                gap_results = None
                try:
                    missing_data = json.loads(missing_raw) if isinstance(missing_raw, str) else missing_raw
                    if isinstance(missing_data, dict):
                        gap_results = missing_data.get('gap_results')
                        missing_core = missing_data.get('core', [])
                        missing_pref = missing_data.get('preferred', [])
                        partial_core = missing_data.get('partial_core', [])
                        partial_pref = missing_data.get('partial_pref', [])
                        missing_list = missing_data.get('all', missing_core + missing_pref)
                    elif isinstance(missing_data, list):
                        missing_list = missing_data
                    else:
                        missing_list = []
                except Exception:
                    missing_list = []

                jobs.append({
                    'id': r['id'],
                    'company': r['company'] or 'Unknown Company',
                    'title': r['title'] or 'Role',
                    'status': r['status'],
                    'status_id': r['status_id'],
                    'date_submitted': r['date_submitted'],
                    'match_score': float(r['match_score']) if r['match_score'] is not None else 0.0,
                    'salary': r['salary'] or 'N/A',
                    'experience': r['experience'] or 'N/A',
                    'skills': skills_list,
                    'missing_skills': missing_list,
                    'missing_core': missing_core,
                    'missing_preferred': missing_pref,
                    'partial_core': partial_core,
                    'partial_preferred': partial_pref,
                    'gap_results': gap_results,
                    'jd_file': r['jd_file'] or '',
                    'resume_file': r['resume_file'],
                    'notes': r['notes'] or ''
                })
            return jobs
    except Exception:
        return []

def normalize_partial_view_item(p) -> dict:
    """Normalizes a partial credit item into a dict with skill and reason."""
    if isinstance(p, dict):
        return {"skill": str(p.get("skill", "")).strip(), "reason": str(p.get("reason", "")).strip()}
    if isinstance(p, str):
        parts = p.split(":", 1)
        if len(parts) == 2:
            return {"skill": parts[0].strip(), "reason": re.sub(r"\s*\(0\.5\)\s*$", "", parts[1].strip()).strip()}
        return {"skill": p.strip(), "reason": "Transferable experience (0.5)"}
    return {"skill": str(p), "reason": ""}

def load_analyzed_job_into_session(job: dict, input_dir: Path):
    """Loads a previously analyzed role from the database into session state without re-running Gemma."""
    jd_text = ""
    if job.get('jd_file'):
        p = Path(job['jd_file'])
        if not p.is_absolute():
            p = Path(".") / p
        if p.exists():
            try:
                jd_text = p.read_text(encoding="utf-8")
            except Exception:
                pass
        if not jd_text:
            alt_p = input_dir / Path(job['jd_file']).name
            if alt_p.exists():
                try:
                    jd_text = alt_p.read_text(encoding="utf-8")
                except Exception:
                    pass

    if not jd_text and job.get('notes'):
        jd_text = job['notes']

    # Classify missing skills
    raw_missing = list(job.get('missing_skills', []))
    missing_core = list(job.get('missing_core', []))
    missing_pref = list(job.get('missing_preferred', []))
    partial_core = [normalize_partial_view_item(p) for p in job.get('partial_core', [])]
    partial_pref = [normalize_partial_view_item(p) for p in job.get('partial_preferred', [])]

    if not missing_core and not missing_pref and not partial_core and not partial_pref:
        for item in raw_missing:
            item_str = str(item)
            item_lower = item_str.lower()
            if "(0.5)" in item_str or "partial" in item_lower or "transferable" in item_lower or "0.5 credit" in item_lower:
                partial_core.append(normalize_partial_view_item(item_str))
            elif "preferred" in item_lower or "bonus" in item_lower or "(nice to have)" in item_lower:
                missing_pref.append(item_str)
            else:
                missing_core.append(item_str)

    missing_list = raw_missing if raw_missing else (missing_core + missing_pref)

    skills_list = job.get('skills', [])
    pref_keywords = ("nice to have", "bonus", "preferred", "familiarity with tools", "design partners", "figma", "cursor", "lovable", "replit", "claude code")
    core_reqs = [s for s in skills_list if not any(p in s.lower() for p in pref_keywords)]
    pref_skills = [s for s in skills_list if any(p in s.lower() for p in pref_keywords)]
    if not core_reqs and not pref_skills:
        core_reqs = skills_list

    extracted = {
        "company": job['company'],
        "title": job['title'],
        "salary": job['salary'],
        "experience": job['experience'],
        "skills": skills_list,
        "core_requirements": core_reqs,
        "preferred_skills": pref_skills
    }

    slug = generate_file_slug(job['company'], job['title'])
    rel_jd_path = job.get('jd_file') or f"01_Input/{slug}.md"

    raw_score = job.get('match_score', 0.0)
    score = int(raw_score) if float(raw_score).is_integer() else round(float(raw_score), 1)

    notes = job.get('notes', '') or ''
    core_match = re.search(r'Core Fit:\s*([\d\.]+)%', notes)
    pref_match = re.search(r'Bonus Fit:\s*([\d\.]+)%', notes)
    if core_match:
        c_val = float(core_match.group(1))
        core_score = int(c_val) if c_val.is_integer() else round(c_val, 1)
    else:
        core_score = score

    if pref_match:
        p_val = float(pref_match.group(1))
        pref_score = int(p_val) if p_val.is_integer() else round(p_val, 1)
    else:
        pref_score = score

    gap_result = job.get('gap_results')
    if not isinstance(gap_result, dict) or not gap_result.get("core_counts"):
        core_total = len(core_reqs) if core_reqs else (len(partial_core) + len(missing_core))
        c_matched = max(0, core_total - len(partial_core) - len(missing_core))
        c_points = c_matched + (len(partial_core) * 0.5)
        core_score_val = round((c_points / core_total) * 100, 1) if core_total > 0 else 100.0

        pref_total = len(pref_skills) if pref_skills else (len(partial_pref) + len(missing_pref))
        p_matched = max(0, pref_total - len(partial_pref) - len(missing_pref))
        p_points = p_matched + (len(partial_pref) * 0.5)
        pref_score_val = round((p_points / pref_total) * 100, 1) if pref_total > 0 else 100.0

        final_score_val = round((core_score_val * 0.85) + (pref_score_val * 0.15), 1) if pref_total > 0 else core_score_val

        gap_result = {
            "final_match_rate": score if score > 0 else final_score_val,
            "core_match_rate": core_score if core_score > 0 else core_score_val,
            "preferred_match_rate": pref_score if pref_score > 0 else pref_score_val,
            "core_counts": {"matched": c_matched, "partial": len(partial_core), "total": core_total, "points": c_points},
            "preferred_counts": {"matched": p_matched, "partial": len(partial_pref), "total": pref_total, "points": p_points},
            "partial_core": partial_core,
            "partial_preferred": partial_pref,
            "missing_core": missing_core,
            "missing_preferred": missing_pref,
            "missing_skills": missing_list
        }

    st.session_state['gap_results'] = gap_result
    st.session_state['current_app_id'] = job['id']
    st.session_state['current_extracted'] = extracted
    st.session_state['current_jd_text'] = jd_text
    st.session_state['current_score'] = score
    st.session_state['current_core_score'] = core_score
    st.session_state['current_pref_score'] = pref_score
    st.session_state['current_missing'] = missing_list
    st.session_state['current_missing_core'] = missing_core
    st.session_state['current_missing_pref'] = missing_pref
    st.session_state['current_partial_core'] = partial_core
    st.session_state['current_partial_pref'] = partial_pref
    st.session_state['current_slug'] = slug
    st.session_state['current_jd_path'] = rel_jd_path
    st.session_state['raw_text_input'] = jd_text
    st.session_state['url_input'] = ""
    st.query_params.pop('app_id', None)

    st.session_state.pop('tailored_done', None)
    st.session_state.pop('tailored_markdown', None)
    st.session_state.pop('output_filename', None)
    st.session_state.pop('output_filename_docx', None)
    st.session_state.pop('rel_resume_path', None)

def dismiss_analyzed_job(db_path: Path, app_id: int, export_db_to_markdown=None):
    """Updates the application record to Ignored status and dismisses it from view."""
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            # Ensure 'Ignored' exists in application_statuses reference table
            cursor.execute("SELECT id FROM application_statuses WHERE status_name = 'Ignored'")
            row = cursor.fetchone()
            if row:
                ignored_status_id = row[0]
            else:
                cursor.execute("SELECT COALESCE(MAX(display_order), 0) + 1 FROM application_statuses")
                next_order = cursor.fetchone()[0]
                cursor.execute(
                    "INSERT INTO application_statuses (status_name, display_order, is_default) VALUES ('Ignored', ?, 0)",
                    (next_order,)
                )
                ignored_status_id = cursor.lastrowid

            cursor.execute(
                "UPDATE applications SET status = 'Ignored', status_id = ? WHERE id = ?",
                (ignored_status_id, app_id)
            )
            conn.commit()
        if export_db_to_markdown:
            export_db_to_markdown()
    except Exception:
        pass

    dismissed = st.session_state.setdefault('dismissed_job_ids', set())
    dismissed.add(app_id)

    if st.session_state.get('current_app_id') == app_id:
        st.session_state.pop('gap_results', None)
        st.session_state.pop('current_extracted', None)
        st.session_state.pop('current_score', None)
        st.session_state.pop('current_core_score', None)
        st.session_state.pop('current_pref_score', None)
        st.session_state.pop('current_missing', None)
        st.session_state.pop('current_missing_core', None)
        st.session_state.pop('current_missing_pref', None)
        st.session_state.pop('current_partial_core', None)
        st.session_state.pop('current_partial_pref', None)
        st.session_state.pop('current_matched_core', None)
        st.session_state.pop('current_matched_pref', None)
        st.session_state.pop('current_slug', None)
        st.session_state.pop('current_jd_path', None)
        st.session_state.pop('current_jd_text', None)
        st.session_state.pop('current_app_id', None)
        st.session_state.pop('tailored_done', None)
        st.session_state.pop('tailored_markdown', None)
        st.query_params.pop('app_id', None)

def tailor_view(db_path: Path, master_resume_path: Path, input_dir: Path, output_dir: Path, export_db_to_markdown):
    # Header matching prototype layout & HTML
    header_left, header_right = st.columns([3, 2], vertical_alignment="center")
    with header_left:
        st.markdown("""
            <div class="main-header-info">
                <h2 class="main-header-title" id="header-view-title">Add Job & Tailor</h2>
                <p class="main-header-desc" id="header-view-desc">Paste details or input URL to optimize, matching exact skill definitions.</p>
            </div>
        """, unsafe_allow_html=True)
    with header_right:
        with st.container(horizontal_alignment="right", key="hdr_right_tailor"):
            if st.button("Go to Tracker", key="btn_goto_tracker", width="content"):
                st.session_state["main_nav_radio"] = "Application Tracker"
                st.rerun()

    st.markdown('<div class="main-header-border"></div>', unsafe_allow_html=True)

    if "url_input" not in st.session_state or st.session_state.url_input == "https://www.instacart.careers/job?id=8120469":
        st.session_state.url_input = ""
    if "raw_text_input" not in st.session_state:
        st.session_state.raw_text_input = ""

    # Clear residual mock demo state from previous sessions
    if st.session_state.get('current_slug') in ("instacart_resume_tailored", "2026_10_25_Instacart_Senior_Product_Manager"):
        st.session_state.pop('current_extracted', None)
        st.session_state.pop('current_score', None)
        st.session_state.pop('current_missing', None)
        st.session_state.pop('current_slug', None)
        st.session_state.pop('current_jd_path', None)
        st.session_state.pop('current_jd_text', None)
        st.session_state.pop('gap_results', None)

    # Clear any residual app_id query param so refreshing the browser starts a clean page
    if st.query_params.get("app_id"):
        st.query_params.pop("app_id", None)

    # Main content containers matching prototype:
    # <div class="space-y-8 max-w-5xl" id="view-ingest-tailor">
    with st.container(key="view_ingest_tailor"):
        # 1. Optimization Blueprint Banner (#tailor-instruction-banner)
        st.markdown("""
        <div class="bg-slate-50 border border-slate-200 rounded-xl p-4 flex items-start gap-3" id="tailor-instruction-banner">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-circle-alert w-5 h-5 text-slate-500 shrink-0 mt-0.5" aria-hidden="true">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" x2="12" y1="8" y2="12"></line>
                <line x1="12" x2="12.01" y1="16" y2="16"></line>
            </svg>
            <div>
                <h4 class="text-xs font-bold text-slate-800 uppercase tracking-wide">Optimization Blueprint</h4>
                <p class="text-xs text-slate-500 mt-1 leading-relaxed">To optimize your outcome, input a Job Description URL or raw requirements text. Our engine parses critical terms, produces a gap analysis match score, and formats tailored versions into isolated directories automatically.</p>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # 2. Recently Analyzed (Ready to Tailor) Section (#presets-selector-section)
        recent_jobs = get_recently_analyzed_jobs(db_path, limit=3)
        if recent_jobs:
            with st.container(key="presets_selector_section"):
                st.markdown('<span class="presets-section-title">Recently Analyzed / Ready to Tailor</span>', unsafe_allow_html=True)
                c_cols = st.columns(3, gap="small")
                for idx, job in enumerate(recent_jobs):
                    with c_cols[idx]:
                        is_active = (st.session_state.get('current_app_id') == job['id'])
                        card_box_key = f"analyzed_card_box_active_{job['id']}" if is_active else f"analyzed_card_box_{job['id']}"
                        score_badge = f"{job['match_score']:.1f}%" if job.get('match_score') else "Analyzed"
                        badge_active_class = " active" if is_active else ""

                        with st.container(border=True, key=card_box_key):
                            st.markdown(f"""
                            <div class="analyzed-card-content">
                                <div class="analyzed-card-header">
                                    <span class="analyzed-card-company">{job['company']}</span>
                                    <span class="analyzed-card-badge{badge_active_class}">{score_badge}</span>
                                </div>
                                <div class="analyzed-card-title">{job['title']}</div>
                            </div>
                            """, unsafe_allow_html=True)

                            c_act_load, c_act_dismiss = st.columns([1.3, 1], gap="small")
                            with c_act_load:
                                btn_load = st.button("Load & Review", key=f"btn_load_{job['id']}", width="stretch")
                            with c_act_dismiss:
                                btn_dismiss = st.button("✕ Dismiss", key=f"btn_dismiss_{job['id']}", width="stretch")

                            if btn_load:
                                load_analyzed_job_into_session(job, input_dir)
                                st.rerun()

                            if btn_dismiss:
                                dismiss_analyzed_job(db_path, job['id'], export_db_to_markdown)
                                st.rerun()

        # 3. Ingest Form Container (#ingest-form-container)
        with st.container(border=True, key="ingest_form_container"):
            st.markdown('<label class="ingest-label">Job Description Link / Target URL</label>', unsafe_allow_html=True)
            url_input = st.text_input(
                "Job Description Link / Target URL",
                key="url_input",
                placeholder="e.g. https://careers.stripe.com/jobs/designer-platform-frontend",
                label_visibility="collapsed"
            )

            st.markdown("""
            <div class="ingest-label-row">
                <label class="ingest-label">Or Paste Raw Requirements Text</label>
                <span class="ingest-hint">Optional if URL provided</span>
            </div>
            """, unsafe_allow_html=True)
            raw_text_input = st.text_area(
                "Or Paste Raw Requirements Text",
                key="raw_text_input",
                height=110,
                placeholder="Paste the full job requirements, skills, and about sections here...",
                label_visibility="collapsed"
            )

            st.markdown('<div class="ingest-footer-divider"></div>', unsafe_allow_html=True)
            f_left, f_right = st.columns([1, 1], vertical_alignment="center")
            with f_left:
                st.markdown('<span class="ingest-footer-note">Prepares Gap Analysis Match Matrix</span>', unsafe_allow_html=True)
            with f_right:
                btn_fetch = st.button("Fetch & Extract Requirements", type="primary", key="btn_fetch_extract", width="content")

        if btn_fetch:
            jd_content = ""
            st.session_state.pop('tailored_done', None)
            st.session_state.pop('tailored_markdown', None)
            fetch_progress = st.empty()

            render_progress_card(
                fetch_progress,
                "Fetching & Analyzing Job Requirements",
                15,
                [
                    ("Fetching job description content...", "active"),
                    ("Extracting role details, salary, and core/bonus requirements", "pending"),
                    ("Scoring requirements against Master Resume (1.0 / 0.5 / 0.0 credit)", "pending"),
                    ("Saving JD copy and updating tracker database", "pending"),
                ]
            )

            try:
                jd_content = get_job_description_content(url_input, raw_text_input)
            except Exception as e:
                fetch_progress.empty()
                st.error(f"Error extracting job description: {e}")
                jd_content = ""

            if jd_content:
                try:
                    resolved_master_path = resolve_master_resume_path(master_resume_path)
                except Exception:
                    resolved_master_path = master_resume_path

                render_progress_card(
                    fetch_progress,
                    "Fetching & Analyzing Job Requirements",
                    45,
                    [
                        ("Fetched job description content", "done"),
                        ("Extracting role details, salary, and core/bonus requirements...", "active"),
                        ("Scoring requirements against Master Resume (1.0 / 0.5 / 0.0 credit)", "pending"),
                        ("Saving JD copy and updating tracker database", "pending"),
                    ]
                )

                try:
                    extracted = extract_jd_details(jd_content)
                    core_reqs = extracted.get("core_requirements", [])
                    pref_skills = extracted.get("preferred_skills", [])
                    if not core_reqs and not pref_skills:
                        core_reqs = extracted.get("skills", [])

                    ext_comp = extracted.get("company", "Company")
                    ext_title = extracted.get("title", "Role")
                    render_progress_card(
                        fetch_progress,
                        "Fetching & Analyzing Job Requirements",
                        80,
                        [
                            ("Fetched job description content", "done"),
                            (f"Extracted role details ({ext_comp} — {ext_title})", "done"),
                            ("Scoring requirements against Master Resume (1.0 / 0.5 / 0.0 credit)...", "active"),
                            ("Saving JD copy and updating tracker database", "pending"),
                        ]
                    )

                    gap_result = calculate_gap(core_reqs, pref_skills, resolved_master_path)
                except Exception as llm_err:
                    fetch_progress.empty()
                    st.error(f"AI Model Error: {llm_err}")
                    st.stop()

                render_progress_card(
                    fetch_progress,
                    "Fetching & Analyzing Job Requirements",
                    95,
                    [
                        ("Fetched job description content", "done"),
                        (f"Extracted role details ({ext_comp} — {ext_title})", "done"),
                        ("Scored requirements against Master Resume", "done"),
                        ("Saving JD copy and updating tracker database...", "active"),
                    ]
                )

                raw_score = gap_result["final_match_rate"]
                score = int(raw_score) if float(raw_score).is_integer() else round(float(raw_score), 1)

                raw_core = gap_result["core_match_rate"]
                core_score = int(raw_core) if float(raw_core).is_integer() else round(float(raw_core), 1)

                raw_pref = gap_result["preferred_match_rate"]
                pref_score = int(raw_pref) if float(raw_pref).is_integer() else round(float(raw_pref), 1)

                missing = gap_result.get("missing_skills", [])
                missing_core = gap_result.get("missing_core", [])
                missing_pref = gap_result.get("missing_preferred", [])
                partial_core = gap_result.get("partial_core", [])
                partial_pref = gap_result.get("partial_preferred", [])
                matched_core = gap_result.get("matched_core", [])
                matched_pref = gap_result.get("matched_preferred", [])

                slug = generate_file_slug(extracted.get('company', 'Company'), extracted.get('title', 'Role'))
                jd_file_path = input_dir / f"{slug}.md"
                jd_file_path.write_text(jd_content, encoding="utf-8")

                rel_jd_path = f"01_Input/{slug}.md"
                today_str = datetime.now().strftime("%Y-%m-%d")
                notes_str = f"JD extracted on {today_str} | Core Fit: {core_score}% | Bonus Fit: {pref_score}% | Overall: {score}%"

                # Check or insert application record into DB with Analyzed status (status_id=1)
                app_id = None
                try:
                    with sqlite3.connect(db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            "SELECT id FROM applications WHERE jd_file = ? OR (company = ? AND title = ?) ORDER BY id DESC LIMIT 1",
                            (rel_jd_path, extracted.get('company', ''), extracted.get('title', ''))
                        )
                        existing_app = cursor.fetchone()
                        missing_storage = {
                            "gap_results": dict(gap_result),
                            "core": missing_core,
                            "preferred": missing_pref,
                            "partial_core": partial_core,
                            "partial_pref": partial_pref,
                            "all": missing
                        }
                        if existing_app:
                            app_id = existing_app[0]
                            cursor.execute("""
                                UPDATE applications
                                SET match_score = ?, salary = ?, experience = ?, skills = ?, missing_skills = ?, jd_file = ?, notes = ?
                                WHERE id = ?
                            """, (
                                score,
                                extracted.get('salary', 'N/A'),
                                extracted.get('experience', 'N/A'),
                                json.dumps(extracted.get('skills', [])),
                                json.dumps(missing_storage),
                                rel_jd_path,
                                notes_str,
                                app_id
                            ))
                        else:
                            cursor.execute("""
                                INSERT INTO applications (company, title, status, status_id, date_submitted, match_score, salary, experience, skills, missing_skills, jd_file, notes)
                                VALUES (?, ?, 'Analyzed', 1, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                extracted.get('company', ''),
                                extracted.get('title', ''),
                                today_str,
                                score,
                                extracted.get('salary', 'N/A'),
                                extracted.get('experience', 'N/A'),
                                json.dumps(extracted.get('skills', [])),
                                json.dumps(missing_storage),
                                rel_jd_path,
                                notes_str
                            ))
                            app_id = cursor.lastrowid
                    export_db_to_markdown()
                except Exception:
                    pass

                fetch_progress.empty()
                st.session_state['gap_results'] = gap_result
                st.session_state['current_app_id'] = app_id
                st.session_state['current_extracted'] = extracted
                st.session_state['current_jd_text'] = jd_content
                st.session_state['current_score'] = score
                st.session_state['current_core_score'] = core_score
                st.session_state['current_pref_score'] = pref_score
                st.session_state['current_missing'] = missing
                st.session_state['current_missing_core'] = missing_core
                st.session_state['current_missing_pref'] = missing_pref
                st.session_state['current_partial_core'] = partial_core
                st.session_state['current_partial_pref'] = partial_pref
                st.session_state['current_matched_core'] = matched_core
                st.session_state['current_matched_pref'] = matched_pref
                st.session_state['current_slug'] = slug
                st.session_state['current_jd_path'] = rel_jd_path
                st.query_params.pop('app_id', None)
                st.rerun()

        if st.session_state.get('gap_results') and st.session_state.get('current_extracted'):
            gap_result = st.session_state['gap_results']
            ext = st.session_state['current_extracted']
            filename_md, filename_docx = generate_tailored_filenames(ext.get('company', 'Company'), ext.get('title', 'Role'))
            target_storage_file = f"02_Output/{filename_md}"


            raw_score = gap_result.get('final_match_rate', 0.0)
            score = int(raw_score) if float(raw_score).is_integer() else round(float(raw_score), 1)

            raw_core = gap_result.get('core_match_rate', 0.0)
            core_score = int(raw_core) if float(raw_core).is_integer() else round(float(raw_core), 1)

            raw_pref = gap_result.get('preferred_match_rate', 0.0)
            pref_score = int(raw_pref) if float(raw_pref).is_integer() else round(float(raw_pref), 1)

            core_counts = gap_result.get('core_counts', {})
            pref_counts = gap_result.get('preferred_counts', {})

            partial_core = gap_result.get('partial_core', [])
            partial_pref = gap_result.get('partial_preferred', [])
            missing_core = gap_result.get('missing_core', [])
            missing_pref = gap_result.get('missing_preferred', [])
            missing = gap_result.get('missing_skills', missing_core + missing_pref)

            # Calculate explicit tallies for metric cards
            c_matched = core_counts.get("matched", 0)
            c_total = core_counts.get("total", 0)
            c_points = core_counts.get("points", c_matched)
            if not float(c_points).is_integer() or core_counts.get("partial", 0) > 0:
                c_pts_str = f"{c_points:g}"
                core_tally = f"{c_pts_str} / {c_total} Core Met"
            else:
                core_tally = f"{c_matched} of {c_total} Core Met"

            p_matched = pref_counts.get("matched", 0)
            p_total = pref_counts.get("total", 0)
            p_points = pref_counts.get("points", p_matched)
            if not float(p_points).is_integer() or pref_counts.get("partial", 0) > 0:
                p_pts_str = f"{p_points:g}"
                pref_tally = f"{p_pts_str} / {p_total} Bonus Met"
            else:
                pref_tally = f"{p_matched} of {p_total} Bonus Met"
            
            with st.container(key="extraction_results_block"):
                col_meta, col_gap = st.columns([3, 2], gap="medium")
                
                with col_meta:
                    with st.container(border=True, key="extracted_meta_card"):
                        skills_html = ""
                        missing_skill_names = []
                        for m in (missing_core + missing_pref):
                            if isinstance(m, dict):
                                missing_skill_names.append(m.get("skill", "").lower())
                            else:
                                missing_skill_names.append(str(m).split(":")[0].strip().lower())

                        partial_skill_names = []
                        for p in (partial_core + partial_pref):
                            if isinstance(p, dict):
                                partial_skill_names.append(p.get("skill", "").lower())
                            else:
                                partial_skill_names.append(str(p).split(":")[0].strip().lower())

                        pref_skills_lower = [str(p).lower() for p in ext.get("preferred_skills", [])]
                        for skill in ext.get("skills", []):
                            sk_low = skill.lower().strip()
                            is_missing = any(sk_low in m or m in sk_low for m in missing_skill_names if m)
                            is_partial = any(sk_low in p or p in sk_low for p in partial_skill_names if p)
                            is_preferred = any(sk_low in p or p in sk_low for p in pref_skills_lower if p)

                            if is_missing and is_preferred:
                                skills_html += f'<span class="extracted-skill-badge missing-preferred">{skill} (preferred gap)</span>'
                            elif is_missing:
                                skills_html += f'<span class="extracted-skill-badge missing">{skill} (core gap)</span>'
                            elif is_partial:
                                skills_html += f'<span class="extracted-skill-badge partial">{skill} (0.5 credit)</span>'
                            else:
                                skills_html += f'<span class="extracted-skill-badge match">{skill}</span>'

                        st.markdown(f"""
                        <div>
                            <div class="extracted-header-row">
                                <div>
                                    <p class="extracted-sub-label">Extraction Summary</p>
                                    <h3 class="extracted-job-title">{ext.get('title', 'Position')}</h3>
                                    <p class="extracted-company-exp">{ext.get('company', 'Company')} — {ext.get('experience', '3+ years')}</p>
                                </div>
                                <span class="extracted-badge-fulltime">Full-time</span>
                            </div>
                            <div class="extracted-details-grid">
                                <div class="extracted-detail-box">
                                    <p class="detail-box-label">Experience Required</p>
                                    <p class="detail-box-val">{ext.get('experience', 'N/A')}</p>
                                </div>
                                <div class="extracted-detail-box">
                                    <p class="detail-box-label">Salary Range</p>
                                    <p class="detail-box-val">{ext.get('salary', 'N/A')}</p>
                                </div>
                            </div>
                            <p class="extracted-sub-label skills-label">Required Skills Matrix</p>
                            <div class="extracted-skills-wrap">
                                {skills_html}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        st.markdown('<div class="extracted-footer-divider"></div>', unsafe_allow_html=True)
                        f_left, f_right = st.columns([1.2, 1], vertical_alignment="center")
                        with f_left:
                            st.markdown(f"""
                            <div class="extracted-storage-target" style="min-width: 0 !important; max-width: 100% !important; width: 100% !important; overflow: hidden !important; display: flex !important; flex-direction: column !important;">
                                <span class="storage-target-label">File Storage Target</span>
                                <span class="storage-target-path" style="display: block !important; width: 100% !important; word-break: break-all !important; overflow-wrap: anywhere !important; white-space: normal !important; line-height: 1.4 !important;">{target_storage_file}</span>
                            </div>
                            """, unsafe_allow_html=True)
                        with f_right:
                            btn_gen_tailored = st.button("Generate Tailored Resume", key="btn_generate_tailored_resume", type="primary", width="stretch")

                with col_gap:
                    dashoffset = 364 - (364 * score) / 100
                    
                    items_html_list = []
                    # 1. Partial items (orange badge: 0.5 CREDIT)
                    for p in (partial_core + partial_pref):
                        p_norm = normalize_partial_view_item(p)
                        p_skill = p_norm.get("skill", "")
                        p_reason = p_norm.get("reason", "")
                        p_content = f"<strong>{p_skill}</strong>: {p_reason}" if p_reason else f"<strong>{p_skill}</strong>"
                        items_html_list.append(
                            f'<li class="missing-skill-item">'
                            f'<span class="missing-dot amber"></span>'
                            f'<div style="font-size: 13px; color: #334155; line-height: 1.5;">'
                            f'<span style="font-size: 9px; font-weight: 800; background: #fef3c7; color: #b45309; padding: 2px 6px; border-radius: 4px; margin-right: 6px; letter-spacing: 0.5px; border: 1px solid #fde68a; display: inline-block;">0.5 CREDIT</span>'
                            f'<span>{p_content}</span>'
                            f'</div></li>'
                        )

                    # 2. Missing items (red badge: MISSING (0.0))
                    for m in (missing_core + missing_pref):
                        m_str = str(m)
                        if ":" in m_str:
                            parts = m_str.split(":", 1)
                            m_content = f"<strong>{parts[0].strip()}</strong>: {parts[1].strip()}"
                        else:
                            m_content = f"<strong>{m_str}</strong>"
                        items_html_list.append(
                            f'<li class="missing-skill-item">'
                            f'<span class="missing-dot red"></span>'
                            f'<div style="font-size: 13px; color: #334155; line-height: 1.5;">'
                            f'<span style="font-size: 9px; font-weight: 800; background: #fee2e2; color: #b91c1c; padding: 2px 6px; border-radius: 4px; margin-right: 6px; letter-spacing: 0.5px; border: 1px solid #fecaca; display: inline-block;">MISSING (0.0)</span>'
                            f'<span>{m_content}</span>'
                            f'</div></li>'
                        )

                    if items_html_list:
                        gaps_card_content = f'<ul class="space-y-3" style="list-style: none; padding-left: 0; margin: 0;">{"".join(items_html_list)}</ul>'
                    else:
                        gaps_card_content = (
                            '<div style="padding: 12px 16px; background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; color: #166534; font-size: 13px; font-weight: 600; display: flex; align-items: center; gap: 8px;">'
                            '<span class="missing-dot green"></span>'
                            '<span>All required core and bonus qualifications confirmed in Master Resume!</span>'
                            '</div>'
                        )

                    total_missing = len(missing_core) + len(missing_pref)
                    total_partial = len(partial_core) + len(partial_pref)

                    if total_missing == 0 and total_partial == 0:
                        summary_msg = "All required core and bonus qualifications confirmed in Master Resume!"
                    elif total_missing == 0:
                        summary_msg = f"All essential qualifications confirmed! {total_partial} requirements awarded 0.5 credit for transferable skills."
                    elif core_score >= 85 and core_score > score:
                        summary_msg = f"Strong core alignment ({core_score}%)! Gaps are primarily nice-to-have bonus items rather than essential dealbreakers."
                    else:
                        grammar = "requirement" if total_missing == 1 else "requirements"
                        summary_msg = f"Essential qualifications drive 85% of your match. We found {total_missing} missing {grammar}."

                    st.markdown(f"""<div class="extraction-right-col-wrapper" id="extraction-right-column">
<div class="border border-slate-200 rounded-lg p-6 bg-white flex flex-col items-center text-center shadow-sm flex-1 justify-center" id="gap-analysis-card">
<p class="text-xs font-bold text-slate-400 uppercase tracking-widest mb-3">Gap Analysis Score</p>
<div class="relative w-32 h-32 flex items-center justify-center gauge-container" style="position: relative; width: 128px; height: 128px; display: flex; align-items: center; justify-content: center; margin: 0 auto;">
<svg class="w-full h-full transform -rotate-90" viewBox="0 0 128 128" style="width: 128px; height: 128px; transform: rotate(-90deg);">
<circle cx="64" cy="64" r="58" stroke="#F1F5F9" stroke-width="12" fill="transparent"></circle>
<circle cx="64" cy="64" r="58" stroke="#334155" stroke-width="12" fill="transparent" stroke-dasharray="364" stroke-dashoffset="{dashoffset}" stroke-linecap="round"></circle>
</svg>
<span class="absolute text-3xl font-black text-slate-800 gauge-score-text" style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 30px; font-weight: 900; color: #1e293b; line-height: 1;">{score}%</span>
</div>
<div style="display: flex; gap: 8px; justify-content: center; width: 100%; margin-top: 14px;">
<div style="flex: 1.1; padding: 6px 4px; background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; text-align: center;">
<span style="display: block; font-size: 10px; font-weight: 700; color: #166534; text-transform: uppercase; letter-spacing: 0.5px;">Core Fit (85%)</span>
<span style="display: block; font-size: 18px; font-weight: 800; color: #15803d; line-height: 1.2;">{core_score}%</span>
<span style="display: block; font-size: 10px; font-weight: 600; color: #166534; margin-top: 2px;">{core_tally}</span>
</div>
<div style="flex: 1; padding: 6px 4px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; text-align: center;">
<span style="display: block; font-size: 10px; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px;">Bonus Fit (15%)</span>
<span style="display: block; font-size: 18px; font-weight: 800; color: #334155; line-height: 1.2;">{pref_score}%</span>
<span style="display: block; font-size: 10px; font-weight: 600; color: #64748b; margin-top: 2px;">{pref_tally}</span>
</div>
<div style="flex: 1; padding: 6px 4px; background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 8px; text-align: center;">
<span style="display: block; font-size: 10px; font-weight: 700; color: #475569; text-transform: uppercase; letter-spacing: 0.5px;">Overall</span>
<span style="display: block; font-size: 18px; font-weight: 800; color: #0f172a; line-height: 1.2;">{score}%</span>
<span style="display: block; font-size: 10px; font-weight: 600; color: #475569; margin-top: 2px;">Weighted</span>
</div>
</div>
<p class="mt-3 text-xs text-slate-500 leading-relaxed">{summary_msg}</p>
</div>
<div class="border border-slate-200 rounded-lg p-6 bg-slate-50 shadow-sm" id="missing-skills-card">
<p class="text-xs font-bold text-slate-400 uppercase tracking-widest mb-4">Gaps & Transferable Skills</p>
{gaps_card_content}
</div>
</div>""", unsafe_allow_html=True)

            if btn_gen_tailored:
                company_val = ext.get('company', 'Company').strip() or "Company"
                title_val = ext.get('title', 'Role').strip() or "Role"

                filename_md, filename_docx = generate_tailored_filenames(company_val, title_val)
                output_filename = filename_md
                md_path = output_dir / filename_md
                docx_path = output_dir / filename_docx
                rel_resume_path = f"02_Output/{filename_md}"
                rel_docx_path = f"02_Output/{filename_docx}"
                today_str = datetime.now().strftime("%Y-%m-%d")

                tailor_progress = st.empty()
                stage_order = ["loading", "thinking", "summary", "skills", "experience", "assembling"]
                stage_labels = {
                    "loading": "Load Master Profile and static sections",
                    "thinking": f"Plan achievement selection for {company_val} ({title_val})",
                    "summary": "Draft tailored Professional Summary",
                    "skills": "Prioritize and categorize Skills Matrix",
                    "experience": "Tailor Professional Experience bullets",
                    "assembling": "Assemble static sections and export .md and .docx files",
                }

                def update_tailor_ui(stage_key: str, active_detail: str, pct: int):
                    idx = stage_order.index(stage_key) if stage_key in stage_order else 0
                    steps_list = []
                    for i, s_key in enumerate(stage_order):
                        if i < idx:
                            steps_list.append((stage_labels[s_key], "done"))
                        elif i == idx:
                            steps_list.append((active_detail or stage_labels[s_key], "active"))
                        else:
                            steps_list.append((stage_labels[s_key], "pending"))
                    render_progress_card(
                        tailor_progress,
                        f"Generating Tailored Resume — {company_val}",
                        pct,
                        steps_list
                    )

                tailored_markdown = None
                try:
                    resolved_master_path = resolve_master_resume_path(master_resume_path)
                    tailored_markdown = generate_tailored_resume(
                        st.session_state['current_jd_text'],
                        resolved_master_path,
                        company_val,
                        title_val,
                        progress_callback=update_tailor_ui
                    )
                except FileNotFoundError as fnf:
                    tailor_progress.empty()
                    st.error(f"Cannot tailor resume: {fnf}")
                except Exception as e:
                    tailor_progress.empty()
                    st.error(f"Failed to generate tailored resume: {e}")

                if tailored_markdown:
                    md_path.write_text(tailored_markdown, encoding="utf-8")
                    try:
                        convert_md_to_docx(tailored_markdown, docx_path)
                    except Exception as docx_err:
                        st.warning(f"Could not convert to Word format: {docx_err}")

                    initial_notes = f"Tailored resume generated on {today_str} matching skills: {', '.join(ext.get('skills', []))}."

                    # Update SQLite database
                    with sqlite3.connect(db_path) as conn:
                        cursor = conn.cursor()
                        app_id = st.session_state.get('current_app_id')
                        old_status_id = 1
                        if not app_id:
                            cursor.execute(
                                "SELECT id, status_id FROM applications WHERE jd_file = ? OR (company = ? AND title = ?) ORDER BY id DESC LIMIT 1",
                                (st.session_state.get('current_jd_path', ''), company_val, title_val)
                            )
                            row = cursor.fetchone()
                            if row:
                                app_id, old_status_id = row[0], row[1]
                        else:
                            cursor.execute("SELECT status_id FROM applications WHERE id = ?", (app_id,))
                            row = cursor.fetchone()
                            if row:
                                old_status_id = row[0]

                        if app_id:
                            cursor.execute("""
                                UPDATE applications
                                SET resume_file = ?, resume_docx = ?, status = 'Tailored', status_id = 2, notes = ?
                                WHERE id = ?
                            """, (rel_resume_path, rel_docx_path, initial_notes, app_id))
                        else:
                            cursor.execute("""
                                INSERT INTO applications (company, title, status, status_id, date_submitted, match_score, salary, experience, skills, missing_skills, jd_file, resume_file, resume_docx, notes)
                                VALUES (?, ?, 'Tailored', 2, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                company_val,
                                title_val,
                                today_str,
                                st.session_state.get('current_score', 0),
                                ext.get('salary', 'N/A'),
                                ext.get('experience', 'N/A'),
                                json.dumps(ext.get('skills', [])),
                                json.dumps(st.session_state.get('current_missing', [])),
                                st.session_state.get('current_jd_path', ''),
                                rel_resume_path,
                                rel_docx_path,
                                initial_notes
                            ))
                            app_id = cursor.lastrowid
                            old_status_id = 1

                        # Insert / update record into application_status_history logging the move to 'Tailored'
                        cursor.execute(
                            "SELECT id FROM application_status_history WHERE application_id = ? AND new_status_id = 2 ORDER BY id DESC LIMIT 1",
                            (app_id,)
                        )
                        hist_record = cursor.fetchone()
                        if hist_record:
                            cursor.execute(
                                "UPDATE application_status_history SET notes = ? WHERE id = ?",
                                (f"Moved to Tailored with resume {filename_md} and {filename_docx}", hist_record[0])
                            )
                        else:
                            cursor.execute("""
                                INSERT INTO application_status_history (application_id, old_status_id, new_status_id, notes)
                                VALUES (?, ?, 2, ?)
                            """, (app_id, old_status_id, f"Moved to Tailored with resume {filename_md} and {filename_docx}"))

                    export_db_to_markdown()
                    tailor_progress.empty()

                    st.session_state['tailored_done'] = True
                    st.session_state['tailored_markdown'] = tailored_markdown
                    st.session_state['md_path'] = md_path
                    st.session_state['docx_path'] = docx_path
                    st.session_state['output_filename'] = filename_md
                    st.session_state['output_filename_docx'] = filename_docx
                    st.session_state['rel_resume_path'] = rel_resume_path
                    st.session_state['rel_docx_path'] = rel_docx_path
                    st.rerun()

        if st.session_state.get('tailored_done', False):
            output_filename = st.session_state.get('output_filename', 'tailored_resume.md')
            st.success(f"Tailored resume saved to {output_filename}!")

            with st.container(key="tailored_output_container"):
                st.markdown(f"""
                <div style="background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; margin-top: 12px; margin-bottom: 16px;">
                    <div style="background-color: #fcfcfc; border-bottom: 1px solid #e2e8f0; padding: 14px 20px; display: flex; justify-content: space-between; align-items: center;">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span style="width: 8px; height: 8px; border-radius: 50%; background-color: #10b981; display: inline-block;"></span>
                            <span style="font-weight: 700; font-size: 13px; color: #0f172a;">Tailored Resume Generated & Persisted</span>
                        </div>
                    </div>
                    <div style="background-color: #f8fafc; padding: 12px 16px; display: flex; flex-direction: column; gap: 6px; font-size: 11px; color: #475569;">
                        <div style="display: flex; align-items: center; gap: 6px;"><b>JD Copy Auto-Saved:</b> <code style="background-color: #ffffff; border: 1px solid #e2e8f0; padding: 2px 6px; border-radius: 4px; font-family: monospace;">{st.session_state.get('current_jd_path', '')}</code></div>
                        <div style="display: flex; align-items: center; gap: 6px;"><b>Markdown Output:</b> <code style="background-color: #ffffff; border: 1px solid #e2e8f0; padding: 2px 6px; border-radius: 4px; font-family: monospace;">{st.session_state.get('rel_resume_path', '')}</code></div>
                        <div style="display: flex; align-items: center; gap: 6px;"><b>Word Document:</b> <code style="background-color: #ffffff; border: 1px solid #e2e8f0; padding: 2px 6px; border-radius: 4px; font-family: monospace;">02_Output/{st.session_state.get('output_filename_docx', '')}</code></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                st.text_area(
                    "Tailored Resume Preview (Markdown)",
                    value=st.session_state.get('tailored_markdown', ''),
                    height=450,
                    key="tailored_resume_preview_area"
                )

                col_dl_md, col_dl_docx = st.columns(2, gap="small")
                with col_dl_md:
                    st.download_button(
                        label="Download Markdown (.md)",
                        data=st.session_state.get('tailored_markdown', ''),
                        file_name=output_filename,
                        mime="text/markdown",
                        width='stretch',
                        key="btn_download_md"
                    )
                with col_dl_docx:
                    docx_file = Path(st.session_state.get('docx_path', ''))
                    if docx_file.exists():
                        with open(docx_file, "rb") as f:
                            st.download_button(
                                label="Download MS Word (.docx)",
                                data=f,
                                file_name=st.session_state.get('output_filename_docx', 'resume.docx'),
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                width='stretch',
                                key="btn_download_docx"
                            )