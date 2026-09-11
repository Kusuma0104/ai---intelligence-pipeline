import asyncio
import time
from dataclasses import dataclass
from typing import List, Dict, Optional

import aiohttp

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None


@dataclass
class CrawlResult:
    url: str
    status: str
    content: str = ""
    error: Optional[str] = None
    cache_hit: bool = False


class AsyncCrawler:
    """
    Async, concurrent crawler with:
    - asyncio + aiohttp
    - concurrency limit
    - timeout
    - simple in-memory cache
    - Playwright fallback for JavaScript-heavy pages
    - source-friendly architecture
    """

    def __init__(self, concurrency: int = 5, timeout_seconds: int = 20):
        self.concurrency = concurrency
        self.timeout_seconds = timeout_seconds
        self.cache: Dict[str, str] = {}
        self.semaphore = asyncio.Semaphore(concurrency)

    async def fetch_http(self, session: aiohttp.ClientSession, url: str) -> CrawlResult:
        if url in self.cache:
            return CrawlResult(
                url=url,
                status="success",
                content=self.cache[url],
                cache_hit=True,
            )

        async with self.semaphore:
            try:
                timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)

                async with session.get(
                    url,
                    timeout=timeout,
                    headers={
                        "User-Agent": (
                            "AI-Intelligence-Pipeline/1.0 "
                            "(research crawler; contact via repository)"
                        )
                    },
                ) as response:

                    text = await response.text(errors="ignore")

                    if response.status >= 400:
                        return CrawlResult(
                            url=url,
                            status="failed",
                            error=f"HTTP {response.status}",
                        )

                    self.cache[url] = text

                    return CrawlResult(
                        url=url,
                        status="success",
                        content=text,
                        cache_hit=False,
                    )

            except Exception as exc:
                return CrawlResult(
                    url=url,
                    status="failed",
                    error=str(exc),
                )

    async def fetch_playwright(self, url: str) -> CrawlResult:
        """
        JS-rendered page fallback.

        This does NOT bypass CAPTCHA, Cloudflare, Datadome,
        authentication, or other security controls.
        """

        if async_playwright is None:
            return CrawlResult(
                url=url,
                status="failed",
                error="Playwright is not installed",
            )

        if url in self.cache:
            return CrawlResult(
                url=url,
                status="success",
                content=self.cache[url],
                cache_hit=True,
            )

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)

                page = await browser.new_page()

                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=self.timeout_seconds * 1000,
                )

                content = await page.content()

                await browser.close()

                self.cache[url] = content

                return CrawlResult(
                    url=url,
                    status="success",
                    content=content,
                    cache_hit=False,
                )

        except Exception as exc:
            return CrawlResult(
                url=url,
                status="failed",
                error=str(exc),
            )
            
    def needs_playwright(self, result: CrawlResult) -> bool:
        """
        Decide whether a successful HTTP response appears to be
        JavaScript-heavy and should be rendered with Playwright.

        Security note:
        This is only for permitted JS rendering. It does not
        bypass CAPTCHA, Cloudflare, Datadome, authentication,
        or other security controls.
        """

        if result.status != "success":
            return False

        content = result.content.lower()

        if len(content) < 1000:
            return True

        js_markers = [
            "__next",
            "__nuxt",
            "webpack",
            "react",
            "vue",
            "angular",
            "window.__",
            "<script",
        ]

        marker_count = sum(
            marker in content
            for marker in js_markers
        )

        text_length = len(
            " ".join(
                line.strip()
                for line in content.splitlines()
                if line.strip()
            )
        )

        return marker_count >= 3 and text_length < 3000
    
    async def fetch_with_strategy(
        self,
        session: aiohttp.ClientSession,
        url: str
    ) -> CrawlResult:

        http_result = await self.fetch_http(
            session,
            url
        )

        # Never attempt to bypass protected endpoints.
        if http_result.status == "failed":
            if http_result.error in {
                "HTTP 401",
                "HTTP 403",
                "HTTP 429",
            }:
                return http_result

            # For ordinary HTTP failures, keep the failure
            # rather than attempting to defeat access controls.
            return http_result

        if self.needs_playwright(http_result):
            print(
                f"JS-heavy source detected -> "
                f"Playwright: {url}"
            )

            return await self.fetch_playwright(url)

        return http_result
    
    async def crawl(self, urls: List[str]) -> List[CrawlResult]:
        start = time.perf_counter()

        connector = aiohttp.TCPConnector(limit=self.concurrency)

        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [
                self.fetch_with_strategy(session, url)
                for url in urls
            ]

            results = await asyncio.gather(*tasks)

        elapsed = time.perf_counter() - start

        print("\nAsync Crawler Results:\n")

        for result in results:
            print(
                f"{result.url} -> "
                f"{result.status} | "
                f"cache: {result.cache_hit}"
            )

        print(
            f"\nCrawled {len(urls)} URLs "
            f"in {elapsed:.2f} seconds"
        )

        return results


async def main():
    urls = [
        "https://example.com",
        "https://www.python.org",
        "https://httpbin.org/html",
    ]

    crawler = AsyncCrawler(
        concurrency=5,
        timeout_seconds=20,
    )

    # First crawl: fetches from network
    await crawler.crawl(urls)

    # Second crawl: demonstrates cache
    await crawler.crawl(urls)


if __name__ == "__main__":
    asyncio.run(main())