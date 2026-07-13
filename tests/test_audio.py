from pathlib import Path

import pytest

from services.audio.hashing import sha256_file
from services.audio.models import AudioAssetRef, SpeechProfile
from services.audio.storage import resolve_media_path
from services.audio.validation import validate_audio_asset
from services.providers.fake_tts import FakeTTSProvider


def profile() -> SpeechProfile:
    return SpeechProfile(
        level="A1",
        learning_target_wpm=85,
        pause_style="clear",
        articulation="natural",
        connected_speech="light",
    )


def test_fake_tts_writes_hashable_audio(tmp_path: Path) -> None:
    output = tmp_path / "lessons" / "lesson.opus"
    FakeTTSProvider().synthesize("Bonjour", output, profile())
    asset = AudioAssetRef(
        asset_id="lesson-audio",
        path="lessons/lesson.opus",
        sha256=sha256_file(output),
        mime_type="audio/ogg",
        provider="fake",
        model="fake-tts",
    )

    assert validate_audio_asset(asset, tmp_path) == output.resolve()


def test_media_path_rejects_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="inside the media root"):
        resolve_media_path(tmp_path, "../secret.txt")


def test_audio_validation_rejects_hash_mismatch(tmp_path: Path) -> None:
    output = tmp_path / "lesson.opus"
    output.write_bytes(b"audio")
    asset = AudioAssetRef(
        asset_id="lesson-audio",
        path="lesson.opus",
        sha256="0" * 64,
        mime_type="audio/ogg",
        provider="fake",
        model="fake-tts",
    )

    with pytest.raises(ValueError, match="hash mismatch"):
        validate_audio_asset(asset, tmp_path)
