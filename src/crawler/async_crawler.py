"""Bounded-concurrency async crawler used by all source adapters."""

from typing import Optional

import aiohttp

from src.config import DEFAULT_CONCURRENCY, REQUEST_TIMEOUT_SECONDS, USER_AGENT
from src.crawler.browser import fetch_rendered_html
from src.crawler.http import RetryingFetcher, looks_like_challenge
from src.utils.logging import get_logger

logger = get_logger("async_crawler")


class AsyncCrawler:
    def __init__(
        self,
        concurrency: int = DEFAULT_CONCURRENCY,
        timeout: int = REQUEST_TIMEOUT_SECONDS,
        js_fallback: bool = True,
    ):
        self.concurrency = concurrency
        self.timeout = timeout
        self.js_fallback = js_fallback
        self._semaphore = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.fetcher: Optional[RetryingFetcher] = None

    async def __aenter__(self):
        self._semaphore = __import__("asyncio").Semaphore(self.concurrency)
        self.session = aiohttp.ClientSession(
            headers={"User-Agent": USER_AGENT},
            timeout=aiohttp.ClientTimeout(total=self.timeout),
        )
        self.fetcher = RetryingFetcher(self.session, timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.session:
            await self.session.close()

    async def fetch_text(self, url: str, allow_js_fallback: bool = True) -> str:
        async with self._semaphore:
            status, text = await self.fetcher.get_text(url)

        if status == 200 and text and not looks_like_challenge(status, text):
            return text

        if self.js_fallback and allow_js_fallback:
            logger.info("Trying Playwright fallback for %s", url)
            rendered = await fetch_rendered_html(url)
            if rendered:
                return rendered

        logger.warning("Could not fetch %s (HTTP %s)", url, status)
        return text if status == 200 else ""

    async def fetch_json(self, url: str):
        async with self._semaphore:
            status, data = await self.fetcher.get_json(url)
        if status != 200:
            logger.warning("JSON fetch failed %s (HTTP %s)", url, status)
            return None
        return data
