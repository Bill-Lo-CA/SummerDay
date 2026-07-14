import argparse
import json
import os
import re
import shutil
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic import ValidationError

from services.api.schemas import DailyLesson, LessonGeneration
from services.audio.generation import AudioGenerationError, attach_required_audio
from services.audio.publication import mark_audio_published, validate_publishable_lesson
from services.config import application_date
from services.nlp import NLPAnalysis, analyze_text
from services.providers.fake_tts import FakeTTSProvider
from services.providers.command_tts import CommandTTSProvider
from services.providers.ollama import OllamaContentProvider
from services.providers.piper_tts import PiperTTSProvider


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


def find_suitable_article(
    fetcher: Callable[[], list[SourceArticle]] | None = None,
    analyzer: Callable[[str], NLPAnalysis] | None = None,
    max_batches: int | None = None,
) -> tuple[SourceArticle, NLPAnalysis]:
    fetcher = fetcher or fetch_vikidia_articles
    default_analyzer = analyzer is None
    analyzer = analyzer or analyze_text
    batches = max_batches if max_batches is not None else int(os.getenv("SUMMERDAY_VIKIDIA_MAX_BATCHES", "5"))
    if batches <= 0:
        raise ValueError("SUMMERDAY_VIKIDIA_MAX_BATCHES must be greater than zero")

    last_error: RuntimeError | None = None
    for batch in range(1, batches + 1):
        try:
            articles = fetcher()
            return select_article(articles) if default_analyzer else select_article(articles, analyzer)
        except RuntimeError as exc:
            last_error = exc
            print(f"Vikidia batch {batch}/{batches} skipped: {exc}")

    message = f"Vikidia returned no A1-suitable article after {batches} batch(es)."
    if last_error is not None:
        message = f"{message} Last error: {last_error}"
    raise RuntimeError(message)


@dataclass(frozen=True)
class VocabularyCandidate:
    id: str
    surface_form: str
    lexical_item: str
    part_of_speech: str
    lemma: str
    morphology: str | None
    source_sentence: str


class EvidenceValidationError(ValueError):
    def __init__(self, errors: list[dict[str, str]]) -> None:
        self.errors = errors
        super().__init__("; ".join(f"{error['path']}: {error['message']}" for error in errors))


def vocabulary_candidates(analysis: NLPAnalysis) -> list[VocabularyCandidate]:
    candidates = []

    def add_candidate(tokens, source_sentence: str) -> None:
        first = tokens[0]
        verbs = [token for token in tokens if token.upos in {"VERB", "AUX"}]
        reflexive = first.text.casefold() in {"se", "s'", "s’"} and verbs
        if reflexive:
            lexical_item = f"se {verbs[-1].lemma}"
        elif first.upos in {"VERB", "AUX"}:
            lexical_item = " ".join(token.lemma for token in tokens)
        else:
            lexical_item = " ".join(token.text for token in tokens)
        candidates.append(
            VocabularyCandidate(
                id=f"v{len(candidates) + 1}",
                surface_form=" ".join(token.text for token in tokens),
                lexical_item=lexical_item,
                part_of_speech="expression",
                lemma=lexical_item,
                morphology=verbs[0].feats if verbs else None,
                source_sentence=source_sentence,
            )
        )

    for sentence in analysis.sentences:
        for token in sentence.tokens:
            if token.upos in {"PUNCT", "PROPN"}:
                continue
            candidates.append(
                VocabularyCandidate(
                    id=f"v{len(candidates) + 1}",
                    surface_form=token.text,
                    lexical_item=token.lemma,
                    part_of_speech=token.upos.lower(),
                    lemma=token.lemma,
                    morphology=token.feats,
                    source_sentence=sentence.text,
                )
            )
        tokens = sentence.tokens
        for index, token in enumerate(tokens):
            following = tokens[index + 1 :]
            if token.text.casefold() in {"se", "s'", "s’"} and following and following[0].upos in {"VERB", "AUX"}:
                add_candidate(tokens[index : index + 2], sentence.text)
            if token.upos in {"VERB", "AUX"}:
                if following and following[0].upos == "ADP":
                    add_candidate(tokens[index : index + 2], sentence.text)
                if len(following) >= 2 and following[0].upos == "DET" and following[1].upos == "NOUN":
                    add_candidate(tokens[index : index + 3], sentence.text)
            if token.upos == "DET":
                for length in (2, 3):
                    span = tokens[index : index + length]
                    if len(span) == length and span[-1].upos == "NOUN":
                        add_candidate(span, sentence.text)
    unique_candidates = []
    seen_lexical_items = set()
    for candidate in candidates:
        lexical_item = candidate.lexical_item.casefold()
        if lexical_item in seen_lexical_items:
            continue
        seen_lexical_items.add(lexical_item)
        unique_candidates.append(replace(candidate, id=f"v{len(unique_candidates) + 1}"))
    return unique_candidates


