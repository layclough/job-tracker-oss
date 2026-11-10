import sqlite3
import pandas as pd
import streamlit as st


def dashboard_view(db_path):
    # Header matching prototype layout & HTML
    st.markdown(
        """
        <div class="main-header-info">
            <h2 class="main-header-title" id="header-view-title">Dashboard</h2>
            <p class="main-header-desc" id="header-view-desc">Overview of your job application pipeline and conversion metrics.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="main-header-border"></div>', unsafe_allow_html=True)

    # Main content container constrained to max-w-5xl (1024px) matching Tailor & Tracker pages
    with st.container(key="view_dashboard"):
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

            # Query total unique applications that reached an interview / phone screen
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(DISTINCT a.id)
                FROM applications a
                WHERE EXISTS (
                    SELECT 1 FROM application_status_history h 
                    JOIN application_statuses s ON h.new_status_id = s.id 
                    WHERE h.application_id = a.id AND s.status_name = 'Interviewing'
                ) OR a.status = 'Interviewing'
                """
            )
            total_interviewed = cursor.fetchone()[0] or 0

        # Funnel counts
        total_analyzed = len(df)
        total_tailored = int((df["ACTIONS"].notna() & (df["ACTIONS"] != "N/A") & (df["ACTIONS"] != "")).sum())
        submitted_mask = df["APPLICATION STATUS"].isin(["Applied", "Interviewing", "Rejected", "Ghosted", "Withdrawn", "Offered"])
        total_submitted = int(submitted_mask.sum())
        active_applied = int((df["APPLICATION STATUS"] == "Applied").sum())
        active_interviewing = int((df["APPLICATION STATUS"] == "Interviewing").sum())
        interview_rate = f"{(total_interviewed / total_submitted * 100):.1f}%" if total_submitted > 0 else "0.0%"

        # 1. Pipeline Summary Metric Cards
        m1, m2, m3, m4, m5 = st.columns(5)
        with m1:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span class="metric-title">TOTAL ANALYZED</span>
                        <span style="background: #f1f5f9; color: #475569; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 700;">Leads</span>
                    </div>
                    <div class="metric-value">{total_analyzed}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with m2:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span class="metric-title">TOTAL TAILORED</span>
                        <span style="background: #fef3c7; color: #d97706; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 700;">Prepared</span>
                    </div>
                    <div class="metric-value">{total_tailored}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with m3:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span class="metric-title">TOTAL APPLIED</span>
                        <span style="background: #e0e7ff; color: #4338ca; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 700;">Submitted</span>
                    </div>
                    <div class="metric-value">{total_submitted}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with m4:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span class="metric-title">INTERVIEWED</span>
                        <span style="background: #dbeafe; color: #1d4ed8; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 700;">Screens</span>
                    </div>
                    <div class="metric-value">{total_interviewed}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with m5:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span class="metric-title">INTERVIEW RATE</span>
                        <span style="background: #dcfce7; color: #15803d; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 700;">Conversion</span>
                    </div>
                    <div class="metric-value">{interview_rate}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.caption(
            f"Active Status: **{active_applied}** awaiting response · **{active_interviewing}** active in interview cycles · **{total_analyzed - total_submitted}** leads in draft or ignored"
        )

        # 2. Historical Conversion Analytics
        st.markdown(
            '<span class="presets-section-title" style="margin-top: 8px; margin-bottom: 0px;">Historical Conversion Analytics</span>',
            unsafe_allow_html=True,
        )

        with sqlite3.connect(db_path) as conn:
            conv_df = pd.read_sql_query(
                """
                SELECT 
                    CASE 
                        WHEN a.match_score >= 90 THEN '90%+'
                        WHEN a.match_score >= 80 THEN '80-89%'
                        WHEN a.match_score >= 70 THEN '70-79%'
                        ELSE '<70%' 
                    END as bucket,
                    COUNT(*) as total_apps,
                    SUM(CASE WHEN EXISTS (
                        SELECT 1 FROM application_status_history h 
                        JOIN application_statuses s ON h.new_status_id = s.id 
                        WHERE h.application_id = a.id AND s.status_name = 'Interviewing'
                    ) OR a.status = 'Interviewing' THEN 1 ELSE 0 END) as interviewed
                FROM applications a
                WHERE a.status IN ('Applied', 'Interviewing', 'Rejected', 'Ghosted', 'Withdrawn', 'Offered')
                GROUP BY bucket
                """,
                conn,
            )

            interviewed_details_df = pd.read_sql_query(
                """
                SELECT 
                    a.company AS "Company",
                    a.title AS "Role Title",
                    printf('%.1f%%', a.match_score) AS "Match Score",
                    a.date_submitted AS "Date Submitted",
                    a.status AS "Current Status",
                    a.notes AS "Notes"
                FROM applications a
                WHERE EXISTS (
                    SELECT 1 FROM application_status_history h 
                    JOIN application_statuses s ON h.new_status_id = s.id 
                    WHERE h.application_id = a.id AND s.status_name = 'Interviewing'
                ) OR a.status = 'Interviewing'
                ORDER BY a.id DESC
                """,
                conn,
            )

        # Reindex to ensure all buckets are present
        bucket_order = ["90%+", "80-89%", "70-79%", "<70%"]
        conv_df.set_index("bucket", inplace=True)
        conv_df = conv_df.reindex(bucket_order).fillna(0).astype(int)

        c1, c2, c3, c4 = st.columns(4)
        cols = [c1, c2, c3, c4]
        for idx, bucket in enumerate(bucket_order):
            row = conv_df.loc[bucket]
            total = row["total_apps"]
            interviewed = row["interviewed"]
            rate = f"{int((interviewed / total) * 100)}%" if total > 0 else "0%"

            with cols[idx]:
                st.markdown(
                    f"""
                    <div class="metric-card">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                            <span class="metric-title">{bucket} MATCH SCORE</span>
                            <span style="background: #f3e8ff; color: #7e22ce; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 700;">Conversion Rate</span>
                        </div>
                        <div class="metric-value">{rate}</div>
                        <div style="font-size: 11px; color: #64748b; margin-top: 4px;">{interviewed} interviews / {total} apps</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        with st.expander("View Detailed Conversion Breakdown & Interview Records"):
            st.markdown(
                '<div style="font-size: 12px; font-weight: 700; color: #0f172a; margin-bottom: 8px;">CONVERSION BY MATCH SCORE BUCKET (SUBMITTED APPS)</div>',
                unsafe_allow_html=True,
            )
            summary_table_df = conv_df.reset_index().rename(
                columns={
                    "bucket": "Match Score Bucket",
                    "total_apps": "Applications Submitted",
                    "interviewed": "Reached Phone Screen / Interview",
                }
            )
            summary_table_df["Conversion Rate"] = summary_table_df.apply(
                lambda r: f"{(r['Reached Phone Screen / Interview'] / r['Applications Submitted'] * 100):.1f}%" if r["Applications Submitted"] > 0 else "0.0%",
                axis=1,
            )
            st.dataframe(
                summary_table_df,
                hide_index=True,
                width="stretch",
            )

            if not interviewed_details_df.empty:
                st.markdown(
                    '<div style="font-size: 12px; font-weight: 700; color: #0f172a; margin-top: 16px; margin-bottom: 8px;">ALL INTERVIEWED APPLICATIONS (RECORD AUDIT)</div>',
                    unsafe_allow_html=True,
                )
                st.dataframe(
                    interviewed_details_df,
                    hide_index=True,
                    width="stretch",
                )

