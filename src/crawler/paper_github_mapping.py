import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

OUTPUT_FILE = DATA_DIR / "research_papers_verified.csv"

PWC_URL = (
    "https://huggingface.co/datasets/"
    "pwc-archive/links-between-paper-and-code/"
    "resolve/main/data/train-00000-of-00001.parquet"
)

print("Loading Papers With Code archive...")

pwc = pd.read_parquet(PWC_URL)

print(f"Total mapping records: {len(pwc)}")

# Keep only records that have:
# 1. an arXiv ID
# 2. a GitHub repository
pwc = pwc[
    pwc["paper_arxiv_id"].notna()
    & pwc["repo_url"].notna()
]

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

# Prefer official implementations.
pwc["priority"] = pwc["is_official"].fillna(False).astype(int)

pwc = pwc.sort_values(
    ["priority", "mentioned_in_paper", "mentioned_in_github"],
    ascending=False
)

# One repository per paper.
pwc = pwc.drop_duplicates(
    subset=["paper_arxiv_id"],
    keep="first"
)

# Take first 1000 verified paper-code relationships.
pwc = pwc.head(1000).copy()

papers = pd.DataFrame({
    "schemaVersion": "1.0",
    "recordType": "RESEARCH_PAPER",
    "title": pwc["paper_title"],
    "authors": "",
    "paper_url": pwc["paper_url_abs"],
    "github_url": pwc["repo_url"],
    "github_stars": "",
    "published_date": "",
    "source_name": "Papers With Code / arXiv",
    "arxiv_id": pwc["paper_arxiv_id"],
})

papers.to_csv(
    OUTPUT_FILE,
    index=False,
    encoding="utf-8"
)

print()
print("===================================")
print("Verified paper → GitHub mapping complete")
print(f"Research papers: {len(papers)}")
print(
    f"Unique GitHub repositories: "
    f"{papers['github_url'].nunique()}"
)
print(f"Output: {OUTPUT_FILE}")
print("===================================")