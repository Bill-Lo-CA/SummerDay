import argparse
import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic import ValidationError

from services.api.schemas import DailyLesson
from services.audio.generation import attach_required_audio
from services.audio.publication import mark_audio_published, validate_publishable_lesson
from services.config import application_date
from services.nlp import NLPAnalysis, analyze_text
from services.providers.fake_tts import FakeTTSProvider
from services.providers.command_tts import CommandTTSProvider
from services.providers.ollama import OllamaContentProvider


VIKIDIA_API = "https://fr.vikidia.org/w/api.php"
DATA_DIR = Path(os.getenv("SUMMERDAY_DATA_DIR", "data"))
MEDIA_DIR = Path(os.getenv("SUMMERDAY_MEDIA_DIR", str(DATA_DIR / "media")))


@dataclass(frozen=True)
class SourceArticle:
    page_id: int
    revision_id: int
    title: str
    url: str
    retrieved_at: str
    text: str


def request_json(url: str, payload: dict | None = None, timeout: float = 180) -> dict:
    body = json.dumps(payload).encode() if payload else None
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "SummerDay/0.1"},
    )
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def clean_segment(text: str, minimum: int = 90, maximum: int = 160) -> str | None:
    text = re.sub(r"\s+", " ", text).strip()
    sentences = re.split(r"(?<=[.!?])\s+", text)
    selected: list[str] = []
    words = 0
    for sentence in sentences:
        count = len(sentence.split())
        if words + count > maximum:
            break
        selected.append(sentence)
        words += count
        if words >= minimum:
            break
    return " ".join(selected) if minimum <= words <= maximum else None


def fetch_vikidia_articles() -> list[SourceArticle]:
    params = urlencode(
        {
            "action": "query",
            "generator": "random",
            "grnnamespace": 0,
            "grnlimit": 20,
            "prop": "extracts|info|revisions",
            "explaintext": 1,
            "exintro": 1,
            "exlimit": "max",
            "inprop": "url",
            "rvprop": "ids|timestamp",
            "format": "json",
            "formatversion": 2,
        }
    )
    pages = request_json(f"{VIKIDIA_API}?{params}")["query"]["pages"]
    articles = []
    for page in pages:
        segment = clean_segment(page.get("extract", ""))
        if segment:
            revision = page["revisions"][0]
            articles.append(
                SourceArticle(
                    page_id=page["pageid"],
                    revision_id=revision["revid"],
                    title=page["title"],
                    url=page["fullurl"],
                    retrieved_at=datetime.now(timezone.utc).isoformat(),
                    text=segment,
                )
            )
    if not articles:
        raise RuntimeError("Vikidia returned no article with a usable 90–160 word segment.")
    return articles


def select_article(
    articles: list[SourceArticle], analyzer: Callable[[str], NLPAnalysis] = analyze_text
) -> tuple[SourceArticle, NLPAnalysis]:
    for article in articles:
        analysis = analyzer(article.text)
        if analysis.suitability.classification == "suitable":
            return article, analysis
    raise RuntimeError("Vikidia returned no article that passed A1 NLP suitability checks.")


def ollama_generate(prompt: str) -> dict:
    return OllamaContentProvider().generate(prompt)


def lesson_prompt(source: SourceArticle, lesson_date: date, analysis: NLPAnalysis) -> str:
    tokens = [
        f"{token.text}|{token.lemma}|{token.upos}|{token.feats or '_'}"
        for sentence in analysis.sentences
        for token in sentence.tokens
        if token.upos != "PUNCT"
    ]
    return f"""Create an A1 French lesson for {lesson_date.isoformat()} from only the source text below.
Return JSON matching the supplied schema. Select 8–12 useful core lexical items. Keep pronominal verbs and multiword expressions complete. Every surface_form, source_sentence, morphology evidence, and pronunciation evidence must occur verbatim in article_text. Definitions must be short French explanations; English hints are rescue translations. Do not invent source facts.
Use the deterministic NLP evidence below for lemmas, part of speech, and morphology. Avoid PROPN items.

Set these fields exactly:
id: vikidia-{source.page_id}-{source.revision_id}-{lesson_date.isoformat()}
source_title: {source.title}
source_url: {source.url}
source_revision: {source.revision_id}
article_text: {source.text}

Source text:
{source.text}

NLP tokens (surface|lemma|UPOS|features):
{chr(10).join(tokens)}"""


