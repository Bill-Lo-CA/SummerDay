import json
import os
from datetime import date
from dataclasses import replace
from pathlib import Path

import pytest

from services.audio.generation import AudioGenerationError, attach_required_audio
from services.audio.generation import synthesis_fingerprint
from services.audio.models import SpeechProfile
from services.audio.publication import mark_audio_published, validate_publishable_lesson
import services.audio.publication as publication
from services.api.schemas import DailyLesson
from services.nlp import NLPAnalysis
from services.providers.fake_tts import FakeTTSProvider
from services.providers.tts import AudioGenerationResult
from services.providers.piper_tts import PiperTTSProvider


class PublishableTTSProvider(FakeTTSProvider):
    def synthesize(self, text, output_path, profile):
        super().synthesize(text, output_path, profile)
        return AudioGenerationResult(
            provider="test",
            model="test-tts",
            mime_type="audio/wav",
            target_wpm=float(profile.learning_target_wpm),
        )


class FailFirstVocabularyProvider(FakeTTSProvider):
    def __init__(self) -> None:
        self.calls = []
        self.failed = False

    def synthesize(self, text, output_path, profile):
        self.calls.append(output_path.name)
        if output_path.name == "00.wav" and not self.failed:
            self.failed = True
            raise RuntimeError("temporary TTS failure")
        return super().synthesize(text, output_path, profile)


class ReplacementTTSProvider:
    def __init__(self) -> None:
        self.calls = []

    def synthesize(self, text, output_path, profile):
        self.calls.append(output_path)
        FakeTTSProvider().synthesize(text, output_path, profile)
        return AudioGenerationResult(
            provider="piper",
            model="replacement",
            mime_type="audio/wav",
            target_wpm=float(profile.learning_target_wpm),
        )


def lesson_and_analysis() -> tuple[DailyLesson, NLPAnalysis]:
    lesson = DailyLesson.model_validate_json(Path("content/fixtures/daily-lesson.json").read_text())
    analysis = NLPAnalysis.model_validate({
        "sentences": [
            {"text": sentence, "tokens": []}
            for sentence in lesson.article_text.split(". ")
            if sentence
        ],
        "suitability": {
            "classification": "suitable", "word_count": 1, "sentence_count": 1,
            "average_sentence_length": 1, "longest_sentence_length": 1,
            "proper_noun_density": 0, "number_density": 0, "morphology_opportunities": 0,
        },
    })
    return lesson, analysis


def publish_fixture(tmp_path: Path) -> tuple[DailyLesson, Path, Path]:
    lesson, analysis = lesson_and_analysis()
    lesson.pronunciation_focus.review_status = "approved"
    media = tmp_path / "media"
    attach_required_audio(lesson, analysis, PublishableTTSProvider(), media)
    lesson.pronunciation_focus.reference_audio.review_status = "approved"
    data = tmp_path / "data"
    (data / "drafts").mkdir(parents=True)
    (data / "analysis").mkdir()
    (data / "drafts" / "2026-07-12.json").write_text(lesson.model_dump_json())
    (data / "analysis" / "2026-07-12.json").write_text(analysis.model_dump_json())
    return lesson, data, media


def test_required_audio_package_can_be_published(tmp_path: Path) -> None:
    lesson, analysis = lesson_and_analysis()
    lesson.pronunciation_focus.review_status = "approved"
    attach_required_audio(lesson, analysis, PublishableTTSProvider(), tmp_path)
    assert lesson.pronunciation_focus.review_status == "approved"
    assert lesson.pronunciation_focus.reference_audio.review_status == "pending"
    lesson.pronunciation_focus.review_status = "approved"
    lesson.pronunciation_focus.reference_audio.review_status = "approved"

    validate_publishable_lesson(lesson, tmp_path)
    mark_audio_published(lesson, tmp_path)
    assert json.loads((tmp_path / "lessons" / lesson.id / "manifest.json").read_text())["status"] == "published"


