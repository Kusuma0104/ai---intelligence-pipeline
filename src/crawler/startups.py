import asyncio
from pathlib import Path

import aiohttp
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

OUTPUT_FILE = DATA_DIR / "startups_1000.csv"


# Real YC AI-related public datasets
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


async def fetch_tag(session, slug, tag_name):

    url = f"{BASE_URL}/{slug}.json"

    try:

        async with session.get(url) as response:

            print(
                f"{tag_name}: HTTP {response.status}"
            )

            if response.status != 200:

                print(
                    f"Skipping {tag_name}"
                )

                return []

            data = await response.json()

            print(
                f"{tag_name}: "
                f"{len(data)} records"
            )

            records = []

            for company in data:

                records.append({

                    "schemaVersion": "1.0",

                    "recordType": "STARTUP",

                    "name": company.get(
                        "name",
                        ""
                    ),

                    "slug": company.get(
                        "slug",
                        ""
                    ),

                    "website": company.get(
                        "website",
                        ""
                    ),

                    "yc_url": company.get(
                        "url",
                        ""
                    ),

                    "description": company.get(
                        "one_liner",
                        company.get(
                            "description",
                            ""
                        )
                    ),

                    "batch": company.get(
                        "batch",
                        ""
                    ),

                    "location": company.get(
                        "location",
                        ""
                    ),

                    "status": company.get(
                        "status",
                        ""
                    ),

                    "yc_tag": tag_name,

                    "source_name":
                        "Y Combinator",

                    "source_url": url,
                })

            return records

    except Exception as exc:

        print(
            f"Error fetching "
            f"{tag_name}: {exc}"
        )

        return []


async def fetch_startups():

    print()
    print("===================================")
    print("Building 1000 AI startups")
    print("===================================")


    timeout = aiohttp.ClientTimeout(
        total=60
    )


    all_records = []


    async with aiohttp.ClientSession(
        timeout=timeout
    ) as session:

        for slug, tag_name in TAGS:

            records = await fetch_tag(
                session,
                slug,
                tag_name
            )

            all_records.extend(records)

            await asyncio.sleep(0.5)


    print()
    print(
        f"Total records collected: "
        f"{len(all_records)}"
    )


    # ---------------------------------
    # Convert to DataFrame
    # ---------------------------------

    df = pd.DataFrame(
        all_records
    )


    if df.empty:

        raise RuntimeError(
            "No startup records were collected."
        )


    # ---------------------------------
    # Clean names
    # ---------------------------------

    df["name"] = (
        df["name"]
        .astype(str)
        .str.strip()
    )


    df = df[
        df["name"] != ""
    ]


    # ---------------------------------
    # Remove duplicate companies
    # ---------------------------------

    df = df.drop_duplicates(
        subset=["name"],
        keep="first"
    )


    print(
        f"Unique AI startups: "
        f"{len(df)}"
    )


    # ---------------------------------
    # Need at least 1000
    # ---------------------------------

    if len(df) < 1000:

        raise RuntimeError(
            f"Only {len(df)} unique "
            f"AI startups found. "
            f"Need at least 1000."
        )


    # ---------------------------------
    # Keep exactly 1000
    # ---------------------------------

    df = df.head(1000)


    # ---------------------------------
    # Save
    # ---------------------------------

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
    print("STARTUP DATASET COMPLETE")
    print("===================================")

    print(
        f"AI startups saved: "
        f"{len(df)}"
    )

    print(
        f"Unique startup names: "
        f"{df['name'].nunique()}"
    )

    print(
        f"Records with website: "
        f"{(df['website'].astype(str).str.strip() != '').sum()}"
    )

    print(
        f"Output: {OUTPUT_FILE}"
    )

    print("===================================")


if __name__ == "__main__":

    asyncio.run(
        fetch_startups()
    )