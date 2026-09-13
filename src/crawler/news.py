import asyncio
import aiohttp
import feedparser
import pandas as pd

from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dateparser import parse
from src.utils.dates import normalize_date
from src.crawler.async_crawler import AsyncCrawler
from src.extraction.llm_orchestrator import LLMOrchestrator
from src.extraction.schemas import NewsContent, NewsEntity, SourceInfo, news_row
from src.resolution.entity_resolver import EntityResolver
from src.utils.logging import get_logger

logger = get_logger("news")


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_FILE = DATA_DIR / "news_24h.csv"


NEWS_SOURCES = [
    {"name": "OpenAI", "feed": "https://openai.com/news/rss.xml"},
    {"name": "Wired AI", "feed": "https://www.wired.com/feed/tag/ai/latest/rss"},
    {"name": "Ars Technica AI", "feed": "https://arstechnica.com/ai/feed/"},
    {"name": "The Verge AI", "feed": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"},
    {"name": "TechCrunch AI", "feed": "https://techcrunch.com/category/artificial-intelligence/feed/"},
]

def parse_date(entry):
    # Prefer feedparser's structured date values
    for field in ("published_parsed", "updated_parsed", "created_parsed"):
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

    # Fallback to textual date fields
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
            parsed = datetime.fromisoformat(normalized)

            if parsed.tzinfo is None:
                parsed = parsed.replace(
                    tzinfo=timezone.utc
                )

            return parsed.astimezone(timezone.utc)

        except Exception:
            continue

    return None


def clean_text(html):
    soup = BeautifulSoup(
        html or "",
        "html.parser"
    )

    for tag in soup(
        ["script", "style", "noscript"]
    ):
        tag.decompose()

    return " ".join(
        soup.stripped_strings
    )


async def fetch_article(
    session,
    url
):
    try:
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=30),
            headers={
                "User-Agent":
                    "AI-Intelligence-Pipeline/1.0"
            },
        ) as response:

            if response.status != 200:
                return ""

            html = await response.text()

            soup = BeautifulSoup(
                html,
                "html.parser"
            )

            article = soup.find("article")

            if article:
                text = clean_text(
                    str(article)
                )
            else:
                main = soup.find("main")

                if main:
                    text = clean_text(
                        str(main)
                    )
                else:
                    paragraphs = soup.find_all(
                        "p"
                    )

                    text = " ".join(
                        p.get_text(
                            " ",
                            strip=True
                        )
                        for p in paragraphs
                    )

            return text.strip()

    except Exception as exc:
        print(
            f"Article extraction failed: "
            f"{url} | {exc}"
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
        now.isoformat()
    )

    print(
        "24-hour cutoff:",
        cutoff.isoformat()
    )

    records = []
    resolver = EntityResolver()
    orchestrator = LLMOrchestrator()
    collected_at = datetime.now(timezone.utc)

    async with AsyncCrawler() as crawler:
        for source in NEWS_SOURCES:
            logger.info("Source: %s", source["name"])
            try:
                xml = await crawler.fetch_text(source["feed"], allow_js_fallback=False)
                if not xml:
                    logger.warning("Skipping source %s", source["name"])
                    continue

                feed = feedparser.parse(xml)
                logger.info("Feed entries: %s", len(feed.entries))
                logger.info("Feed bozo: %s", feed.bozo)
                logger.info("Feed status: %s", getattr(feed, "status", "unknown"))

                fresh_count = 0

                for entry in feed.entries:
                    published_dt = parse_date(entry)

                    if (
                        not published_dt
                        or published_dt < cutoff
                        or published_dt > now
                    ):
                        continue

                    fresh_count += 1

                    title = (entry.get("title") or "").strip()
                    url = (entry.get("link") or "").strip()

                    if not title or not url:
                        continue

                    logger.info("Fresh: %s", title)


                    full_text = await crawler.fetch_text(url)
                    if not full_text:
                        full_text = clean_text(entry.get("summary") or "")

                    entity_name = resolver.canonical_or_self(source["name"])
                    if orchestrator.enabled():
                        extraction = await orchestrator.extract(full_text[:12000], url)
                        if extraction:
                            entity_name = resolver.canonical_or_self(
                                extraction.entity_name
                            )

                    news_entity = NewsEntity(
                        source=SourceInfo(name=source["name"], url=url),
                        content=NewsContent(
                            title=title,
                            published_date=published_dt.isoformat(),
                            full_text=full_text,
                            entity_name=entity_name,
                        ),
                        collectedAt=collected_at,
                    )
                    records.append(news_row(news_entity))
                logger.info(
                    "Source %s fresh entries: %s",
                    source["name"],
                    fresh_count
                    )
            except Exception as exc:
                logger.warning("Source error for %s: %s", source["name"], exc)

    df = pd.DataFrame(
        records
    )

    if df.empty:
        raise RuntimeError(
            "No fresh news records found."
        )

    df = df.drop_duplicates(
        subset=["source.url"],
        keep="first"
    )

    df = df.sort_values(
        "content.published_date",
        ascending=False
    )

    DATA_DIR.mkdir(
        exist_ok=True
    )

    df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8"
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
        len(df)
    )

    print(
        "Unique sources:",
        df["source.name"].nunique()
    )

    print(
        "Records with full text:",
        (
            df["content.full_text"]
            .astype(str)
            .str.strip()
            .ne("")
            .sum()
        )
    )

    print(
        "Output:",
        OUTPUT_FILE
    )

    print(
        "==================================="
    )


if __name__ == "__main__":
    asyncio.run(
        collect_news()
    )
