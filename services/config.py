import os
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def load_dotenv(path: Path | None = None) -> None:
    env_path = path or Path(__file__).resolve().parents[1] / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key:
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def application_timezone() -> ZoneInfo:
    name = os.getenv("SUMMERDAY_TIMEZONE", "America/Toronto")
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(f"invalid SUMMERDAY_TIMEZONE: {name}") from exc


def application_date(now: datetime | None = None) -> date:
    instant = now or datetime.now(timezone.utc)
    return instant.astimezone(application_timezone()).date()
