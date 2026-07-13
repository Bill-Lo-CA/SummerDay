import json
from pathlib import Path

import pytest

from services.audio.generation import attach_required_audio
from services.audio.publication import mark_audio_published, validate_publishable_lesson
from services.api.schemas import DailyLesson
from services.nlp import NLPAnalysis
from services.providers.fake_tts import FakeTTSProvider


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


def test_required_audio_package_can_be_published(tmp_path: Path) -> None:
    lesson, analysis = lesson_and_analysis()
    lesson.pronunciation_focus.review_status = "approved"
    attach_required_audio(lesson, analysis, FakeTTSProvider(), tmp_path)
    assert lesson.pronunciation_focus.review_status == "approved"
    assert lesson.pronunciation_focus.reference_audio.review_status == "pending"
    lesson.pronunciation_focus.review_status = "approved"
    lesson.pronunciation_focus.reference_audio.review_status = "approved"

    validate_publishable_lesson(lesson, tmp_path)
    mark_audio_published(lesson, tmp_path)
    assert json.loads((tmp_path / "lessons" / lesson.id / "manifest.json").read_text())["status"] == "published"


def test_missing_vocabulary_audio_blocks_publication(tmp_path: Path) -> None:
    lesson, analysis = lesson_and_analysis()
    lesson.pronunciation_focus.review_status = "approved"
    attach_required_audio(lesson, analysis, FakeTTSProvider(), tmp_path)
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
