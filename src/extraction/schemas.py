from datetime import datetime, timezone
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field, HttpUrl


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PricingModel(str, Enum):
    FREE = "FREE"
    FREEMIUM = "FREEMIUM"
    PAID = "PAID"
    ENTERPRISE = "ENTERPRISE"


class SourceInfo(BaseModel):
    name: str
    url: HttpUrl


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


class ProductContent(BaseModel):
    startupName: str
    pricingModel: PricingModel


class ProductEntity(BaseModel):
    schemaVersion: str = "1.0"
    recordType: str = "PRODUCT"
    source: SourceInfo
    content: ProductContent
    collectedAt: datetime


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


class NewsContent(BaseModel):
    title: str
    published_date: str
    full_text: str
    entity_name: Optional[str] = None


class NewsEntity(BaseModel):
    schemaVersion: str = "1.0"
    recordType: str = "NEWS"
    source: SourceInfo
    content: NewsContent
    collectedAt: datetime


class LLMExtraction(BaseModel):
    schemaVersion: str = "1.0"
    recordType: str = "LLM_EXTRACTION"
    entity_name: Optional[str] = None
    entity_type: Optional[str] = None
    description: Optional[str] = None
    website: Optional[HttpUrl] = None
    source_url: HttpUrl
    confidence: float = Field(ge=0.0, le=1.0)


class ResearchPaper(BaseModel):
    """Flat crawler-compatible paper model."""

    schemaVersion: str = "1.0"
    recordType: str = "RESEARCH_PAPER"
    title: str
    authors: List[str]
    paper_url: HttpUrl
    github_url: Optional[HttpUrl] = None
    github_stars: Optional[int] = None
    published_date: str
    source_name: str = "arXiv"


def _url_str(value: Any) -> str:
    return str(value) if value is not None else ""


def startup_row(entity: StartupEntity) -> dict:
    return {
        "schemaVersion": entity.schemaVersion,
        "recordType": entity.recordType,
        "source.name": entity.source.name,
        "source.url": _url_str(entity.source.url),
        "content.entityName": entity.content.entityName,
        "content.data.employeeCount": entity.content.data.employeeCount,
        "collectedAt": entity.collectedAt.isoformat(),
    }


def product_row(entity: ProductEntity) -> dict:
    return {
        "schemaVersion": entity.schemaVersion,
        "recordType": entity.recordType,
        "source.name": entity.source.name,
        "source.url": _url_str(entity.source.url),
        "content.startupName": entity.content.startupName,
        "content.pricingModel": entity.content.pricingModel.value,
        "collectedAt": entity.collectedAt.isoformat(),
    }


def paper_row(entity: ResearchPaperEntity) -> dict:
    authors = entity.content.authors
    return {
        "schemaVersion": entity.schemaVersion,
        "recordType": entity.recordType,
        "source.name": entity.source.name,
        "source.url": _url_str(entity.source.url),
        "content.title": entity.content.title,
        "content.authors": "; ".join(authors),
        "content.paper_url": _url_str(entity.content.paper_url),
        "content.github_url": _url_str(entity.content.github_url) or "",
        "content.github_stars": entity.content.github_stars,
        "content.published_date": entity.content.published_date,
        "collectedAt": entity.collectedAt.isoformat(),
    }


def job_row(entity: JobEntity, extra: Optional[dict] = None) -> dict:
    row = {
        "schemaVersion": entity.schemaVersion,
        "recordType": entity.recordType,
        "source.name": entity.source.name,
        "source.url": _url_str(entity.source.url),
        "content.company": entity.content.company,
        "content.date": entity.content.date,
        "content.is_remote": entity.content.is_remote,
        "content.role_family": entity.content.role_family,
        "collectedAt": entity.collectedAt.isoformat(),
    }
    if extra:
        row.update(extra)
    return row


def news_row(entity: NewsEntity) -> dict:
    return {
        "schemaVersion": entity.schemaVersion,
        "recordType": entity.recordType,
        "source.name": entity.source.name,
        "source.url": _url_str(entity.source.url),
        "content.title": entity.content.title,
        "content.published_date": entity.content.published_date,
        "content.full_text": entity.content.full_text,
        "content.entity_name": entity.content.entity_name or "",
        "collectedAt": entity.collectedAt.isoformat(),
    }
