import asyncio
import csv
import re
from pathlib import Path
from urllib.parse import urlencode

import aiohttp
import feedparser


ARXIV_API = "https://export.arxiv.org/api/query"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_FILE = DATA_DIR / "research_papers.csv"


def clean_text(text: str) -> str:
    """Remove extra whitespace from scraped text."""
    return " ".join(text.split())


def extract_arxiv_id(url: str) -> str:
    """Extract the arXiv ID from an arXiv URL."""
    match = re.search(r"arxiv\.org/(?:abs|pdf)/([^/?]+)", url)

    if match:
        return re.sub(r"v\d+$", "", match.group(1))

    return url.rsplit("/", 1)[-1]


async def fetch_batch(
    session: aiohttp.ClientSession,
    start: int,
    batch_size: int = 100,
):
    """Fetch one page of arXiv results."""

    params = {
        "search_query": "cat:cs.AI OR cat:cs.LG OR cat:cs.CL",
        "start": start,
        "max_results": batch_size,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }

    url = f"{ARXIV_API}?{urlencode(params)}"

    print(f"Fetching papers {start} - {start + batch_size - 1}")

    async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as response:

        if response.status != 200:
            raise RuntimeError(
                f"arXiv request failed: HTTP {response.status}"
            )

        content = await response.text()

    feed = feedparser.parse(content)

    papers = []

    for entry in feed.entries:

        paper_url = entry.get("link", "")

        authors = [
            author.name
            for author in entry.get("authors", [])
            if hasattr(author, "name")
        ]

        paper = {
            "schemaVersion": "1.0",
            "recordType": "RESEARCH_PAPER",
            "title": clean_text(entry.get("title", "")),
            "authors": "; ".join(authors),
            "paper_url": paper_url,
            "github_url": "",
            "github_stars": "",
            "published_date": entry.get("published", ""),
            "source_name": "arXiv",
            "arxiv_id": extract_arxiv_id(paper_url),
        }

        papers.append(paper)

    return papers


async def collect_papers(total: int = 1000):

    DATA_DIR.mkdir(exist_ok=True)

    batch_size = 100
    all_papers = []

    headers = {
        "User-Agent": "AI-Intelligence-Pipeline/1.0"
    }

    async with aiohttp.ClientSession(headers=headers) as session:

        for start in range(0, total, batch_size):

            current_batch = min(batch_size, total - start)

            papers = await fetch_batch(
                session,
                start=start,
                batch_size=current_batch,
            )

            all_papers.extend(papers)

            print(f"Collected so far: {len(all_papers)}")

            # arXiv recommends being polite between repeated API calls.
            if len(all_papers) < total:
                await asyncio.sleep(3)

    # Remove duplicate paper URLs.
    unique = {}

    for paper in all_papers:
        unique[paper["paper_url"]] = paper

    all_papers = list(unique.values())

    with OUTPUT_FILE.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:

        fieldnames = [
            "schemaVersion",
            "recordType",
            "title",
            "authors",
            "paper_url",
            "github_url",
            "github_stars",
            "published_date",
            "source_name",
            "arxiv_id",
        ]

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(all_papers)

    print()
    print("===================================")
    print("Research paper collection complete")
    print(f"Unique papers: {len(all_papers)}")
    print(f"Output: {OUTPUT_FILE}")
    print("===================================")


if __name__ == "__main__":
    asyncio.run(collect_papers(1000))