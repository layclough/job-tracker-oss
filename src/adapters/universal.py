import re
import urllib.request
import trafilatura
from playwright.sync_api import sync_playwright
from .base import ExtractedJob


def fetch_universal_browser(url: str) -> ExtractedJob:
    """Universal browser engine using Playwright headless Chromium and Trafilatura.
    
    Falls back gracefully to standard HTTP fetch if Playwright fails.
    """
    url = url.strip()
    html_content = ""
    clean_pay = ""

    # 1. Primary engine: Playwright Headless Chromium
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                )
            )
            page = context.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                try:
                    page.wait_for_selector(
                        "main, article, .job-description, [data-qa='job-description'], body",
                        timeout=15000,
                    )
                except Exception:
                    pass
                page.wait_for_timeout(1000)
            except Exception as nav_e:
                print(f"[UniversalBrowser] Page navigation warning for {url}: {nav_e}")

            html_content = page.content()
            browser.close()
    except Exception as e:
        print(f"[UniversalBrowser] Playwright failed for {url}: {e}. Attempting direct HTTP fallback...")

    # 2. Fallback: Direct HTTP request if Playwright failed to yield content
    if not html_content or len(html_content) < 200:
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                html_content = resp.read().decode("utf-8", errors="ignore")
        except Exception as http_e:
            print(f"[UniversalBrowser] Direct HTTP fetch failed for {url}: {http_e}")

    if not html_content:
        return ExtractedJob(title="", body_text="", salary=None, source_type="browser")

    # Capture pay transparency if present in rendered HTML
    pay_match = re.search(
        r'<div[^>]*class=[\"\'][^\"\']*(?:content-pay-transparency|pay-range|pay-input|salary)[^\"\']*[\"\'][\s\S]*?</div>\s*</div>\s*</div>',
        html_content,
        re.IGNORECASE,
    )
    if not pay_match:
        pay_match = re.search(
            r'<div[^>]*class=[\"\'][^\"\']*(?:pay-range|salary-range)[^\"\']*[\"\'][\s\S]*?</div>',
            html_content,
            re.IGNORECASE,
        )
    if pay_match:
        clean_pay = re.sub(r"<[^>]+>", " ", pay_match.group(0))
        clean_pay = re.sub(r"\s+", " ", clean_pay).strip()

    extracted = (
        trafilatura.extract(
            html_content, include_comments=False, include_tables=True
        )
        or ""
    )
    if clean_pay and clean_pay not in extracted:
        extracted = f"{extracted}\n\nSalary & Compensation:\n{clean_pay}"

    # Extract page title tag if available
    title = ""
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html_content, re.IGNORECASE | re.DOTALL)
    if title_match:
        title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()

    return ExtractedJob(
        title=title,
        body_text=extracted,
        salary=clean_pay if clean_pay else None,
        source_type="browser",
    )