def test_fake_audio_blocks_publication(tmp_path: Path) -> None:
    lesson, analysis = lesson_and_analysis()
    attach_required_audio(lesson, analysis, FakeTTSProvider(), tmp_path)
    lesson.pronunciation_focus.review_status = "approved"
    lesson.pronunciation_focus.reference_audio.review_status = "approved"

    with pytest.raises(ValueError, match="fake audio"):
        validate_publishable_lesson(lesson, tmp_path)


def test_generate_audio_replaces_fake_assets_with_real_provider(tmp_path: Path) -> None:
    lesson, analysis = lesson_and_analysis()
    attach_required_audio(lesson, analysis, FakeTTSProvider(), tmp_path)
    replacement = ReplacementTTSProvider()

    attach_required_audio(lesson, analysis, replacement, tmp_path)

    assert len(replacement.calls) == 2 + len(analysis.sentences) + len(lesson.core_vocabulary)
    assert lesson.learning_audio.provider == "piper"
    assert all(item.audio.provider == "piper" for item in lesson.core_vocabulary)


def test_published_audio_package_cannot_resume(tmp_path: Path) -> None:
    lesson, analysis = lesson_and_analysis()
    attach_required_audio(lesson, analysis, FakeTTSProvider(), tmp_path)
    mark_audio_published(lesson, tmp_path)
    manifest_path = tmp_path / "lessons" / lesson.id / "manifest.json"
    manifest = manifest_path.read_text()

    with pytest.raises(FileExistsError, match="immutable"):
        attach_required_audio(lesson, analysis, FakeTTSProvider(), tmp_path)

    assert manifest_path.read_text() == manifest


def test_missing_vocabulary_audio_blocks_publication(tmp_path: Path) -> None:
    lesson, analysis = lesson_and_analysis()
    lesson.pronunciation_focus.review_status = "approved"
    attach_required_audio(lesson, analysis, PublishableTTSProvider(), tmp_path)
    lesson.pronunciation_focus.reference_audio.review_status = "approved"
    lesson.core_vocabulary[0].audio = None

    with pytest.raises(ValueError, match="vocabulary audio"):
        validate_publishable_lesson(lesson, tmp_path)


def test_unapproved_focus_blocks_publication(tmp_path: Path) -> None:
    lesson, analysis = lesson_and_analysis()
    attach_required_audio(lesson, analysis, FakeTTSProvider(), tmp_path)

    with pytest.raises(ValueError, match="requires approval"):
        validate_publishable_lesson(lesson, tmp_path)


def test_pending_focus_audio_blocks_publication_even_when_focus_is_approved(tmp_path: Path) -> None:
    lesson, analysis = lesson_and_analysis()
    attach_required_audio(lesson, analysis, FakeTTSProvider(), tmp_path)
    lesson.pronunciation_focus.review_status = "approved"

    with pytest.raises(ValueError, match="requires approval"):
        validate_publishable_lesson(lesson, tmp_path)


def test_audio_generation_resumes_only_failed_assets(tmp_path: Path) -> None:
    lesson, analysis = lesson_and_analysis()
    provider = FailFirstVocabularyProvider()

    with pytest.raises(AudioGenerationError, match="vocabulary/00.wav"):
        attach_required_audio(lesson, analysis, provider, tmp_path)

    manifest_path = tmp_path / "lessons" / lesson.id / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["status"] == "failed"
    assert any(asset["status"] == "failed" for asset in manifest["assets"])
    completed_calls = len(provider.calls)

    attach_required_audio(lesson, analysis, provider, tmp_path)

    manifest = json.loads(manifest_path.read_text())
    assert manifest["status"] == "complete"
    assert len(provider.calls) == completed_calls + 1
    assert lesson.core_vocabulary[0].audio is not None
    with pytest.raises(ValueError, match="requires approval"):
        validate_publishable_lesson(lesson, tmp_path)


def test_audio_regenerates_when_spoken_text_changes(tmp_path: Path) -> None:
    lesson, analysis = lesson_and_analysis()
    provider = ReplacementTTSProvider()
    attach_required_audio(lesson, analysis, provider, tmp_path)
    calls = len(provider.calls)

    lesson.article_text += " Nouvelle phrase."
    attach_required_audio(lesson, analysis, provider, tmp_path)

    assert len(provider.calls) == calls + 1


