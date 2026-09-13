import asyncio
from datetime import datetime, timezone

import pandas as pd
from pydantic import ValidationError

from src.config import DATA_DIR
from src.crawler.async_crawler import AsyncCrawler
from src.extraction.llm_orchestrator import LLMOrchestrator
from src.extraction.schemas import (
    PricingModel,
    ProductContent,
    ProductEntity,
    SourceInfo,
    product_row,
)
from src.resolution.entity_resolver import EntityResolver
from src.utils.logging import get_logger

logger = get_logger("products")

OUTPUT_FILE = DATA_DIR / "products_1000.csv"

AIFOXX_URL = (
    "https://raw.githubusercontent.com/withkarann/aifoxx/main/src/data/tools.json"
)
BEST_AI_URL = "https://bestaihub.cc/index.json"


def _http_url(value: str) -> str:
    value = (value or "").strip()
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return ""


async def collect_products(limit: int = 1000, use_llm: bool = False):
    logger.info("Collecting AI products from public directories")
    resolver = EntityResolver()
    orchestrator = LLMOrchestrator() if use_llm else None
    collected_at = datetime.now(timezone.utc)

    async with AsyncCrawler(js_fallback=False) as crawler:
        aifoxx = await crawler.fetch_json(AIFOXX_URL) or []
        best_ai = await crawler.fetch_json(BEST_AI_URL) or []

    logger.info("AIFOXX records: %s", len(aifoxx) if isinstance(aifoxx, list) else 0)
    logger.info("Best of AI records: %s", len(best_ai) if isinstance(best_ai, list) else 0)

    raw_items = []
    if isinstance(aifoxx, list):
        for item in aifoxx:
            website = _http_url(item.get("url"))
            name = str(item.get("name") or "").strip()
            if name and website:
                raw_items.append(
                    {
                        "name": name,
                        "description": str(item.get("description") or ""),
                        "pricing": str(item.get("pricing") or ""),
                        "website": website,
                        "source_name": "AIFOXX",
                    }
                )

    if isinstance(best_ai, list):
        for item in best_ai:
            website = _http_url(item.get("website"))
            name = str(item.get("name") or "").strip()
            if name and website:
                raw_items.append(
                    {
                        "name": name,
                        "description": str(item.get("description") or ""),
                        "pricing": str(item.get("price") or item.get("pricing") or ""),
                        "website": website,
                        "source_name": "Best of AI",
                    }
                )

    records = []
    seen = set()

    for item in raw_items:
        key = (item["name"].lower(), item["website"].lower())
        if key in seen:
            continue
        seen.add(key)

        fallback_startup = resolver.canonical_or_self(item["name"])
        pricing = PricingModel.FREEMIUM
        startup_name = fallback_startup

        if orchestrator:
            classified = await orchestrator.classify_product(
                item["name"],
                item["description"],
                item["pricing"],
                fallback_startup,
            )
            pricing = classified.pricingModel
            startup_name = resolver.canonical_or_self(classified.startupName)
        else:
            from src.extraction.classifiers import classify_pricing

            pricing = classify_pricing(item["pricing"], item["description"])

        try:
            entity = ProductEntity(
                source=SourceInfo(name=item["source_name"], url=item["website"]),
                content=ProductContent(
                    startupName=startup_name,
                    pricingModel=pricing,
                ),
                collectedAt=collected_at,
            )
        except ValidationError:
            continue

        row = product_row(entity)
        row["product_name"] = item["name"]
        row["description"] = item["description"]
        records.append(row)

        if len(records) >= limit:
            break

    df = pd.DataFrame(records)
    if df.empty or len(df) < limit:
        raise RuntimeError(
            f"Only {len(df)} unique products found. Need at least {limit}."
        )

    df = df.head(limit)
    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")
    logger.info("Saved %s products to %s", len(df), OUTPUT_FILE)
    return df


if __name__ == "__main__":
    asyncio.run(collect_products())