def validate_evidence(lesson: DailyLesson) -> DailyLesson:
    items = lesson.core_vocabulary
    lexical_items = [item.lexical_item.casefold() for item in items]
    if len(lexical_items) != len(set(lexical_items)):
        raise ValueError("core vocabulary contains duplicates")
    for item in items:
        if item.surface_form not in lesson.article_text:
            raise ValueError(f"surface form is absent from article: {item.surface_form}")
        if item.source_sentence not in lesson.article_text:
            raise ValueError(f"source sentence is absent from article: {item.source_sentence}")
    for focus in (lesson.morphology_focus, lesson.pronunciation_focus):
        if focus.evidence not in lesson.article_text:
            raise ValueError(f"focus evidence is absent from article: {focus.evidence}")
    return lesson


def deduplicate_vocabulary(payload: dict) -> dict:
    seen: set[str] = set()
    items = []
    for item in payload.get("core_vocabulary", []):
        key = item.get("lexical_item", "").casefold().strip()
        if key and key not in seen:
            seen.add(key)
            items.append(item)
    return {**payload, "core_vocabulary": items}


def apply_source_fields(payload: dict, source: SourceArticle, lesson_date: date) -> dict:
    return {
        **payload,
        "id": f"vikidia-{source.page_id}-{source.revision_id}-{lesson_date.isoformat()}",
        "level": "A1",
        "source_title": source.title,
        "source_url": source.url,
        "source_revision": str(source.revision_id),
        "article_text": source.text,
    }


def normalize_vocabulary(payload: dict, analysis: NLPAnalysis) -> dict:
    tokens = [token for sentence in analysis.sentences for token in sentence.tokens]
    for item in payload.get("core_vocabulary", []):
        source_sentence = next(
            (
                sentence.text
                for sentence in analysis.sentences
                if item.get("surface_form", "").casefold() in sentence.text.casefold()
            ),
            None,
        )
        if source_sentence:
            item["source_sentence"] = source_sentence
        surface = item.get("surface_form", "").casefold().split()
        matches = [
            tokens[index : index + len(surface)]
            for index in range(len(tokens) - len(surface) + 1)
            if [token.text.casefold() for token in tokens[index : index + len(surface)]] == surface
        ]
        if not matches:
            continue
        match = matches[0]
        verbs = [token for token in match if token.upos in {"VERB", "AUX"}]
        if len(match) == 1 and verbs:
            item["lexical_item"] = verbs[0].lemma
        reflexive = any(
            token.text.casefold() in {"se", "s'", "s’"} or token.lemma.casefold() in {"se", "soi"}
            for token in match
        ) and verbs
        if reflexive:
            item["lexical_item"] = f"se {verbs[-1].lemma}"
        if len(match) == 1 or reflexive:
            head = verbs[0] if verbs else match[0]
            item["lemma"] = head.lemma
            item["part_of_speech"] = head.upos.lower()
            item["morphology"] = head.feats
    payload["core_vocabulary"] = [
        item for item in payload.get("core_vocabulary", []) if item.get("part_of_speech") != "propn"
    ]
    return payload


def normalize_focus_evidence(payload: dict, analysis: NLPAnalysis) -> dict:
    sentences = [sentence.text for sentence in analysis.sentences]
    for key in ("morphology_focus", "pronunciation_focus"):
        focus = payload.get(key, {})
        if focus.get("evidence") in sentences:
            continue
        focus_text = f"{focus.get('title', '')} {focus.get('explanation', '')}"
        terms = {word.casefold() for word in re.findall(r"[\wÀ-ÿ]+", focus_text) if len(word) > 2}
        scored = [(sum(term in sentence.casefold() for term in terms), sentence) for sentence in sentences]
        score, sentence = max(scored, default=(0, ""))
        if score:
            focus["evidence"] = sentence
    return payload


