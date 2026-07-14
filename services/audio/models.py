from typing import Literal

from pydantic import BaseModel, Field


ReviewStatus = Literal["pending", "approved", "rejected"]


class AudioAssetRef(BaseModel):
    asset_id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mime_type: str = Field(min_length=1)
    duration_ms: int | None = Field(default=None, ge=0)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    voice: str | None = None
    speech_rate: float | None = Field(default=None, gt=0)
    target_wpm: float | None = Field(default=None, gt=0)
    measured_wpm: float | None = Field(default=None, gt=0)
    length_scale: float | None = Field(default=None, gt=0)
    sample_rate: int | None = Field(default=None, gt=0)
    synthesis_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    review_status: ReviewStatus = "pending"


class SpeechProfile(BaseModel):
    level: Literal["A1", "A2"]
    learning_target_wpm: int = Field(gt=0)
    natural_target_wpm: int | None = Field(default=None, gt=0)
    pause_style: str = Field(min_length=1)
    articulation: str = Field(min_length=1)
    connected_speech: str = Field(min_length=1)


class LessonSentence(BaseModel):
    id: str = Field(min_length=1)
    index: int = Field(ge=0)
    text: str = Field(min_length=1)
    learning_audio: AudioAssetRef
    natural_audio: AudioAssetRef | None = None
