from pathlib import Path

from fastapi.testclient import TestClient

from services.api.main import app


def test_media_route_serves_asset_and_rejects_traversal(tmp_path: Path, monkeypatch) -> None:
    asset = tmp_path / "lessons" / "lesson-1" / "audio.opus"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"audio")
    monkeypatch.setenv("SUMMERDAY_MEDIA_DIR", str(tmp_path))
    client = TestClient(app)

    response = client.get("/media/lessons/lesson-1/audio.opus")
    assert response.status_code == 200
    assert response.content == b"audio"
    assert response.headers["cache-control"].endswith("immutable")
    assert client.get("/media/../secret").status_code == 404
