import shlex
import subprocess
from pathlib import Path

from services.audio.models import SpeechProfile
from services.providers.tts import AudioGenerationResult


class CommandTTSProvider:
    """Adapt a local CLI TTS engine without adding a Python model dependency."""

    def __init__(self, command: str, model: str = "configured") -> None:
        self.command = shlex.split(command)
        self.model = model

    def synthesize(self, text: str, output_path: Path, profile: SpeechProfile) -> AudioGenerationResult:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [*self.command, str(output_path)],
            input=text.encode(),
            check=True,
            stdout=subprocess.DEVNULL,
        )
        return AudioGenerationResult(
            provider="command",
            model=self.model,
            mime_type="audio/ogg",
            speech_rate=float(profile.learning_target_wpm),
        )
