import hashlib
import json
from pathlib import Path
from typing import Protocol

from services.api.schemas import DailyLesson
from services.audio.models import AudioAssetRef, LessonSentence, SpeechProfile
from services.audio.hashing import sha256_file
from services.nlp import NLPAnalysis
from services.providers.tts import AudioGenerationResult


class Synthesizer(Protocol):
    def synthesize(self, text: str, output_path: Path, profile: SpeechProfile) -> AudioGenerationResult:
        ...


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
    return AudioAssetRef(
        asset_id=f"{lesson_id}:{relative_path}",
        path=relative_path,
        sha256=sha256_file(output),
        mime_type=result.mime_type,
        duration_ms=result.duration_ms,
        provider=result.provider,
        model=result.model,
        voice=result.voice,
        speech_rate=result.speech_rate,
        review_status="pending",
    )


def attach_required_audio(
    lesson: DailyLesson,
    analysis: NLPAnalysis,
    provider: Synthesizer,
    media_root: Path,
) -> DailyLesson:
    profile = lesson.speech_profile or default_speech_profile(lesson.level)
    lesson.speech_profile = profile
    package = media_root / "lessons" / lesson.id
    package.mkdir(parents=True, exist_ok=True)
    prefix = f"lessons/{lesson.id}"
    lesson.learning_audio = _asset(
        lesson.id, f"{prefix}/segment-learning.opus", lesson.article_text, profile, provider, media_root
    )
    lesson.sentences = [
        LessonSentence(
            id=sentence_id(index, sentence.text),
            index=index,
            text=sentence.text,
            learning_audio=_asset(
                lesson.id,
                f"{prefix}/sentences/{sentence_id(index, sentence.text)}.opus",
                sentence.text,
                profile,
                provider,
                media_root,
            ),
        )
        for index, sentence in enumerate(analysis.sentences)
    ]
    for index, item in enumerate(lesson.core_vocabulary):
        item.spoken_text = item.spoken_text or item.lexical_item
        item.audio = _asset(
            lesson.id,
            f"{prefix}/vocabulary/{index:02d}.opus",
            item.spoken_text,
            profile,
            provider,
            media_root,
        )
    focus = lesson.pronunciation_focus
    focus.target_phrase = focus.target_phrase or focus.evidence
    focus.reference_audio = _asset(
        lesson.id,
        f"{prefix}/pronunciation/focus.opus",
        focus.target_phrase,
        profile,
        provider,
        media_root,
    )
    manifest = {
        "lesson_id": lesson.id,
        "status": "draft",
        "assets": [
            lesson.learning_audio.model_dump(),
            *(sentence.learning_audio.model_dump() for sentence in lesson.sentences),
            *(item.audio.model_dump() for item in lesson.core_vocabulary if item.audio),
            focus.reference_audio.model_dump(),
        ],
    }
    (package / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return lesson
