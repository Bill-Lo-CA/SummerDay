from pathlib import Path

from services.audio.models import SpeechProfile
from services.providers.tts import AudioGenerationResult


class FakeTTSProvider:
    def synthesize(self, text: str, output_path: Path, profile: SpeechProfile) -> AudioGenerationResult:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(f"fake-audio:{profile.level}:{text}".encode())
        return AudioGenerationResult(
            provider="fake",
            model="fake-tts",
            mime_type="audio/ogg",
            duration_ms=max(1, len(text) * 20),
            speech_rate=float(profile.learning_target_wpm),
        )
