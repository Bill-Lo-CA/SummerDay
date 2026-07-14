import json
from datetime import date
from pathlib import Path

import pytest

import services.pipeline as pipeline
from services.api.schemas import DailyLesson
from services.nlp import NLPAnalysis
from services.pipeline import (
    SourceArticle,
    clean_segment,
    generate_lesson,
    lesson_generation_schema,
    materialize_vocabulary,
    normalize_focus_evidence,
    validate_evidence,
    vocabulary_candidates,
    write_generation_record,
)


def analysis_for(text: str) -> NLPAnalysis:
    return NLPAnalysis.model_validate(
        {
            "sentences": [
                {
                    "text": text,
                    "tokens": [
                        {
                            "text": "meurt",
                            "lemma": "mourir",
                            "upos": "VERB",
                            "feats": "Mood=Ind|VerbForm=Fin",
                            "head": 0,
                            "deprel": "root",
                        }
                    ],
                }
            ],
            "suitability": {
                "classification": "suitable",
                "word_count": 100,
                "sentence_count": 5,
                "average_sentence_length": 20,
                "longest_sentence_length": 25,
                "proper_noun_density": 0,
                "number_density": 0,
                "morphology_opportunities": 1,
            },
        }
    )


def candidate_analysis() -> NLPAnalysis:
    text = "Elle circule dans la ville avec son petit vélo rouge chaque matin."
    words = [
        ("Elle", "elle", "PRON"),
        ("circule", "circuler", "VERB"),
        ("dans", "dans", "ADP"),
        ("la", "le", "DET"),
        ("ville", "ville", "NOUN"),
        ("avec", "avec", "ADP"),
        ("son", "son", "DET"),
        ("petit", "petit", "ADJ"),
        ("vélo", "vélo", "NOUN"),
    ]
    return NLPAnalysis.model_validate(
        {
            "sentences": [
                {
                    "text": text,
                    "tokens": [
                        {
                            "text": surface,
                            "lemma": lemma,
                            "upos": upos,
                            "feats": None,
                            "head": 0,
                            "deprel": "dep",
                        }
                        for surface, lemma, upos in words
                    ],
                }
            ],
            "suitability": analysis_for(text).suitability.model_dump(),
        }
    )


def generation_payload(candidate_ids: list[str]) -> dict:
    return {
        "title": "La ville",
        "core_vocabulary": [
            {
                "candidate_id": candidate_id,
                "french_definition": "mot utile",
                "english_hint": "useful word",
            }
            for candidate_id in candidate_ids
        ],
        "morphology_focus": {"title": "verbe", "explanation": "forme", "evidence": "Elle circule dans la ville avec son petit vélo rouge chaque matin."},
        "pronunciation_focus": {"title": "ville", "explanation": "son", "evidence": "Elle circule dans la ville avec son petit vélo rouge chaque matin."},
    }


def multiword_analysis() -> NLPAnalysis:
    text = "Les enfants se réveillent et jouent un rôle."
    words = [
        ("Les", "le", "DET"),
        ("enfants", "enfant", "NOUN"),
        ("se", "soi", "PRON"),
        ("réveillent", "réveiller", "VERB"),
        ("et", "et", "CCONJ"),
        ("jouent", "jouer", "VERB"),
        ("un", "un", "DET"),
        ("rôle", "rôle", "NOUN"),
    ]
    return NLPAnalysis.model_validate(
        {
            "sentences": [
                {
                    "text": text,
                    "tokens": [
                        {
                            "text": surface,
                            "lemma": lemma,
                            "upos": upos,
                            "feats": "Mood=Ind|VerbForm=Fin" if upos == "VERB" else None,
                            "head": 0,
                            "deprel": "dep",
                        }
                        for surface, lemma, upos in words
                    ],
                }
            ],
            "suitability": analysis_for(text).suitability.model_dump(),
        }
    )


def test_pipeline_validates_generated_lesson() -> None:
    analysis = candidate_analysis()
    source = SourceArticle(1, 2, "Ville", "https://example.test/ville", "now", analysis.sentences[0].text)

    lesson = generate_lesson(source, date(2026, 7, 12), analysis, lambda _: generation_payload([f"v{index}" for index in range(1, 9)]))

    assert len(lesson.core_vocabulary) == 8
    assert lesson.id == "vikidia-1-2-2026-07-12"
    assert lesson.source_revision == "2"
    assert lesson.core_vocabulary[1].surface_form == "circule"
    assert lesson.core_vocabulary[1].lexical_item == "circuler"


