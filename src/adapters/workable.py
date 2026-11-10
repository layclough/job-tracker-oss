import html
import json
import re
import urllib.request
from typing import Optional
import trafilatura
from .base import BaseATSAdapter, ExtractedJob


class WorkableAdapter(BaseATSAdapter):
    """Adapter for Workable public JSON API (apply.workable.com/api/v3/accounts/{account}/jobs/{shortcode})."""

    def can_handle(self, url: str) -> bool:
        if not url:
            return False
        clean_url = url.lower()
        return "workable.com" in clean_url

    def _extract_account_and_shortcode(self, url: str) -> tuple[Optional[str], Optional[str]]:
        # Pattern 1: apply.workable.com/{account}/j/{shortcode} or /jobs/{shortcode}
        match = re.search(r"workable\.com/(?:[a-zA-Z]{2}/)?([^/?#]+)/(?:j|jobs)/([a-zA-Z0-9_\-]+)", url)
        if match:
            account = match.group(1)
            shortcode = match.group(2)
            if account not in ("api", "v3", "accounts", "view"):
                return account, shortcode

        # Pattern 2: jobs.workable.com/view/{shortcode}
        view_match = re.search(r"jobs\.workable\.com/view/([a-zA-Z0-9_\-]+)", url)
        if view_match:
            # When account is not in URL, this can't use the accounts API without a resolve step
            return None, None

        return None, None

    def extract(self, url: str) -> ExtractedJob | None:
        account, shortcode = self._extract_account_and_shortcode(url)
        if not account or not shortcode:
            return None

        api_url = f"https://apply.workable.com/api/v3/accounts/{account}/jobs/{shortcode}"
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
            print(f"[WorkableAdapter] API fetch failed for {api_url}: {e}")
            return None

        title = data.get("title", "").strip()
        description = html.unescape(data.get("description", ""))
        requirements = html.unescape(data.get("requirements", ""))
        benefits = html.unescape(data.get("benefits", ""))

        html_parts = [f"<h1>{title}</h1>"]
        if description:
            html_parts.append(f"<div>{description}</div>")
        if requirements:
            html_parts.append(f"<h2>Requirements</h2><div>{requirements}</div>")
        if benefits:
            html_parts.append(f"<h2>Benefits</h2><div>{benefits}</div>")

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

        # Extract salary if provided in data
        clean_pay = ""
        salary_info = data.get("salary") or data.get("salary_range")
        if isinstance(salary_info, dict):
            s_from = salary_info.get("from")
            s_to = salary_info.get("to")
            s_curr = salary_info.get("currency", "USD")
            if s_from and s_to:
                clean_pay = f"${s_from:,} - ${s_to:,} {s_curr}"
            elif s_from:
                clean_pay = f"${s_from:,}+ {s_curr}"
        elif isinstance(salary_info, str) and salary_info.strip():
            clean_pay = salary_info.strip()

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
