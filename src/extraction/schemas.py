from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional


class ResearchPaper(BaseModel):
    schemaVersion: str = "1.0"
    recordType: str = "RESEARCH_PAPER"

    title: str
    authors: List[str]

    paper_url: HttpUrl
    github_url: Optional[HttpUrl] = None
    github_stars: Optional[int] = None

    published_date: str
    source_name: str = "arXiv"
class LLMExtraction(BaseModel):
    schemaVersion: str = "1.0"
    recordType: str = "LLM_EXTRACTION"
    entity_name: str
    entity_type: str
    description: str
    website: Optional[HttpUrl] = None
    source_url: HttpUrl
    confidence: float = Field(ge=0.0, le=1.0)