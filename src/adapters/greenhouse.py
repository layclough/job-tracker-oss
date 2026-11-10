import html
import json
import re
import urllib.request
from typing import Optional
import trafilatura
from .base import BaseATSAdapter, ExtractedJob


class GreenhouseAdapter(BaseATSAdapter):
    """Adapter for Greenhouse ATS public JSON API (boards-api.greenhouse.io)."""

    def can_handle(self, url: str) -> bool:
        if not url:
            return False
        clean_url = url.lower()
        return "greenhouse.io" in clean_url

    def _extract_board_and_job_id(self, url: str) -> tuple[Optional[str], Optional[str]]:
        # Pattern 1: embed/job_app?for={board}&token={id} (in any order)
        if "embed/job_app" in url:
            board_match = re.search(r"[?&]for=([^&#]+)", url)
            token_match = re.search(r"[?&]token=(\d+)", url)
            if board_match and token_match:
                return board_match.group(1), token_match.group(1)

        # Pattern 2: boards.greenhouse.io/{board}/jobs/{id} or job-boards.greenhouse.io/{board}/jobs/{id}
        match = re.search(r"greenhouse\.io/(?:job-boards/|v1/boards/)?([^/?#]+)/jobs/(\d+)", url)
        if match:
            board = match.group(1)
            job_id = match.group(2)
            if board not in ("embed", "v1"):
                return board, job_id

        # Pattern 3: Fallback query parameter id/token/gh_jid with board in path
        board_fallback = re.search(r"greenhouse\.io/([^/?#]+)", url)
        id_fallback = re.search(r"[?&](?:job\?id=|id=|token=|gh_jid=)(\d+)", url)
        if board_fallback and id_fallback:
            board = board_fallback.group(1)
            if board not in ("embed", "v1", "job-boards"):
                return board, id_fallback.group(1)

        return None, None

    def extract(self, url: str) -> ExtractedJob | None:
        board, job_id = self._extract_board_and_job_id(url)
        if not board or not job_id:
            return None

        api_url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}"
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
            print(f"[GreenhouseAdapter] API fetch failed for {api_url}: {e}")
            return None

        title = data.get("title", "").strip()
        raw_content = data.get("content", "")
        unescaped_html = html.unescape(raw_content)

        # Extract pay transparency / salary block from unescaped HTML if present
        clean_pay = ""
        pay_match = re.search(
            r'<div[^>]*class=[\"\'][^\"\']*(?:content-pay-transparency|pay-range|pay-input|salary)[^\"\']*[\"\'][\s\S]*?</div>\s*</div>\s*</div>',
            unescaped_html,
            re.IGNORECASE,
        )
        if not pay_match:
            pay_match = re.search(
                r'<div[^>]*class=[\"\'][^\"\']*(?:pay-range|salary-range)[^\"\']*[\"\'][\s\S]*?</div>',
                unescaped_html,
                re.IGNORECASE,
            )
        if pay_match:
            clean_pay = re.sub(r"<[^>]+>", " ", pay_match.group(0))
            clean_pay = re.sub(r"\s+", " ", clean_pay).strip()

        # Extract structured text using trafilatura
        extracted_text = trafilatura.extract(
            f"<h1>{title}</h1><div>{unescaped_html}</div>",
            include_comments=False,
            include_tables=True,
        )
        if not extracted_text:
            clean_body = re.sub(r"<[^>]+>", " ", unescaped_html)
            extracted_text = re.sub(r"\s+", " ", clean_body).strip()

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
