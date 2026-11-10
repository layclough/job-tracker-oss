import json
from pathlib import Path
import re
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor
from src.llm_config import get_llm_client_and_model, MAX_JD_CHARS


def resolve_master_resume_path(custom_path: Path | str | None = None) -> Path:
    """Resolves and validates the Master Resume file path across standard project locations."""
    candidates = []
    if custom_path:
        candidates.append(Path(custom_path))

    base_repo_dir = Path(__file__).resolve().parent.parent
    candidates.extend([
        Path("00_Data/Master_resume.md"),
        Path("00_Data/Master_Resume.md"),
        Path("Master_resume.md"),
        Path("Master_Resume.md"),
        base_repo_dir / "00_Data" / "Master_resume.md",
        base_repo_dir / "00_Data" / "Master_Resume.md",
    ])

    for candidate in candidates:
        if candidate and candidate.exists() and candidate.is_file():
            return candidate.resolve()

    searched_paths = [str(c) for c in candidates if c is not None]
    raise FileNotFoundError(
        f"Master Resume not found. Searched in: {searched_paths[:4]}"
    )


def parse_markdown_to_profile(text: str) -> dict:
    """Parses markdown ATS resume into structured profile dictionary if JSON is missing."""
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
        lines = [line.strip() for line in sec_str.split("\n") if line.strip()]
        if not lines:
            continue
        first_line = lines[0]

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
                    c_parts = h_line.split("|", 1)
                    company = c_parts[0].strip()
                    location = c_parts[1].strip()

                title, start_date, end_date = "", "", ""
                bullets = []
                for b_line in rb_lines[1:]:
                    is_styled_role = (
                        b_line.startswith("**")
                        or (b_line.startswith("*") and not b_line.startswith("* "))
                    )
                    is_earlier = b_line.lower().startswith("**earlier") or b_line.lower().startswith("*earlier")
                    if is_styled_role and "|" in b_line and not is_earlier:
                        raw_t = b_line.strip("*").strip()
                        t_parts = raw_t.split("|")
                        title = t_parts[0].strip()
                        if len(t_parts) > 1:
                            dates = t_parts[-1].strip()
                            if "-" in dates:
                                d_split = dates.split("-", 1)
                                start_date = d_split[0].strip()
                                end_date = d_split[1].strip()
                            else:
                                start_date = dates
                    elif b_line.startswith("- ") or b_line.startswith("* "):
                        bullets.append(b_line[2:].strip())
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


def load_master_profile(custom_path: Path | str | None = None) -> dict:
    """Loads candidate profile from master_profile.json, falling back to Master_resume.md."""
    base_repo_dir = Path(__file__).resolve().parent.parent
    json_candidates = [
        Path(custom_path) if custom_path and str(custom_path).endswith(".json") else None,
        Path("00_Data/master_profile.json"),
        base_repo_dir / "00_Data" / "master_profile.json",
    ]
    for cand in json_candidates:
        if cand and cand.exists():
            try:
                return json.loads(cand.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"[Warning] Failed to read {cand}: {e}")

    # Fallback to Master_resume.md
    resume_path = resolve_master_resume_path(custom_path)
    resume_md = resume_path.read_text(encoding="utf-8")
    return parse_markdown_to_profile(resume_md)


