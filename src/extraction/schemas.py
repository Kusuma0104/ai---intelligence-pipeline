from enum import Enum
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, HttpUrl


# --------------------------------------------------
# Existing ResearchPaper model
# Keep this for crawler compatibility
# --------------------------------------------------

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


# --------------------------------------------------
# Common source
# --------------------------------------------------

class SourceInfo(BaseModel):
    name: str
    url: HttpUrl


# --------------------------------------------------
# Startup
# --------------------------------------------------

class StartupData(BaseModel):
    employeeCount: Optional[int] = None


class StartupContent(BaseModel):
    entityName: str
    data: StartupData = Field(default_factory=StartupData)


class StartupEntity(BaseModel):
    schemaVersion: str = "1.0"
    recordType: str = "STARTUP"
    source: SourceInfo
    content: StartupContent
    collectedAt: datetime


# --------------------------------------------------
# Product
# --------------------------------------------------

class PricingModel(str, Enum):
    FREE = "FREE"
    FREEMIUM = "FREEMIUM"
    PAID = "PAID"
    ENTERPRISE = "ENTERPRISE"


class ProductContent(BaseModel):
    startupName: str
    pricingModel: PricingModel


class ProductEntity(BaseModel):
    schemaVersion: str = "1.0"
    recordType: str = "PRODUCT"
    source: SourceInfo
    content: ProductContent
    collectedAt: datetime


# --------------------------------------------------
# Research Paper
# --------------------------------------------------

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
    collectedAt: datetime


# --------------------------------------------------
# Job
# --------------------------------------------------

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
    collectedAt: datetime


# --------------------------------------------------
# LLM Extraction
# --------------------------------------------------

class LLMExtraction(BaseModel):
    schemaVersion: str = "1.0"
    recordType: str = "LLM_EXTRACTION"
    entity_name: str
    entity_type: str
    description: str
    website: Optional[HttpUrl] = None
    source_url: HttpUrl
    confidence: float = Field(ge=0.0, le=1.0)