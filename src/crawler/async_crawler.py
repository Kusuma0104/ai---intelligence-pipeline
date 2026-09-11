from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional


class SourceInfo(BaseModel):
    name: str
    url: HttpUrl


# -------------------------
# STARTUP
# -------------------------

class StartupData(BaseModel):
    employeeCount: Optional[int] = None


class StartupContent(BaseModel):
    entityName: str
    data: StartupData = StartupData()


class StartupEntity(BaseModel):
    schemaVersion: str = "1.0"
    recordType: str = "STARTUP"
    source: SourceInfo
    content: StartupContent
    collectedAt: str


# -------------------------
# PRODUCT
# -------------------------

class ProductContent(BaseModel):
    startupName: str
    pricingModel: str


class ProductEntity(BaseModel):
    schemaVersion: str = "1.0"
    recordType: str = "PRODUCT"
    source: SourceInfo
    content: ProductContent
    collectedAt: str


# -------------------------
# RESEARCH PAPER
# -------------------------

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
    source: SourceInfo
    content: ResearchPaperContent
    collectedAt: str


# -------------------------
# JOB
# -------------------------

class JobContent(BaseModel):
    company: str
    date: str
    is_remote: bool
    role_family: str


class JobEntity(BaseModel):
    schemaVersion: str = "1.0"
    recordType: str = "JOB"
    source: SourceInfo
    content: JobContent
    collectedAt: str


# -------------------------
# LLM EXTRACTION
# -------------------------

class LLMExtraction(BaseModel):
    schemaVersion: str = "1.0"
    recordType: str = "LLM_EXTRACTION"
    entity_name: str
    entity_type: str
    description: str
    website: Optional[HttpUrl] = None
    source_url: HttpUrl
    confidence: float = Field(ge=0.0, le=1.0)