def test_piper_fingerprint_uses_effective_length_scale() -> None:
    provider = object.__new__(PiperTTSProvider)
    provider.model_path = Path("voice.onnx")
    provider.baseline_wpm = 100
    provider.length_scale = 1
    profile = SpeechProfile(
        level="A1",
        learning_target_wpm=85,
        pause_style="clear",
        articulation="natural",
        connected_speech="light",
    )
    result = AudioGenerationResult(
        provider="piper",
        model="voice",
        voice="voice",
        mime_type="audio/wav",
        target_wpm=float(profile.learning_target_wpm),
        length_scale=100 / profile.learning_target_wpm,
    )

    assert synthesis_fingerprint("Bonjour", provider, profile) == synthesis_fingerprint(
        "Bonjour", provider, profile, result
    )


@pytest.mark.parametrize("change", ["provider", "model", "voice", "text", "speed"])
def test_synthesis_fingerprint_changes_for_each_synthesis_input(change: str) -> None:
    provider = object.__new__(PiperTTSProvider)
    provider.model_path = Path("voice.onnx")
    provider.baseline_wpm = 100
    provider.length_scale = 1
    profile = SpeechProfile(
        level="A1",
        learning_target_wpm=85,
        pause_style="clear",
        articulation="natural",
        connected_speech="light",
    )
    result = AudioGenerationResult(
        provider="piper",
        model="voice",
        voice="voice",
        mime_type="audio/wav",
        target_wpm=85,
        length_scale=100 / 85,
    )
    changed_result = replace(result, **{"provider": "other" if change == "provider" else result.provider,
        "model": "other" if change == "model" else result.model,
        "voice": "other" if change == "voice" else result.voice,
        "length_scale": 2 if change == "speed" else result.length_scale})
    changed_profile = profile.model_copy(update={"learning_target_wpm": 90}) if change == "speed" else profile
    changed_text = "Au revoir" if change == "text" else "Bonjour"
    changed_provider = object.__new__(FakeTTSProvider) if change == "provider" else provider

    assert synthesis_fingerprint("Bonjour", provider, profile, result) != synthesis_fingerprint(
        changed_text, changed_provider, changed_profile, changed_result
    )
@pytest.mark.parametrize("fail_at", [1, 2, 3])
def test_publish_recovers_after_each_pipeline_write_boundary(tmp_path: Path, monkeypatch, fail_at: int) -> None:
    from services import pipeline

    lesson, data, media = publish_fixture(tmp_path)
    monkeypatch.setattr(pipeline, "DATA_DIR", data)
    monkeypatch.setattr(pipeline, "MEDIA_DIR", media)
    original_replace = os.replace
    calls = {"count": 0}

    def fail_once(source, destination):
        calls["count"] += 1
        if calls["count"] == fail_at:
            raise OSError("injected publication failure")
        original_replace(source, destination)

    monkeypatch.setattr(pipeline.os, "replace", fail_once)
    with pytest.raises(OSError, match="publication failure"):
        pipeline.publish(date(2026, 7, 12))

    monkeypatch.setattr(pipeline.os, "replace", original_replace)
    pipeline.publish(date(2026, 7, 12))
    assert json.loads((media / "lessons" / lesson.id / "manifest.json").read_text())["status"] == "published"


def test_publish_recovers_after_final_manifest_write_failure(tmp_path: Path, monkeypatch) -> None:
    from services import pipeline

    lesson, data, media = publish_fixture(tmp_path)
    monkeypatch.setattr(pipeline, "DATA_DIR", data)
    monkeypatch.setattr(pipeline, "MEDIA_DIR", media)
    original_atomic_json = publication._atomic_json

    def fail_final_manifest(path, value):
        raise OSError("injected final failure")

    monkeypatch.setattr(publication, "_atomic_json", fail_final_manifest)

    with pytest.raises(OSError, match="final failure"):
        pipeline.publish(date(2026, 7, 12))

    monkeypatch.setattr(publication, "_atomic_json", original_atomic_json)
    pipeline.publish(date(2026, 7, 12))
    assert json.loads((media / "lessons" / lesson.id / "manifest.json").read_text())["status"] == "published"
