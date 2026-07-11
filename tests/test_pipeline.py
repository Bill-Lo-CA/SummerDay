import json
from datetime import date
from pathlib import Path

import pytest

from services.api.schemas import DailyLesson
from services.nlp import NLPAnalysis, TokenAnalysis
from services.pipeline import (
    SourceArticle,
    clean_segment,
    deduplicate_vocabulary,
    generate_lesson,
    normalize_focus_evidence,
    normalize_vocabulary,
    validate_evidence,
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


def reflexive_analysis() -> NLPAnalysis:
    analysis = analysis_for("Ils se réveillent.")
    analysis.sentences[0].tokens = [
        TokenAnalysis.model_validate(
            {
            "text": "se",
            "lemma": "soi",
            "upos": "PRON",
            "feats": "Person=3|PronType=Prs",
            "head": 2,
            "deprel": "expl:pv",
            }
        ),
        TokenAnalysis.model_validate(
            {
            "text": "réveillent",
            "lemma": "réveiller",
            "upos": "VERB",
            "feats": "Mood=Ind|VerbForm=Fin",
            "head": 0,
            "deprel": "root",
            }
        ),
    ]
    return analysis


def test_pipeline_validates_generated_lesson() -> None:
    payload = json.loads(Path("content/fixtures/daily-lesson.json").read_text())
    source = SourceArticle(1, 2, "Abeille", payload["source_url"], "now", payload["article_text"])

    lesson = generate_lesson(source, date(2026, 7, 12), analysis_for(source.text), lambda _: payload)

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


def test_single_word_verb_uses_nlp_lemma() -> None:
    payload = {
        "core_vocabulary": [
            {"surface_form": "meurt", "lexical_item": "meurt", "source_sentence": "Il ... meurt."}
        ]
    }

    normalized = normalize_vocabulary(payload, analysis_for("Il meurt."))

    assert normalized["core_vocabulary"][0]["lexical_item"] == "mourir"
    assert normalized["core_vocabulary"][0]["source_sentence"] == "Il meurt."


def test_reflexive_verb_keeps_reflexive_marker() -> None:
    payload = {"core_vocabulary": [{"surface_form": "se réveillent", "lexical_item": "réveillent"}]}

    normalized = normalize_vocabulary(payload, reflexive_analysis())

    assert normalized["core_vocabulary"][0]["lexical_item"] == "se réveiller"


def test_proper_nouns_are_removed_from_vocabulary() -> None:
    analysis = analysis_for("Paris")
    analysis.sentences[0].tokens[0].text = "Paris"
    analysis.sentences[0].tokens[0].lemma = "Paris"
    analysis.sentences[0].tokens[0].upos = "PROPN"
    payload = {"core_vocabulary": [{"surface_form": "Paris", "lexical_item": "Paris"}]}

    assert normalize_vocabulary(payload, analysis)["core_vocabulary"] == []


def test_non_reflexive_multiword_item_is_not_reduced_to_one_lemma() -> None:
    analysis = reflexive_analysis()
    analysis.sentences[0].tokens[0].text = "faire"
    analysis.sentences[0].tokens[0].lemma = "faire"
    analysis.sentences[0].tokens[0].upos = "VERB"
    analysis.sentences[0].tokens[1].text = "attention"
    analysis.sentences[0].tokens[1].lemma = "attention"
    analysis.sentences[0].tokens[1].upos = "NOUN"
    payload = {"core_vocabulary": [{"surface_form": "faire attention", "lexical_item": "faire attention"}]}

    item = normalize_vocabulary(payload, analysis)["core_vocabulary"][0]

    assert item["lexical_item"] == "faire attention"
    assert "lemma" not in item


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
