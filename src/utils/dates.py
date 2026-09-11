import re
from datetime import datetime, timezone, timedelta
from dateparser import parse


def normalize_date(value, reference_time=None):
    """
    Normalize many date formats into UTC ISO-8601.

    Handles:
    - ISO dates
    - RSS dates
    - timestamps
    - relative dates such as '2 hours ago'
    - 'yesterday'
    """

    if reference_time is None:
        reference_time = datetime.now(timezone.utc)

    if value is None:
        return None

    # Unix timestamp
    if isinstance(value, (int, float)):
        try:
            # milliseconds
            if value > 10_000_000_000:
                result = datetime.fromtimestamp(
                    value / 1000,
                    tz=timezone.utc
                )
            else:
                result = datetime.fromtimestamp(
                    value,
                    tz=timezone.utc
                )

            return result.isoformat()
        except Exception:
            return None

    text = str(value).strip()

    if not text:
        return None

    # Relative time: "2 hours ago"
    match = re.search(
        r"(\d+)\s*(minute|minutes|min|mins|hour|hours|day|days)\s*ago",
        text,
        re.IGNORECASE
    )

    if match:
        amount = int(match.group(1))
        unit = match.group(2).lower()

        if "minute" in unit or unit in ("min", "mins"):
            result = reference_time - timedelta(
                minutes=amount
            )
        elif "hour" in unit:
            result = reference_time - timedelta(
                hours=amount
            )
        else:
            result = reference_time - timedelta(
                days=amount
            )

        return result.astimezone(
            timezone.utc
        ).isoformat()

    # "yesterday"
    if text.lower() == "yesterday":
        result = reference_time - timedelta(
            days=1
        )

        return result.astimezone(
            timezone.utc
        ).isoformat()

    # Normal date parsing
    try:
        result = parse(
            text,
            settings={
                "RETURN_AS_TIMEZONE_AWARE": True,
                "RELATIVE_BASE": reference_time,
            }
        )

        if result is None:
            return None

        if result.tzinfo is None:
            result = result.replace(
                tzinfo=timezone.utc
            )

        return result.astimezone(
            timezone.utc
        ).isoformat()

    except Exception:
        return None


def is_within_last_24_hours(
    normalized_date,
    reference_time=None
):
    """Return True only when the date is within 24 hours."""

    if not normalized_date:
        return False

    if reference_time is None:
        reference_time = datetime.now(
            timezone.utc
        )

    try:
        published = datetime.fromisoformat(
            normalized_date
        )

        if published.tzinfo is None:
            published = published.replace(
                tzinfo=timezone.utc
            )

        cutoff = (
            reference_time
            - timedelta(hours=24)
        )

        return cutoff <= published <= reference_time

    except Exception:
        return False


def missing_date_heuristic(
    page_text,
    content_hash,
    seen_hashes,
    reference_time=None
):
    """
    Conservative heuristic for sources without
    a publication date.

    New content is accepted only when:
    1. meaningful text exists
    2. its content hash was not seen previously

    The first-seen time is used as the normalized
    ingestion timestamp.
    """

    if reference_time is None:
        reference_time = datetime.now(
            timezone.utc
        )

    if not page_text or len(
        page_text.strip()
    ) < 100:
        return None, False

    if content_hash in seen_hashes:
        return None, False

    return (
        reference_time.isoformat(),
        True
    )