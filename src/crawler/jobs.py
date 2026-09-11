import asyncio
import aiohttp
import feedparser
import pandas as pd
import re

from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from dateparser import parse
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_FILE = DATA_DIR / "jobs_24h.csv"


AI_PATTERNS = [
    r"\bartificial intelligence\b",
    r"\bartificial-intelligence\b",
    r"\bmachine learning\b",
    r"\bmachine-learning\b",
    r"\bdeep learning\b",
    r"\bdeep-learning\b",
    r"\bgenerative ai\b",
    r"\bgenai\b",
    r"\bllm\b",
    r"\blarge language model\b",
    r"\bnlp\b",
    r"\bnatural language processing\b",
    r"\bcomputer vision\b",
    r"\bai engineer\b",
    r"\bai developer\b",
    r"\bai researcher\b",
    r"\bml engineer\b",
    r"\bmachine learning engineer\b",
    r"\bdata scientist\b",
    r"\bAI\b",
    r"\bML\b",
]


def is_ai_job(title, description):
    text = f"{title} {description}"
    return any(
        re.search(pattern, text, flags=re.IGNORECASE)
        for pattern in AI_PATTERNS
    )


def parse_date(value):
    if not value:
        return None

    try:
        parsed = parse(
            str(value),
            settings={"RETURN_AS_TIMEZONE_AWARE": True}
        )

        if parsed is None:
            return None

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)

    except Exception:
        return None


def clean_text(value):
    soup = BeautifulSoup(str(value or ""), "html.parser")
    return " ".join(soup.stripped_strings)


async def fetch_page_text(session, url):
    if not url:
        return ""

    try:
        async with session.get(
            url,
            headers={
                "User-Agent":
                "AI-Intelligence-Pipeline/1.0"
            },
            timeout=aiohttp.ClientTimeout(total=30)
        ) as response:

            if response.status != 200:
                return ""

            html = await response.text(
                errors="ignore"
            )

            soup = BeautifulSoup(
                html,
                "html.parser"
            )

            article = (
                soup.find("article")
                or soup.find("main")
                or soup.find("body")
            )

            if not article:
                return ""

            for tag in article(
                ["script", "style", "nav", "footer"]
            ):
                tag.decompose()

            return " ".join(
                article.stripped_strings
            )

    except Exception:
        return ""


async def add_record(
    records,
    session,
    source,
    title,
    company,
    url,
    published,
    description,
    location=""
):

    published_dt = parse_date(published)

    if not published_dt:
        return

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)

    if published_dt < cutoff:
        return

    clean_description = clean_text(description)

    if not is_ai_job(
        title,
        clean_description
    ):
        return

    if not title or not url:
        return

    if len(clean_description) < 200:
        page_text = await fetch_page_text(
            session,
            str(url)
        )

        if len(page_text) > len(clean_description):
            clean_description = page_text

    records.append({
        "schemaVersion": "1.0",
        "recordType": "JOB",
        "title": str(title).strip(),
        "company": str(company or "").strip(),
        "location": str(location or "").strip(),
        "published_date": published_dt.isoformat(),
        "source_name": source,
        "source_url": str(url).strip(),
        "full_text": clean_description,
    })


async def fetch_json(
    session,
    url,
    source
):

    print()
    print("Source:", source)

    try:
        async with session.get(
            url,
            headers={
                "User-Agent":
                "AI-Intelligence-Pipeline/1.0"
            },
            timeout=aiohttp.ClientTimeout(total=60)
        ) as response:

            print(
                "HTTP status:",
                response.status
            )

            if response.status != 200:
                return None

            return await response.json(
                content_type=None
            )

    except Exception as exc:
        print(
            "Source error:",
            exc
        )
        return None


async def fetch_rss(
    session,
    url,
    source
):

    print()
    print("Source:", source)

    try:
        async with session.get(
            url,
            headers={
                "User-Agent":
                "AI-Intelligence-Pipeline/1.0"
            },
            timeout=aiohttp.ClientTimeout(total=60)
        ) as response:

            print(
                "HTTP status:",
                response.status
            )

            if response.status != 200:
                return []

            xml = await response.text(
                errors="ignore"
            )

            feed = feedparser.parse(xml)

            print(
                "Feed entries:",
                len(feed.entries)
            )

            return feed

    except Exception as exc:
        print(
            "RSS error:",
            exc
        )
        return []


def rss_full_text(entry):

    content = entry.get(
        "content",
        []
    )

    if content:
        try:
            return content[0].get(
                "value",
                ""
            )
        except Exception:
            pass

    return entry.get(
        "summary",
        ""
    )


