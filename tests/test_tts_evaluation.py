from pathlib import Path

from content.evaluations.tts.cases import evaluation_cases
from services.audio.models import SpeechProfile
from services.providers.command_tts import CommandTTSProvider
from services.providers.piper_tts import PiperTTSProvider


def test_evaluation_covers_required_case_counts() -> None:
    cases = evaluation_cases()
    assert sum(case.category == "letter" for case in cases) == 26
    assert sum(case.category == "vocabulary" for case in cases) == 30
    assert sum(case.category == "connected_speech" for case in cases) == 20
    assert sum(case.category == "article_sentence" for case in cases) == 20


def test_command_tts_passes_profile_speed(monkeypatch, tmp_path: Path) -> None:
    commands = []
    monkeypatch.setattr(
        "services.providers.command_tts.subprocess.run",
        lambda command, **kwargs: commands.append(command),
    )
    provider = CommandTTSProvider("tts --rate {speed} --output {output_path}")
    provider.synthesize("Bonjour", tmp_path / "learning.wav", SpeechProfile(
        level="A1", learning_target_wpm=85, pause_style="clear",
        articulation="clear", connected_speech="light",
    ))
    provider.synthesize("Bonjour", tmp_path / "natural.wav", SpeechProfile(
        level="A1", learning_target_wpm=105, pause_style="natural",
        articulation="natural", connected_speech="natural",
    ))

    assert commands[0][2] == "85"
    assert commands[1][2] == "105"


def test_piper_tts_converts_wpm_to_length_scale(monkeypatch, tmp_path: Path) -> None:
    commands = []
    model = tmp_path / "fr_FR-siwis-medium.onnx"
    model.touch()
    monkeypatch.setattr(
        "services.providers.piper_tts.subprocess.run",
        lambda command, **kwargs: commands.append(command),
    )
    provider = PiperTTSProvider(str(model))
    provider.synthesize("Bonjour", tmp_path / "learning.wav", SpeechProfile(
        level="A1", learning_target_wpm=85, pause_style="clear",
        articulation="clear", connected_speech="light",
    ))
    provider.synthesize("Bonjour", tmp_path / "natural.wav", SpeechProfile(
        level="A1", learning_target_wpm=105, pause_style="natural",
        articulation="natural", connected_speech="natural",
    ))

    assert commands[0][-1] == "1.1765"
    assert commands[1][-1] == "0.9524"