def generate_lesson(
    source: SourceArticle,
    lesson_date: date,
    analysis: NLPAnalysis,
    generator: Callable[[str], dict] = ollama_generate,
) -> DailyLesson:
    prompt = lesson_prompt(source, lesson_date, analysis)
    error = ""
    for _ in range(2):
        try:
            payload = apply_source_fields(generator(prompt), source, lesson_date)
            payload = normalize_vocabulary(payload, analysis)
            payload = normalize_focus_evidence(payload, analysis)
            payload = deduplicate_vocabulary(payload)
            return validate_evidence(DailyLesson.model_validate(payload))
        except (ValidationError, ValueError, KeyError, json.JSONDecodeError) as exc:
            error = str(exc)
            prompt += f"\n\nRepair the JSON. Validation errors:\n{error}"
    raise RuntimeError(f"Ollama output remained invalid after one repair: {error}")


def generate(lesson_date: date) -> Path:
    source, analysis = select_article(fetch_vikidia_articles())
    lesson = generate_lesson(source, lesson_date, analysis)
    provider_name = os.getenv("SUMMERDAY_TTS_PROVIDER", "command")
    if provider_name == "command":
        command = os.getenv("SUMMERDAY_TTS_COMMAND")
        if not command:
            raise RuntimeError("SUMMERDAY_TTS_COMMAND is required for command TTS")
        provider = CommandTTSProvider(command, os.getenv("SUMMERDAY_TTS_MODEL", "configured"))
    else:
        provider = FakeTTSProvider()
    lesson = attach_required_audio(lesson, analysis, provider, MEDIA_DIR)
    draft = DATA_DIR / "drafts" / f"{lesson_date.isoformat()}.json"
    analysis_path = DATA_DIR / "analysis" / f"{lesson_date.isoformat()}.json"
    draft.parent.mkdir(parents=True, exist_ok=True)
    analysis_path.parent.mkdir(parents=True, exist_ok=True)
    draft.write_text(lesson.model_dump_json(indent=2) + "\n")
    analysis_path.write_text(analysis.model_dump_json(indent=2) + "\n")
    return draft


def publish(lesson_date: date) -> Path:
    draft = DATA_DIR / "drafts" / f"{lesson_date.isoformat()}.json"
    target = DATA_DIR / "lessons" / draft.name
    if target.exists():
        raise FileExistsError(f"Published lesson is immutable: {target}")
    lesson = validate_evidence(DailyLesson.model_validate_json(draft.read_text()))
    lesson = validate_publishable_lesson(lesson, MEDIA_DIR)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(draft, target)
    analysis = DATA_DIR / "analysis" / draft.name
    shutil.copyfile(analysis, target.with_suffix(".analysis.json"))
    mark_audio_published(lesson, MEDIA_DIR)
    return target


def review(lesson_date: date) -> Path:
    draft = DATA_DIR / "drafts" / f"{lesson_date.isoformat()}.json"
    lesson = DailyLesson.model_validate_json(draft.read_text())
    if lesson.pronunciation_focus.reference_audio is None:
        raise ValueError("audio must be generated before pronunciation review")
    lesson.pronunciation_focus.review_status = "approved"
    lesson.pronunciation_focus.reference_audio.review_status = "approved"
    draft.write_text(lesson.model_dump_json(indent=2) + "\n")
    manifest = MEDIA_DIR / "lessons" / lesson.id / "manifest.json"
    data = json.loads(manifest.read_text())
    for asset in data["assets"]:
        if asset["asset_id"] == lesson.pronunciation_focus.reference_audio.asset_id:
            asset["review_status"] = "approved"
    manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return draft


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate or publish a daily lesson.")
    parser.add_argument("command", choices=("generate", "review", "publish"))
    parser.add_argument("--date", type=date.fromisoformat, default=application_date())
    args = parser.parse_args()
    path = {"generate": generate, "review": review, "publish": publish}[args.command](args.date)
    print(path)


if __name__ == "__main__":
    main()
