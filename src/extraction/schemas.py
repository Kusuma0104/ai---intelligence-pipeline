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
    
class SourceInfo(BaseModel):
    name: str
    url: HttpUrl


class StartupContent(BaseModel):
    entityName: str
    data: dict = {}


class StartupEntity(BaseModel):
    schemaVersion: str = "1.0"
    recordType: str = "STARTUP"
    source: SourceInfo
    content: StartupContent
    collectedAt: str


class ProductContent(BaseModel):
    startupName: str
    pricingModel: str


class ProductEntity(BaseModel):
    schemaVersion: str = "1.0"
    recordType: str = "PRODUCT"
    source: SourceInfo
    content: ProductContent
    collectedAt: str


class ResearchPaperContent(BaseModel):
    title: str
    authors: List[str]
    paper_url: HttpUrl
    github_url: Optional[HttpUrl] = None
    github_stars: Optional[int] = None
    published_date: str


class ResearchPaperEntity(BaseModel):
    schemaVersion: str = "1.0"
    recordType: str = "RESEARCH_PAPER"
    content: ResearchPaperContent


class JobContent(BaseModel):
    company: str
    date: str
    is_remote: bool
    role_family: str


class JobEntity(BaseModel):
    schemaVersion: str = "1.0"
    recordType: str = "JOB"
    content: JobContent