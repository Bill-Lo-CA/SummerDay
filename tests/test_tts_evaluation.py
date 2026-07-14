import os
from pathlib import Path
from types import SimpleNamespace
import wave

import pytest
from content.evaluations.tts.cases import evaluation_cases
from services.audio.models import SpeechProfile
from services.providers.command_tts import CommandTTSProvider
from services.providers.piper_tts import PiperTTSProvider


class StubVoice:
    def __init__(self, frames: int = 1_600) -> None:
        self.frames = frames
        self.length_scales = []

    def synthesize_wav(self, text, wav_file, syn_config) -> None:
        self.length_scales.append(syn_config.length_scale)
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16_000)
        wav_file.writeframes(b"\0\0" * self.frames)


def piper_paths(tmp_path: Path) -> Path:
    model = tmp_path / "fr_FR-siwis-medium.onnx"
    model.write_bytes(b"model")
    Path(f"{model}.json").write_text("{}")
    return model


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


def test_piper_requires_model_config_and_positive_settings(monkeypatch, tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="model not found"):
        PiperTTSProvider(str(tmp_path / "missing.onnx"))

    model = tmp_path / "model.onnx"
    model.write_bytes(b"model")
    with pytest.raises(RuntimeError, match="config not found"):
        PiperTTSProvider(str(model))

    model = piper_paths(tmp_path)
    with pytest.raises(ValueError, match="greater than zero"):
        PiperTTSProvider(str(model), baseline_wpm=0)
    with pytest.raises(ValueError, match="greater than zero"):
        PiperTTSProvider(str(model), length_scale=0)


def test_piper_loads_once_writes_valid_wav_and_replaces_atomically(monkeypatch, tmp_path: Path) -> None:
    model = piper_paths(tmp_path)
    voice = StubVoice()
    loads = []
    replacements = []
    monkeypatch.setattr(
        "services.providers.piper_tts.PiperVoice.load",
        lambda *args: (loads.append(args), voice)[1],
    )
    replace = os.replace
    monkeypatch.setattr(
        "services.providers.piper_tts.os.replace",
        lambda source, destination: (replacements.append((Path(source), Path(destination))), replace(source, destination))[1],
    )
    provider = PiperTTSProvider(str(model))
    learning = tmp_path / "learning.wav"
    result = provider.synthesize("Bonjour monde", learning, SpeechProfile(
        level="A1", learning_target_wpm=85, pause_style="clear",
        articulation="clear", connected_speech="light",
    ))
    provider.synthesize("Bonjour", tmp_path / "natural.wav", SpeechProfile(
        level="A1", learning_target_wpm=105, pause_style="natural",
        articulation="natural", connected_speech="natural",
    ))

    with wave.open(str(learning), "rb") as wav_file:
        assert wav_file.getframerate() == 16_000
        assert wav_file.getnframes() == 1_600
    assert len(loads) == 1
    assert voice.length_scales == [pytest.approx(100 / 85), pytest.approx(100 / 105)]
    assert replacements[0] == (learning.with_suffix(".wav.tmp"), learning)
    assert result.duration_ms == 100
    assert result.target_wpm == 85


def test_piper_rejects_empty_wav_and_cleans_temporary_file(monkeypatch, tmp_path: Path) -> None:
    model = piper_paths(tmp_path)
    monkeypatch.setattr("services.providers.piper_tts.PiperVoice.load", lambda *args: StubVoice(frames=0))
    provider = PiperTTSProvider(str(model))
    output = tmp_path / "empty.wav"

    with pytest.raises(ValueError, match="no frames"):
        provider.synthesize("Bonjour", output, SpeechProfile(
            level="A1", learning_target_wpm=85, pause_style="clear",
            articulation="clear", connected_speech="light",
        ))

    assert not output.exists()
    assert not output.with_suffix(".wav.tmp").exists()


def test_piper_rejects_invalid_target_wpm(monkeypatch, tmp_path: Path) -> None:
    model = piper_paths(tmp_path)
    monkeypatch.setattr("services.providers.piper_tts.PiperVoice.load", lambda *args: StubVoice())
    provider = PiperTTSProvider(str(model))

    with pytest.raises(ValueError, match="target WPM"):
        provider.synthesize("Bonjour", tmp_path / "output.wav", SimpleNamespace(learning_target_wpm=0))
