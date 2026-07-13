import os
import mimetypes
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from services.api.schemas import DailyLesson
from services.audio.storage import resolve_media_path
from services.config import application_date, application_timezone

app = FastAPI(title="SomeADay API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/lessons/today", response_model=DailyLesson)
def today_lesson() -> DailyLesson:
    data_dir = Path(os.getenv("SOMEADAY_DATA_DIR", "data"))
    path = data_dir / "lessons" / f"{application_date().isoformat()}.json"
    if not path.exists():
        raise HTTPException(404, "Today's lesson has not been published.")
    return DailyLesson.model_validate_json(path.read_text())


@app.get("/media/{asset_path:path}")
def media(asset_path: str) -> FileResponse:
    media_root = Path(os.getenv("SOMEADAY_MEDIA_DIR", str(Path(os.getenv("SOMEADAY_DATA_DIR", "data")) / "media")))
    try:
        path = resolve_media_path(media_root, asset_path)
    except ValueError as exc:
        raise HTTPException(404, "Media asset not found.") from exc
    if not path.is_file():
        raise HTTPException(404, "Media asset not found.")
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "timezone": str(application_timezone())}
