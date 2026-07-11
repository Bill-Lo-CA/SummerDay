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


VIKIDIA_API = "https://fr.vikidia.org/w/api.php"
OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_CONTENT_MODEL", "qwen3:8b")
DATA_DIR = Path(os.getenv("SOMEADAY_DATA_DIR", "data"))


@dataclass(frozen=True)
class SourceArticle:
    page_id: int
    revision_id: int
    title: str
    url: str
    retrieved_at: str
    text: str


def request_json(url: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode() if payload else None
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "SomeADay/0.1"},
    )
    with urlopen(request, timeout=180) as response:
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


def fetch_vikidia_article() -> SourceArticle:
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
    for page in pages:
        segment = clean_segment(page.get("extract", ""))
        if segment:
            revision = page["revisions"][0]
            return SourceArticle(
                page_id=page["pageid"],
                revision_id=revision["revid"],
                title=page["title"],
                url=page["fullurl"],
                retrieved_at=datetime.now(timezone.utc).isoformat(),
                text=segment,
            )
    raise RuntimeError("Vikidia returned no article with a usable 90–160 word segment.")


def ollama_generate(prompt: str) -> dict:
    response = request_json(
        f"{OLLAMA_URL}/api/chat",
        {
            "model": OLLAMA_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "format": DailyLesson.model_json_schema(),
            "stream": False,
            "think": False,
            "options": {"temperature": 0.2},
        },
    )
    return json.loads(response["message"]["content"])


def lesson_prompt(source: SourceArticle, lesson_date: date) -> str:
    return f"""Create an A1 French lesson for {lesson_date.isoformat()} from only the source text below.
Return JSON matching the supplied schema. Select 8–12 useful core lexical items. Keep pronominal verbs and multiword expressions complete. Every surface_form, source_sentence, morphology evidence, and pronunciation evidence must occur verbatim in article_text. Definitions must be short French explanations; English hints are rescue translations. Do not invent source facts.

Set these fields exactly:
id: vikidia-{source.page_id}-{source.revision_id}-{lesson_date.isoformat()}
source_title: {source.title}
source_url: {source.url}
source_revision: {source.revision_id}
article_text: {source.text}

Source text:
{source.text}"""


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


def generate_lesson(
    source: SourceArticle,
    lesson_date: date,
    generator: Callable[[str], dict] = ollama_generate,
) -> DailyLesson:
    prompt = lesson_prompt(source, lesson_date)
    error = ""
    for _ in range(2):
        try:
            payload = apply_source_fields(generator(prompt), source, lesson_date)
            payload = deduplicate_vocabulary(payload)
            return validate_evidence(DailyLesson.model_validate(payload))
        except (ValidationError, ValueError, KeyError, json.JSONDecodeError) as exc:
            error = str(exc)
            prompt += f"\n\nRepair the JSON. Validation errors:\n{error}"
    raise RuntimeError(f"Ollama output remained invalid after one repair: {error}")


def generate(lesson_date: date) -> Path:
    source = fetch_vikidia_article()
    lesson = generate_lesson(source, lesson_date)
    draft = DATA_DIR / "drafts" / f"{lesson_date.isoformat()}.json"
    draft.parent.mkdir(parents=True, exist_ok=True)
    draft.write_text(lesson.model_dump_json(indent=2) + "\n")
    return draft


def publish(lesson_date: date) -> Path:
    draft = DATA_DIR / "drafts" / f"{lesson_date.isoformat()}.json"
    target = DATA_DIR / "lessons" / draft.name
    if target.exists():
        raise FileExistsError(f"Published lesson is immutable: {target}")
    lesson = validate_evidence(DailyLesson.model_validate_json(draft.read_text()))
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(draft, target)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate or publish a daily lesson.")
    parser.add_argument("command", choices=("generate", "publish"))
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    path = generate(args.date) if args.command == "generate" else publish(args.date)
    print(path)


if __name__ == "__main__":
    main()
