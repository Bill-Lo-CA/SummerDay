from pathlib import Path

import httpx
import pytest

from services.api.main import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_media_route_serves_asset_and_rejects_traversal(tmp_path: Path, monkeypatch) -> None:
    asset = tmp_path / "lessons" / "lesson-1" / "audio.opus"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"audio")
    monkeypatch.setenv("SUMMERDAY_MEDIA_DIR", str(tmp_path))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/media/lessons/lesson-1/audio.opus")
        traversal = await client.get("/media/../secret")

    assert response.status_code == 200
    assert response.content == b"audio"
    assert response.headers["cache-control"].endswith("immutable")
    assert traversal.status_code == 404
