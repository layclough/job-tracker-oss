from .base import BaseATSAdapter, ExtractedJob
from .greenhouse import GreenhouseAdapter
from .smartrecruiters import SmartRecruitersAdapter
from .workable import WorkableAdapter
from .universal import fetch_universal_browser

# Ordered list of direct ATS API adapters
ATS_ADAPTERS: list[BaseATSAdapter] = [
    GreenhouseAdapter(),
    SmartRecruitersAdapter(),
    WorkableAdapter(),
]


def extract_job(url: str) -> ExtractedJob:
    """Extracts job posting using fast direct ATS APIs with universal browser fallback."""
    url = url.strip()

    # 1. Check direct ATS API adapters
    for adapter in ATS_ADAPTERS:
        if adapter.can_handle(url):
            try:
                job = adapter.extract(url)
                if job and job.body_text and len(job.body_text.strip()) > 100:
                    return job
            except Exception as e:
                print(f"[{adapter.__class__.__name__}] Failed to extract {url}: {e}")

    # 2. Universal Browser fallback (Playwright + Trafilatura)
    return fetch_universal_browser(url)


def fetch_job_content(url: str) -> str:
    """Convenience function returning clean body text for downstream extraction and gap analysis."""
    job = extract_job(url)
    return job.body_text.strip() if job else ""
