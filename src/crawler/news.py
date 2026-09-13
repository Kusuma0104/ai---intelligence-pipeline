import asyncio
import aiohttp
import feedparser
import pandas as pd

from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.utils.dates import normalize_date
from src.crawler.async_crawler import AsyncCrawler
from src.extraction.llm_orchestrator import LLMOrchestrator
from src.extraction.schemas import (
    NewsContent,
    NewsEntity,
    SourceInfo,
    news_row,
)
from src.resolution.entity_resolver import EntityResolver
from src.utils.logging import get_logger


logger = get_logger("news")


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_FILE = DATA_DIR / "news_24h.csv"


NEWS_SOURCES = [
    {
        "name": "The Guardian AI",
        "feed": "https://www.theguardian.com/technology/artificialintelligenceai/rss",
    },
    {
        "name": "Wired AI",
        "feed": "https://www.wired.com/feed/tag/ai/latest/rss",
    },
    {
        "name": "Engadget AI",
        "feed": "https://www.engadget.com/rss.xml",
    },
    {
        "name": "The Verge AI",
        "feed": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    },
    {
        "name": "TechCrunch AI",
        "feed": "https://techcrunch.com/category/artificial-intelligence/feed/",
    },
]


def parse_date(entry):
    """
    Parse feed publication/update dates.

    Prefer feedparser structured dates, then fall back
    to textual date fields and normalize_date().
    """

    for field in (
        "published_parsed",
        "updated_parsed",
        "created_parsed",
    ):
        value = entry.get(field)

        if value:
            try:
                return datetime(
                    value.tm_year,
                    value.tm_mon,
                    value.tm_mday,
                    value.tm_hour,
                    value.tm_min,
                    value.tm_sec,
                    tzinfo=timezone.utc,
                )
            except Exception:
                pass

    possible_dates = [
        entry.get("published"),
        entry.get("updated"),
        entry.get("created"),
    ]

    for value in possible_dates:
        if not value:
            continue

        normalized = normalize_date(value)

        if not normalized:
            continue

        try:
            parsed = datetime.fromisoformat(
                normalized
            )

            if parsed.tzinfo is None:
                parsed = parsed.replace(
                    tzinfo=timezone.utc
                )

            return parsed.astimezone(
                timezone.utc
            )

        except Exception:
            continue

    return None


def clean_text(html):
    """
    Convert HTML into readable plain text.
    """

    soup = BeautifulSoup(
        html or "",
        "html.parser",
    )

    for tag in soup(
        [
            "script",
            "style",
            "noscript",
            "svg",
            "nav",
            "footer",
            "header",
        ]
    ):
        tag.decompose()

    return " ".join(
        soup.stripped_strings
    ).strip()


def is_blocked_page(text):
    """
    Detect security/challenge pages instead of
    treating them as article content.
    """

    if not text:
        return True

    text_lower = text.lower()

    blocked_markers = [
        "awswafintegration",
        "awswaf",
        "challenge.js",
        "verify that you're not a robot",
        "javascript is disabled",
        "enable javascript and then reload",
        "cloudflare",
        "cf-chl-",
        "datadome",
        "access denied",
        "captcha",
        "robot check",
    ]

    return any(
        marker in text_lower
        for marker in blocked_markers
    )


def is_valid_article_text(text):
    """
    Validate that extracted content looks like
    real article text.
    """

    if not text:
        return False

    if is_blocked_page(text):
        return False

    words = text.split()

    # Require enough content to qualify as
    # article full text rather than a title/snippet.
    if len(words) < 80:
        return False

    return True


