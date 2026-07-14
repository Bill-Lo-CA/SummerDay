import subprocess
from pathlib import Path

from services.audio.models import SpeechProfile
from services.providers.tts import AudioGenerationResult


class PiperTTSProvider:
    """Run a locally installed Piper voice."""

    def __init__(self, model_path: str, baseline_wpm: float = 100, length_scale: float = 1) -> None:
        self.model_path = Path(model_path)
        self.baseline_wpm = baseline_wpm
        self.length_scale = length_scale

    def synthesize(self, text: str, output_path: Path, profile: SpeechProfile) -> AudioGenerationResult:
        if not self.model_path.is_file():
            raise RuntimeError(f"Piper model not found: {self.model_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        length_scale = self.length_scale * self.baseline_wpm / profile.learning_target_wpm
        command = [
            "piper",
            "--model",
            str(self.model_path),
            "--output-file",
            str(output_path),
            "--length-scale",
            f"{length_scale:.4f}",
        ]
        try:
            subprocess.run(command, input=text.encode(), check=True, stdout=subprocess.DEVNULL)
        except FileNotFoundError as exc:
            raise RuntimeError("Piper is not installed or is not on PATH.") from exc
        return AudioGenerationResult(
            provider="piper",
            model=self.model_path.stem,
            voice=self.model_path.stem,
            mime_type="audio/wav",
            speech_rate=float(profile.learning_target_wpm),
        )