def test_lesson_generation_schema_allows_only_deterministic_candidate_ids() -> None:
    candidates = vocabulary_candidates(candidate_analysis())

    schema = lesson_generation_schema(candidates)
    candidate_id_schema = schema["$defs"]["VocabularySelection"]["properties"]["candidate_id"]

    assert candidate_id_schema["enum"] == [candidate.id for candidate in candidates]
    assert "VOCAB-001" in candidate_id_schema["description"]


def test_default_generator_uses_dynamic_candidate_schema(monkeypatch) -> None:
    analysis = candidate_analysis()
    source = SourceArticle(1, 2, "Ville", "https://example.test/ville", "now", analysis.sentences[0].text)
    captured = {}

    class Provider:
        def __init__(self, schema) -> None:
            captured["schema"] = schema

        def generate(self, prompt: str) -> dict:
            return generation_payload([f"v{index}" for index in range(1, 9)])

    monkeypatch.setattr(pipeline, "OllamaContentProvider", Provider)

    generate_lesson(source, date(2026, 7, 12), analysis)

    assert captured["schema"]["$defs"]["VocabularySelection"]["properties"]["candidate_id"]["enum"] == [
        candidate.id for candidate in vocabulary_candidates(analysis)
    ]


def test_pipeline_rejects_evidence_not_in_article() -> None:
    payload = json.loads(Path("content/fixtures/daily-lesson.json").read_text())
    payload["core_vocabulary"][0]["surface_form"] = "absent"

    with pytest.raises(ValueError, match="surface_form"):
        validate_evidence(DailyLesson.model_validate(payload))


def test_pipeline_repairs_with_raw_payload_and_field_paths() -> None:
    analysis = candidate_analysis()
    source = SourceArticle(1, 2, "Ville", "https://example.test/ville", "now", analysis.sentences[0].text)
    responses = [generation_payload(["missing", *[f"v{index}" for index in range(2, 9)]]), generation_payload([f"v{index}" for index in range(1, 9)])]
    prompts = []
    diagnostics = []

    lesson = generate_lesson(
        source,
        date(2026, 7, 12),
        analysis,
        lambda prompt: (prompts.append(prompt), responses.pop(0))[1],
        diagnostics,
    )

    assert lesson.core_vocabulary[0].surface_form == "Elle"
    assert diagnostics[0]["validation_errors"][0]["path"] == "core_vocabulary.0.candidate_id"
    assert '"candidate_id": "missing"' in prompts[1]
    assert 'Allowed candidate IDs:\n["v1"' in prompts[1]


def test_multi_token_candidates_preserve_infinitives_and_surfaces() -> None:
    candidates = vocabulary_candidates(multiword_analysis())
    by_lexical_item = {candidate.lexical_item: candidate for candidate in candidates}
    payload = {
        "core_vocabulary": [
            {"candidate_id": by_lexical_item["se réveiller"].id},
            {"candidate_id": by_lexical_item["jouer un rôle"].id},
        ]
    }

    materialized = materialize_vocabulary(payload, candidates)["core_vocabulary"]

    assert materialized[0]["surface_form"] == "se réveillent"
    assert materialized[0]["lexical_item"] == "se réveiller"
    assert materialized[1]["surface_form"] == "jouent un rôle"
    assert materialized[1]["lexical_item"] == "jouer un rôle"


def test_generation_record_preserves_attempt_details(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pipeline, "DATA_DIR", tmp_path)
    record = {"source_article": {"title": "Ville"}, "attempts": [{"raw_response": {"title": "x"}, "normalized_payload": None, "validation_errors": [{"path": "title", "message": "missing"}]}]}

    path = write_generation_record(date(2026, 7, 12), record)

    assert json.loads(path.read_text()) == record


def test_focus_evidence_uses_matching_nlp_sentence() -> None:
    analysis = analysis_for("Il meurt.")
    payload = {
        "morphology_focus": {
            "title": "présent",
            "explanation": "La forme meurt vient du verbe mourir.",
            "evidence": "not source text",
        },
        "pronunciation_focus": {"title": "unrelated", "evidence": "still invalid"},
    }

    normalized = normalize_focus_evidence(payload, analysis)

    assert normalized["morphology_focus"]["evidence"] == "Il meurt."
    assert normalized["pronunciation_focus"]["evidence"] == "still invalid"


def test_clean_segment_keeps_complete_sentences() -> None:
    sentence = "Les abeilles vivent ensemble dans une grande colonie près des fleurs."
    segment = clean_segment(" ".join([sentence] * 10), minimum=20, maximum=30)

    assert segment == " ".join([sentence] * 2)