def extract_article_text(html):
    """
    Extract article body from a news webpage.

    Extraction order:
    1. <article>
    2. common article-body containers
    3. <main>
    4. paragraph fallback

    Security/challenge pages are rejected.
    """

    if not html:
        return ""

    html_lower = html.lower()

    blocked_markers = [
        "awswafintegration",
        "awswaf",
        "challenge.js",
        "verify that you're not a robot",
        "javascript is disabled",
        "enable javascript and then reload",
        "cloudflare",
        "cf-chl-",
        "datadome",
    ]

    if any(
        marker in html_lower
        for marker in blocked_markers
    ):
        return ""

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    for tag in soup(
        [
            "script",
            "style",
            "noscript",
            "svg",
            "nav",
            "footer",
            "header",
        ]
    ):
        tag.decompose()

    # 1. Semantic article element
    article = soup.find("article")

    if article:
        text = clean_text(
            str(article)
        )

        if is_valid_article_text(text):
            return text

    # 2. Common article body containers
    selectors = [
        '[itemprop="articleBody"]',
        '[class*="article-body"]',
        '[class*="article-content"]',
        '[class*="article__body"]',
        '[class*="post-content"]',
        '[class*="entry-content"]',
    ]

    for selector in selectors:
        element = soup.select_one(
            selector
        )

        if element:
            text = clean_text(
                str(element)
            )

            if is_valid_article_text(text):
                return text

    # 3. Main content
    main = soup.find("main")

    if main:
        text = clean_text(
            str(main)
        )

        if is_valid_article_text(text):
            return text

    # 4. Paragraph fallback
    paragraphs = soup.find_all("p")

    text = " ".join(
        p.get_text(
            " ",
            strip=True,
        )
        for p in paragraphs
    ).strip()

    if is_valid_article_text(text):
        return text

    return ""


async def fetch_article(
    session,
    url,
):
    """
    Fetch and extract article full text.
    """

    try:
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(
                total=30
            ),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(compatible; "
                    "AI-Intelligence-Pipeline/1.0)"
                )
            },
            allow_redirects=True,
        ) as response:

            if response.status != 200:
                logger.warning(
                    "Article HTTP %s: %s",
                    response.status,
                    url,
                )
                return ""

            html = await response.text(
                errors="ignore"
            )

            text = extract_article_text(
                html
            )

            if not text:
                logger.warning(
                    "No valid article text extracted: %s",
                    url,
                )
                return ""

            return text

    except Exception as exc:
        logger.warning(
            "Article extraction failed: %s | %s",
            url,
            exc,
        )
        return ""


