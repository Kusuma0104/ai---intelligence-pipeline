import asyncio
import aiohttp
import feedparser
import pandas as pd

from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dateparser import parse
from src.utils.dates import normalize_date


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_FILE = DATA_DIR / "news_24h.csv"


NEWS_SOURCES = [
    {
        "name": "OpenAI",
        "feed": "https://openai.com/news/rss.xml",
    },
    {
        "name": "Google AI",
        "feed": "https://blog.google/technology/ai/rss/",
    },
    {
        "name": "Hugging Face",
        "feed": "https://huggingface.co/blog/feed.xml",
    },
    {
        "name": "MarkTechPost",
        "feed": "https://www.marktechpost.com/feed/",
    },
    {
        "name": "TechCrunch AI",
        "feed": "https://techcrunch.com/category/artificial-intelligence/feed/",
    },
]


def parse_date(entry):
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

        parsed = datetime.fromisoformat(normalized)
        
        if parsed:
            if parsed.tzinfo is None:
                parsed = parsed.replace(
                    tzinfo=timezone.utc
                )

            return parsed.astimezone(timezone.utc)

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

    timeout = aiohttp.ClientTimeout(
        total=60
    )

    async with aiohttp.ClientSession(
        timeout=timeout
    ) as session:

        for source in NEWS_SOURCES:

            print()
            print(
                "Source:",
                source["name"]
            )

            try:

                async with session.get(
                    source["feed"]
                ) as response:

                    print(
                        "HTTP status:",
                        response.status
                    )

                    if response.status != 200:
                        print(
                            "Skipping source."
                        )
                        continue

                    xml = await response.text()

                feed = feedparser.parse(
                    xml
                )

                print(
                    "Feed entries:",
                    len(feed.entries)
                )

                for entry in feed.entries:

                    published_dt = parse_date(
                        entry
                    )

                    if not published_dt:
                        continue

                    if published_dt < cutoff:
                        continue

                    title = (
                        entry.get(
                            "title",
                            ""
                        )
                        .strip()
                    )

                    url = (
                        entry.get(
                            "link",
                            ""
                        )
                        .strip()
                    )

                    if not title or not url:
                        continue

                    print(
                        "Fresh:",
                        title
                    )

                    full_text = (
                        await fetch_article(
                            session,
                            url
                        )
                    )

                    if not full_text:

                        summary = (
                            entry.get(
                                "summary",
                                ""
                            )
                        )

                        full_text = (
                            clean_text(
                                summary
                            )
                        )

                    records.append({
                        "schemaVersion": "1.0",
                        "recordType": "NEWS",
                        "title": title,
                        "published_date": (
                            published_dt
                            .isoformat()
                        ),
                        "source_name": (
                            source["name"]
                        ),
                        "source_url": url,
                        "full_text": full_text,
                    })

            except Exception as exc:

                print(
                    "Source error:",
                    exc
                )

    df = pd.DataFrame(
        records
    )

    if df.empty:
        raise RuntimeError(
            "No fresh news records found."
        )

    df = df.drop_duplicates(
        subset=["source_url"],
        keep="first"
    )

    df = df.sort_values(
        "published_date",
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
        df["source_name"].nunique()
    )

    print(
        "Records with full text:",
        (
            df["full_text"]
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