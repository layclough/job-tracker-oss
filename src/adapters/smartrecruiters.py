import html
import json
import re
import urllib.request
from typing import Optional
import trafilatura
from .base import BaseATSAdapter, ExtractedJob


class SmartRecruitersAdapter(BaseATSAdapter):
    """Adapter for SmartRecruiters ATS public JSON API (api.smartrecruiters.com/v1/companies/{company}/postings/{job_id})."""

    def can_handle(self, url: str) -> bool:
        if not url:
            return False
        clean_url = url.lower()
        return "smartrecruiters.com" in clean_url

    def _extract_company_and_job_id(self, url: str) -> tuple[Optional[str], Optional[str]]:
        # Pattern: smartrecruiters.com/(?:ni/)?([^/?#]+)/([a-zA-Z0-9_\-]+)
        match = re.search(r"smartrecruiters\.com/(?:[a-zA-Z]{2}/)?([^/?#]+)/([a-zA-Z0-9_\-]+)", url)
        if match:
            company = match.group(1)
            job_id = match.group(2)
            # Exclude non-posting routes like api, default, signin
            if company not in ("api", "v1", "signin", "embed"):
                return company, job_id
        return None, None

    def extract(self, url: str) -> ExtractedJob | None:
        company, job_id = self._extract_company_and_job_id(url)
        if not company or not job_id:
            return None

        api_url = f"https://api.smartrecruiters.com/v1/companies/{company}/postings/{job_id}"
        req = urllib.request.Request(
            api_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"[SmartRecruitersAdapter] API fetch failed for {api_url}: {e}")
            return None

        title = data.get("name", "").strip()
        job_ad = data.get("jobAd", {})
        sections = job_ad.get("sections", {}) if isinstance(job_ad, dict) else {}

        # Build combined HTML content from sections
        html_parts = [f"<h1>{title}</h1>"]
        section_order = [
            "companyDescription",
            "jobDescription",
            "qualifications",
            "additionalInformation",
        ]

        # Add predefined sections in logical reading order
        for key in section_order:
            if key in sections and isinstance(sections[key], dict):
                sec_title = sections[key].get("title", "")
                sec_text = html.unescape(sections[key].get("text", ""))
                if sec_title:
                    html_parts.append(f"<h2>{sec_title}</h2>")
                if sec_text:
                    html_parts.append(f"<div>{sec_text}</div>")

        # Add any other remaining sections not in section_order
        for key, sec in sections.items():
            if key not in section_order and isinstance(sec, dict):
                sec_title = sec.get("title", "")
                sec_text = html.unescape(sec.get("text", ""))
                if sec_title:
                    html_parts.append(f"<h2>{sec_title}</h2>")
                if sec_text:
                    html_parts.append(f"<div>{sec_text}</div>")

        combined_html = "\n".join(html_parts)

        # Extract structured text using trafilatura
        extracted_text = trafilatura.extract(
            combined_html,
            include_comments=False,
            include_tables=True,
        )
        if not extracted_text:
            clean_body = re.sub(r"<[^>]+>", " ", combined_html)
            extracted_text = re.sub(r"\s+", " ", clean_body).strip()

        # Check compensation in top-level payload or sections
        clean_pay = ""
        comp = data.get("compensation")
        if isinstance(comp, dict):
            c_min = comp.get("min")
            c_max = comp.get("max")
            c_curr = comp.get("currency", "USD")
            if c_min and c_max:
                clean_pay = f"${c_min:,} - ${c_max:,} {c_curr}"
            elif c_min:
                clean_pay = f"${c_min:,}+ {c_curr}"

        if clean_pay and clean_pay not in extracted_text:
            extracted_text = f"{extracted_text}\n\nSalary & Compensation:\n{clean_pay}"

        full_text = (
            f"{title}\n\n{extracted_text}".strip()
            if title and title not in extracted_text
            else extracted_text
        )

        if not full_text or len(full_text) < 100:
            return None

        return ExtractedJob(
            title=title,
            body_text=full_text,
            salary=clean_pay if clean_pay else None,
            source_type="api",
        )
