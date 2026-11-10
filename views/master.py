import streamlit as st
from pathlib import Path
import json
import re
import uuid

MONTH_MAP = {
    "january": "01", "jan": "01",
    "february": "02", "feb": "02",
    "march": "03", "mar": "03",
    "april": "04", "apr": "04",
    "may": "05",
    "june": "06", "jun": "06",
    "july": "07", "jul": "07",
    "august": "08", "aug": "08",
    "september": "09", "sep": "09", "sept": "09",
    "october": "10", "oct": "10",
    "november": "11", "nov": "11",
    "december": "12", "dec": "12"
}

def clean_date_str(d: str) -> str:
    """Format string date e.g. 'March 2021' to '03/2021' if matched."""
    d = d.strip()
    parts = d.split()
    if len(parts) == 2 and parts[0].lower() in MONTH_MAP and parts[1].isdigit():
        return f"{MONTH_MAP[parts[0].lower()]}/{parts[1]}"
    return d

def parse_markdown_to_profile(text: str) -> dict:
    """Parse unstructured ATS markdown resume into structured profile dictionary."""
    profile = {
        "header": {
            "name": "",
            "title_subtitle": "",
            "location": "",
            "phone": "",
            "email": "",
            "linkedin": "",
            "github": "",
            "website": ""
        },
        "summary": "",
        "skills": "",
        "experiences": [],
        "side_projects": [],
        "education": [],
        "personal_achievements": []
    }
    
    if not text.strip():
        return profile

    sections = re.split(r"\n(?=##\s+)", text)
    for sec in sections:
        sec_str = sec.strip()
        lines = [l.strip() for l in sec_str.split("\n") if l.strip()]
        if not lines:
            continue
        first_line = lines[0]
        
        # Header and contact details section
        if first_line.startswith("## ") and not any(k in first_line.lower() for k in ["summary", "skill", "experience", "project", "education", "achievement"]):
            name = first_line.replace("##", "").strip()
            if name:
                profile["header"]["name"] = name
            for l in lines[1:]:
                if l.startswith("**") and l.endswith("**"):
                    profile["header"]["title_subtitle"] = l.strip("*").strip()
                elif "@" in l and "|" in l:
                    parts = [p.strip() for p in l.split("|")]
                    for p in parts:
                        if "@" in p and not p.startswith("@"):
                            profile["header"]["email"] = p
                        elif "linkedin.com" in p.lower():
                            profile["header"]["linkedin"] = p
                        elif "github.com" in p.lower():
                            profile["header"]["github"] = p
                        elif re.search(r"\+?\d[\d\s\-\(\)]{7,}\d", p):
                            profile["header"]["phone"] = p
                        elif any(c in p.lower() for c in ["http://", "https://", "www."]):
                            profile["header"]["website"] = p
                        elif any(st_name in p for st_name in ["WA", "CA", "NY", "TX", "Australia", "Remote", "Seattle"]):
                            profile["header"]["location"] = p
                            
        elif "## professional summary" in first_line.lower() or "## summary" in first_line.lower():
            profile["summary"] = "\n\n".join(lines[1:])
            
        elif "## skills" in first_line.lower():
            profile["skills"] = "\n".join(lines[1:])
            
        elif "## professional experience" in first_line.lower() or "## experience" in first_line.lower():
            role_blocks = re.split(r"\n(?=###\s+)", sec_str)[1:]
            for rb in role_blocks:
                rb_lines = [l.strip() for l in rb.strip().split("\n") if l.strip()]
                if not rb_lines:
                    continue
                h_line = rb_lines[0].replace("###", "").strip()
                company = h_line
                location = ""
                if "|" in h_line:
                    c_parts = [p.strip() for p in h_line.split("|", 1)]
                    company = c_parts[0]
                    location = c_parts[1]
                
                title = ""
                start_date = ""
                end_date = ""
                bullets = []
                
                content_idx = 1
                if (
                    len(rb_lines) > 1
                    and (rb_lines[1].startswith("**") or (rb_lines[1].startswith("*") and not rb_lines[1].startswith("* ")))
                    and rb_lines[1].endswith("*")
                ):
                    t_line = rb_lines[1].strip("*").strip()
                    content_idx = 2
                    if "|" in t_line:
                        parts = [p.strip() for p in t_line.split("|")]
                        date_cand = parts[-1]
                        if any(char.isdigit() for char in date_cand) and ("-" in date_cand or "–" in date_cand or "present" in date_cand.lower()):
                            dates_raw = re.split(r"[-–]", date_cand, maxsplit=1)
                            start_date = clean_date_str(dates_raw[0])
                            end_date = clean_date_str(dates_raw[1]) if len(dates_raw) > 1 else "Present"
                            title = " | ".join(parts[:-1])
                        else:
                            title = t_line
                    else:
                        title = t_line
                
                for b_line in rb_lines[content_idx:]:
                    if b_line.startswith("- ") or b_line.startswith("* "):
                        bullet_txt = b_line[2:].strip()
                        bullets.append(bullet_txt)
                    else:
                        bullets.append(b_line)
                        
                profile["experiences"].append({
                    "company": company,
                    "title": title,
                    "location": location,
                    "start_date": start_date,
                    "end_date": end_date,
                    "bullets": bullets
                })
                
        elif "## ai projects" in first_line.lower() or "## projects" in first_line.lower():
            proj_blocks = re.split(r"\n(?=###\s+)", sec_str)[1:]
            for pb in proj_blocks:
                pb_lines = [l.strip() for l in pb.strip().split("\n") if l.strip()]
                if not pb_lines:
                    continue
                p_title = pb_lines[0].replace("###", "").strip()
                p_bullets = []
                for p_l in pb_lines[1:]:
                    if p_l.startswith("- ") or p_l.startswith("* "):
                        p_bullets.append(p_l[2:].strip())
                    else:
                        p_bullets.append(p_l)
                profile["side_projects"].append({
                    "title": p_title,
                    "bullets": p_bullets
                })
                
        elif "## education" in first_line.lower():
            for l in lines[1:]:
                item = l[2:].strip() if (l.startswith("- ") or l.startswith("* ")) else l
                if item:
                    profile["education"].append(item)
                    
        elif "## personal achievements" in first_line.lower() or "## achievements" in first_line.lower():
            for l in lines[1:]:
                item = l[2:].strip() if (l.startswith("- ") or l.startswith("* ")) else l
                if item:
                    profile["personal_achievements"].append(item)

    return profile

