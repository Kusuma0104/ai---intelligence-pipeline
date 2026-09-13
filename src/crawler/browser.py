"""Playwright adapter for JavaScript-rendered pages.

This adapter does not solve CAPTCHAs or bypass Cloudflare/Datadome.
It only renders pages that the local browser can open, and it backs off
when a bot-challenge page is detected.
"""

from typing import Optional

from src.crawler.http import looks_like_challenge
from src.utils.logging import get_logger

logger = get_logger("browser")


async def fetch_rendered_html(
    url: str,
    timeout_ms: int = 30000,
    wait_until: str = "domcontentloaded",
) -> Optional[str]:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning("Playwright is not installed; skipping JS render for %s", url)
        return None

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page()
            response = await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            html = await page.content()
            status = response.status if response else 0
            await browser.close()

            if looks_like_challenge(status, html):
                logger.warning(
                    "Challenge page detected for %s (status=%s). "
                    "Refusing to bypass bot protection; use an official API/feed instead.",
                    url,
                    status,
                )
                return None

            return html
    except Exception as exc:
        logger.warning("Playwright render failed for %s: %s", url, exc)
        return None
