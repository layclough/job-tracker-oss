import sqlite3
import re
from pathlib import Path
import pandas as pd
import streamlit as st

def get_status_options(db_path):
    with sqlite3.connect(db_path) as conn:
        try:
            df = pd.read_sql("SELECT status_name FROM application_statuses ORDER BY display_order", conn)
            return df['status_name'].tolist()
        except Exception:
            return ["Analyzed", "Tailored", "Applied", "Interviewing", "Rejected", "Ghosted", "Withdrawn", "Offered", "Ignored"]


def resolve_tailored_md_path(file_path_str: str | None) -> Path | None:
    """Resolves the path to the generated tailored resume (.md) file."""
    if not file_path_str or file_path_str == "N/A":
        return None

    file_path = Path(file_path_str)
    if not file_path.is_absolute() and not file_path_str.startswith("02_Output"):
        file_path = Path("02_Output") / file_path.name

    md_path = file_path.with_suffix(".md")

    if not md_path.exists():
        fallback_name = re.sub(r'^(\d{4})_(\d{2})_(\d{2})', r'\1-\2-\3', md_path.name)
        fallback_path = md_path.with_name(fallback_name)
        if fallback_path.exists():
            md_path = fallback_path
        else:
            fallback_name_2 = md_path.name.replace("_", "-")
            fallback_path_2 = md_path.with_name(fallback_name_2)
            if fallback_path_2.exists():
                md_path = fallback_path_2

    return md_path

