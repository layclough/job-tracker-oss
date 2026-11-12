import json
from pathlib import Path
import re
from src.adapters import fetch_job_content
from src.llm_config import complete_chat, MAX_JD_CHARS


def resolve_master_resume_path(custom_path: Path | str | None = None) -> Path:
  """Resolves the Master Resume path dynamically from canonical project locations."""
  if custom_path:
    p = Path(custom_path)
    if p.exists():
      return p

  candidate_paths = [
      Path("00_Data/Master_resume.md"),
      Path("00_Data/Master_Resume.md"),
      Path("Master_resume.md"),
      Path("Master_Resume.md"),
  ]
  resolved_resume = next((p for p in candidate_paths if p.exists()), None)
  if not resolved_resume:
    matches = list(Path(".").glob("**/Master_resume.md")) + list(
        Path(".").glob("**/Master_Resume.md")
    )
    resolved_resume = matches[0] if matches else None

  if not resolved_resume or not resolved_resume.exists():
    raise FileNotFoundError(
        "Master resume not found in candidate paths (00_Data/Master_resume.md)."
    )

  return resolved_resume


def fetch_rendered_url_text(url: str) -> str:
  """Renders dynamic JavaScript SPAs or resolves direct ATS APIs to extract clean body text."""
  return fetch_job_content(url)



def get_job_description_content(url_input: str, pasted_text: str) -> str:
  """Prioritizes pasted text; falls back to Playwright/ATS URL rendering."""
  if pasted_text and len(pasted_text.strip()) > 50:
    return pasted_text.strip()

  if url_input and url_input.strip().startswith("http"):
    rendered = fetch_rendered_url_text(url_input.strip())
    if rendered and len(rendered) > 100:
      return rendered

  raise ValueError(
      "Unable to extract text from URL or input is empty. Please paste the job"
      " description directly."
  )


def extract_json_from_response(raw_text: str) -> dict:
  """Robustly isolates and parses JSON even if surrounded by thoughts or conversational text."""
  raw_text = raw_text.strip()

  # 1. Match standard markdown fenced block
  match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
  if match:
    try:
      return json.loads(match.group(1))
    except json.JSONDecodeError:
      pass

  # 2. Match first balanced JSON object {...}
  match = re.search(r"(\{[\s\S]*\})", raw_text)
  if match:
    candidate = match.group(1)
    try:
      return json.loads(candidate)
    except json.JSONDecodeError:
      # If trailing text broke it, attempt rfind for last valid closing brace
      end_idx = candidate.rfind("}")
      if end_idx != -1:
        return json.loads(candidate[: end_idx + 1])

  return json.loads(raw_text)


def extract_jd_details(jd_text: str) -> dict:
  """Extracts categorized requirements to prevent domain noise from diluting core PM scores."""
  prompt = """You are an executive technical recruiter. Analyze the job description and extract key attributes.
Categorize skills into 'core_requirements' (minimum/fundamental requirements) and 'preferred_skills' (domain-specific/nice-to-have).
For salary, extract the full compensation range (e.g. '$148,680 - $214,800 USD') if mentioned anywhere in the job text.
THINKING CONSTRAINT: Keep any internal reasoning extremely brief (under 50 words total); do not restate the text or second-guess.

Return ONLY valid JSON matching this schema:
{
    "company": "Company Name",
    "title": "Job Title",
    "salary": "Salary range or Not specified",
    "experience": "Years of experience required",
    "core_requirements": ["Core Skill 1", "Core Skill 2"],
    "preferred_skills": ["Domain Skill 1", "Domain Skill 2"]
}"""

  safe_jd_text = jd_text[:MAX_JD_CHARS]

  response_text = complete_chat(
      system=prompt,
      user=safe_jd_text,
      temperature=0.1,
      max_tokens=1500,
  )

  parsed = extract_json_from_response(response_text)
  if "skills" not in parsed:
    parsed["skills"] = parsed.get("core_requirements", []) + parsed.get(
        "preferred_skills", []
    )
  return parsed