def clean_markdown_output(raw_text: str) -> str:
    """Sanitizes LLM markdown output to ensure clean, raw markdown."""
    if not raw_text:
        return ""

    # Strip <think>...</think> tags
    text = re.sub(r"<think>[\s\S]*?</think>", "", raw_text, flags=re.IGNORECASE).strip()

    # Strip code block wrappers
    text = re.sub(r"^```(?:markdown)?\s*\n?", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\n?```\s*$", "", text).strip()
    if text.endswith("```"):
        text = text[:-3].strip()

    return text.strip()


def add_formatted_text(paragraph, text: str, base_size: Pt = Pt(10), font_name: str = "Calibri"):
    """Parses markdown bold (**text**) and italics (*text*) into native Word runs."""
    tokens = re.split(r'(\*\*.*?\*\*|\*.*?\*)', text)
    for token in tokens:
        if not token:
            continue
        if token.startswith('**') and token.endswith('**'):
            run = paragraph.add_run(token[2:-2])
            run.bold = True
            run.font.name = font_name
            run.font.size = base_size
            run.font.color.rgb = RGBColor(0x11, 0x18, 0x27)
        elif token.startswith('*') and token.endswith('*'):
            run = paragraph.add_run(token[1:-1])
            run.italic = True
            run.font.name = font_name
            run.font.size = base_size
            run.font.color.rgb = RGBColor(0x37, 0x41, 0x51)
        else:
            run = paragraph.add_run(token)
            run.font.name = font_name
            run.font.size = base_size
            run.font.color.rgb = RGBColor(0x37, 0x41, 0x51)


def normalize_experience_markdown(exp_md: str) -> str:
    """Ensures role/title lines under Professional Experience are formatted as italic (*Role | Dates*) and not bold."""
    out_lines = []
    after_company_header = False
    for line in exp_md.split("\n"):
        stripped = line.strip()
        if not stripped:
            out_lines.append("")
            continue
        if stripped.startswith("### "):
            out_lines.append(stripped)
            after_company_header = True
            continue
        if stripped.startswith("- ") or (stripped.startswith("* ") and not stripped.endswith("*")):
            after_company_header = False
            # Fix lowercase "**from 0 to 1" at the start of bold bullet headings
            fixed_bullet = re.sub(r"^([\-\*]\s+\*\*)from 0 to 1\b", r"\g<1>0-to-1", stripped)
            out_lines.append(fixed_bullet)
            continue
        is_earlier = (
            stripped.lower().startswith("**earlier")
            or stripped.lower().startswith("*earlier")
            or stripped.lower().startswith("earlier career")
        )
        if not is_earlier and (after_company_header or ("|" in stripped and re.search(r"\d{4}", stripped))):
            after_company_header = False
            clean_role = re.sub(r"\*+", "", stripped).strip()
            out_lines.append(f"*{clean_role}*")
        else:
            out_lines.append(stripped)
    return "\n".join(out_lines).strip()


def convert_md_to_docx(md_text: str, output_path: Path):
    """Converts tailored Markdown into a beautifully formatted Word Document matching design specs."""
    doc = Document()

    # Page margins: 0.5 inches on all sides for a tight 2-page fit
    for section in doc.sections:
        section.top_margin = Inches(0.5)
        section.bottom_margin = Inches(0.5)
        section.left_margin = Inches(0.5)
        section.right_margin = Inches(0.5)

    # Set document normal font to Calibri and default left alignment with tight line spacing
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Calibri'
    font.size = Pt(10)
    font.color.rgb = RGBColor(0x1F, 0x29, 0x37)
    style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    style.paragraph_format.space_before = Pt(0)
    style.paragraph_format.space_after = Pt(0)
    style.paragraph_format.line_spacing = 1.0

    lines = md_text.split('\n')
    in_header = True
    current_section = ""
    after_company_header = False

    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue

        # Document Header Title (# Header): 17 pt Bold, Centered
        if line_str.startswith('# ') and in_header:
            clean_title = line_str[2:].strip()
            # Remove any trailing descriptor e.g. "- Master PM Resume"
            if " - " in clean_title:
                clean_title = clean_title.split(" - ")[0].strip()

            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.line_spacing = 1.0
            run = p.add_run(clean_title)
            run.bold = True
            run.font.name = 'Calibri'
            run.font.size = Pt(17)
            run.font.color.rgb = RGBColor(0x11, 0x18, 0x27)

        # Section Headers (## Header): 10.5 pt Bold Uppercase (Calibri), Left-aligned
        elif line_str.startswith('## '):
            clean_sec = line_str[3:].strip()
            # Skip if this is a redundant name/contact header
            if clean_sec.lower() in ("contact", "profile", "personal information", "header"):
                continue

            in_header = False
            current_section = clean_sec.lower()
            after_company_header = False

            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.space_before = Pt(6)
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.line_spacing = 1.0
            run = p.add_run(clean_sec.upper())
            run.bold = True
            run.font.name = 'Calibri'
            run.font.size = Pt(10.5)
            run.font.color.rgb = RGBColor(0x11, 0x18, 0x27)

        # Header Subtitle / Contact lines (centered before first section header, no gap between Title and Contact)
        elif in_header:
            if "· @" in line_str:
                continue
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.line_spacing = 1.0
            is_contact_line = ("@" in line_str and "|" in line_str) or "linkedin.com" in line_str.lower()
            if is_contact_line:
                p.paragraph_format.space_after = Pt(4)
                add_formatted_text(p, line_str, base_size=Pt(9))
            else:
                p.paragraph_format.space_after = Pt(0)
                add_formatted_text(p, line_str, base_size=Pt(10))

        # Subheadings (### Header): 10 pt Bold, Left-aligned
        elif line_str.startswith('### '):
            clean_sub = line_str[4:].strip()
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(1)
            p.paragraph_format.line_spacing = 1.0
            run = p.add_run(clean_sub)
            run.bold = True
            run.font.name = 'Calibri'
            run.font.size = Pt(10)
            run.font.color.rgb = RGBColor(0x1F, 0x29, 0x37)
            after_company_header = ("experience" in current_section)

        # Bullet Items (- Item or * Item): 10 pt, Left-aligned, single-spaced with 1.5 pt after
        elif line_str.startswith('- ') or (line_str.startswith('* ') and not line_str.endswith('*')):
            after_company_header = False
            clean_bullet = re.sub(r'^[\-\*]\s+', '', line_str)
            p = doc.add_paragraph(style='List Bullet')
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(1.5)
            p.paragraph_format.line_spacing = 1.0
            add_formatted_text(p, clean_bullet, base_size=Pt(10))

        # Regular Paragraphs / Role dates lines (Left-aligned)
        else:
            is_earlier = (
                line_str.lower().startswith("**earlier")
                or line_str.lower().startswith("*earlier")
                or line_str.lower().startswith("earlier career")
            )
            is_role_line = (
                "experience" in current_section
                and not is_earlier
                and (after_company_header or ("|" in line_str and re.search(r"\d{4}", line_str)))
            )
            if is_role_line:
                after_company_header = False
                clean_role = re.sub(r"\*+", "", line_str).strip()
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                p.paragraph_format.space_before = Pt(0)
                p.paragraph_format.space_after = Pt(2)
                p.paragraph_format.line_spacing = 1.0
                run = p.add_run(clean_role)
                run.bold = False
                run.italic = True
                run.font.name = 'Calibri'
                run.font.size = Pt(10)
                run.font.color.rgb = RGBColor(0x37, 0x41, 0x51)
            else:
                after_company_header = False
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                p.paragraph_format.space_before = Pt(0)
                p.paragraph_format.space_after = Pt(3)
                p.paragraph_format.line_spacing = 1.0
                add_formatted_text(p, line_str, base_size=Pt(10))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))