def lesson_generation_schema(candidates: list[VocabularyCandidate]) -> dict:
    schema = LessonGeneration.model_json_schema()
    candidate_id_schema = schema["$defs"]["VocabularySelection"]["properties"]["candidate_id"]
    candidate_id_schema["enum"] = [candidate.id for candidate in candidates]
    candidate_id_schema["description"] = (
        "Copy exactly one candidate ID from the vocabulary candidate list. "
        "Never invent placeholder IDs such as VOCAB-001."
    )
    return schema


def lesson_prompt(source: SourceArticle, lesson_date: date, analysis: NLPAnalysis) -> str:
    candidates = vocabulary_candidates(analysis)
    candidate_text = [
        f"{item.id}|{item.surface_form}|{item.lexical_item}|{item.part_of_speech}|"
        f"{item.morphology or '_'}|{item.source_sentence}"
        for item in candidates
    ]
    return f"""Create an A1 French lesson for {lesson_date.isoformat()} from only the source text below.
Return JSON matching the supplied schema. Select 8–12 different useful core vocabulary candidate IDs. Copy every candidate_id exactly from the candidate list. Use each candidate ID at most once. Do not select two candidates with the same lexical item. Every candidate_id must be copied exactly from the first column of the candidate list below. Valid IDs look like v1, v2, and v3. Never invent IDs such as VOCAB-001. Do not emit or rewrite surface forms, lemmas, part of speech, morphology, or source sentences; the pipeline fills those from the selected IDs. Definitions must be short French explanations; English hints are rescue translations. Do not invent source facts.

Set these fields exactly:
id: vikidia-{source.page_id}-{source.revision_id}-{lesson_date.isoformat()}
source_title: {source.title}
source_url: {source.url}
source_revision: {source.revision_id}
article_text: {source.text}

Source text:
{source.text}

Vocabulary candidates (id|surface|lexical item|part of speech|morphology|source sentence):
{chr(10).join(candidate_text)}"""


def validate_evidence(lesson: DailyLesson) -> DailyLesson:
    items = lesson.core_vocabulary
    lexical_items = [item.lexical_item.casefold() for item in items]
    errors = []
    if len(lexical_items) != len(set(lexical_items)):
        errors.append({"path": "core_vocabulary", "message": "contains duplicate lexical items"})
    for index, item in enumerate(items):
        if item.surface_form not in lesson.article_text:
            errors.append(
                {
                    "path": f"core_vocabulary.{index}.surface_form",
                    "message": f"is absent from article: {item.surface_form}",
                }
            )
        if item.source_sentence not in lesson.article_text:
            errors.append(
                {
                    "path": f"core_vocabulary.{index}.source_sentence",
                    "message": f"is absent from article: {item.source_sentence}",
                }
            )
    for name, focus in (("morphology_focus", lesson.morphology_focus), ("pronunciation_focus", lesson.pronunciation_focus)):
        if focus.evidence not in lesson.article_text:
            errors.append({"path": f"{name}.evidence", "message": f"is absent from article: {focus.evidence}"})
    if errors:
        raise EvidenceValidationError(errors)
    return lesson


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


def materialize_vocabulary(payload: dict, candidates: list[VocabularyCandidate]) -> dict:
    by_id = {candidate.id: candidate for candidate in candidates}
    items = []
    errors = []
    selected_candidate_ids = set()
    selected_lexical_items = {}
    for index, selection in enumerate(payload.get("core_vocabulary", [])):
        candidate_id = selection.get("candidate_id", "")
        candidate = by_id.get(candidate_id)
        if candidate is None:
            errors.append(
                {
                    "path": f"core_vocabulary.{index}.candidate_id",
                    "message": f"is not a known vocabulary candidate: {candidate_id}",
                }
            )
            continue
        if candidate_id in selected_candidate_ids:
            errors.append(
                {
                    "path": f"core_vocabulary.{index}.candidate_id",
                    "message": f"is selected more than once: {candidate_id}; each candidate ID may be used only once",
                }
            )
            continue
        lexical_item = candidate.lexical_item.casefold()
        previous_candidate_id = selected_lexical_items.get(lexical_item)
        if previous_candidate_id is not None:
            errors.append(
                {
                    "path": f"core_vocabulary.{index}.candidate_id",
                    "message": (
                        f"{candidate_id} resolves to duplicate lexical item "
                        f"'{candidate.lexical_item}', already selected by {previous_candidate_id}"
                    ),
                }
            )
            continue
        selected_candidate_ids.add(candidate_id)
        selected_lexical_items[lexical_item] = candidate_id
        items.append(
            {
                **selection,
                "surface_form": candidate.surface_form,
                "lexical_item": candidate.lexical_item,
                "part_of_speech": candidate.part_of_speech,
                "lemma": candidate.lemma,
                "morphology": candidate.morphology,
                "source_sentence": candidate.source_sentence,
            }
        )
    if errors:
        raise EvidenceValidationError(errors)
    return {**payload, "core_vocabulary": items}


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