async def collect_jobs():

    print()
    print(
        "==================================="
    )
    print(
        "Collecting AI jobs from last 24 hours"
    )
    print(
        "==================================="
    )

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)

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

        # =================================
        # 1. JOBICY
        # =================================

        data = await fetch_json(
            session,
            "https://jobicy.com/api/v2/remote-jobs?count=200",
            "Jobicy"
        )

        if data:

            jobs = data.get(
                "jobs",
                []
            )

            print(
                "Records received:",
                len(jobs)
            )

            for job in jobs:

                await add_record(
                    records,
                    session,
                    "Jobicy",
                    job.get("jobTitle"),
                    job.get("companyName"),
                    job.get("url"),
                    job.get("pubDate"),
                    job.get("jobDescription"),
                    job.get("jobGeo")
                )

        # =================================
        # 2. REMOTE FIRST JOBS - AI
        # =================================

        feed = await fetch_rss(
            session,
            "https://remotefirstjobs.com/rss/jobs/ai.rss",
            "RemoteFirstJobs"
        )

        for entry in feed.entries:

            await add_record(
                records,
                session,
                "RemoteFirstJobs",
                entry.get("title", ""),
                "",
                entry.get("link", ""),
                entry.get(
                    "published",
                    entry.get("updated", "")
                ),
                rss_full_text(entry),
                ""
            )

        # =================================
        # 3. WE WORK REMOTELY
        # =================================

        feed = await fetch_rss(
            session,
            "https://weworkremotely.com/remote-jobs.rss",
            "We Work Remotely"
        )

        for entry in feed.entries:

            await add_record(
                records,
                session,
                "We Work Remotely",
                entry.get("title", ""),
                "",
                entry.get("link", ""),
                entry.get(
                    "published",
                    entry.get("updated", "")
                ),
                rss_full_text(entry),
                ""
            )

        # =================================
        # 4. REMOTE OK
        # =================================

        data = await fetch_json(
            session,
            "https://remoteok.com/api",
            "Remote OK"
        )

        if data and isinstance(data, list):

            print(
                "Records received:",
                len(data)
            )

            for job in data:

                if not isinstance(
                    job,
                    dict
                ):
                    continue

                await add_record(
                    records,
                    session,
                    "Remote OK",
                    job.get("position"),
                    job.get("company"),
                    job.get("url"),
                    job.get("date"),
                    job.get("description"),
                    job.get("location")
                )
        # =================================
        # 5. ARBEITNOW
        # =================================

        data = await fetch_json(
            session,
            "https://www.arbeitnow.com/api/job-board-api",
            "Arbeitnow"
        )

        if data:

            jobs = data.get(
                "data",
                []
            )

            print(
                "Records received:",
                len(jobs)
            )

            for job in jobs:

                created = job.get(
                    "created_at"
                )

                if isinstance(
                    created,
                    (int, float)
                ):
                    created = datetime.fromtimestamp(
                        created,
                        tz=timezone.utc
                    ).isoformat()

                await add_record(
                    records,
                    session,
                    "Arbeitnow",
                    job.get("title"),
                    job.get("company_name"),
                    job.get("url"),
                    created,
                    job.get("description"),
                    job.get("location")
                )

        # =================================
        # 6. HIMALAYAS
        # =================================
        

        feed = await fetch_rss(
            session,
            "https://himalayas.app/jobs/rss",
            "Himalayas"
        )

        for entry in feed.entries:

            company = entry.get(
                "himalayasjobs_companyname",
                ""
            )

            location = entry.get(
                "himalayasjobs_locationrestriction",
                ""
            )

            await add_record(
                records,
                session,
                "Himalayas",
                entry.get("title", ""),
                company,
                entry.get("link", ""),
                entry.get(
                    "published",
                    entry.get("updated", "")
                ),
                rss_full_text(entry),
                location
            )

    # =================================
    # SAVE DATA
    # =================================

    df = pd.DataFrame(records)

    if df.empty:

        raise RuntimeError(
            "No AI jobs published within "
            "the last 24 hours."
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
        "JOBS DATASET COMPLETE"
    )
    print(
        "==================================="
    )

    print(
        "Fresh AI jobs:",
        len(df)
    )

    print(
        "Unique job sources:",
        df["source_name"].nunique()
    )

    print(
        "Sources:",
        ", ".join(
            sorted(
                df["source_name"].unique()
            )
        )
    )

    print(
        "Jobs with full text:",
        df["full_text"]
        .astype(str)
        .str.strip()
        .ne("")
        .sum()
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
        collect_jobs()
    )