def format_side_projects_markdown(projects: list[dict]) -> str:
    """Formats side projects list into standardized markdown."""
    parts = []
    for proj in projects:
        p_title = proj.get("title", "").strip()
        if p_title:
            parts.append(f"### {p_title}")
        for b in proj.get("bullets", []):
            b_str = b.strip()
            if not b_str:
                continue
            if b_str.startswith("- ") or b_str.startswith("* "):
                parts.append(b_str)
            else:
                parts.append(f"- {b_str}")
        parts.append("")
    return "\n".join(parts).strip()


def format_list_markdown(items: list[str]) -> str:
    """Formats string list into bulleted markdown."""
    parts = []
    for item in items:
        i_str = item.strip()
        if not i_str:
            continue
        if i_str.startswith("- ") or i_str.startswith("* "):
            parts.append(i_str)
        else:
            parts.append(f"- {i_str}")
    return "\n".join(parts).strip()


def format_master_experience_for_llm(experiences: list[dict]) -> str:
    """Formats experience pool into readable text for Gemma to prune and reorder."""
    parts = []
    for exp in experiences:
        company = exp.get("company", "").strip()
        loc = exp.get("location", "").strip()
        title = exp.get("title", "").strip()
        start = exp.get("start_date", "").strip()
        end = exp.get("end_date", "").strip()

        header = f"### {company} | {loc}" if loc else f"### {company}"
        date_str = f"{start} - {end}" if start and end else (start or end)
        title_line = f"*{title} | {date_str}*" if title and date_str else f"*{title or date_str}*"

        parts.append(header)
        parts.append(title_line)
        for b in exp.get("bullets", []):
            b_str = b.strip()
            if not b_str:
                continue
            if b_str.startswith("- ") or b_str.startswith("* "):
                parts.append(b_str)
            elif b_str.startswith("*") and b_str.endswith("*"):
                parts.append(f"\n{b_str}\n")
            elif b_str.startswith("**Earlier career:"):
                parts.append(f"\n{b_str}\n")
            else:
                parts.append(f"- {b_str}")
        parts.append("")
    return "\n".join(parts).strip()


