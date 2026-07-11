import os
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from services.api.schemas import DailyLesson

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
    path = data_dir / "lessons" / f"{date.today().isoformat()}.json"
    if not path.exists():
        raise HTTPException(404, "Today's lesson has not been published.")
    return DailyLesson.model_validate_json(path.read_text())

