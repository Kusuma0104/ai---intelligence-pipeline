import asyncio
import aiohttp
import feedparser
import pandas as pd
import re
import hashlib

from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from dateparser import parse
from pathlib import Path
from src.extraction.classifiers import (
    classify_is_remote,
    classify_role_family,
    company_from_job_title,
)
from src.extraction.schemas import JobContent, JobEntity, SourceInfo, job_row
from src.resolution.entity_resolver import EntityResolver
from src.utils.dates import normalize_date, missing_date_heuristic

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_FILE = DATA_DIR / "jobs_24h.csv"
SEEN_HASH_FILE = DATA_DIR / "job_seen_hashes.txt"

def load_seen_hashes():
    if not SEEN_HASH_FILE.exists():
        return set()

    try:
        return {
            line.strip()
            for line in SEEN_HASH_FILE.read_text(
                encoding="utf-8"
            ).splitlines()
            if line.strip()
        }
    except Exception:
        return set()


def save_seen_hashes(hashes):
    DATA_DIR.mkdir(exist_ok=True)

    SEEN_HASH_FILE.write_text(
        "\n".join(sorted(hashes)),
        encoding="utf-8"
    )


def make_content_hash(title, company, url, description):
    raw = "||".join([
        str(title or "").strip(),
        str(company or "").strip(),
        str(url or "").strip(),
        str(description or "").strip(),
    ])

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()
    
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
    r"\bai engineer\b",
    r"\bmlops\b",
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
    location="",
    seen_hashes = None
):

    if seen_hashes is None:
        seen_hashes = set()

    normalized_date = normalize_date(published)

    clean_description = clean_text(description)

    content_hash = make_content_hash(
        title,
        company,
        url,
        clean_description
    )

    heuristic_used = False

    if normalized_date:
        published_dt = datetime.fromisoformat(
            normalized_date
        )
    else:
        normalized_date, heuristic_used = missing_date_heuristic(
            clean_description,
            content_hash,
            seen_hashes
        )

        if not normalized_date:
            return

        published_dt = datetime.fromisoformat(
            normalized_date
        )

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)

    if published_dt < cutoff:
        return

    
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
    seen_hashes.add(content_hash)

    title_text = str(title).strip()
    company_text = company_from_job_title(title_text, str(company or "").strip())
    resolver = EntityResolver()
    canonical_company = resolver.canonical_or_self(company_text) if company_text else company_text
    source_url = str(url).strip()
    collected_at = datetime.now(timezone.utc)

    entity = JobEntity(
        source=SourceInfo(name=source, url=source_url),
        content=JobContent(
            company=canonical_company or company_text or "Unknown",
            date=published_dt.isoformat(),
            is_remote=classify_is_remote(
                title_text,
                clean_description,
                str(location or ""),
                source,
            ),
            role_family=classify_role_family(title_text, clean_description),
        ),
        collectedAt=collected_at,
    )

    row = job_row(
        entity,
        extra={
            "content.title": title_text,
            "content.location": str(location or "").strip(),
            "date_heuristic_used": heuristic_used,
            "full_text": clean_description,
        },
    )
    records.append(row)


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
    seen_hashes = load_seen_hashes()
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
                    job.get("jobGeo"),
                    seen_hashes
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
                "",
                seen_hashes
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
                "",
                seen_hashes
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
                    job.get("location"),
                    seen_hashes
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
                    job.get("location"),
                    seen_hashes
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
                location,
                seen_hashes
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

    url_col = "source.url" if "source.url" in df.columns else "source_url"
    date_col = "content.date" if "content.date" in df.columns else "published_date"
    source_col = "source.name" if "source.name" in df.columns else "source"

    df = df.drop_duplicates(
        subset=[url_col],
        keep="first"
    )

    df = df.sort_values(
        date_col,
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
    save_seen_hashes(seen_hashes)

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
        "source.name" if "source.name" in df.columns else "source_name"
    )

    print(
        "Unique job sources:",
        df[source_col].nunique()
    )

    print(
        "Sources:",
        ", ".join(
            sorted(
                df[source_col].astype(str).unique()
            )
        )
    )

    print(
        "Jobs with full text:",
        df.get("full_text", pd.Series(dtype=str))
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