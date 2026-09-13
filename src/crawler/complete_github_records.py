import asyncio
import csv
import os
import random
import re
import time
from pathlib import Path

import aiohttp
import pandas as pd
from dotenv import load_dotenv
import feedparser


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

INPUT_FILE = DATA_DIR / "research_papers_complete.csv"
OUTPUT_FILE = DATA_DIR / "research_papers_1000_verified.csv"

PWC_URL = (
    "https://huggingface.co/datasets/"
    "pwc-archive/links-between-paper-and-code/"
    "resolve/main/data/train-00000-of-00001.parquet"
)

GITHUB_API = "https://api.github.com"


load_dotenv(PROJECT_ROOT / ".env")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

if not GITHUB_TOKEN:
    raise RuntimeError(
        "GITHUB_TOKEN not found. Check your .env file."
    )


HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2026-03-10",
    "User-Agent": "AI-Intelligence-Pipeline/1.0",
}


def extract_github_repo(url):

    if not url:
        return None

    match = re.search(
        r"github\.com/([^/]+)/([^/#?]+)",
        str(url)
    )

    if not match:
        return None

    return (
        match.group(1),
        match.group(2).replace(".git", "")
    )

async def fetch_arxiv_metadata(session, arxiv_id):
    """Fetch authoritative metadata for a paper from arXiv."""
    url = (
        "https://export.arxiv.org/api/query"
        f"?search_query=id:{arxiv_id}&max_results=1"
    )

    try:
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as response:
            if response.status != 200:
                return {}

            content = await response.text()

        feed = feedparser.parse(content)

        if not feed.entries:
            return {}

        entry = feed.entries[0]

        authors = [
            author.name
            for author in entry.get("authors", [])
            if hasattr(author, "name")
        ]

        return {
            "title": " ".join(entry.get("title", "").split()),
            "authors": "; ".join(authors),
            "paper_url": entry.get("link", ""),
            "published_date": entry.get("published", ""),
        }

    except Exception as exc:
        print(f"arXiv metadata lookup failed for {arxiv_id}: {exc}")
        return {}