@st.dialog("Track New Application")
def add_application_dialog(db_path, export_func):
    company = st.text_input("Company Name", placeholder="e.g. Figma")
    title = st.text_input("Job Title", placeholder="e.g. Senior Frontend Engineer")
    col1, col2 = st.columns(2)
    with col1:
        match_score = st.number_input("Match Score %", min_value=1, max_value=100, value=75)
    with col2:
        status = st.selectbox(
            "Initial Status",
            options=get_status_options(db_path),
        )
    date_submitted = st.date_input("Date Submitted (Optional)", value=None)
    notes = st.text_area(
        "Initial Notes (Optional)",
        placeholder="Write initial phone screen, referral details...",
        height=80,
    )

    st.markdown("<br>", unsafe_allow_html=True)
    col_btn1, col_btn2 = st.columns([1, 1])
    with col_btn2:
        if st.button("Track Application", type="primary", width='stretch', key="dlg_add_submit"):
            if not company or not title:
                st.error("Company and Title are required!")
            else:
                today_str = str(date_submitted) if date_submitted else "—"
                with sqlite3.connect(db_path) as conn:
                    conn.execute(
                        """
                        INSERT INTO applications (company, title, status, date_submitted, match_score, jd_file, resume_file, follow_up_date, notes)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (company, title, status, today_str, float(match_score), "N/A", "N/A", "—", notes or ""),
                    )
                    conn.commit()
                export_func()
                st.session_state["show_add_modal"] = False
                st.rerun()
    with col_btn1:
        if st.button("Cancel", width='stretch', key="dlg_add_cancel"):
            st.session_state["show_add_modal"] = False
            st.rerun()


@st.dialog("Application Details", width="small")
def show_application_details(app_id, db_path, export_func):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()

    if not row:
        st.error("Application not found.")
        if st.button("Close", key="dlg_not_found_close"):
            st.session_state.active_details_app_id = None
            st.rerun()
        return

    st.markdown(
        f"""
        <div style="margin-bottom: 16px;">
            <span style="font-size: 10px; font-weight: 700; color: #94a3b8; letter-spacing: 0.05em; text-transform: uppercase;">APPLICATION DETAILS</span>
            <h2 style="font-size: 22px; font-weight: 800; color: #0f172a; margin: 4px 0 0 0; padding: 0; line-height: 1.2;">{row['company']}</h2>
            <p style="font-size: 13px; color: #475569; margin: 2px 0 0 0; padding: 0; font-weight: 500;">{row['title']}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    row_keys = row.keys()
    file_keys = ["jd_file", "resume_file", "resume_docx"]
    files_count = sum(1 for k in file_keys if k in row_keys and row[k] and row[k] != "N/A")

    st.markdown(
        f"""
        <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px 16px; margin-bottom: 16px; display: flex; justify-content: space-between;">
            <div>
                <div style="font-size: 10px; font-weight: 700; color: #94a3b8; letter-spacing: 0.05em; text-transform: uppercase;">MATCH ALIGNMENT</div>
                <div style="font-size: 18px; font-weight: 800; color: #b45309; margin-top: 4px; display: flex; align-items: center; gap: 4px;">
                    ✨ {int(row["match_score"])}%
                </div>
            </div>
            <div style="text-align: right;">
                <div style="font-size: 10px; font-weight: 700; color: #94a3b8; letter-spacing: 0.05em; text-transform: uppercase;">FILES FOUND</div>
                <div style="font-size: 18px; font-weight: 800; color: #0f172a; margin-top: 4px;">
                    {files_count} file(s)
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1 FROM application_status_history h
            JOIN application_statuses s ON h.new_status_id = s.id
            WHERE h.application_id = ? AND s.status_name = 'Interviewing'
        """, (app_id,))
        reached_interview = cursor.fetchone() is not None

    if not reached_interview and row["status"] == "Interviewing":
        reached_interview = True

    if reached_interview:
        st.markdown(
            """
            <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 12px 16px; margin-bottom: 16px; display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 16px;">🎯</span>
                <span style="font-size: 14px; font-weight: 700; color: #166534;">Reached Interview Stage</span>
            </div>
            """, unsafe_allow_html=True
        )
    else:
        if st.checkbox("Reached Recruiter/Interview Stage", key=f"dlg_interview_cb_{app_id}"):
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM application_statuses WHERE status_name = 'Interviewing'")
                interviewing_status_id = cursor.fetchone()[0]
                cursor.execute(
                    "INSERT INTO application_status_history (application_id, old_status_id, new_status_id) VALUES (?, NULL, ?)",
                    (app_id, interviewing_status_id)
                )
                conn.commit()
            st.rerun()

    edit_col1, edit_col2 = st.columns(2)
    with edit_col1:
        edit_company = st.text_input("COMPANY NAME", value=row["company"], key=f"dlg_company_{app_id}")
    with edit_col2:
        edit_title = st.text_input("JOB TITLE", value=row["title"], key=f"dlg_title_{app_id}")

    col1, col2, col3 = st.columns(3)
    with col1:
        status_opts = get_status_options(db_path)
        cur_status = row["status"]
        status_idx = status_opts.index(cur_status) if cur_status in status_opts else 0
        new_status = st.selectbox("STATUS", options=status_opts, index=status_idx, key=f"dlg_status_{app_id}")
    with col2:
        new_date_sub = st.text_input("SUBMITTED", value=row["date_submitted"] or "—", key=f"dlg_sub_{app_id}")
    with col3:
        parsed_date = None
        try:
            if row["follow_up_date"] and str(row["follow_up_date"]).strip() not in ["", "—", "N/A", "None", "nan"]:
                dt = pd.to_datetime(row["follow_up_date"], errors="coerce")
                if pd.notna(dt):
                    parsed_date = dt.date()
        except Exception:
            pass
        new_follow_date = st.date_input("FOLLOW-UP", value=parsed_date, key=f"dlg_follow_{app_id}")

    st.markdown("<br>", unsafe_allow_html=True)

    new_notes = st.text_area(
        "📝 APPLICATION NOTES & CONVERSATION LOGS",
        value=row["notes"] or "",
        height=120,
        key=f"dlg_notes_{app_id}",
        help="Record interview logs, recruiter screens, take-home tasks, etc.",
    )

    st.markdown(
        "<div style='font-size: 10px; font-weight: 700; color: #94a3b8; letter-spacing: 0.05em; text-transform: uppercase; margin-top: 8px; margin-bottom: 6px;'>RELATED WORKSPACE FILES</div>",
        unsafe_allow_html=True,
    )

    related_files = []

    if "jd_file" in row_keys and row["jd_file"] and row["jd_file"] != "N/A":
        related_files.append(("📄 Job Description (JD)", row["jd_file"]))

    if "resume_file" in row_keys and row["resume_file"] and row["resume_file"] != "N/A":
        related_files.append(("📝 Tailored Resume (Markdown)", row["resume_file"]))

    if "resume_docx" in row_keys and row["resume_docx"] and row["resume_docx"] != "N/A":
        related_files.append(("💼 Recruiter Document (.docx)", row["resume_docx"]))

    with st.container(border=True):
        if related_files:
            for label, file_path in related_files:
                path_obj = Path(file_path)
                exists = path_obj.exists()
                status_icon = "✅" if exists else "⚠️"
                st.markdown(f"**{label}**")
                st.code(f"{status_icon} {file_path}", language="text")
        else:
            st.info("No related files linked to this application.")

    st.markdown("<br>", unsafe_allow_html=True)

    btn_col1, btn_col2 = st.columns([1, 1])
    with btn_col1:
        if st.button("Cancel", width='stretch', key=f"dlg_details_cancel_{app_id}"):
            st.session_state.active_details_app_id = None
            st.rerun()
    with btn_col2:
        if st.button("Save Changes", type="primary", width='stretch', key=f"dlg_details_save_{app_id}"):
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM application_statuses WHERE status_name = ?", (new_status,))
                new_status_id = cursor.fetchone()[0]
                conn.execute(
                    """
                    UPDATE applications 
                    SET company = ?, title = ?, status = ?, status_id = ?, date_submitted = ?, follow_up_date = ?, notes = ?
                    WHERE id = ?
                    """,
                    (edit_company, edit_title, new_status, new_status_id, new_date_sub, str(new_follow_date) if new_follow_date else "—", new_notes, app_id),
                )
                conn.commit()
            export_func()
            st.rerun()


@st.dialog("Generated Tailored Resume", width="small")
def show_resume_link_dialog(app_id, db_path):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT company, title, resume_file, resume_docx FROM applications WHERE id = ?",
            (app_id,)
        ).fetchone()

    if not row:
        st.warning("Application record not found.")
        if st.button("Close", key=f"dlg_link_not_found_{app_id}", width="stretch"):
            st.session_state["show_resume_link_app_id"] = None
            st.rerun()
        return

    st.markdown(
        f"""
        <div style="margin-bottom: 14px;">
            <span style="font-size: 10px; font-weight: 700; color: #94a3b8; letter-spacing: 0.05em; text-transform: uppercase;">GENERATED TAILORED RESUME</span>
            <h3 style="font-size: 18px; font-weight: 700; color: #0f172a; margin: 4px 0 0 0; padding: 0; line-height: 1.25;">{row['company']}</h3>
            <p style="font-size: 12px; color: #64748b; margin: 2px 0 0 0; padding: 0; font-weight: 500;">{row['title']}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    md_path = resolve_tailored_md_path(row["resume_file"])

    with st.container(border=True, key=f"resume_link_card_{app_id}"):
        st.markdown(
            '<div style="font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px;">Markdown File (.md)</div>',
            unsafe_allow_html=True,
        )
        if md_path and md_path.exists():
            display_rel_path = f"02_Output/{md_path.name}"
            if st.button(
                display_rel_path,
                key=f"open_md_link_btn_{app_id}",
                type="tertiary",
                help="Click to view and edit the generated Markdown resume",
            ):
                st.session_state["show_resume_link_app_id"] = None
                st.session_state["view_file_app_id"] = app_id
                st.rerun()
        else:
            st.markdown(
                '<div style="font-size: 12px; color: #94a3b8; font-style: italic; padding: 4px 0;">No generated tailored resume (.md) found for this application.</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
    if st.button("Close", key=f"dlg_resume_link_close_{app_id}", width="stretch"):
        st.session_state["show_resume_link_app_id"] = None
        st.rerun()


@st.dialog("Refine Tailored Resume", width="large")
def view_and_edit_file_dialog(app_id, db_path):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute("SELECT resume_file, resume_docx FROM applications WHERE id = ?", (app_id,))
        row = cursor.fetchone()
    
    if not row or not row[0] or row[0] == "N/A":
        st.warning("Tailored resume (.md) is not available for this application.")
        if st.button("Close", key=f"dlg_edit_empty_close_{app_id}"):
            st.session_state.view_file_app_id = None
            st.rerun()
        return

    file_path_str = row[0]
    docx_path_str = row[1] if len(row) > 1 else None
    md_path = resolve_tailored_md_path(file_path_str)

    if not md_path or not md_path.exists():
        st.warning("Tailored resume (.md) is not available for this application.")
        if st.button("Close", key=f"dlg_edit_missing_close_{app_id}"):
            st.session_state.view_file_app_id = None
            st.rerun()
        return
    try:
        content = md_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        st.error("This file appears to be a Word Document (.docx) disguised as a .md file, and cannot be edited as plain text.")
        if st.button("Close", key=f"dlg_edit_decode_close_{app_id}"):
            st.session_state.view_file_app_id = None
            st.rerun()
        return

    st.markdown(
        f'<div style="font-size: 12px; color: #64748b; margin-bottom: 8px;">File: <code style="background-color: #f1f5f9; border: 1px solid #e2e8f0; padding: 2px 6px; border-radius: 4px; color: #0f172a; font-family: monospace;">02_Output/{md_path.name}</code></div>',
        unsafe_allow_html=True,
    )
    edited_content = st.text_area("Refine Tailored Resume", value=content, height=500, label_visibility="collapsed")
    
    act_btn1, act_btn2 = st.columns([1, 1])
    with act_btn1:
        if st.button("Cancel", width='stretch', key=f"dlg_edit_cancel_{app_id}"):
            st.session_state.view_file_app_id = None
            st.rerun()
    with act_btn2:
        if st.button("Save Changes to Disk", type="primary", width='stretch', key=f"dlg_edit_save_{app_id}"):
            md_path.write_text(edited_content, encoding="utf-8")
            try:
                from src.generator import convert_md_to_docx
                target_docx = Path(docx_path_str) if (docx_path_str and docx_path_str != "N/A") else md_path.with_suffix(".docx")
                convert_md_to_docx(edited_content, target_docx)
            except Exception:
                pass
            st.session_state.view_file_app_id = None
            st.rerun()


def tracker_view(db_path, export_db_to_markdown):
    status_opts_global = get_status_options(db_path)

    if st.session_state.get("show_add_modal", False):
        add_application_dialog(db_path, export_db_to_markdown)
    elif st.session_state.get("active_details_app_id"):
        show_application_details(st.session_state.active_details_app_id, db_path, export_db_to_markdown)
    elif st.session_state.get("show_resume_link_app_id"):
        show_resume_link_dialog(st.session_state.show_resume_link_app_id, db_path)
    elif st.session_state.get("view_file_app_id"):
        view_and_edit_file_dialog(st.session_state.view_file_app_id, db_path)

    # Header matching prototype layout & HTML
    header_left, header_right = st.columns([3, 2], vertical_alignment="center")
    with header_left:
        st.markdown("""
            <div class="main-header-info">
                <h2 class="main-header-title" id="header-view-title">Application Tracker</h2>
                <p class="main-header-desc" id="header-view-desc">Monitor and manage your active corporate job prospects.</p>
            </div>
        """, unsafe_allow_html=True)
    with header_right:
        with st.container(horizontal_alignment="right", key="hdr_right_tracker"):
            if st.button("New Application", type="primary", width="content", key="hdr_add_btn"):
                add_application_dialog(db_path, export_db_to_markdown)

    st.markdown('<div class="main-header-border"></div>', unsafe_allow_html=True)

    # Main content container constrained to max-w-5xl (1024px) matching Tailor page
    with st.container(key="view_application_tracker"):
        # 1. Search & Status Dropdown Filter Container
        st.markdown('<div class="tracker-search-anchor" style="height:0; margin:0; padding:0; overflow:hidden;"></div>', unsafe_allow_html=True)
        with st.container(border=True, key="tracker_search_container"):
            f_col1, f_col2 = st.columns([2.2, 1.2], vertical_alignment="center")
            with f_col1:
                search_query = st.text_input(
                    "Search",
                    placeholder="Search company or job title...",
                    label_visibility="collapsed",
                    key="tracker_search_input"
                )
            with f_col2:
                fc1, fc2 = st.columns([1, 3.2], vertical_alignment="center")
                with fc1:
                    st.markdown('<div style="text-align: right; font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 0.05em; text-transform: uppercase;">Filter:</div>', unsafe_allow_html=True)
                with fc2:
                    status_filter = st.selectbox(
                        "Filter Status",
                        options=["All"] + status_opts_global,
                        index=0,
                        label_visibility="collapsed",
                        key="tracker_status_filter"
                    )

        # Fetch Data
        with sqlite3.connect(db_path) as conn:
            df = pd.read_sql_query(
                """
                SELECT 
                    id, company AS "COMPANY", title AS "JOB TITLE", match_score AS "MATCH SCORE", 
                    status AS "APPLICATION STATUS", date_submitted AS "DATE SUBMITTED", 
                    follow_up_date AS "FOLLOW-UP TARGET", resume_file AS "ACTIONS", notes AS "NOTES"
                FROM applications ORDER BY id DESC
                """,
                conn,
            )

        if search_query and not df.empty:
            df = df[df["COMPANY"].str.contains(search_query, case=False) | df["JOB TITLE"].str.contains(search_query, case=False)]
        if status_filter and status_filter != "All" and not df.empty:
            df = df[df["APPLICATION STATUS"] == status_filter]

        # 2. Applications List Container
        if not df.empty:
            with st.container(border=True, key="tracker_table_container"):
                with st.container(key="tracker_table_header"):
                    h_cols = st.columns([1.5, 2.3, 1.35, 1.95, 1.5, 1.7, 1.2], vertical_alignment="center")
                    headers = ["COMPANY", "JOB TITLE", "MATCH SCORE", "APPLICATION STATUS", "DATE SUBMITTED", "FOLLOW-UP TARGET", "ACTIONS"]
                    for col, title in zip(h_cols, headers):
                        col.markdown(
                            f'<div class="tracker-col-header-text" style="font-size: 11px; font-weight: 700; color: #62758e; letter-spacing: 0.05em; text-transform: uppercase;">{title}</div>',
                            unsafe_allow_html=True
                        )

                # Data Rows
                for idx, row in df.iterrows():
                    app_id = int(row["id"])
                    
                    with st.container(key=f"tracker_row_{app_id}"):
                        cols = st.columns([1.5, 2.3, 1.35, 1.95, 1.5, 1.7, 1.2], vertical_alignment="center")

                        # 1. Company
                        with cols[0]:
                            comp_label = f"**{row['COMPANY']}**"
                            if st.button(comp_label, key=f"comp_btn_{app_id}", type="tertiary"):
                                show_application_details(app_id, db_path, export_db_to_markdown)

                        # 2. Job Title
                        with cols[1]:
                            st.markdown(f'<div class="tracker-job-title" style="font-size: 13px; color: #334155; font-weight: 500; display: flex; align-items: center; min-height: 32px;">{row["JOB TITLE"]}</div>', unsafe_allow_html=True)

                        # 3. Match Score
                        with cols[2]:
                            score = int(row["MATCH SCORE"])
                            if score >= 90:
                                s_bg, s_bd, s_tx = "#dcfce7", "#86efac", "#166534"
                            elif score >= 70:
                                s_bg, s_bd, s_tx = "#fef3c7", "#fde68a", "#d97706"
                            else:
                                s_bg, s_bd, s_tx = "#f1f5f9", "#e2e8f0", "#475569"

                            st.markdown(
                                f'<div class="tracker-score-badge" style="background-color: {s_bg}; border: 1px solid {s_bd}; color: {s_tx}; padding: 0 10px; height: 32px; min-height: 32px; border-radius: 6px; font-weight: 600; font-size: 12px; display: inline-flex; align-items: center; justify-content: center; box-sizing: border-box;">{score}%</div>',
                                unsafe_allow_html=True,
                            )

                        # 4. Status Dropdown (distinct color per status, 13px normal weight matching job title)
                        with cols[3]:
                            status_opts = status_opts_global
                            current_status = row["APPLICATION STATUS"] or "Analyzed"
                            status_idx = status_opts.index(current_status) if current_status in status_opts else 0
                            status_slug = re.sub(r"[^a-z0-9]+", "_", current_status.lower()).strip("_") or "default"

                            with st.container(key=f"status_tone_{status_slug}_{app_id}"):
                                status_val = st.selectbox(
                                    "Status",
                                    options=status_opts,
                                    index=status_idx,
                                    key=f"status_sel_{app_id}",
                                    label_visibility="collapsed"
                                )
                            if status_val != current_status:
                                with sqlite3.connect(db_path) as conn:
                                    cursor = conn.cursor()
                                    cursor.execute("SELECT id FROM application_statuses WHERE status_name = ?", (status_val,))
                                    new_status_id = cursor.fetchone()[0]
                                    conn.execute("UPDATE applications SET status = ?, status_id = ? WHERE id = ?", (status_val, new_status_id, app_id))
                                    conn.commit()
                                export_db_to_markdown()
                                st.rerun()

                        # 5. Date Submitted
                        with cols[4]:
                            sub_str = row["DATE SUBMITTED"] if row["DATE SUBMITTED"] and row["DATE SUBMITTED"] != "—" else "–"
                            st.markdown(f'<div class="tracker-date-submitted" style="font-size: 13px; color: #475569; font-family: monospace; height: 32px; min-height: 32px; display: inline-flex; align-items: center;">{sub_str}</div>', unsafe_allow_html=True)

                        # 6. Follow-Up Target Date
                        with cols[5]:
                            current_follow = row["FOLLOW-UP TARGET"]
                            parsed_date = None
                            try:
                                if current_follow and str(current_follow).strip() not in ["", "—", "N/A", "None", "nan"]:
                                    dt = pd.to_datetime(current_follow, errors="coerce")
                                    if pd.notna(dt):
                                        parsed_date = dt.date()
                            except Exception:
                                pass

                            follow_val = st.date_input(
                                "Follow",
                                value=parsed_date,
                                key=f"follow_in_{app_id}",
                                format="MM/DD/YYYY",
                                label_visibility="collapsed"
                            )
                            original_follow_str = str(parsed_date) if parsed_date else "—"
                            new_follow_str = str(follow_val) if follow_val else "—"
                            if new_follow_str != original_follow_str:
                                with sqlite3.connect(db_path) as conn:
                                    conn.execute("UPDATE applications SET follow_up_date = ? WHERE id = ?", (new_follow_str, app_id))
                                    conn.commit()
                                export_db_to_markdown()
                                st.rerun()

                        # 7. Actions ("View" link & SVG trash bin button)
                        with cols[6]:
                            act_c1, act_c2 = st.columns([2.2, 1], vertical_alignment="center")
                            with act_c1:
                                if st.button("View", key=f"act_view_btn_{app_id}", type="tertiary"):
                                    show_resume_link_dialog(app_id, db_path)
                            with act_c2:
                                if st.button("\u200b", key=f"del_{app_id}", type="tertiary", help="Delete Job Application"):
                                    with sqlite3.connect(db_path) as conn:
                                        conn.execute("DELETE FROM applications WHERE id = ?", (app_id,))
                                        conn.commit()
                                    export_db_to_markdown()
                                    st.rerun()
        else:
            st.info("No applications match your current filters.")
