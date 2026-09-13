import asyncio
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from pydantic import HttpUrl, ValidationError

from src.config import DATA_DIR
from src.crawler.async_crawler import AsyncCrawler
from src.extraction.schemas import (
    SourceInfo,
    StartupContent,
    StartupData,
    StartupEntity,
    startup_row,
)
from src.resolution.entity_resolver import EntityResolver
from src.utils.logging import get_logger

logger = get_logger("startups")

OUTPUT_FILE = DATA_DIR / "startups_1000.csv"

TAGS = [
    ("artificial-intelligence", "Artificial Intelligence"),
    ("ai", "AI"),
    ("generative-ai", "Generative AI"),
    ("machine-learning", "Machine Learning"),
    ("ai-assistant", "AI Assistant"),
    ("computer-vision", "Computer Vision"),
    ("conversational-ai", "Conversational AI"),
    ("deep-learning", "Deep Learning"),
    ("aiops", "AIOps"),
    ("robotics", "Robotics"),
]

BASE_URL = "https://yc-oss.github.io/api/tags"


def _as_url(value: str, fallback: str) -> str:
    candidate = (value or "").strip() or fallback
    if candidate.startswith("http://") or candidate.startswith("https://"):
        return candidate
    return fallback


def parse_employee_count(raw) -> Optional[int]:
    if raw in (None, "", "None"):
        return None
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


async def fetch_startups(limit: int = 1000):
    logger.info("Collecting AI startups from Y Combinator public tag dumps")
    resolver = EntityResolver()
    collected_at = datetime.now(timezone.utc)
    records = []

    async with AsyncCrawler(js_fallback=False) as crawler:
        for slug, tag_name in TAGS:
            url = f"{BASE_URL}/{slug}.json"
            data = await crawler.fetch_json(url)
            if not isinstance(data, list):
                logger.warning("Skipping %s", tag_name)
                continue

            logger.info("%s: %s records", tag_name, len(data))
            for company in data:
                name = str(company.get("name") or "").strip()
                if not name:
                    continue

                yc_url = str(company.get("url") or "").strip()
                website = str(company.get("website") or "").strip()
                source_url = _as_url(yc_url or website, url)

                try:
                    entity = StartupEntity(
                        source=SourceInfo(name="Y Combinator", url=source_url),
                        content=StartupContent(
                            entityName=resolver.canonical_or_self(name),
                            data=StartupData(
                                employeeCount=parse_employee_count(
                                    company.get("team_size")
                                )
                            ),
                        ),
                        collectedAt=collected_at,
                    )
                except ValidationError:
                    continue

                row = startup_row(entity)
                row["raw_name"] = name
                row["website"] = website
                row["yc_tag"] = tag_name
                records.append(row)

            await asyncio.sleep(0.2)

    df = pd.DataFrame(records)
    if df.empty:
        raise RuntimeError("No startup records were collected.")

    df = df.drop_duplicates(subset=["content.entityName"], keep="first")
    logger.info("Unique AI startups: %s", len(df))
    if len(df) < limit:
        raise RuntimeError(f"Only {len(df)} unique AI startups found. Need at least {limit}.")

    df = df.head(limit)
    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")
    logger.info("Saved %s startups to %s", len(df), OUTPUT_FILE)
    return df


if __name__ == "__main__":
    asyncio.run(fetch_startups())