def error_details(exc: Exception) -> list[dict[str, str]]:
    if isinstance(exc, EvidenceValidationError):
        return exc.errors
    if isinstance(exc, ValidationError):
        return [
            {"path": ".".join(str(part) for part in error["loc"]), "message": error["msg"]}
            for error in exc.errors(include_url=False)
        ]
    return [{"path": "$", "message": str(exc)}]


def sanitized_error_message(exc: Exception) -> str:
    message = re.sub(r"https?://\S+", "<url>", str(exc))
    return re.sub(
        r"(?i)((?:authorization\s*[:=]\s*(?:bearer\s+)?|token|password|secret|api[_-]?key)\s*[:=]?\s*)\S+",
        r"\1<redacted>",
        message,
    )


def write_generation_record(lesson_date: date, record: dict) -> Path:
    path = DATA_DIR / "generation" / f"{lesson_date.isoformat()}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    return path


def generate_lesson(
    source: SourceArticle,
    lesson_date: date,
    analysis: NLPAnalysis,
    generator: Callable[[str], dict] | None = None,
    diagnostics: list[dict] | None = None,
) -> DailyLesson:
    prompt = lesson_prompt(source, lesson_date, analysis)
    errors = []
    candidates = vocabulary_candidates(analysis)
    allowed_candidate_ids = [candidate.id for candidate in candidates]
    if generator is None:
        generator = OllamaContentProvider(schema=lesson_generation_schema(candidates)).generate
    for attempt in range(2):
        raw_payload = None
        normalized_payload = None
        try:
            raw_payload = generator(prompt)
            payload = LessonGeneration.model_validate(raw_payload).model_dump()
            payload = apply_source_fields(payload, source, lesson_date)
            payload = materialize_vocabulary(payload, candidates)
            normalized_payload = normalize_focus_evidence(payload, analysis)
            lesson = validate_evidence(DailyLesson.model_validate(normalized_payload))
            if diagnostics is not None:
                diagnostics.append(
                    {
                        "attempt": attempt + 1,
                        "raw_response": raw_payload,
                        "normalized_payload": normalized_payload,
                        "validation_errors": [],
                    }
                )
            return lesson
        except (ValidationError, EvidenceValidationError, KeyError, json.JSONDecodeError) as exc:
            errors = error_details(exc)
            if diagnostics is not None:
                diagnostics.append(
                    {
                        "attempt": attempt + 1,
                        "raw_response": raw_payload,
                        "normalized_payload": normalized_payload,
                        "validation_errors": errors,
                    }
                )
            prompt += (
                "\n\nRepair the invalid JSON below. Return only replacement JSON.\n"
                "Every core_vocabulary candidate_id must be copied exactly from the allowed ID list below.\n"
                "Do not use placeholders such as VOCAB-001, VOCAB-002, or similar IDs.\n"
                "Every candidate ID may appear at most once.\n"
                "Every selected candidate must represent a different lexical item.\n"
                f"Allowed candidate IDs:\n{json.dumps(allowed_candidate_ids, ensure_ascii=False)}\n"
                f"Invalid payload:\n{json.dumps(raw_payload, ensure_ascii=False)}\n"
                f"Validation errors:\n{json.dumps(errors, ensure_ascii=False)}"
            )
    raise RuntimeError(f"Ollama output remained invalid after one repair: {json.dumps(errors, ensure_ascii=False)}")


def draft_path(lesson_date: date) -> Path:
    return DATA_DIR / "drafts" / f"{lesson_date.isoformat()}.json"


def analysis_path(lesson_date: date) -> Path:
    return DATA_DIR / "analysis" / f"{lesson_date.isoformat()}.json"


