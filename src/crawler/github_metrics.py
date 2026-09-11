import asyncio
import csv
import os
import random
import re
import time
from pathlib import Path

import aiohttp
from dotenv import load_dotenv


# -----------------------------
# Project paths
# -----------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

INPUT_FILE = DATA_DIR / "research_papers_verified.csv"
OUTPUT_FILE = DATA_DIR / "research_papers_final.csv"

GITHUB_API = "https://api.github.com"


# -----------------------------
# Load GitHub token
# -----------------------------

load_dotenv(PROJECT_ROOT / ".env")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

if not GITHUB_TOKEN:
    raise RuntimeError(
        "GITHUB_TOKEN not found. Please check your .env file."
    )


HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2026-03-10",
    "User-Agent": "AI-Intelligence-Pipeline/1.0",
}


# -----------------------------
# Extract owner/repository
# -----------------------------

def extract_github_repo(url):
    if not url:
        return None

    match = re.search(
        r"github\.com/([^/]+)/([^/#?]+)",
        str(url)
    )

    if not match:
        return None

    owner = match.group(1)
    repo = match.group(2)

    repo = repo.replace(".git", "")

    return owner, repo


# -----------------------------
# Get GitHub repository data
# -----------------------------

async def get_repository(session, github_url):

    repo_info = extract_github_repo(github_url)

    if not repo_info:
        return None

    owner, repo = repo_info

    url = f"{GITHUB_API}/repos/{owner}/{repo}"

    max_retries = 5

    for attempt in range(max_retries):

        try:

            async with session.get(
                url,
                headers=HEADERS,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:

                # -------------------------
                # Successful response
                # -------------------------

                if response.status == 200:

                    data = await response.json()

                    return {
                        "github_url": data.get("html_url"),
                        "github_stars": data.get("stargazers_count"),
                        "github_forks": data.get("forks_count"),
                        "github_watchers": data.get("watchers_count"),
                    }


                # -------------------------
                # Repository not found
                # -------------------------

                if response.status == 404:

                    return None


                # -------------------------
                # Rate limit
                # -------------------------

                if response.status in (403, 429):

                    retry_after = response.headers.get(
                        "Retry-After"
                    )

                    remaining = response.headers.get(
                        "X-RateLimit-Remaining"
                    )

                    reset = response.headers.get(
                        "X-RateLimit-Reset"
                    )

                    if retry_after:

                        wait_time = float(retry_after)

                    elif remaining == "0" and reset:

                        wait_time = max(
                            1,
                            int(reset) - int(time.time())
                        )

                    else:

                        # Exponential backoff + jitter
                        wait_time = (
                            min(60, 2 ** attempt)
                            + random.uniform(0, 1)
                        )

                    print(
                        f"Rate limit HTTP {response.status}. "
                        f"Retrying in {wait_time:.1f}s..."
                    )

                    await asyncio.sleep(wait_time)

                    continue


                # -------------------------
                # Server error
                # -------------------------

                if response.status >= 500:

                    wait_time = (
                        min(30, 2 ** attempt)
                        + random.uniform(0, 1)
                    )

                    print(
                        f"GitHub server error HTTP "
                        f"{response.status}. "
                        f"Retrying in {wait_time:.1f}s..."
                    )

                    await asyncio.sleep(wait_time)

                    continue


                # -------------------------
                # Other error
                # -------------------------

                print(
                    f"GitHub request failed: "
                    f"HTTP {response.status}"
                )

                return None


        except asyncio.TimeoutError:

            wait_time = (
                min(30, 2 ** attempt)
                + random.uniform(0, 1)
            )

            print(
                f"Request timeout. "
                f"Retrying in {wait_time:.1f}s..."
            )

            await asyncio.sleep(wait_time)


        except Exception as exc:

            print(
                f"GitHub request error: {exc}"
            )

            return None


    print(
        f"Failed after {max_retries} attempts: "
        f"{github_url}"
    )

    return None


# -----------------------------
# Main enrichment
# -----------------------------

async def enrich_papers():

    DATA_DIR.mkdir(exist_ok=True)

    if not INPUT_FILE.exists():

        raise FileNotFoundError(
            f"Input file not found: {INPUT_FILE}"
        )


    # -------------------------
    # Load papers
    # -------------------------

    with INPUT_FILE.open(
        "r",
        newline="",
        encoding="utf-8"
    ) as file:

        reader = csv.DictReader(file)

        papers = list(reader)


    print()
    print("===================================")
    print("GitHub enrichment started")
    print("===================================")

    print(f"Research papers loaded: {len(papers)}")


    # -------------------------
    # Count GitHub candidates
    # -------------------------

    github_candidates = [
        paper
        for paper in papers
        if paper.get("github_url")
    ]


    print(
        f"GitHub repositories to verify: "
        f"{len(github_candidates)}"
    )


    # -------------------------
    # Process repositories
    # -------------------------

    async with aiohttp.ClientSession() as session:

        total = len(github_candidates)

        verified = 0
        missing = 0

        for index, paper in enumerate(
            github_candidates,
            start=1
        ):

            github_url = paper["github_url"]

            result = await get_repository(
                session,
                github_url
            )


            if result:

                paper["github_url"] = result["github_url"]

                paper["github_stars"] = (
                    result["github_stars"]
                )

                paper["github_forks"] = (
                    result["github_forks"]
                )

                paper["github_watchers"] = (
                    result["github_watchers"]
                )

                verified += 1

                print(
                    f"[{index}/{total}] "
                    f"Verified: "
                    f"{result['github_url']} "
                    f"| stars="
                    f"{result['github_stars']}"
                )

            else:

                missing += 1

                print(
                    f"[{index}/{total}] "
                    f"Repository not verified: "
                    f"{github_url}"
                )


            # Small delay to avoid aggressive API usage
            await asyncio.sleep(0.2)


    # -------------------------
    # Prepare output columns
    # -------------------------

    fieldnames = list(papers[0].keys())

    for field in [
        "github_forks",
        "github_watchers"
    ]:

        if field not in fieldnames:

            fieldnames.append(field)


    # -------------------------
    # Save final CSV
    # -------------------------

    with OUTPUT_FILE.open(
        "w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames
        )

        writer.writeheader()

        writer.writerows(papers)


    print()
    print("===================================")
    print("GitHub enrichment complete")
    print("===================================")

    print(
        f"Research papers: {len(papers)}"
    )

    print(
        f"Verified GitHub repositories: "
        f"{verified}"
    )

    print(
        f"Repositories not verified: "
        f"{missing}"
    )

    print(
        f"Output file: {OUTPUT_FILE}"
    )

    print("===================================")


# -----------------------------
# Run
# -----------------------------

if __name__ == "__main__":

    asyncio.run(
        enrich_papers()
    )