def _normalize_partial_item(item) -> dict:
  """Ensures partial item is a dictionary with 'skill' and 'reason' keys."""
  if isinstance(item, dict):
    skill = str(item.get("skill", "")).strip()
    reason = str(item.get("reason", "")).strip()
    return {"skill": skill, "reason": reason}
  elif isinstance(item, str):
    parts = item.split(":", 1)
    if len(parts) == 2:
      skill = parts[0].strip()
      reason = re.sub(r"\s*\(0\.5\)\s*$", "", parts[1].strip()).strip()
      return {"skill": skill, "reason": reason}
    return {"skill": item.strip(), "reason": "Transferable experience (0.5)"}
  return {"skill": str(item).strip(), "reason": ""}


def _normalize_string_item(item) -> str:
  """Ensures item is a clean string representation."""
  if isinstance(item, dict):
    skill = str(item.get("skill", "")).strip()
    reason = str(item.get("reason", "")).strip()
    return f"{skill}: {reason}" if reason else skill
  return str(item).strip()


class GapAnalysisResult(dict):
  """Result dictionary that also supports tuple unpacking: score, missing = calculate_gap(...)"""

  def __iter__(self):
    yield self["final_match_rate"]
    yield self.get(
        "missing_skills",
        self.get("missing_core", []) + self.get("missing_preferred", []),
    )