def generate_content(lesson_date: date) -> Path:
    draft = draft_path(lesson_date)
    if draft.exists():
        raise FileExistsError(f"Draft already exists: {draft}")
    source, analysis = find_suitable_article()
    diagnostics: list[dict] = []
    record = {"source_article": asdict(source), "attempts": diagnostics}
    try:
        lesson = generate_lesson(source, lesson_date, analysis, diagnostics=diagnostics)
    except Exception as exc:
        record["terminal_failure"] = {
            "exception_type": type(exc).__name__,
            "message": sanitized_error_message(exc),
            "stage": "content_generation",
            "provider": "ollama",
        }
        write_generation_record(lesson_date, record)
        raise
    write_generation_record(lesson_date, record)
    draft.parent.mkdir(parents=True, exist_ok=True)
    analysis_file = analysis_path(lesson_date)
    analysis_file.parent.mkdir(parents=True, exist_ok=True)
    draft.write_text(lesson.model_dump_json(indent=2) + "\n")
    analysis_file.write_text(analysis.model_dump_json(indent=2) + "\n")
    return draft


def tts_provider():
    provider_name = os.getenv("SUMMERDAY_TTS_PROVIDER", "command")
    if provider_name == "piper":
        return PiperTTSProvider(
            os.getenv("SUMMERDAY_PIPER_MODEL", "data/piper/fr_FR-siwis-medium.onnx"),
            float(os.getenv("SUMMERDAY_PIPER_BASELINE_WPM", "100")),
            float(os.getenv("SUMMERDAY_PIPER_LENGTH_SCALE", "1")),
        )
    elif provider_name == "command":
        command = os.getenv("SUMMERDAY_TTS_COMMAND")
        if not command:
            raise RuntimeError("SUMMERDAY_TTS_COMMAND is required for command TTS")
        return CommandTTSProvider(command, os.getenv("SUMMERDAY_TTS_MODEL", "configured"))
    if provider_name == "fake":
        return FakeTTSProvider()
    raise ValueError(f"unknown TTS provider: {provider_name}")


def generate_audio(lesson_date: date) -> Path:
    draft = draft_path(lesson_date)
    analysis_file = analysis_path(lesson_date)
    if not draft.exists() or not analysis_file.exists():
        raise FileNotFoundError("generate-content must complete before generate-audio")
    lesson = DailyLesson.model_validate_json(draft.read_text())
    analysis = NLPAnalysis.model_validate_json(analysis_file.read_text())

    def save(current: DailyLesson) -> None:
        draft.write_text(current.model_dump_json(indent=2) + "\n")

    try:
        attach_required_audio(lesson, analysis, tts_provider(), MEDIA_DIR, on_progress=save)
    except AudioGenerationError:
        raise
    return draft


def generate(lesson_date: date) -> Path:
    generate_content(lesson_date)
    return generate_audio(lesson_date)


def publish(lesson_date: date) -> Path:
    draft = DATA_DIR / "drafts" / f"{lesson_date.isoformat()}.json"
    target = DATA_DIR / "lessons" / draft.name
    lesson = validate_evidence(DailyLesson.model_validate_json(draft.read_text()))
    lesson = validate_publishable_lesson(lesson, MEDIA_DIR)
    analysis = DATA_DIR / "analysis" / draft.name
    if not analysis.exists():
        raise FileNotFoundError(f"analysis is missing: {analysis}")
    published_analysis = target.with_suffix(".analysis.json")
    manifest_path = MEDIA_DIR / "lessons" / lesson.id / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("status") == "published":
        if target.read_bytes() != draft.read_bytes() or published_analysis.read_bytes() != analysis.read_bytes():
            raise ValueError("published package conflicts with the current validated package")
        return target
    if manifest.get("status") not in {"complete", "partially_published"}:
        raise ValueError(f"audio manifest is not publishable: {manifest.get('status')}")
    for source, destination in ((draft, target), (analysis, published_analysis)):
        if destination.exists() and destination.read_bytes() != source.read_bytes():
            raise ValueError(f"published package conflicts with immutable target: {destination}")
    manifest["status"] = "partially_published"
    temporary_manifest = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    temporary_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    os.replace(temporary_manifest, manifest_path)

    def atomic_copy(source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if destination.read_bytes() != source.read_bytes():
                raise ValueError(f"published package conflicts with immutable target: {destination}")
            return
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        shutil.copyfile(source, temporary)
        os.replace(temporary, destination)

    atomic_copy(draft, target)
    atomic_copy(analysis, published_analysis)
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
            asset["asset"]["review_status"] = "approved"
    manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return draft


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate or publish a daily lesson.")
    parser.add_argument("command", choices=("generate", "generate-content", "generate-audio", "review", "publish"))
    parser.add_argument("--date", type=date.fromisoformat, default=application_date())
    args = parser.parse_args()
    path = {
        "generate": generate,
        "generate-content": generate_content,
        "generate-audio": generate_audio,
        "review": review,
        "publish": publish,
    }[args.command](args.date)
    print(path)


if __name__ == "__main__":
    main()
