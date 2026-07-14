import json
import os
from pathlib import Path

from services.api.schemas import DailyLesson
from services.audio.validation import validate_audio_asset


def _atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    os.replace(temporary, path)


def validate_publishable_audio(asset, media_root: Path) -> None:
    if asset.provider == "fake":
        raise ValueError("fake audio cannot be published")
    validate_audio_asset(asset, media_root)


def validate_publishable_lesson(lesson: DailyLesson, media_root: Path) -> DailyLesson:
    if lesson.speech_profile is None or lesson.learning_audio is None:
        raise ValueError("published lesson requires a speech profile and learning audio")
    if not lesson.sentences:
        raise ValueError("published lesson requires deterministic sentence audio")
    if lesson.pronunciation_focus.target_phrase is None:
        raise ValueError("pronunciation focus requires a target phrase")
    focus = lesson.pronunciation_focus
    if (
        focus.review_status != "approved"
        or focus.reference_audio is None
        or focus.reference_audio.review_status != "approved"
    ):
        raise ValueError("pronunciation focus audio requires approval")
    validate_publishable_audio(lesson.learning_audio, media_root)
    for sentence in lesson.sentences:
        validate_publishable_audio(sentence.learning_audio, media_root)
    for item in lesson.core_vocabulary:
        if item.audio is None:
            raise ValueError(f"vocabulary audio is missing: {item.lexical_item}")
        validate_publishable_audio(item.audio, media_root)
    validate_publishable_audio(focus.reference_audio, media_root)
    if lesson.natural_audio:
        validate_publishable_audio(lesson.natural_audio, media_root)
    for sentence in lesson.sentences:
        if sentence.natural_audio:
            validate_publishable_audio(sentence.natural_audio, media_root)
    manifest_path = media_root / "lessons" / lesson.id / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("lesson_id") != lesson.id:
        raise ValueError("audio manifest lesson ID does not match the lesson")
    expected = {
        asset.asset_id: (asset.path, asset.sha256)
        for asset in [
            lesson.learning_audio,
            *(sentence.learning_audio for sentence in lesson.sentences),
            *(item.audio for item in lesson.core_vocabulary),
            focus.reference_audio,
            lesson.natural_audio,
            *(sentence.natural_audio for sentence in lesson.sentences),
        ]
        if asset is not None
    }
    actual = {
        entry["asset_id"]: (entry["path"], entry.get("asset", {}).get("sha256"))
        for entry in manifest.get("assets", [])
        if entry.get("status") == "complete"
    }
    if any(actual.get(asset_id) != details for asset_id, details in expected.items()):
        raise ValueError("audio manifest does not match the validated lesson assets")
    return lesson


def mark_audio_published(lesson: DailyLesson, media_root: Path) -> None:
    manifest_path = media_root / "lessons" / lesson.id / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["status"] = "published"
    _atomic_json(manifest_path, manifest)
