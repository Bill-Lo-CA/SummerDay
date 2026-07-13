import os
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def application_timezone() -> ZoneInfo:
    name = os.getenv("SUMMERDAY_TIMEZONE", "America/Toronto")
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(f"invalid SUMMERDAY_TIMEZONE: {name}") from exc


def application_date(now: datetime | None = None) -> date:
    instant = now or datetime.now(timezone.utc)
    return instant.astimezone(application_timezone()).date()
