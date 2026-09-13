import re
from typing import Optional

from src.extraction.schemas import PricingModel

ROLE_RULES = [
    (r"research scientist|research engineer|scientist|phd|research", "Research"),
    (r"product manager|\bpm\b|product owner", "Product"),
    (r"design|ux|ui researcher", "Design"),
    (r"sales|account manager|account executive|business development|go-to-market|\bgtm\b", "Sales"),
    (r"marketing|growth|content marketer", "Marketing"),
    (r"recruiter|talent|people ops|hr ", "People"),
    (r"finance|accounting|controller", "Finance"),
    (r"legal|counsel|compliance", "Legal"),
    (r"data scientist|machine learning|ml engineer|ai engineer|deep learning|nlp|computer vision", "Engineering"),
    (r"engineer|developer|sre|devops|software|platform|backend|frontend|full.?stack|security", "Engineering"),
    (r"annotat|labeler|trainer|operations|ops |support", "Operations"),
]

REMOTE_TRUE = re.compile(
    r"\b(remote|distributed|work from home|wfh|anywhere)\b",
    re.IGNORECASE,
)
REMOTE_FALSE = re.compile(
    r"\b(on[- ]site|onsite|in[- ]office|hybrid|relocate|presence in (our|the) .+ office)\b",
    re.IGNORECASE,
)

PRICING_MAP = [
    (r"enterprise|contact sales|custom pricing", PricingModel.ENTERPRISE),
    (r"freemium|free tier|free plan", PricingModel.FREEMIUM),
    (r"\bfree\b|open source|no cost", PricingModel.FREE),
    (r"paid|subscription|pro plan|premium|per month|\$", PricingModel.PAID),
]


def classify_role_family(title: str, description: str = "") -> str:
    text = f"{title} {description}".lower()
    for pattern, family in ROLE_RULES:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return family
    return "Other"


def classify_is_remote(
    title: str,
    description: str = "",
    location: str = "",
    source_name: str = "",
) -> bool:
    remote_boards = {
        "jobicy",
        "remote ok",
        "we work remotely",
        "remotefirstjobs",
        "himalayas",
    }
    text = f"{title} {description} {location}"
    if REMOTE_FALSE.search(text) and not REMOTE_TRUE.search(title):
        return False
    if REMOTE_TRUE.search(text):
        return True
    if source_name.strip().lower() in remote_boards:
        return True
    return False


def classify_pricing(raw: Optional[str], description: str = "") -> PricingModel:
    text = f"{raw or ''} {description}".strip().lower()
    if not text:
        return PricingModel.PAID

    for pattern, model in PRICING_MAP:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return model

    compact = re.sub(r"[^a-z]", "", text)
    try:
        return PricingModel(compact.upper())
    except ValueError:
        return PricingModel.FREEMIUM


def company_from_job_title(title: str, company: str) -> str:
    if company and company.strip():
        return company.strip()

    # Common RSS shapes: "Company: Role" or "Role at Company"
    at_match = re.search(r"\bat\s+(.+)$", title or "", flags=re.IGNORECASE)
    if at_match:
        return at_match.group(1).strip(" -|")

    if ":" in (title or ""):
        left, right = title.split(":", 1)
        if len(left.strip()) < 40:
            return left.strip()

    return ""