def compile_profile_to_markdown(profile: dict) -> str:
    """Compile structured profile into standardized ATS Markdown format."""
    lines = []
    hdr = profile.get("header", {})
    name = hdr.get("name", "").strip() or "Candidate"
    lines.append(f"# {name} - Master Resume\n")
    lines.append(f"## {name}\n")
    
    title_sub = hdr.get("title_subtitle", "")
    contact_parts = []
    for field in ["location", "phone", "email", "linkedin", "github", "website"]:
        val = hdr.get(field, "").strip()
        if val:
            contact_parts.append(val)
    contact_line = " | ".join(contact_parts) if contact_parts else ""
    if title_sub and contact_line:
        lines.append(f"**{title_sub}**\n{contact_line}\n")
    elif title_sub:
        lines.append(f"**{title_sub}**\n")
    elif contact_line:
        lines.append(f"{contact_line}\n")
        
    lines.append("## Professional Summary\n")
    lines.append(profile.get("summary", "").strip() + "\n")
    
    lines.append("## Skills\n")
    lines.append(profile.get("skills", "").strip() + "\n")
    
    lines.append("## Professional Experience\n")
    for exp in profile.get("experiences", []):
        company = exp.get("company", "").strip()
        loc = exp.get("location", "").strip()
        if loc:
            lines.append(f"### {company} | {loc}\n")
        else:
            lines.append(f"### {company}\n")
            
        title = exp.get("title", "").strip()
        start = exp.get("start_date", "").strip()
        end = exp.get("end_date", "").strip()
        date_str = ""
        if start and end:
            date_str = f"{start} - {end}"
        elif start:
            date_str = start
        elif end:
            date_str = end
            
        if title and date_str:
            lines.append(f"*{title} | {date_str}*\n")
        elif title:
            lines.append(f"*{title}*\n")
        elif date_str:
            lines.append(f"*{date_str}*\n")
            
        for b in exp.get("bullets", []):
            b_str = b.strip()
            if not b_str:
                continue
            if b_str.startswith("- ") or b_str.startswith("* "):
                lines.append(b_str)
            elif b_str.startswith("*") and b_str.endswith("*"):
                lines.append(f"\n{b_str}\n")
            elif b_str.startswith("**Earlier career:"):
                lines.append(f"\n{b_str}\n")
            else:
                lines.append(f"- {b_str}")
        lines.append("")
        
    lines.append("## AI Projects (Built Solo)\n")
    for proj in profile.get("side_projects", []):
        p_title = proj.get("title", "").strip()
        lines.append(f"### {p_title}\n")
        for b in proj.get("bullets", []):
            b_str = b.strip()
            if not b_str:
                continue
            if b_str.startswith("- ") or b_str.startswith("* "):
                lines.append(b_str)
            else:
                lines.append(f"- {b_str}")
        lines.append("")
        
    lines.append("## Education\n")
    for edu in profile.get("education", []):
        edu_str = edu.strip()
        if not edu_str:
            continue
        if edu_str.startswith("- ") or edu_str.startswith("* "):
            lines.append(edu_str)
        else:
            lines.append(f"- {edu_str}")
    lines.append("")
    
    lines.append("## Personal Achievements\n")
    for ach in profile.get("personal_achievements", []):
        ach_str = ach.strip()
        if not ach_str:
            continue
        if ach_str.startswith("- ") or ach_str.startswith("* "):
            lines.append(ach_str)
        else:
            lines.append(f"- {ach_str}")
    lines.append("")
    
    return "\n".join(lines).strip() + "\n"

