import asyncio
import aiohttp
from pathlib import Path
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_FILE = DATA_DIR / "products_1000.csv"

AIFOXX_URL = (
    "https://raw.githubusercontent.com/"
    "withkarann/aifoxx/main/src/data/tools.json"
)

BEST_AI_URL = "https://bestaihub.cc/index.json"


async def fetch_json(session, url):
    async with session.get(url) as response:
        print("Source:", url)
        print("HTTP status:", response.status)

        if response.status != 200:
            print("Failed to fetch source.")
            return []

        return await response.json(content_type = None)


async def collect_products():

    print()
    print("===================================")
    print("Building 1000 AI products")
    print("===================================")

    timeout = aiohttp.ClientTimeout(total=120)

    async with aiohttp.ClientSession(
        timeout=timeout
    ) as session:

        # Source 1
        aifoxx = await fetch_json(
            session,
            AIFOXX_URL
        )

        print(
            "AIFOXX records received:",
            len(aifoxx)
        )

        # Source 2
        best_ai = await fetch_json(
            session,
            BEST_AI_URL
        )

        print(
            "Best of AI records received:",
            len(best_ai)
        )

    products = []

    # AIFOXX
    for item in aifoxx:

        name = str(
            item.get("name", "")
        ).strip()

        website = str(
            item.get("url", "")
        ).strip()

        if not name or not website:
            continue

        products.append({
            "schemaVersion": "1.0",
            "recordType": "PRODUCT",
            "name": name,
            "description": item.get(
                "description",
                ""
            ),
            "category": item.get(
                "category",
                ""
            ),
            "pricing": item.get(
                "pricing",
                ""
            ),
            "website": website,
            "source_name": "AIFOXX",
            "source_url": website,
        })

    # Best of AI
    for item in best_ai:

        name = str(
            item.get("name", "")
        ).strip()

        website = str(
            item.get("website", "")
        ).strip()

        if not name or not website:
            continue

        products.append({
            "schemaVersion": "1.0",
            "recordType": "PRODUCT",
            "name": name,
            "description": item.get(
                "description",
                ""
            ),
            "category": item.get(
                "category",
                ""
            ),
            "pricing": item.get(
                "price",
                ""
            ),
            "website": website,
            "source_name": "Best of AI",
            "source_url": website,
        })

    # Convert to DataFrame
    df = pd.DataFrame(products)

    if df.empty:
        raise RuntimeError(
            "No product records collected."
        )

    # Clean names
    df["name"] = (
        df["name"]
        .astype(str)
        .str.strip()
    )

    # Clean websites
    df["website"] = (
        df["website"]
        .astype(str)
        .str.strip()
    )

    # Remove empty values
    df = df[
        (df["name"] != "")
        & (df["website"] != "")
    ]

    # Remove duplicate product + website
    df = df.drop_duplicates(
        subset=["name", "website"],
        keep="first"
    )

    print()
    print(
        "Combined unique products:",
        len(df)
    )

    if len(df) < 1000:
        raise RuntimeError(
            "Less than 1000 real products "
            "were found."
        )

    # Keep exactly 1000
    df = df.head(1000)

    DATA_DIR.mkdir(
        exist_ok=True
    )

    df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8"
    )

    print()
    print("===================================")
    print("PRODUCT DATASET COMPLETE")
    print("===================================")
    print(
        "AI products saved:",
        len(df)
    )
    print(
        "Unique product names:",
        df["name"].nunique()
    )
    print(
        "Products with website:",
        (
            df["website"]
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

if __name__ == "__main__":
    asyncio.run(collect_products())