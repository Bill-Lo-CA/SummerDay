import sys
from datetime import date
from pathlib import Path

import pytest

import services.pipeline as pipeline
from services.api.schemas import DailyLesson
from services.nlp import NLPAnalysis


def test_cli_defaults_to_application_date(monkeypatch, capsys) -> None:
    expected = date(2026, 7, 12)
    captured: dict[str, date] = {}
    monkeypatch.setattr(pipeline, "application_date", lambda: expected)
    def fake_publish(lesson_date: date) -> Path:
        captured["date"] = lesson_date
        return Path("draft.json")

    monkeypatch.setattr(pipeline, "publish", fake_publish)
    monkeypatch.setattr(sys, "argv", ["pipeline", "publish"])

    pipeline.main()

    assert captured["date"] == expected
    assert capsys.readouterr().out == "draft.json\n"


def test_generate_content_persists_draft_and_analysis_before_audio(tmp_path: Path, monkeypatch) -> None:
    lesson_date = date(2026, 7, 12)
    lesson = DailyLesson.model_validate_json(Path("content/fixtures/daily-lesson.json").read_text())
    analysis = NLPAnalysis.model_validate(
        {
            "sentences": [],
            "suitability": {
                "classification": "suitable", "word_count": 1, "sentence_count": 1,
                "average_sentence_length": 1, "longest_sentence_length": 1,
                "proper_noun_density": 0, "number_density": 0, "morphology_opportunities": 0,
            },
        }
    )
    source = pipeline.SourceArticle(1, 2, "Abeille", "https://example.test", "now", lesson.article_text)
    monkeypatch.setattr(pipeline, "DATA_DIR", tmp_path)
    monkeypatch.setattr(pipeline, "fetch_vikidia_articles", lambda: [])
    monkeypatch.setattr(pipeline, "select_article", lambda _: (source, analysis))
    monkeypatch.setattr(pipeline, "generate_lesson", lambda *args, **kwargs: lesson)

    draft = pipeline.generate_content(lesson_date)

    assert DailyLesson.model_validate_json(draft.read_text()).id == lesson.id
    assert (tmp_path / "analysis" / "2026-07-12.json").exists()


def test_generate_content_persists_provider_failure_before_reraising(tmp_path: Path, monkeypatch) -> None:
    lesson_date = date(2026, 7, 12)
    analysis = NLPAnalysis.model_validate({"sentences": [], "suitability": {
        "classification": "suitable", "word_count": 1, "sentence_count": 1,
        "average_sentence_length": 1, "longest_sentence_length": 1,
        "proper_noun_density": 0, "number_density": 0, "morphology_opportunities": 0,
    }})
    source = pipeline.SourceArticle(1, 2, "Abeille", "https://example.test", "now", "Texte.")
    monkeypatch.setattr(pipeline, "DATA_DIR", tmp_path)
    monkeypatch.setattr(pipeline, "find_suitable_article", lambda: (source, analysis))
    monkeypatch.setattr(pipeline, "generate_lesson", lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError("timed out")))

    with pytest.raises(TimeoutError):
        pipeline.generate_content(lesson_date)

    record = __import__("json").loads((tmp_path / "generation" / "2026-07-12.json").read_text())
    assert record["terminal_failure"] == {
        "exception_type": "TimeoutError",
        "message": "timed out",
        "stage": "content_generation",
        "provider": "ollama",
    }


def test_generate_audio_uses_existing_draft_without_fetching_content(tmp_path: Path, monkeypatch) -> None:
    lesson_date = date(2026, 7, 12)
    lesson = DailyLesson.model_validate_json(Path("content/fixtures/daily-lesson.json").read_text())
    analysis = NLPAnalysis.model_validate(
        {
            "sentences": [],
            "suitability": {
                "classification": "suitable", "word_count": 1, "sentence_count": 1,
                "average_sentence_length": 1, "longest_sentence_length": 1,
                "proper_noun_density": 0, "number_density": 0, "morphology_opportunities": 0,
            },
        }
    )
    monkeypatch.setattr(pipeline, "DATA_DIR", tmp_path)
    monkeypatch.setattr(pipeline, "MEDIA_DIR", tmp_path / "media")
    draft = pipeline.draft_path(lesson_date)
    draft.parent.mkdir(parents=True)
    draft.write_text(lesson.model_dump_json())
    analysis_file = pipeline.analysis_path(lesson_date)
    analysis_file.parent.mkdir(parents=True)
    analysis_file.write_text(analysis.model_dump_json())
    monkeypatch.setattr(pipeline, "fetch_vikidia_articles", lambda: (_ for _ in ()).throw(AssertionError("must not fetch")))
    monkeypatch.setattr(pipeline, "tts_provider", lambda: pipeline.FakeTTSProvider())

    assert pipeline.generate_audio(lesson_date) == draft
    assert DailyLesson.model_validate_json(draft.read_text()).learning_audio is not None


def test_tts_provider_selects_piper(monkeypatch) -> None:
    created = {}

    class StubPiper:
        def __init__(self, *args) -> None:
            created["args"] = args

    monkeypatch.setattr(pipeline, "PiperTTSProvider", StubPiper)
    monkeypatch.setenv("SUMMERDAY_TTS_PROVIDER", "piper")
    monkeypatch.setenv("SUMMERDAY_PIPER_MODEL", "data/piper/fr_FR-tom-medium.onnx")

    provider = pipeline.tts_provider()

    assert isinstance(provider, StubPiper)
    assert created["args"][0] == "data/piper/fr_FR-tom-medium.onnx"


def test_tts_provider_rejects_unknown_value(monkeypatch) -> None:
    monkeypatch.setenv("SUMMERDAY_TTS_PROVIDER", "unknown")

    with pytest.raises(ValueError, match="unknown TTS provider"):
        pipeline.tts_provider()