def load_or_seed_profile(json_path: Path, md_path: Path) -> dict:
    """Load profile from JSON, or seed from markdown/defaults if JSON does not exist."""
    if json_path.exists():
        try:
            return json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Fallback to markdown file if present
    if md_path.exists():
        try:
            prof = parse_markdown_to_profile(md_path.read_text(encoding="utf-8"))
            json_path.write_text(json.dumps(prof, indent=2), encoding="utf-8")
            return prof
        except Exception:
            pass
            
    # Fallback to template files if present
    template_json = json_path.parent / "templates" / "master_profile.template.json"
    template_md = json_path.parent / "templates" / "Master_Resume.template.md"

    if template_json.exists():
        try:
            prof = json.loads(template_json.read_text(encoding="utf-8"))
            json_path.write_text(json.dumps(prof, indent=2), encoding="utf-8")
            if not md_path.exists() and template_md.exists():
                md_path.write_text(template_md.read_text(encoding="utf-8"), encoding="utf-8")
            return prof
        except Exception:
            pass

    # Default empty profile seed
    default_profile = {
        "header": {
            "name": "",
            "title_subtitle": "",
            "location": "",
            "phone": "",
            "email": "",
            "linkedin": "",
            "github": "",
            "website": ""
        },
        "summary": "",
        "skills": "",
        "experiences": [],
        "side_projects": [],
        "education": [],
        "personal_achievements": []
    }
    json_path.write_text(json.dumps(default_profile, indent=2), encoding="utf-8")
    return default_profile