def generate_tailored_resume(
    jd_text: str,
    master_resume_path: Path | str | None = None,
    company: str = "Target Company",
    title: str = "Target Role",
    progress_callback=None
) -> str:
    """Generates tailored resume with local Gemma 4 (31B) for dynamic sections and programmatically combines with static anchors."""
    if progress_callback:
        progress_callback("loading", "Loading Master Profile and static sections...", 10)

    profile = load_master_profile(master_resume_path)
    hdr = profile.get("header", {})
    name = hdr.get("name", "").strip() or "Candidate"

    # Build target subtitle
    clean_title = title.strip()
    if clean_title and clean_title not in ("Role", "Target Role", "Position"):
        if "|" in clean_title:
            target_subtitle = clean_title
        else:
            target_subtitle = f"{clean_title} | B2B SaaS | AI Products and Platforms"
    else:
        target_subtitle = hdr.get("title_subtitle", "").strip() or "Product Manager"

    # Build contact line
    contact_parts = []
    for field in ["location", "phone", "email", "linkedin", "github", "website"]:
        val = hdr.get(field, "").strip()
        if val:
            contact_parts.append(val)
    contact_line = " | ".join(contact_parts)

    master_summary = profile.get("summary", "").strip()
    master_skills = profile.get("skills", "").strip()
    master_exp_text = format_master_experience_for_llm(profile.get("experiences", []))

    # Static sections
    side_projects_md = format_side_projects_markdown(profile.get("side_projects", []))
    education_md = format_list_markdown(profile.get("education", []))
    achievements_md = format_list_markdown(profile.get("personal_achievements", []))

    system_prompt = (
        "You are an elite executive resume tailor. Your job is to tailor the candidate's Summary, Skills, and Experience "
        "to the target Job Description while enforcing strict anti-fabrication rules. Keep internal thinking ultra-concise "
        "(under 120 words total; do NOT restate rules or draft bullets in thinking). Output ONLY the three requested tagged sections."
    )

    prompt = f"""INSTRUCTIONS:
Generate ONLY the three tagged dynamic sections below. Do NOT output a header, side projects, education, or personal achievements.
THINKING CONSTRAINT: Keep internal reasoning brief (under 120 words). Do NOT repeat these instructions or summarize the JD; briefly note which bullets to prioritize, then immediately output <<<SUMMARY>>>.

<<<SUMMARY>>>
Write a high-impact, professional 3-4 sentence summary tailored directly to the target role and company. Emphasize the candidate's relevant enterprise B2B SaaS leadership, AI products/platforms, software engineering foundation, and cross-functional delivery. Highlight transferable competencies that match the target role.

<<<SKILLS>>>
Provide the categorized skills matrix formatted as markdown bullet points (e.g., - **Product Management:** ..., - **AI & Platforms:** ...), reordered and prioritized to highlight the skills most critical to this target job description. Include ONLY skills the candidate actually possesses in their profile.

<<<EXPERIENCE>>>
Output the candidate's professional experience.
- Keep the company headers (### Company | Location) and italicized title/date lines (*Title | Dates*) accurate to the candidate profile (use *italic* and NOT **bold** for the Role/Title and Dates line).
- Under each role, select, prune, and reorder the existing bullet points so achievements most relevant to the target company and role appear first.
- STRICT LIMIT: Total across all roles combined MUST be between 20 and 24 bullet points (to ensure an exact 2-page fit).
- ZERO FABRICATION: Do not invent new tools, metrics, employers, or dates. Every bullet must be grounded in the candidate's actual accomplishments.
- PHRASING REQUIREMENT: In prose sentences, use the phrasing "from 0 to 1" when describing greenfield work (never "0->1"), but keep bold bullet labels/skill titles capitalized (e.g., "**0-to-1 Platform:**" or "0-to-1 Product Development").

OUTPUT FORMAT:
Return ONLY the three tagged blocks starting with <<<SUMMARY>>>:
<<<SUMMARY>>>
...
<<<SKILLS>>>
...
<<<EXPERIENCE>>>
...

Candidate Master Profile:
---
CURRENT SUMMARY:
{master_summary}

CURRENT SKILLS:
{master_skills}

CURRENT EXPERIENCE POOL:
{master_exp_text}
---

Target Job Description:
Company: {company}
Role: {title}
{jd_text[:MAX_JD_CHARS]}
"""

    if progress_callback:
        progress_callback("thinking", f"Planning achievement selection for {company} ({title})...", 20)

    client, model_name = get_llm_client_and_model(timeout=180.0)

    stream = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1,
        max_tokens=3500,
        stream=True
    )

    content_chunks = []
    current_stage = "thinking"
    last_company_seen = ""
    companies_count = 0
    reasoning_chunks = 0
    last_thinking_pct = 20

    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        r_piece = getattr(delta, "reasoning_content", None) or ""
        if r_piece and current_stage == "thinking" and progress_callback:
            reasoning_chunks += 1
            if reasoning_chunks % 25 == 0:
                new_pct = min(35, 20 + (reasoning_chunks // 25))
                if new_pct > last_thinking_pct:
                    last_thinking_pct = new_pct
                    progress_callback(
                        "thinking",
                        f"Planning achievement selection for {company} ({title})...",
                        new_pct
                    )

        piece = getattr(delta, "content", None) or ""
        if piece:
            content_chunks.append(piece)
            if progress_callback:
                joined = "".join(content_chunks)
                if "<<<EXPERIENCE>>>" in joined:
                    exp_part = joined.split("<<<EXPERIENCE>>>", 1)[1]
                    comp_matches = re.findall(r"###\s+([^\n|]+)", exp_part)
                    if comp_matches:
                        latest_comp = comp_matches[-1].strip()
                        if latest_comp != last_company_seen:
                            last_company_seen = latest_comp
                            companies_count += 1
                            pct = min(90, 68 + companies_count * 3)
                            progress_callback(
                                "experience",
                                f"Tailoring Professional Experience — {latest_comp}...",
                                pct
                            )
                    elif current_stage != "experience":
                        current_stage = "experience"
                        progress_callback("experience", "Tailoring Professional Experience...", 68)
                elif "<<<SKILLS>>>" in joined and current_stage not in ("skills", "experience"):
                    current_stage = "skills"
                    progress_callback("skills", "Prioritizing and categorizing Skills Matrix...", 54)
                elif "<<<SUMMARY>>>" in joined and current_stage == "thinking":
                    current_stage = "summary"
                    progress_callback("summary", "Drafting tailored Professional Summary...", 38)

    if progress_callback:
        progress_callback("assembling", "Assembling static sections and exporting .md and .docx...", 95)

    raw_output = "".join(content_chunks)
    clean_text = clean_markdown_output(raw_output)

    # Extract dynamic sections from tags
    tailored_summary = master_summary
    tailored_skills = master_skills
    tailored_experience = master_exp_text

    sum_match = re.search(r"<<<SUMMARY>>>(.*?)(?:<<<SKILLS>>>|$)", clean_text, re.DOTALL)
    if sum_match and sum_match.group(1).strip():
        tailored_summary = sum_match.group(1).strip()

    skills_match = re.search(r"<<<SKILLS>>>(.*?)(?:<<<EXPERIENCE>>>|$)", clean_text, re.DOTALL)
    if skills_match and skills_match.group(1).strip():
        tailored_skills = skills_match.group(1).strip()

    exp_match = re.search(r"<<<EXPERIENCE>>>(.*?)$", clean_text, re.DOTALL)
    if exp_match and exp_match.group(1).strip():
        tailored_experience = exp_match.group(1).strip()

    # Fallback if model used markdown headers instead of tags
    if not sum_match and "## professional summary" in clean_text.lower():
        parts = re.split(r"\n(?=##\s+)", clean_text)
        for p in parts:
            p_strip = p.strip()
            if "## professional summary" in p_strip.lower() or "## summary" in p_strip.lower():
                tailored_summary = "\n".join(p_strip.split("\n")[1:]).strip()
            elif "## skills" in p_strip.lower():
                tailored_skills = "\n".join(p_strip.split("\n")[1:]).strip()
            elif "## professional experience" in p_strip.lower() or "## experience" in p_strip.lower():
                tailored_experience = "\n".join(p_strip.split("\n")[1:]).strip()

    # Clean any accidental residual tags
    tailored_summary = re.sub(r"<<<[A-Z]+>>>", "", tailored_summary).strip()
    tailored_skills = re.sub(r"<<<[A-Z]+>>>", "", tailored_skills).strip()
    tailored_experience = re.sub(r"<<<[A-Z]+>>>", "", tailored_experience).strip()

    # Clean residual headers in dynamic sections if LLM prepended them
    if tailored_summary.lower().startswith("## professional summary") or tailored_summary.lower().startswith("## summary"):
        tailored_summary = "\n".join(tailored_summary.split("\n")[1:]).strip()
    if tailored_skills.lower().startswith("## skills"):
        tailored_skills = "\n".join(tailored_skills.split("\n")[1:]).strip()
    tailored_skills = re.sub(r"(:\*\*\s+)from 0 to 1 Product Development", r"\g<1>0-to-1 Product Development", tailored_skills)
    if tailored_experience.lower().startswith("## professional experience") or tailored_experience.lower().startswith("## experience"):
        tailored_experience = "\n".join(tailored_experience.split("\n")[1:]).strip()

    tailored_experience = normalize_experience_markdown(tailored_experience)

    # Programmatically assemble complete Markdown resume
    assembled_parts = [
        f"# {name}\n",
        f"**{target_subtitle}**\n{contact_line}\n",
        "## Professional Summary\n",
        f"{tailored_summary}\n",
        "## Skills\n",
        f"{tailored_skills}\n",
        "## Professional Experience\n",
        f"{tailored_experience}\n",
    ]

    if side_projects_md:
        assembled_parts.extend(["## AI Projects (Built Solo)\n", f"{side_projects_md}\n"])

    if education_md:
        assembled_parts.extend(["## Education\n", f"{education_md}\n"])

    if achievements_md:
        assembled_parts.extend(["## Personal Achievements\n", f"{achievements_md}\n"])

    return "\n".join(assembled_parts).strip()