async def collect_news():

    print()
    print(
        "==================================="
    )
    print(
        "Collecting AI news from last 24 hours"
    )
    print(
        "==================================="
    )

    now = datetime.now(
        timezone.utc
    )

    cutoff = now - timedelta(
        hours=24
    )

    print(
        "Current UTC time:",
        now.isoformat(),
    )

    print(
        "24-hour cutoff:",
        cutoff.isoformat(),
    )

    records = []

    resolver = EntityResolver()
    orchestrator = LLMOrchestrator()

    collected_at = datetime.now(
        timezone.utc
    )

    # One HTTP session for all article requests.
    async with aiohttp.ClientSession() as article_session:

        async with AsyncCrawler() as crawler:

            for source in NEWS_SOURCES:

                logger.info(
                    "Source: %s",
                    source["name"],
                )

                try:

                    xml = await crawler.fetch_text(
                        source["feed"],
                        allow_js_fallback=False,
                    )

                    if not xml:
                        logger.warning(
                            "Skipping source %s",
                            source["name"],
                        )
                        continue

                    feed = feedparser.parse(
                        xml
                    )

                    logger.info(
                        "Feed entries: %s",
                        len(feed.entries),
                    )

                    logger.info(
                        "Feed bozo: %s",
                        feed.bozo,
                    )

                    logger.info(
                        "Feed status: %s",
                        getattr(
                            feed,
                            "status",
                            "unknown",
                        ),
                    )

                    fresh_count = 0
                    valid_full_text_count = 0

                    for entry in feed.entries:

                        published_dt = parse_date(
                            entry
                        )

                        # Strict 24-hour freshness.
                        if (
                            not published_dt
                            or published_dt < cutoff
                            or published_dt > now
                        ):
                            continue

                        fresh_count += 1

                        title = (
                            entry.get("title")
                            or ""
                        ).strip()

                        url = (
                            entry.get("link")
                            or ""
                        ).strip()

                        if not title or not url:
                            continue

                        logger.info(
                            "Fresh: %s",
                            title,
                        )

                        # -------------------------------------------------
                        # FULL TEXT EXTRACTION
                        # -------------------------------------------------

                        full_text = await fetch_article(
                            article_session,
                            url,
                        )

                        # If direct extraction failed, try the existing
                        # crawler strategy. Still validate the result.
                        if not is_valid_article_text(
                            full_text
                        ):
                            try:

                                candidate = (
                                    await crawler.fetch_text(
                                        url
                                    )
                                )

                                candidate = clean_text(
                                    candidate
                                )

                                if is_valid_article_text(
                                    candidate
                                ):
                                    full_text = candidate

                            except Exception as exc:
                                logger.warning(
                                    "Crawler article extraction failed: %s | %s",
                                    url,
                                    exc,
                                )

                        # Never store RSS summaries as article full text.
                        if not is_valid_article_text(
                            full_text
                        ):
                            logger.warning(
                                "Skipping article without valid full text: %s",
                                url,
                            )
                            continue

                        valid_full_text_count += 1

                        # -------------------------------------------------
                        # ENTITY RESOLUTION / LLM EXTRACTION
                        # -------------------------------------------------

                        entity_name = (
                            resolver.canonical_or_self(
                                source["name"]
                            )
                        )

                        if orchestrator.enabled():

                            extraction = (
                                await orchestrator.extract(
                                    full_text[:12000],
                                    url,
                                )
                            )

                            if extraction:

                                entity_name = (
                                    resolver.canonical_or_self(
                                        extraction.entity_name
                                    )
                                )

                        # -------------------------------------------------
                        # BUILD RECORD
                        # -------------------------------------------------

                        news_entity = NewsEntity(
                            source=SourceInfo(
                                name=source["name"],
                                url=url,
                            ),
                            content=NewsContent(
                                title=title,
                                published_date=(
                                    published_dt.isoformat()
                                ),
                                full_text=full_text,
                                entity_name=entity_name,
                            ),
                            collectedAt=collected_at,
                        )

                        records.append(
                            news_row(
                                news_entity
                            )
                        )

                    logger.info(
                        "Source %s fresh entries: %s",
                        source["name"],
                        fresh_count,
                    )

                    logger.info(
                        "Source %s valid full text: %s",
                        source["name"],
                        valid_full_text_count,
                    )

                except Exception as exc:

                    logger.warning(
                        "Source error for %s: %s",
                        source["name"],
                        exc,
                    )

    # -----------------------------------------------------
    # DATASET VALIDATION
    # -----------------------------------------------------

    df = pd.DataFrame(
        records
    )

    if df.empty:
        raise RuntimeError(
            "No fresh news records with valid full text found."
        )

    df = df.drop_duplicates(
        subset=["source.url"],
        keep="first",
    )

    # Final full-text validation before writing.
    df = df[
        df["content.full_text"]
        .astype(str)
        .apply(
            is_valid_article_text
        )
    ].copy()

    if df.empty:
        raise RuntimeError(
            "No valid full-text news records remain after validation."
        )

    df = df.sort_values(
        "content.published_date",
        ascending=False,
    )

    DATA_DIR.mkdir(
        exist_ok=True
    )

    df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8",
    )

    # -----------------------------------------------------
    # FINAL REPORT
    # -----------------------------------------------------

    full_text_count = (
        df["content.full_text"]
        .astype(str)
        .apply(
            is_valid_article_text
        )
        .sum()
    )

    print()
    print(
        "==================================="
    )
    print(
        "NEWS DATASET COMPLETE"
    )
    print(
        "==================================="
    )

    print(
        "Fresh news records:",
        len(df),
    )

    print(
        "Unique sources:",
        df["source.name"].nunique(),
    )

    print(
        "Records with valid full text:",
        full_text_count,
    )

    print(
        "Unique URLs:",
        df["source.url"].nunique(),
    )

    print(
        "Sources:",
        ", ".join(
            sorted(
                df["source.name"]
                .dropna()
                .unique()
            )
        ),
    )

    print(
        "Output:",
        OUTPUT_FILE,
    )

    print(
        "==================================="
    )


if __name__ == "__main__":
    asyncio.run(
        collect_news()
    )