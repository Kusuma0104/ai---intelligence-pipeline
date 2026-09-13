import asyncio
import random
from typing import Optional

import aiohttp

from src.config import REQUEST_TIMEOUT_SECONDS, USER_AGENT
from src.utils.logging import get_logger

logger = get_logger("http")

CHALLENGE_MARKERS = (
    "cf-browser-verification",
    "attention required | cloudflare",
    "cdn-cgi/challenge",
    "datadome",
    "please verify you are a human",
    "access denied",
)


def looks_like_challenge(status: int, text: str) -> bool:
    if status in {401, 403, 429, 503}:
        lowered = (text or "")[:4000].lower()
        return any(marker in lowered for marker in CHALLENGE_MARKERS) or status in {403, 503}
    lowered = (text or "")[:4000].lower()
    return any(marker in lowered for marker in CHALLENGE_MARKERS)


def default_headers() -> dict:
    return {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }


class RetryingFetcher:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        max_retries: int = 4,
        timeout: int = REQUEST_TIMEOUT_SECONDS,
    ):
        self.session = session
        self.max_retries = max_retries
        self.timeout = aiohttp.ClientTimeout(total=timeout)

    async def request(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> aiohttp.ClientResponse:
        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = await self.session.request(
                    method,
                    url,
                    timeout=kwargs.pop("timeout", self.timeout),
                    headers={**default_headers(), **(kwargs.pop("headers", {}) or {})},
                    **kwargs,
                )
                if response.status in {429, 500, 502, 503, 504}:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else min(30, 2 ** attempt) + random.uniform(0, 1)
                    logger.info("HTTP %s for %s; retrying in %.1fs", response.status, url, delay)
                    await response.release()
                    await asyncio.sleep(delay)
                    continue
                return response
            except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
                last_error = exc
                delay = min(30, 2 ** attempt) + random.uniform(0, 1)
                logger.info("Request error for %s (%s); retrying in %.1fs", url, exc, delay)
                await asyncio.sleep(delay)

        raise RuntimeError(f"Failed to fetch {url}: {last_error}")

    async def get_text(self, url: str) -> tuple[int, str]:
        response = await self.request("GET", url)
        async with response:
            text = await response.text(errors="ignore")
            return response.status, text

    async def get_json(self, url: str) -> tuple[int, Optional[object]]:
        response = await self.request("GET", url)
        async with response:
            if response.status != 200:
                return response.status, None
            return response.status, await response.json(content_type=None)