def master_view(master_resume_path: Path):
    json_path = master_resume_path.parent / "master_profile.json"
    
    # Initialize session state profile
    if "master_profile" not in st.session_state:
        profile_data = load_or_seed_profile(json_path, master_resume_path)
        # Ensure internal stable IDs for dynamic list widgets
        for exp in profile_data.get("experiences", []):
            if "_id" not in exp:
                exp["_id"] = uuid.uuid4().hex[:8]
        for proj in profile_data.get("side_projects", []):
            if "_id" not in proj:
                proj["_id"] = uuid.uuid4().hex[:8]
        st.session_state["master_profile"] = profile_data

    profile = st.session_state["master_profile"]

    def sync_from_widgets():
        """Sync all current input widgets into session_state master_profile."""
        prof = st.session_state["master_profile"]
        
        # Header
        if "m_hdr_name" in st.session_state:
            prof["header"]["name"] = st.session_state["m_hdr_name"]
            prof["header"]["title_subtitle"] = st.session_state.get("m_hdr_title", "")
            prof["header"]["location"] = st.session_state.get("m_hdr_location", "")
            prof["header"]["phone"] = st.session_state.get("m_hdr_phone", "")
            prof["header"]["email"] = st.session_state.get("m_hdr_email", "")
            prof["header"]["linkedin"] = st.session_state.get("m_hdr_linkedin", "")
            prof["header"]["github"] = st.session_state.get("m_hdr_github", "")
            prof["header"]["website"] = st.session_state.get("m_hdr_website", "")
            
        # Summary & Skills
        if "m_summary" in st.session_state:
            prof["summary"] = st.session_state["m_summary"]
        if "m_skills" in st.session_state:
            prof["skills"] = st.session_state["m_skills"]
            
        # Education & Achievements
        if "m_education" in st.session_state:
            prof["education"] = [l.strip() for l in st.session_state["m_education"].split("\n") if l.strip()]
        if "m_achievements" in st.session_state:
            prof["personal_achievements"] = [l.strip() for l in st.session_state["m_achievements"].split("\n") if l.strip()]
            
        # Experiences
        for exp in prof.get("experiences", []):
            eid = exp["_id"]
            if f"m_exp_comp_{eid}" in st.session_state:
                exp["company"] = st.session_state[f"m_exp_comp_{eid}"]
                exp["title"] = st.session_state.get(f"m_exp_title_{eid}", "")
                exp["location"] = st.session_state.get(f"m_exp_loc_{eid}", "")
                exp["start_date"] = st.session_state.get(f"m_exp_start_{eid}", "")
                exp["end_date"] = st.session_state.get(f"m_exp_end_{eid}", "")
                b_raw = st.session_state.get(f"m_exp_bullets_{eid}", "")
                exp["bullets"] = [b.strip() for b in b_raw.split("\n") if b.strip()]
                
        # Side Projects
        for proj in prof.get("side_projects", []):
            pid = proj["_id"]
            if f"m_proj_title_{pid}" in st.session_state:
                proj["title"] = st.session_state[f"m_proj_title_{pid}"]
                pb_raw = st.session_state.get(f"m_proj_bullets_{pid}", "")
                proj["bullets"] = [b.strip() for b in pb_raw.split("\n") if b.strip()]

    def execute_save():
        """Persist profile to JSON and compile to Markdown."""
        sync_from_widgets()
        prof = st.session_state["master_profile"]
        
        # Prepare clean JSON without internal _id keys
        clean_profile = {
            "header": prof.get("header", {}),
            "summary": prof.get("summary", ""),
            "skills": prof.get("skills", ""),
            "experiences": [
                {
                    "company": e.get("company", ""),
                    "title": e.get("title", ""),
                    "location": e.get("location", ""),
                    "start_date": e.get("start_date", ""),
                    "end_date": e.get("end_date", ""),
                    "bullets": e.get("bullets", [])
                }
                for e in prof.get("experiences", [])
            ],
            "side_projects": [
                {
                    "title": p.get("title", ""),
                    "bullets": p.get("bullets", [])
                }
                for p in prof.get("side_projects", [])
            ],
            "education": prof.get("education", []),
            "personal_achievements": prof.get("personal_achievements", [])
        }
        
        # 1. Write structured JSON
        json_path.write_text(json.dumps(clean_profile, indent=2), encoding="utf-8")
        
        # 2. Compile ATS Markdown
        compiled_md = compile_profile_to_markdown(clean_profile)
        
        # 3. Overwrite 00_Data/Master_resume.md and any aliases
        master_resume_path.write_text(compiled_md, encoding="utf-8")
        lowercase_path = master_resume_path.parent / "Master_resume.md"
        if lowercase_path != master_resume_path:
            lowercase_path.write_text(compiled_md, encoding="utf-8")
            
        st.session_state["save_success_flag"] = True

    # Page Header
    header_left, header_right = st.columns([3, 2], vertical_alignment="center")
    with header_left:
        st.subheader("Master Resume Profile")
    with header_right:
        with st.container(horizontal_alignment="right", key="hdr_right_master"):
            if st.button("Save Master Profile", type="primary", key="top_save_profile_btn"):
                execute_save()

    st.markdown('<div class="main-header-border"></div>', unsafe_allow_html=True)

    # Main Structured Section Editor
    with st.container(key="view_master_resume"):
        if st.session_state.get("save_success_flag"):
            st.success("Master profile saved and synced to Master_resume.md")
            st.session_state["save_success_flag"] = False

        st.session_state.setdefault("master_all_expanded", True)
        st.session_state.setdefault("master_expander_nonce", 0)
        is_expanded = st.session_state["master_all_expanded"]
        zw_suffix = "\u200b" * (st.session_state["master_expander_nonce"] % 2)

        with st.container(horizontal_alignment="right", key="master_expand_toggle_row"):
            toggle_label = "Collapse All" if is_expanded else "Expand All"
            if st.button(toggle_label, key="btn_toggle_master_expanders", width="content"):
                sync_from_widgets()
                st.session_state["master_all_expanded"] = not is_expanded
                st.session_state["master_expander_nonce"] += 1
                st.rerun()

        # 1. Header and Contact Details
        with st.expander(f"Header and Contact Details{zw_suffix}", expanded=is_expanded):
            hdr = profile.get("header", {})
            h_c1, h_c2 = st.columns(2)
            with h_c1:
                st.text_input("Name", value=hdr.get("name", ""), key="m_hdr_name")
            with h_c2:
                st.text_input("Title Subtitle", value=hdr.get("title_subtitle", ""), key="m_hdr_title")
                
            h_c3, h_c4 = st.columns(2)
            with h_c3:
                st.text_input("Location", value=hdr.get("location", ""), key="m_hdr_location")
            with h_c4:
                st.text_input("Phone", value=hdr.get("phone", ""), key="m_hdr_phone")
                
            h_c5, h_c6 = st.columns(2)
            with h_c5:
                st.text_input("Email", value=hdr.get("email", ""), key="m_hdr_email")
            with h_c6:
                st.text_input("LinkedIn", value=hdr.get("linkedin", ""), key="m_hdr_linkedin")
                
            h_c7, h_c8 = st.columns(2)
            with h_c7:
                st.text_input("GitHub", value=hdr.get("github", ""), key="m_hdr_github")
            with h_c8:
                st.text_input("Website URL", value=hdr.get("website", ""), key="m_hdr_website")

        # 2. Professional Summary
        with st.expander(f"Professional Summary{zw_suffix}", expanded=is_expanded):
            st.text_area(
                "Professional Summary",
                value=profile.get("summary", ""),
                height=140,
                key="m_summary",
                label_visibility="collapsed"
            )

        # 3. Core Skills and Competencies
        with st.expander(f"Core Skills and Competencies{zw_suffix}", expanded=is_expanded):
            st.text_area(
                "Core Skills and Competencies",
                value=profile.get("skills", ""),
                height=200,
                key="m_skills",
                label_visibility="collapsed"
            )

        # 4. Professional Experience
        with st.expander(f"Professional Experience{zw_suffix}", expanded=is_expanded):
            experiences = profile.get("experiences", [])
            for idx, exp in enumerate(experiences):
                eid = exp["_id"]
                company_label = exp.get("company", "").strip() or f"Role {idx + 1}"
                title_label = exp.get("title", "").strip()
                heading_text = f"Role {idx + 1}: {company_label}" + (f" — {title_label}" if title_label else "")
                
                with st.container(border=True):
                    st.markdown(f"**{heading_text}**")
                    
                    e_col1, e_col2, e_col3 = st.columns([1.5, 2, 1.2])
                    with e_col1:
                        st.text_input("Company Name", value=exp.get("company", ""), key=f"m_exp_comp_{eid}")
                    with e_col2:
                        st.text_input("Role Title", value=exp.get("title", ""), key=f"m_exp_title_{eid}")
                    with e_col3:
                        st.text_input("Location", value=exp.get("location", ""), key=f"m_exp_loc_{eid}")
                        
                    e_col4, e_col5 = st.columns(2)
                    with e_col4:
                        st.text_input("Start Date", value=exp.get("start_date", ""), key=f"m_exp_start_{eid}")
                    with e_col5:
                        st.text_input("End Date", value=exp.get("end_date", ""), key=f"m_exp_end_{eid}")
                        
                    st.text_area(
                        "Bullet Points (one bullet per line)",
                        value="\n".join(exp.get("bullets", [])),
                        height=160,
                        key=f"m_exp_bullets_{eid}"
                    )
            
            exp_btn_col1, exp_btn_col2 = st.columns(2)
            with exp_btn_col1:
                if st.button("Add Role", key="btn_add_role"):
                    sync_from_widgets()
                    profile["experiences"].append({
                        "company": "",
                        "title": "",
                        "location": "",
                        "start_date": "",
                        "end_date": "",
                        "bullets": [],
                        "_id": uuid.uuid4().hex[:8]
                    })
                    st.rerun()
            with exp_btn_col2:
                if st.button("Remove Role", key="btn_remove_role", disabled=len(experiences) <= 1):
                    sync_from_widgets()
                    if len(profile["experiences"]) > 1:
                        profile["experiences"].pop()
                    st.rerun()

        # 5. AI and Side Projects
        with st.expander(f"AI and Side Projects{zw_suffix}", expanded=is_expanded):
            side_projects = profile.get("side_projects", [])
            for p_idx, proj in enumerate(side_projects):
                pid = proj["_id"]
                p_heading = proj.get("title", "").strip() or f"Project {p_idx + 1}"
                
                with st.container(border=True):
                    st.markdown(f"**Project {p_idx + 1}: {p_heading}**")
                    st.text_input("Project Title", value=proj.get("title", ""), key=f"m_proj_title_{pid}")
                    st.text_area(
                        "Bullet Points (one bullet per line)",
                        value="\n".join(proj.get("bullets", [])),
                        height=120,
                        key=f"m_proj_bullets_{pid}"
                    )
                    
            p_btn_col1, p_btn_col2 = st.columns(2)
            with p_btn_col1:
                if st.button("Add Project", key="btn_add_project"):
                    sync_from_widgets()
                    profile["side_projects"].append({
                        "title": "",
                        "bullets": [],
                        "_id": uuid.uuid4().hex[:8]
                    })
                    st.rerun()
            with p_btn_col2:
                if st.button("Remove Project", key="btn_remove_project", disabled=len(side_projects) <= 1):
                    sync_from_widgets()
                    if len(profile["side_projects"]) > 1:
                        profile["side_projects"].pop()
                    st.rerun()

        # 6. Education and Credentials
        with st.expander(f"Education and Credentials{zw_suffix}", expanded=is_expanded):
            edu_items = profile.get("education", [])
            st.text_area(
                "Education and Credentials (one item per line)",
                value="\n".join(edu_items),
                height=100,
                key="m_education",
                label_visibility="collapsed"
            )

        # 7. Personal Achievements
        with st.expander(f"Personal Achievements{zw_suffix}", expanded=is_expanded):
            ach_items = profile.get("personal_achievements", [])
            st.text_area(
                "Personal Achievements (one item per line)",
                value="\n".join(ach_items),
                height=120,
                key="m_achievements",
                label_visibility="collapsed"
            )

        # Bottom Actions
        st.markdown('<div style="height: 12px;"></div>', unsafe_allow_html=True)
        if st.button("Save Master Profile", type="primary", key="bottom_save_profile_btn"):
            execute_save()
