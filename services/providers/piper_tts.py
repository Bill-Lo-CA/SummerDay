import os
from pathlib import Path
import wave

from piper import PiperVoice, SynthesisConfig
from services.audio.models import SpeechProfile
from services.audio.validation import wav_metadata
from services.providers.tts import AudioGenerationResult


class PiperTTSProvider:
    """Run one locally loaded Piper voice."""

    def __init__(self, model_path: str, baseline_wpm: float = 100, length_scale: float = 1) -> None:
        self.model_path = Path(model_path)
        self.config_path = Path(f"{self.model_path}.json")
        self.baseline_wpm = baseline_wpm
        self.length_scale = length_scale
        if not self.model_path.is_file():
            raise RuntimeError(f"Piper model not found: {self.model_path}")
        if not self.config_path.is_file():
            raise RuntimeError(f"Piper model config not found: {self.config_path}")
        if baseline_wpm <= 0 or length_scale <= 0:
            raise ValueError("Piper baseline WPM and length scale must be greater than zero")
        self.voice = PiperVoice.load(self.model_path, self.config_path)

    def synthesize(self, text: str, output_path: Path, profile: SpeechProfile) -> AudioGenerationResult:
        target_wpm = profile.learning_target_wpm
        if target_wpm <= 0:
            raise ValueError("Piper target WPM must be greater than zero")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        length_scale = self.length_scale * self.baseline_wpm / target_wpm
        if length_scale <= 0:
            raise ValueError("Piper length scale must be greater than zero")
        temporary = output_path.with_suffix(output_path.suffix + ".tmp")
        try:
            with wave.open(str(temporary), "wb") as wav_file:
                self.voice.synthesize_wav(text, wav_file, SynthesisConfig(length_scale=length_scale))
            metadata = wav_metadata(temporary)
            os.replace(temporary, output_path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return AudioGenerationResult(
            provider="piper",
            model=self.model_path.stem,
            voice=self.model_path.stem,
            mime_type="audio/wav",
            duration_ms=metadata.duration_ms,
            target_wpm=float(target_wpm),
            length_scale=length_scale,
        )
