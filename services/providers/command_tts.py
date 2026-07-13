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
        if not any(token in self.command for token in ("{speed}", "{wpm}")):
            raise ValueError("command must include a {speed} or {wpm} placeholder")

    def synthesize(self, text: str, output_path: Path, profile: SpeechProfile) -> AudioGenerationResult:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        speed = str(profile.learning_target_wpm)
        command = [
            token.replace("{speed}", speed)
            .replace("{wpm}", speed)
            .replace("{output_path}", str(output_path))
            for token in self.command
        ]
        if "{output_path}" not in self.command:
            command.append(str(output_path))
        subprocess.run(
            command,
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