async def verify_repository(session, github_url):

    repo_info = extract_github_repo(github_url)

    if not repo_info:
        return None

    owner, repo = repo_info

    url = f"{GITHUB_API}/repos/{owner}/{repo}"

    for attempt in range(5):

        try:

            async with session.get(
                url,
                headers=HEADERS,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:

                if response.status == 200:

                    data = await response.json()

                    return {
                        "github_url": data.get("html_url"),
                        "github_stars": data.get(
                            "stargazers_count"
                        ),
                        "github_forks": data.get(
                            "forks_count"
                        ),
                        "github_watchers": data.get(
                            "watchers_count"
                        ),
                    }

                if response.status == 404:
                    return None

                if response.status in (403, 429):

                    retry_after = response.headers.get(
                        "Retry-After"
                    )

                    reset = response.headers.get(
                        "X-RateLimit-Reset"
                    )

                    remaining = response.headers.get(
                        "X-RateLimit-Remaining"
                    )

                    if retry_after:

                        wait_time = float(retry_after)

                    elif remaining == "0" and reset:

                        wait_time = max(
                            1,
                            int(reset) - int(time.time())
                        )

                    else:

                        wait_time = (
                            min(60, 2 ** attempt)
                            + random.uniform(0, 1)
                        )

                    print(
                        f"Rate limit HTTP {response.status}. "
                        f"Waiting {wait_time:.1f}s..."
                    )

                    await asyncio.sleep(wait_time)
                    continue

                if response.status >= 500:

                    wait_time = (
                        min(30, 2 ** attempt)
                        + random.uniform(0, 1)
                    )

                    print(
                        f"Server error HTTP "
                        f"{response.status}. Retrying..."
                    )

                    await asyncio.sleep(wait_time)
                    continue

                return None

        except asyncio.TimeoutError:

            wait_time = (
                min(30, 2 ** attempt)
                + random.uniform(0, 1)
            )

            print(
                f"Timeout. Waiting "
                f"{wait_time:.1f}s..."
            )

            await asyncio.sleep(wait_time)

        except Exception as exc:

            print(f"Request error: {exc}")
            return None

    return None


async def complete_records():

    print()
    print("===================================")
    print("Building 1000 verified GitHub records")
    print("===================================")


    if not INPUT_FILE.exists():

        raise FileNotFoundError(
            f"Input file not found: {INPUT_FILE}"
        )


    papers = pd.read_csv(INPUT_FILE)

        # Restore authoritative publication dates from the original arXiv dataset
    metadata_file = DATA_DIR / "research_papers.csv"

    if metadata_file.exists():
        metadata = pd.read_csv(metadata_file)

        if "arxiv_id" in metadata.columns and "published_date" in metadata.columns:
            date_map = (
                metadata.dropna(subset=["arxiv_id"])
                .assign(arxiv_id=lambda x: x["arxiv_id"].astype(str).str.strip())
                .set_index("arxiv_id")["published_date"]
                .to_dict()
            )

            papers["arxiv_id"] = papers["arxiv_id"].astype(str).str.strip()

            papers["published_date"] = papers.apply(
                lambda row: (
                    date_map.get(row["arxiv_id"], "")
                    if not str(row.get("published_date", "")).strip()
                    else row["published_date"]
                ),
                axis=1,
            )

    papers["github_stars"] = pd.to_numeric(
        papers["github_stars"],
        errors="coerce"
    )


    verified = papers[
        papers["github_stars"].notna()
    ].copy()


    missing = papers[
        papers["github_stars"].isna()
    ].copy()


    print(
        f"Existing papers: {len(papers)}"
    )

    print(
        f"Already verified: {len(verified)}"
    )

    print(
        f"Missing: {len(missing)}"
    )


    # ---------------------------------
    # Load real Papers With Code data
    # ---------------------------------

    print()
    print("Loading Papers With Code archive...")

    pwc = pd.read_parquet(PWC_URL)

    print(
        f"Archive records: {len(pwc)}"
    )


    pwc = pwc[
        pwc["paper_arxiv_id"].notna()
        & pwc["repo_url"].notna()
    ].copy()


    pwc["paper_arxiv_id"] = (
        pwc["paper_arxiv_id"]
        .astype(str)
        .str.strip()
    )

    pwc["repo_url"] = (
        pwc["repo_url"]
        .astype(str)
        .str.strip()
    )


    # Prefer official implementations
    pwc["priority"] = (
        pwc["is_official"]
        .fillna(False)
        .astype(int)
    )


    pwc = pwc.sort_values(
        [
            "priority",
            "mentioned_in_paper",
            "mentioned_in_github"
        ],
        ascending=False
    )


    # ---------------------------------
    # Used papers and repositories
    # ---------------------------------

    used_papers = set(
        verified["arxiv_id"]
        .dropna()
        .astype(str)
    )

    used_repos = set(
        verified["github_url"]
        .dropna()
        .astype(str)
    )


    # ---------------------------------
    # First try missing papers
    # ---------------------------------

    async with aiohttp.ClientSession() as session:

        for index in missing.index:

            if verified["paper_url"].nunique() >= 1000:
                break


            arxiv_id = str(
                papers.loc[index, "arxiv_id"]
            ).strip()


            candidates = pwc[
                pwc["paper_arxiv_id"] == arxiv_id
            ]


            for candidate in candidates.itertuples(index=False):

                repo_url = candidate.repo_url

                if repo_url in used_repos:
                    continue


                result = await verify_repository(
                    session,
                    repo_url
                )


                if result:

                    papers.loc[
                        index,
                        "github_url"
                    ] = result["github_url"]

                    papers.loc[
                        index,
                        "github_stars"
                    ] = result["github_stars"]

                    papers.loc[
                        index,
                        "github_forks"
                    ] = result["github_forks"]

                    papers.loc[
                        index,
                        "github_watchers"
                    ] = result["github_watchers"]


                    used_repos.add(
                        result["github_url"]
                    )

                    verified = pd.concat(
                        [
                            verified,
                            papers.loc[
                                [index]
                            ]
                        ]
                    )

                    print(
                        f"Replacement verified: "
                        f"{result['github_url']} "
                        f"| stars="
                        f"{result['github_stars']}"
                    )

                    break


                await asyncio.sleep(0.2)


        # ---------------------------------
        # Add new verified papers if needed
        # ---------------------------------

        if len(verified) < 1000:

            print()
            print(
                "Searching for additional "
                "verified paper/repository records..."
            )


            for _, candidate in pwc.iterrows():

                if verified["paper_url"].nunique() >= 1000:
                    break


                arxiv_id = candidate[
                    "paper_arxiv_id"
                ]


                repo_url = candidate[
                    "repo_url"
                ]


                if arxiv_id in used_papers:
                    continue


                if repo_url in used_repos:
                    continue


                result = await verify_repository(
                    session,
                    repo_url
                )


                if not result:
                    await asyncio.sleep(0.2)
                    continue


                metadata = await fetch_arxiv_metadata(
                    session,
                    arxiv_id,
                )

                new_record = {
                    "schemaVersion": "1.0",
                    "recordType": "RESEARCH_PAPER",
                    "title": metadata.get(
                        "title"
                    ) or candidate["paper_title"],
                    "authors": metadata.get(
                        "authors",
                        "",
                    ),
                    "paper_url": metadata.get(
                        "paper_url"
                    ) or candidate["paper_url_abs"],
                    "github_url": result[
                        "github_url"
                    ],
                    "github_stars": result[
                        "github_stars"
                    ],
                    "published_date": metadata.get(
                        "published_date",
                        "",
                    ),
                    "source_name": "arXiv",
                    "arxiv_id": arxiv_id,
                    "github_forks": result[
                        "github_forks"
                    ],
                    "github_watchers": result[
                        "github_watchers"
                    ],
                }

                papers = pd.concat(
                    [
                        papers,
                        pd.DataFrame([new_record])
                    ],
                    ignore_index=True
                )


                verified = pd.concat(
                    [
                        verified,
                        pd.DataFrame([new_record])
                    ],
                    ignore_index=True
                )


                used_papers.add(arxiv_id)
                used_repos.add(
                    result["github_url"]
                )


                print(
                    f"Added verified paper "
                    f"{len(verified)}/1000: "
                    f"{result['github_url']} "
                    f"| stars="
                    f"{result['github_stars']}"
                )


                await asyncio.sleep(0.2)


    # ---------------------------------
    # Keep exactly 1000 verified records
    # ---------------------------------

    papers["github_stars"] = pd.to_numeric(
        papers["github_stars"],
        errors="coerce"
    )


    papers = papers[
        papers["github_stars"].notna()
    ].copy()


    papers = papers.drop_duplicates(
        subset=["paper_url"],
        keep="first"
    )

    if len(papers) < 1000:
        print(
            f"WARNING: only {len(papers)} unique verified papers "
            f"available after deduplication."
        )


    papers = papers.head(1000)

        # ---------------------------------
    # Backfill missing arXiv publication dates
    # ---------------------------------

    missing_date_indexes = papers[
        papers["published_date"].isna()
        | (papers["published_date"].astype(str).str.strip() == "")
    ].index.tolist()

    if missing_date_indexes:
        print()
        print(
            f"Fetching arXiv publication dates for "
            f"{len(missing_date_indexes)} papers..."
        )

        async with aiohttp.ClientSession() as session:
            for index in missing_date_indexes:
                arxiv_id = str(
                    papers.loc[index, "arxiv_id"]
                ).strip()

                if not arxiv_id or arxiv_id.lower() == "nan":
                    continue

                metadata = await fetch_arxiv_metadata(
                    session,
                    arxiv_id,
                )

                published_date = metadata.get(
                    "published_date",
                    "",
                )

                if published_date:
                    papers.loc[
                        index,
                        "published_date"
                    ] = published_date

                await asyncio.sleep(0.2)


    papers.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8"
    )


    print()
    print("===================================")
    print("FINAL RESEARCH PAPER DATASET")
    print("===================================")

    print(
        f"Total verified papers: "
        f"{len(papers)}"
    )

    print(
        f"Unique GitHub repositories: "
        f"{papers['github_url'].nunique()}"
    )

    print(
        f"Output: {OUTPUT_FILE}"
    )

    print("===================================")


if __name__ == "__main__":

    asyncio.run(
        complete_records()
    )
