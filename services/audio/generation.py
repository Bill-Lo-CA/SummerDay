import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from services.api.schemas import DailyLesson
from services.audio.models import AudioAssetRef, LessonSentence, SpeechProfile
from services.audio.hashing import sha256_file
from services.nlp import NLPAnalysis
from services.providers.tts import AudioGenerationResult
from services.providers.fake_tts import FakeTTSProvider
from services.audio.validation import validate_audio_asset, wav_metadata


class Synthesizer(Protocol):
    def synthesize(self, text: str, output_path: Path, profile: SpeechProfile) -> AudioGenerationResult:
        ...


class AudioGenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class AudioTask:
    asset_id: str
    relative_path: str
    text: str


def default_speech_profile(level: str) -> SpeechProfile:
    return SpeechProfile(
        level=level if level in {"A1", "A2"} else "A1",
        learning_target_wpm=85 if level == "A1" else 100,
        natural_target_wpm=105 if level == "A1" else 125,
        pause_style="clear",
        articulation="natural",
        connected_speech="light",
    )


def sentence_id(index: int, text: str) -> str:
    digest = hashlib.sha256(text.encode()).hexdigest()[:16]
    return f"sentence-{index:03d}-{digest}"


def _asset(
    lesson_id: str,
    relative_path: str,
    text: str,
    profile: SpeechProfile,
    provider: Synthesizer,
    media_root: Path,
) -> AudioAssetRef:
    if relative_path.startswith(f"lessons/{lesson_id}/") is False:
        raise ValueError("lesson audio path must use the lesson package directory")
    output = (media_root / relative_path).resolve()
    root = media_root.resolve()
    output.relative_to(root)
    if (media_root / "lessons" / lesson_id / "manifest.json").exists():
        manifest = json.loads((media_root / "lessons" / lesson_id / "manifest.json").read_text())
        if manifest.get("status") == "published":
            raise FileExistsError(f"published lesson audio is immutable: {lesson_id}")
    result = provider.synthesize(text, output, profile)
    metadata = wav_metadata(output)
    measured_wpm = len(text.split()) * 60_000 / metadata.duration_ms
    return AudioAssetRef(
        asset_id=f"{lesson_id}:{relative_path}",
        path=relative_path,
        sha256=sha256_file(output),
        mime_type=result.mime_type,
        duration_ms=metadata.duration_ms,
        provider=result.provider,
        model=result.model,
        voice=result.voice,
        speech_rate=measured_wpm,
        target_wpm=result.target_wpm or float(profile.learning_target_wpm),
        measured_wpm=measured_wpm,
        length_scale=result.length_scale,
        sample_rate=metadata.sample_rate,
        review_status="pending",
    )


def attach_required_audio(
    lesson: DailyLesson,
    analysis: NLPAnalysis,
    provider: Synthesizer,
    media_root: Path,
    on_progress: Callable[[DailyLesson], None] | None = None,
) -> DailyLesson:
    profile = lesson.speech_profile or default_speech_profile(lesson.level)
    lesson.speech_profile = profile
    package = media_root / "lessons" / lesson.id
    package.mkdir(parents=True, exist_ok=True)
    prefix = f"lessons/{lesson.id}"
    manifest_path = package / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("status") == "published":
            raise FileExistsError(f"published lesson audio is immutable: {lesson.id}")
    else:
        manifest = {"lesson_id": lesson.id, "status": "pending", "assets": []}
    entries = {
        entry["asset_id"]: entry if "status" in entry else {"asset_id": entry["asset_id"], "path": entry["path"], "status": "complete", "asset": entry}
        for entry in manifest.get("assets", [])
    }
    errors = []

    def write_manifest() -> None:
        manifest["assets"] = list(entries.values())
        manifest["status"] = "failed" if errors else "pending"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        if on_progress:
            on_progress(lesson)

    def run(task: AudioTask, existing, assign: Callable[[AudioAssetRef], None]) -> None:
        try:
            if existing is not None and not (existing.provider == "fake" and not isinstance(provider, FakeTTSProvider)):
                try:
                    validate_audio_asset(existing, media_root)
                    asset = existing
                except ValueError:
                    asset = _asset(lesson.id, task.relative_path, task.text, profile, provider, media_root)
            else:
                asset = _asset(lesson.id, task.relative_path, task.text, profile, provider, media_root)
            assign(asset)
            entries[task.asset_id] = {
                "asset_id": task.asset_id,
                "path": task.relative_path,
                "status": "complete",
                "asset": asset.model_dump(),
            }
        except Exception as exc:
            entries[task.asset_id] = {
                "asset_id": task.asset_id,
                "path": task.relative_path,
                "status": "failed",
                "error": str(exc),
            }
            errors.append(task.asset_id)
        write_manifest()

    run(
        AudioTask(f"{lesson.id}:{prefix}/segment-learning.wav", f"{prefix}/segment-learning.wav", lesson.article_text),
        lesson.learning_audio,
        lambda asset: setattr(lesson, "learning_audio", asset),
    )
    existing_sentences = {sentence.id: sentence for sentence in lesson.sentences}
    lesson.sentences = []
    for index, sentence in enumerate(analysis.sentences):
        identifier = sentence_id(index, sentence.text)
        previous = existing_sentences.get(identifier)
        result = {"asset": previous.learning_audio if previous else None}
        task = AudioTask(f"{lesson.id}:{prefix}/sentences/{identifier}.wav", f"{prefix}/sentences/{identifier}.wav", sentence.text)
        run(task, result["asset"], lambda asset: result.update(asset=asset))
        if result["asset"] is not None:
            lesson.sentences.append(
                LessonSentence(id=identifier, index=index, text=sentence.text, learning_audio=result["asset"])
            )
    for index, item in enumerate(lesson.core_vocabulary):
        item.spoken_text = item.spoken_text or item.lexical_item
        task = AudioTask(f"{lesson.id}:{prefix}/vocabulary/{index:02d}.wav", f"{prefix}/vocabulary/{index:02d}.wav", item.spoken_text)
        run(task, item.audio, lambda asset, item=item: setattr(item, "audio", asset))
    focus = lesson.pronunciation_focus
    focus.target_phrase = focus.target_phrase or focus.evidence
    task = AudioTask(f"{lesson.id}:{prefix}/pronunciation/focus.wav", f"{prefix}/pronunciation/focus.wav", focus.target_phrase)
    run(task, focus.reference_audio, lambda asset: setattr(focus, "reference_audio", asset))
    manifest["status"] = "complete" if not errors else "failed"
    manifest["assets"] = list(entries.values())
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    if on_progress:
        on_progress(lesson)
    if errors:
        raise AudioGenerationError(f"audio generation failed for: {', '.join(errors)}")
    return lesson
