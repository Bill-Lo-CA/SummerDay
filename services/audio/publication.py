import json
from pathlib import Path

from services.api.schemas import DailyLesson
from services.audio.validation import validate_audio_asset


def validate_publishable_lesson(lesson: DailyLesson, media_root: Path) -> DailyLesson:
    if lesson.speech_profile is None or lesson.learning_audio is None:
        raise ValueError("published lesson requires a speech profile and learning audio")
    if not lesson.sentences:
        raise ValueError("published lesson requires deterministic sentence audio")
    if lesson.pronunciation_focus.target_phrase is None:
        raise ValueError("pronunciation focus requires a target phrase")
    focus = lesson.pronunciation_focus
    if focus.review_status != "approved" or focus.reference_audio is None:
        raise ValueError("pronunciation focus audio requires approval")
    validate_audio_asset(lesson.learning_audio, media_root)
    for sentence in lesson.sentences:
        validate_audio_asset(sentence.learning_audio, media_root)
    for item in lesson.core_vocabulary:
        if item.audio is None:
            raise ValueError(f"vocabulary audio is missing: {item.lexical_item}")
        validate_audio_asset(item.audio, media_root)
    validate_audio_asset(focus.reference_audio, media_root)
    if lesson.natural_audio:
        validate_audio_asset(lesson.natural_audio, media_root)
    for sentence in lesson.sentences:
        if sentence.natural_audio:
            validate_audio_asset(sentence.natural_audio, media_root)
    return lesson


def mark_audio_published(lesson: DailyLesson, media_root: Path) -> None:
    manifest_path = media_root / "lessons" / lesson.id / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["status"] = "published"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
