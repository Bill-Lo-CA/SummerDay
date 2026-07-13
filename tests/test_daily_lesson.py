from datetime import date
from pathlib import Path

import httpx
import pytest

from services.api.main import app
from services.config import application_date


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_today_lesson_has_core_learning_content(tmp_path: Path, monkeypatch) -> None:
    fixture = Path("content/fixtures/daily-lesson.json")
    lesson_dir = tmp_path / "lessons"
    lesson_dir.mkdir()
    (lesson_dir / f"{date.today().isoformat()}.json").write_text(fixture.read_text())
    monkeypatch.setenv("SOMEADAY_DATA_DIR", str(tmp_path))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/lessons/today")
    lesson = response.json()

    assert response.status_code == 200
    assert 8 <= len(lesson["core_vocabulary"]) <= 12
    assert any(item["lexical_item"] == "jouer un rôle" for item in lesson["core_vocabulary"])
    assert lesson["morphology_focus"]["evidence"] in lesson["article_text"]


@pytest.mark.anyio
async def test_today_lesson_is_missing_until_published(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SOMEADAY_DATA_DIR", str(tmp_path))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/api/lessons/today")).status_code == 404


def test_application_date_uses_configured_timezone(monkeypatch) -> None:
    from datetime import datetime, timezone

    monkeypatch.setenv("SOMEADAY_TIMEZONE", "America/Toronto")
    instant = datetime(2026, 7, 13, 2, 30, tzinfo=timezone.utc)
    assert application_date(instant) == date(2026, 7, 12)
