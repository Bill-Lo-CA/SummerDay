from pathlib import Path
from dataclasses import dataclass
from typing import Protocol

from services.audio.models import SpeechProfile


@dataclass(frozen=True)
class AudioGenerationResult:
    provider: str
    model: str
    mime_type: str
    duration_ms: int | None = None
    voice: str | None = None
    speech_rate: float | None = None


class TTSProvider(Protocol):
    def synthesize(self, text: str, output_path: Path, profile: SpeechProfile) -> AudioGenerationResult:
        ...