def calculate_gap(
    core_skills: list,
    preferred_skills: list | Path | str | None = None,
    master_resume_path: Path | str | None = None,
    core_weight: float = 0.85,
    preferred_weight: float = 0.15,
):
  """Performs semantic gap analysis with weighted deterministic scoring between core requirements (0.85) and domain preferences (0.15), allowing 0.5 partial credit for transferable skills."""
  # Support 2-argument signature: calculate_gap(skills_list, master_resume_path)
  if isinstance(preferred_skills, (Path, str)) and master_resume_path is None:
    master_resume_path = preferred_skills
    preferred_skills = []
  elif preferred_skills is None:
    preferred_skills = []

  resolved_resume = resolve_master_resume_path(master_resume_path)
  resume_text = resolved_resume.read_text(encoding="utf-8")

  prompt = f"""You are a rigorous executive talent evaluator performing an objective candidate gap analysis.
Evaluate whether the candidate's Master Resume provides concrete, verifiable evidence for each skill requirement.

EVALUATION RULES:
1. Verifiable Full Match (1.0 Credit): Classify in 'matched_core' or 'matched_preferred' ONLY if the candidate's resume shows direct, concrete evidence of having performed this work or possessing this specific skill.
2. Partial Credit for Transferable Skills & Adjacent Tooling (0.5 Credit):
   Classify in 'partial_core' or 'partial_preferred' when the candidate demonstrates strong, adjacent, transferable experience or equivalent foundational tooling even if the exact proprietary tool or brand is not explicitly named.
   Each item in partial_core and partial_preferred MUST be an object with "skill" and "reason" keys:
   {{"skill": "Skill Name", "reason": "Why it is transferable (0.5)"}}
   Examples of transferable credit:
   - Modern rapid prototyping, LLM prompting, or frontend prototyping counts as 0.5 partial credit towards specific modern tools like Cursor, Lovable, v0, Bolt, Windsurf, or Replit.
   - Deep production experience in one major cloud provider (e.g. AWS or GCP) counts as 0.5 partial credit for adjacent cloud platforms (e.g. Azure) if the core architectural skill is identical.
   - Robust relational database / data pipeline experience (e.g. PostgreSQL, MySQL) counts as 0.5 partial credit for adjacent warehousing tools (e.g. Snowflake, BigQuery).
   - Core PM leadership and discovery methodologies count partially towards adjacent framework variations.
3. Domain & Regulated Knowledge: Do NOT give credit for specialized regulated domains (e.g., 'regulated financial-services workflows', 'mortgage/escrow/title', 'clinical healthcare') unless the candidate explicitly worked in that specific sector. General B2B SaaS or financial ROI modeling does NOT count as regulated financial services.
4. Technical Depth: For specialized technical competencies (e.g., 'machine-learning lifecycle including model training, evaluation, retraining', 'data pipelines'), verify that the resume shows practical execution experience beyond basic tool usage.
5. Foundational PM Practices: Standard PM competencies (roadmaps, user stories, OKRs, stakeholder alignment, agile, customer interviews) should be matched (1.0) if senior PM experience is demonstrated.
6. Missing (0.0 Credit): If no direct evidence or reasonable transferable adjacent experience exists, classify in 'missing_core' or 'missing_preferred'.

DO NOT CALCULATE MATHEMATICAL SCORES OR PERCENTAGES. Only classify requirements into the structured schema below.
THINKING CONSTRAINT: In your internal reasoning, do NOT repeat these rules or the requirements list. Evaluate each requirement once in a single brief bullet line (max 15 words per item) and do not re-evaluate after deciding.

Return ONLY valid JSON:
{{
    "matched_core": ["Full Match 1", "Full Match 2"],
    "partial_core": [{{"skill": "Skill Name", "reason": "Why it is transferable (0.5)"}}],
    "missing_core": ["Missing Skill"],
    "matched_preferred": ["Preferred 1"],
    "partial_preferred": [{{"skill": "Skill Name", "reason": "Why it is transferable (0.5)"}}],
    "missing_preferred": ["Missing Preferred"]
}}

CANDIDATE MASTER RESUME:
{resume_text}

CORE REQUIREMENTS (Essential Qualifications - drives 85% of overall score):
{json.dumps(core_skills, indent=2)}

PREFERRED / DOMAIN SKILLS (Nice to Have / Bonus - drives 15% of overall score):
{json.dumps(preferred_skills, indent=2)}"""

  response_text = complete_chat(
      system=(
          "You are a rigorous executive talent evaluator. Keep internal thinking ultra-concise (1 short line per item, no rule repetition, no second-guessing). Output valid JSON only."
      ),
      user=prompt,
      temperature=0.0,
      max_tokens=2000,
  )

  parsed = extract_json_from_response(response_text)

  matched_core = [_normalize_string_item(s) for s in parsed.get("matched_core", []) if s]
  partial_core = [_normalize_partial_item(p) for p in parsed.get("partial_core", []) if p]
  missing_core = [_normalize_string_item(m) for m in parsed.get("missing_core", []) if m]

  matched_preferred = [_normalize_string_item(s) for s in parsed.get("matched_preferred", []) if s]
  partial_preferred = [_normalize_partial_item(p) for p in parsed.get("partial_preferred", []) if p]
  missing_preferred = [_normalize_string_item(m) for m in parsed.get("missing_preferred", []) if m]

  # Deterministic Python scoring
  core_total = len(matched_core) + len(partial_core) + len(missing_core)
  core_points = len(matched_core) + (len(partial_core) * 0.5)
  core_score = round((core_points / core_total) * 100, 1) if core_total > 0 else 100.0

  pref_total = len(matched_preferred) + len(partial_preferred) + len(missing_preferred)
  pref_points = len(matched_preferred) + (len(partial_preferred) * 0.5)
  pref_score = round((pref_points / pref_total) * 100, 1) if pref_total > 0 else 100.0

  if pref_total > 0:
    final_score = round((core_score * 0.85) + (pref_score * 0.15), 1)
  else:
    final_score = core_score

  return GapAnalysisResult({
      "final_match_rate": final_score,
      "core_match_rate": core_score,
      "preferred_match_rate": pref_score,
      "core_counts": {
          "matched": len(matched_core),
          "partial": len(partial_core),
          "total": core_total,
          "points": core_points,
      },
      "preferred_counts": {
          "matched": len(matched_preferred),
          "partial": len(partial_preferred),
          "total": pref_total,
          "points": pref_points,
      },
      "partial_core": partial_core,
      "partial_preferred": partial_preferred,
      "missing_core": missing_core,
      "missing_preferred": missing_preferred,
      "matched_core": matched_core,
      "matched_preferred": matched_preferred,
      "missing_skills": missing_core + missing_preferred,
      "core_weight": core_weight,
      "preferred_weight": preferred_weight,
  })


calculate_semantic_gap = calculate_gap


