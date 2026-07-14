from pathlib import Path
import wave

from services.audio.models import SpeechProfile
from services.providers.tts import AudioGenerationResult


class FakeTTSProvider:
    def synthesize(self, text: str, output_path: Path, profile: SpeechProfile) -> AudioGenerationResult:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16_000)
            wav_file.writeframes(b"\0\0" * 1_600)
        return AudioGenerationResult(
            provider="fake",
            model="fake-tts",
            mime_type="audio/wav",
            target_wpm=float(profile.learning_target_wpm),
        )
