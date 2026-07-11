import json
from datetime import date
from pathlib import Path

import pytest

from services.api.schemas import DailyLesson
from services.pipeline import (
    SourceArticle,
    clean_segment,
    deduplicate_vocabulary,
    generate_lesson,
    validate_evidence,
)


def test_pipeline_validates_generated_lesson() -> None:
    payload = json.loads(Path("content/fixtures/daily-lesson.json").read_text())
    source = SourceArticle(1, 2, "Abeille", payload["source_url"], "now", payload["article_text"])

    lesson = generate_lesson(source, date(2026, 7, 12), lambda _: payload)

    assert len(lesson.core_vocabulary) == 8
    assert lesson.id == "vikidia-1-2-2026-07-12"
    assert lesson.source_revision == "2"


def test_pipeline_rejects_evidence_not_in_article() -> None:
    payload = json.loads(Path("content/fixtures/daily-lesson.json").read_text())
    payload["core_vocabulary"][0]["surface_form"] = "absent"

    with pytest.raises(ValueError, match="surface form"):
        validate_evidence(DailyLesson.model_validate(payload))


def test_model_output_deduplicates_lexical_items() -> None:
    payload = json.loads(Path("content/fixtures/daily-lesson.json").read_text())
    payload["core_vocabulary"].append(payload["core_vocabulary"][0])

    assert len(deduplicate_vocabulary(payload)["core_vocabulary"]) == 8


def test_clean_segment_keeps_complete_sentences() -> None:
    sentence = "Les abeilles vivent ensemble dans une grande colonie près des fleurs."
    segment = clean_segment(" ".join([sentence] * 10), minimum=20, maximum=30)

    assert segment == " ".join([sentence] * 2)
